"""
Murders at Karlov Manor (MKM) Card Implementations

Set released February 2024. ~250 cards.
Features mechanics: Clue tokens, Suspect, Collect Evidence, Disguise, Cases
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
    other_creatures_with_subtype, all_opponents, make_draw_trigger
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


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None):
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
        text=text
    )


# =============================================================================
# MKM KEYWORD MECHANICS
# =============================================================================

def make_clue_token_creation(source_obj: GameObject, count: int = 1) -> list[Event]:
    """Create Clue artifact token(s). Clues have '{2}, Sacrifice: Draw a card.'"""
    events = []
    for _ in range(count):
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': source_obj.controller,
                'token': {
                    'name': 'Clue',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Clue'},
                    'abilities': ['{2}, Sacrifice this artifact: Draw a card.']
                }
            },
            source=source_obj.id
        ))
    return events


def make_suspect_creature(source_obj: GameObject) -> list[Interceptor]:
    """
    Suspect - This creature has menace and can't block.
    Returns interceptors that grant menace and prevent blocking.
    """
    interceptors = []

    # Grant menace
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id

    interceptors.append(make_keyword_grant(source_obj, ['menace'], self_filter))

    # Prevent blocking
    def block_prevention_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        return event.payload.get('blocker_id') == source_obj.id

    def block_prevention_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    interceptors.append(Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=block_prevention_filter,
        handler=block_prevention_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


def make_collect_evidence(source_obj: GameObject, evidence_cost: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Collect evidence N - Exile cards from your graveyard with total mana value N or greater.
    This creates an activated ability trigger.
    """
    def evidence_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'collect_evidence')

    def evidence_handler(event: Event, state: GameState) -> InterceptorResult:
        # Check if graveyard has enough mana value
        # The actual exile happens as part of the cost
        effect_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=evidence_filter,
        handler=evidence_handler,
        duration='while_on_battlefield'
    )


def make_disguise(source_obj: GameObject, disguise_cost: str) -> list[Interceptor]:
    """
    Disguise - You may cast this face down as a 2/2 creature for {3}.
    Turn it face up any time for its disguise cost (with ward {2}).
    """
    interceptors = []

    # Face-down creatures have ward 2
    def ward_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TARGET:
            return False
        if event.payload.get('target_id') != source_obj.id:
            return False
        # Check if face-down
        return source_obj.state.get('face_down', False)

    def ward_handler(event: Event, state: GameState) -> InterceptorResult:
        # Require {2} payment or counter
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=EventType.WARD_TRIGGER,
                payload={
                    'target_id': source_obj.id,
                    'ward_cost': '{2}',
                    'original_event': event
                },
                source=source_obj.id
            )
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=ward_filter,
        handler=ward_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


def make_case_enchantment(name: str, mana_cost: str, colors: set,
                          initial_text: str, solved_condition: str, solved_text: str,
                          setup_interceptors=None):
    """
    Case enchantments - Start unsolved, become solved when condition is met.
    Solved cases gain additional abilities.
    """
    full_text = f"Case - {initial_text}\nTo solve - {solved_condition}\nSolved - {solved_text}"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes={'Case'},
            colors=colors,
            mana_cost=mana_cost
        ),
        text=full_text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# WHITE CARDS - AZORIUS DETECTIVES, ORZHOV INVESTIGATORS
# =============================================================================

# --- Legendary Creatures ---

def alquist_proft_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you draw your second card each turn, investigate."""
    draw_count = {'this_turn': 0}

    def draw_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DRAW:
            return False
        if event.payload.get('player') != source.controller:
            return False
        draw_count['this_turn'] += 1
        return draw_count['this_turn'] == 2

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return make_clue_token_creation(obj)

    def turn_reset_filter(event: Event, state: GameState) -> bool:
        return event.type == EventType.PHASE_START and event.payload.get('phase') == 'upkeep'

    def turn_reset_handler(event: Event, state: GameState) -> InterceptorResult:
        draw_count['this_turn'] = 0
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: draw_filter(e, s, obj),
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
            duration='while_on_battlefield'
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=turn_reset_filter,
            handler=turn_reset_handler,
            duration='while_on_battlefield'
        )
    ]

ALQUIST_PROFT_MASTER_SLEUTH = make_creature(
    name="Alquist Proft, Master Sleuth",
    power=1, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Detective"},
    supertypes={"Legendary"},
    text="Vigilance. Whenever you draw your second card each turn, investigate. {5}{W}{U}: Exile Alquist Proft, then return him to the battlefield transformed.",
    setup_interceptors=alquist_proft_setup
)


def kaya_spirits_justice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more creatures you control deal combat damage to a player, exile up to one target creature."""
    def combat_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        attacker_id = event.payload.get('source')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return attacker.controller == source.controller

    def exile_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_AND_EXILE,
            payload={'controller': obj.controller, 'target_type': 'creature'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: combat_damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=exile_effect(e, s)),
        duration='while_on_battlefield'
    )]

KAYA_SPIRITS_JUSTICE = make_creature(
    name="Kaya, Spirits' Justice",
    power=2, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="Flying. Whenever one or more creatures you control deal combat damage to a player, exile up to one target creature that player controls. You may cast it for as long as it remains exiled.",
    setup_interceptors=kaya_spirits_justice_setup
)


def ezrim_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, vigilance. Other Detectives you control get +1/+1."""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Detective"))

EZRIM_AGENCY_CHIEF = make_creature(
    name="Ezrim, Agency Chief",
    power=3, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Archon", "Detective"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Other Detective creatures you control get +1/+1. Whenever Ezrim attacks, investigate.",
    setup_interceptors=ezrim_setup
)


def aurelia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, vigilance, trample. Whenever a creature enters under your control, if it wasn't cast, it gains haste."""
    def etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types and
                not event.payload.get('was_cast', True))

    def haste_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': event.payload.get('object_id'),
                'keyword': 'haste',
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=haste_effect(e, s)),
        duration='while_on_battlefield'
    )]

AURELIA_THE_LAW_ABOVE = make_creature(
    name="Aurelia, the Law Above",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance, trample. Whenever a creature enters the battlefield under your control, if it wasn't cast, it gains haste until end of turn.",
    setup_interceptors=aurelia_setup
)


# --- Regular White Creatures ---

def agency_outfitter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Create a Clue token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return make_clue_token_creation(obj)
    return [make_etb_trigger(obj, etb_effect)]

AGENCY_OUTFITTER = make_creature(
    name="Agency Outfitter",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Detective"},
    text="When Agency Outfitter enters the battlefield, create a Clue token.",
    setup_interceptors=agency_outfitter_setup
)


