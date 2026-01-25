"""
Man of Pider - Custom Card Set (formerly "Marvel's Spider-Man")

Custom/fan-made set with 198 cards.
Features mechanics: Web, Sinister, Heroic, Spider-Sense, Symbiote

Renamed to avoid collision with official MTG Spider-Man set in src/cards/spider_man.py
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    from src.engine import CardDefinition, Characteristics
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


def make_land(name: str, subtypes: set = None, supertypes: set = None, text: str = ""):
    """Helper to create land card definitions."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        ),
        text=text
    )


# =============================================================================
# SPIDER-MAN KEYWORD HELPERS
# =============================================================================

from src.cards.interceptor_helpers import (
    make_etb_trigger, make_attack_trigger, make_damage_trigger,
    make_spell_cast_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, all_opponents, other_creatures_with_subtype,
    make_death_trigger, make_upkeep_trigger, make_end_step_trigger
)


def make_web_etb(source_obj: GameObject, num_targets: int = 1) -> Interceptor:
    """
    Web — When this creature enters, tap up to N target creatures.
    They don't untap during their controllers' next untap steps.

    Note: Full implementation requires targeting system. This creates the ETB trigger.
    """
    def web_effect(event: Event, state: GameState) -> list[Event]:
        # In full implementation, targets would be chosen
        # For now, returns events that would tap and freeze targets
        return []  # Targeting system fills this in

    return make_etb_trigger(source_obj, web_effect)


def make_web_attack(source_obj: GameObject) -> Interceptor:
    """
    Web — Whenever this creature attacks, tap target creature an opponent controls.
    It doesn't untap during its controller's next untap step.
    """
    def web_effect(event: Event, state: GameState) -> list[Event]:
        # In full implementation, target would be chosen
        return []  # Targeting system fills this in

    return make_attack_trigger(source_obj, web_effect)


def make_spider_sense(source_obj: GameObject, cost: int = 1) -> Interceptor:
    """
    Spider-Sense — Whenever an opponent casts a spell, you may pay {N}. If you do, scry 1.

    Args:
        source_obj: The creature with spider-sense
        cost: Mana to pay (default 1)
    """
    def sense_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        # Trigger when opponent casts
        return event.payload.get('caster') != obj.controller

    def sense_effect(event: Event, state: GameState) -> list[Event]:
        # Creates a scry trigger (player can choose to pay)
        # Full implementation would include mana payment choice
        return []  # Priority system handles may ability

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: sense_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=sense_effect(e, s)
        ),
        duration='while_on_battlefield'
    )


def make_heroic(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]]
) -> Interceptor:
    """
    Heroic — Whenever you cast a spell that targets this creature, trigger effect.

    Args:
        source_obj: The creature with heroic
        effect_fn: Effect to trigger (receives the CAST event)
    """
    def heroic_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        # Check if this creature is targeted
        targets = event.payload.get('targets', [])
        return obj.id in targets

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: heroic_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(e, s)
        ),
        duration='while_on_battlefield'
    )


def make_sinister(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]]
) -> Interceptor:
    """
    Sinister — Whenever an opponent loses life, trigger effect.

    Args:
        source_obj: The permanent with sinister
        effect_fn: Effect to trigger
    """
    def sinister_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount >= 0:  # Must be life loss
            return False
        player = event.payload.get('player')
        return player != obj.controller  # Opponent lost life

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: sinister_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(e, s)
        ),
        duration='while_on_battlefield'
    )


def make_symbiote_host(
    source_obj: GameObject,
    power_bonus: int,
    toughness_bonus: int
) -> list[Interceptor]:
    """
    Symbiote — This creature gets +X/+Y. When it takes damage, you may detach the symbiote.

    Returns interceptors for the P/T boost and damage trigger.
    """
    interceptors = []

    # Static P/T boost
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id

    interceptors.extend(make_static_pt_boost(source_obj, power_bonus, toughness_bonus, is_self))

    # Damage trigger (optional detach)
    def damage_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == obj.id

    def damage_handler(event: Event, state: GameState) -> InterceptorResult:
        # Could create a "may detach" choice event
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    interceptors.append(Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: damage_filter(e, s, source_obj),
        handler=damage_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


# =============================================================================
# WHITE CARDS - HEROES
# =============================================================================

def spider_man_friendly_neighbor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Web ETB (tap 2) + Spider-Sense (pay 1, scry 1)"""
    interceptors = []
    interceptors.append(make_web_etb(obj, num_targets=2))
    interceptors.append(make_spider_sense(obj, cost=1))
    return interceptors

SPIDER_MAN_FRIENDLY_NEIGHBOR = make_creature(
    name="Spider-Man, Friendly Neighbor",
    power=3,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flash. Web — When Spider-Man enters, tap up to two target creatures. They don't untap during their controllers' next untap steps. Spider-Sense — Whenever an opponent casts a spell, you may pay {1}. If you do, scry 1.",
    setup_interceptors=spider_man_friendly_neighbor_setup
)

def spider_man_with_great_power_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Heroic - draw a card and create a 1/1 Spider token"""
    def heroic_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Spider'}},
            }, source=obj.id)
        ]
    return [make_heroic(obj, heroic_effect)]

SPIDER_MAN_WITH_GREAT_POWER = make_creature(
    name="Spider-Man, With Great Power",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Heroic — Whenever you cast a spell that targets Spider-Man, draw a card and create a 1/1 white Spider creature token.",
    setup_interceptors=spider_man_with_great_power_setup
)

def spider_gwen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Web on attack - tap target creature"""
    return [make_web_attack(obj)]

SPIDER_GWEN = make_creature(
    name="Spider-Gwen",
    power=3,
    toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Web — Whenever Spider-Gwen attacks, tap target creature an opponent controls. It doesn't untap during its controller's next untap step.",
    setup_interceptors=spider_gwen_setup
)

def miles_morales_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Venom Strike - combat damage to player, deal 2 to creature"""
    def venom_strike_effect(event: Event, state: GameState) -> list[Event]:
        # May deal 2 damage to target creature (targeting handled by system)
        return []  # Targeting system fills this in
    return [make_damage_trigger(obj, venom_strike_effect, combat_only=True)]

MILES_MORALES = make_creature(
    name="Miles Morales",
    power=3,
    toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flash. Camouflage — Miles Morales can't be blocked as long as you control another Spider. Venom Strike — When Miles deals combat damage to a player, you may have him deal 2 damage to target creature.",
    setup_interceptors=miles_morales_setup
)

def spider_woman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pheromone Control - opponent creatures get -1/-0"""
    def opponent_creatures(target: GameObject, state: GameState) -> bool:
        return (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return make_static_pt_boost(obj, -1, 0, opponent_creatures)

SPIDER_WOMAN = make_creature(
    name="Spider-Woman",
    power=4,
    toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Pheromone Control — Creatures your opponents control get -1/-0. Venom Blast — {2}{R}: Spider-Woman deals 2 damage to target creature.",
    setup_interceptors=spider_woman_setup
)

def aunt_may_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Spider you control attacks, gain 1 life"""
    def spider_attacks_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == source.controller and
                'Spider' in attacker.characteristics.subtypes)

    def gain_life_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_attack_trigger(obj, gain_life_effect, filter_fn=spider_attacks_filter)]

AUNT_MAY = make_creature(
    name="Aunt May",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="Whenever a Spider you control attacks, you gain 1 life. {T}: Target Spider you control gets +1/+1 until end of turn.",
    setup_interceptors=aunt_may_setup
)

def mary_jane_watson_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Spider enters under your control, scry 1"""
    def spider_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                'Spider' in entering.characteristics.subtypes)

    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_etb_trigger(obj, scry_effect, filter_fn=spider_etb_filter)]

MARY_JANE_WATSON = make_creature(
    name="Mary Jane Watson",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ally"},
    supertypes={"Legendary"},
    text="Whenever a Spider enters under your control, scry 1. {T}: Target Spider you control gains vigilance until end of turn.",
    setup_interceptors=mary_jane_watson_setup
)

def daily_bugle_photographer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - investigate"""
    def investigate_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Clue', 'types': {CardType.ARTIFACT}, 'subtypes': {'Clue'},
                     'abilities': ['{2}, Sacrifice: Draw a card.']},
        }, source=obj.id)]
    return [make_etb_trigger(obj, investigate_effect)]

DAILY_BUGLE_PHOTOGRAPHER = make_creature(
    name="Daily Bugle Photographer",
    power=1,
    toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Daily Bugle Photographer enters, investigate.",
    setup_interceptors=daily_bugle_photographer_setup
)

def nyc_police_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Heroic - create 1/1 Citizen token"""
    def heroic_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Citizen', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Citizen'}},
        }, source=obj.id)]
    return [make_heroic(obj, heroic_effect)]

NYC_POLICE_OFFICER = make_creature(
    name="NYC Police Officer",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. Heroic — Whenever you cast a spell that targets NYC Police Officer, create a 1/1 white Citizen creature token.",
    setup_interceptors=nyc_police_officer_setup
)

def rescue_workers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 3 life. Heroic - gain 2 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]

    def heroic_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]

    return [
        make_etb_trigger(obj, etb_effect),
        make_heroic(obj, heroic_effect)
    ]

RESCUE_WORKERS = make_creature(
    name="Rescue Workers",
    power=1,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ally"},
    text="When Rescue Workers enters, you gain 3 life. Heroic — Whenever you cast a spell that targets Rescue Workers, you gain 2 life.",
    setup_interceptors=rescue_workers_setup
)

WEB_SHIELD = make_instant(
    name="Web Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control gains indestructible until end of turn. If it's a Spider, it also gains hexproof until end of turn."
)

GREAT_RESPONSIBILITY = make_enchantment(
    name="Great Responsibility",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control attacks alone, it gets +2/+2 and gains vigilance until end of turn."
)

WITH_GREAT_POWER = make_sorcery(
    name="With Great Power",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    text="Put two +1/+1 counters on target creature. If it's a Spider, also put a +1/+1 counter on each other Spider you control."
)

SAVE_THE_DAY = make_instant(
    name="Save the Day",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target attacking creature. Its controller gains life equal to its power."
)


# =============================================================================
# BLUE CARDS - SCIENCE & CONTROL
# =============================================================================

def peter_parker_scientist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a noncreature spell, draw then discard"""
    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def loot_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [make_spell_cast_trigger(obj, loot_effect, filter_fn=noncreature_filter)]

PETER_PARKER_SCIENTIST = make_creature(
    name="Peter Parker, Scientist",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, draw a card, then discard a card. {3}{U}: Transform Peter Parker into Spider-Man.",
    setup_interceptors=peter_parker_scientist_setup
)

def dr_octopus_otto_octavius_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain control of target artifact (targeting handled by system)"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Target artifact control change (targeting system handles selection)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

DR_OCTOPUS_OTTO_OCTAVIUS = make_creature(
    name="Dr. Octopus, Otto Octavius",
    power=4,
    toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — When Dr. Octopus enters, gain control of target artifact. Mechanical Arms — You may cast artifact spells as though they had flash.",
    setup_interceptors=dr_octopus_otto_octavius_setup
)

def mysterio_master_of_illusion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create copy token (Illusion), sacrifice at end of turn"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Create token copy of target creature (targeting system handles selection)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

MYSTERIO_MASTER_OF_ILLUSION = make_creature(
    name="Mysterio, Master of Illusion",
    power=2,
    toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — When Mysterio enters, create a token that's a copy of target creature. That token is an Illusion in addition to its other types. Sacrifice the token at end of turn. Hexproof from creatures.",
    setup_interceptors=mysterio_master_of_illusion_setup
)

