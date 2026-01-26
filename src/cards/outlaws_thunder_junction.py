"""
Outlaws_of_Thunder_Junction (OTJ) Card Implementations

Real card data fetched from Scryfall API.
276 cards in set.
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
    make_damage_trigger, make_upkeep_trigger, make_end_step_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, create_target_choice, create_modal_choice
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

# Helper: Check if a creature is an outlaw (Assassin, Mercenary, Pirate, Rogue, Warlock)
OUTLAW_TYPES = {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"}

def is_outlaw(obj: GameObject) -> bool:
    """Check if a creature is an outlaw type."""
    return bool(obj.characteristics.subtypes & OUTLAW_TYPES)


def other_outlaws_you_control(source: GameObject):
    """Filter: Other outlaws you control."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                is_outlaw(target) and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


# -----------------------------------------------------------------------------
# WHITE CARDS
# -----------------------------------------------------------------------------

def holy_cow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 2 life and scry 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sterling_supplier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, put a +1/+1 counter on another target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - placeholder creates counter event
        return []
    return [make_etb_trigger(obj, etb_effect)]


def prosperity_tycoon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def stagecoach_security_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, creatures you control get +1/+1 and vigilance until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Creates temporary buff event
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump_all',
                'controller': obj.controller,
                'power_mod': 1,
                'toughness_mod': 1,
                'keywords': ['vigilance'],
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def wanted_griffin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create a Mercenary token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def outlaw_medic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, draw a card."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def vengeful_townsfolk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more other creatures you control die, put a +1/+1 counter on this creature."""
    def other_creature_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj_id = event.payload.get('object_id')
        if dying_obj_id == source.id:
            return False
        dying_obj = state.objects.get(dying_obj_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == source.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def death_trigger_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_death_trigger(obj, death_trigger_effect, other_creature_dies_filter)]


def claim_jumper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if opponent controls more lands, search for Plains."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library search not fully implemented - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


def frontier_seeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, look at top 5, may reveal Mount or Plains."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library manipulation not fully implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def shepherd_of_clouds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return target permanent card mv 3 or less from graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Graveyard recursion with targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def fortune_loyal_steed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Fortune enters, scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# BLUE CARDS
# -----------------------------------------------------------------------------

def harrier_strix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, tap target permanent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def loan_shark_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you've cast two+ spells this turn, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check spell count this turn - simplified, always triggers for now
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def peerless_ropemaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return up to one target tapped creature to its owner's hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Bounce effect - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def outlaw_stitcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Zombie Rogue token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Zombie Rogue Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Zombie', 'Rogue'],
                'colors': [Color.BLUE, Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def geralf_the_fleshwright_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell during your turn other than your first, create a Zombie Rogue."""
    # Complex trigger - simplified placeholder
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Zombie Rogue Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Zombie', 'Rogue'],
                'colors': [Color.BLUE, Color.BLACK]
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, spell_cast_effect)]


def nimble_brigand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature deals combat damage to a player, draw a card."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def spring_splasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, target creature defending player controls gets -3/-0."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required
        return []
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# BLACK CARDS
# -----------------------------------------------------------------------------

def ambush_gigapede_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature an opponent controls gets -2/-2 until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def desperate_bloodseeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target player mills two cards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required - mills opponent
        return []
    return [make_etb_trigger(obj, etb_effect)]


def nezumi_linkbreaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create a Mercenary token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def vault_plunderer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target player draws a card and loses 1 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Can target self or opponent - simplified to self
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
    return [make_etb_trigger(obj, etb_effect)]


def rictus_robber_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if a creature died this turn, create a Zombie Rogue token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check if creature died this turn - simplified, always triggers
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Zombie Rogue Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Zombie', 'Rogue'],
                'colors': [Color.BLUE, Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def rooftop_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, destroy target creature an opponent controls that was dealt damage this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Conditional destruction - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def gisa_the_hellraiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Skeletons and Zombies you control get +1/+1 and have menace."""
    def affects_zombie_or_skeleton(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                ("Zombie" in target.characteristics.subtypes or
                 "Skeleton" in target.characteristics.subtypes) and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors = make_static_pt_boost(obj, 1, 1, affects_zombie_or_skeleton)
    interceptors.append(make_keyword_grant(obj, ['menace'], affects_zombie_or_skeleton))
    return interceptors


def hollow_marauder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target opponents each discard a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Discard targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def rakish_crew_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def tinybones_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Tinybones Joins Up enters, target players each discard a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Discard effect - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# RED CARDS
# -----------------------------------------------------------------------------

def cunning_coyote_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, another target creature gets +1/+1 and haste until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def discerning_peddler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may discard a card. If you do, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Looting effect
        return []
    return [make_etb_trigger(obj, etb_effect)]


def hellspur_posse_boss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other outlaws you control have haste. When this enters, create two Mercenary tokens."""
    interceptors = []

    # Grant haste to other outlaws
    interceptors.append(make_keyword_grant(obj, ['haste'], other_outlaws_you_control(obj)))

    # ETB: Create two Mercenary tokens
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Mercenary Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Mercenary'],
                    'colors': [Color.RED]
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Mercenary Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Mercenary'],
                    'colors': [Color.RED]
                },
                source=obj.id
            )
        ]

    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors


def prickly_pair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def mine_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you control another outlaw, create a Treasure token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check for other outlaw - simplified
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


def irascible_wolverine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, exile the top card of your library. Until end of turn, you may play that card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Impulse draw - library manipulation required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def scalestorm_summoner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, create a 3/1 red Dinosaur token if you control a creature with power 4+."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Check for power 4+ creature - simplified
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dinosaur Token',
                'controller': obj.controller,
                'power': 3,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Dinosaur'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def terror_of_the_peaks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control enters, this deals damage equal to that creature's power to any target."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if entering_obj:
            power = entering_obj.characteristics.power or 0
            # Would need targeting - placeholder
            return []
        return []

    return [make_etb_trigger(obj, creature_etb_effect, creature_etb_filter)]


def ertha_jo_frontier_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Ertha Jo enters, create a Mercenary token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# GREEN CARDS
# -----------------------------------------------------------------------------

def beastbond_outcaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you control a creature with power 4+, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check for power 4+ creature - simplified
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def goldvein_hydra_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create Treasure tokens equal to its power."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Would need to track power at death
        power = obj.characteristics.power or 0
        events = []
        for _ in range(power):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Treasure Token',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Treasure'],
                    'colors': []
                },
                source=obj.id
            ))
        return events
    return [make_death_trigger(obj, death_effect)]


def outcaster_greenblade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, search for a basic land or Desert card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library search - not fully implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def outcaster_trailblazer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, add one mana of any color. Whenever another power 4+ creature enters, draw a card."""
    interceptors = []

    # ETB mana
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MANA_ADDED,
            payload={'player': obj.controller, 'mana': 'any', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Draw on big creature ETB
    def big_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
                CardType.CREATURE in entering_obj.characteristics.types and
                (entering_obj.characteristics.power or 0) >= 4)

    def big_creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, big_creature_etb_effect, big_creature_etb_filter))
    return interceptors


def patient_naturalist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, mill three cards. Put a land card from among them into your hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Mill effect
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def railway_brawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control enters, put +1/+1 counters on it equal to its power."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if entering_obj:
            power = entering_obj.characteristics.power or 0
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': entering_id, 'counter_type': '+1/+1', 'amount': power},
                source=obj.id
            )]
        return []

    return [make_etb_trigger(obj, creature_etb_effect, creature_etb_filter)]


def spinewoods_paladin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# MULTICOLOR CARDS
# -----------------------------------------------------------------------------

def annie_flash_the_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Annie Flash enters, if you cast it, return target permanent card mv 3 or less from graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Graveyard recursion with targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def annie_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def baron_bertram_graywater_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more tokens you control enter, create a 1/1 Vampire Rogue with lifelink."""
    def token_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        # Check if it's a token controlled by us
        return (entering_obj.controller == source.controller and
                entering_obj.state.is_token)

    def token_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Vampire Rogue Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Vampire', 'Rogue'],
                'colors': [Color.BLACK],
                'keywords': ['lifelink']
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, token_etb_effect, token_etb_filter)]


def bonny_pall_clearcutter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Bonny Pall enters, create Beau, a legendary blue Ox creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Beau',
                'controller': obj.controller,
                'power': 0,  # Variable based on lands
                'toughness': 0,
                'types': [CardType.CREATURE],
                'subtypes': ['Ox'],
                'supertypes': ['Legendary'],
                'colors': [Color.BLUE]
            },
            source=obj.id
        )]

    interceptors = [make_etb_trigger(obj, etb_effect)]

    # Whenever you attack, draw a card
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors


def bruse_tarl_roving_rancher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Oxen you control have double strike."""
    def affects_oxen(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                "Ox" in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    return [make_keyword_grant(obj, ['double_strike'], affects_oxen)]


def honest_rutstein_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Honest Rutstein enters, return target creature card from your graveyard to your hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Graveyard recursion - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def intimidation_campaign_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, each opponent loses 1 life, you gain 1 life, and you draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
        # Each opponent loses 1 life
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def jem_lightfoote_sky_explorer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Check if no spell cast from hand - simplified
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def kellan_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a legendary creature you control enters, put a +1/+1 counter on each creature you control."""
    def legendary_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
                "Legendary" in (entering_obj.characteristics.supertypes or set()))

    def legendary_etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, target in state.objects.items():
            if (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj_id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events

    return [make_etb_trigger(obj, legendary_etb_effect, legendary_etb_filter)]


def kraum_violent_cacophony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, put a +1/+1 counter on Kraum and draw a card."""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_spell_cast_trigger(obj, spell_cast_effect)]


def malcolm_the_eyes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, investigate."""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, spell_cast_effect)]


def miriam_herd_whisperer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Mount or Vehicle you control attacks, put a +1/+1 counter on it."""
    def mount_or_vehicle_attacks_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        # Check for Mount or Vehicle subtypes (Vehicle is an artifact subtype, not a CardType)
        subtypes = attacker.characteristics.subtypes
        return (attacker.controller == source.controller and
                ("Mount" in subtypes or "Vehicle" in subtypes))

    def mount_attack_effect(event: Event, state: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id')
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': attacker_id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_attack_trigger(obj, mount_attack_effect, mount_or_vehicle_attacks_filter)]


def ruthless_lawbringer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may sacrifice another creature. When you do, destroy target nonland permanent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Sacrifice + destroy - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def selvala_eager_trailblazer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a creature spell, create a Mercenary token."""
    def creature_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Mercenary Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Mercenary'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, creature_cast_effect, spell_type_filter={CardType.CREATURE})]


def vial_smasher_gleeful_grenadier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another outlaw you control enters, Vial Smasher deals 1 damage to target opponent."""
    def outlaw_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
                CardType.CREATURE in entering_obj.characteristics.types and
                is_outlaw(entering_obj))

    def outlaw_etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting required - simplified to first opponent
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                )]
        return []

    return [make_etb_trigger(obj, outlaw_etb_effect, outlaw_etb_filter)]


def vraska_joins_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Vraska Joins Up enters, put a deathtouch counter on each creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, target in state.objects.items():
            if (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj_id, 'counter_type': 'deathtouch', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def wrangler_of_the_damned_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, create a Spirit token."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Spirit Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Spirit'],
                'colors': [Color.WHITE],
                'keywords': ['flying']
            },
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


# -----------------------------------------------------------------------------
# ARTIFACT CREATURES
# -----------------------------------------------------------------------------

def oasis_gardener_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def silver_deputy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may search for a basic land or Desert card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library search not implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def sterling_hound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, surveil 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# MORE SETUP FUNCTIONS
# -----------------------------------------------------------------------------

def slickshot_showoff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a noncreature spell, this creature gets +2/+0 until end of turn."""
    def noncreature_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target': obj.id,
                'power_mod': 2,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]

    def is_noncreature_spell(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    return [make_spell_cast_trigger(obj, noncreature_cast_effect, filter_fn=is_noncreature_spell)]


def razzledazzler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, put a +1/+1 counter on this creature."""
    def second_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, second_spell_effect)]


def ironfist_pulverizer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, this deals 2 damage to target opponent."""
    def second_spell_effect(event: Event, state: GameState) -> list[Event]:
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 2, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                )]
        return []
    return [make_spell_cast_trigger(obj, second_spell_effect)]


def blacksnag_buzzard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature enters with a +1/+1 counter on it if a creature died this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - always adds counter
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def blood_hustler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, put a +1/+1 counter on this creature."""
    # Simplified - triggers on targeting opponents
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return []  # Crime tracking not fully implemented


def raven_of_fell_omens_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, each opponent loses 1 life and you gain 1 life."""
    # Crime tracking not implemented - placeholder
    return []


def canyon_crab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, draw and discard."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_end_step_trigger(obj, end_step_effect)]


def prairie_dog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, +1/+1 counter."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def inventive_wingsmith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you haven't cast a spell from your hand this turn, put a flying counter."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'flying', 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def shepherd_of_clouds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return target permanent card mv 3 or less from your graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Graveyard recursion - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def nurturing_pixie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return up to one target non-Faerie, nonland permanent you control to its owner's hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Bounce effect with counter - targeting required
        return []
    return [make_etb_trigger(obj, etb_effect)]


def magda_the_hoardmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, create a tapped Treasure token."""
    # Crime tracking not implemented - placeholder
    return []


def rodeo_pyromancers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your first spell each turn, add RR."""
    def first_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MANA_ADDED,
            payload={'player': obj.controller, 'mana': 'RR', 'amount': 2},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, first_spell_effect)]


def trained_arynx_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks while saddled, it gains first strike until end of turn. Scry 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def bridled_bighorn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks while saddled, create a 1/1 white Sheep creature token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Sheep Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Sheep'],
                'colors': [Color.WHITE]
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def bounding_felidar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks while saddled, put a +1/+1 counter on each other creature you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, target in state.objects.items():
            if (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj_id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]


def caustic_bronco_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, reveal the top card and put it into your hand."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def duelist_of_the_mind_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Power is equal to the number of cards drawn this turn."""
    # Dynamic power tracking not fully implemented
    return []


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

ANOTHER_ROUND = make_sorcery(
    name="Another Round",
    mana_cost="{X}{X}{2}{W}",
    colors={Color.WHITE},
    text="Exile any number of creatures you control, then return them to the battlefield under their owner's control. Then repeat this process X more times.",
)

ARCHANGEL_OF_TITHES = make_creature(
    name="Archangel of Tithes",
    power=3, toughness=5,
    mana_cost="{1}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nAs long as this creature is untapped, creatures can't attack you or planeswalkers you control unless their controller pays {1} for each of those creatures.\nAs long as this creature is attacking, creatures can't block unless their controller pays {1} for each of those creatures.",
)

ARMORED_ARMADILLO = make_creature(
    name="Armored Armadillo",
    power=0, toughness=4,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Armadillo"},
    text="Ward {1} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\n{3}{W}: This creature gets +X/+0 until end of turn, where X is its toughness.",
)

AVEN_INTERRUPTER = make_creature(
    name="Aven Interrupter",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Rogue"},
    text="Flash\nFlying\nWhen this creature enters, exile target spell. It becomes plotted. (Its owner may cast it as a sorcery on a later turn without paying its mana cost.)\nSpells your opponents cast from graveyards or from exile cost {2} more to cast.",
)

BOUNDING_FELIDAR = make_creature(
    name="Bounding Felidar",
    power=4, toughness=7,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat", "Mount"},
    text="Whenever this creature attacks while saddled, put a +1/+1 counter on each other creature you control. You gain 1 life for each of those creatures.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=bounding_felidar_setup,
)

# =============================================================================
# BOVINE INTERVENTION - Targeted removal with token compensation
# =============================================================================

def _bovine_intervention_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Bovine Intervention after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Verify target is still an artifact or creature
    types = target.characteristics.types
    if CardType.ARTIFACT not in types and CardType.CREATURE not in types:
        return []

    controller = target.controller
    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': controller,
                'name': 'Ox',
                'power': 2,
                'toughness': 2,
                'types': {CardType.CREATURE},
                'subtypes': {'Ox'},
                'colors': {Color.WHITE},
                'is_token': True
            },
            source=choice.source_id
        )
    ]


def bovine_intervention_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Bovine Intervention: Destroy target artifact or creature.
    Its controller creates a 2/2 white Ox creature token.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Bovine Intervention":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "bovine_intervention_spell"

    # Find valid targets: artifacts or creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            types = obj.characteristics.types
            if CardType.ARTIFACT in types or CardType.CREATURE in types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an artifact or creature to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _bovine_intervention_execute

    return []


BOVINE_INTERVENTION = make_instant(
    name="Bovine Intervention",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or creature. Its controller creates a 2/2 white Ox creature token.",
    resolve=bovine_intervention_resolve,
)

BRIDLED_BIGHORN = make_creature(
    name="Bridled Bighorn",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Mount", "Sheep"},
    text="Vigilance\nWhenever this creature attacks while saddled, create a 1/1 white Sheep creature token.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=bridled_bighorn_setup,
)

CLAIM_JUMPER = make_creature(
    name="Claim Jumper",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mercenary", "Rabbit"},
    text="Vigilance\nWhen this creature enters, if an opponent controls more lands than you, you may search your library for a Plains card and put it onto the battlefield tapped. Then if an opponent controls more lands than you, repeat this process once. If you search your library this way, shuffle.",
    setup_interceptors=claim_jumper_setup,
)

DUST_ANIMUS = make_creature(
    name="Dust Animus",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nIf you control five or more untapped lands, this creature enters with two +1/+1 counters and a lifelink counter on it.\nPlot {1}{W} (You may pay {1}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

# =============================================================================
# ERIETTE'S LULLABY - Destroy tapped creature + life gain
# =============================================================================

def _eriettes_lullaby_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Eriette's Lullaby after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Verify still tapped
    if not target.state.tapped:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': controller, 'amount': 2},
            source=choice.source_id
        )
    ]