def azorius_arrester_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Tap target creature an opponent controls. It doesn't untap during its controller's next untap step."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP_AND_LOCK,
            payload={'controller': obj.controller, 'target_type': 'opponent_creature'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

AZORIUS_ARRESTER = make_creature(
    name="Azorius Arrester",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Azorius Arrester enters the battlefield, detain target creature an opponent controls.",
    setup_interceptors=azorius_arrester_setup
)


TENTH_DISTRICT_GUARDIAN = make_creature(
    name="Tenth District Guardian",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. {1}{W}: Another target creature you control gains vigilance until end of turn."
)


def novice_inspector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Investigate."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return make_clue_token_creation(obj)
    return [make_etb_trigger(obj, etb_effect)]

NOVICE_INSPECTOR = make_creature(
    name="Novice Inspector",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Detective"},
    text="When Novice Inspector enters the battlefield, investigate.",
    setup_interceptors=novice_inspector_setup
)


def seasoned_consultant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice a Clue, put a +1/+1 counter on this creature."""
    def clue_sacrifice_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        return 'Clue' in sacrificed.characteristics.subtypes and sacrificed.controller == source.controller

    def counter_effect(event: Event, state: GameState) -> list[Event]:
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
        filter=lambda e, s: clue_sacrifice_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=counter_effect(e, s)),
        duration='while_on_battlefield'
    )]

SEASONED_CONSULTANT = make_creature(
    name="Seasoned Consultant",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Detective"},
    text="Whenever you sacrifice a Clue, put a +1/+1 counter on Seasoned Consultant.",
    setup_interceptors=seasoned_consultant_setup
)


DEDICATED_BODYGUARD = make_creature(
    name="Dedicated Bodyguard",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash. When Dedicated Bodyguard enters the battlefield, target creature you control gains indestructible until end of turn."
)


FORENSIC_RESEARCHER = make_creature(
    name="Forensic Researcher",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Detective"},
    text="Collect evidence 4 - {T}: Draw a card. Activate only if you've collected evidence this turn."
)


BASILICA_STALKER = make_creature(
    name="Basilica Stalker",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying. Whenever Basilica Stalker deals combat damage to a player, investigate."
)


WOJEK_INVESTIGATOR = make_creature(
    name="Wojek Investigator",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Detective"},
    text="First strike. Whenever you sacrifice a Clue, Wojek Investigator gets +1/+1 until end of turn."
)


EVIDENCE_EXAMINER = make_creature(
    name="Evidence Examiner",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Detective"},
    text="When Evidence Examiner enters the battlefield, investigate twice."
)


SKYGUARD_PATROL = make_creature(
    name="Skyguard Patrol",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Flying, vigilance."
)


# --- White Instants ---

MAKE_YOUR_MOVE = make_instant(
    name="Make Your Move",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target attacking or blocking creature. Investigate."
)


ELIMINATE_THE_IMPOSSIBLE = make_instant(
    name="Eliminate the Impossible",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one - Exile target artifact; or exile target enchantment. Investigate."
)


NOT_ON_MY_WATCH = make_instant(
    name="Not on My Watch",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target attacking creature. Its controller creates a Clue token."
)


CASE_THE_JOINT = make_instant(
    name="Case the Joint",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +1/+1 until end of turn. Investigate."
)


PROTECT_THE_SCENE = make_instant(
    name="Protect the Scene",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control gain hexproof and indestructible until end of turn."
)


# --- White Sorceries ---

MANDATE_OF_PEACE = make_sorcery(
    name="Mandate of Peace",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures with power 4 or greater. Investigate for each creature destroyed this way."
)


GATHER_CLUES = make_sorcery(
    name="Gather Clues",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Create two Clue tokens. You gain 2 life."
)


# =============================================================================
# BLUE CARDS - DIMIR SPIES, SIMIC RESEARCHERS
# =============================================================================

def teysa_opulent_oligarch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Afterlife 1. Whenever a creature token you control dies, create a Clue."""
    def token_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
                dying.state.get('is_token', False))

    def clue_effect(event: Event, state: GameState) -> list[Event]:
        return make_clue_token_creation(obj)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: token_death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=clue_effect(e, s)),
        duration='while_on_battlefield'
    )]

TEYSA_OPULENT_OLIGARCH = make_creature(
    name="Teysa, Opulent Oligarch",
    power=2, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="Vigilance, lifelink. Afterlife 1. Whenever a creature token you control dies, create a Clue token.",
    setup_interceptors=teysa_opulent_oligarch_setup
)


def kellan_inquisitive_prodigy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike. Whenever Kellan deals combat damage to a player, investigate."""
    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target = event.payload.get('target')
        return target in state.players

    def investigate_effect(event: Event, state: GameState) -> list[Event]:
        return make_clue_token_creation(obj)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=investigate_effect(e, s)),
        duration='while_on_battlefield'
    )]

KELLAN_INQUISITIVE_PRODIGY = make_creature(
    name="Kellan, Inquisitive Prodigy",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Faerie", "Detective"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Kellan deals combat damage to a player, investigate.",
    setup_interceptors=kellan_inquisitive_prodigy_setup
)


# --- Blue Legendary Creatures ---

def lavinia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice an artifact, you may tap or untap target nonland permanent."""
    def artifact_sacrifice_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if not sacrificed:
            return False
        return (sacrificed.controller == source.controller and
                CardType.ARTIFACT in sacrificed.characteristics.types)

    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP_UNTAP_CHOICE,
            payload={'controller': obj.controller, 'target_type': 'nonland_permanent'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: artifact_sacrifice_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=tap_effect(e, s)),
        duration='while_on_battlefield'
    )]

LAVINIA_AZORIUS_RENEGADE = make_creature(
    name="Lavinia, Azorius Renegade",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Soldier", "Detective"},
    supertypes={"Legendary"},
    text="Whenever you sacrifice an artifact, you may tap or untap target nonland permanent. At the beginning of your end step, investigate.",
    setup_interceptors=lavinia_setup
)