def the_lizard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - put a +1/+1 counter on The Lizard"""
    from src.cards.interceptor_helpers import make_upkeep_trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

THE_LIZARD = make_creature(
    name="The Lizard",
    power=5,
    toughness=4,
    mana_cost="{3}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Lizard", "Villain"},
    supertypes={"Legendary"},
    text="Trample. Sinister — At the beginning of your upkeep, put a +1/+1 counter on The Lizard. Regenerate — {G}: Regenerate The Lizard.",
    setup_interceptors=the_lizard_setup
)

def madame_web_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - scry 2"""
    from src.cards.interceptor_helpers import make_upkeep_trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

MADAME_WEB = make_creature(
    name="Madame Web",
    power=1,
    toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Psychic"},
    supertypes={"Legendary"},
    text="Spider-Sense — At the beginning of your upkeep, scry 2. {T}: Target Spider you control gains hexproof until end of turn.",
    setup_interceptors=madame_web_setup
)

def oscorp_scientist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - draw then discard (loot)"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

OSCORP_SCIENTIST = make_creature(
    name="Oscorp Scientist",
    power=1,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    text="When Oscorp Scientist enters, draw a card, then discard a card.",
    setup_interceptors=oscorp_scientist_setup
)

SPIDER_SENSE_ALERT = make_instant(
    name="Spider-Sense Alert",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If you control a Spider, scry 2."
)

WEB_SLING = make_instant(
    name="Web Sling",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Web — Tap target creature. It doesn't untap during its controller's next untap step. Draw a card."
)

ILLUSION_DUPLICATE = make_instant(
    name="Illusion Duplicate",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control. Sacrifice it at end of turn."
)

ADVANCED_WEB_FORMULA = make_enchantment(
    name="Advanced Web Formula",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Spiders you control have 'Web — Whenever this creature attacks, tap target creature an opponent controls.'"
)

TECHNOLOGICAL_BREAKTHROUGH = make_sorcery(
    name="Technological Breakthrough",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards. If you control an artifact, draw four cards instead."
)

MIND_CONTROL_DEVICE = make_artifact(
    name="Mind Control Device",
    mana_cost="{4}{U}",
    text="When Mind Control Device enters, gain control of target creature for as long as you control Mind Control Device."
)


# =============================================================================
# BLACK CARDS - VILLAINS & SYMBIOTES
# =============================================================================

def venom_lethal_protector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Symbiote - combat damage to player, they discard"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        return [Event(type=EventType.DISCARD, payload={'player': target, 'amount': 1}, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

VENOM_LETHAL_PROTECTOR = make_creature(
    name="Venom, Lethal Protector",
    power=6,
    toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Symbiote", "Villain"},
    supertypes={"Legendary"},
    text="Menace. Symbiote — Whenever Venom deals combat damage to a player, that player discards a card. You may put a creature card discarded this way onto the battlefield under your control. It's a Symbiote in addition to its other types.",
    setup_interceptors=venom_lethal_protector_setup
)

def carnage_cletus_kasady_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Symbiote - damage to creature destroys it. Creature dies = +1/+0"""
    interceptors = []

    # Damage to creature destroys it
    def creature_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def destroy_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=obj.id)]

    interceptors.append(make_damage_trigger(obj, destroy_effect, filter_fn=creature_damage_filter))

    # Creature dies = +1/+0
    def creature_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        return dying and CardType.CREATURE in dying.characteristics.types

    def boost_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TEMPORARY_EFFECT, payload={
            'object_id': obj.id,
            'effect': 'power_boost',
            'amount': 1,
            'duration': 'end_of_turn'
        }, source=obj.id)]

    interceptors.append(make_death_trigger(obj, boost_effect, filter_fn=creature_dies_filter))
    return interceptors

CARNAGE_CLETUS_KASADY = make_creature(
    name="Carnage, Cletus Kasady",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Symbiote", "Villain"},
    supertypes={"Legendary"},
    text="Haste, menace. Symbiote — Whenever Carnage deals damage to a creature, destroy that creature. Whenever a creature dies, Carnage gets +1/+0 until end of turn.",
    setup_interceptors=carnage_cletus_kasady_setup
)

def green_goblin_norman_osborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - deal 3 damage to any target"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Deal 3 damage to any target (targeting system handles selection)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

GREEN_GOBLIN_NORMAN_OSBORN = make_creature(
    name="Green Goblin, Norman Osborn",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Sinister — When Green Goblin enters, he deals 3 damage to any target. Pumpkin Bombs — {2}{R}: Green Goblin deals 2 damage to each creature you don't control.",
    setup_interceptors=green_goblin_norman_osborn_setup
)

def hobgoblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create two 1/1 red Goblin tokens with haste"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Goblin', 'power': 1, 'toughness': 1, 'colors': {Color.RED},
                         'subtypes': {'Goblin'}, 'keywords': ['haste']},
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Goblin', 'power': 1, 'toughness': 1, 'colors': {Color.RED},
                         'subtypes': {'Goblin'}, 'keywords': ['haste']},
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

HOBGOBLIN = make_creature(
    name="Hobgoblin",
    power=3,
    toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Sinister — When Hobgoblin enters, create two 1/1 red Goblin creature tokens with haste.",
    setup_interceptors=hobgoblin_setup
)

def morbius_the_living_vampire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to creature: +2 counters and destroy"""
    def creature_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [
            Event(type=EventType.COUNTER_ADDED, payload={
                'object_id': obj.id,
                'counter_type': '+1/+1',
                'amount': 2
            }, source=obj.id),
            Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=obj.id)
        ]

    return [make_damage_trigger(obj, damage_effect, combat_only=True, filter_fn=creature_damage_filter)]

MORBIUS_THE_LIVING_VAMPIRE = make_creature(
    name="Morbius, the Living Vampire",
    power=4,
    toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Vampire", "Villain"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Whenever Morbius deals combat damage to a creature, put two +1/+1 counters on Morbius and destroy that creature.",
    setup_interceptors=morbius_the_living_vampire_setup
)

def kingpin_wilson_fisk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - each opponent sacrifices a creature"""
    from src.cards.interceptor_helpers import make_upkeep_trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(type=EventType.SACRIFICE, payload={
                    'player': p_id,
                    'filter': 'creature'
                }, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

KINGPIN_WILSON_FISK = make_creature(
    name="Kingpin, Wilson Fisk",
    power=5,
    toughness=6,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — At the beginning of your upkeep, each opponent sacrifices a creature. Crime Lord — {2}{B}, {T}: Target creature gets -3/-3 until end of turn.",
    setup_interceptors=kingpin_wilson_fisk_setup
)

def symbiote_tendril_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Symbiote - combat damage to player, +1/+1 counter"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

SYMBIOTE_TENDRIL = make_creature(
    name="Symbiote Tendril",
    power=2,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Symbiote"},
    text="Symbiote — Whenever Symbiote Tendril deals combat damage to a player, put a +1/+1 counter on it.",
    setup_interceptors=symbiote_tendril_setup
)

def black_cat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - discard chosen nonland"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        return [Event(type=EventType.DISCARD_CHOICE, payload={
            'player': target,
            'chooser': obj.controller,
            'filter': 'nonland'
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

BLACK_CAT = make_creature(
    name="Black Cat",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Menace. Bad Luck — Whenever Black Cat deals combat damage to a player, that player reveals their hand. You choose a nonland card from it. That player discards that card.",
    setup_interceptors=black_cat_setup
)

def crime_boss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - create two Treasure tokens"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'},
                         'abilities': ['{T}, Sacrifice: Add one mana of any color.']},
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'},
                         'abilities': ['{T}, Sacrifice: Add one mana of any color.']},
            }, source=obj.id)
        ]
    return [make_death_trigger(obj, death_effect)]

CRIME_BOSS = make_creature(
    name="Crime Boss",
    power=3,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Crime Boss dies, create two Treasure tokens.",
    setup_interceptors=crime_boss_setup
)

SINISTER_PLOT = make_sorcery(
    name="Sinister Plot",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. Sinister — If you control a Villain, each opponent also discards a card."
)

SYMBIOTE_BOND = make_enchantment(
    name="Symbiote Bond",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature. Enchanted creature gets +2/+2 and has menace. It's a Symbiote in addition to its other types. When enchanted creature dies, return Symbiote Bond to your hand."
)

WEB_OF_SHADOWS = make_instant(
    name="Web of Shadows",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with power 3 or less. If you control a Symbiote, destroy target creature instead."
)


# =============================================================================
# RED CARDS - ACTION & COMBAT
# =============================================================================

def scarlet_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Heroic - deal 2 damage to any target"""
    def heroic_effect(event: Event, state: GameState) -> list[Event]:
        # Deal 2 damage to any target (targeting system handles selection)
        return []  # Targeting system fills this in
    return [make_heroic(obj, heroic_effect)]

SCARLET_SPIDER = make_creature(
    name="Scarlet Spider",
    power=3,
    toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Heroic — Whenever you cast a spell that targets Scarlet Spider, it deals 2 damage to any target.",
    setup_interceptors=scarlet_spider_setup
)

def electro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - deal 3 damage to each creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o_id, o in state.objects.items():
            if CardType.CREATURE in o.characteristics.types and o.zone == ZoneType.BATTLEFIELD:
                events.append(Event(type=EventType.DAMAGE, payload={
                    'target': o_id,
                    'amount': 3,
                    'source': obj.id,
                    'is_combat': False
                }, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]

ELECTRO = make_creature(
    name="Electro",
    power=4,
    toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — When Electro enters, he deals 3 damage to each creature. Electric Surge — {R}: Electro gets +1/+0 until end of turn.",
    setup_interceptors=electro_setup
)

def shocker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - deal 2 damage to any target"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Deal 2 damage to any target (targeting system handles selection)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

SHOCKER = make_creature(
    name="Shocker",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — When Shocker enters, he deals 2 damage to any target. Shock Wave — {1}{R}: Shocker deals 1 damage to each creature.",
    setup_interceptors=shocker_setup
)

def sandman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Prevent destruction by damage (replacement effect)"""
    def damage_destroy_filter(event: Event, state: GameState) -> bool:
        # This would intercept DESTROY events caused by damage
        if event.type != EventType.DESTROY:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return event.payload.get('cause') == 'damage'

    def prevent_destroy(event: Event, state: GameState) -> InterceptorResult:
        # Replace with nothing (prevent the destruction)
        return InterceptorResult(action=InterceptorAction.CANCEL)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REPLACE,
        filter=damage_destroy_filter,
        handler=prevent_destroy,
        duration='while_on_battlefield'
    )]

SANDMAN = make_creature(
    name="Sandman",
    power=5,
    toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Elemental", "Villain"},
    supertypes={"Legendary"},
    text="Trample. Sinister — Sandman can't be destroyed by damage. Reform — At the beginning of your upkeep, if Sandman is in your graveyard, you may pay {2}{R}. If you do, return it to the battlefield.",
    setup_interceptors=sandman_setup
)

def rhino_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - +2/+0 until end of turn"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TEMPORARY_EFFECT, payload={
            'object_id': obj.id,
            'effect': 'power_boost',
            'amount': 2,
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

RHINO = make_creature(
    name="Rhino",
    power=6,
    toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Trample, haste. Sinister — Rhino must attack each combat if able. Charge — Whenever Rhino attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=rhino_setup
)

def scorpion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beginning of combat - deal 1 damage to target opponent creature"""
    def combat_start_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'combat':
            return False
        return state.active_player == obj.controller

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        # Deal 1 damage to target creature opponent controls (targeting system)
        return []  # Targeting system fills this in

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_start_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]

SCORPION = make_creature(
    name="Scorpion",
    power=4,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="First strike. Sinister — At the beginning of combat on your turn, Scorpion deals 1 damage to target creature an opponent controls.",
    setup_interceptors=scorpion_setup
)

WEB_STRIKE = make_instant(
    name="Web Strike",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains first strike until end of turn. If it's a Spider, it also gains trample until end of turn."
)

PUMPKIN_BOMB = make_instant(
    name="Pumpkin Bomb",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Pumpkin Bomb deals 3 damage to any target. If you control a Villain, it deals 4 damage instead."
)