def eriettes_lullaby_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Eriette's Lullaby: Destroy target tapped creature. You gain 2 life.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Eriette's Lullaby":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "eriettes_lullaby_spell"

    # Find valid targets: tapped creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types and obj.state.tapped:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a tapped creature to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _eriettes_lullaby_execute

    return []


ERIETTES_LULLABY = make_sorcery(
    name="Eriette's Lullaby",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target tapped creature. You gain 2 life.",
    resolve=eriettes_lullaby_resolve,
)

# =============================================================================
# FINAL SHOWDOWN - Spree board wipe / ability removal / protection
# =============================================================================

def _final_showdown_indestructible_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Final Showdown indestructible mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'grant_keywords',
            'target_id': target_id,
            'keywords': ['indestructible'],
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def _final_showdown_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Final Showdown modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: All creatures lose all abilities until end of turn
    if 0 in selected_modes:
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    events.append(Event(
                        type=EventType.TEMPORARY_EFFECT,
                        payload={
                            'effect': 'lose_all_abilities',
                            'target_id': obj.id,
                            'duration': 'end_of_turn'
                        },
                        source=spell_id
                    ))

    # Mode 1: Choose a creature you control. It gains indestructible until end of turn.
    if 1 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and obj.controller == controller_id:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature you control to gain indestructible",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _final_showdown_indestructible_execute
            return events  # Wait for target selection

    # Mode 2: Destroy all creatures
    if 2 in selected_modes:
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    events.append(Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': obj.id},
                        source=spell_id
                    ))

    return events


def final_showdown_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Final Showdown - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1} — All creatures lose all abilities until end of turn.
    + {1} — Choose a creature you control. It gains indestructible until end of turn.
    + {3}{W}{W} — Destroy all creatures.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Final Showdown":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "final_showdown_spell"

    modes = [
        {"index": 0, "text": "All creatures lose all abilities until end of turn."},
        {"index": 1, "text": "Choose a creature you control. It gains indestructible until end of turn."},
        {"index": 2, "text": "Destroy all creatures."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=3,
        prompt="Final Showdown - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _final_showdown_mode_execute

    return []


FINAL_SHOWDOWN = make_instant(
    name="Final Showdown",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — All creatures lose all abilities until end of turn.\n+ {1} — Choose a creature you control. It gains indestructible until end of turn.\n+ {3}{W}{W} — Destroy all creatures.",
    resolve=final_showdown_resolve,
)

FORTUNE_LOYAL_STEED = make_creature(
    name="Fortune, Loyal Steed",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Mount"},
    supertypes={"Legendary"},
    text="When Fortune enters, scry 2.\nWhenever Fortune attacks while saddled, at end of combat, exile it and up to one creature that saddled it this turn, then return those cards to the battlefield under their owner's control.\nSaddle 1",
    setup_interceptors=fortune_loyal_steed_setup,
)

FRONTIER_SEEKER = make_creature(
    name="Frontier Seeker",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When this creature enters, look at the top five cards of your library. You may reveal a Mount creature card or a Plains card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=frontier_seeker_setup,
)

# =============================================================================
# GETAWAY GLAMER - Spree flicker/conditional removal
# =============================================================================

def _getaway_glamer_flicker_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Getaway Glamer flicker mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if target.is_token:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'to_zone': 'exile',
            'to_zone_type': ZoneType.EXILE,
            'reason': 'flickered',
            'return_at_end_step': True,
            'return_owner': target.owner
        },
        source=choice.source_id
    )]


def _getaway_glamer_destroy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Getaway Glamer destroy mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Check if no other creature has greater power
    from src.engine import get_power
    target_power = get_power(target, state)

    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.id != target_id:
            if CardType.CREATURE in obj.characteristics.types:
                if get_power(obj, state) > target_power:
                    return []  # Another creature has greater power, spell fizzles

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _getaway_glamer_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Getaway Glamer modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Flicker target nontoken creature
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    if not obj.is_token:
                        valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a nontoken creature to exile and return",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _getaway_glamer_flicker_execute
            return events

    # Mode 1: Destroy target creature if no other has greater power
    if 1 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature to destroy (if none has greater power)",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _getaway_glamer_destroy_execute

    return events


def getaway_glamer_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Getaway Glamer - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1} — Exile target nontoken creature. Return it at the next end step.
    + {2} — Destroy target creature if no other creature has greater power.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Getaway Glamer":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "getaway_glamer_spell"

    modes = [
        {"index": 0, "text": "Exile target nontoken creature. Return it at end step."},
        {"index": 1, "text": "Destroy target creature if no other has greater power."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Getaway Glamer - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _getaway_glamer_mode_execute

    return []


GETAWAY_GLAMER = make_instant(
    name="Getaway Glamer",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Exile target nontoken creature. Return it to the battlefield under its owner's control at the beginning of the next end step.\n+ {2} — Destroy target creature if no other creature has greater power.",
    resolve=getaway_glamer_resolve,
)

HIGH_NOON = make_enchantment(
    name="High Noon",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Each player can't cast more than one spell each turn.\n{4}{R}, Sacrifice this enchantment: It deals 5 damage to any target.",
)

HOLY_COW = make_creature(
    name="Holy Cow",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Ox"},
    text="Flash\nFlying\nWhen this creature enters, you gain 2 life and scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    setup_interceptors=holy_cow_setup,
)

INVENTIVE_WINGSMITH = make_creature(
    name="Inventive Wingsmith",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Dwarf"},
    text="At the beginning of your end step, if you haven't cast a spell from your hand this turn and this creature doesn't have a flying counter on it, put a flying counter on it.",
    setup_interceptors=inventive_wingsmith_setup,
)

LASSOED_BY_THE_LAW = make_enchantment(
    name="Lassoed by the Law",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.\nWhen this enchantment enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

MYSTICAL_TETHER = make_enchantment(
    name="Mystical Tether",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="You may cast this spell as though it had flash if you pay {2} more to cast it.\nWhen this enchantment enters, exile target artifact or creature an opponent controls until this enchantment leaves the battlefield.",
)

NURTURING_PIXIE = make_creature(
    name="Nurturing Pixie",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nWhen this creature enters, return up to one target non-Faerie, nonland permanent you control to its owner's hand. If a permanent was returned this way, put a +1/+1 counter on this creature.",
)

OMENPORT_VIGILANTE = make_creature(
    name="Omenport Vigilante",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="This creature has double strike as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

ONE_LAST_JOB = make_sorcery(
    name="One Last Job",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Return target creature card from your graveyard to the battlefield.\n+ {1} — Return target Mount or Vehicle card from your graveyard to the battlefield.\n+ {1} — Return target Aura or Equipment card from your graveyard to the battlefield attached to a creature you control.",
)

OUTLAW_MEDIC = make_creature(
    name="Outlaw Medic",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rogue"},
    text="Lifelink\nWhen this creature dies, draw a card.",
    setup_interceptors=outlaw_medic_setup,
)

PRAIRIE_DOG = make_creature(
    name="Prairie Dog",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Squirrel"},
    text="Lifelink\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, put a +1/+1 counter on this creature.\n{4}{W}: Until end of turn, if you would put one or more +1/+1 counters on a creature you control, put that many plus one +1/+1 counters on it instead.",
    setup_interceptors=prairie_dog_setup,
)

PROSPERITY_TYCOON = make_creature(
    name="Prosperity Tycoon",
    power=4, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="When this creature enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\n{2}, Sacrifice a token: This creature gains indestructible until end of turn. Tap it. (Damage and effects that say \"destroy\" don't destroy it.)",
    setup_interceptors=prosperity_tycoon_setup,
)

# =============================================================================
# REQUISITION RAID - Spree artifact/enchantment destruction + counters
# =============================================================================

def _requisition_raid_artifact_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Requisition Raid artifact destruction mode."""
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


def _requisition_raid_enchantment_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Requisition Raid enchantment destruction mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.ENCHANTMENT not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _requisition_raid_counters_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Requisition Raid counters mode."""
    target_player = selected[0] if selected else None
    if not target_player:
        return []

    events = []
    for obj in state.objects.values():
        if obj.controller == target_player and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=choice.source_id
                ))

    return events


def _requisition_raid_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Requisition Raid modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Destroy target artifact
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.ARTIFACT in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose an artifact to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _requisition_raid_artifact_execute
            return events

    # Mode 1: Destroy target enchantment
    if 1 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.ENCHANTMENT in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose an enchantment to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _requisition_raid_enchantment_execute
            return events

    # Mode 2: Put a +1/+1 counter on each creature target player controls
    if 2 in selected_modes:
        valid_targets = list(state.players.keys())

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a player to give +1/+1 counters to their creatures",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _requisition_raid_counters_execute

    return events


def requisition_raid_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Requisition Raid - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1} — Destroy target artifact.
    + {1} — Destroy target enchantment.
    + {1} — Put a +1/+1 counter on each creature target player controls.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Requisition Raid":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "requisition_raid_spell"

    modes = [
        {"index": 0, "text": "Destroy target artifact."},
        {"index": 1, "text": "Destroy target enchantment."},
        {"index": 2, "text": "Put a +1/+1 counter on each creature target player controls."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=3,
        prompt="Requisition Raid - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _requisition_raid_mode_execute

    return []


REQUISITION_RAID = make_sorcery(
    name="Requisition Raid",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Destroy target artifact.\n+ {1} — Destroy target enchantment.\n+ {1} — Put a +1/+1 counter on each creature target player controls.",
    resolve=requisition_raid_resolve,
)

RUSTLER_RAMPAGE = make_instant(
    name="Rustler Rampage",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Untap all creatures target player controls.\n+ {1} — Target creature gains double strike until end of turn.",
)

SHEPHERD_OF_THE_CLOUDS = make_creature(
    name="Shepherd of the Clouds",
    power=4, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Pegasus"},
    text="Flying, vigilance\nWhen this creature enters, return target permanent card with mana value 3 or less from your graveyard to your hand. Return that card to the battlefield instead if you control a Mount.",
)

SHERIFF_OF_SAFE_PASSAGE = make_creature(
    name="Sheriff of Safe Passage",
    power=0, toughness=0,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="This creature enters with a +1/+1 counter on it plus an additional +1/+1 counter on it for each other creature you control.\nPlot {1}{W} (You may pay {1}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

STAGECOACH_SECURITY = make_creature(
    name="Stagecoach Security",
    power=4, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, creatures you control get +1/+1 and gain vigilance until end of turn.\nPlot {3}{W} (You may pay {3}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=stagecoach_security_setup,
)

# =============================================================================
# STEER CLEAR - Conditional damage to attacker/blocker
# =============================================================================

def _steer_clear_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Steer Clear after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Check if controller has a Mount (stored at cast time in callback_data)
    has_mount = choice.callback_data.get('has_mount', False)
    damage = 4 if has_mount else 2

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': damage,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def steer_clear_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Steer Clear: Steer Clear deals 2 damage to target attacking or blocking creature.
    Deals 4 damage instead if you controlled a Mount as you cast this spell.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Steer Clear":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "steer_clear_spell"

    # Check if controller has a Mount at cast time
    has_mount = False
    for obj in state.objects.values():
        if obj.controller == caster_id and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                if 'Mount' in obj.characteristics.subtypes:
                    has_mount = True
                    break

    # Find valid targets: attacking or blocking creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                # Check if attacking or blocking
                if obj.state.attacking or obj.state.blocking:
                    valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose an attacking or blocking creature (deals {4 if has_mount else 2} damage)",
        min_targets=1,
        max_targets=1,
        callback_data={'has_mount': has_mount}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _steer_clear_execute

    return []


STEER_CLEAR = make_instant(
    name="Steer Clear",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Steer Clear deals 2 damage to target attacking or blocking creature. Steer Clear deals 4 damage to that creature instead if you controlled a Mount as you cast this spell.",
    resolve=steer_clear_resolve,
)

STERLING_KEYKEEPER = make_creature(
    name="Sterling Keykeeper",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="{2}, {T}: Tap target non-Mount creature.",
)

STERLING_SUPPLIER = make_creature(
    name="Sterling Supplier",
    power=3, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Soldier"},
    text="Flying\nWhen this creature enters, put a +1/+1 counter on another target creature you control.",
    setup_interceptors=sterling_supplier_setup,
)

# =============================================================================
# TAKE UP THE SHIELD - Combat trick with counter + abilities
# =============================================================================

def _take_up_the_shield_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Take Up the Shield after target selection."""
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
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': target_id,
                'keywords': ['lifelink', 'indestructible'],
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


def take_up_the_shield_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Take Up the Shield: Put a +1/+1 counter on target creature.
    It gains lifelink and indestructible until end of turn.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Take Up the Shield":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "take_up_the_shield_spell"

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +1/+1 counter and abilities",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _take_up_the_shield_execute

    return []


TAKE_UP_THE_SHIELD = make_instant(
    name="Take Up the Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature. It gains lifelink and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    resolve=take_up_the_shield_resolve,
)

THUNDER_LASSO = make_artifact(
    name="Thunder Lasso",
    mana_cost="{2}{W}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +1/+1.\nWhenever equipped creature attacks, tap target creature defending player controls.\nEquip {2}",
    subtypes={"Equipment"},
)

TRAINED_ARYNX = make_creature(
    name="Trained Arynx",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat", "Mount"},
    text="Whenever this creature attacks while saddled, it gains first strike until end of turn. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=trained_arynx_setup,
)

VENGEFUL_TOWNSFOLK = make_creature(
    name="Vengeful Townsfolk",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="Whenever one or more other creatures you control die, put a +1/+1 counter on this creature.",
    setup_interceptors=vengeful_townsfolk_setup,
)

WANTED_GRIFFIN = make_creature(
    name="Wanted Griffin",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Griffin"},
    text="Flying\nWhen this creature dies, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=wanted_griffin_setup,
)

ARCHMAGES_NEWT = make_creature(
    name="Archmage's Newt",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Mount", "Salamander"},
    text="Whenever this creature deals combat damage to a player, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to its mana cost. That card gains flashback {0} until end of turn instead if this creature is saddled. (You may cast that card from your graveyard for its flashback cost. Then exile it.)\nSaddle 3",
)

CANYON_CRAB = make_creature(
    name="Canyon Crab",
    power=0, toughness=5,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Crab"},
    text="{1}{U}: This creature gets +2/-2 until end of turn.\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card, then discard a card.",
    setup_interceptors=canyon_crab_setup,
)

DARING_THUNDERTHIEF = make_creature(
    name="Daring Thunder-Thief",
    power=4, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Turtle"},
    text="Flash\nThis creature enters tapped.",
)

DEEPMUCK_DESPERADO = make_creature(
    name="Deepmuck Desperado",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Homarid", "Mercenary"},
    text="Whenever you commit a crime, each opponent mills three cards. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

DJINN_OF_FOOLS_FALL = make_creature(
    name="Djinn of Fool's Fall",
    power=4, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Djinn"},
    text="Flying\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

DOUBLE_DOWN = make_enchantment(
    name="Double Down",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an outlaw spell, copy that spell. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. Copies of permanent spells become tokens.)",
)

DUELIST_OF_THE_MIND = make_creature(
    name="Duelist of the Mind",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Human"},
    text="Flying, vigilance\nDuelist of the Mind's power is equal to the number of cards you've drawn this turn.\nWhenever you commit a crime, you may draw a card. If you do, discard a card. This ability triggers only once each turn.",
)

EMERGENT_HAUNTING = make_enchantment(
    name="Emergent Haunting",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="At the beginning of your end step, if you haven't cast a spell from your hand this turn and this enchantment isn't a creature, it becomes a 3/3 Spirit creature with flying in addition to its other types.\n{2}{U}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

# =============================================================================
# FAILED FORDING - Bounce + surveil if Desert
# =============================================================================

def _failed_fording_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Failed Fording after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.LAND in target.characteristics.types:
        return []

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'to_zone': f'hand_{target.owner}',
            'to_zone_type': ZoneType.HAND,
            'reason': 'bounced'
        },
        source=choice.source_id
    )]

    # Check if controller controls a Desert
    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player
    has_desert = False
    for obj in state.objects.values():
        if obj.controller == controller and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.LAND in obj.characteristics.types:
                if 'Desert' in obj.characteristics.subtypes:
                    has_desert = True
                    break

    if has_desert:
        events.append(Event(
            type=EventType.SURVEIL,
            payload={'player': controller, 'amount': 1},
            source=choice.source_id
        ))

    return events


def failed_fording_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Failed Fording: Return target nonland permanent to its owner's hand.
    If you control a Desert, surveil 1.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Failed Fording":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "failed_fording_spell"

    # Find valid targets: nonland permanents
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.LAND not in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a nonland permanent to return to hand",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _failed_fording_execute

    return []


FAILED_FORDING = make_instant(
    name="Failed Fording",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. If you control a Desert, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    resolve=failed_fording_resolve,
)

FBLTHP_LOST_ON_THE_RANGE = make_creature(
    name="Fblthp, Lost on the Range",
    power=1, toughness=1,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus"},
    supertypes={"Legendary"},
    text="Ward {2}\nYou may look at the top card of your library any time.\nThe top card of your library has plot. The plot cost is equal to its mana cost.\nYou may plot nonland cards from the top of your library.",
)

FLEETING_REFLECTION = make_instant(
    name="Fleeting Reflection",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof until end of turn. Untap that creature. Until end of turn, it becomes a copy of up to one other target creature.",
)

GERALF_THE_FLESHWRIGHT = make_creature(
    name="Geralf, the Fleshwright",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell during your turn other than your first spell that turn, create a 2/2 blue and black Zombie Rogue creature token.\nWhenever a Zombie you control enters, put a +1/+1 counter on it for each other Zombie that entered the battlefield under your control this turn.",
    setup_interceptors=geralf_the_fleshwright_setup,
)

GEYSER_DRAKE = make_creature(
    name="Geyser Drake",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nDuring turns other than yours, spells you cast cost {1} less to cast.",
)

HARRIER_STRIX = make_creature(
    name="Harrier Strix",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying\nWhen this creature enters, tap target permanent.\n{2}{U}: Draw a card, then discard a card.",
    setup_interceptors=harrier_strix_setup,
)

JAILBREAK_SCHEME = make_sorcery(
    name="Jailbreak Scheme",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {3} — Put a +1/+1 counter on target creature. It can't be blocked this turn.\n+ {2} — Target artifact or creature's owner puts it on their choice of the top or bottom of their library.",
)

THE_KEY_TO_THE_VAULT = make_artifact(
    name="The Key to the Vault",
    mana_cost="{1}{U}",
    text="Whenever equipped creature deals combat damage to a player, look at that many cards from the top of your library. You may exile a nonland card from among them. Put the rest on the bottom of your library in a random order. You may cast the exiled card without paying its mana cost.\nEquip {2}{U}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

LOAN_SHARK = make_creature(
    name="Loan Shark",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Shark"},
    text="When this creature enters, if you've cast two or more spells this turn, draw a card.\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=loan_shark_setup,
)

MARAUDING_SPHINX = make_creature(
    name="Marauding Sphinx",
    power=3, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Sphinx"},
    text="Flying, vigilance, ward {2}\nWhenever you commit a crime, surveil 2. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

# =============================================================================
# METAMORPHIC BLAST - Spree transform/draw
# =============================================================================

def _metamorphic_blast_rabbit_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Metamorphic Blast rabbit mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'become_creature',
            'target_id': target_id,
            'name': 'Rabbit',
            'power': 0,
            'toughness': 1,
            'colors': {Color.WHITE},
            'subtypes': {'Rabbit'},
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def _metamorphic_blast_draw_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Metamorphic Blast draw mode."""
    target_player = selected[0] if selected else None
    if not target_player:
        return []

    return [Event(
        type=EventType.DRAW,
        payload={'player': target_player, 'amount': 2},
        source=choice.source_id
    )]


def _metamorphic_blast_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Metamorphic Blast modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Turn target creature into a 0/1 white Rabbit
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature to become a 0/1 white Rabbit",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _metamorphic_blast_rabbit_execute
            return events

    # Mode 1: Target player draws two cards
    if 1 in selected_modes:
        valid_targets = list(state.players.keys())

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a player to draw two cards",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _metamorphic_blast_draw_execute

    return events


def metamorphic_blast_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Metamorphic Blast - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1} — Target creature becomes a white Rabbit with base power and toughness 0/1.
    + {3} — Target player draws two cards.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Metamorphic Blast":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "metamorphic_blast_spell"

    modes = [
        {"index": 0, "text": "Target creature becomes a white Rabbit with base P/T 0/1."},
        {"index": 1, "text": "Target player draws two cards."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Metamorphic Blast - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _metamorphic_blast_mode_execute

    return []


METAMORPHIC_BLAST = make_instant(
    name="Metamorphic Blast",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Until end of turn, target creature becomes a white Rabbit with base power and toughness 0/1.\n+ {3} — Target player draws two cards.",
    resolve=metamorphic_blast_resolve,
)

NIMBLE_BRIGAND = make_creature(
    name="Nimble Brigand",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="This creature can't be blocked if you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nWhenever this creature deals combat damage to a player, draw a card.",
    setup_interceptors=nimble_brigand_setup,
)

OUTLAW_STITCHER = make_creature(
    name="Outlaw Stitcher",
    power=1, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    text="When this creature enters, create a 2/2 blue and black Zombie Rogue creature token, then put two +1/+1 counters on that token for each spell you've cast this turn other than the first.\nPlot {4}{U} (You may pay {4}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=outlaw_stitcher_setup,
)

PEERLESS_ROPEMASTER = make_creature(
    name="Peerless Ropemaster",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, return up to one target tapped creature to its owner's hand.",
    setup_interceptors=peerless_ropemaster_setup,
)

# =============================================================================
# PHANTOM INTERFERENCE - Spree counter spell
# =============================================================================


def _phantom_interference_counter_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Phantom Interference counter mode after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # The target_id is the source_id of a spell on the stack
    stack_zone = state.zones.get('stack')
    if not stack_zone:
        return []

    # Find the card being countered
    target_card = state.objects.get(target_id)
    if not target_card or target_card.zone != ZoneType.STACK:
        return []  # Target no longer valid

    # Counter the spell (unless controller pays {2} - simplified: just counter it)
    # NOTE: Full implementation would require a mana payment choice from opponent
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered'
        },
        source=choice.source_id
    )]


def _phantom_interference_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Phantom Interference modes after mode selection."""
    events = []
    spell_id = choice.source_id

    # Mode 0 (+{3}): Create a 2/2 white Spirit creature token with flying
    if 0 in selected_modes:
        # Get the caster
        spell = state.objects.get(spell_id)
        controller_id = spell.controller if spell else state.active_player
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': controller_id,
                'name': 'Spirit',
                'power': 2,
                'toughness': 2,
                'types': {CardType.CREATURE},
                'subtypes': {'Spirit'},
                'colors': {Color.WHITE},
                'abilities': ['flying'],
                'is_token': True
            },
            source=spell_id
        ))

    # Mode 1 (+{1}): Counter target spell unless its controller pays {2}
    if 1 in selected_modes:
        # Need to prompt for target selection
        stack_zone = state.zones.get('stack')
        spell = state.objects.get(spell_id)
        caster_id = spell.controller if spell else state.active_player

        # Find valid targets: any spell on the stack (except this one)
        valid_targets = []
        for obj_id in (stack_zone.objects if stack_zone else []):
            obj = state.objects.get(obj_id)
            if not obj:
                continue
            if obj_id == spell_id:
                continue  # Can't counter itself
            if obj.zone != ZoneType.STACK:
                continue
            valid_targets.append(obj_id)

        if valid_targets:
            # Create target choice for counter effect
            target_choice = create_target_choice(
                state=state,
                player_id=caster_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a spell to counter (unless they pay {2})",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _phantom_interference_counter_execute

    return events


def phantom_interference_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Phantom Interference - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {3} -- Create a 2/2 white Spirit creature token with flying.
    + {1} -- Counter target spell unless its controller pays {2}.
    """
    # Find the spell on the stack
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Phantom Interference":
                caster_id = obj.controller
                spell_id = obj.id
                break

    # Fallback
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "phantom_interference_spell"

    # Define the Spree modes
    modes = [
        {"index": 0, "text": "Create a 2/2 white Spirit creature token with flying."},
        {"index": 1, "text": "Counter target spell unless its controller pays {2}."}
    ]

    # Create modal choice - Spree allows one or more modes
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,  # Can choose both modes
        prompt="Phantom Interference - Choose one or more:"
    )

    # Set up callback for when modes are selected
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _phantom_interference_mode_execute

    # Return empty events to pause resolution until choice is submitted
    return []


PHANTOM_INTERFERENCE = make_instant(
    name="Phantom Interference",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {3} — Create a 2/2 white Spirit creature token with flying.\n+ {1} — Counter target spell unless its controller pays {2}.",
    resolve=phantom_interference_resolve,
)

PLAN_THE_HEIST = make_sorcery(
    name="Plan the Heist",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Surveil 3 if you have no cards in hand. Then draw three cards. (To surveil 3, look at the top three cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

RAZZLEDAZZLER = make_creature(
    name="Razzle-Dazzler",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you cast your second spell each turn, put a +1/+1 counter on this creature. It can't be blocked this turn.",
    setup_interceptors=razzledazzler_setup,
)

SEIZE_THE_SECRETS = make_sorcery(
    name="Seize the Secrets",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast if you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nDraw two cards.",
)

SHACKLE_SLINGER = make_creature(
    name="Shackle Slinger",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="Whenever you cast your second spell each turn, choose target creature an opponent controls. If it's tapped, put a stun counter on it. Otherwise, tap it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

SHIFTING_GRIFT = make_sorcery(
    name="Shifting Grift",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Exchange control of two target creatures.\n+ {1} — Exchange control of two target artifacts.\n+ {1} — Exchange control of two target enchantments.",
)

SLICKSHOT_LOCKPICKER = make_creature(
    name="Slickshot Lockpicker",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to its mana cost. (You may cast that card from your graveyard for its flashback cost. Then exile it.)\nPlot {2}{U} (You may pay {2}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

SLICKSHOT_VAULTBUSTER = make_creature(
    name="Slickshot Vault-Buster",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Vigilance\nThis creature gets +2/+0 as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

SPRING_SPLASHER = make_creature(
    name="Spring Splasher",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Beast", "Frog"},
    text="Whenever this creature attacks, target creature defending player controls gets -3/-0 until end of turn.",
    setup_interceptors=spring_splasher_setup,
)

STEP_BETWEEN_WORLDS = make_sorcery(
    name="Step Between Worlds",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Each player may shuffle their hand and graveyard into their library. Each player who does draws seven cards. Exile Step Between Worlds.\nPlot {4}{U}{U} (You may pay {4}{U}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

STOIC_SPHINX = make_creature(
    name="Stoic Sphinx",
    power=5, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flash\nFlying\nThis creature has hexproof as long as you haven't cast a spell this turn.",
)

STOP_COLD = make_enchantment(
    name="Stop Cold",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant artifact or creature\nWhen this Aura enters, tap enchanted permanent.\nEnchanted permanent loses all abilities and doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
)

# =============================================================================
# TAKE THE FALL - Conditional debuff + cantrip
# =============================================================================

def _take_the_fall_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Take the Fall after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    has_outlaw = choice.callback_data.get('has_outlaw', False)
    power_mod = -4 if has_outlaw else -1

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    return [
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': target_id,
                'power_mod': power_mod,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.DRAW,
            payload={'player': controller, 'amount': 1},
            source=choice.source_id
        )
    ]


def take_the_fall_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Take the Fall: Target creature gets -1/-0 until end of turn.
    It gets -4/-0 instead if you control an outlaw. Draw a card.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Take the Fall":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "take_the_fall_spell"

    # Check if controller has an outlaw
    outlaw_types = {'Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock'}
    has_outlaw = False
    for obj in state.objects.values():
        if obj.controller == caster_id and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                subtypes = obj.characteristics.subtypes or set()
                if subtypes & outlaw_types:
                    has_outlaw = True
                    break

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature to get {-4 if has_outlaw else -1}/-0",
        min_targets=1,
        max_targets=1,
        callback_data={'has_outlaw': has_outlaw}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _take_the_fall_execute

    return []


TAKE_THE_FALL = make_instant(
    name="Take the Fall",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -1/-0 until end of turn. It gets -4/-0 until end of turn instead if you control an outlaw. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nDraw a card.",
    resolve=take_the_fall_resolve,
)

# =============================================================================
# THIS TOWN AIN'T BIG ENOUGH - Bounce up to 2 permanents
# =============================================================================

def _this_town_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute This Town Ain't Big Enough after target selection."""
    events = []
    for target_id in selected:
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            continue

        if CardType.LAND in target.characteristics.types:
            continue

        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone': f'battlefield_{target.controller}',
                'to_zone': f'hand_{target.owner}',
                'to_zone_type': ZoneType.HAND,
                'reason': 'bounced'
            },
            source=choice.source_id
        ))

    return events


def this_town_aint_big_enough_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve This Town Ain't Big Enough: Return up to two target nonland
    permanents to their owners' hands.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "This Town Ain't Big Enough":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "this_town_aint_big_enough_spell"

    # Find valid targets: nonland permanents
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.LAND not in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose up to two nonland permanents to return to hand",
        min_targets=0,  # "up to two"
        max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _this_town_execute

    return []


THIS_TOWN_AINT_BIG_ENOUGH = make_instant(
    name="This Town Ain't Big Enough",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="This spell costs {3} less to cast if it targets a permanent you control.\nReturn up to two target nonland permanents to their owners' hands.",
    resolve=this_town_aint_big_enough_resolve,
)

# =============================================================================
# THREE STEPS AHEAD - Spree counterspell/copy/draw
# =============================================================================

def _three_steps_ahead_counter_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Three Steps Ahead counter mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target_card = state.objects.get(target_id)
    if not target_card or target_card.zone != ZoneType.STACK:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': 'stack',
            'to_zone': f'graveyard_{target_card.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'countered'
        },
        source=choice.source_id
    )]


def _three_steps_ahead_copy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Three Steps Ahead copy mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': controller,
            'copy_of': target_id,
            'is_token': True
        },
        source=choice.source_id
    )]