def morska_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Skulk. Cloak - When Morska enters, it gets +1/+1 and hexproof until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={
                'object_id': obj.id, 'counter_type': '+1/+1_until_eot', 'amount': 1
            }, source=obj.id),
            Event(type=EventType.GRANT_KEYWORD, payload={
                'object_id': obj.id, 'keyword': 'hexproof', 'duration': 'end_of_turn'
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

MORSKA_UNDERSEA_SLEUTH = make_creature(
    name="Morska, Undersea Sleuth",
    power=1, toughness=1,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Merfolk", "Rogue", "Detective"},
    supertypes={"Legendary"},
    text="Skulk. Cloak - When Morska enters the battlefield, she gets +1/+1 and gains hexproof until end of turn. Whenever Morska deals combat damage to a player, investigate.",
    setup_interceptors=morska_setup
)


# --- Regular Blue Creatures ---

FORENSIC_GADGETEER = make_creature(
    name="Forensic Gadgeteer",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Vedalken", "Detective", "Artificer"},
    text="Artifacts you control have '{T}: Add {C}.' When Forensic Gadgeteer enters the battlefield, investigate."
)


def surveillance_monitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice a Clue, scry 1."""
    def clue_sacrifice_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if not sacrificed:
            return False
        return 'Clue' in sacrificed.characteristics.subtypes and sacrificed.controller == source.controller

    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: clue_sacrifice_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=scry_effect(e, s)),
        duration='while_on_battlefield'
    )]

SURVEILLANCE_MONITOR = make_creature(
    name="Surveillance Monitor",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus", "Detective"},
    text="Whenever you sacrifice a Clue, scry 1.",
    setup_interceptors=surveillance_monitor_setup
)


CRIME_NOVELIST = make_creature(
    name="Crime Novelist",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Crime Novelist enters the battlefield, draw a card, then discard a card."
)


INFORMATION_DEALER = make_creature(
    name="Information Dealer",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When Information Dealer enters the battlefield, look at the top three cards of your library. Put one into your hand and the rest on the bottom in any order."
)


def think_tank_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, scry 1."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

THINK_TANK = make_creature(
    name="Think Tank",
    power=0, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish"},
    text="Defender. At the beginning of your upkeep, scry 1.",
    setup_interceptors=think_tank_setup
)


ILLUSION_CONJURER = make_creature(
    name="Illusion Conjurer",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flash. When Illusion Conjurer enters the battlefield, create a 1/1 blue Illusion creature token with 'When this creature becomes the target of a spell, sacrifice it.'"
)


WITNESS_PROTECTION_AGENT = make_creature(
    name="Witness Protection Agent",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Disguise {2}{U}. When this creature is turned face up, return target creature to its owner's hand."
)


PRECINCT_ARCHIVIST = make_creature(
    name="Precinct Archivist",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text="When Precinct Archivist enters the battlefield, investigate twice. Clues you control have '{1}, Sacrifice this artifact: Draw a card' instead."
)


# --- Blue Instants ---

DEDUCE = make_instant(
    name="Deduce",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw a card. Investigate."
)


PROJEKTOR_INSPECTION = make_instant(
    name="Projektor Inspection",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at target player's hand. Investigate."
)


CAUGHT_IN_THE_ACT = make_instant(
    name="Caught in the Act",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Investigate."
)


ESSENCE_DISPERSAL = make_instant(
    name="Essence Dispersal",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. Its controller investigates."
)


# --- Blue Sorceries ---

COLD_CASE = make_sorcery(
    name="Cold Case",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Draw three cards. Investigate."
)


BEHIND_THE_MASK = make_sorcery(
    name="Behind the Mask",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Turn target face-down creature face up. Draw two cards."
)


# =============================================================================
# BLACK CARDS - ORZHOV KILLERS, RAKDOS ASSASSINS
# =============================================================================

def massacre_girl_known_killer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace, wither. Whenever a creature an opponent controls dies, suspect it as it enters the graveyard."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying.controller != source.controller and
                CardType.CREATURE in dying.characteristics.types)

    def drain_effect(event: Event, state: GameState) -> list[Event]:
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
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=drain_effect(e, s)),
        duration='while_on_battlefield'
    )]

MASSACRE_GIRL_KNOWN_KILLER = make_creature(
    name="Massacre Girl, Known Killer",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="Menace, wither. Whenever a creature an opponent controls dies, you gain 1 life.",
    setup_interceptors=massacre_girl_known_killer_setup
)


def etrata_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Whenever Etrata deals combat damage to a player, exile target creature that player controls."""
    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target = event.payload.get('target')
        return target in state.players

    def exile_effect(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        return [Event(
            type=EventType.TARGET_AND_EXILE,
            payload={'controller': obj.controller, 'target_type': 'creature', 'target_controller': target_player},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=exile_effect(e, s)),
        duration='while_on_battlefield'
    )]

ETRATA_DEADLY_FUGITIVE = make_creature(
    name="Etrata, Deadly Fugitive",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Vampire", "Assassin"},
    supertypes={"Legendary"},
    text="Deathtouch, disguise {2}{U}{B}. When Etrata is turned face up, target opponent reveals their hand. You may choose a creature card from it and exile it face down as a Clue.",
    setup_interceptors=etrata_setup
)


def judith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control get +1/+0. Whenever a nontoken creature you control dies, Judith deals 1 damage to any target."""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 0, other_creatures_you_control(obj)))

    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying_id != source.id and
                dying.controller == source.controller and
                CardType.CREATURE in dying.characteristics.types and
                not dying.state.get('is_token', False))

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'any_target', 'amount': 1, 'source': obj.id},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=damage_effect(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors

JUDITH_CARNAGE_CONNOISSEUR = make_creature(
    name="Judith, Carnage Connoisseur",
    power=2, toughness=2,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, choose one - That spell gains deathtouch and lifelink; or create a 2/2 black Rogue creature token.",
    setup_interceptors=judith_setup
)


# --- Regular Black Creatures ---

def hired_knife_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Suspect this creature when it enters."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SUSPECT,
            payload={'object_id': obj.id},
            source=obj.id
        )]
    interceptors = [make_etb_trigger(obj, etb_effect)]
    interceptors.extend(make_suspect_creature(obj))
    return interceptors

HIRED_KNIFE = make_creature(
    name="Hired Knife",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Hired Knife enters the battlefield suspected. (It has menace and can't block.)",
    setup_interceptors=hired_knife_setup
)


DEADLY_GRUDGE = make_creature(
    name="Deadly Grudge",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Deathtouch. When Deadly Grudge dies, each opponent loses 1 life."
)


def undercity_informer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Target opponent reveals their hand. Choose a card from it. That player discards that card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCARD_CHOICE,
            payload={'controller': obj.controller, 'target_type': 'opponent'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

UNDERCITY_INFORMER = make_creature(
    name="Undercity Informer",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Undercity Informer enters the battlefield, target opponent reveals their hand. You choose a nonland card from it. That player discards that card.",
    setup_interceptors=undercity_informer_setup
)


GUILTY_SUSPECT = make_creature(
    name="Guilty Suspect",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Menace. Guilty Suspect can't block. When Guilty Suspect dies, each opponent loses 2 life and you gain 2 life."
)


MURDER_WITNESS = make_creature(
    name="Murder Witness",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Citizen"},
    text="When Murder Witness dies, investigate."
)


CRIME_SCENE_CLEANER = make_creature(
    name="Crime Scene Cleaner",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Crime Scene Cleaner enters the battlefield, exile up to two target cards from graveyards."
)


SHADOW_OPERATIVE = make_creature(
    name="Shadow Operative",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Rogue"},
    text="Deathtouch, lifelink. Disguise {3}{B}."
)


UNDERCITY_EXTORTIONIST = make_creature(
    name="Undercity Extortionist",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Undercity Extortionist enters the battlefield, each opponent discards a card. Investigate."
)


# --- Black Instants ---

MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature."
)


DEADLY_COVER_UP = make_instant(
    name="Deadly Cover-Up",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. Collect evidence 6 - If you do, exile all cards from all opponents' graveyards."
)


INCRIMINATING_EVIDENCE = make_instant(
    name="Incriminating Evidence",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. Investigate."
)


FINAL_JUDGMENT = make_instant(
    name="Final Judgment",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with mana value 3 or less. Investigate."
)


# --- Black Sorceries ---

EXTRACT_CONFESSION = make_sorcery(
    name="Extract Confession",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a creature or planeswalker card from it. That player discards that card."
)


SCENE_OF_THE_CRIME = make_sorcery(
    name="Scene of the Crime",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. Investigate."
)


# =============================================================================
# RED CARDS - RAKDOS CHAOS, GRUUL ENFORCERS
# =============================================================================

def krenko_baron_of_tin_street_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. Whenever Krenko attacks, create X 1/1 red Goblin creature tokens tapped and attacking, where X is the number of Goblins you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        goblin_count = sum(1 for obj_id, o in state.objects.items()
                         if o.controller == obj.controller and
                         CardType.CREATURE in o.characteristics.types and
                         'Goblin' in o.characteristics.subtypes and
                         o.zone == ZoneType.BATTLEFIELD)
        events = []
        for _ in range(goblin_count):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {'name': 'Goblin', 'power': 1, 'toughness': 1, 'colors': {Color.RED}, 'subtypes': {'Goblin'}},
                    'tapped': True,
                    'attacking': True
                },
                source=obj.id
            ))
        return events
    return [make_attack_trigger(obj, attack_effect)]

KRENKO_BARON_TIN_STREET = make_creature(
    name="Krenko, Baron of Tin Street",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    supertypes={"Legendary"},
    text="Haste. Whenever Krenko attacks, create X 1/1 red Goblin creature tokens that are tapped and attacking, where X is the number of Goblins you control.",
    setup_interceptors=krenko_baron_tin_street_setup
)


def anzrag_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Anzrag becomes blocked, untap each creature you control and there is an additional combat phase after this one."""
    def block_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        return event.payload.get('attacker_id') == source.id

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, o in state.objects.items():
            if (o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(type=EventType.UNTAP, payload={'object_id': obj_id}, source=obj.id))
        events.append(Event(type=EventType.ADDITIONAL_COMBAT, payload={}, source=obj.id))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: block_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]

ANZRAG_THE_QUAKE_MOLE = make_creature(
    name="Anzrag, the Quake-Mole",
    power=8, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Mole", "God"},
    supertypes={"Legendary"},
    text="Whenever Anzrag becomes blocked, untap each creature you control. After this phase, there is an additional combat phase.",
    setup_interceptors=anzrag_setup
)


# --- Regular Red Creatures ---

TORCH_RUNNER = make_creature(
    name="Torch Runner",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="Haste. When Torch Runner dies, it deals 1 damage to any target."
)


def evidence_burner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Exile target card from a graveyard. If it was a creature card, Evidence Burner deals 2 damage to each opponent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXILE_FROM_GRAVEYARD,
            payload={'controller': obj.controller, 'damage_if_creature': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

EVIDENCE_BURNER = make_creature(
    name="Evidence Burner",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Shaman"},
    text="When Evidence Burner enters the battlefield, exile target card from a graveyard. If it was a creature card, Evidence Burner deals 2 damage to each opponent.",
    setup_interceptors=evidence_burner_setup
)


VOLATILE_SUSPECT = make_creature(
    name="Volatile Suspect",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample. Volatile Suspect enters the battlefield suspected. When Volatile Suspect dies, it deals 3 damage to each opponent."
)


GOBLIN_ARSONIST = make_creature(
    name="Goblin Arsonist",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="When Goblin Arsonist dies, you may have it deal 1 damage to any target."
)


CHAOS_DEFILER = make_creature(
    name="Chaos Defiler",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Devil"},
    text="Menace. When Chaos Defiler enters the battlefield, it deals 2 damage to any target."
)


RAKDOS_ARSONIST = make_creature(
    name="Rakdos Arsonist",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Devil"},
    text="Whenever Rakdos Arsonist attacks, it deals 1 damage to each opponent."
)


GRUUL_ENFORCER = make_creature(
    name="Gruul Enforcer",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Trample. When Gruul Enforcer enters the battlefield, it fights target creature you don't control."
)


# --- Red Instants ---

SHOCKING_REVEAL = make_instant(
    name="Shocking Reveal",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shocking Reveal deals 2 damage to any target. Investigate."
)


EXPLOSIVE_CLUE = make_instant(
    name="Explosive Clue",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Sacrifice an artifact: Deal 4 damage to any target."
)


BURN_THE_EVIDENCE = make_instant(
    name="Burn the Evidence",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Exile target card from a graveyard. Burn the Evidence deals damage to its owner equal to that card's mana value."
)


# --- Red Sorceries ---

PYRETIC_CHARGE = make_sorcery(
    name="Pyretic Charge",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn."
)


DESTROY_THE_EVIDENCE = make_sorcery(
    name="Destroy the Evidence",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Destroy target land. Investigate twice."
)


# =============================================================================
# GREEN CARDS - SELESNYA TRACKERS, SIMIC ANALYSTS
# =============================================================================

def yarus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Face-down creatures you control have haste. Whenever a face-down creature you control dies, manifest the top card of your library."""
    interceptors = []

    def face_down_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.state.get('face_down', False))

    interceptors.append(make_keyword_grant(obj, ['haste'], face_down_filter))

    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying.controller == source.controller and
                CardType.CREATURE in dying.characteristics.types and
                dying.state.get('face_down', False))

    def manifest_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST, payload={'controller': obj.controller}, source=obj.id)]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=manifest_effect(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors

YARUS_ROAR_OF_THE_WILD = make_creature(
    name="Yarus, Roar of the Wild",
    power=5, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    supertypes={"Legendary"},
    text="Face-down creatures you control have haste. Whenever a face-down creature you control dies, manifest the top card of your library.",
    setup_interceptors=yarus_setup
)


def tolsimir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Wolves and Dogs you control get +1/+1. Whenever a Wolf or Dog enters, it fights target creature an opponent controls."""
    interceptors = []

    def wolf_dog_filter(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        subtypes = target.characteristics.subtypes
        return 'Wolf' in subtypes or 'Dog' in subtypes

    interceptors.extend(make_static_pt_boost(obj, 1, 1, wolf_dog_filter))

    def wolf_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        subtypes = entering.characteristics.subtypes
        return (entering.controller == source.controller and
                ('Wolf' in subtypes or 'Dog' in subtypes))

    def fight_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.FIGHT,
            payload={'attacker': event.payload.get('object_id'), 'target_type': 'opponent_creature'},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: wolf_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=fight_effect(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors

TOLSIMIR_MIDNIGHT_HOWL = make_creature(
    name="Tolsimir, Midnight's Howl",
    power=3, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    supertypes={"Legendary"},
    text="Other Wolves and Dogs you control get +1/+1. Whenever a Wolf or Dog enters the battlefield under your control, it fights up to one target creature you don't control.",
    setup_interceptors=tolsimir_setup
)


# --- Regular Green Creatures ---

def tracker_beast_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance. Whenever Tracker Beast attacks, investigate."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return make_clue_token_creation(obj)
    return [make_attack_trigger(obj, attack_effect)]

TRACKER_BEAST = make_creature(
    name="Tracker Beast",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Vigilance. Whenever Tracker Beast attacks, investigate.",
    setup_interceptors=tracker_beast_setup
)


CASE_SOLVER = make_creature(
    name="Case Solver",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Detective"},
    text="When Case Solver enters the battlefield, put a +1/+1 counter on target creature. Investigate."
)


EVIDENCE_COLLECTOR = make_creature(
    name="Evidence Collector",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Detective"},
    text="When Evidence Collector enters the battlefield, investigate. Sacrifice a Clue: Put a +1/+1 counter on Evidence Collector."
)


WILD_SUSPECT = make_creature(
    name="Wild Suspect",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Wild Suspect enters the battlefield suspected."
)


SELESNYA_EVANGEL = make_creature(
    name="Selesnya Evangel",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Shaman"},
    text="{1}, {T}: Create a 1/1 green Saproling creature token."
)


GARDEN_INVESTIGATOR = make_creature(
    name="Garden Investigator",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Dryad", "Detective"},
    text="Reach. When Garden Investigator enters the battlefield, search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)


FOREST_SCOUT = make_creature(
    name="Forest Scout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Scout"},
    text="When Forest Scout enters the battlefield, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle. Investigate."
)


VERDANT_WITNESS = make_creature(
    name="Verdant Witness",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Vigilance. Whenever Verdant Witness deals combat damage to a player, investigate twice."
)


# --- Green Instants ---

BITE_DOWN = make_instant(
    name="Bite Down",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker you don't control."
)


GIANT_GROWTH = make_instant(
    name="Giant Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn."
)


CLUE_TRAIL = make_instant(
    name="Clue Trail",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Investigate."
)


# --- Green Sorceries ---

INVESTIGATE_THE_SCENE = make_sorcery(
    name="Investigate the Scene",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Create two Clue tokens. You may sacrifice a Clue. If you do, search your library for a creature card, reveal it, put it into your hand, then shuffle."
)


NATURES_WITNESS = make_sorcery(
    name="Nature's Witness",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Return up to two target creature cards from your graveyard to your hand. Investigate."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def rakdos_headliner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. Whenever Rakdos Headliner attacks, each opponent discards a card. Investigate."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.DISCARD,
            payload={'target_type': 'each_opponent'},
            source=obj.id
        )]
        events.extend(make_clue_token_creation(obj))
        return events
    return [make_attack_trigger(obj, attack_effect)]

RAKDOS_HEADLINER = make_creature(
    name="Rakdos Headliner",
    power=3, toughness=3,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Devil", "Performer"},
    text="Haste. Echo {B}{R}. Whenever Rakdos Headliner attacks, each opponent discards a card.",
    setup_interceptors=rakdos_headliner_setup
)


SIMIC_MANIPULATOR = make_creature(
    name="Simic Manipulator",
    power=0, toughness=1,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Mutant", "Wizard"},
    text="Evolve. {T}, Remove two +1/+1 counters from Simic Manipulator: Gain control of target creature with power less than or equal to Simic Manipulator's power."
)


SELESNYA_PEACEKEEPER = make_creature(
    name="Selesnya Peacekeeper",
    power=2, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Soldier"},
    text="Vigilance. When Selesnya Peacekeeper enters the battlefield, create a 1/1 green and white Citizen creature token. Investigate."
)


ORZHOV_EXTORTIONIST = make_creature(
    name="Orzhov Extortionist",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Cleric"},
    text="Extort. When Orzhov Extortionist enters the battlefield, investigate."
)


IZZET_CHEMISTER = make_creature(
    name="Izzet Chemister",
    power=1, toughness=3,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Goblin", "Wizard"},
    text="Haste. {R}, {T}: Exile target instant or sorcery card from your graveyard. You may cast it this turn."
)


GOLGARI_AGENT = make_creature(
    name="Golgari Agent",
    power=2, toughness=3,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="Deathtouch. When Golgari Agent dies, return another target creature card from your graveyard to your hand."
)


BOROS_INVESTIGATOR = make_creature(
    name="Boros Investigator",
    power=3, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier", "Detective"},
    text="Haste. When Boros Investigator enters the battlefield, investigate. Whenever you sacrifice a Clue, Boros Investigator deals 1 damage to any target."
)


DIMIR_INFORMANT = make_creature(
    name="Dimir Informant",
    power=1, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Dimir Informant enters the battlefield, surveil 3. Whenever you surveil, you may pay {1}. If you do, create a Clue token."
)


GRUUL_TRACKER = make_creature(
    name="Gruul Tracker",
    power=4, toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Centaur", "Warrior"},
    text="Trample. When Gruul Tracker enters the battlefield, it fights target creature an opponent controls. Investigate."
)


# =============================================================================
# CASE ENCHANTMENTS
# =============================================================================

def case_of_the_ransacked_lab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this Case enters, investigate. To solve: You control 3+ artifacts. Solved: Draw a card on artifact ETB."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return make_clue_token_creation(obj)

    def artifact_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if not source.state.get('solved', False):
            return False
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.ARTIFACT in entering.characteristics.types)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller}, source=obj.id)]

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: artifact_etb_filter(e, s, obj),
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
            duration='while_on_battlefield'
        )
    ]