GOBLIN_GLIDER_ASSAULT = make_sorcery(
    name="Goblin Glider Assault",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Create two 2/2 red Goblin creature tokens with flying and haste."
)

ELECTRIC_DISCHARGE = make_instant(
    name="Electric Discharge",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Electric Discharge deals 2 damage to any target. If you control a Villain, Electric Discharge deals 3 damage instead."
)

SINISTER_RAGE = make_enchantment(
    name="Sinister Rage",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Villains you control get +1/+0 and have haste."
)

BUILDING_COLLAPSE = make_sorcery(
    name="Building Collapse",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Building Collapse deals 4 damage to each creature. If you control a Spider, it deals 4 damage to each creature you don't control instead."
)


# =============================================================================
# GREEN CARDS - STRENGTH & NATURE
# =============================================================================

def spider_hulk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - four +1/+1 counters. Takes damage - +1/+1 counter"""
    interceptors = []

    # ETB with counters
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 4
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Takes damage trigger
    def takes_damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == obj.id

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=takes_damage_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=damage_effect(e, s)),
        duration='while_on_battlefield'
    ))
    return interceptors

SPIDER_HULK = make_creature(
    name="Spider-Hulk",
    power=7,
    toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Spider-Hulk enters with four +1/+1 counters on it. Whenever Spider-Hulk takes damage, put a +1/+1 counter on it.",
    setup_interceptors=spider_hulk_setup
)

def spider_pig_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - other Spiders get +1/+1 until end of turn"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o_id, o in state.objects.items():
            if (o_id != obj.id and
                o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                'Spider' in o.characteristics.subtypes and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(type=EventType.TEMPORARY_EFFECT, payload={
                    'object_id': o_id,
                    'effect': 'pt_boost',
                    'power': 1,
                    'toughness': 1,
                    'duration': 'end_of_turn'
                }, source=obj.id))
        return events
    return [make_attack_trigger(obj, attack_effect)]

SPIDER_PIG = make_creature(
    name="Spider-Pig (Peter Porker)",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Pig", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Whenever Spider-Pig attacks, other Spiders you control get +1/+1 until end of turn.",
    setup_interceptors=spider_pig_setup
)

def kraven_the_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to creature - destroy that creature"""
    def creature_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def destroy_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=obj.id)]

    return [make_damage_trigger(obj, destroy_effect, combat_only=True, filter_fn=creature_damage_filter)]

KRAVEN_THE_HUNTER = make_creature(
    name="Kraven the Hunter",
    power=5,
    toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — Kraven has hexproof from creatures with power less than his. Hunt — Whenever Kraven deals combat damage to a creature, destroy that creature.",
    setup_interceptors=kraven_the_hunter_setup
)

def vermin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step - create Rat token. Rats get +1/+0"""
    from src.cards.interceptor_helpers import make_end_step_trigger
    interceptors = []

    # End step trigger
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Rat', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Rat'}},
        }, source=obj.id)]
    interceptors.append(make_end_step_trigger(obj, end_step_effect))

    # Rats get +1/+0
    def rat_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Rat' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    interceptors.extend(make_static_pt_boost(obj, 1, 0, rat_filter))

    return interceptors

VERMIN = make_creature(
    name="Vermin",
    power=4,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Rat", "Villain"},
    supertypes={"Legendary"},
    text="Trample. Sinister — At the beginning of your end step, create a 1/1 black Rat creature token. Rats you control get +1/+0.",
    setup_interceptors=vermin_setup
)

def spider_colony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create two 1/1 Spider tokens with reach"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN},
                         'subtypes': {'Spider'}, 'keywords': ['reach']},
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN},
                         'subtypes': {'Spider'}, 'keywords': ['reach']},
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

SPIDER_COLONY = make_creature(
    name="Spider Colony",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="When Spider Colony enters, create two 1/1 green Spider creature tokens with reach.",
    setup_interceptors=spider_colony_setup
)

def forest_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - create 1/1 Spider token with reach"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN},
                     'subtypes': {'Spider'}, 'keywords': ['reach']},
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

FOREST_SPIDER = make_creature(
    name="Forest Spider",
    power=2,
    toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach. When Forest Spider dies, create a 1/1 green Spider creature token with reach.",
    setup_interceptors=forest_spider_setup
)

VENOMOUS_BITE = make_instant(
    name="Venomous Bite",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature you don't control. If your creature is a Spider, it gains deathtouch until end of turn."
)

SPIDER_SWARM = make_sorcery(
    name="Spider Swarm",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create X 1/1 green Spider creature tokens with reach, where X is the number of creatures you control."
)

WEB_TRAP = make_enchantment(
    name="Web Trap",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Web — Whenever a creature an opponent controls attacks, tap it. It doesn't untap during its controller's next untap step."
)

PRIMAL_INSTINCT = make_instant(
    name="Primal Instinct",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. If it's a Spider, it also gains trample until end of turn."
)

JUNGLE_AMBUSH = make_instant(
    name="Jungle Ambush",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control. If your creature is a Villain, it gets +2/+2 until end of turn first."
)

NATURES_WRATH = make_sorcery(
    name="Nature's Wrath",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="Destroy all artifacts and enchantments. You gain 2 life for each permanent destroyed this way."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def spider_verse_team_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Web ETB (tap all opponent creatures). Other Spiders get +2/+2"""
    interceptors = []

    # Web ETB - tap all opponent creatures
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o_id, o in state.objects.items():
            if (o.controller != obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(type=EventType.TAP, payload={
                    'object_id': o_id,
                    'freeze': True  # Doesn't untap next untap step
                }, source=obj.id))
        return events
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Other Spiders get +2/+2
    interceptors.extend(make_static_pt_boost(obj, 2, 2, other_creatures_with_subtype(obj, 'Spider')))

    return interceptors

SPIDER_VERSE_TEAM = make_creature(
    name="Spider-Verse Team",
    power=5,
    toughness=5,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flying, vigilance, trample. Web — When Spider-Verse Team enters, tap all creatures your opponents control. They don't untap during their controllers' next untap steps. Other Spiders you control get +2/+2.",
    setup_interceptors=spider_verse_team_setup
)

def sinister_six_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - modal choices based on Villains controlled"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Count villains and create modal event
        villain_count = sum(1 for o in state.objects.values()
                          if o.controller == obj.controller and
                          CardType.CREATURE in o.characteristics.types and
                          'Villain' in o.characteristics.subtypes and
                          o.zone == ZoneType.BATTLEFIELD)
        return [Event(type=EventType.MODAL_CHOICE, payload={
            'controller': obj.controller,
            'choices': villain_count,
            'modes': ['draw', 'discard', 'damage', 'destroy']
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SINISTER_SIX = make_creature(
    name="Sinister Six",
    power=6,
    toughness=6,
    mana_cost="{2}{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — When Sinister Six enters, choose one for each Villain you control: Draw a card; target opponent discards a card; deal 2 damage to any target; destroy target creature with power 3 or less.",
    setup_interceptors=sinister_six_setup
)

def anti_venom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Symbiote - combat damage to creature, exile it"""
    def creature_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def exile_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [Event(type=EventType.ZONE_CHANGE, payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.EXILE
        }, source=obj.id)]

    return [make_damage_trigger(obj, exile_effect, combat_only=True, filter_fn=creature_damage_filter)]

ANTI_VENOM = make_creature(
    name="Anti-Venom",
    power=5,
    toughness=5,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Symbiote", "Hero"},
    supertypes={"Legendary"},
    text="Lifelink. Symbiote — Whenever Anti-Venom deals combat damage to a creature, exile that creature. Cure — {W}: Remove all counters from target creature.",
    setup_interceptors=anti_venom_setup
)

def silk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Web on attack - create Spider token. Spider-Sense - opponent casts on your turn, draw"""
    interceptors = []

    # Attack trigger - create Spider token
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE},
                     'subtypes': {'Spider'}, 'keywords': ['reach']},
        }, source=obj.id)]
    interceptors.append(make_attack_trigger(obj, attack_effect))

    # Spider-Sense - opponent casts during your turn
    def opponent_cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') == source.controller:
            return False
        return state.active_player == source.controller

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    interceptors.append(make_spell_cast_trigger(obj, draw_effect, controller_only=False, filter_fn=opponent_cast_filter))

    return interceptors

SILK = make_creature(
    name="Silk",
    power=3,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flash. Web — Whenever Silk attacks, create a 1/1 white Spider creature token with reach. Spider-Sense — Whenever an opponent casts a spell during your turn, draw a card.",
    setup_interceptors=silk_setup
)

def prowler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - bounce creature MV 3 or less. Combat damage - destroy artifact"""
    interceptors = []

    # ETB bounce
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Target creature with MV 3 or less (targeting system)
        return []  # Targeting system fills this in
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Combat damage - destroy artifact
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # Target artifact that player controls (targeting system)
        return []  # Targeting system fills this in
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))

    return interceptors

PROWLER = make_creature(
    name="Prowler",
    power=3,
    toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flash. Menace. When Prowler enters, you may return target creature with mana value 3 or less to its owner's hand. Sabotage — Whenever Prowler deals combat damage to a player, destroy target artifact that player controls.",
    setup_interceptors=prowler_setup
)

def toxin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Symbiote - combat damage to creature +1/+1. Death - create 2/2 Symbiote"""
    interceptors = []

    # Combat damage to creature
    def creature_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]
    interceptors.append(make_damage_trigger(obj, counter_effect, combat_only=True, filter_fn=creature_damage_filter))

    # Death trigger
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Symbiote', 'power': 2, 'toughness': 2, 'colors': {Color.BLACK}, 'subtypes': {'Symbiote'}},
        }, source=obj.id)]
    interceptors.append(make_death_trigger(obj, death_effect))

    return interceptors

TOXIN = make_creature(
    name="Toxin",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Symbiote", "Hero"},
    supertypes={"Legendary"},
    text="Trample, lifelink. Symbiote — Whenever Toxin deals combat damage to a creature, put a +1/+1 counter on Toxin. When Toxin dies, create a 2/2 black Symbiote creature token.",
    setup_interceptors=toxin_setup
)

def agent_venom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Symbiote - attack creates 1/1 Symbiote token with menace"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Symbiote', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK},
                     'subtypes': {'Symbiote'}, 'keywords': ['menace']},
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

AGENT_VENOM = make_creature(
    name="Agent Venom",
    power=4,
    toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Symbiote", "Soldier", "Hero"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Symbiote — Whenever Agent Venom attacks, create a 1/1 black Symbiote creature token with menace. {2}: Target Symbiote you control gains indestructible until end of turn.",
    setup_interceptors=agent_venom_setup
)