def _three_steps_ahead_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Three Steps Ahead modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Counter target spell
    if 0 in selected_modes:
        stack_zone = state.zones.get('stack')
        valid_targets = []
        for obj_id in (stack_zone.objects if stack_zone else []):
            obj = state.objects.get(obj_id)
            if obj and obj_id != spell_id and obj.zone == ZoneType.STACK:
                valid_targets.append(obj_id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a spell to counter",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _three_steps_ahead_counter_execute
            return events  # Wait for target choice

    # Mode 1: Create a token copy of target artifact or creature you control
    if 1 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and obj.controller == controller_id:
                types = obj.characteristics.types
                if CardType.ARTIFACT in types or CardType.CREATURE in types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose an artifact or creature you control to copy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _three_steps_ahead_copy_execute
            return events  # Wait for target choice

    # Mode 2: Draw two cards, then discard a card
    if 2 in selected_modes:
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': controller_id, 'amount': 2},
            source=spell_id
        ))
        # Note: Discard choice would need to be handled separately
        events.append(Event(
            type=EventType.DISCARD,
            payload={'player': controller_id, 'amount': 1},
            source=spell_id
        ))

    return events


def three_steps_ahead_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Three Steps Ahead - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1}{U} — Counter target spell.
    + {3} — Create a token that's a copy of target artifact or creature you control.
    + {2} — Draw two cards, then discard a card.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Three Steps Ahead":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "three_steps_ahead_spell"

    modes = [
        {"index": 0, "text": "Counter target spell."},
        {"index": 1, "text": "Create a token that's a copy of target artifact or creature you control."},
        {"index": 2, "text": "Draw two cards, then discard a card."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=3,
        prompt="Three Steps Ahead - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _three_steps_ahead_mode_execute

    return []


THREE_STEPS_AHEAD = make_instant(
    name="Three Steps Ahead",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {1}{U} — Counter target spell.\n+ {3} — Create a token that's a copy of target artifact or creature you control.\n+ {2} — Draw two cards, then discard a card.",
    resolve=three_steps_ahead_resolve,
)

VISAGE_BANDIT = make_creature(
    name="Visage Bandit",
    power=2, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Shapeshifter"},
    text="You may have this creature enter as a copy of a creature you control, except it's a Shapeshifter Rogue in addition to its other types.\nPlot {2}{U} (You may pay {2}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

AMBUSH_GIGAPEDE = make_creature(
    name="Ambush Gigapede",
    power=6, toughness=2,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="Flash\nWhen this creature enters, target creature an opponent controls gets -2/-2 until end of turn.",
    setup_interceptors=ambush_gigapede_setup,
)

BINDING_NEGOTIATION = make_sorcery(
    name="Binding Negotiation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a face-up exiled card they own into their graveyard.",
)

BLACKSNAG_BUZZARD = make_creature(
    name="Blacksnag Buzzard",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bird"},
    text="Flying\nThis creature enters with a +1/+1 counter on it if a creature died this turn.\nPlot {1}{B} (You may pay {1}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=blacksnag_buzzard_setup,
)

BLOOD_HUSTLER = make_creature(
    name="Blood Hustler",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="Whenever you commit a crime, put a +1/+1 counter on this creature. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\n{3}{B}: Target opponent loses 1 life and you gain 1 life.",
)

BONEYARD_DESECRATOR = make_creature(
    name="Boneyard Desecrator",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Mercenary", "Zombie"},
    text="Menace\n{1}{B}, Sacrifice another creature: Put a +1/+1 counter on this creature. If an outlaw was sacrificed this way, create a Treasure token. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
)

CAUSTIC_BRONCO = make_creature(
    name="Caustic Bronco",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horse", "Mount", "Snake"},
    text="Whenever this creature attacks, reveal the top card of your library and put it into your hand. You lose life equal to that card's mana value if this creature isn't saddled. Otherwise, each opponent loses that much life.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    setup_interceptors=caustic_bronco_setup,
)

# =============================================================================
# CONSUMING ASHES - Exile creature + conditional surveil
# =============================================================================

def _consuming_ashes_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Consuming Ashes after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Calculate mana value
    mana_value = 0
    mana_cost = target.characteristics.mana_cost or ""
    for char in mana_cost:
        if char.isdigit():
            mana_value += int(char)
        elif char in 'WUBRGC':
            mana_value += 1

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone': f'battlefield_{target.controller}',
            'to_zone': 'exile',
            'to_zone_type': ZoneType.EXILE,
            'reason': 'exiled'
        },
        source=choice.source_id
    )]

    # Surveil 2 if mana value 3 or less
    if mana_value <= 3:
        events.append(Event(
            type=EventType.SURVEIL,
            payload={'player': controller, 'amount': 2},
            source=choice.source_id
        ))

    return events


def consuming_ashes_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Consuming Ashes: Exile target creature.
    If it had mana value 3 or less, surveil 2.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Consuming Ashes":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "consuming_ashes_spell"

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
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
    choice.callback_data['handler'] = _consuming_ashes_execute

    return []


CONSUMING_ASHES = make_instant(
    name="Consuming Ashes",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature. If it had mana value 3 or less, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    resolve=consuming_ashes_resolve,
)

CORRUPTED_CONVICTION = make_instant(
    name="Corrupted Conviction",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature.\nDraw two cards.",
)

# =============================================================================
# DESERT'S DUE - Scaled debuff based on Deserts
# =============================================================================

def _deserts_due_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Desert's Due after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    # Count Deserts
    desert_count = 0
    for obj in state.objects.values():
        if obj.controller == controller and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.LAND in obj.characteristics.types:
                if 'Desert' in obj.characteristics.subtypes:
                    desert_count += 1

    # Base -2/-2 plus -1/-1 per Desert
    total_mod = -2 - desert_count

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'pump',
            'target_id': target_id,
            'power_mod': total_mod,
            'toughness_mod': total_mod,
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def deserts_due_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Desert's Due: Target creature gets -2/-2 until end of turn.
    It gets an additional -1/-1 until end of turn for each Desert you control.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Desert's Due":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "deserts_due_spell"

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to give -2/-2 (and more for each Desert)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _deserts_due_execute

    return []