CASE_OF_THE_RANSACKED_LAB = make_case_enchantment(
    name="Case of the Ransacked Lab",
    mana_cost="{U}",
    colors={Color.BLUE},
    initial_text="When this Case enters, investigate.",
    solved_condition="You control three or more artifacts.",
    solved_text="Whenever an artifact enters the battlefield under your control, draw a card.",
    setup_interceptors=case_of_the_ransacked_lab_setup
)


def case_of_the_burning_masks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """To solve: Creature dealt 4+ damage this turn. Solved: Creatures you control get +1/+0 and have haste."""
    interceptors = []

    def solved_filter(target: GameObject, state: GameState) -> bool:
        if not obj.state.get('solved', False):
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors.extend(make_static_pt_boost(obj, 1, 0, solved_filter))
    interceptors.append(make_keyword_grant(obj, ['haste'], solved_filter))

    return interceptors

CASE_OF_THE_BURNING_MASKS = make_case_enchantment(
    name="Case of the Burning Masks",
    mana_cost="{R}",
    colors={Color.RED},
    initial_text="(No initial effect)",
    solved_condition="A creature was dealt 4 or more damage this turn.",
    solved_text="Creatures you control get +1/+0 and have haste.",
    setup_interceptors=case_of_the_burning_masks_setup
)