def dr_strange_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - counter unless pay 4. Instant/sorcery cast - create Spider token"""
    interceptors = []

    # ETB counter
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Counter target spell unless pay 4 (targeting system)
        return []  # Targeting system fills this in
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Instant/sorcery trigger
    def instant_sorcery_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.INSTANT in spell_types or CardType.SORCERY in spell_types

    def token_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Spider'}},
        }, source=obj.id)]

    interceptors.append(make_spell_cast_trigger(obj, token_effect, filter_fn=instant_sorcery_filter))

    return interceptors

DR_STRANGE_SPIDER = make_creature(
    name="Spider-Man, Sorcerer Supreme",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Spider", "Wizard", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Web — When Spider-Man, Sorcerer Supreme enters, counter target spell unless its controller pays {4}. Whenever you cast an instant or sorcery spell, create a 1/1 white Spider creature token.",
    setup_interceptors=dr_strange_spider_setup
)


# =============================================================================
# ARTIFACTS
# =============================================================================

WEB_SHOOTERS = make_artifact(
    name="Web Shooters",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1 and has 'Web — Whenever this creature attacks, tap target creature an opponent controls.' Equip {2}"
)

def spider_tracer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - attach to creature, upkeep reveal top card"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Attach to target creature (targeting system)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

SPIDER_TRACER = make_artifact(
    name="Spider-Tracer",
    mana_cost="{1}",
    text="When Spider-Tracer enters, attach it to target creature. That creature's controller reveals the top card of their library at the beginning of their upkeep.",
    setup_interceptors=spider_tracer_setup
)

OSCORP_TECH = make_artifact(
    name="Oscorp Tech",
    mana_cost="{3}",
    text="{T}: Add {C}{C}. {2}, {T}: Draw a card. Activate only if you control a Scientist."
)

GOBLIN_GLIDER = make_artifact(
    name="Goblin Glider",
    mana_cost="{3}",
    subtypes={"Equipment", "Vehicle"},
    text="Equipped creature gets +2/+1 and has flying. Whenever equipped creature deals combat damage to a player, you may have it deal 1 damage to another target creature. Crew 1. Equip {2}"
)

IRON_SPIDER_SUIT = make_artifact(
    name="Iron Spider Suit",
    mana_cost="{4}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +3/+3 and has flying and hexproof. Equipped creature is a Spider in addition to its other types. Equip Spider {2}. Equip {4}"
)

SYMBIOTE_SAMPLE = make_artifact(
    name="Symbiote Sample",
    mana_cost="{2}",
    text="{2}, {T}, Sacrifice Symbiote Sample: Target creature gets +2/+2 and becomes a Symbiote in addition to its other types until end of turn. It gains menace until end of turn."
)

DAILY_BUGLE_PRESS = make_artifact(
    name="Daily Bugle Press",
    mana_cost="{3}",
    text="{T}: Add {U}. {2}, {T}: Investigate."
)

STARK_TECH_UPGRADE = make_artifact(
    name="Stark Tech Upgrade",
    mana_cost="{3}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+2 and has 'Whenever this creature deals combat damage to a player, draw a card.' Equip {3}"
)


# =============================================================================
# LANDS
# =============================================================================

NEW_YORK_CITY = make_land(
    name="New York City",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add one mana of any color. Activate only if you control a Spider or a Villain."
)

DAILY_BUGLE_BUILDING = make_land(
    name="Daily Bugle Building",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a Human."
)

OSCORP_TOWER = make_land(
    name="Oscorp Tower",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {U} or {B}. Activate only if you control an artifact or a Scientist."
)

FISK_TOWER = make_land(
    name="Fisk Tower",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {B}. {4}{B}, {T}: Target creature gets -2/-2 until end of turn."
)

HELL_KITCHEN = make_land(
    name="Hell's Kitchen",
    text="Hell's Kitchen enters tapped. {T}: Add {B} or {R}."
)

BROOKLYN_BRIDGE = make_land(
    name="Brooklyn Bridge",
    text="Brooklyn Bridge enters tapped. {T}: Add {W} or {U}. {2}, {T}: Target creature gains flying until end of turn."
)

QUEENS_NEIGHBORHOOD = make_land(
    name="Queens Neighborhood",
    text="Queens Neighborhood enters tapped. {T}: Add {W} or {G}. When Queens Neighborhood enters, you gain 1 life."
)

STARK_TOWER = make_land(
    name="Stark Tower",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {U} or {R}. Activate only if you control an Equipment."
)

SYMBIOTE_PLANET = make_land(
    name="Symbiote Planet",
    text="Symbiote Planet enters tapped. {T}: Add {B} or {G}. {3}, {T}: Create a 1/1 black Symbiote creature token."
)


# =============================================================================
# BASIC LANDS
# =============================================================================

PLAINS_SPM = make_land(
    name="Plains",
    subtypes={"Plains"},
    supertypes={"Basic"},
    text="({T}: Add {W}.)"
)

ISLAND_SPM = make_land(
    name="Island",
    subtypes={"Island"},
    supertypes={"Basic"},
    text="({T}: Add {U}.)"
)

SWAMP_SPM = make_land(
    name="Swamp",
    subtypes={"Swamp"},
    supertypes={"Basic"},
    text="({T}: Add {B}.)"
)

MOUNTAIN_SPM = make_land(
    name="Mountain",
    subtypes={"Mountain"},
    supertypes={"Basic"},
    text="({T}: Add {R}.)"
)

FOREST_SPM = make_land(
    name="Forest",
    subtypes={"Forest"},
    supertypes={"Basic"},
    text="({T}: Add {G}.)"
)


# =============================================================================
# MORE CARDS TO REACH 198
# =============================================================================

def spider_noir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - target creature can't block"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Target creature can't block (targeting system)
        return []  # Targeting system fills this in
    return [make_attack_trigger(obj, attack_effect)]

SPIDER_NOIR = make_creature(
    name="Spider-Noir",
    power=3,
    toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Spider-Noir attacks, target creature can't block this turn.",
    setup_interceptors=spider_noir_setup
)

def mayday_parker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Heroic - +2/+0 until end of turn"""
    def heroic_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TEMPORARY_EFFECT, payload={
            'object_id': obj.id,
            'effect': 'power_boost',
            'amount': 2,
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_heroic(obj, heroic_effect)]

MAYDAY_PARKER = make_creature(
    name="Mayday Parker",
    power=3,
    toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="First strike, haste. Heroic — Whenever you cast a spell that targets Mayday Parker, she gets +2/+0 until end of turn.",
    setup_interceptors=mayday_parker_setup
)

def spider_2099_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to creature - destroy that creature"""
    def creature_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def destroy_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=obj.id)]

    return [make_damage_trigger(obj, destroy_effect, combat_only=True, filter_fn=creature_damage_filter)]

SPIDER_2099 = make_creature(
    name="Spider-Man 2099",
    power=4,
    toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Talons — Whenever Spider-Man 2099 deals combat damage to a creature, destroy that creature. Accelerated Vision — {U}: Scry 1.",
    setup_interceptors=spider_2099_setup
)

def spider_uk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Web on attack - bounce target nonland permanent"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Target nonland permanent bounce (targeting system)
        return []  # Targeting system fills this in
    return [make_attack_trigger(obj, attack_effect)]

SPIDER_UK = make_creature(
    name="Spider-UK",
    power=3,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Vigilance. Web — Whenever Spider-UK attacks, return target nonland permanent to its owner's hand.",
    setup_interceptors=spider_uk_setup
)

def peni_parker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create SP//dr Vehicle token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'SP//dr', 'types': {CardType.ARTIFACT}, 'subtypes': {'Vehicle'},
                     'abilities': ['Crew 2', 'This Vehicle gets +1/+1 for each Spider you control.']},
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

PENI_PARKER = make_creature(
    name="Peni Parker",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    text="Peni Parker crews Vehicles as though her power were 4. When Peni Parker enters, create a colorless Vehicle artifact token named SP//dr with 'Crew 2' and 'This Vehicle gets +1/+1 for each Spider you control.'",
    setup_interceptors=peni_parker_setup
)

def superior_spider_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - look at top 3, take 1, rest to graveyard"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LOOK_TOP_CARDS, payload={
            'player': obj.controller,
            'amount': 3,
            'choose': 1,
            'destination': 'hand',
            'rest_destination': 'graveyard'
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

SUPERIOR_SPIDER_MAN = make_creature(
    name="Superior Spider-Man",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Spider", "Villain"},
    supertypes={"Legendary"},
    text="Menace. Superior Tactics — Whenever Superior Spider-Man deals combat damage to a player, look at the top three cards of your library. Put one into your hand and the rest into your graveyard.",
    setup_interceptors=superior_spider_man_setup
)

def spider_punk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - creatures you control get +1/+0"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o_id, o in state.objects.items():
            if (o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(type=EventType.TEMPORARY_EFFECT, payload={
                    'object_id': o_id,
                    'effect': 'power_boost',
                    'amount': 1,
                    'duration': 'end_of_turn'
                }, source=obj.id))
        return events
    return [make_attack_trigger(obj, attack_effect)]

SPIDER_PUNK = make_creature(
    name="Spider-Punk",
    power=3,
    toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="Haste. Rebellion — Whenever Spider-Punk attacks, creatures you control get +1/+0 until end of turn. {R}: Spider-Punk gains first strike until end of turn.",
    setup_interceptors=spider_punk_setup
)

SPIDER_HAM_ATTACK = make_instant(
    name="Spider-Ham Attack",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Target Spider gets +3/+3 and gains trample until end of turn. Create a Food token."
)

MULTIVERSE_PORTAL = make_sorcery(
    name="Multiverse Portal",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Search your library for a Spider card, reveal it, and put it into your hand. Then shuffle. Draw a card."
)

DIMENSION_HOPPING = make_instant(
    name="Dimension Hopping",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Exile target creature you control, then return it to the battlefield under its owner's control. If it's a Spider, draw a card."
)

SYMBIOTE_INVASION = make_sorcery(
    name="Symbiote Invasion",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Create three 2/2 black Symbiote creature tokens with menace."
)

ELECTRO_SHOCK = make_instant(
    name="Electro Shock",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Electro Shock deals 3 damage to each creature. Creatures dealt damage this way can't attack during their controller's next turn."
)

def hunters_trap_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - exile creature power 4 or less until this leaves"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Exile target creature opponent controls with power 4 or less (targeting system)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

HUNTERS_TRAP = make_enchantment(
    name="Hunter's Trap",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When Hunter's Trap enters, exile target creature an opponent controls with power 4 or less until Hunter's Trap leaves the battlefield.",
    setup_interceptors=hunters_trap_setup
)

SPIDER_ARMY = make_sorcery(
    name="Spider Army",
    mana_cost="{4}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Create five 1/1 green Spider creature tokens with reach. Spiders you control get +1/+1 until end of turn."
)

def j_jonah_jameson_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - opponents may let you draw or you get Treasure"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # This requires opponent choice - simplified to create Treasure if no draw
        return [Event(type=EventType.MODAL_CHOICE, payload={
            'controller': obj.controller,
            'modes': ['opponent_draw', 'treasure'],
            'chooser': 'opponent'
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

J_JONAH_JAMESON = make_creature(
    name="J. Jonah Jameson",
    power=1,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, each opponent may have you draw a card. If no opponents do, create a Treasure token.",
    setup_interceptors=j_jonah_jameson_setup
)

def gwen_stacy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Spider attacks, Gwen gets +1/+1 until end of turn"""
    def spider_attacks_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == source.controller and
                'Spider' in attacker.characteristics.subtypes)

    def boost_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TEMPORARY_EFFECT, payload={
            'object_id': obj.id,
            'effect': 'pt_boost',
            'power': 1,
            'toughness': 1,
            'duration': 'end_of_turn'
        }, source=obj.id)]

    return [make_attack_trigger(obj, boost_effect, filter_fn=spider_attacks_filter)]

GWEN_STACY = make_creature(
    name="Gwen Stacy",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ally"},
    supertypes={"Legendary"},
    text="Whenever a Spider you control attacks, Gwen Stacy gets +1/+1 until end of turn. {T}: Target Spider you control gains lifelink until end of turn.",
    setup_interceptors=gwen_stacy_setup
)

def harry_osborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - modal: draw and lose 1 life, or +1/+1 counter"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MODAL_CHOICE, payload={
            'controller': obj.controller,
            'modes': ['draw_lose_life', 'counter'],
            'object_id': obj.id
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

HARRY_OSBORN = make_creature(
    name="Harry Osborn",
    power=2,
    toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, choose one: Draw a card and lose 1 life; or put a +1/+1 counter on Harry Osborn.",
    setup_interceptors=harry_osborn_setup
)

def felicia_hardy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - create Treasure"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'},
                     'abilities': ['{T}, Sacrifice: Add one mana of any color.']},
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

FELICIA_HARDY = make_creature(
    name="Felicia Hardy",
    power=2,
    toughness=1,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Skulk. Whenever Felicia Hardy deals combat damage to a player, create a Treasure token.",
    setup_interceptors=felicia_hardy_setup
)

def vulture_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - exile top card, may play it"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        return [Event(type=EventType.EXILE_TOP_CARD, payload={
            'player': target,
            'may_play': True,
            'until': 'end_of_turn',
            'caster': obj.controller
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