DESERTS_DUE = make_instant(
    name="Desert's Due",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. It gets an additional -1/-1 until end of turn for each Desert you control.",
    resolve=deserts_due_resolve,
)

DESPERATE_BLOODSEEKER = make_creature(
    name="Desperate Bloodseeker",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Lifelink\nWhen this creature enters, target player mills two cards. (They put the top two cards of their library into their graveyard.)",
    setup_interceptors=desperate_bloodseeker_setup,
)

# =============================================================================
# FAKE YOUR OWN DEATH - Combat trick + death trigger
# =============================================================================

def _fake_your_own_death_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Fake Your Own Death after target selection."""
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
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': target_id,
                'power_mod': 2,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_death_trigger',
                'target_id': target_id,
                'trigger': 'return_and_treasure',
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


def fake_your_own_death_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Fake Your Own Death: Until end of turn, target creature gets +2/+0
    and gains death trigger to return and create Treasure.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Fake Your Own Death":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "fake_your_own_death_spell"

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +2/+0 and death protection",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _fake_your_own_death_execute

    return []


FAKE_YOUR_OWN_DEATH = make_instant(
    name="Fake Your Own Death",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield tapped under its owner's control and you create a Treasure token.\" (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    resolve=fake_your_own_death_resolve,
)

FORSAKEN_MINER = make_creature(
    name="Forsaken Miner",
    power=2, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    text="This creature can't block.\nWhenever you commit a crime, you may pay {B}. If you do, return this card from your graveyard to the battlefield. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

GISA_THE_HELLRAISER = make_creature(
    name="Gisa, the Hellraiser",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Ward—{2}, Pay 2 life.\nSkeletons and Zombies you control get +1/+1 and have menace.\nWhenever you commit a crime, create two tapped 2/2 blue and black Zombie Rogue creature tokens. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=gisa_the_hellraiser_setup,
)

HOLLOW_MARAUDER = make_creature(
    name="Hollow Marauder",
    power=4, toughness=2,
    mana_cost="{6}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Specter"},
    text="This spell costs {1} less to cast for each creature card in your graveyard.\nFlying\nWhen this creature enters, any number of target opponents each discard a card. For each of those opponents who didn't discard a card with mana value 4 or greater, draw a card.",
    setup_interceptors=hollow_marauder_setup,
)

INSATIABLE_AVARICE = make_sorcery(
    name="Insatiable Avarice",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Search your library for a card, then shuffle and put that card on top.\n+ {B}{B} — Target player draws three cards and loses 3 life.",
)

KAERVEK_THE_PUNISHER = make_creature(
    name="Kaervek, the Punisher",
    power=3, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, exile up to one target black card from your graveyard and copy it. You may cast the copy. If you do, you lose 2 life. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime. Copies of permanent spells become tokens.)",
)

LIVELY_DIRGE = make_sorcery(
    name="Lively Dirge",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Search your library for a card, put it into your graveyard, then shuffle.\n+ {2} — Return up to two creature cards with total mana value 4 or less from your graveyard to the battlefield.",
)

MOURNERS_SURPRISE = make_sorcery(
    name="Mourner's Surprise",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return up to one target creature card from your graveyard to your hand. Create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

# =============================================================================
# NEUTRALIZE THE GUARDS - Mass debuff to opponent's creatures + surveil
# =============================================================================

def _neutralize_the_guards_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Neutralize the Guards after target selection."""
    target_player = selected[0] if selected else None
    if not target_player:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    events = []
    # Give -1/-1 to all creatures that opponent controls
    for obj in state.objects.values():
        if obj.controller == target_player and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                events.append(Event(
                    type=EventType.TEMPORARY_EFFECT,
                    payload={
                        'effect': 'pump',
                        'target_id': obj.id,
                        'power_mod': -1,
                        'toughness_mod': -1,
                        'duration': 'end_of_turn'
                    },
                    source=choice.source_id
                ))

    # Surveil 2
    events.append(Event(
        type=EventType.SURVEIL,
        payload={'player': controller, 'amount': 2},
        source=choice.source_id
    ))

    return events


def neutralize_the_guards_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Neutralize the Guards: Creatures target opponent controls get -1/-1
    until end of turn. Surveil 2.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Neutralize the Guards":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "neutralize_the_guards_spell"

    # Find valid targets: opponents
    valid_targets = [p_id for p_id in state.players.keys() if p_id != caster_id]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an opponent",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _neutralize_the_guards_execute

    return []


NEUTRALIZE_THE_GUARDS = make_instant(
    name="Neutralize the Guards",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Creatures target opponent controls get -1/-1 until end of turn. Surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    resolve=neutralize_the_guards_resolve,
)

NEZUMI_LINKBREAKER = make_creature(
    name="Nezumi Linkbreaker",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Warlock"},
    text="When this creature dies, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=nezumi_linkbreaker_setup,
)

OVERZEALOUS_MUSCLE = make_creature(
    name="Overzealous Muscle",
    power=5, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Mercenary", "Ogre"},
    text="Whenever you commit a crime during your turn, this creature gains indestructible until end of turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime. Damage and effects that say \"destroy\" don't destroy a creature with indestructible.)",
)