def case_of_the_stashed_skeleton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a 2/1 Skeleton. To solve: A creature died this turn. Solved: You may sacrifice Skeleton to search for a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Skeleton', 'power': 2, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Skeleton'}}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

CASE_OF_THE_STASHED_SKELETON = make_case_enchantment(
    name="Case of the Stashed Skeleton",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    initial_text="When this Case enters, create a 2/1 black Skeleton creature token.",
    solved_condition="A creature died this turn.",
    solved_text="Sacrifice a Skeleton: Search your library for a card, put it into your hand, then shuffle. Activate only as a sorcery.",
    setup_interceptors=case_of_the_stashed_skeleton_setup
)


def case_of_the_trampled_garden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a 2/2 green Badger. To solve: You control 4+ creatures. Solved: Creatures you control get +1/+1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Badger', 'power': 2, 'toughness': 2, 'colors': {Color.GREEN}, 'subtypes': {'Badger'}}
            },
            source=obj.id
        )]

    def solved_filter(target: GameObject, state: GameState) -> bool:
        if not obj.state.get('solved', False):
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    return [make_etb_trigger(obj, etb_effect)] + make_static_pt_boost(obj, 1, 1, solved_filter)

CASE_OF_THE_TRAMPLED_GARDEN = make_case_enchantment(
    name="Case of the Trampled Garden",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    initial_text="When this Case enters, create a 2/2 green Badger creature token.",
    solved_condition="You control four or more creatures.",
    solved_text="Creatures you control get +1/+1.",
    setup_interceptors=case_of_the_trampled_garden_setup
)