VULTURE = make_creature(
    name="Vulture",
    power=4,
    toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Sinister — Whenever Vulture deals combat damage to a player, exile the top card of that player's library. You may play that card this turn.",
    setup_interceptors=vulture_setup
)

HYDRO_MAN = make_creature(
    name="Hydro-Man",
    power=4,
    toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Elemental", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — Hydro-Man can't be blocked. Water Form — {U}: Hydro-Man gets +1/-1 or -1/+1 until end of turn."
)

CHAMELEON = make_creature(
    name="Chameleon",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Shapeshifter", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — {2}: Chameleon becomes a copy of target creature until end of turn."
)

def beetle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create two Thopter tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Thopter', 'power': 1, 'toughness': 1, 'types': {CardType.ARTIFACT, CardType.CREATURE},
                         'subtypes': {'Thopter'}, 'keywords': ['flying']},
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Thopter', 'power': 1, 'toughness': 1, 'types': {CardType.ARTIFACT, CardType.CREATURE},
                         'subtypes': {'Thopter'}, 'keywords': ['flying']},
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

BEETLE = make_creature(
    name="Beetle",
    power=3,
    toughness=4,
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Sinister — When Beetle enters, create two 1/1 colorless Thopter artifact creature tokens with flying.",
    setup_interceptors=beetle_setup
)

def hammerhead_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - destroy target artifact/creature MV 2 or less"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Target artifact/creature MV 2 or less (targeting system)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

HAMMERHEAD = make_creature(
    name="Hammerhead",
    power=4,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Menace. Sinister — When Hammerhead enters, destroy target artifact or creature with mana value 2 or less.",
    setup_interceptors=hammerhead_setup
)

def tombstone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static - +1/+1 for each creature card in your graveyard"""
    def count_creatures_in_graveyard(state: GameState) -> int:
        count = 0
        for o in state.objects.values():
            if (o.owner == obj.controller and
                o.zone == ZoneType.GRAVEYARD and
                CardType.CREATURE in o.characteristics.types):
                count += 1
        return count

    # Dynamic P/T boost based on graveyard count
    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        bonus = count_creatures_in_graveyard(state)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        return event.payload.get('object_id') == obj.id

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        bonus = count_creatures_in_graveyard(state)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + bonus
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

TOMBSTONE = make_creature(
    name="Tombstone",
    power=5,
    toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Indestructible. Sinister — Tombstone gets +1/+1 for each creature card in your graveyard.",
    setup_interceptors=tombstone_setup
)

def silver_sable_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - create Soldier token"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Soldier', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Soldier'}},
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

SILVER_SABLE = make_creature(
    name="Silver Sable",
    power=3,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="First strike. Whenever Silver Sable deals combat damage to a player, create a 1/1 white Soldier creature token.",
    setup_interceptors=silver_sable_setup
)


# =============================================================================
# ADDITIONAL CARDS
# =============================================================================

SPECTACULAR_SWING = make_instant(
    name="Spectacular Swing",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 and gains flying until end of turn."
)

def neighborhood_watch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create Citizen token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Citizen', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Citizen'}},
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

NEIGHBORHOOD_WATCH = make_creature(
    name="Neighborhood Watch",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="Vigilance. When Neighborhood Watch enters, create a 1/1 white Citizen creature token.",
    setup_interceptors=neighborhood_watch_setup
)

def uncle_ben_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - target Spider +2/+2, draw a card"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
            # Target Spider effect handled by targeting system
        ]
    return [make_death_trigger(obj, death_effect)]

UNCLE_BEN = make_creature(
    name="Uncle Ben",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="When Uncle Ben dies, target Spider you control gets +2/+2 and gains vigilance until end of turn. Draw a card.",
    setup_interceptors=uncle_ben_setup
)

SPIDER_SENSE = make_instant(
    name="Spider-Sense",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 2. Draw a card if you control a Spider."
)

def oscorp_lab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - scry 1"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

OSCORP_LAB = make_enchantment(
    name="Oscorp Lab",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1. {3}{U}: Draw a card.",
    setup_interceptors=oscorp_lab_setup
)

EXPERIMENT_GONE_WRONG = make_sorcery(
    name="Experiment Gone Wrong",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If it was a Villain, its controller discards a card."
)

HOLOGRAM_DECOY = make_instant(
    name="Hologram Decoy",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control except it's an Illusion. Sacrifice it at end of turn."
)

GENETIC_MUTATION = make_enchantment(
    name="Genetic Mutation",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Enchanted creature gets +3/+3 and has trample. When enchanted creature dies, create a 3/3 green Mutant creature token."
)

SYMBIOTE_SURGE = make_instant(
    name="Symbiote Surge",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets +2/+0 and gains menace until end of turn. If it's a Symbiote, it also gains lifelink."
)

def underworld_connections_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - may pay 1 life to draw"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MAY_PAY_LIFE, payload={
            'player': obj.controller,
            'amount': 1,
            'effect_if_do': {'type': 'draw', 'amount': 1}
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

UNDERWORLD_CONNECTIONS = make_enchantment(
    name="Underworld Connections",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, you may pay 1 life. If you do, draw a card.",
    setup_interceptors=underworld_connections_setup
)

def hired_muscle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - create Treasure"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'},
                     'abilities': ['{T}, Sacrifice: Add one mana of any color.']},
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

HIRED_MUSCLE = make_creature(
    name="Hired Muscle",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Menace. When Hired Muscle dies, create a Treasure token.",
    setup_interceptors=hired_muscle_setup
)

SHOCK_THERAPY = make_instant(
    name="Shock Therapy",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock Therapy deals 2 damage to any target."
)

EXPLOSIVE_RAMPAGE = make_sorcery(
    name="Explosive Rampage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Explosive Rampage deals 4 damage to each creature without flying."
)

GOBLIN_ARMY = make_sorcery(
    name="Goblin Army",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Create two 1/1 red Goblin creature tokens with haste."
)

FIRE_PUNCH = make_instant(
    name="Fire Punch",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn."
)

RADIOACTIVE_BITE = make_instant(
    name="Radioactive Bite",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +1/+1 until end of turn. If it's a Spider, put a +1/+1 counter on it instead."
)

def predator_instinct_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Grant trample to creatures with power 4+"""
    def power_4_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD and
                target.characteristics.power >= 4)
    return [make_keyword_grant(obj, ['trample'], power_4_filter)]

PREDATOR_INSTINCT = make_enchantment(
    name="Predator Instinct",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Creatures you control with power 4 or greater have trample.",
    setup_interceptors=predator_instinct_setup
)

def giant_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create Spider token with reach"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN},
                     'subtypes': {'Spider'}, 'keywords': ['reach']},
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

GIANT_SPIDER = make_creature(
    name="Giant Spider",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach. When Giant Spider enters, create a 1/1 green Spider creature token with reach.",
    setup_interceptors=giant_spider_setup
)

def savage_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - draw a card"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

SAVAGE_HUNTER = make_creature(
    name="Savage Hunter",
    power=4,
    toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    text="Trample. Whenever Savage Hunter deals combat damage to a player, draw a card.",
    setup_interceptors=savage_hunter_setup
)

WEB_COCOON = make_enchantment(
    name="Web Cocoon",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Enchant creature. Enchanted creature can't attack or block. When enchanted creature leaves the battlefield, draw a card."
)

def spider_queen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Spiders +1/+1. Upkeep - create Spider token"""
    interceptors = []

    # Other Spiders get +1/+1
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, 'Spider')))

    # Upkeep trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN},
                     'subtypes': {'Spider'}, 'keywords': ['reach']},
        }, source=obj.id)]
    interceptors.append(make_upkeep_trigger(obj, upkeep_effect))

    return interceptors

SPIDER_QUEEN = make_creature(
    name="Spider Queen",
    power=5,
    toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    supertypes={"Legendary"},
    text="Reach. Other Spiders you control get +1/+1. At the beginning of your upkeep, create a 1/1 green Spider creature token with reach.",
    setup_interceptors=spider_queen_setup
)

def scream_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - deal 1 damage to each opponent"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(type=EventType.DAMAGE, payload={
                    'target': p_id,
                    'amount': 1,
                    'source': obj.id,
                    'is_combat': False
                }, source=obj.id))
        return events
    return [make_attack_trigger(obj, attack_effect)]

SCREAM = make_creature(
    name="Scream",
    power=4,
    toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Symbiote"},
    supertypes={"Legendary"},
    text="Haste. Symbiote — Whenever Scream attacks, it deals 1 damage to each opponent. Hair Tendrils — {R}: Scream gets +1/+0 until end of turn.",
    setup_interceptors=scream_setup
)

def riot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - may sacrifice creature for +2 counters"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MAY_SACRIFICE, payload={
            'controller': obj.controller,
            'filter': 'creature',
            'effect_if_do': {'type': 'counter', 'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2}
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

RIOT = make_creature(
    name="Riot",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Symbiote"},
    supertypes={"Legendary"},
    text="Trample. Symbiote — Whenever Riot deals combat damage to a player, you may sacrifice another creature. If you do, put two +1/+1 counters on Riot.",
    setup_interceptors=riot_setup
)

def phage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to creature - destroy and gain life equal to toughness"""
    def creature_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def destroy_and_lifegain(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        toughness = target.characteristics.toughness if target else 0
        return [
            Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': toughness}, source=obj.id)
        ]

    return [make_damage_trigger(obj, destroy_and_lifegain, combat_only=True, filter_fn=creature_damage_filter)]

PHAGE = make_creature(
    name="Phage",
    power=3,
    toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Symbiote"},
    supertypes={"Legendary"},
    text="Deathtouch. Symbiote — Whenever Phage deals combat damage to a creature, destroy that creature. You gain life equal to its toughness.",
    setup_interceptors=phage_setup
)

def lasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step - if creature died this turn, +1/+1 counter"""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Check if creature died this turn (simplified - checks turn_creatures_died flag)
        if state.turn_state.get('creature_died_this_turn', False):
            return [Event(type=EventType.COUNTER_ADDED, payload={
                'object_id': obj.id,
                'counter_type': '+1/+1',
                'amount': 1
            }, source=obj.id)]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]

LASHER = make_creature(
    name="Lasher",
    power=3,
    toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Symbiote"},
    supertypes={"Legendary"},
    text="Reach. Symbiote — At the beginning of your end step, if a creature died this turn, put a +1/+1 counter on Lasher.",
    setup_interceptors=lasher_setup
)

def agony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - they discard"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        return [Event(type=EventType.DISCARD, payload={'player': target, 'amount': 1}, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

AGONY = make_creature(
    name="Agony",
    power=3,
    toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Symbiote"},
    supertypes={"Legendary"},
    text="Lifelink. Symbiote — Whenever Agony deals combat damage to a player, that player discards a card.",
    setup_interceptors=agony_setup
)

def web_warriors_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create Spider token with reach"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE},
                     'subtypes': {'Spider'}, 'keywords': ['reach']},
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

WEB_WARRIORS = make_creature(
    name="Web Warriors",
    power=3,
    toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Spider", "Hero"},
    text="Flying. When Web Warriors enters, create a 1/1 white Spider creature token with reach.",
    setup_interceptors=web_warriors_setup
)

def spider_slayers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - +2/+2 if defending player has Spider"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        defender = event.payload.get('defending_player')
        # Check if defender controls a Spider
        has_spider = any(
            o.controller == defender and
            CardType.CREATURE in o.characteristics.types and
            'Spider' in o.characteristics.subtypes and
            o.zone == ZoneType.BATTLEFIELD
            for o in state.objects.values()
        )
        if has_spider:
            return [Event(type=EventType.TEMPORARY_EFFECT, payload={
                'object_id': obj.id,
                'effect': 'pt_boost',
                'power': 2,
                'toughness': 2,
                'duration': 'end_of_turn'
            }, source=obj.id)]
        return []
    return [make_attack_trigger(obj, attack_effect)]

SPIDER_SLAYERS = make_creature(
    name="Spider-Slayers",
    power=4,
    toughness=4,
    mana_cost="{4}",
    subtypes={"Construct"},
    text="Whenever Spider-Slayers attacks a player who controls a Spider, it gets +2/+2 until end of turn.",
    setup_interceptors=spider_slayers_setup
)

def oscorp_security_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact dies trigger - +1/+1 until end of turn"""
    def artifact_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        return (dying and
                dying.controller == source.controller and
                CardType.ARTIFACT in dying.characteristics.types)

    def boost_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TEMPORARY_EFFECT, payload={
            'object_id': obj.id,
            'effect': 'pt_boost',
            'power': 1,
            'toughness': 1,
            'duration': 'end_of_turn'
        }, source=obj.id)]

    return [make_death_trigger(obj, boost_effect, filter_fn=artifact_dies_filter)]