PITILESS_CARNAGE = make_sorcery(
    name="Pitiless Carnage",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Sacrifice any number of permanents you control, then draw that many cards.\nPlot {1}{B}{B} (You may pay {1}{B}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

RAKISH_CREW = make_enchantment(
    name="Rakish Crew",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nWhenever an outlaw you control dies, each opponent loses 1 life and you gain 1 life. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
    setup_interceptors=rakish_crew_setup,
)

RATTLEBACK_APOTHECARY = make_creature(
    name="Rattleback Apothecary",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Gorgon", "Warlock"},
    text="Deathtouch\nWhenever you commit a crime, target creature you control gains your choice of menace or lifelink until end of turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

RAVEN_OF_FELL_OMENS = make_creature(
    name="Raven of Fell Omens",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bird"},
    text="Flying\nWhenever you commit a crime, each opponent loses 1 life and you gain 1 life. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

RICTUS_ROBBER = make_creature(
    name="Rictus Robber",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Zombie"},
    text="When this creature enters, if a creature died this turn, create a 2/2 blue and black Zombie Rogue creature token.\nPlot {2}{B} (You may pay {2}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=rictus_robber_setup,
)

ROOFTOP_ASSASSIN = make_creature(
    name="Rooftop Assassin",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Vampire"},
    text="Flash\nFlying, lifelink\nWhen this creature enters, destroy target creature an opponent controls that was dealt damage this turn.",
    setup_interceptors=rooftop_assassin_setup,
)

RUSH_OF_DREAD = make_sorcery(
    name="Rush of Dread",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Target opponent sacrifices half the creatures they control of their choice, rounded up.\n+ {2} — Target opponent discards half the cards in their hand, rounded up.\n+ {2} — Target opponent loses half their life, rounded up.",
)

SERVANT_OF_THE_STINGER = make_creature(
    name="Servant of the Stinger",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Deathtouch\nWhenever this creature deals combat damage to a player, if you've committed a crime this turn, you may sacrifice this creature. If you do, search your library for a card, put it into your hand, then shuffle. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

def _shoot_the_sheriff_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Shoot the Sheriff after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Verify target is still valid (on battlefield and not an outlaw)
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []  # Target no longer valid

    if CardType.CREATURE not in target.characteristics.types:
        return []  # Not a creature

    # Check if target is now an outlaw (subtypes may have changed)
    outlaw_types = {'Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock'}
    subtypes = target.characteristics.subtypes or set()
    if subtypes & outlaw_types:
        return []  # Target is now an outlaw, spell fizzles

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def shoot_the_sheriff_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Shoot the Sheriff: Destroy target non-outlaw creature.

    Outlaws are: Assassins, Mercenaries, Pirates, Rogues, and Warlocks.
    Creates a target choice for the caster. Returns empty events to pause resolution.
    """
    # Find the spell on the stack to determine who cast it
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Shoot the Sheriff":
                caster_id = obj.controller
                spell_id = obj.id
                break

    # Fallback to active player if we can't find the spell
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "shoot_the_sheriff_spell"

    # Find non-outlaw creatures (valid targets)
    outlaw_types = {'Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock'}
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            subtypes = obj.characteristics.subtypes or set()
            if not subtypes & outlaw_types:
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
        prompt="Choose a non-outlaw creature to destroy",
        min_targets=1,
        max_targets=1
    )

    # Set up callback for when target is selected
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _shoot_the_sheriff_execute

    # Return empty events to pause resolution until choice is submitted
    return []


SHOOT_THE_SHERIFF = make_instant(
    name="Shoot the Sheriff",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target non-outlaw creature. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. Everyone else is fair game.)",
    resolve=shoot_the_sheriff_resolve,
)

# =============================================================================
# SKULDUGGERY - Two-target pump/debuff
# =============================================================================

def _skulduggery_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Skulduggery after target selection."""
    if len(selected) < 2:
        return []

    your_creature = selected[0]
    opponent_creature = selected[1]

    events = []

    # Your creature gets +1/+1
    your_obj = state.objects.get(your_creature)
    if your_obj and your_obj.zone == ZoneType.BATTLEFIELD:
        events.append(Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': your_creature,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ))

    # Opponent's creature gets -1/-1
    opp_obj = state.objects.get(opponent_creature)
    if opp_obj and opp_obj.zone == ZoneType.BATTLEFIELD:
        events.append(Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': opponent_creature,
                'power_mod': -1,
                'toughness_mod': -1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ))

    return events


def skulduggery_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Skulduggery: Until end of turn, target creature you control gets +1/+1
    and target creature an opponent controls gets -1/-1.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Skulduggery":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "skulduggery_spell"

    # Find your creatures
    your_creatures = []
    opponent_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                if obj.controller == caster_id:
                    your_creatures.append(obj.id)
                else:
                    opponent_creatures.append(obj.id)

    if not your_creatures or not opponent_creatures:
        return []

    # Combined targeting - your creature first, then opponent's
    all_targets = your_creatures + opponent_creatures

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=all_targets,
        prompt="Choose a creature you control, then a creature an opponent controls",
        min_targets=2,
        max_targets=2,
        callback_data={'your_creatures': your_creatures, 'opponent_creatures': opponent_creatures}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _skulduggery_execute

    return []


SKULDUGGERY = make_instant(
    name="Skulduggery",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature you control gets +1/+1 and target creature an opponent controls gets -1/-1.",
    resolve=skulduggery_resolve,
)

TINYBONES_JOINS_UP = make_enchantment(
    name="Tinybones Joins Up",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When Tinybones Joins Up enters, any number of target players each discard a card.\nWhenever a legendary creature you control enters, any number of target players each mill a card and lose 1 life.",
    supertypes={"Legendary"},
    setup_interceptors=tinybones_joins_up_setup,
)

TINYBONES_THE_PICKPOCKET = make_creature(
    name="Tinybones, the Pickpocket",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    supertypes={"Legendary"},
    text="Deathtouch\nWhenever Tinybones deals combat damage to a player, you may cast target nonland permanent card from that player's graveyard, and mana of any type can be spent to cast that spell.",
)

TREASURE_DREDGER = make_creature(
    name="Treasure Dredger",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="{1}, {T}, Pay 1 life: Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

# =============================================================================
# UNFORTUNATE ACCIDENT - Spree removal/token creation
# =============================================================================

def _unfortunate_accident_destroy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Unfortunate Accident destroy mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _unfortunate_accident_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Unfortunate Accident modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 1: Create a Mercenary token (process this first as it doesn't need targeting)
    if 1 in selected_modes:
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': controller_id,
                'name': 'Mercenary',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Mercenary'},
                'colors': {Color.RED},
                'is_token': True
            },
            source=spell_id
        ))

    # Mode 0: Destroy target creature
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _unfortunate_accident_destroy_execute
            return events  # Process token creation then wait for target

    return events


def unfortunate_accident_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Unfortunate Accident - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {2}{B} — Destroy target creature.
    + {1} — Create a 1/1 red Mercenary creature token.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Unfortunate Accident":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "unfortunate_accident_spell"

    modes = [
        {"index": 0, "text": "Destroy target creature."},
        {"index": 1, "text": "Create a 1/1 red Mercenary creature token."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Unfortunate Accident - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _unfortunate_accident_mode_execute

    return []


UNFORTUNATE_ACCIDENT = make_instant(
    name="Unfortunate Accident",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {2}{B} — Destroy target creature.\n+ {1} — Create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    resolve=unfortunate_accident_resolve,
)

UNSCRUPULOUS_CONTRACTOR = make_creature(
    name="Unscrupulous Contractor",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    text="When this creature enters, you may sacrifice a creature. When you do, target player draws two cards and loses 2 life.\nPlot {2}{B} (You may pay {2}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

VADMIR_NEW_BLOOD = make_creature(
    name="Vadmir, New Blood",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, put a +1/+1 counter on Vadmir. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nAs long as Vadmir has four or more +1/+1 counters on it, it has menace and lifelink.",
)

VAULT_PLUNDERER = make_creature(
    name="Vault Plunderer",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, target player draws a card and loses 1 life.",
    setup_interceptors=vault_plunderer_setup,
)

BRIMSTONE_ROUNDUP = make_enchantment(
    name="Brimstone Roundup",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever you cast your second spell each turn, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

CALAMITY_GALLOPING_INFERNO = make_creature(
    name="Calamity, Galloping Inferno",
    power=4, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Horse", "Mount"},
    supertypes={"Legendary"},
    text="Haste\nWhenever Calamity attacks while saddled, choose a nonlegendary creature that saddled it this turn and create a tapped and attacking token that's a copy of it. Sacrifice that token at the beginning of the next end step. Repeat this process once.\nSaddle 1",
)

# =============================================================================
# CAUGHT IN THE CROSSFIRE - Spree mass damage to outlaws/non-outlaws
# =============================================================================

def _caught_in_the_crossfire_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Caught in the Crossfire modes after mode selection."""
    events = []
    spell_id = choice.source_id
    outlaw_types = {'Assassin', 'Mercenary', 'Pirate', 'Rogue', 'Warlock'}

    # Mode 0: Deal 2 damage to each outlaw creature
    if 0 in selected_modes:
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    subtypes = obj.characteristics.subtypes or set()
                    if subtypes & outlaw_types:
                        events.append(Event(
                            type=EventType.DAMAGE,
                            payload={
                                'target': obj.id,
                                'amount': 2,
                                'source': spell_id,
                                'is_combat': False
                            },
                            source=spell_id
                        ))

    # Mode 1: Deal 2 damage to each non-outlaw creature
    if 1 in selected_modes:
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    subtypes = obj.characteristics.subtypes or set()
                    if not (subtypes & outlaw_types):
                        events.append(Event(
                            type=EventType.DAMAGE,
                            payload={
                                'target': obj.id,
                                'amount': 2,
                                'source': spell_id,
                                'is_combat': False
                            },
                            source=spell_id
                        ))

    return events


def caught_in_the_crossfire_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Caught in the Crossfire - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {1} — Deal 2 damage to each outlaw creature.
    + {1} — Deal 2 damage to each non-outlaw creature.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Caught in the Crossfire":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "caught_in_the_crossfire_spell"

    modes = [
        {"index": 0, "text": "Deal 2 damage to each outlaw creature."},
        {"index": 1, "text": "Deal 2 damage to each non-outlaw creature."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Caught in the Crossfire - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _caught_in_the_crossfire_mode_execute

    return []


CAUGHT_IN_THE_CROSSFIRE = make_instant(
    name="Caught in the Crossfire",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Caught in the Crossfire deals 2 damage to each outlaw creature. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\n+ {1} — Caught in the Crossfire deals 2 damage to each non-outlaw creature.",
    resolve=caught_in_the_crossfire_resolve,
)

CUNNING_COYOTE = make_creature(
    name="Cunning Coyote",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Coyote"},
    text="Haste\nWhen this creature enters, another target creature you control gets +1/+1 and gains haste until end of turn.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=cunning_coyote_setup,
)

DEADEYE_DUELIST = make_creature(
    name="Deadeye Duelist",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    text="Reach\n{1}, {T}: This creature deals 1 damage to target opponent.",
)

DEMONIC_RUCKUS = make_enchantment(
    name="Demonic Ruckus",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Enchant creature\nEnchanted creature gets +1/+1 and has menace and trample.\nWhen this Aura is put into a graveyard from the battlefield, draw a card.\nPlot {R} (You may pay {R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    subtypes={"Aura"},
)

DISCERNING_PEDDLER = make_creature(
    name="Discerning Peddler",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, you may discard a card. If you do, draw a card.",
    setup_interceptors=discerning_peddler_setup,
)

# =============================================================================
# EXPLOSIVE DERAILMENT - Spree damage/artifact destruction
# =============================================================================

def _explosive_derailment_damage_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Explosive Derailment damage mode."""
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
        payload={
            'target': target_id,
            'amount': 4,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def _explosive_derailment_artifact_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Explosive Derailment artifact destruction mode."""
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


def _explosive_derailment_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Explosive Derailment modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Mode 0: Deal 4 damage to target creature
    if 0 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose a creature to deal 4 damage to",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _explosive_derailment_damage_execute
            return events

    # Mode 1: Destroy target artifact
    if 1 in selected_modes:
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.ARTIFACT in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if valid_targets:
            target_choice = create_target_choice(
                state=state,
                player_id=controller_id,
                source_id=spell_id,
                legal_targets=valid_targets,
                prompt="Choose an artifact to destroy",
                min_targets=1,
                max_targets=1
            )
            target_choice.choice_type = "target_with_callback"
            target_choice.callback_data['handler'] = _explosive_derailment_artifact_execute

    return events


def explosive_derailment_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Explosive Derailment - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {2} — Explosive Derailment deals 4 damage to target creature.
    + {2} — Destroy target artifact.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Explosive Derailment":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "explosive_derailment_spell"

    modes = [
        {"index": 0, "text": "Deal 4 damage to target creature."},
        {"index": 1, "text": "Destroy target artifact."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Explosive Derailment - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _explosive_derailment_mode_execute

    return []


EXPLOSIVE_DERAILMENT = make_instant(
    name="Explosive Derailment",
    mana_cost="{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Explosive Derailment deals 4 damage to target creature.\n+ {2} — Destroy target artifact.",
    resolve=explosive_derailment_resolve,
)

FEROCIFICATION = make_enchantment(
    name="Ferocification",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="At the beginning of combat on your turn, choose one —\n• Target creature you control gets +2/+0 until end of turn.\n• Target creature you control gains menace and haste until end of turn.",
)

GILA_COURSER = make_creature(
    name="Gila Courser",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Mount"},
    text="Whenever this creature attacks while saddled, exile the top card of your library. Until the end of your next turn, you may play that card.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

GREAT_TRAIN_HEIST = make_instant(
    name="Great Train Heist",
    mana_cost="{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {2}{R} — Untap all creatures you control. If it's your combat phase, there is an additional combat phase after this phase.\n+ {2} — Creatures you control get +1/+0 and gain first strike until end of turn.\n+ {R} — Choose target opponent. Whenever a creature you control deals combat damage to that player this turn, create a tapped Treasure token.",
)

# =============================================================================
# HELL TO PAY - X damage with treasure creation
# =============================================================================

def _hell_to_pay_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Hell to Pay after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    x_value = choice.callback_data.get('x_value', 0)
    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    # Calculate toughness to determine excess damage
    from src.engine import get_toughness
    toughness = get_toughness(target, state)

    events = [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': x_value,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]

    # Calculate excess damage (damage beyond toughness)
    excess = max(0, x_value - toughness)
    if excess > 0:
        for _ in range(excess):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': controller,
                    'name': 'Treasure',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                    'is_token': True,
                    'enters_tapped': True
                },
                source=choice.source_id
            ))

    return events


def hell_to_pay_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Hell to Pay: Hell to Pay deals X damage to target creature.
    Create a number of tapped Treasure tokens equal to the amount of excess damage.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    x_value = 0
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Hell to Pay":
                caster_id = obj.controller
                spell_id = obj.id
                # X value would be stored in the spell object
                x_value = getattr(obj, 'x_value', 0)
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "hell_to_pay_spell"

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature to deal {x_value} damage to",
        min_targets=1,
        max_targets=1,
        callback_data={'x_value': x_value}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _hell_to_pay_execute

    return []


HELL_TO_PAY = make_sorcery(
    name="Hell to Pay",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Hell to Pay deals X damage to target creature. Create a number of tapped Treasure tokens equal to the amount of excess damage dealt to that creature this way.",
    resolve=hell_to_pay_resolve,
)

HELLSPUR_BRUTE = make_creature(
    name="Hellspur Brute",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Mercenary", "Minotaur"},
    text="Affinity for outlaws (This spell costs {1} less to cast for each Assassin, Mercenary, Pirate, Rogue, and/or Warlock you control.)\nTrample",
)

HELLSPUR_POSSE_BOSS = make_creature(
    name="Hellspur Posse Boss",
    power=2, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Rogue"},
    text="Other outlaws you control have haste. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhen this creature enters, create two 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=hellspur_posse_boss_setup,
)

HIGHWAY_ROBBERY = make_sorcery(
    name="Highway Robbery",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="You may discard a card or sacrifice a land. If you do, draw two cards.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

IRASCIBLE_WOLVERINE = make_creature(
    name="Irascible Wolverine",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Wolverine"},
    text="When this creature enters, exile the top card of your library. Until end of turn, you may play that card.\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=irascible_wolverine_setup,
)

IRONFIST_PULVERIZER = make_creature(
    name="Iron-Fist Pulverizer",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Reach\nWhenever you cast your second spell each turn, this creature deals 2 damage to target opponent. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    setup_interceptors=ironfist_pulverizer_setup,
)

LONGHORN_SHARPSHOOTER = make_creature(
    name="Longhorn Sharpshooter",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Rogue"},
    text="Reach\nWhen this card becomes plotted, it deals 2 damage to any target.\nPlot {3}{R} (You may pay {3}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

MAGDA_THE_HOARDMASTER = make_creature(
    name="Magda, the Hoardmaster",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Dwarf"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, create a tapped Treasure token. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nSacrifice three Treasures: Create a 4/4 red Scorpion Dragon creature token with flying and haste. Activate only as a sorcery.",
)

MAGEBANE_LIZARD = make_creature(
    name="Magebane Lizard",
    power=1, toughness=4,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Whenever a player casts a noncreature spell, this creature deals damage to that player equal to the number of noncreature spells they've cast this turn.",
)

MINE_RAIDER = make_creature(
    name="Mine Raider",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="Trample\nWhen this creature enters, if you control another outlaw, create a Treasure token. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=mine_raider_setup,
)

OUTLAWS_FURY = make_instant(
    name="Outlaws' Fury",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 until end of turn. If you control an outlaw, exile the top card of your library. Until the end of your next turn, you may play that card. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
)

PRICKLY_PAIR = make_creature(
    name="Prickly Pair",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Mercenary", "Plant"},
    text="When this creature enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
    setup_interceptors=prickly_pair_setup,
)

# =============================================================================
# QUICK DRAW - Combat trick with ability manipulation
# =============================================================================

def _quick_draw_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Quick Draw after target selection."""
    if len(selected) < 2:
        return []

    creature_target = selected[0]
    opponent_target = selected[1]

    creature = state.objects.get(creature_target)
    if not creature or creature.zone != ZoneType.BATTLEFIELD:
        return []

    events = [
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': creature_target,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': creature_target,
                'keywords': ['first_strike'],
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]

    # Remove first strike and double strike from opponent's creatures
    for obj in state.objects.values():
        if obj.controller == opponent_target and obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                events.append(Event(
                    type=EventType.TEMPORARY_EFFECT,
                    payload={
                        'effect': 'remove_keywords',
                        'target_id': obj.id,
                        'keywords': ['first_strike', 'double_strike'],
                        'duration': 'end_of_turn'
                    },
                    source=choice.source_id
                ))

    return events


def quick_draw_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Quick Draw: Target creature you control gets +1/+1 and gains first strike
    until end of turn. Creatures target opponent controls lose first strike and
    double strike until end of turn.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Quick Draw":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "quick_draw_spell"

    # Find valid creature targets: creatures you control
    creature_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == caster_id:
            if CardType.CREATURE in obj.characteristics.types:
                creature_targets.append(obj.id)

    # Find opponents
    opponent_targets = [p_id for p_id in state.players.keys() if p_id != caster_id]

    if not creature_targets or not opponent_targets:
        return []

    # For simplicity, combine into one choice - first select creature, then opponent
    # Note: This is a simplified implementation; ideally these would be two separate choices
    all_targets = creature_targets + opponent_targets

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=all_targets,
        prompt="Choose a creature you control, then an opponent",
        min_targets=2,
        max_targets=2,
        callback_data={'creature_targets': creature_targets, 'opponent_targets': opponent_targets}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _quick_draw_execute

    return []


QUICK_DRAW = make_instant(
    name="Quick Draw",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +1/+1 and gains first strike until end of turn. Creatures target opponent controls lose first strike and double strike until end of turn.",
    resolve=quick_draw_resolve,
)

QUILLED_CHARGER = make_creature(
    name="Quilled Charger",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Mount", "Porcupine"},
    text="Whenever this creature attacks while saddled, it gets +1/+2 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

RECKLESS_LACKEY = make_creature(
    name="Reckless Lackey",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="First strike, haste\n{2}{R}, Sacrifice this creature: Draw a card and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

RESILIENT_ROADRUNNER = make_creature(
    name="Resilient Roadrunner",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bird"},
    text="Haste, protection from Coyotes\n{3}: This creature can't be blocked this turn except by creatures with haste.",
)

RETURN_THE_FAVOR = make_instant(
    name="Return the Favor",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Copy target instant spell, sorcery spell, activated ability, or triggered ability. You may choose new targets for the copy.\n+ {1} — Change the target of target spell or ability with a single target.",
)

RODEO_PYROMANCERS = make_creature(
    name="Rodeo Pyromancers",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mercenary"},
    text="Whenever you cast your first spell each turn, add {R}{R}.",
    setup_interceptors=rodeo_pyromancers_setup,
)

SCALESTORM_SUMMONER = make_creature(
    name="Scalestorm Summoner",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warlock"},
    text="Whenever this creature attacks, create a 3/1 red Dinosaur creature token if you control a creature with power 4 or greater.",
    setup_interceptors=scalestorm_summoner_setup,
)

# =============================================================================
# SCORCHING SHOT - Simple damage spell
# =============================================================================

def _scorching_shot_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Scorching Shot after target selection."""
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
        payload={
            'target': target_id,
            'amount': 5,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def scorching_shot_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Scorching Shot: Scorching Shot deals 5 damage to target creature.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Scorching Shot":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "scorching_shot_spell"

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to deal 5 damage to",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _scorching_shot_execute

    return []


SCORCHING_SHOT = make_sorcery(
    name="Scorching Shot",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Scorching Shot deals 5 damage to target creature.",
    resolve=scorching_shot_resolve,
)

SLICKSHOT_SHOWOFF = make_creature(
    name="Slickshot Show-Off",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bird", "Wizard"},
    text="Flying, haste\nWhenever you cast a noncreature spell, this creature gets +2/+0 until end of turn.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=slickshot_showoff_setup,
)

STINGERBACK_TERROR = make_creature(
    name="Stingerback Terror",
    power=7, toughness=7,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon", "Scorpion"},
    text="Flying, trample\nThis creature gets -1/-1 for each card in your hand.\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

# =============================================================================
# TAKE FOR A RIDE - Threaten effect
# =============================================================================

def _take_for_a_ride_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Take for a Ride after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    return [
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'gain_control',
                'target_id': target_id,
                'new_controller': controller,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': target_id,
                'keywords': ['haste'],
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


def take_for_a_ride_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Take for a Ride: Gain control of target creature until end of turn.
    Untap that creature. It gains haste until end of turn.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Take for a Ride":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "take_for_a_ride_spell"

    # Find valid targets: creatures (typically opponent's, but can target any)
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to gain control of",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _take_for_a_ride_execute

    return []


TAKE_FOR_A_RIDE = make_sorcery(
    name="Take for a Ride",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Take for a Ride has flash as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nGain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.",
    resolve=take_for_a_ride_resolve,
)

TERROR_OF_THE_PEAKS = make_creature(
    name="Terror of the Peaks",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nSpells your opponents cast that target this creature cost an additional 3 life to cast.\nWhenever another creature you control enters, this creature deals damage equal to that creature's power to any target.",
    setup_interceptors=terror_of_the_peaks_setup,
)

# =============================================================================
# THUNDER SALVO - Scaled damage based on spells cast
# =============================================================================

def _thunder_salvo_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Thunder Salvo after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    damage = choice.callback_data.get('damage', 2)

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': damage,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]


def thunder_salvo_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Thunder Salvo: Thunder Salvo deals X damage to target creature,
    where X is 2 plus the number of other spells you've cast this turn.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Thunder Salvo":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "thunder_salvo_spell"

    # Count spells cast this turn (simplified - would need turn tracking)
    # For now, base damage is 2 + 0 other spells
    other_spells = getattr(state, 'spells_cast_this_turn', {}).get(caster_id, 0)
    damage = 2 + max(0, other_spells - 1)  # -1 because Thunder Salvo itself counts

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature to deal {damage} damage to",
        min_targets=1,
        max_targets=1,
        callback_data={'damage': damage}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _thunder_salvo_execute

    return []


THUNDER_SALVO = make_instant(
    name="Thunder Salvo",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Thunder Salvo deals X damage to target creature, where X is 2 plus the number of other spells you've cast this turn.",
    resolve=thunder_salvo_resolve,
)

TRICK_SHOT = make_instant(
    name="Trick Shot",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Trick Shot deals 6 damage to target creature and 2 damage to up to one other target creature token.",
)

ALOE_ALCHEMIST = make_creature(
    name="Aloe Alchemist",
    power=3, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Warlock"},
    text="Trample\nWhen this card becomes plotted, target creature gets +3/+2 and gains trample until end of turn.\nPlot {1}{G} (You may pay {1}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

ANKLE_BITER = make_creature(
    name="Ankle Biter",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Snake"},
    text="Deathtouch",
)

BEASTBOND_OUTCASTER = make_creature(
    name="Beastbond Outcaster",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="When this creature enters, if you control a creature with power 4 or greater, draw a card.\nPlot {1}{G} (You may pay {1}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=beastbond_outcaster_setup,
)

# =============================================================================
# BETRAYAL AT THE VAULT - One creature damages two others
# =============================================================================

def _betrayal_at_the_vault_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Betrayal at the Vault after target selection."""
    if len(selected) < 3:
        return []

    your_creature_id = selected[0]
    target1_id = selected[1]
    target2_id = selected[2]

    your_creature = state.objects.get(your_creature_id)
    if not your_creature or your_creature.zone != ZoneType.BATTLEFIELD:
        return []

    from src.engine import get_power
    power = get_power(your_creature, state)

    events = []

    # Deal damage to first target
    target1 = state.objects.get(target1_id)
    if target1 and target1.zone == ZoneType.BATTLEFIELD:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': target1_id,
                'amount': power,
                'source': your_creature_id,
                'is_combat': False
            },
            source=choice.source_id
        ))

    # Deal damage to second target
    target2 = state.objects.get(target2_id)
    if target2 and target2.zone == ZoneType.BATTLEFIELD:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': target2_id,
                'amount': power,
                'source': your_creature_id,
                'is_combat': False
            },
            source=choice.source_id
        ))

    return events


def betrayal_at_the_vault_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Betrayal at the Vault: Target creature you control deals damage equal
    to its power to each of two other target creatures.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Betrayal at the Vault":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "betrayal_at_the_vault_spell"

    # Find your creatures
    your_creatures = []
    other_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                if obj.controller == caster_id:
                    your_creatures.append(obj.id)
                other_creatures.append(obj.id)  # All creatures can be targets

    if not your_creatures or len(other_creatures) < 3:
        return []

    # Need to select: 1 creature you control, 2 other creatures
    all_targets = your_creatures + [c for c in other_creatures if c not in your_creatures]

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=list(set(all_targets)),  # Dedupe
        prompt="Choose your creature, then two other creatures to damage",
        min_targets=3,
        max_targets=3,
        callback_data={'your_creatures': your_creatures}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _betrayal_at_the_vault_execute

    return []


BETRAYAL_AT_THE_VAULT = make_instant(
    name="Betrayal at the Vault",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to each of two other target creatures.",
    resolve=betrayal_at_the_vault_resolve,
)

BRISTLEPACK_SENTRY = make_creature(
    name="Bristlepack Sentry",
    power=3, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wolf"},
    text="Defender\nAs long as you control a creature with power 4 or greater, this creature can attack as though it didn't have defender.",
)

BRISTLY_BILL_SPINE_SOWER = make_creature(
    name="Bristly Bill, Spine Sower",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Plant"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, put a +1/+1 counter on target creature.\n{3}{G}{G}: Double the number of +1/+1 counters on each creature you control.",
)

CACTARANTULA = make_creature(
    name="Cactarantula",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spider"},
    text="This spell costs {1} less to cast if you control a Desert.\nReach\nWhenever this creature becomes the target of a spell or ability an opponent controls, you may draw a card.",
)

COLOSSAL_RATTLEWURM = make_creature(
    name="Colossal Rattlewurm",
    power=6, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Colossal Rattlewurm has flash as long as you control a Desert.\nTrample\n{1}{G}, Exile this card from your graveyard: Search your library for a Desert card, put it onto the battlefield tapped, then shuffle.",
)

DANCE_OF_THE_TUMBLEWEEDS = make_sorcery(
    name="Dance of the Tumbleweeds",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Search your library for a basic land card or a Desert card, put it onto the battlefield, then shuffle.\n+ {3} — Create an X/X green Elemental creature token, where X is the number of lands you control.",
)

DROVER_GRIZZLY = make_creature(
    name="Drover Grizzly",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Bear", "Mount"},
    text="Whenever this creature attacks while saddled, creatures you control gain trample until end of turn.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

FREESTRIDER_COMMANDO = make_creature(
    name="Freestrider Commando",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Mercenary"},
    text="This creature enters with two +1/+1 counters on it if it wasn't cast or no mana was spent to cast it.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

FREESTRIDER_LOOKOUT = make_creature(
    name="Freestrider Lookout",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Rogue"},
    text="Reach\nWhenever you commit a crime, look at the top five cards of your library. You may put a land card from among them onto the battlefield tapped. Put the rest on the bottom of your library in a random order. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

FULL_STEAM_AHEAD = make_sorcery(
    name="Full Steam Ahead",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Until end of turn, each creature you control gets +2/+2 and gains trample and \"This creature can't be blocked by more than one creature.\"",
)

GIANT_BEAVER = make_creature(
    name="Giant Beaver",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beaver", "Mount"},
    text="Vigilance\nWhenever this creature attacks while saddled, put a +1/+1 counter on target creature that saddled it this turn.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

# =============================================================================
# GOLD RUSH - Treasure creation + optional pump
# =============================================================================

def _gold_rush_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Gold Rush after target selection."""
    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    events = [
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': controller,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True
            },
            source=choice.source_id
        )
    ]

    # If a target was selected, pump it
    if selected:
        target_id = selected[0]
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            # Count treasures (including the one we just created)
            treasure_count = 1  # The one we're creating
            for obj in state.objects.values():
                if obj.controller == controller and obj.zone == ZoneType.BATTLEFIELD:
                    if CardType.ARTIFACT in obj.characteristics.types:
                        if 'Treasure' in obj.characteristics.subtypes:
                            treasure_count += 1

            pump = treasure_count * 2
            events.append(Event(
                type=EventType.TEMPORARY_EFFECT,
                payload={
                    'effect': 'pump',
                    'target_id': target_id,
                    'power_mod': pump,
                    'toughness_mod': pump,
                    'duration': 'end_of_turn'
                },
                source=choice.source_id
            ))

    return events


def gold_rush_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Gold Rush: Create a Treasure token. Until end of turn, up to one target
    creature gets +2/+2 for each Treasure you control.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Gold Rush":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "gold_rush_spell"

    # Find valid targets: any creature (optional)
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose up to one creature to pump (or none)",
        min_targets=0,  # "up to one"
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _gold_rush_execute

    return []


GOLD_RUSH = make_instant(
    name="Gold Rush",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create a Treasure token. Until end of turn, up to one target creature gets +2/+2 for each Treasure you control.",
    resolve=gold_rush_resolve,
)

GOLDVEIN_HYDRA = make_creature(
    name="Goldvein Hydra",
    power=0, toughness=0,
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="Vigilance, trample, haste\nThis creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a number of tapped Treasure tokens equal to its power.",
    setup_interceptors=goldvein_hydra_setup,
)

HARDBRISTLE_BANDIT = make_creature(
    name="Hardbristle Bandit",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Rogue"},
    text="{T}: Add one mana of any color.\nWhenever you commit a crime, untap this creature. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

INTREPID_STABLEMASTER = make_creature(
    name="Intrepid Stablemaster",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="Reach\n{T}: Add {G}.\n{T}: Add two mana of any one color. Spend this mana only to cast Mount or Vehicle spells.",
)

MAP_THE_FRONTIER = make_sorcery(
    name="Map the Frontier",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and/or Desert cards, put them onto the battlefield tapped, then shuffle.",
)

ORNERY_TUMBLEWAGG = make_creature(
    name="Ornery Tumblewagg",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Brushwagg", "Mount"},
    text="At the beginning of combat on your turn, put a +1/+1 counter on target creature.\nWhenever this creature attacks while saddled, double the number of +1/+1 counters on target creature.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

OUTCASTER_GREENBLADE = make_creature(
    name="Outcaster Greenblade",
    power=1, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Mercenary"},
    text="When this creature enters, search your library for a basic land card or a Desert card, reveal it, put it into your hand, then shuffle.\nThis creature gets +1/+1 for each Desert you control.",
    setup_interceptors=outcaster_greenblade_setup,
)

OUTCASTER_TRAILBLAZER = make_creature(
    name="Outcaster Trailblazer",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="When this creature enters, add one mana of any color.\nWhenever another creature you control with power 4 or greater enters, draw a card.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=outcaster_trailblazer_setup,
)

PATIENT_NATURALIST = make_creature(
    name="Patient Naturalist",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When this creature enters, mill three cards. Put a land card from among the milled cards into your hand. If you can't, create a Treasure token. (To mill three cards, put the top three cards of your library into your graveyard.)",
    setup_interceptors=patient_naturalist_setup,
)

RAILWAY_BRAWLER = make_creature(
    name="Railway Brawler",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino", "Warrior"},
    text="Reach, trample\nWhenever another creature you control enters, put X +1/+1 counters on it, where X is its power.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=railway_brawler_setup,
)

RAMBLING_POSSUM = make_creature(
    name="Rambling Possum",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Mount", "Possum"},
    text="Whenever this creature attacks while saddled, it gets +1/+2 until end of turn. Then you may return any number of creatures that saddled it this turn to their owner's hand.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

RAUCOUS_ENTERTAINER = make_creature(
    name="Raucous Entertainer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bard", "Plant"},
    text="{1}, {T}: Put a +1/+1 counter on each creature you control that entered this turn.",
)

REACH_FOR_THE_SKY = make_enchantment(
    name="Reach for the Sky",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nEnchanted creature gets +3/+2 and has reach.\nWhen this Aura is put into a graveyard from the battlefield, draw a card.",
    subtypes={"Aura"},
)

RISE_OF_THE_VARMINTS = make_sorcery(
    name="Rise of the Varmints",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Create X 2/1 green Varmint creature tokens, where X is the number of creature cards in your graveyard.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

SMUGGLERS_SURPRISE = make_instant(
    name="Smuggler's Surprise",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Mill four cards. You may put up to two creature and/or land cards from among the milled cards into your hand.\n+ {4}{G} — You may put up to two creature cards from your hand onto the battlefield.\n+ {1} — Creatures you control with power 4 or greater gain hexproof and indestructible until end of turn.",
)

# =============================================================================
# SNAKESKIN VEIL - Protection + counter
# =============================================================================

def _snakeskin_veil_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Snakeskin Veil after target selection."""
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
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ),
        Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'grant_keywords',
                'target_id': target_id,
                'keywords': ['hexproof'],
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


def snakeskin_veil_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Snakeskin Veil: Put a +1/+1 counter on target creature you control.
    It gains hexproof until end of turn.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Snakeskin Veil":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "snakeskin_veil_spell"

    # Find valid targets: creatures you control
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == caster_id:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature you control to give +1/+1 and hexproof",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _snakeskin_veil_execute

    return []


SNAKESKIN_VEIL = make_instant(
    name="Snakeskin Veil",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
    resolve=snakeskin_veil_resolve,
)

SPINEWOODS_ARMADILLO = make_creature(
    name="Spinewoods Armadillo",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Armadillo"},
    text="Reach\nWard {3} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {3}.)\n{1}{G}, Discard this card: Search your library for a basic land card or a Desert card, reveal it, put it into your hand, then shuffle. You gain 3 life.",
)

SPINEWOODS_PALADIN = make_creature(
    name="Spinewoods Paladin",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="Trample\nWhen this creature enters, you gain 3 life.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    setup_interceptors=spinewoods_paladin_setup,
)

STUBBORN_BURROWFIEND = make_creature(
    name="Stubborn Burrowfiend",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Beast", "Mount"},
    text="Whenever this creature becomes saddled for the first time each turn, mill two cards, then this creature gets +X/+X until end of turn, where X is the number of creature cards in your graveyard.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

# =============================================================================
# THROW FROM THE SADDLE - Pump + fight effect
# =============================================================================

def _throw_from_the_saddle_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Throw from the Saddle after target selection."""
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

    events = []

    # Check if it's a Mount
    is_mount = 'Mount' in your_creature.characteristics.subtypes

    if is_mount:
        # Put a +1/+1 counter on it
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': your_creature_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ))
    else:
        # Gets +1/+1 until end of turn
        events.append(Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={
                'effect': 'pump',
                'target_id': your_creature_id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ))

    # Deal damage equal to power to target creature
    from src.engine import get_power
    power = get_power(your_creature, state)
    if is_mount:
        power += 1  # Account for the counter we're adding

    events.append(Event(
        type=EventType.DAMAGE,
        payload={
            'target': opponent_creature_id,
            'amount': power,
            'source': your_creature_id,
            'is_combat': False
        },
        source=choice.source_id
    ))

    return events


def throw_from_the_saddle_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Throw from the Saddle: Target creature you control gets +1/+1 until end of turn.
    Put a +1/+1 counter on it instead if it's a Mount. Then it deals damage equal to its
    power to target creature you don't control.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Throw from the Saddle":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "throw_from_the_saddle_spell"

    # Find your creatures and opponent creatures
    your_creatures = []
    opponent_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                if obj.controller == caster_id:
                    your_creatures.append(obj.id)
                else:
                    opponent_creatures.append(obj.id)

    if not your_creatures or not opponent_creatures:
        return []

    # Combined targeting
    all_targets = your_creatures + opponent_creatures

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=all_targets,
        prompt="Choose your creature to pump, then opponent's creature to damage",
        min_targets=2,
        max_targets=2,
        callback_data={'your_creatures': your_creatures, 'opponent_creatures': opponent_creatures}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _throw_from_the_saddle_execute

    return []


THROW_FROM_THE_SADDLE = make_sorcery(
    name="Throw from the Saddle",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+1 until end of turn. Put a +1/+1 counter on it instead if it's a Mount. Then it deals damage equal to its power to target creature you don't control.",
    resolve=throw_from_the_saddle_resolve,
)

# =============================================================================
# TRASH THE TOWN - Spree pump/trample/card draw
# =============================================================================

def _trash_the_town_counters_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Trash the Town counters mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 2},
        source=choice.source_id
    )]


def _trash_the_town_trample_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Trash the Town trample mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'grant_keywords',
            'target_id': target_id,
            'keywords': ['trample'],
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def _trash_the_town_draw_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Trash the Town draw mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'effect': 'grant_combat_damage_trigger',
            'target_id': target_id,
            'trigger': 'draw_two',
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def _trash_the_town_mode_execute(choice, selected_modes, state: GameState) -> list[Event]:
    """Execute Trash the Town modes after mode selection."""
    events = []
    spell_id = choice.source_id
    spell = state.objects.get(spell_id)
    controller_id = spell.controller if spell else state.active_player

    # Find valid targets: creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        return events

    # Process modes in order
    if 0 in selected_modes:
        target_choice = create_target_choice(
            state=state,
            player_id=controller_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a creature to put two +1/+1 counters on",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _trash_the_town_counters_execute
        return events

    if 1 in selected_modes:
        target_choice = create_target_choice(
            state=state,
            player_id=controller_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a creature to gain trample",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _trash_the_town_trample_execute
        return events

    if 2 in selected_modes:
        target_choice = create_target_choice(
            state=state,
            player_id=controller_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a creature to gain card draw trigger",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _trash_the_town_draw_execute

    return events


def trash_the_town_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Trash the Town - Spree modal spell.

    Spree (Choose one or more additional costs.):
    + {2} — Put two +1/+1 counters on target creature.
    + {1} — Target creature gains trample until end of turn.
    + {1} — Target creature gains draw trigger until end of turn.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Trash the Town":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "trash_the_town_spell"

    modes = [
        {"index": 0, "text": "Put two +1/+1 counters on target creature."},
        {"index": 1, "text": "Target creature gains trample until end of turn."},
        {"index": 2, "text": "Target creature gains card draw trigger until end of turn."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=3,
        prompt="Trash the Town - Choose one or more:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _trash_the_town_mode_execute

    return []


TRASH_THE_TOWN = make_instant(
    name="Trash the Town",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Put two +1/+1 counters on target creature.\n+ {1} — Target creature gains trample until end of turn.\n+ {1} — Until end of turn, target creature gains \"Whenever this creature deals combat damage to a player, draw two cards.\"",
    resolve=trash_the_town_resolve,
)

TUMBLEWEED_RISING = make_sorcery(
    name="Tumbleweed Rising",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create an X/X green Elemental creature token, where X is the greatest power among creatures you control.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

VORACIOUS_VARMINT = make_creature(
    name="Voracious Varmint",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Varmint"},
    text="Vigilance\n{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
)

AKUL_THE_UNREPENTANT = make_creature(
    name="Akul the Unrepentant",
    power=5, toughness=5,
    mana_cost="{B}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Dragon", "Rogue", "Scorpion"},
    supertypes={"Legendary"},
    text="Flying, trample\nSacrifice three other creatures: You may put a creature card from your hand onto the battlefield. Activate only as a sorcery and only once each turn.",
)

ANNIE_FLASH_THE_VETERAN = make_creature(
    name="Annie Flash, the Veteran",
    power=4, toughness=5,
    mana_cost="{3}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flash\nWhen Annie Flash enters, if you cast it, return target permanent card with mana value 3 or less from your graveyard to the battlefield tapped.\nWhenever Annie Flash becomes tapped, exile the top two cards of your library. You may play those cards this turn.",
    setup_interceptors=annie_flash_the_veteran_setup,
)

ANNIE_JOINS_UP = make_enchantment(
    name="Annie Joins Up",
    mana_cost="{1}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    text="When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls.\nIf a triggered ability of a legendary creature you control triggers, that ability triggers an additional time.",
    supertypes={"Legendary"},
    setup_interceptors=annie_joins_up_setup,
)

ASSIMILATION_AEGIS = make_artifact(
    name="Assimilation Aegis",
    mana_cost="{1}{W}{U}",
    text="When this Equipment enters, exile up to one target creature until this Equipment leaves the battlefield.\nWhenever this Equipment becomes attached to a creature, for as long as this Equipment remains attached to it, that creature becomes a copy of a creature card exiled with this Equipment.\nEquip {2}",
    subtypes={"Equipment"},
)

AT_KNIFEPOINT = make_enchantment(
    name="At Knifepoint",
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="During your turn, outlaws you control have first strike. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhenever you commit a crime, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\" This ability triggers only once each turn.",
)

BADLANDS_REVIVAL = make_sorcery(
    name="Badlands Revival",
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Return up to one target creature card from your graveyard to the battlefield. Return up to one target permanent card from your graveyard to your hand.",
)

BARON_BERTRAM_GRAYWATER = make_creature(
    name="Baron Bertram Graywater",
    power=3, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Noble", "Vampire"},
    supertypes={"Legendary"},
    text="Whenever one or more tokens you control enter, create a 1/1 black Vampire Rogue creature token with lifelink. This ability triggers only once each turn.\n{1}{B}, Sacrifice another creature or artifact: Draw a card.",
    setup_interceptors=baron_bertram_graywater_setup,
)

BONNY_PALL_CLEARCUTTER = make_creature(
    name="Bonny Pall, Clearcutter",
    power=6, toughness=5,
    mana_cost="{3}{G}{U}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Giant", "Scout"},
    supertypes={"Legendary"},
    text="Reach\nWhen Bonny Pall enters, create Beau, a legendary blue Ox creature token with \"Beau's power and toughness are each equal to the number of lands you control.\"\nWhenever you attack, draw a card, then you may put a land card from your hand or graveyard onto the battlefield.",
    setup_interceptors=bonny_pall_clearcutter_setup,
)

BREECHES_THE_BLASTMAKER = make_creature(
    name="Breeches, the Blastmaker",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Goblin", "Pirate"},
    supertypes={"Legendary"},
    text="Menace\nWhenever you cast your second spell each turn, you may sacrifice an artifact. If you do, flip a coin. When you win the flip, copy that spell. You may choose new targets for the copy. When you lose the flip, Breeches deals damage equal to that spell's mana value to any target.",
)

BRUSE_TARL_ROVING_RANCHER = make_creature(
    name="Bruse Tarl, Roving Rancher",
    power=4, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Oxen you control have double strike.\nWhenever Bruse Tarl enters or attacks, exile the top card of your library. If it's a land card, create a 2/2 white Ox creature token. Otherwise, you may cast it until the end of your next turn.",
    setup_interceptors=bruse_tarl_roving_rancher_setup,
)

CACTUSFOLK_SURESHOT = make_creature(
    name="Cactusfolk Sureshot",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Mercenary", "Plant"},
    text="Reach\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nAt the beginning of combat on your turn, other creatures you control with power 4 or greater gain trample and haste until end of turn.",
)

CONGREGATION_GRYFF = make_creature(
    name="Congregation Gryff",
    power=1, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hippogriff", "Mount"},
    text="Flying, lifelink\nWhenever this creature attacks while saddled, it gets +X/+X until end of turn, where X is the number of Mounts you control.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

DOC_AURLOCK_GRIZZLED_GENIUS = make_creature(
    name="Doc Aurlock, Grizzled Genius",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bear", "Druid"},
    supertypes={"Legendary"},
    text="Spells you cast from your graveyard or from exile cost {2} less to cast.\nPlotting cards from your hand costs {2} less.",
)

ERIETTE_THE_BEGUILER = make_creature(
    name="Eriette, the Beguiler",
    power=4, toughness=4,
    mana_cost="{1}{W}{U}{B}",
    colors={Color.BLACK, Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Lifelink\nWhenever an Aura you control becomes attached to a nonland permanent an opponent controls with mana value less than or equal to that Aura's mana value, gain control of that permanent for as long as that Aura is attached to it.",
)

ERTHA_JO_FRONTIER_MENTOR = make_creature(
    name="Ertha Jo, Frontier Mentor",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Advisor", "Kor"},
    supertypes={"Legendary"},
    text="When Ertha Jo enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nWhenever you activate an ability that targets a creature or player, copy that ability. You may choose new targets for the copy.",
    setup_interceptors=ertha_jo_frontier_mentor_setup,
)

FORM_A_POSSE = make_sorcery(
    name="Form a Posse",
    mana_cost="{X}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Create X 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

GHIRED_MIRROR_OF_THE_WILDS = make_creature(
    name="Ghired, Mirror of the Wilds",
    power=3, toughness=3,
    mana_cost="{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Haste\nNontoken creatures you control have \"{T}: Create a token that's a copy of target token you control that entered this turn.\"",
)

THE_GITROG_RAVENOUS_RIDE = make_creature(
    name="The Gitrog, Ravenous Ride",
    power=6, toughness=5,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Frog", "Horror", "Mount"},
    supertypes={"Legendary"},
    text="Trample, haste\nWhenever The Gitrog deals combat damage to a player, you may sacrifice a creature that saddled it this turn. If you do, draw X cards, then put up to X land cards from your hand onto the battlefield tapped, where X is the sacrificed creature's power.\nSaddle 1",
)

HONEST_RUTSTEIN = make_creature(
    name="Honest Rutstein",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Honest Rutstein enters, return target creature card from your graveyard to your hand.\nCreature spells you cast cost {1} less to cast.",
    setup_interceptors=honest_rutstein_setup,
)

INTIMIDATION_CAMPAIGN = make_enchantment(
    name="Intimidation Campaign",
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="When this enchantment enters, each opponent loses 1 life, you gain 1 life, and you draw a card.\nWhenever you commit a crime, you may return this enchantment to its owner's hand. (It returns only from the battlefield. Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
    setup_interceptors=intimidation_campaign_setup,
)

JEM_LIGHTFOOTE_SKY_EXPLORER = make_creature(
    name="Jem Lightfoote, Sky Explorer",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card.",
    setup_interceptors=jem_lightfoote_sky_explorer_setup,
)

JOLENE_PLUNDERING_PUGILIST = make_creature(
    name="Jolene, Plundering Pugilist",
    power=4, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever you attack with one or more creatures with power 4 or greater, create a Treasure token.\n{1}{R}, Sacrifice a Treasure: Jolene deals 1 damage to any target.",
)

KAMBAL_PROFITEERING_MAYOR = make_creature(
    name="Kambal, Profiteering Mayor",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Whenever one or more tokens your opponents control enter, for each of them, create a tapped token that's a copy of it. This ability triggers only once each turn.\nWhenever one or more tokens you control enter, each opponent loses 1 life and you gain 1 life.",
)

KELLAN_JOINS_UP = make_enchantment(
    name="Kellan Joins Up",
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    text="When Kellan Joins Up enters, you may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted. (You may cast it as a sorcery on a later turn without paying its mana cost.)\nWhenever a legendary creature you control enters, put a +1/+1 counter on each creature you control.",
    supertypes={"Legendary"},
    setup_interceptors=kellan_joins_up_setup,
)

KELLAN_THE_KID = make_creature(
    name="Kellan, the Kid",
    power=3, toughness=3,
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    subtypes={"Faerie", "Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flying, lifelink\nWhenever you cast a spell from anywhere other than your hand, you may cast a permanent spell with equal or lesser mana value from your hand without paying its mana cost. If you don't, you may put a land card from your hand onto the battlefield.",
)

KRAUM_VIOLENT_CACOPHONY = make_creature(
    name="Kraum, Violent Cacophony",
    power=2, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Horror", "Zombie"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast your second spell each turn, put a +1/+1 counter on Kraum and draw a card.",
    setup_interceptors=kraum_violent_cacophony_setup,
)

LAUGHING_JASPER_FLINT = make_creature(
    name="Laughing Jasper Flint",
    power=4, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Lizard", "Rogue"},
    supertypes={"Legendary"},
    text="Creatures you control but don't own are Mercenaries in addition to their other types.\nAt the beginning of your upkeep, exile the top X cards of target opponent's library, where X is the number of outlaws you control. Until end of turn, you may cast spells from among those cards, and mana of any type can be spent to cast those spells.",
)

LAZAV_FAMILIAR_STRANGER = make_creature(
    name="Lazav, Familiar Stranger",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Shapeshifter"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, put a +1/+1 counter on Lazav. Then you may exile a card from a graveyard. If a creature card was exiled this way, you may have Lazav become a copy of that card until end of turn. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

LILAH_UNDEFEATED_SLICKSHOT = make_creature(
    name="Lilah, Undefeated Slickshot",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever you cast a multicolored instant or sorcery spell from your hand, exile that spell instead of putting it into your graveyard as it resolves. If you do, it becomes plotted. (You may cast it as a sorcery on a later turn without paying its mana cost.)",
)

MAKE_YOUR_OWN_LUCK = make_sorcery(
    name="Make Your Own Luck",
    mana_cost="{3}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Look at the top three cards of your library. You may exile a nonland card from among them. If you do, it becomes plotted. Put the rest into your hand. (You may cast it as a sorcery on a later turn without paying its mana cost.)",
)

MALCOLM_THE_EYES = make_creature(
    name="Malcolm, the Eyes",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Pirate", "Siren"},
    supertypes={"Legendary"},
    text="Flying, haste\nWhenever you cast your second spell each turn, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=malcolm_the_eyes_setup,
)

MARCHESA_DEALER_OF_DEATH = make_creature(
    name="Marchesa, Dealer of Death",
    power=3, toughness=4,
    mana_cost="{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, you may pay {1}. If you do, look at the top two cards of your library. Put one of them into your hand and the other into your graveyard. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

MIRIAM_HERD_WHISPERER = make_creature(
    name="Miriam, Herd Whisperer",
    power=3, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Druid", "Human"},
    supertypes={"Legendary"},
    text="During your turn, Mounts and Vehicles you control have hexproof.\nWhenever a Mount or Vehicle you control attacks, put a +1/+1 counter on it.",
    setup_interceptors=miriam_herd_whisperer_setup,
)

OBEKA_SPLITTER_OF_SECONDS = make_creature(
    name="Obeka, Splitter of Seconds",
    power=2, toughness=5,
    mana_cost="{1}{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Ogre", "Warlock"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Obeka deals combat damage to a player, you get that many additional upkeep steps after this phase.",
)

OKO_THE_RINGLEADER = make_planeswalker(
    name="Oko, the Ringleader",
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    loyalty=3,
    subtypes={"Oko"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, Oko becomes a copy of up to one target creature you control until end of turn, except he has hexproof.\n+1: Draw two cards. If you've committed a crime this turn, discard a card. Otherwise, discard two cards.\n−1: Create a 3/3 green Elk creature token.\n−5: For each other nonland permanent you control, create a token that's a copy of that permanent.",
)

PILLAGE_THE_BOG = make_sorcery(
    name="Pillage the Bog",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Look at the top X cards of your library, where X is twice the number of lands you control. Put one of them into your hand and the rest on the bottom of your library in a random order.\nPlot {1}{B}{G} (You may pay {1}{B}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

RAKDOS_JOINS_UP = make_enchantment(
    name="Rakdos Joins Up",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="When Rakdos Joins Up enters, return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it.\nWhenever a legendary creature you control dies, Rakdos Joins Up deals damage equal to that creature's power to target opponent.",
    supertypes={"Legendary"},
)

RAKDOS_THE_MUSCLE = make_creature(
    name="Rakdos, the Muscle",
    power=6, toughness=5,
    mana_cost="{2}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "Mercenary"},
    supertypes={"Legendary"},
    text="Flying, trample\nWhenever you sacrifice another creature, exile cards equal to its mana value from the top of target player's library. Until your next end step, you may play those cards, and mana of any type can be spent to cast those spells.\nSacrifice another creature: Rakdos gains indestructible until end of turn. Tap it. Activate only once each turn.",
)

RIKU_OF_MANY_PATHS = make_creature(
    name="Riku of Many Paths",
    power=3, toughness=3,
    mana_cost="{G}{U}{R}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a modal spell, choose up to X, where X is the number of times you chose a mode for that spell —\n• Exile the top card of your library. Until the end of your next turn, you may play it.\n• Put a +1/+1 counter on Riku. It gains trample until end of turn.\n• Create a 1/1 blue Bird creature token with flying.",
)

ROXANNE_STARFALL_SAVANT = make_creature(
    name="Roxanne, Starfall Savant",
    power=4, toughness=3,
    mana_cost="{3}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Cat", "Druid"},
    supertypes={"Legendary"},
    text="Whenever Roxanne enters or attacks, create a tapped colorless artifact token named Meteorite with \"When this token enters, it deals 2 damage to any target\" and \"{T}: Add one mana of any color.\"\nWhenever you tap an artifact token for mana, add one mana of any type that artifact token produced.",
)

RUTHLESS_LAWBRINGER = make_creature(
    name="Ruthless Lawbringer",
    power=3, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Assassin", "Vampire"},
    text="When this creature enters, you may sacrifice another creature. When you do, destroy target nonland permanent.",
    setup_interceptors=ruthless_lawbringer_setup,
)

SATORU_THE_INFILTRATOR = make_creature(
    name="Satoru, the Infiltrator",
    power=2, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Ninja", "Rogue"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Satoru and/or one or more other nontoken creatures you control enter, if none of them were cast or no mana was spent to cast them, draw a card.",
)

SELVALA_EAGER_TRAILBLAZER = make_creature(
    name="Selvala, Eager Trailblazer",
    power=4, toughness=5,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever you cast a creature spell, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\n{T}: Choose a color. Add one mana of that color for each different power among creatures you control.",
    setup_interceptors=selvala_eager_trailblazer_setup,
)

SERAPHIC_STEED = make_creature(
    name="Seraphic Steed",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Mount", "Unicorn"},
    text="First strike, lifelink\nWhenever this creature attacks while saddled, create a 3/3 white Angel creature token with flying.\nSaddle 4 (Tap any number of other creatures you control with total power 4 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

# =============================================================================
# SLICK SEQUENCE - Damage + conditional draw
# =============================================================================

def _slick_sequence_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Slick Sequence after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    spell = state.objects.get(choice.source_id)
    controller = spell.controller if spell else state.active_player

    events = [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': 2,
            'source': choice.source_id,
            'is_combat': False
        },
        source=choice.source_id
    )]

    # Check if we've cast another spell this turn
    cast_another = choice.callback_data.get('cast_another_spell', False)
    if cast_another:
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': controller, 'amount': 1},
            source=choice.source_id
        ))

    return events


def slick_sequence_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Slick Sequence: Slick Sequence deals 2 damage to any target.
    If you've cast another spell this turn, draw a card.
    """
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Slick Sequence":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "slick_sequence_spell"

    # Check if we've cast another spell this turn
    spells_cast = getattr(state, 'spells_cast_this_turn', {}).get(caster_id, 0)
    cast_another = spells_cast > 1  # More than just this spell

    # Find valid targets: any target (creature, planeswalker, or player)
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            types = obj.characteristics.types
            if CardType.CREATURE in types or CardType.PLANESWALKER in types:
                valid_targets.append(obj.id)

    # Add players as targets
    for player_id in state.players.keys():
        valid_targets.append(player_id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose any target to deal 2 damage to",
        min_targets=1,
        max_targets=1,
        callback_data={'cast_another_spell': cast_another}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _slick_sequence_execute

    return []


SLICK_SEQUENCE = make_instant(
    name="Slick Sequence",
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Slick Sequence deals 2 damage to any target. If you've cast another spell this turn, draw a card.",
    resolve=slick_sequence_resolve,
)

TAII_WAKEEN_PERFECT_SHOT = make_creature(
    name="Taii Wakeen, Perfect Shot",
    power=2, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever a source you control deals noncombat damage to a creature equal to that creature's toughness, draw a card.\n{X}, {T}: If a source you control would deal noncombat damage to a permanent or player this turn, it deals that much damage plus X instead.",
)

VIAL_SMASHER_GLEEFUL_GRENADIER = make_creature(
    name="Vial Smasher, Gleeful Grenadier",
    power=3, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever another outlaw you control enters, Vial Smasher deals 1 damage to target opponent. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
    setup_interceptors=vial_smasher_gleeful_grenadier_setup,
)

VRASKA_JOINS_UP = make_enchantment(
    name="Vraska Joins Up",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="When Vraska Joins Up enters, put a deathtouch counter on each creature you control.\nWhenever a legendary creature you control deals combat damage to a player, draw a card.",
    supertypes={"Legendary"},
    setup_interceptors=vraska_joins_up_setup,
)

VRASKA_THE_SILENCER = make_creature(
    name="Vraska, the Silencer",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Assassin", "Gorgon"},
    supertypes={"Legendary"},
    text="Deathtouch\nWhenever a nontoken creature an opponent controls dies, you may pay {1}. If you do, return that card to the battlefield tapped under your control. It's a Treasure artifact with \"{T}, Sacrifice this artifact: Add one mana of any color,\" and it loses all other card types.",
)

WRANGLER_OF_THE_DAMNED = make_creature(
    name="Wrangler of the Damned",
    power=1, toughness=4,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, create a 2/2 white Spirit creature token with flying.",
    setup_interceptors=wrangler_of_the_damned_setup,
)

WYLIE_DUKE_ATIIN_HERO = make_creature(
    name="Wylie Duke, Atiin Hero",
    power=4, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Ranger"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever Wylie Duke becomes tapped, you gain 1 life and draw a card.",
)

BANDITS_HAUL = make_artifact(
    name="Bandit's Haul",
    mana_cost="{3}",
    text="Whenever you commit a crime, put a loot counter on this artifact. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\n{T}: Add one mana of any color.\n{2}, {T}, Remove two loot counters from this artifact: Draw a card.",
)

BOOM_BOX = make_artifact(
    name="Boom Box",
    mana_cost="{2}",
    text="{6}, {T}, Sacrifice this artifact: Destroy up to one target artifact, up to one target creature, and up to one target land.",
)

GOLD_PAN = make_artifact(
    name="Gold Pan",
    mana_cost="{2}",
    text="When this Equipment enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nEquipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

LAVASPUR_BOOTS = make_artifact(
    name="Lavaspur Boots",
    mana_cost="{1}",
    text="Equipped creature gets +1/+0 and has haste and ward {1}. (Whenever it becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\nEquip {1}",
    subtypes={"Equipment"},
)

LUXURIOUS_LOCOMOTIVE = make_artifact(
    name="Luxurious Locomotive",
    mana_cost="{5}",
    text="Whenever this Vehicle attacks, create a Treasure token for each creature that crewed it this turn. (They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")\nCrew 1. Activate only once each turn. (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

MOBILE_HOMESTEAD = make_artifact(
    name="Mobile Homestead",
    mana_cost="{2}",
    text="This Vehicle has haste as long as you control a Mount.\nWhenever this Vehicle attacks, look at the top card of your library. If it's a land card, you may put it onto the battlefield tapped.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

OASIS_GARDENER = make_artifact_creature(
    name="Oasis Gardener",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="When this creature enters, you gain 2 life.\n{T}: Add one mana of any color.",
    setup_interceptors=oasis_gardener_setup,
)

REDROCK_SENTINEL = make_artifact_creature(
    name="Redrock Sentinel",
    power=2, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Golem"},
    text="Defender\n{2}, {T}, Sacrifice a land: Draw a card and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SILVER_DEPUTY = make_artifact_creature(
    name="Silver Deputy",
    power=1, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Mercenary"},
    text="When this creature enters, you may search your library for a basic land card or a Desert card, reveal it, then shuffle and put it on top.\n{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.",
    setup_interceptors=silver_deputy_setup,
)

STERLING_HOUND = make_artifact_creature(
    name="Sterling Hound",
    power=3, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Dog"},
    text="When this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    setup_interceptors=sterling_hound_setup,
)

TOMB_TRAWLER = make_artifact_creature(
    name="Tomb Trawler",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Golem"},
    text="{2}: Put target card from your graveyard on the bottom of your library.",
)

ABRADED_BLUFFS = make_land(
    name="Abraded Bluffs",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {R} or {W}.",
    subtypes={"Desert"},
)

ARID_ARCHWAY = make_land(
    name="Arid Archway",
    text="This land enters tapped.\nWhen this land enters, return a land you control to its owner's hand. If another Desert was returned this way, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Add {C}{C}.",
    subtypes={"Desert"},
)

BRISTLING_BACKWOODS = make_land(
    name="Bristling Backwoods",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {R} or {G}.",
    subtypes={"Desert"},
)

CONDUIT_PYLONS = make_land(
    name="Conduit Pylons",
    text="When this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Add {C}.\n{1}, {T}: Add one mana of any color.",
    subtypes={"Desert"},
)

CREOSOTE_HEATH = make_land(
    name="Creosote Heath",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {G} or {W}.",
    subtypes={"Desert"},
)

ERODED_CANYON = make_land(
    name="Eroded Canyon",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {U} or {R}.",
    subtypes={"Desert"},
)

FESTERING_GULCH = make_land(
    name="Festering Gulch",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {B} or {G}.",
    subtypes={"Desert"},
)

FORLORN_FLATS = make_land(
    name="Forlorn Flats",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {W} or {B}.",
    subtypes={"Desert"},
)

JAGGED_BARRENS = make_land(
    name="Jagged Barrens",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {B} or {R}.",
    subtypes={"Desert"},
)

LONELY_ARROYO = make_land(
    name="Lonely Arroyo",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {W} or {U}.",
    subtypes={"Desert"},
)

LUSH_OASIS = make_land(
    name="Lush Oasis",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {G} or {U}.",
    subtypes={"Desert"},
)

MIRAGE_MESA = make_land(
    name="Mirage Mesa",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
    subtypes={"Desert"},
)

SANDSTORM_VERGE = make_land(
    name="Sandstorm Verge",
    text="{T}: Add {C}.\n{3}, {T}: Target creature can't block this turn. Activate only as a sorcery.",
    subtypes={"Desert"},
)

SOURED_SPRINGS = make_land(
    name="Soured Springs",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {U} or {B}.",
    subtypes={"Desert"},
)

BUCOLIC_RANCH = make_land(
    name="Bucolic Ranch",
    text="{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a Mount spell.\n{3}, {T}: Look at the top card of your library. If it's a Mount card, you may reveal it and put it into your hand. If you don't put it into your hand, you may put it on the bottom of your library.",
    subtypes={"Desert"},
)

BLOOMING_MARSH = make_land(
    name="Blooming Marsh",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {B} or {G}.",
)

BOTANICAL_SANCTUM = make_land(
    name="Botanical Sanctum",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {G} or {U}.",
)

CONCEALED_COURTYARD = make_land(
    name="Concealed Courtyard",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {W} or {B}.",
)

INSPIRING_VANTAGE = make_land(
    name="Inspiring Vantage",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {R} or {W}.",
)

SPIREBLUFF_CANAL = make_land(
    name="Spirebluff Canal",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {U} or {R}.",
)

JACE_REAWAKENED = make_planeswalker(
    name="Jace Reawakened",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    loyalty=3,
    subtypes={"Jace"},
    supertypes={"Legendary"},
    text="You can't cast Jace Reawakened during your first, second, or third turns of the game.\n+1: Draw a card, then discard a card.\n+1: You may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted.\n−6: Until end of turn, whenever you cast a spell, copy it. You may choose new targets for the copy.",
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

OUTLAWS_THUNDER_JUNCTION_CARDS = {
    "Another Round": ANOTHER_ROUND,
    "Archangel of Tithes": ARCHANGEL_OF_TITHES,
    "Armored Armadillo": ARMORED_ARMADILLO,
    "Aven Interrupter": AVEN_INTERRUPTER,
    "Bounding Felidar": BOUNDING_FELIDAR,
    "Bovine Intervention": BOVINE_INTERVENTION,
    "Bridled Bighorn": BRIDLED_BIGHORN,
    "Claim Jumper": CLAIM_JUMPER,
    "Dust Animus": DUST_ANIMUS,
    "Eriette's Lullaby": ERIETTES_LULLABY,
    "Final Showdown": FINAL_SHOWDOWN,
    "Fortune, Loyal Steed": FORTUNE_LOYAL_STEED,
    "Frontier Seeker": FRONTIER_SEEKER,
    "Getaway Glamer": GETAWAY_GLAMER,
    "High Noon": HIGH_NOON,
    "Holy Cow": HOLY_COW,
    "Inventive Wingsmith": INVENTIVE_WINGSMITH,
    "Lassoed by the Law": LASSOED_BY_THE_LAW,
    "Mystical Tether": MYSTICAL_TETHER,
    "Nurturing Pixie": NURTURING_PIXIE,
    "Omenport Vigilante": OMENPORT_VIGILANTE,
    "One Last Job": ONE_LAST_JOB,
    "Outlaw Medic": OUTLAW_MEDIC,
    "Prairie Dog": PRAIRIE_DOG,
    "Prosperity Tycoon": PROSPERITY_TYCOON,
    "Requisition Raid": REQUISITION_RAID,
    "Rustler Rampage": RUSTLER_RAMPAGE,
    "Shepherd of the Clouds": SHEPHERD_OF_THE_CLOUDS,
    "Sheriff of Safe Passage": SHERIFF_OF_SAFE_PASSAGE,
    "Stagecoach Security": STAGECOACH_SECURITY,
    "Steer Clear": STEER_CLEAR,
    "Sterling Keykeeper": STERLING_KEYKEEPER,
    "Sterling Supplier": STERLING_SUPPLIER,
    "Take Up the Shield": TAKE_UP_THE_SHIELD,
    "Thunder Lasso": THUNDER_LASSO,
    "Trained Arynx": TRAINED_ARYNX,
    "Vengeful Townsfolk": VENGEFUL_TOWNSFOLK,
    "Wanted Griffin": WANTED_GRIFFIN,
    "Archmage's Newt": ARCHMAGES_NEWT,
    "Canyon Crab": CANYON_CRAB,
    "Daring Thunder-Thief": DARING_THUNDERTHIEF,
    "Deepmuck Desperado": DEEPMUCK_DESPERADO,
    "Djinn of Fool's Fall": DJINN_OF_FOOLS_FALL,
    "Double Down": DOUBLE_DOWN,
    "Duelist of the Mind": DUELIST_OF_THE_MIND,
    "Emergent Haunting": EMERGENT_HAUNTING,
    "Failed Fording": FAILED_FORDING,
    "Fblthp, Lost on the Range": FBLTHP_LOST_ON_THE_RANGE,
    "Fleeting Reflection": FLEETING_REFLECTION,
    "Geralf, the Fleshwright": GERALF_THE_FLESHWRIGHT,
    "Geyser Drake": GEYSER_DRAKE,
    "Harrier Strix": HARRIER_STRIX,
    "Jailbreak Scheme": JAILBREAK_SCHEME,
    "The Key to the Vault": THE_KEY_TO_THE_VAULT,
    "Loan Shark": LOAN_SHARK,
    "Marauding Sphinx": MARAUDING_SPHINX,
    "Metamorphic Blast": METAMORPHIC_BLAST,
    "Nimble Brigand": NIMBLE_BRIGAND,
    "Outlaw Stitcher": OUTLAW_STITCHER,
    "Peerless Ropemaster": PEERLESS_ROPEMASTER,
    "Phantom Interference": PHANTOM_INTERFERENCE,
    "Plan the Heist": PLAN_THE_HEIST,
    "Razzle-Dazzler": RAZZLEDAZZLER,
    "Seize the Secrets": SEIZE_THE_SECRETS,
    "Shackle Slinger": SHACKLE_SLINGER,
    "Shifting Grift": SHIFTING_GRIFT,
    "Slickshot Lockpicker": SLICKSHOT_LOCKPICKER,
    "Slickshot Vault-Buster": SLICKSHOT_VAULTBUSTER,
    "Spring Splasher": SPRING_SPLASHER,
    "Step Between Worlds": STEP_BETWEEN_WORLDS,
    "Stoic Sphinx": STOIC_SPHINX,
    "Stop Cold": STOP_COLD,
    "Take the Fall": TAKE_THE_FALL,
    "This Town Ain't Big Enough": THIS_TOWN_AINT_BIG_ENOUGH,
    "Three Steps Ahead": THREE_STEPS_AHEAD,
    "Visage Bandit": VISAGE_BANDIT,
    "Ambush Gigapede": AMBUSH_GIGAPEDE,
    "Binding Negotiation": BINDING_NEGOTIATION,
    "Blacksnag Buzzard": BLACKSNAG_BUZZARD,
    "Blood Hustler": BLOOD_HUSTLER,
    "Boneyard Desecrator": BONEYARD_DESECRATOR,
    "Caustic Bronco": CAUSTIC_BRONCO,
    "Consuming Ashes": CONSUMING_ASHES,
    "Corrupted Conviction": CORRUPTED_CONVICTION,
    "Desert's Due": DESERTS_DUE,
    "Desperate Bloodseeker": DESPERATE_BLOODSEEKER,
    "Fake Your Own Death": FAKE_YOUR_OWN_DEATH,
    "Forsaken Miner": FORSAKEN_MINER,
    "Gisa, the Hellraiser": GISA_THE_HELLRAISER,
    "Hollow Marauder": HOLLOW_MARAUDER,
    "Insatiable Avarice": INSATIABLE_AVARICE,
    "Kaervek, the Punisher": KAERVEK_THE_PUNISHER,
    "Lively Dirge": LIVELY_DIRGE,
    "Mourner's Surprise": MOURNERS_SURPRISE,
    "Neutralize the Guards": NEUTRALIZE_THE_GUARDS,
    "Nezumi Linkbreaker": NEZUMI_LINKBREAKER,
    "Overzealous Muscle": OVERZEALOUS_MUSCLE,
    "Pitiless Carnage": PITILESS_CARNAGE,
    "Rakish Crew": RAKISH_CREW,
    "Rattleback Apothecary": RATTLEBACK_APOTHECARY,
    "Raven of Fell Omens": RAVEN_OF_FELL_OMENS,
    "Rictus Robber": RICTUS_ROBBER,
    "Rooftop Assassin": ROOFTOP_ASSASSIN,
    "Rush of Dread": RUSH_OF_DREAD,
    "Servant of the Stinger": SERVANT_OF_THE_STINGER,
    "Shoot the Sheriff": SHOOT_THE_SHERIFF,
    "Skulduggery": SKULDUGGERY,
    "Tinybones Joins Up": TINYBONES_JOINS_UP,
    "Tinybones, the Pickpocket": TINYBONES_THE_PICKPOCKET,
    "Treasure Dredger": TREASURE_DREDGER,
    "Unfortunate Accident": UNFORTUNATE_ACCIDENT,
    "Unscrupulous Contractor": UNSCRUPULOUS_CONTRACTOR,
    "Vadmir, New Blood": VADMIR_NEW_BLOOD,
    "Vault Plunderer": VAULT_PLUNDERER,
    "Brimstone Roundup": BRIMSTONE_ROUNDUP,
    "Calamity, Galloping Inferno": CALAMITY_GALLOPING_INFERNO,
    "Caught in the Crossfire": CAUGHT_IN_THE_CROSSFIRE,
    "Cunning Coyote": CUNNING_COYOTE,
    "Deadeye Duelist": DEADEYE_DUELIST,
    "Demonic Ruckus": DEMONIC_RUCKUS,
    "Discerning Peddler": DISCERNING_PEDDLER,
    "Explosive Derailment": EXPLOSIVE_DERAILMENT,
    "Ferocification": FEROCIFICATION,
    "Gila Courser": GILA_COURSER,
    "Great Train Heist": GREAT_TRAIN_HEIST,
    "Hell to Pay": HELL_TO_PAY,
    "Hellspur Brute": HELLSPUR_BRUTE,
    "Hellspur Posse Boss": HELLSPUR_POSSE_BOSS,
    "Highway Robbery": HIGHWAY_ROBBERY,
    "Irascible Wolverine": IRASCIBLE_WOLVERINE,
    "Iron-Fist Pulverizer": IRONFIST_PULVERIZER,
    "Longhorn Sharpshooter": LONGHORN_SHARPSHOOTER,
    "Magda, the Hoardmaster": MAGDA_THE_HOARDMASTER,
    "Magebane Lizard": MAGEBANE_LIZARD,
    "Mine Raider": MINE_RAIDER,
    "Outlaws' Fury": OUTLAWS_FURY,
    "Prickly Pair": PRICKLY_PAIR,
    "Quick Draw": QUICK_DRAW,
    "Quilled Charger": QUILLED_CHARGER,
    "Reckless Lackey": RECKLESS_LACKEY,
    "Resilient Roadrunner": RESILIENT_ROADRUNNER,
    "Return the Favor": RETURN_THE_FAVOR,
    "Rodeo Pyromancers": RODEO_PYROMANCERS,
    "Scalestorm Summoner": SCALESTORM_SUMMONER,
    "Scorching Shot": SCORCHING_SHOT,
    "Slickshot Show-Off": SLICKSHOT_SHOWOFF,
    "Stingerback Terror": STINGERBACK_TERROR,
    "Take for a Ride": TAKE_FOR_A_RIDE,
    "Terror of the Peaks": TERROR_OF_THE_PEAKS,
    "Thunder Salvo": THUNDER_SALVO,
    "Trick Shot": TRICK_SHOT,
    "Aloe Alchemist": ALOE_ALCHEMIST,
    "Ankle Biter": ANKLE_BITER,
    "Beastbond Outcaster": BEASTBOND_OUTCASTER,
    "Betrayal at the Vault": BETRAYAL_AT_THE_VAULT,
    "Bristlepack Sentry": BRISTLEPACK_SENTRY,
    "Bristly Bill, Spine Sower": BRISTLY_BILL_SPINE_SOWER,
    "Cactarantula": CACTARANTULA,
    "Colossal Rattlewurm": COLOSSAL_RATTLEWURM,
    "Dance of the Tumbleweeds": DANCE_OF_THE_TUMBLEWEEDS,
    "Drover Grizzly": DROVER_GRIZZLY,
    "Freestrider Commando": FREESTRIDER_COMMANDO,
    "Freestrider Lookout": FREESTRIDER_LOOKOUT,
    "Full Steam Ahead": FULL_STEAM_AHEAD,
    "Giant Beaver": GIANT_BEAVER,
    "Gold Rush": GOLD_RUSH,
    "Goldvein Hydra": GOLDVEIN_HYDRA,
    "Hardbristle Bandit": HARDBRISTLE_BANDIT,
    "Intrepid Stablemaster": INTREPID_STABLEMASTER,
    "Map the Frontier": MAP_THE_FRONTIER,
    "Ornery Tumblewagg": ORNERY_TUMBLEWAGG,
    "Outcaster Greenblade": OUTCASTER_GREENBLADE,
    "Outcaster Trailblazer": OUTCASTER_TRAILBLAZER,
    "Patient Naturalist": PATIENT_NATURALIST,
    "Railway Brawler": RAILWAY_BRAWLER,
    "Rambling Possum": RAMBLING_POSSUM,
    "Raucous Entertainer": RAUCOUS_ENTERTAINER,
    "Reach for the Sky": REACH_FOR_THE_SKY,
    "Rise of the Varmints": RISE_OF_THE_VARMINTS,
    "Smuggler's Surprise": SMUGGLERS_SURPRISE,
    "Snakeskin Veil": SNAKESKIN_VEIL,
    "Spinewoods Armadillo": SPINEWOODS_ARMADILLO,
    "Spinewoods Paladin": SPINEWOODS_PALADIN,
    "Stubborn Burrowfiend": STUBBORN_BURROWFIEND,
    "Throw from the Saddle": THROW_FROM_THE_SADDLE,
    "Trash the Town": TRASH_THE_TOWN,
    "Tumbleweed Rising": TUMBLEWEED_RISING,
    "Voracious Varmint": VORACIOUS_VARMINT,
    "Akul the Unrepentant": AKUL_THE_UNREPENTANT,
    "Annie Flash, the Veteran": ANNIE_FLASH_THE_VETERAN,
    "Annie Joins Up": ANNIE_JOINS_UP,
    "Assimilation Aegis": ASSIMILATION_AEGIS,
    "At Knifepoint": AT_KNIFEPOINT,
    "Badlands Revival": BADLANDS_REVIVAL,
    "Baron Bertram Graywater": BARON_BERTRAM_GRAYWATER,
    "Bonny Pall, Clearcutter": BONNY_PALL_CLEARCUTTER,
    "Breeches, the Blastmaker": BREECHES_THE_BLASTMAKER,
    "Bruse Tarl, Roving Rancher": BRUSE_TARL_ROVING_RANCHER,
    "Cactusfolk Sureshot": CACTUSFOLK_SURESHOT,
    "Congregation Gryff": CONGREGATION_GRYFF,
    "Doc Aurlock, Grizzled Genius": DOC_AURLOCK_GRIZZLED_GENIUS,
    "Eriette, the Beguiler": ERIETTE_THE_BEGUILER,
    "Ertha Jo, Frontier Mentor": ERTHA_JO_FRONTIER_MENTOR,
    "Form a Posse": FORM_A_POSSE,
    "Ghired, Mirror of the Wilds": GHIRED_MIRROR_OF_THE_WILDS,
    "The Gitrog, Ravenous Ride": THE_GITROG_RAVENOUS_RIDE,
    "Honest Rutstein": HONEST_RUTSTEIN,
    "Intimidation Campaign": INTIMIDATION_CAMPAIGN,
    "Jem Lightfoote, Sky Explorer": JEM_LIGHTFOOTE_SKY_EXPLORER,
    "Jolene, Plundering Pugilist": JOLENE_PLUNDERING_PUGILIST,
    "Kambal, Profiteering Mayor": KAMBAL_PROFITEERING_MAYOR,
    "Kellan Joins Up": KELLAN_JOINS_UP,
    "Kellan, the Kid": KELLAN_THE_KID,
    "Kraum, Violent Cacophony": KRAUM_VIOLENT_CACOPHONY,
    "Laughing Jasper Flint": LAUGHING_JASPER_FLINT,
    "Lazav, Familiar Stranger": LAZAV_FAMILIAR_STRANGER,
    "Lilah, Undefeated Slickshot": LILAH_UNDEFEATED_SLICKSHOT,
    "Make Your Own Luck": MAKE_YOUR_OWN_LUCK,
    "Malcolm, the Eyes": MALCOLM_THE_EYES,
    "Marchesa, Dealer of Death": MARCHESA_DEALER_OF_DEATH,
    "Miriam, Herd Whisperer": MIRIAM_HERD_WHISPERER,
    "Obeka, Splitter of Seconds": OBEKA_SPLITTER_OF_SECONDS,
    "Oko, the Ringleader": OKO_THE_RINGLEADER,
    "Pillage the Bog": PILLAGE_THE_BOG,
    "Rakdos Joins Up": RAKDOS_JOINS_UP,
    "Rakdos, the Muscle": RAKDOS_THE_MUSCLE,
    "Riku of Many Paths": RIKU_OF_MANY_PATHS,
    "Roxanne, Starfall Savant": ROXANNE_STARFALL_SAVANT,
    "Ruthless Lawbringer": RUTHLESS_LAWBRINGER,
    "Satoru, the Infiltrator": SATORU_THE_INFILTRATOR,
    "Selvala, Eager Trailblazer": SELVALA_EAGER_TRAILBLAZER,
    "Seraphic Steed": SERAPHIC_STEED,
    "Slick Sequence": SLICK_SEQUENCE,
    "Taii Wakeen, Perfect Shot": TAII_WAKEEN_PERFECT_SHOT,
    "Vial Smasher, Gleeful Grenadier": VIAL_SMASHER_GLEEFUL_GRENADIER,
    "Vraska Joins Up": VRASKA_JOINS_UP,
    "Vraska, the Silencer": VRASKA_THE_SILENCER,
    "Wrangler of the Damned": WRANGLER_OF_THE_DAMNED,
    "Wylie Duke, Atiin Hero": WYLIE_DUKE_ATIIN_HERO,
    "Bandit's Haul": BANDITS_HAUL,
    "Boom Box": BOOM_BOX,
    "Gold Pan": GOLD_PAN,
    "Lavaspur Boots": LAVASPUR_BOOTS,
    "Luxurious Locomotive": LUXURIOUS_LOCOMOTIVE,
    "Mobile Homestead": MOBILE_HOMESTEAD,
    "Oasis Gardener": OASIS_GARDENER,
    "Redrock Sentinel": REDROCK_SENTINEL,
    "Silver Deputy": SILVER_DEPUTY,
    "Sterling Hound": STERLING_HOUND,
    "Tomb Trawler": TOMB_TRAWLER,
    "Abraded Bluffs": ABRADED_BLUFFS,
    "Arid Archway": ARID_ARCHWAY,
    "Bristling Backwoods": BRISTLING_BACKWOODS,
    "Conduit Pylons": CONDUIT_PYLONS,
    "Creosote Heath": CREOSOTE_HEATH,
    "Eroded Canyon": ERODED_CANYON,
    "Festering Gulch": FESTERING_GULCH,
    "Forlorn Flats": FORLORN_FLATS,
    "Jagged Barrens": JAGGED_BARRENS,
    "Lonely Arroyo": LONELY_ARROYO,
    "Lush Oasis": LUSH_OASIS,
    "Mirage Mesa": MIRAGE_MESA,
    "Sandstorm Verge": SANDSTORM_VERGE,
    "Soured Springs": SOURED_SPRINGS,
    "Bucolic Ranch": BUCOLIC_RANCH,
    "Blooming Marsh": BLOOMING_MARSH,
    "Botanical Sanctum": BOTANICAL_SANCTUM,
    "Concealed Courtyard": CONCEALED_COURTYARD,
    "Inspiring Vantage": INSPIRING_VANTAGE,
    "Spirebluff Canal": SPIREBLUFF_CANAL,
    "Jace Reawakened": JACE_REAWAKENED,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(OUTLAWS_THUNDER_JUNCTION_CARDS)} Outlaws_of_Thunder_Junction cards")