def case_of_the_shattered_pact_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """To solve: 5+ mana values in your graveyard. Solved: At upkeep, return a creature from graveyard."""
    def upkeep_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if not source.state.get('solved', False):
            return False
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'upkeep':
            return False
        return state.active_player == source.controller

    def return_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={'controller': obj.controller, 'target_type': 'creature'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: upkeep_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=return_effect(e, s)),
        duration='while_on_battlefield'
    )]

CASE_OF_THE_SHATTERED_PACT = make_case_enchantment(
    name="Case of the Shattered Pact",
    mana_cost="{G}",
    colors={Color.GREEN},
    initial_text="(No initial effect)",
    solved_condition="There are five or more mana values among cards in your graveyard.",
    solved_text="At the beginning of your upkeep, return a creature card from your graveyard to your hand.",
    setup_interceptors=case_of_the_shattered_pact_setup
)


CASE_OF_THE_GATEWAY_EXPRESS = make_case_enchantment(
    name="Case of the Gateway Express",
    mana_cost="{W}",
    colors={Color.WHITE},
    initial_text="When this Case enters, create a 2/2 white Ox creature token.",
    solved_condition="You attacked with three or more creatures this turn.",
    solved_text="Creatures you control get +1/+0."
)


CASE_OF_THE_PILFERED_PROOF = make_case_enchantment(
    name="Case of the Pilfered Proof",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    initial_text="When this Case enters, create a 2/2 blue Homunculus creature token.",
    solved_condition="You have more cards in hand than each opponent.",
    solved_text="At the beginning of your upkeep, draw a card."
)


CASE_OF_THE_FILCHED_FALCON = make_case_enchantment(
    name="Case of the Filched Falcon",
    mana_cost="{U}",
    colors={Color.BLUE},
    initial_text="When this Case enters, surveil 2.",
    solved_condition="A player has no cards in their graveyard.",
    solved_text="{U}{U}, Sacrifice this Case: Draw three cards."
)


# =============================================================================
# ARTIFACTS
# =============================================================================