OSCORP_SECURITY = make_creature(
    name="Oscorp Security",
    power=2,
    toughness=2,
    mana_cost="{2}",
    subtypes={"Human", "Soldier"},
    text="Whenever an artifact you control is put into a graveyard from the battlefield, Oscorp Security gets +1/+1 until end of turn.",
    setup_interceptors=oscorp_security_setup
)

def midtown_high_student_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 1"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

MIDTOWN_HIGH_STUDENT = make_creature(
    name="Midtown High Student",
    power=1,
    toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Citizen"},
    text="When Midtown High Student enters, scry 1.",
    setup_interceptors=midtown_high_student_setup
)

def ned_leeds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Noncreature spell cast - +1/+1 counter on target Spider"""
    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        # Target Spider gets counter (targeting system)
        return []  # Targeting system fills this in

    return [make_spell_cast_trigger(obj, counter_effect, filter_fn=noncreature_filter)]

NED_LEEDS = make_creature(
    name="Ned Leeds",
    power=1,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ally"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, put a +1/+1 counter on target Spider you control.",
    setup_interceptors=ned_leeds_setup
)

def flash_thompson_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - if you control a Spider, create Soldier token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        has_spider = any(
            o.controller == obj.controller and
            CardType.CREATURE in o.characteristics.types and
            'Spider' in o.characteristics.subtypes and
            o.zone == ZoneType.BATTLEFIELD
            for o in state.objects.values()
        )
        if has_spider:
            return [Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Soldier', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Soldier'}},
            }, source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]

FLASH_THOMPSON = make_creature(
    name="Flash Thompson",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="When Flash Thompson enters, if you control a Spider, create a 1/1 white Soldier creature token.",
    setup_interceptors=flash_thompson_setup
)

def liz_allan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spider attacks - gain 1 life"""
    def spider_attacks_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == source.controller and
                'Spider' in attacker.characteristics.subtypes)

    def gain_life_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_attack_trigger(obj, gain_life_effect, filter_fn=spider_attacks_filter)]

LIZ_ALLAN = make_creature(
    name="Liz Allan",
    power=1,
    toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="Whenever a Spider you control attacks, you gain 1 life.",
    setup_interceptors=liz_allan_setup
)

ROBBIE_ROBERTSON = make_creature(
    name="Robbie Robertson",
    power=1,
    toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Advisor"},
    text="{T}: Investigate."
)

def betty_brant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - draw a card"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

BETTY_BRANT = make_creature(
    name="Betty Brant",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Betty Brant enters, draw a card.",
    setup_interceptors=betty_brant_setup
)

EMPIRE_STATE_BUILDING = make_land(
    name="Empire State Building",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {2}, {T}: Target creature gains flying until end of turn."
)

AVENGERS_TOWER = make_land(
    name="Avengers Tower",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Hero spells."
)

RAFT_PRISON = make_land(
    name="The Raft Prison",
    text="The Raft Prison enters tapped. {T}: Add {B}. {3}{B}, {T}: Destroy target creature with power 2 or less."
)

TIMES_SQUARE = make_land(
    name="Times Square",
    text="Times Square enters tapped. {T}: Add {R} or {W}. {4}, {T}: Create a 1/1 white Citizen creature token."
)

CENTRAL_PARK = make_land(
    name="Central Park",
    text="Central Park enters tapped. {T}: Add {G} or {W}. When Central Park enters, you gain 1 life."
)

MANHATTAN_SKYLINE = make_land(
    name="Manhattan Skyline",
    text="Manhattan Skyline enters tapped. {T}: Add {W} or {U}. Spiders you control have flying."
)

HERO_LANDING = make_instant(
    name="Hero Landing",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature you control gains indestructible until end of turn. If it's a Spider or Hero, untap it."
)

TEAM_UP = make_sorcery(
    name="Team Up",
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Create two 1/1 white and blue Spider creature tokens with flying and reach."
)

SINISTER_SUMMIT = make_sorcery(
    name="Sinister Summit",
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Search your library for a Villain card, reveal it, put it into your hand, then shuffle. Each opponent loses 2 life."
)

THWIP = make_instant(
    name="Thwip!",
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Web — Tap up to two target creatures. They don't untap during their controllers' next untap steps."
)

QUIP = make_instant(
    name="Quip",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +1/+3 until end of turn. If you control a Spider, draw a card."
)

def scientific_genius_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact or instant spell cast - scry 1"""
    def artifact_instant_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.ARTIFACT in spell_types or CardType.INSTANT in spell_types

    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_spell_cast_trigger(obj, scry_effect, filter_fn=artifact_instant_filter)]

SCIENTIFIC_GENIUS = make_enchantment(
    name="Scientific Genius",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an artifact or instant spell, scry 1.",
    setup_interceptors=scientific_genius_setup
)

def kingpins_empire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - create Treasure"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'},
                     'abilities': ['{T}, Sacrifice: Add one mana of any color.']},
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

KINGPINS_EMPIRE = make_enchantment(
    name="Kingpin's Empire",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, create a Treasure token. Sacrifice a creature: Draw a card.",
    setup_interceptors=kingpins_empire_setup
)

GLIDER_BOMB = make_artifact(
    name="Glider Bomb",
    mana_cost="{2}",
    text="{1}, Sacrifice Glider Bomb: Glider Bomb deals 2 damage to any target."
)

def tracking_device_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 2"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

TRACKING_DEVICE = make_artifact(
    name="Tracking Device",
    mana_cost="{1}",
    text="When Tracking Device enters, scry 2. {2}, {T}, Sacrifice Tracking Device: Draw a card.",
    setup_interceptors=tracking_device_setup
)

SHOCK_GAUNTLETS = make_artifact(
    name="Shock Gauntlets",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+0. Whenever equipped creature deals combat damage to a player, you may tap target creature that player controls. Equip {2}"
)

def sand_containment_unit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - exile creature power 5+ until this leaves"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Exile target creature with power 5+ (targeting system)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

SAND_CONTAINMENT_UNIT = make_artifact(
    name="Sand Containment Unit",
    mana_cost="{3}",
    text="When Sand Containment Unit enters, exile target creature with power 5 or greater until Sand Containment Unit leaves the battlefield.",
    setup_interceptors=sand_containment_unit_setup
)

ELECTRO_PROOF_SUIT = make_artifact(
    name="Electro-Proof Suit",
    mana_cost="{3}",
    subtypes={"Equipment"},
    text="Equipped creature has protection from red. Equip {2}"
)

ANTI_SYMBIOTE_SONIC = make_artifact(
    name="Anti-Symbiote Sonic Device",
    mana_cost="{3}",
    text="{2}, {T}: All Symbiotes get -2/-2 until end of turn."
)

MYSTERIOS_HELMET = make_artifact(
    name="Mysterio's Helmet",
    mana_cost="{2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +1/+2 and has hexproof from creatures. Equip {2}"
)

DOCS_TENTACLES = make_artifact(
    name="Doc's Tentacles",
    mana_cost="{4}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +2/+2. At the beginning of combat on your turn, you may tap target artifact or creature. Equip {3}"
)

LIZARD_SERUM = make_artifact(
    name="Lizard Serum",
    mana_cost="{2}",
    text="{2}, {T}, Sacrifice Lizard Serum: Target creature gets +3/+3 and gains trample until end of turn. It becomes a Lizard in addition to its other types."
)

NEWSPAPER_HEADLINE = make_sorcery(
    name="Newspaper Headline",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Draw two cards. Then discard a card unless you control a Spider."
)

ROOFTOP_CHASE = make_instant(
    name="Rooftop Chase",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. You may have that creature's controller scry 1."
)

DARK_ALLEY_AMBUSH = make_instant(
    name="Dark Alley Ambush",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If it's your turn, it gets -4/-4 instead."
)

COLLATERAL_DAMAGE = make_sorcery(
    name="Collateral Damage",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Collateral Damage deals 3 damage to target creature and 1 damage to its controller."
)

NATURE_UNLEASHED = make_sorcery(
    name="Nature Unleashed",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on each creature you control."
)

CLONE_SAGA = make_sorcery(
    name="Clone Saga",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control. Then create another token that's a copy of that creature."
)

MAXIMUM_CARNAGE = make_sorcery(
    name="Maximum Carnage",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy all creatures. Then create a 6/6 black and red Symbiote creature token with menace and trample for each creature destroyed this way that was a Symbiote."
)

def spider_island_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures have reach. Upkeep - create Spider token"""
    interceptors = []

    # Creatures have reach
    def your_creatures(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    interceptors.append(make_keyword_grant(obj, ['reach'], your_creatures))

    # Upkeep trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN},
                     'subtypes': {'Spider'}, 'keywords': ['reach']},
        }, source=obj.id)]
    interceptors.append(make_upkeep_trigger(obj, upkeep_effect))

    return interceptors

SPIDER_ISLAND = make_enchantment(
    name="Spider-Island",
    mana_cost="{3}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Creatures you control are Spiders in addition to their other types and have reach. At the beginning of your upkeep, create a 1/1 green Spider creature token with reach.",
    setup_interceptors=spider_island_setup
)

def spot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player - exile top card, may play"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        return [Event(type=EventType.EXILE_TOP_CARD, payload={
            'player': target,
            'may_play': True,
            'until': 'end_of_turn',
            'caster': obj.controller
        }, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]

SPOT = make_creature(
    name="Spot",
    power=3,
    toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — Spot can't be blocked. Portal Punch — Whenever Spot deals combat damage to a player, exile the top card of that player's library. You may play it this turn.",
    setup_interceptors=spot_setup
)

def demogoblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - destroy creature with lowest toughness"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Destroy creature with lowest toughness (targeting system)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

DEMOGOBLIN = make_creature(
    name="Demogoblin",
    power=4,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "Goblin", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Sinister — When Demogoblin enters, destroy target creature with the lowest toughness.",
    setup_interceptors=demogoblin_setup
)

def molten_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step - deal 1 damage to each opponent"""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(type=EventType.DAMAGE, payload={
                    'target': p_id,
                    'amount': 1,
                    'source': obj.id,
                    'is_combat': False
                }, source=obj.id))
        return events
    return [make_end_step_trigger(obj, end_step_effect)]

MOLTEN_MAN = make_creature(
    name="Molten Man",
    power=4,
    toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Elemental", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — Molten Man can't be blocked by creatures with power 2 or less. At the beginning of your end step, Molten Man deals 1 damage to each opponent.",
    setup_interceptors=molten_man_setup
)

def jackal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step - create copy token of target creature"""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Create copy token (targeting system)
        return []  # Targeting system fills this in
    return [make_end_step_trigger(obj, end_step_effect)]

JACKAL = make_creature(
    name="Jackal",
    power=3,
    toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Sinister — At the beginning of your end step, create a token that's a copy of target creature you control except it's named Clone and is a Shapeshifter in addition to its other types.",
    setup_interceptors=jackal_setup
)

def swarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - create three Insect tokens"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Insect', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK, Color.GREEN},
                         'subtypes': {'Insect'}, 'keywords': ['flying']},
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Insect', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK, Color.GREEN},
                         'subtypes': {'Insect'}, 'keywords': ['flying']},
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Insect', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK, Color.GREEN},
                         'subtypes': {'Insect'}, 'keywords': ['flying']},
            }, source=obj.id)
        ]
    return [make_death_trigger(obj, death_effect)]

SWARM = make_creature(
    name="Swarm",
    power=3,
    toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Insect", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Sinister — When Swarm dies, create three 1/1 black and green Insect creature tokens with flying.",
    setup_interceptors=swarm_setup
)

def will_o_wisp_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - tap target creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Tap target creature (targeting system)
        return []  # Targeting system fills this in
    return [make_etb_trigger(obj, etb_effect)]

WILL_O_WISP = make_creature(
    name="Will-o'-the-Wisp",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Villain"},
    text="Flash. Sinister — When Will-o'-the-Wisp enters, tap target creature.",
    setup_interceptors=will_o_wisp_setup
)

STILT_MAN = make_creature(
    name="Stilt-Man",
    power=3,
    toughness=5,
    mana_cost="{4}",
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Reach. Sinister — Stilt-Man can't be blocked by creatures with power 3 or less."
)

BIG_WHEEL = make_artifact(
    name="Big Wheel",
    mana_cost="{5}",
    subtypes={"Vehicle"},
    text="Trample. Whenever Big Wheel deals combat damage to a player, destroy target artifact that player controls. Crew 3"
)

def spider_mobile_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create Spider token with reach"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE},
                     'subtypes': {'Spider'}, 'keywords': ['reach']},
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SPIDER_MOBILE = make_artifact(
    name="Spider-Mobile",
    mana_cost="{3}",
    subtypes={"Vehicle"},
    text="When Spider-Mobile enters, create a 1/1 white Spider creature token with reach. Crew 1",
    setup_interceptors=spider_mobile_setup
)

RADIO_SILENCE = make_instant(
    name="Radio Silence",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target activated or triggered ability."
)

def city_that_never_sleeps_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Grant vigilance to creatures you control"""
    def your_creatures(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['vigilance'], your_creatures)]

CITY_THAT_NEVER_SLEEPS = make_enchantment(
    name="City That Never Sleeps",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control have vigilance.",
    setup_interceptors=city_that_never_sleeps_setup
)

SPIDER_SENSE_TINGLING = make_instant(
    name="Spider-Sense Tingling",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library. Put one into your hand and the rest on the bottom in any order. If you control a Spider, you may look at four cards instead."
)

def nyc_firefighter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 2 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

NYC_FIREFIGHTER = make_creature(
    name="NYC Firefighter",
    power=2,
    toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Citizen"},
    text="When NYC Firefighter enters, you gain 2 life.",
    setup_interceptors=nyc_firefighter_setup
)

SUBWAY_ESCAPE = make_instant(
    name="Subway Escape",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature you control to its owner's hand."
)

def power_and_responsibility_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spiders +1/+1. Spider combat damage to player - draw"""
    interceptors = []

    # Spiders get +1/+1
    def spider_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Spider' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    interceptors.extend(make_static_pt_boost(obj, 1, 1, spider_filter))

    # Spider combat damage to player - draw
    def spider_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        damager_id = event.payload.get('source')
        damager = state.objects.get(damager_id)
        if not damager:
            return False
        if damager.controller != source.controller:
            return False
        if 'Spider' not in damager.characteristics.subtypes:
            return False
        # Check if damage to player
        target = event.payload.get('target')
        return target in state.players

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    interceptors.append(make_damage_trigger(obj, draw_effect, combat_only=True, filter_fn=spider_damage_filter))

    return interceptors

POWER_AND_RESPONSIBILITY = make_enchantment(
    name="Power and Responsibility",
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Spiders you control get +1/+1. Whenever a Spider you control deals combat damage to a player, draw a card.",
    setup_interceptors=power_and_responsibility_setup
)

def ben_reilly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Web on attack - tap defender's creature. Death - return to hand"""
    interceptors = []

    # Web on attack
    interceptors.append(make_web_attack(obj))

    # Death trigger - return to hand
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ZONE_CHANGE, payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.GRAVEYARD,
            'to_zone_type': ZoneType.HAND,
            'may': True
        }, source=obj.id)]
    interceptors.append(make_death_trigger(obj, death_effect))

    return interceptors

BEN_REILLY = make_creature(
    name="Ben Reilly",
    power=3,
    toughness=3,
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Spider", "Hero"},
    supertypes={"Legendary"},
    text="First strike. Web — Whenever Ben Reilly attacks, tap target creature defending player controls. Clone — When Ben Reilly dies, you may return him to your hand.",
    setup_interceptors=ben_reilly_setup
)


# =============================================================================
# REGISTRY
# =============================================================================

SPIDER_MAN_CUSTOM_CARDS = {
    # WHITE - HEROES
    "Spider-Man, Friendly Neighbor": SPIDER_MAN_FRIENDLY_NEIGHBOR,
    "Spider-Man, With Great Power": SPIDER_MAN_WITH_GREAT_POWER,
    "Spider-Gwen": SPIDER_GWEN,
    "Miles Morales": MILES_MORALES,
    "Spider-Woman": SPIDER_WOMAN,
    "Aunt May": AUNT_MAY,
    "Mary Jane Watson": MARY_JANE_WATSON,
    "Daily Bugle Photographer": DAILY_BUGLE_PHOTOGRAPHER,
    "NYC Police Officer": NYC_POLICE_OFFICER,
    "Rescue Workers": RESCUE_WORKERS,
    "Web Shield": WEB_SHIELD,
    "Great Responsibility": GREAT_RESPONSIBILITY,
    "With Great Power": WITH_GREAT_POWER,
    "Save the Day": SAVE_THE_DAY,

    # BLUE - SCIENCE
    "Peter Parker, Scientist": PETER_PARKER_SCIENTIST,
    "Dr. Octopus, Otto Octavius": DR_OCTOPUS_OTTO_OCTAVIUS,
    "Mysterio, Master of Illusion": MYSTERIO_MASTER_OF_ILLUSION,
    "The Lizard": THE_LIZARD,
    "Madame Web": MADAME_WEB,
    "Oscorp Scientist": OSCORP_SCIENTIST,
    "Spider-Sense Alert": SPIDER_SENSE_ALERT,
    "Web Sling": WEB_SLING,
    "Illusion Duplicate": ILLUSION_DUPLICATE,
    "Advanced Web Formula": ADVANCED_WEB_FORMULA,
    "Technological Breakthrough": TECHNOLOGICAL_BREAKTHROUGH,
    "Mind Control Device": MIND_CONTROL_DEVICE,

    # BLACK - VILLAINS & SYMBIOTES
    "Venom, Lethal Protector": VENOM_LETHAL_PROTECTOR,
    "Carnage, Cletus Kasady": CARNAGE_CLETUS_KASADY,
    "Green Goblin, Norman Osborn": GREEN_GOBLIN_NORMAN_OSBORN,
    "Hobgoblin": HOBGOBLIN,
    "Morbius, the Living Vampire": MORBIUS_THE_LIVING_VAMPIRE,
    "Kingpin, Wilson Fisk": KINGPIN_WILSON_FISK,
    "Symbiote Tendril": SYMBIOTE_TENDRIL,
    "Black Cat": BLACK_CAT,
    "Crime Boss": CRIME_BOSS,
    "Sinister Plot": SINISTER_PLOT,
    "Symbiote Bond": SYMBIOTE_BOND,
    "Web of Shadows": WEB_OF_SHADOWS,

    # RED - ACTION
    "Scarlet Spider": SCARLET_SPIDER,
    "Electro": ELECTRO,
    "Shocker": SHOCKER,
    "Sandman": SANDMAN,
    "Rhino": RHINO,
    "Scorpion": SCORPION,
    "Web Strike": WEB_STRIKE,
    "Pumpkin Bomb": PUMPKIN_BOMB,
    "Goblin Glider Assault": GOBLIN_GLIDER_ASSAULT,
    "Electric Discharge": ELECTRIC_DISCHARGE,
    "Sinister Rage": SINISTER_RAGE,
    "Building Collapse": BUILDING_COLLAPSE,

    # GREEN - STRENGTH
    "Spider-Hulk": SPIDER_HULK,
    "Spider-Pig (Peter Porker)": SPIDER_PIG,
    "Kraven the Hunter": KRAVEN_THE_HUNTER,
    "Vermin": VERMIN,
    "Spider Colony": SPIDER_COLONY,
    "Forest Spider": FOREST_SPIDER,
    "Venomous Bite": VENOMOUS_BITE,
    "Spider Swarm": SPIDER_SWARM,
    "Web Trap": WEB_TRAP,
    "Primal Instinct": PRIMAL_INSTINCT,
    "Jungle Ambush": JUNGLE_AMBUSH,
    "Nature's Wrath": NATURES_WRATH,

    # MULTICOLOR
    "Spider-Verse Team": SPIDER_VERSE_TEAM,
    "Sinister Six": SINISTER_SIX,
    "Anti-Venom": ANTI_VENOM,
    "Silk": SILK,
    "Prowler": PROWLER,
    "Toxin": TOXIN,
    "Agent Venom": AGENT_VENOM,
    "Spider-Man, Sorcerer Supreme": DR_STRANGE_SPIDER,

    # ARTIFACTS
    "Web Shooters": WEB_SHOOTERS,
    "Spider-Tracer": SPIDER_TRACER,
    "Oscorp Tech": OSCORP_TECH,
    "Goblin Glider": GOBLIN_GLIDER,
    "Iron Spider Suit": IRON_SPIDER_SUIT,
    "Symbiote Sample": SYMBIOTE_SAMPLE,
    "Daily Bugle Press": DAILY_BUGLE_PRESS,
    "Stark Tech Upgrade": STARK_TECH_UPGRADE,

    # LANDS
    "New York City": NEW_YORK_CITY,
    "Daily Bugle Building": DAILY_BUGLE_BUILDING,
    "Oscorp Tower": OSCORP_TOWER,
    "Fisk Tower": FISK_TOWER,
    "Hell's Kitchen": HELL_KITCHEN,
    "Brooklyn Bridge": BROOKLYN_BRIDGE,
    "Queens Neighborhood": QUEENS_NEIGHBORHOOD,
    "Stark Tower": STARK_TOWER,
    "Symbiote Planet": SYMBIOTE_PLANET,

    # BASIC LANDS
    "Plains": PLAINS_SPM,
    "Island": ISLAND_SPM,
    "Swamp": SWAMP_SPM,
    "Mountain": MOUNTAIN_SPM,
    "Forest": FOREST_SPM,

    # EXTRA CARDS
    "Spider-Noir": SPIDER_NOIR,
    "Mayday Parker": MAYDAY_PARKER,
    "Spider-Man 2099": SPIDER_2099,
    "Spider-UK": SPIDER_UK,
    "Peni Parker": PENI_PARKER,
    "Superior Spider-Man": SUPERIOR_SPIDER_MAN,
    "Spider-Punk": SPIDER_PUNK,
    "Spider-Ham Attack": SPIDER_HAM_ATTACK,
    "Multiverse Portal": MULTIVERSE_PORTAL,
    "Dimension Hopping": DIMENSION_HOPPING,
    "Symbiote Invasion": SYMBIOTE_INVASION,
    "Electro Shock": ELECTRO_SHOCK,
    "Hunter's Trap": HUNTERS_TRAP,
    "Spider Army": SPIDER_ARMY,
    "J. Jonah Jameson": J_JONAH_JAMESON,
    "Gwen Stacy": GWEN_STACY,
    "Harry Osborn": HARRY_OSBORN,
    "Felicia Hardy": FELICIA_HARDY,
    "Vulture": VULTURE,
    "Hydro-Man": HYDRO_MAN,
    "Chameleon": CHAMELEON,
    "Beetle": BEETLE,
    "Hammerhead": HAMMERHEAD,
    "Tombstone": TOMBSTONE,
    "Silver Sable": SILVER_SABLE,

    # ADDITIONAL CARDS
    "Spectacular Swing": SPECTACULAR_SWING,
    "Neighborhood Watch": NEIGHBORHOOD_WATCH,
    "Uncle Ben": UNCLE_BEN,
    "Spider-Sense": SPIDER_SENSE,
    "Oscorp Lab": OSCORP_LAB,
    "Experiment Gone Wrong": EXPERIMENT_GONE_WRONG,
    "Hologram Decoy": HOLOGRAM_DECOY,
    "Genetic Mutation": GENETIC_MUTATION,
    "Symbiote Surge": SYMBIOTE_SURGE,
    "Underworld Connections": UNDERWORLD_CONNECTIONS,
    "Hired Muscle": HIRED_MUSCLE,
    "Shock Therapy": SHOCK_THERAPY,
    "Explosive Rampage": EXPLOSIVE_RAMPAGE,
    "Goblin Army": GOBLIN_ARMY,
    "Fire Punch": FIRE_PUNCH,
    "Radioactive Bite": RADIOACTIVE_BITE,
    "Predator Instinct": PREDATOR_INSTINCT,
    "Giant Spider": GIANT_SPIDER,
    "Savage Hunter": SAVAGE_HUNTER,
    "Web Cocoon": WEB_COCOON,
    "Spider Queen": SPIDER_QUEEN,
    "Scream": SCREAM,
    "Riot": RIOT,
    "Phage": PHAGE,
    "Lasher": LASHER,
    "Agony": AGONY,
    "Web Warriors": WEB_WARRIORS,
    "Spider-Slayers": SPIDER_SLAYERS,
    "Oscorp Security": OSCORP_SECURITY,
    "Midtown High Student": MIDTOWN_HIGH_STUDENT,
    "Ned Leeds": NED_LEEDS,
    "Flash Thompson": FLASH_THOMPSON,
    "Liz Allan": LIZ_ALLAN,
    "Robbie Robertson": ROBBIE_ROBERTSON,
    "Betty Brant": BETTY_BRANT,
    "Empire State Building": EMPIRE_STATE_BUILDING,
    "Avengers Tower": AVENGERS_TOWER,
    "The Raft Prison": RAFT_PRISON,
    "Times Square": TIMES_SQUARE,
    "Central Park": CENTRAL_PARK,
    "Manhattan Skyline": MANHATTAN_SKYLINE,
    "Hero Landing": HERO_LANDING,
    "Team Up": TEAM_UP,
    "Sinister Summit": SINISTER_SUMMIT,
    "Thwip!": THWIP,
    "Quip": QUIP,
    "Scientific Genius": SCIENTIFIC_GENIUS,
    "Kingpin's Empire": KINGPINS_EMPIRE,
    "Glider Bomb": GLIDER_BOMB,
    "Tracking Device": TRACKING_DEVICE,
    "Shock Gauntlets": SHOCK_GAUNTLETS,
    "Sand Containment Unit": SAND_CONTAINMENT_UNIT,
    "Electro-Proof Suit": ELECTRO_PROOF_SUIT,
    "Anti-Symbiote Sonic Device": ANTI_SYMBIOTE_SONIC,
    "Mysterio's Helmet": MYSTERIOS_HELMET,
    "Doc's Tentacles": DOCS_TENTACLES,
    "Lizard Serum": LIZARD_SERUM,
    "Newspaper Headline": NEWSPAPER_HEADLINE,
    "Rooftop Chase": ROOFTOP_CHASE,
    "Dark Alley Ambush": DARK_ALLEY_AMBUSH,
    "Collateral Damage": COLLATERAL_DAMAGE,
    "Nature Unleashed": NATURE_UNLEASHED,
    "Clone Saga": CLONE_SAGA,
    "Maximum Carnage": MAXIMUM_CARNAGE,
    "Spider-Island": SPIDER_ISLAND,
    "Spot": SPOT,
    "Demogoblin": DEMOGOBLIN,
    "Molten Man": MOLTEN_MAN,
    "Jackal": JACKAL,
    "Swarm": SWARM,
    "Will-o'-the-Wisp": WILL_O_WISP,
    "Stilt-Man": STILT_MAN,
    "Big Wheel": BIG_WHEEL,
    "Spider-Mobile": SPIDER_MOBILE,
    "Radio Silence": RADIO_SILENCE,
    "City That Never Sleeps": CITY_THAT_NEVER_SLEEPS,
    "Spider-Sense Tingling": SPIDER_SENSE_TINGLING,
    "NYC Firefighter": NYC_FIREFIGHTER,
    "Subway Escape": SUBWAY_ESCAPE,
    "Power and Responsibility": POWER_AND_RESPONSIBILITY,
    "Ben Reilly": BEN_REILLY,
}