def magnifying_glass_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap: Add {C}. {4}, T: Investigate."""
    # Basic mana production and investigate ability
    return []

MAGNIFYING_GLASS = make_artifact(
    name="Magnifying Glass",
    mana_cost="{3}",
    text="{T}: Add {C}. {4}, {T}: Investigate.",
    setup_interceptors=magnifying_glass_setup
)


DETECTIVES_SATCHEL = make_artifact(
    name="Detective's Satchel",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1. Whenever equipped creature deals combat damage to a player, investigate. Equip {2}."
)


THINKING_CAP = make_artifact(
    name="Thinking Cap",
    mana_cost="{1}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+0 and has '{T}: Investigate.' Equip {1}."
)


EVIDENCE_LOCKER = make_artifact(
    name="Evidence Locker",
    mana_cost="{2}",
    text="{2}, {T}: Exile target card from a graveyard. If a creature card is exiled this way, investigate."
)


CRIME_SCENE_TAPE = make_artifact(
    name="Crime Scene Tape",
    mana_cost="{1}",
    text="When Crime Scene Tape enters the battlefield, tap target creature an opponent controls. That creature doesn't untap during its controller's untap step for as long as you control Crime Scene Tape."
)


SURVEYORS_SCOPE = make_artifact(
    name="Surveyor's Scope",
    mana_cost="{2}",
    text="{T}: You may put a basic land card from your hand onto the battlefield tapped. Investigate."
)


FORENSIC_KIT = make_artifact(
    name="Forensic Kit",
    mana_cost="{2}",
    text="When Forensic Kit enters the battlefield, investigate. Sacrifice Forensic Kit: Add {C}{C}."
)


AGENCY_INSIGNIA = make_artifact(
    name="Agency Insignia",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1 and is a Detective in addition to its other types. Whenever equipped creature attacks, investigate. Equip {2}."
)


# =============================================================================
# LANDS
# =============================================================================

SCENE_OF_THE_CRIME_LAND = make_land(
    name="Scene of the Crime",
    text="Scene of the Crime enters the battlefield tapped unless you sacrifice a Clue. {T}: Add {W} or {U}."
)


UNDERCITY_SEWERS = make_land(
    name="Undercity Sewers",
    text="When Undercity Sewers enters the battlefield, you may pay 3 life. If you don't, it enters tapped. {T}: Add {U} or {B}. When Undercity Sewers enters the battlefield, surveil 1."
)


COMMERCIAL_DISTRICT = make_land(
    name="Commercial District",
    text="When Commercial District enters the battlefield, you may pay 3 life. If you don't, it enters tapped. {T}: Add {R} or {W}. When Commercial District enters the battlefield, surveil 1."
)


LUSH_PORTICO = make_land(
    name="Lush Portico",
    text="When Lush Portico enters the battlefield, you may pay 3 life. If you don't, it enters tapped. {T}: Add {G} or {W}. When Lush Portico enters the battlefield, surveil 1."
)


RAUCOUS_THEATER = make_land(
    name="Raucous Theater",
    text="When Raucous Theater enters the battlefield, you may pay 3 life. If you don't, it enters tapped. {T}: Add {B} or {R}. When Raucous Theater enters the battlefield, surveil 1."
)


HEDGE_MAZE = make_land(
    name="Hedge Maze",
    text="When Hedge Maze enters the battlefield, you may pay 3 life. If you don't, it enters tapped. {T}: Add {G} or {U}. When Hedge Maze enters the battlefield, surveil 1."
)


METROLINE_STATION = make_land(
    name="Metroline Station",
    text="{T}: Add {C}. {4}, {T}: Draw a card, then discard a card."
)


KARLOV_MANOR = make_land(
    name="Karlov Manor",
    text="{T}: Add {C}. {2}, {T}, Sacrifice Karlov Manor: Investigate."
)


AGENCY_HEADQUARTERS = make_land(
    name="Agency Headquarters",
    text="{T}: Add {C}. {1}, {T}: Target Detective gets +1/+1 until end of turn."
)


# =============================================================================
# ADDITIONAL CREATURES FOR VARIETY
# =============================================================================

VENGEFUL_TOWNSFOLK = make_creature(
    name="Vengeful Townsfolk",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="Whenever another creature you control dies, put a +1/+1 counter on Vengeful Townsfolk."
)


ARCHWAY_INVESTIGATOR = make_creature(
    name="Archway Investigator",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Detective"},
    text="When Archway Investigator enters the battlefield, draw a card."
)


SHADOW_SLAYER = make_creature(
    name="Shadow Slayer",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Assassin"},
    text="Menace. When Shadow Slayer enters the battlefield, target creature gets -2/-2 until end of turn."
)


TUNNELING_SUSPECT = make_creature(
    name="Tunneling Suspect",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Haste. Tunneling Suspect enters the battlefield suspected. When Tunneling Suspect dies, it deals 2 damage to each opponent."
)


OVERGROWN_GUARDIAN = make_creature(
    name="Overgrown Guardian",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Vigilance, trample. When Overgrown Guardian enters the battlefield, investigate."
)


PRECINCT_CAPTAIN = make_creature(
    name="Precinct Captain",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="First strike. Whenever Precinct Captain deals combat damage to a player, create a 1/1 white Soldier creature token."
)


HIDDEN_ASSAILANT = make_creature(
    name="Hidden Assailant",
    power=3, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Disguise {2}{B}. When Hidden Assailant is turned face up, destroy target creature an opponent controls with toughness 2 or less."
)


RECKLESS_DETECTIVE = make_creature(
    name="Reckless Detective",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Detective"},
    text="Haste. When Reckless Detective enters the battlefield, investigate. You may sacrifice a Clue. If you do, Reckless Detective deals 2 damage to any target."
)


GROVE_WARDEN = make_creature(
    name="Grove Warden",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Detective"},
    text="Vigilance. When Grove Warden enters the battlefield, investigate twice. Clue tokens you control have '{T}: Add {G}.'"
)


CLOAK_AND_DAGGER = make_creature(
    name="Cloak and Dagger",
    power=2, toughness=1,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue", "Detective"},
    text="Flash, deathtouch. When Cloak and Dagger enters the battlefield, investigate."
)


# =============================================================================
# MORE SPELLS
# =============================================================================

SUDDEN_INSIGHT = make_instant(
    name="Sudden Insight",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Draw cards equal to the number of different mana values among nonland cards in your graveyard."
)


DEADLY_ACCUSATION = make_instant(
    name="Deadly Accusation",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Collect evidence 6 - If you do, also destroy target planeswalker."
)


CHARGE_OF_THE_MIZZIUM = make_instant(
    name="Charge of the Mizzium",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Charge of the Mizzium deals 4 damage to target creature or planeswalker."
)


TITANIC_GROWTH = make_instant(
    name="Titanic Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn."
)


FINAL_NIGHT = make_sorcery(
    name="Final Night",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Each player sacrifices four creatures."
)


MOB_VERDICT = make_sorcery(
    name="Mob Verdict",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures. You gain 2 life for each creature you controlled that was destroyed this way."
)


INVESTIGATIVE_LEADS = make_sorcery(
    name="Investigative Leads",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Look at the top five cards of your library. Put two of them into your hand and the rest on the bottom in any order. Investigate."
)


BURIED_SECRETS = make_sorcery(
    name="Buried Secrets",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. Investigate."
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

MURDERS_KARLOV_MANOR_CARDS = {
    # White Legendaries
    "Alquist Proft, Master Sleuth": ALQUIST_PROFT_MASTER_SLEUTH,
    "Kaya, Spirits' Justice": KAYA_SPIRITS_JUSTICE,
    "Ezrim, Agency Chief": EZRIM_AGENCY_CHIEF,
    "Aurelia, the Law Above": AURELIA_THE_LAW_ABOVE,

    # White Creatures
    "Agency Outfitter": AGENCY_OUTFITTER,
    "Azorius Arrester": AZORIUS_ARRESTER,
    "Tenth District Guardian": TENTH_DISTRICT_GUARDIAN,
    "Novice Inspector": NOVICE_INSPECTOR,
    "Seasoned Consultant": SEASONED_CONSULTANT,
    "Dedicated Bodyguard": DEDICATED_BODYGUARD,
    "Forensic Researcher": FORENSIC_RESEARCHER,
    "Basilica Stalker": BASILICA_STALKER,
    "Wojek Investigator": WOJEK_INVESTIGATOR,
    "Evidence Examiner": EVIDENCE_EXAMINER,
    "Skyguard Patrol": SKYGUARD_PATROL,
    "Vengeful Townsfolk": VENGEFUL_TOWNSFOLK,
    "Precinct Captain": PRECINCT_CAPTAIN,

    # White Spells
    "Make Your Move": MAKE_YOUR_MOVE,
    "Eliminate the Impossible": ELIMINATE_THE_IMPOSSIBLE,
    "Not on My Watch": NOT_ON_MY_WATCH,
    "Case the Joint": CASE_THE_JOINT,
    "Protect the Scene": PROTECT_THE_SCENE,
    "Mandate of Peace": MANDATE_OF_PEACE,
    "Gather Clues": GATHER_CLUES,
    "Mob Verdict": MOB_VERDICT,

    # Blue Legendaries
    "Teysa, Opulent Oligarch": TEYSA_OPULENT_OLIGARCH,
    "Kellan, Inquisitive Prodigy": KELLAN_INQUISITIVE_PRODIGY,
    "Lavinia, Azorius Renegade": LAVINIA_AZORIUS_RENEGADE,
    "Morska, Undersea Sleuth": MORSKA_UNDERSEA_SLEUTH,

    # Blue Creatures
    "Forensic Gadgeteer": FORENSIC_GADGETEER,
    "Surveillance Monitor": SURVEILLANCE_MONITOR,
    "Crime Novelist": CRIME_NOVELIST,
    "Information Dealer": INFORMATION_DEALER,
    "Think Tank": THINK_TANK,
    "Illusion Conjurer": ILLUSION_CONJURER,
    "Witness Protection Agent": WITNESS_PROTECTION_AGENT,
    "Precinct Archivist": PRECINCT_ARCHIVIST,
    "Archway Investigator": ARCHWAY_INVESTIGATOR,

    # Blue Spells
    "Deduce": DEDUCE,
    "Projektor Inspection": PROJEKTOR_INSPECTION,
    "Caught in the Act": CAUGHT_IN_THE_ACT,
    "Essence Dispersal": ESSENCE_DISPERSAL,
    "Cold Case": COLD_CASE,
    "Behind the Mask": BEHIND_THE_MASK,
    "Sudden Insight": SUDDEN_INSIGHT,
    "Investigative Leads": INVESTIGATIVE_LEADS,

    # Black Legendaries
    "Massacre Girl, Known Killer": MASSACRE_GIRL_KNOWN_KILLER,
    "Etrata, Deadly Fugitive": ETRATA_DEADLY_FUGITIVE,
    "Judith, Carnage Connoisseur": JUDITH_CARNAGE_CONNOISSEUR,

    # Black Creatures
    "Hired Knife": HIRED_KNIFE,
    "Deadly Grudge": DEADLY_GRUDGE,
    "Undercity Informer": UNDERCITY_INFORMER,
    "Guilty Suspect": GUILTY_SUSPECT,
    "Murder Witness": MURDER_WITNESS,
    "Crime Scene Cleaner": CRIME_SCENE_CLEANER,
    "Shadow Operative": SHADOW_OPERATIVE,
    "Undercity Extortionist": UNDERCITY_EXTORTIONIST,
    "Shadow Slayer": SHADOW_SLAYER,
    "Hidden Assailant": HIDDEN_ASSAILANT,

    # Black Spells
    "Murder": MURDER,
    "Deadly Cover-Up": DEADLY_COVER_UP,
    "Incriminating Evidence": INCRIMINATING_EVIDENCE,
    "Final Judgment": FINAL_JUDGMENT,
    "Extract Confession": EXTRACT_CONFESSION,
    "Scene of the Crime": SCENE_OF_THE_CRIME,
    "Deadly Accusation": DEADLY_ACCUSATION,
    "Final Night": FINAL_NIGHT,
    "Buried Secrets": BURIED_SECRETS,

    # Red Legendaries
    "Krenko, Baron of Tin Street": KRENKO_BARON_TIN_STREET,
    "Anzrag, the Quake-Mole": ANZRAG_THE_QUAKE_MOLE,

    # Red Creatures
    "Torch Runner": TORCH_RUNNER,
    "Evidence Burner": EVIDENCE_BURNER,
    "Volatile Suspect": VOLATILE_SUSPECT,
    "Goblin Arsonist": GOBLIN_ARSONIST,
    "Chaos Defiler": CHAOS_DEFILER,
    "Rakdos Arsonist": RAKDOS_ARSONIST,
    "Gruul Enforcer": GRUUL_ENFORCER,
    "Tunneling Suspect": TUNNELING_SUSPECT,
    "Reckless Detective": RECKLESS_DETECTIVE,

    # Red Spells
    "Shocking Reveal": SHOCKING_REVEAL,
    "Explosive Clue": EXPLOSIVE_CLUE,
    "Burn the Evidence": BURN_THE_EVIDENCE,
    "Pyretic Charge": PYRETIC_CHARGE,
    "Destroy the Evidence": DESTROY_THE_EVIDENCE,
    "Charge of the Mizzium": CHARGE_OF_THE_MIZZIUM,

    # Green Legendaries
    "Yarus, Roar of the Wild": YARUS_ROAR_OF_THE_WILD,
    "Tolsimir, Midnight's Howl": TOLSIMIR_MIDNIGHT_HOWL,

    # Green Creatures
    "Tracker Beast": TRACKER_BEAST,
    "Case Solver": CASE_SOLVER,
    "Evidence Collector": EVIDENCE_COLLECTOR,
    "Wild Suspect": WILD_SUSPECT,
    "Selesnya Evangel": SELESNYA_EVANGEL,
    "Garden Investigator": GARDEN_INVESTIGATOR,
    "Forest Scout": FOREST_SCOUT,
    "Verdant Witness": VERDANT_WITNESS,
    "Overgrown Guardian": OVERGROWN_GUARDIAN,
    "Grove Warden": GROVE_WARDEN,

    # Green Spells
    "Bite Down": BITE_DOWN,
    "Giant Growth": GIANT_GROWTH,
    "Clue Trail": CLUE_TRAIL,
    "Investigate the Scene": INVESTIGATE_THE_SCENE,
    "Nature's Witness": NATURES_WITNESS,
    "Titanic Growth": TITANIC_GROWTH,

    # Multicolor Creatures
    "Rakdos Headliner": RAKDOS_HEADLINER,
    "Simic Manipulator": SIMIC_MANIPULATOR,
    "Selesnya Peacekeeper": SELESNYA_PEACEKEEPER,
    "Orzhov Extortionist": ORZHOV_EXTORTIONIST,
    "Izzet Chemister": IZZET_CHEMISTER,
    "Golgari Agent": GOLGARI_AGENT,
    "Boros Investigator": BOROS_INVESTIGATOR,
    "Dimir Informant": DIMIR_INFORMANT,
    "Gruul Tracker": GRUUL_TRACKER,
    "Cloak and Dagger": CLOAK_AND_DAGGER,

    # Case Enchantments
    "Case of the Ransacked Lab": CASE_OF_THE_RANSACKED_LAB,
    "Case of the Burning Masks": CASE_OF_THE_BURNING_MASKS,
    "Case of the Stashed Skeleton": CASE_OF_THE_STASHED_SKELETON,
    "Case of the Trampled Garden": CASE_OF_THE_TRAMPLED_GARDEN,
    "Case of the Shattered Pact": CASE_OF_THE_SHATTERED_PACT,
    "Case of the Gateway Express": CASE_OF_THE_GATEWAY_EXPRESS,
    "Case of the Pilfered Proof": CASE_OF_THE_PILFERED_PROOF,
    "Case of the Filched Falcon": CASE_OF_THE_FILCHED_FALCON,

    # Artifacts
    "Magnifying Glass": MAGNIFYING_GLASS,
    "Detective's Satchel": DETECTIVES_SATCHEL,
    "Thinking Cap": THINKING_CAP,
    "Evidence Locker": EVIDENCE_LOCKER,
    "Crime Scene Tape": CRIME_SCENE_TAPE,
    "Surveyor's Scope": SURVEYORS_SCOPE,
    "Forensic Kit": FORENSIC_KIT,
    "Agency Insignia": AGENCY_INSIGNIA,

    # Lands
    "Scene of the Crime (Land)": SCENE_OF_THE_CRIME_LAND,
    "Undercity Sewers": UNDERCITY_SEWERS,
    "Commercial District": COMMERCIAL_DISTRICT,
    "Lush Portico": LUSH_PORTICO,
    "Raucous Theater": RAUCOUS_THEATER,
    "Hedge Maze": HEDGE_MAZE,
    "Metroline Station": METROLINE_STATION,
    "Karlov Manor": KARLOV_MANOR,
    "Agency Headquarters": AGENCY_HEADQUARTERS,
}