print(f"Loaded {len(SPIDER_MAN_CUSTOM_CARDS)} Marvel's Spider-Man cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    SPIDER_MAN_FRIENDLY_NEIGHBOR,
    SPIDER_MAN_WITH_GREAT_POWER,
    SPIDER_GWEN,
    MILES_MORALES,
    SPIDER_WOMAN,
    AUNT_MAY,
    MARY_JANE_WATSON,
    DAILY_BUGLE_PHOTOGRAPHER,
    NYC_POLICE_OFFICER,
    RESCUE_WORKERS,
    WEB_SHIELD,
    GREAT_RESPONSIBILITY,
    WITH_GREAT_POWER,
    SAVE_THE_DAY,
    PETER_PARKER_SCIENTIST,
    DR_OCTOPUS_OTTO_OCTAVIUS,
    MYSTERIO_MASTER_OF_ILLUSION,
    THE_LIZARD,
    MADAME_WEB,
    OSCORP_SCIENTIST,
    SPIDER_SENSE_ALERT,
    WEB_SLING,
    ILLUSION_DUPLICATE,
    ADVANCED_WEB_FORMULA,
    TECHNOLOGICAL_BREAKTHROUGH,
    MIND_CONTROL_DEVICE,
    VENOM_LETHAL_PROTECTOR,
    CARNAGE_CLETUS_KASADY,
    GREEN_GOBLIN_NORMAN_OSBORN,
    HOBGOBLIN,
    MORBIUS_THE_LIVING_VAMPIRE,
    KINGPIN_WILSON_FISK,
    SYMBIOTE_TENDRIL,
    BLACK_CAT,
    CRIME_BOSS,
    SINISTER_PLOT,
    SYMBIOTE_BOND,
    WEB_OF_SHADOWS,
    SCARLET_SPIDER,
    ELECTRO,
    SHOCKER,
    SANDMAN,
    RHINO,
    SCORPION,
    WEB_STRIKE,
    PUMPKIN_BOMB,
    GOBLIN_GLIDER_ASSAULT,
    ELECTRIC_DISCHARGE,
    SINISTER_RAGE,
    BUILDING_COLLAPSE,
    SPIDER_HULK,
    SPIDER_PIG,
    KRAVEN_THE_HUNTER,
    VERMIN,
    SPIDER_COLONY,
    FOREST_SPIDER,
    VENOMOUS_BITE,
    SPIDER_SWARM,
    WEB_TRAP,
    PRIMAL_INSTINCT,
    JUNGLE_AMBUSH,
    NATURES_WRATH,
    SPIDER_VERSE_TEAM,
    SINISTER_SIX,
    ANTI_VENOM,
    SILK,
    PROWLER,
    TOXIN,
    AGENT_VENOM,
    DR_STRANGE_SPIDER,
    WEB_SHOOTERS,
    SPIDER_TRACER,
    OSCORP_TECH,
    GOBLIN_GLIDER,
    IRON_SPIDER_SUIT,
    SYMBIOTE_SAMPLE,
    DAILY_BUGLE_PRESS,
    STARK_TECH_UPGRADE,
    NEW_YORK_CITY,
    DAILY_BUGLE_BUILDING,
    OSCORP_TOWER,
    FISK_TOWER,
    HELL_KITCHEN,
    BROOKLYN_BRIDGE,
    QUEENS_NEIGHBORHOOD,
    STARK_TOWER,
    SYMBIOTE_PLANET,
    PLAINS_SPM,
    ISLAND_SPM,
    SWAMP_SPM,
    MOUNTAIN_SPM,
    FOREST_SPM,
    SPIDER_NOIR,
    MAYDAY_PARKER,
    SPIDER_2099,
    SPIDER_UK,
    PENI_PARKER,
    SUPERIOR_SPIDER_MAN,
    SPIDER_PUNK,
    SPIDER_HAM_ATTACK,
    MULTIVERSE_PORTAL,
    DIMENSION_HOPPING,
    SYMBIOTE_INVASION,
    ELECTRO_SHOCK,
    HUNTERS_TRAP,
    SPIDER_ARMY,
    J_JONAH_JAMESON,
    GWEN_STACY,
    HARRY_OSBORN,
    FELICIA_HARDY,
    VULTURE,
    HYDRO_MAN,
    CHAMELEON,
    BEETLE,
    HAMMERHEAD,
    TOMBSTONE,
    SILVER_SABLE,
    SPECTACULAR_SWING,
    NEIGHBORHOOD_WATCH,
    UNCLE_BEN,
    SPIDER_SENSE,
    OSCORP_LAB,
    EXPERIMENT_GONE_WRONG,
    HOLOGRAM_DECOY,
    GENETIC_MUTATION,
    SYMBIOTE_SURGE,
    UNDERWORLD_CONNECTIONS,
    HIRED_MUSCLE,
    SHOCK_THERAPY,
    EXPLOSIVE_RAMPAGE,
    GOBLIN_ARMY,
    FIRE_PUNCH,
    RADIOACTIVE_BITE,
    PREDATOR_INSTINCT,
    GIANT_SPIDER,
    SAVAGE_HUNTER,
    WEB_COCOON,
    SPIDER_QUEEN,
    SCREAM,
    RIOT,
    PHAGE,
    LASHER,
    AGONY,
    WEB_WARRIORS,
    SPIDER_SLAYERS,
    OSCORP_SECURITY,
    MIDTOWN_HIGH_STUDENT,
    NED_LEEDS,
    FLASH_THOMPSON,
    LIZ_ALLAN,
    ROBBIE_ROBERTSON,
    BETTY_BRANT,
    EMPIRE_STATE_BUILDING,
    AVENGERS_TOWER,
    RAFT_PRISON,
    TIMES_SQUARE,
    CENTRAL_PARK,
    MANHATTAN_SKYLINE,
    HERO_LANDING,
    TEAM_UP,
    SINISTER_SUMMIT,
    THWIP,
    QUIP,
    SCIENTIFIC_GENIUS,
    KINGPINS_EMPIRE,
    GLIDER_BOMB,
    TRACKING_DEVICE,
    SHOCK_GAUNTLETS,
    SAND_CONTAINMENT_UNIT,
    ELECTRO_PROOF_SUIT,
    ANTI_SYMBIOTE_SONIC,
    MYSTERIOS_HELMET,
    DOCS_TENTACLES,
    LIZARD_SERUM,
    NEWSPAPER_HEADLINE,
    ROOFTOP_CHASE,
    DARK_ALLEY_AMBUSH,
    COLLATERAL_DAMAGE,
    NATURE_UNLEASHED,
    CLONE_SAGA,
    MAXIMUM_CARNAGE,
    SPIDER_ISLAND,
    SPOT,
    DEMOGOBLIN,
    MOLTEN_MAN,
    JACKAL,
    SWARM,
    WILL_O_WISP,
    STILT_MAN,
    BIG_WHEEL,
    SPIDER_MOBILE,
    RADIO_SILENCE,
    CITY_THAT_NEVER_SLEEPS,
    SPIDER_SENSE_TINGLING,
    NYC_FIREFIGHTER,
    SUBWAY_ESCAPE,
    POWER_AND_RESPONSIBILITY,
    BEN_REILLY
]
