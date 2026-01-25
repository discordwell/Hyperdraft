"""
My Hero Academia: Heroes Rising (MHA) Card Implementations

Set released 2026. ~250 cards.
Features mechanics: Quirk, Plus Ultra, Villain
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from src.engine.abilities import (
    TriggeredAbility, StaticAbility,
    ETBTrigger, DeathTrigger, AttackTrigger, UpkeepTrigger,
    DealsDamageTrigger,
    GainLife, DrawCards, DealDamage, AddCounters, LoseLife,
    PTBoost, KeywordGrant,
    OtherCreaturesYouControlFilter, CreaturesYouControlFilter,
    CreaturesWithSubtypeFilter, SelfTarget, AnotherCreature,
    EachOpponentTarget, ControllerTarget,
)
from typing import Optional, Callable


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
# MY HERO ACADEMIA KEYWORD MECHANICS
# =============================================================================

def make_quirk_ability(source_obj: GameObject, tap_cost: bool, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Quirk - Activated ability unique to each hero.
    If tap_cost is True, requires tapping to activate.
    """
    def quirk_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'quirk')

    def quirk_handler(event: Event, state: GameState) -> InterceptorResult:
        events = []
        if tap_cost:
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': source_obj.id},
                source=source_obj.id
            ))
        events.extend(effect_fn(event, state))
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=quirk_filter,
        handler=quirk_handler,
        duration='while_on_battlefield'
    )


def make_plus_ultra_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int, threshold: int = 5) -> list[Interceptor]:
    """
    Plus Ultra - This creature gets +X/+Y as long as you have N or less life.
    Default threshold is 5 life.
    """
    def plus_ultra_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        player = state.players.get(source_obj.controller)
        return player and player.life <= threshold

    # Use the old helper since this is a conditional static ability
    from src.cards.interceptor_helpers import make_static_pt_boost
    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, plus_ultra_filter)


def make_villain_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Villain - Triggers whenever an opponent loses life.
    """
    def villain_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount >= 0:
            return False
        # Check if it's an opponent losing life
        return event.payload.get('player') != source_obj.controller

    def villain_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=villain_filter,
        handler=villain_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# WHITE CARDS - HEROES, SYMBOL OF PEACE, RESCUE
# =============================================================================

# --- Legendary Creatures ---

ALL_MIGHT = make_creature(
    name="All Might, Symbol of Peace",
    power=6, toughness=6,
    mana_cost="{3}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 2),
            filter=CreaturesWithSubtypeFilter("Hero", include_self=False)
        ),
        # Plus Ultra handled via setup_interceptors since it's conditional on life total
    ],
    setup_interceptors=lambda obj, state: make_plus_ultra_bonus(obj, 3, 3)
)


ENDEAVOR = make_creature(
    name="Endeavor, Number One Hero",
    power=5, toughness=4,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=DealDamage(2, target=EachOpponentTarget())
        ),
    ]
)


def hawks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Heroes have flying"""
    from src.cards.interceptor_helpers import make_keyword_grant, other_creatures_with_subtype
    return [make_keyword_grant(obj, ['flying'], other_creatures_with_subtype(obj, "Hero"))]

HAWKS = make_creature(
    name="Hawks, Number Two Hero",
    power=3, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(['flying']),
            filter=CreaturesWithSubtypeFilter("Hero", include_self=False)
        ),
    ]
)


def eraserhead_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures opponents control lose all abilities"""
    def disable_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return disable_filter(target, state)

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['granted'] = []  # Remove all abilities
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )]

ERASERHEAD = make_creature(
    name="Eraserhead, Underground Hero",
    power=2, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Complex ability - keep setup_interceptors
    setup_interceptors=eraserhead_setup
)


def best_jeanist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures opponents control enter tapped"""
    from src.cards.interceptor_helpers import make_etb_trigger

    def etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller != obj.controller and
                CardType.CREATURE in entering.characteristics.types)

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        return [Event(
            type=EventType.TAP,
            payload={'object_id': entering_id},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect, etb_filter)]

BEST_JEANIST = make_creature(
    name="Best Jeanist, Fiber Master",
    power=2, toughness=5,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Complex ability - keep setup_interceptors
    setup_interceptors=best_jeanist_setup
)


def mirko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike when attacking alone"""
    from src.cards.interceptor_helpers import make_keyword_grant

    def attack_alone_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        # Check if attacking alone (simplified - would need combat state)
        return target.zone == ZoneType.BATTLEFIELD
    return [make_keyword_grant(obj, ['double_strike'], attack_alone_filter)]

MIRKO = make_creature(
    name="Mirko, Rabbit Hero",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Conditional keyword - keep setup
    setup_interceptors=mirko_setup
)


# --- Regular Creatures ---

RESCUE_HERO = make_creature(
    name="Rescue Hero",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(3)
        ),
    ]
)


SIDEKICK = make_creature(
    name="Eager Sidekick",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    # Dynamic P/T based on hero count - needs special handling
)


UA_TEACHER = make_creature(
    name="UA Teacher",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Student", include_self=False)
        ),
    ]
)


POLICE_OFFICER = make_creature(
    name="Hero Public Safety Officer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    # ETB detain - would need targeting, keep text only for now
)


RESCUE_SQUAD = make_creature(
    name="Rescue Squad",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    # ETB gain life for each creature - would need creature counting
)


SUPPORT_COURSE_STUDENT = make_creature(
    name="Support Course Student",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Student", "Artificer"},
    # ETB create equipment token - complex
)


HERO_INTERN = make_creature(
    name="Hero Intern",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Student"},
    # Lifelink - keyword ability
)


NIGHTEYE_AGENCY_MEMBER = make_creature(
    name="Nighteye Agency Member",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    # ETB scry 2 - would need scry effect
)


SELKIE = make_creature(
    name="Selkie, Water Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Hexproof, can't be blocked by power 2 or less - keywords/evasion
)


GANG_ORCA = make_creature(
    name="Gang Orca, Whale Hero",
    power=5, toughness=5,
    mana_cost="{3}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Menace, ETB destroy - would need targeting
)


THIRTEEN = make_creature(
    name="Thirteen, Rescue Hero",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Defender, Quirk activated ability
)


MIDNIGHT = make_creature(
    name="Midnight, R-Rated Hero",
    power=3, toughness=2,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Quirk activated ability
)


PRESENT_MIC = make_creature(
    name="Present Mic, Voice Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Haste, Quirk activated ability
)


CEMENTOSS = make_creature(
    name="Cementoss, Concrete Hero",
    power=1, toughness=6,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Defender, Quirk creates tokens
)


SNIPE = make_creature(
    name="Snipe, Shooting Hero",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Reach, Quirk deals damage
)


# --- Instants ---

PLUS_ULTRA_SMASH = make_instant(
    name="Plus Ultra Smash",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +3/+3 until end of turn. If you have 5 or less life, it also gains indestructible until end of turn."
)


HEROIC_RESCUE = make_instant(
    name="Heroic Rescue",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains protection from the color of your choice until end of turn."
)


SYMBOL_OF_PEACE = make_instant(
    name="Symbol of Peace",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+2 and gain vigilance until end of turn."
)


FEAR_NOT = make_instant(
    name="Fear Not",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. You gain 2 life."
)


EMERGENCY_EVACUATION = make_instant(
    name="Emergency Evacuation",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return all creatures to their owners' hands."
)


UNITED_STATES_OF_SMASH = make_instant(
    name="United States of Smash",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy target creature. You gain life equal to its power."
)


HERO_ARRIVAL = make_instant(
    name="Hero Arrival",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Create two 1/1 white Human Hero creature tokens. They gain haste until end of turn."
)


QUIRK_SUPPRESSION = make_instant(
    name="Quirk Suppression",
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Counter target activated ability. Draw a card."
)


# --- Sorceries ---

HERO_RECRUITMENT = make_sorcery(
    name="Hero Recruitment",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Search your library for a Hero creature card, reveal it, put it into your hand, then shuffle."
)


PEACE_SUMMIT = make_sorcery(
    name="Peace Summit",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Each player gains 5 life. Creatures can't attack until your next turn."
)


UA_TRAINING_SESSION = make_sorcery(
    name="UA Training Session",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on each creature you control."
)


# --- Enchantments ---

SYMBOL_OF_HOPE = make_enchantment(
    name="Symbol of Hope",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(['vigilance', 'lifelink']),
            filter=CreaturesWithSubtypeFilter("Hero")
        ),
    ]
)


HERO_LICENSE = make_enchantment(
    name="Hero License",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchanted creature gets +1/+1 and has 'Whenever this creature deals combat damage to a player, you gain 2 life.'"
)


PROVISIONAL_LICENSE = make_enchantment(
    name="Provisional License",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchanted creature gets +1/+0 and has vigilance."
)


# =============================================================================
# BLUE CARDS - STRATEGY QUIRKS, INTELLIGENCE
# =============================================================================

# --- Legendary Creatures ---

NEZU = make_creature(
    name="Nezu, UA Principal",
    power=1, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Mouse", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=DrawCards(1)
        ),
    ]
)


SIR_NIGHTEYE = make_creature(
    name="Sir Nighteye, Foresight Hero",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(1)  # Simplified from look at 3, put 1 in hand
        ),
    ]
)


SHINSO = make_creature(
    name="Shinso, Mind Control",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    # Can't be blocked by power 3+, Quirk - complex
)


def mandalay_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Heroes have hexproof"""
    from src.cards.interceptor_helpers import make_keyword_grant

    def telepathy_filter(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                "Hero" in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['hexproof'], telepathy_filter)]

MANDALAY = make_creature(
    name="Mandalay, Wild Wild Pussycats",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(['hexproof']),
            filter=CreaturesWithSubtypeFilter("Hero", include_self=False)
        ),
    ]
)


RAGDOLL = make_creature(
    name="Ragdoll, Wild Wild Pussycats",
    power=2, toughness=2,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Quirk - search library
)


TIGER = make_creature(
    name="Tiger, Wild Wild Pussycats",
    power=3, toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Trample, Quirk activated
)


# --- Regular Creatures ---

ANALYST_HERO = make_creature(
    name="Analyst Hero",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    # ETB scry 2
)


INFORMATION_BROKER = make_creature(
    name="Hero Information Broker",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    # Activated ability - look at top card
)


UA_ROBOT = make_creature(
    name="UA Training Robot",
    power=3, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=DrawCards(1)
        ),
    ]
)


ERASURE_AGENT = make_creature(
    name="Erasure Agent",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    # Flash, ETB counter activated ability
)


TACTICAL_SUPPORT = make_creature(
    name="Tactical Support Hero",
    power=1, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    # Flying, spell cast trigger scry
)


STRATEGY_STUDENT = make_creature(
    name="Strategy Student",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    # ETB draw then discard - loot
)


HATSUME_MEI = make_creature(
    name="Hatsume Mei, Inventor",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student", "Artificer"},
    supertypes={"Legendary"},
    # ETB create artifact tokens
)


POWER_LOADER = make_creature(
    name="Power Loader, Support Teacher",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero", "Artificer"},
    supertypes={"Legendary"},
    # Artifacts have hexproof, Quirk untap
)


# --- Instants ---

TACTICAL_ANALYSIS = make_instant(
    name="Tactical Analysis",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 2, then draw a card."
)


COUNTER_STRATEGY = make_instant(
    name="Counter Strategy",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}."
)


QUIRK_ANALYSIS = make_instant(
    name="Quirk Analysis",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards, then discard a card."
)


BRAINWASH = make_instant(
    name="Brainwash",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Gain control of target creature until end of turn. Untap it. It gains haste until end of turn."
)


FORESIGHT = make_instant(
    name="Foresight",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at the top five cards of your library. Put one into your hand and the rest on the bottom in any order."
)


MIND_TRICK = make_instant(
    name="Mind Trick",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature's controller puts it on the top or bottom of their library."
)


TELEPATHIC_LINK = make_instant(
    name="Telepathic Link",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target player reveals their hand. You draw a card."
)


# --- Sorceries ---

INFORMATION_GATHERING = make_sorcery(
    name="Information Gathering",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards."
)


STRATEGIC_PLANNING = make_sorcery(
    name="Strategic Planning",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library. Put one into your hand and the rest into your graveyard."
)


HERO_ANALYSIS = make_sorcery(
    name="Hero Analysis",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 3."
)


# --- Enchantments ---

QUIRK_RESEARCH = make_enchantment(
    name="Quirk Research",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1. Whenever you scry, draw a card. Activate only once each turn."
)


BATTLE_STRATEGY = make_enchantment(
    name="Battle Strategy",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesYouControlFilter()
        ),
    ]
)


# =============================================================================
# BLACK CARDS - VILLAINS, LEAGUE OF VILLAINS, ALL FOR ONE
# =============================================================================

# --- Legendary Creatures ---

def all_for_one_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Villain trigger - steal abilities"""
    def villain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_villain_trigger(obj, villain_effect)]

ALL_FOR_ONE = make_creature(
    name="All For One, Ultimate Villain",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Indestructible, Villain trigger, Quirk - complex
    setup_interceptors=all_for_one_setup
)


def shigaraki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage, destroy target permanent"""
    from src.cards.interceptor_helpers import make_damage_trigger

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DESTROY,
            payload={'target': 'any_permanent'},  # Would need targeting
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

SHIGARAKI = make_creature(
    name="Shigaraki, Decay Lord",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(to_player=True, combat_only=True),
            effect=LoseLife(0)  # Placeholder - destroy effect needs targeting
        ),
    ],
    setup_interceptors=shigaraki_setup
)


def dabi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - deal 1 damage to self and each opponent"""
    from src.cards.interceptor_helpers import make_upkeep_trigger, all_opponents

    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': obj.controller, 'amount': 1, 'source': obj.id},
            source=obj.id
        ))
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 2, 'source': obj.id},
                source=obj.id
            ))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

DABI = make_creature(
    name="Dabi, Cremation",
    power=4, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Complex upkeep trigger with multiple targets
    setup_interceptors=dabi_setup
)


def toga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage to player, copy target creature"""
    from src.cards.interceptor_helpers import make_damage_trigger

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'copy_target': True},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

TOGA = make_creature(
    name="Toga, Blood Obsession",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Deathtouch, complex damage trigger with copy
    setup_interceptors=toga_setup
)


STAIN = make_creature(
    name="Stain, Hero Killer",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # First strike, deathtouch, conditional double strike
)


OVERHAUL = make_creature(
    name="Overhaul, Yakuza Boss",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # ETB destroy then return from graveyard - complex
)


TWICE = make_creature(
    name="Twice, Double Trouble",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # ETB create copy token - complex
)


MR_COMPRESS = make_creature(
    name="Mr. Compress, Showman",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Quirk exile then return
)


KUROGIRI = make_creature(
    name="Kurogiri, Warp Gate",
    power=1, toughness=4,
    mana_cost="{1}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Elemental", "Villain"},
    supertypes={"Legendary"},
    # Flash, Quirk flicker
)


MUSCULAR = make_creature(
    name="Muscular, Villain",
    power=6, toughness=4,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Trample, haste, must attack
)


MOONFISH = make_creature(
    name="Moonfish, Blade Villain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # First strike, destroy on combat damage
)


GIGANTOMACHIA = make_creature(
    name="Gigantomachia, Living Disaster",
    power=12, toughness=12,
    mana_cost="{8}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Giant", "Villain"},
    supertypes={"Legendary"},
    # Trample, vigilance, evasion, ETB destroy all
)


# --- Regular Creatures ---

def league_grunt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Villain - draw card when opponent loses life"""
    def villain_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Simplified
    return [make_villain_trigger(obj, villain_effect)]

LEAGUE_GRUNT = make_creature(
    name="League of Villains Grunt",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    setup_interceptors=league_grunt_setup
)


NOMU = make_creature(
    name="Nomu, Bioengineered",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Villain"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=LoseLife(2, target=EachOpponentTarget())
        ),
    ]
)


HIGH_END_NOMU = make_creature(
    name="High-End Nomu",
    power=7, toughness=6,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Villain"},
    # Flying, trample, regenerate, ETB fight
)


YAKUZA_THUG = make_creature(
    name="Shie Hassaikai Thug",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    # Death trigger discard
)


TRIGGER_DEALER = make_creature(
    name="Trigger Dealer",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    # Activated ability - pay life, pump
)


META_LIBERATION_SOLDIER = make_creature(
    name="Meta Liberation Soldier",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=DrawCards(1)
        ),
    ]
)


SKEPTIC = make_creature(
    name="Skeptic, Liberation Lieutenant",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesWithSubtypeFilter("Villain", include_self=False)
        ),
    ]
)


TRUMPET = make_creature(
    name="Trumpet, Liberation Commander",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Villain", include_self=False)
        ),
        StaticAbility(
            effect=KeywordGrant(['deathtouch']),
            filter=CreaturesWithSubtypeFilter("Villain", include_self=False)
        ),
    ]
)


RE_DESTRO = make_creature(
    name="Re-Destro, Liberation Leader",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Menace, dynamic P/T based on life lost, Quirk
)


CURIOUS = make_creature(
    name="Curious, Information Master",
    power=2, toughness=2,
    mana_cost="{1}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # ETB reveal hand, choose discard
)


GETEN = make_creature(
    name="Geten, Ice Villain",
    power=3, toughness=4,
    mana_cost="{2}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Flying, Quirk tap and freeze
)


# --- Instants ---

DECAY_TOUCH = make_instant(
    name="Decay Touch",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with toughness 3 or less."
)


VILLAIN_AMBUSH = make_instant(
    name="Villain Ambush",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target tapped creature."
)


BLOOD_DRAIN = make_instant(
    name="Blood Drain",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. You gain 2 life."
)


DARK_REUNION = make_instant(
    name="Dark Reunion",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield."
)


QUIRK_ERASURE = make_instant(
    name="Quirk Erasure",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature loses all abilities until end of turn."
)


ASSASSINATION = make_instant(
    name="Villain Assassination",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses life equal to its power."
)


# --- Sorceries ---

WARP_GATE = make_sorcery(
    name="Warp Gate",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to your hand. Each opponent loses 2 life."
)


VILLAIN_RECRUITMENT = make_sorcery(
    name="Villain Recruitment",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Search your library for a Villain creature card, reveal it, put it into your hand, then shuffle. Each opponent loses 2 life."
)


LIBERATION_MARCH = make_sorcery(
    name="Liberation March",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Create three 2/1 black Human Villain creature tokens with menace."
)


DECAY_WAVE = make_sorcery(
    name="Decay Wave",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. You lose 1 life for each creature destroyed this way."
)


# --- Enchantments ---

LEAGUE_HIDEOUT = make_enchantment(
    name="League Hideout",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Villain")
        ),
    ]
)


TRIGGER_DRUG = make_enchantment(
    name="Trigger Drug",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchanted creature gets +3/+1. At the beginning of your upkeep, it deals 1 damage to you."
)


QUIRK_SINGULARITY = make_enchantment(
    name="Quirk Singularity",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of each opponent's upkeep, that player loses 1 life for each Villain you control."
)


# =============================================================================
# RED CARDS - BAKUGO, POWER QUIRKS, AGGRESSION
# =============================================================================

# --- Legendary Creatures ---

def bakugo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, deal 1 damage to each creature defending player controls"""
    from src.cards.interceptor_helpers import make_attack_trigger

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o in state.objects.values():
            if (o.controller != obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types):
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': o.id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events
    interceptors = [make_attack_trigger(obj, attack_effect)]
    interceptors.extend(make_plus_ultra_bonus(obj, 2, 2))
    return interceptors

BAKUGO = make_creature(
    name="Bakugo, Explosion Hero",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Complex attack trigger + Plus Ultra
    setup_interceptors=bakugo_setup
)


def kirishima_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Indestructible while attacking"""
    from src.cards.interceptor_helpers import make_keyword_grant

    def attacking_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id and target.zone == ZoneType.BATTLEFIELD
    return [make_keyword_grant(obj, ['indestructible'], attacking_filter)]

KIRISHIMA = make_creature(
    name="Kirishima, Red Riot",
    power=3, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Conditional indestructible
    setup_interceptors=kirishima_setup
)


KAMINARI = make_creature(
    name="Kaminari, Chargebolt",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Haste, Quirk deals damage to target and self
)


TETSUTETSU = make_creature(
    name="Tetsutetsu, Real Steel",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Trample, Quirk indestructible
)


MINA = make_creature(
    name="Mina Ashido, Pinky",
    power=2, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # First strike, Quirk can't block
)


FATGUM = make_creature(
    name="Fat Gum, BMI Hero",
    power=2, toughness=7,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Defender, Quirk damage conversion
)


RYUKYU = make_creature(
    name="Ryukyu, Dragon Hero",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero", "Dragon"},
    supertypes={"Legendary"},
    # Flying, trample, Quirk pump
)


CRIMSON_RIOT = make_creature(
    name="Crimson Riot, Legendary Hero",
    power=4, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=PTBoost(1, 0)  # Simplified - would affect other attackers
        ),
    ]
)


# --- Regular Creatures ---

EXPLOSION_STUDENT = make_creature(
    name="Explosion Student",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DealDamage(1, target=EachOpponentTarget())
        ),
    ]
)


COMBAT_HERO = make_creature(
    name="Combat Hero",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    # First strike, haste - keywords
)


POWER_TYPE_STUDENT = make_creature(
    name="Power-Type Student",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    # Trample, activated pump
)


RAGING_HERO = make_creature(
    name="Raging Hero",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    # Trample, haste, must attack
)


FIERY_SIDEKICK = make_creature(
    name="Fiery Sidekick",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    # Haste
)


BATTLE_STUDENT = make_creature(
    name="Battle Course Student",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    # First strike
)


BERSERKER_HERO = make_creature(
    name="Berserker Hero",
    power=5, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    # Trample, combat damage to player damages you
)


# --- Instants ---

EXPLOSION = make_instant(
    name="Explosion",
    mana_cost="{R}",
    colors={Color.RED},
    text="Explosion deals 3 damage to target creature or planeswalker."
)


AP_SHOT = make_instant(
    name="AP Shot",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="AP Shot deals 4 damage to target creature."
)


HOWITZER_IMPACT = make_instant(
    name="Howitzer Impact",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Howitzer Impact deals 5 damage to any target."
)


STUN_GRENADE = make_instant(
    name="Stun Grenade",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Stun Grenade deals 2 damage to each creature. Those creatures can't block this turn."
)


BATTLE_FURY = make_instant(
    name="Battle Fury",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn."
)


PLUS_ULTRA_RUSH = make_instant(
    name="Plus Ultra Rush",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+1 and gains haste until end of turn. If you have 5 or less life, it also gains double strike until end of turn."
)


HELLFIRE = make_instant(
    name="Hellfire Storm",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Hellfire Storm deals 4 damage to each creature and each player."
)


CREMATION = make_instant(
    name="Cremation",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Destroy target artifact or land. Cremation deals 2 damage to that permanent's controller."
)


# --- Sorceries ---

EXPLOSIVE_RAMPAGE = make_sorcery(
    name="Explosive Rampage",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Explosive Rampage deals 2 damage to each creature your opponents control."
)


TOTAL_DESTRUCTION = make_sorcery(
    name="Total Destruction",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Destroy all artifacts and lands. Total Destruction deals 2 damage to each player."
)


GROUND_ZERO = make_sorcery(
    name="Ground Zero",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Ground Zero deals X damage to each creature."
)


# --- Enchantments ---

FIGHTING_SPIRIT = make_enchantment(
    name="Fighting Spirit",
    mana_cost="{1}{R}",
    colors={Color.RED},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesYouControlFilter()
        ),
        StaticAbility(
            effect=KeywordGrant(['haste']),
            filter=CreaturesYouControlFilter()
        ),
    ]
)


UNBREAKABLE_WILL = make_enchantment(
    name="Unbreakable Will",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever a creature you control attacks, it gets +2/+0 until end of turn."
)


EXPLOSIVE_POWER = make_enchantment(
    name="Explosive Power",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchanted creature gets +2/+0. Whenever enchanted creature attacks, it deals 1 damage to defending player."
)


# =============================================================================
# GREEN CARDS - DEKU, GROWTH, ONE FOR ALL
# =============================================================================

# --- Legendary Creatures ---

def deku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """One For All - gets bigger each turn, Plus Ultra bonus"""
    from src.cards.interceptor_helpers import make_upkeep_trigger

    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    interceptors = [make_upkeep_trigger(obj, upkeep_effect)]
    interceptors.extend(make_plus_ultra_bonus(obj, 3, 3))
    return interceptors

DEKU = make_creature(
    name="Deku, Inheritor of One For All",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=AddCounters("+1/+1", 1)
        ),
    ],
    setup_interceptors=lambda obj, state: make_plus_ultra_bonus(obj, 3, 3)
)


URARAKA = make_creature(
    name="Uraraka, Zero Gravity",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Flying, Quirk grants flying
)


IIDA = make_creature(
    name="Iida, Ingenium",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Haste, vigilance, conditional first strike
)


TODOROKI = make_creature(
    name="Todoroki, Half-Cold Half-Hot",
    power=4, toughness=4,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Multiple Quirk activated abilities
)


TSUYU = make_creature(
    name="Tsuyu, Froppy",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Flash, hexproof, evasion, Quirk bounce
)


MOMO = make_creature(
    name="Momo, Creation Hero",
    power=2, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # ETB create equipment, Quirk copy equipment
)


def tokoyami_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Shadow - gets stronger at low life"""
    return make_plus_ultra_bonus(obj, 4, 0)

TOKOYAMI = make_creature(
    name="Tokoyami, Dark Shadow",
    power=3, toughness=3,
    mana_cost="{2}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Flying, Plus Ultra, Quirk menace
    setup_interceptors=tokoyami_setup
)


SERO = make_creature(
    name="Sero, Cellophane",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Reach, Quirk tap
)


SHOJI = make_creature(
    name="Shoji, Tentacole",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Vigilance, can block additional creature
)


KODA = make_creature(
    name="Koda, Anima",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Quirk creates bird token
)


OJIRO = make_creature(
    name="Ojiro, Tailman",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # First strike, Quirk pump
)


SATO = make_creature(
    name="Sato, Sugarman",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Trample, Quirk pay life pump
)


# --- Regular Creatures ---

GROWTH_STUDENT = make_creature(
    name="Growth-Type Student",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=AddCounters("+1/+1", 1)
        ),
    ]
)


ONE_FOR_ALL_HEIR = make_creature(
    name="One For All Heir",
    power=2, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    # Trample, activated pump
)


NATURE_HERO = make_creature(
    name="Nature Hero",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    # Reach, trample
)


MUTANT_STUDENT = make_creature(
    name="Mutant-Type Student",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    # Trample
)


HEALING_HERO = make_creature(
    name="Healing Hero",
    power=1, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    # Lifelink, regenerate ability
)


FOREST_GUARDIAN = make_creature(
    name="Forest Guardian Hero",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    # Vigilance, reach
)


WILD_PUSSYCAT = make_creature(
    name="Wild Wild Pussycat Member",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    # ETB search basic land
)


# --- Instants ---

DETROIT_SMASH = make_instant(
    name="Detroit Smash",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +4/+4 and gains trample until end of turn."
)


DELAWARE_SMASH = make_instant(
    name="Delaware Smash",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. If you have 5 or less life, it gets +4/+4 instead."
)


MANCHESTER_SMASH = make_instant(
    name="Manchester Smash",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +5/+5 and gains trample until end of turn. It fights target creature you don't control."
)


FULL_COWLING = make_instant(
    name="Full Cowling",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 and gains hexproof until end of turn."
)


SHOOT_STYLE = make_instant(
    name="Shoot Style",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control. Your creature gets +2/+0 until end of turn."
)


BLACKWHIP = make_instant(
    name="Blackwhip",
    mana_cost="{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    text="Destroy target creature with flying. If you control a creature with +1/+1 counters on it, draw a card."
)


GROWTH_SURGE = make_instant(
    name="Growth Surge",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature you control."
)


ONE_FOR_ALL_100 = make_instant(
    name="One For All: 100%",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +10/+10 and gains trample until end of turn. Sacrifice it at end of turn unless you pay {G}{G}."
)


# --- Sorceries ---

QUIRK_EVOLUTION = make_sorcery(
    name="Quirk Evolution",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on each creature you control."
)


TRAINING_ARC = make_sorcery(
    name="Training Arc",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


FOREST_TRAINING_CAMP = make_sorcery(
    name="Forest Training Camp",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on each creature you control."
)


QUIRK_AWAKENING = make_sorcery(
    name="Quirk Awakening",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Double the number of +1/+1 counters on each creature you control."
)


# --- Enchantments ---

ONE_FOR_ALL = make_enchantment(
    name="One For All",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Enchanted creature gets +3/+3 and has 'At the beginning of your upkeep, put a +1/+1 counter on this creature.'"
)


FULL_COWLING_AURA = make_enchantment(
    name="Full Cowling Mastery",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchanted creature gets +2/+2 and has trample and haste."
)


QUIRK_TRAINING = make_enchantment(
    name="Quirk Training",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# --- Class 1-A Multicolor ---

JIRO = make_creature(
    name="Jiro, Earphone Jack",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Quirk deals damage, spell cast trigger
)


MINETA = make_creature(
    name="Mineta, Grape Rush",
    power=1, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    # Quirk prevents attack/block
)


KENDO = make_creature(
    name="Kendo, Battle Fist",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Student", include_self=False)
        ),
    ]
)


MONOMA = make_creature(
    name="Monoma, Copy Cat",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    # Combat damage copy ability
)


MIRIO = make_creature(
    name="Mirio, Lemillion",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Unblockable, Quirk hexproof/indestructible
)


TAMAKI = make_creature(
    name="Tamaki, Suneater",
    power=3, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Multiple Quirk abilities
)


NEJIRE = make_creature(
    name="Nejire, Nejire Wave",
    power=3, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Flying, Quirk damages flyers
)


AOYAMA = make_creature(
    name="Aoyama, Navel Laser",
    power=2, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # First strike, Quirk deals damage but doesn't untap
)


HAGAKURE = make_creature(
    name="Hagakure, Invisible Girl",
    power=1, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Unblockable, Quirk hexproof
)


# --- Pro Hero Multicolor ---

WASH = make_creature(
    name="Wash, Cleansing Hero",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # ETB bounce
)


EDGESHOT = make_creature(
    name="Edgeshot, Ninja Hero",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Flash, deathtouch, evasion
)


KAMUI_WOODS = make_creature(
    name="Kamui Woods, Tree Hero",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Reach, Quirk tap all
)


MT_LADY = make_creature(
    name="Mt. Lady, Gigantification",
    power=6, toughness=6,
    mana_cost="{4}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Trample, enters with -1/-1 counters, removes them
)


DEATH_ARMS = make_creature(
    name="Death Arms, Punching Hero",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # First strike, destroy on combat damage
)


NATIVE = make_creature(
    name="Native, Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(3)
        ),
    ]
)


FOURTH_KIND = make_creature(
    name="Fourth Kind, Hero",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Menace, can block additional creature
)


MANUAL = make_creature(
    name="Manual, Water Hero",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Quirk grants hexproof
)


# =============================================================================
# ARTIFACTS - SUPPORT ITEMS AND EQUIPMENT
# =============================================================================

DEKU_MASK = make_equipment(
    name="Deku's Iron Mask",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+2 and has hexproof."
)


BAKUGO_GAUNTLETS = make_equipment(
    name="Bakugo's Grenade Gauntlets",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+0. Whenever equipped creature deals combat damage to a player, it deals 2 damage to target creature that player controls."
)


CAPTURE_SCARF = make_equipment(
    name="Eraserhead's Capture Scarf",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has reach. {T}: Tap target creature with power 3 or less.",
    supertypes={"Legendary"}
)


IIDA_ENGINES = make_equipment(
    name="Iida's Engine Calves",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+0 and has haste. Whenever equipped creature attacks, it gets +2/+0 until end of turn."
)


TODOROKI_COSTUME = make_equipment(
    name="Todoroki's Costume",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2. {R}: Equipped creature gets +2/+0 until end of turn. {U}: Equipped creature gains hexproof until end of turn."
)


URARAKA_BOOTS = make_equipment(
    name="Uraraka's Gravity Boots",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature has flying."
)


SUPPORT_GEAR = make_equipment(
    name="Standard Support Gear",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1."
)


HERO_COSTUME = make_equipment(
    name="Hero Costume",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+1 and has vigilance."
)


POWER_SUIT = make_equipment(
    name="Power Loader Suit",
    mana_cost="{4}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has trample."
)


JETPACK_GEAR = make_equipment(
    name="Jetpack Support Item",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has flying and haste."
)


RECORDING_GEAR = make_equipment(
    name="Recording Gear",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature has 'Whenever this creature deals combat damage to a player, scry 1.'"
)


SHOCK_GAUNTLETS = make_equipment(
    name="Shock Gauntlets",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+0. {T}: Equipped creature deals 1 damage to target creature. That creature can't block this turn."
)


GRAPPLING_HOOK = make_equipment(
    name="Grappling Hook",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature has reach and 'Whenever this creature blocks, tap the blocked creature. It doesn't untap during its controller's next untap step.'"
)


# --- Artifacts ---

UA_BARRIER = make_artifact(
    name="UA Security Barrier",
    mana_cost="{3}",
    text="Creatures your opponents control can't attack you unless their controller pays {2} for each creature they attack with."
)


TRAINING_GROUND = make_artifact(
    name="Ground Beta",
    mana_cost="{4}",
    text="Hero creatures you control get +1/+1. At the beginning of your upkeep, put a training counter on Ground Beta. Creatures you control get +1/+1 for each training counter on Ground Beta."
)


RECOVERY_TANK = make_artifact(
    name="Recovery Girl's Tank",
    mana_cost="{3}",
    text="{2}, {T}: Regenerate target creature. You gain 2 life."
)


VILLAIN_MONITOR = make_artifact(
    name="Hero Network Monitor",
    mana_cost="{2}",
    text="{1}, {T}: Scry 1. If you control a Hero, draw a card instead."
)


NOMU_TANK = make_artifact(
    name="Nomu Creation Tank",
    mana_cost="{5}",
    text="{3}{B}{B}, {T}: Create a 5/5 black Zombie Villain creature token named Nomu with trample."
)


TRIGGER_VIAL = make_artifact(
    name="Trigger Vial",
    mana_cost="{1}",
    text="{T}, Sacrifice Trigger Vial: Target creature gets +3/+3 until end of turn. It deals 1 damage to itself at end of turn."
)


# =============================================================================
# LANDS
# =============================================================================

UA_HIGH = make_land(
    name="UA High School",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a Student.",
    supertypes={"Legendary"}
)


HEIGHTS_ALLIANCE = make_land(
    name="Heights Alliance",
    text="{T}: Add {C}. {1}, {T}: Add one mana of any color. Spend this mana only to cast Student spells."
)


TRAINING_GROUND_LAND = make_land(
    name="USJ Training Ground",
    text="{T}: Add {C}. {2}, {T}: Put a +1/+1 counter on target Student creature."
)


GROUND_BETA = make_land(
    name="Ground Beta Arena",
    text="{T}: Add {C}. Hero creatures you control get +0/+1."
)


VILLAIN_BAR = make_land(
    name="League of Villains Hideout",
    text="{T}: Add {B}. Villain creatures you control have '{T}: Add {B}.'",
    supertypes={"Legendary"}
)


TARTARUS = make_land(
    name="Tartarus Prison",
    text="{T}: Add {C}. {3}, {T}: Exile target creature with power 4 or less until Tartarus leaves the battlefield."
)


JAKKU_HOSPITAL = make_land(
    name="Jakku General Hospital",
    text="{T}: Add {W}. {2}{W}, {T}: You gain 3 life."
)


DEIKA_CITY = make_land(
    name="Deika City",
    text="{T}: Add {B} or {R}. Whenever a Villain you control attacks, Deika City deals 1 damage to defending player."
)


NABU_ISLAND = make_land(
    name="Nabu Island",
    text="{T}: Add one mana of any color. Nabu Island enters the battlefield tapped."
)


HOSU_CITY = make_land(
    name="Hosu City",
    text="{T}: Add {W}, {U}, or {R}. Hosu City enters the battlefield tapped."
)


KAMINO_WARD = make_land(
    name="Kamino Ward",
    text="{T}: Add {B}. {B}, {T}: Target creature gets -1/-1 until end of turn."
)


MUSUTAFU = make_land(
    name="Musutafu",
    text="{T}: Add {G} or {W}. {2}, {T}: Scry 1.",
    supertypes={"Legendary"}
)


ENDEAVOR_AGENCY = make_land(
    name="Endeavor Hero Agency",
    text="{T}: Add {R}. {R}, {T}: Target creature gets +1/+0 until end of turn."
)


SHIKETSU_HIGH = make_land(
    name="Shiketsu High",
    text="{T}: Add {C}. {T}: Add {U} or {R}. Activate only if you control a Student.",
    supertypes={"Legendary"}
)


# --- Basic Lands ---

PLAINS_MHA = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"}
)


ISLAND_MHA = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"}
)


SWAMP_MHA = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"}
)


MOUNTAIN_MHA = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"}
)


FOREST_MHA = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"}
)


# =============================================================================
# ADDITIONAL CREATURES
# =============================================================================

PIXIE_BOB = make_creature(
    name="Pixie-Bob, Wild Wild Pussycats",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # ETB create beast tokens, Quirk pump beasts
)


RECOVERY_GIRL = make_creature(
    name="Recovery Girl, Healing Hero",
    power=0, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Quirk regenerate and heal
)


VLAD_KING = make_creature(
    name="Vlad King, Blood Hero",
    power=3, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Menace, Quirk pay life pump
)


ECTOPLASM = make_creature(
    name="Ectoplasm, Clone Hero",
    power=2, toughness=2,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Quirk create copy token
)


HOUND_DOG = make_creature(
    name="Hound Dog, Detection Hero",
    power=3, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Vigilance, Quirk reveal hand
)


LUNCH_RUSH = make_creature(
    name="Lunch Rush, Cook Hero",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=GainLife(1)
        ),
    ]
)


INGENIUM = make_creature(
    name="Tensei Iida, Ingenium",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(['vigilance']),
            filter=CreaturesWithSubtypeFilter("Hero", include_self=False)
        ),
    ]
)


INASA = make_creature(
    name="Inasa Yoarashi, Gale Force",
    power=4, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Flying, Quirk removes flying and damages
)


CAMIE = make_creature(
    name="Camie, Illusion Girl",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    # Quirk create illusion copy
)


SEIJI = make_creature(
    name="Seiji Shishikura, Meatball",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    # Quirk exile small creature temporarily
)


GENTLE_CRIMINAL = make_creature(
    name="Gentle Criminal",
    power=2, toughness=3,
    mana_cost="{1}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(to_player=True, combat_only=True),
            effect=DrawCards(1)
        ),
    ]
)


LA_BRAVA = make_creature(
    name="La Brava, Love",
    power=1, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Quirk massive pump for Gentle
)


SPINNER = make_creature(
    name="Spinner, League Member",
    power=3, toughness=2,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # First strike, gets +1/+1 per villain
)


MAGNE = make_creature(
    name="Magne, Big Sis Magne",
    power=4, toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    # Haste, Quirk force attack/can't block
)


MUSTARD = make_creature(
    name="Mustard, Gas Villain",
    power=2, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Villain"},
    # ETB -1/-1 counters to opponents
)


REDESTRO_HAND = make_creature(
    name="Meta Liberation Hand",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    # Death trigger discard
)


DETNERAT_CEO = make_creature(
    name="Detnerat Executive",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    # Villain ETB drain
)


ENDING = make_creature(
    name="Ending, Obsessed Villain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    # Menace, conditional pump vs legendary
)


SLIDE_N_GO = make_creature(
    name="Slide'n'Go, Pro Hero",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    # Attack trigger tap
)


YOROI_MUSHA = make_creature(
    name="Yoroi Musha, Armored Hero",
    power=2, toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    # Vigilance, pump when equipped
)


BUBBLE_GIRL = make_creature(
    name="Bubble Girl, Sidekick",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    # Quirk tap small creature
)


CENTIPEDER = make_creature(
    name="Centipeder, Sidekick",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    # ETB scry 1
)


SHINDO = make_creature(
    name="Shindo, Quake Hero",
    power=3, toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Trample, Quirk damage non-flyers
)


NAKAGAME = make_creature(
    name="Nakagame, Shield Hero",
    power=1, toughness=5,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    # Defender, Quirk indestructible
)


MS_JOKE = make_creature(
    name="Ms. Joke, Smile Hero",
    power=2, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Quirk can't attack/block
)


# =============================================================================
# ADDITIONAL INSTANTS
# =============================================================================

HALF_COLD = make_instant(
    name="Half-Cold",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)


HALF_HOT = make_instant(
    name="Half-Hot",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Half-Hot deals 3 damage to target creature or planeswalker."
)


RECIPRO_BURST = make_instant(
    name="Recipro Burst",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Target creature gets +4/+0 and gains first strike until end of turn."
)


ZERO_GRAVITY = make_instant(
    name="Zero Gravity",
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Target creature gains flying until end of turn. If it's a Hero, it also gets +2/+2 until end of turn."
)


DARK_SHADOW_STRIKE = make_instant(
    name="Dark Shadow Strike",
    mana_cost="{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    text="Destroy target creature with flying. If you have 5 or less life, destroy any target creature instead."
)


FLASHFIRE_FIST = make_instant(
    name="Flashfire Fist",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Flashfire Fist deals 4 damage to target creature. You gain life equal to the damage dealt."
)


PROMINENCE_BURN = make_instant(
    name="Prominence Burn",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Prominence Burn deals 6 damage to target creature or planeswalker."
)


FIERCE_WINGS = make_instant(
    name="Fierce Wings",
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Target creature gains flying and first strike until end of turn. Draw a card."
)


# =============================================================================
# CARD DICTIONARY EXPORT
# =============================================================================

MY_HERO_ACADEMIA_CARDS = {
    # WHITE - HEROES, SYMBOL OF PEACE, RESCUE
    "All Might, Symbol of Peace": ALL_MIGHT,
    "Endeavor, Number One Hero": ENDEAVOR,
    "Hawks, Number Two Hero": HAWKS,
    "Eraserhead, Underground Hero": ERASERHEAD,
    "Best Jeanist, Fiber Master": BEST_JEANIST,
    "Mirko, Rabbit Hero": MIRKO,
    "Rescue Hero": RESCUE_HERO,
    "Eager Sidekick": SIDEKICK,
    "UA Teacher": UA_TEACHER,
    "Hero Public Safety Officer": POLICE_OFFICER,
    "Rescue Squad": RESCUE_SQUAD,
    "Support Course Student": SUPPORT_COURSE_STUDENT,
    "Hero Intern": HERO_INTERN,
    "Nighteye Agency Member": NIGHTEYE_AGENCY_MEMBER,
    "Selkie, Water Hero": SELKIE,
    "Gang Orca, Whale Hero": GANG_ORCA,
    "Thirteen, Rescue Hero": THIRTEEN,
    "Midnight, R-Rated Hero": MIDNIGHT,
    "Present Mic, Voice Hero": PRESENT_MIC,
    "Cementoss, Concrete Hero": CEMENTOSS,
    "Snipe, Shooting Hero": SNIPE,
    "Plus Ultra Smash": PLUS_ULTRA_SMASH,
    "Heroic Rescue": HEROIC_RESCUE,
    "Symbol of Peace": SYMBOL_OF_PEACE,
    "Fear Not": FEAR_NOT,
    "Emergency Evacuation": EMERGENCY_EVACUATION,
    "United States of Smash": UNITED_STATES_OF_SMASH,
    "Hero Arrival": HERO_ARRIVAL,
    "Quirk Suppression": QUIRK_SUPPRESSION,
    "Hero Recruitment": HERO_RECRUITMENT,
    "Peace Summit": PEACE_SUMMIT,
    "UA Training Session": UA_TRAINING_SESSION,
    "Symbol of Hope": SYMBOL_OF_HOPE,
    "Hero License": HERO_LICENSE,
    "Provisional License": PROVISIONAL_LICENSE,

    # BLUE - STRATEGY QUIRKS, INTELLIGENCE
    "Nezu, UA Principal": NEZU,
    "Sir Nighteye, Foresight Hero": SIR_NIGHTEYE,
    "Shinso, Mind Control": SHINSO,
    "Mandalay, Wild Wild Pussycats": MANDALAY,
    "Ragdoll, Wild Wild Pussycats": RAGDOLL,
    "Tiger, Wild Wild Pussycats": TIGER,
    "Analyst Hero": ANALYST_HERO,
    "Hero Information Broker": INFORMATION_BROKER,
    "UA Training Robot": UA_ROBOT,
    "Erasure Agent": ERASURE_AGENT,
    "Tactical Support Hero": TACTICAL_SUPPORT,
    "Strategy Student": STRATEGY_STUDENT,
    "Hatsume Mei, Inventor": HATSUME_MEI,
    "Power Loader, Support Teacher": POWER_LOADER,
    "Tactical Analysis": TACTICAL_ANALYSIS,
    "Counter Strategy": COUNTER_STRATEGY,
    "Quirk Analysis": QUIRK_ANALYSIS,
    "Brainwash": BRAINWASH,
    "Foresight": FORESIGHT,
    "Mind Trick": MIND_TRICK,
    "Telepathic Link": TELEPATHIC_LINK,
    "Information Gathering": INFORMATION_GATHERING,
    "Strategic Planning": STRATEGIC_PLANNING,
    "Hero Analysis": HERO_ANALYSIS,
    "Quirk Research": QUIRK_RESEARCH,
    "Battle Strategy": BATTLE_STRATEGY,

    # BLACK - VILLAINS, LEAGUE OF VILLAINS, ALL FOR ONE
    "All For One, Ultimate Villain": ALL_FOR_ONE,
    "Shigaraki, Decay Lord": SHIGARAKI,
    "Dabi, Cremation": DABI,
    "Toga, Blood Obsession": TOGA,
    "Stain, Hero Killer": STAIN,
    "Overhaul, Yakuza Boss": OVERHAUL,
    "Twice, Double Trouble": TWICE,
    "Mr. Compress, Showman": MR_COMPRESS,
    "Kurogiri, Warp Gate": KUROGIRI,
    "Muscular, Villain": MUSCULAR,
    "Moonfish, Blade Villain": MOONFISH,
    "Gigantomachia, Living Disaster": GIGANTOMACHIA,
    "League of Villains Grunt": LEAGUE_GRUNT,
    "Nomu, Bioengineered": NOMU,
    "High-End Nomu": HIGH_END_NOMU,
    "Shie Hassaikai Thug": YAKUZA_THUG,
    "Trigger Dealer": TRIGGER_DEALER,
    "Meta Liberation Soldier": META_LIBERATION_SOLDIER,
    "Skeptic, Liberation Lieutenant": SKEPTIC,
    "Trumpet, Liberation Commander": TRUMPET,
    "Re-Destro, Liberation Leader": RE_DESTRO,
    "Curious, Information Master": CURIOUS,
    "Geten, Ice Villain": GETEN,
    "Decay Touch": DECAY_TOUCH,
    "Villain Ambush": VILLAIN_AMBUSH,
    "Blood Drain": BLOOD_DRAIN,
    "Dark Reunion": DARK_REUNION,
    "Quirk Erasure": QUIRK_ERASURE,
    "Villain Assassination": ASSASSINATION,
    "Warp Gate": WARP_GATE,
    "Villain Recruitment": VILLAIN_RECRUITMENT,
    "Liberation March": LIBERATION_MARCH,
    "Decay Wave": DECAY_WAVE,
    "League Hideout": LEAGUE_HIDEOUT,
    "Trigger Drug": TRIGGER_DRUG,
    "Quirk Singularity": QUIRK_SINGULARITY,

    # RED - BAKUGO, POWER QUIRKS, AGGRESSION
    "Bakugo, Explosion Hero": BAKUGO,
    "Kirishima, Red Riot": KIRISHIMA,
    "Kaminari, Chargebolt": KAMINARI,
    "Tetsutetsu, Real Steel": TETSUTETSU,
    "Mina Ashido, Pinky": MINA,
    "Fat Gum, BMI Hero": FATGUM,
    "Ryukyu, Dragon Hero": RYUKYU,
    "Crimson Riot, Legendary Hero": CRIMSON_RIOT,
    "Explosion Student": EXPLOSION_STUDENT,
    "Combat Hero": COMBAT_HERO,
    "Power-Type Student": POWER_TYPE_STUDENT,
    "Raging Hero": RAGING_HERO,
    "Fiery Sidekick": FIERY_SIDEKICK,
    "Battle Course Student": BATTLE_STUDENT,
    "Berserker Hero": BERSERKER_HERO,
    "Explosion": EXPLOSION,
    "AP Shot": AP_SHOT,
    "Howitzer Impact": HOWITZER_IMPACT,
    "Stun Grenade": STUN_GRENADE,
    "Battle Fury": BATTLE_FURY,
    "Plus Ultra Rush": PLUS_ULTRA_RUSH,
    "Hellfire Storm": HELLFIRE,
    "Cremation": CREMATION,
    "Explosive Rampage": EXPLOSIVE_RAMPAGE,
    "Total Destruction": TOTAL_DESTRUCTION,
    "Ground Zero": GROUND_ZERO,
    "Fighting Spirit": FIGHTING_SPIRIT,
    "Unbreakable Will": UNBREAKABLE_WILL,
    "Explosive Power": EXPLOSIVE_POWER,

    # GREEN - DEKU, GROWTH, ONE FOR ALL
    "Deku, Inheritor of One For All": DEKU,
    "Uraraka, Zero Gravity": URARAKA,
    "Iida, Ingenium": IIDA,
    "Todoroki, Half-Cold Half-Hot": TODOROKI,
    "Tsuyu, Froppy": TSUYU,
    "Momo, Creation Hero": MOMO,
    "Tokoyami, Dark Shadow": TOKOYAMI,
    "Sero, Cellophane": SERO,
    "Shoji, Tentacole": SHOJI,
    "Koda, Anima": KODA,
    "Ojiro, Tailman": OJIRO,
    "Sato, Sugarman": SATO,
    "Growth-Type Student": GROWTH_STUDENT,
    "One For All Heir": ONE_FOR_ALL_HEIR,
    "Nature Hero": NATURE_HERO,
    "Mutant-Type Student": MUTANT_STUDENT,
    "Healing Hero": HEALING_HERO,
    "Forest Guardian Hero": FOREST_GUARDIAN,
    "Wild Wild Pussycat Member": WILD_PUSSYCAT,
    "Detroit Smash": DETROIT_SMASH,
    "Delaware Smash": DELAWARE_SMASH,
    "Manchester Smash": MANCHESTER_SMASH,
    "Full Cowling": FULL_COWLING,
    "Shoot Style": SHOOT_STYLE,
    "Blackwhip": BLACKWHIP,
    "Growth Surge": GROWTH_SURGE,
    "One For All: 100%": ONE_FOR_ALL_100,
    "Quirk Evolution": QUIRK_EVOLUTION,
    "Training Arc": TRAINING_ARC,
    "Forest Training Camp": FOREST_TRAINING_CAMP,
    "Quirk Awakening": QUIRK_AWAKENING,
    "One For All": ONE_FOR_ALL,
    "Full Cowling Mastery": FULL_COWLING_AURA,
    "Quirk Training": QUIRK_TRAINING,

    # MULTICOLOR - CLASS 1-A AND HEROES
    "Jiro, Earphone Jack": JIRO,
    "Mineta, Grape Rush": MINETA,
    "Kendo, Battle Fist": KENDO,
    "Monoma, Copy Cat": MONOMA,
    "Mirio, Lemillion": MIRIO,
    "Tamaki, Suneater": TAMAKI,
    "Nejire, Nejire Wave": NEJIRE,
    "Aoyama, Navel Laser": AOYAMA,
    "Hagakure, Invisible Girl": HAGAKURE,
    "Wash, Cleansing Hero": WASH,
    "Edgeshot, Ninja Hero": EDGESHOT,
    "Kamui Woods, Tree Hero": KAMUI_WOODS,
    "Mt. Lady, Gigantification": MT_LADY,
    "Death Arms, Punching Hero": DEATH_ARMS,
    "Native, Hero": NATIVE,
    "Fourth Kind, Hero": FOURTH_KIND,
    "Manual, Water Hero": MANUAL,

    # EQUIPMENT - SUPPORT ITEMS
    "Deku's Iron Mask": DEKU_MASK,
    "Bakugo's Grenade Gauntlets": BAKUGO_GAUNTLETS,
    "Eraserhead's Capture Scarf": CAPTURE_SCARF,
    "Iida's Engine Calves": IIDA_ENGINES,
    "Todoroki's Costume": TODOROKI_COSTUME,
    "Uraraka's Gravity Boots": URARAKA_BOOTS,
    "Standard Support Gear": SUPPORT_GEAR,
    "Hero Costume": HERO_COSTUME,
    "Power Loader Suit": POWER_SUIT,
    "Jetpack Support Item": JETPACK_GEAR,
    "Recording Gear": RECORDING_GEAR,
    "Shock Gauntlets": SHOCK_GAUNTLETS,
    "Grappling Hook": GRAPPLING_HOOK,

    # ARTIFACTS
    "UA Security Barrier": UA_BARRIER,
    "Ground Beta": TRAINING_GROUND,
    "Recovery Girl's Tank": RECOVERY_TANK,
    "Hero Network Monitor": VILLAIN_MONITOR,
    "Nomu Creation Tank": NOMU_TANK,
    "Trigger Vial": TRIGGER_VIAL,

    # LANDS
    "UA High School": UA_HIGH,
    "Heights Alliance": HEIGHTS_ALLIANCE,
    "USJ Training Ground": TRAINING_GROUND_LAND,
    "Ground Beta Arena": GROUND_BETA,
    "League of Villains Hideout": VILLAIN_BAR,
    "Tartarus Prison": TARTARUS,
    "Jakku General Hospital": JAKKU_HOSPITAL,
    "Deika City": DEIKA_CITY,
    "Nabu Island": NABU_ISLAND,
    "Hosu City": HOSU_CITY,
    "Kamino Ward": KAMINO_WARD,
    "Musutafu": MUSUTAFU,
    "Endeavor Hero Agency": ENDEAVOR_AGENCY,
    "Shiketsu High": SHIKETSU_HIGH,

    # BASIC LANDS
    "Plains": PLAINS_MHA,
    "Island": ISLAND_MHA,
    "Swamp": SWAMP_MHA,
    "Mountain": MOUNTAIN_MHA,
    "Forest": FOREST_MHA,

    # ADDITIONAL CREATURES
    "Pixie-Bob, Wild Wild Pussycats": PIXIE_BOB,
    "Recovery Girl, Healing Hero": RECOVERY_GIRL,
    "Vlad King, Blood Hero": VLAD_KING,
    "Ectoplasm, Clone Hero": ECTOPLASM,
    "Hound Dog, Detection Hero": HOUND_DOG,
    "Lunch Rush, Cook Hero": LUNCH_RUSH,
    "Tensei Iida, Ingenium": INGENIUM,
    "Inasa Yoarashi, Gale Force": INASA,
    "Camie, Illusion Girl": CAMIE,
    "Seiji Shishikura, Meatball": SEIJI,
    "Gentle Criminal": GENTLE_CRIMINAL,
    "La Brava, Love": LA_BRAVA,
    "Spinner, League Member": SPINNER,
    "Magne, Big Sis Magne": MAGNE,
    "Mustard, Gas Villain": MUSTARD,
    "Meta Liberation Hand": REDESTRO_HAND,
    "Detnerat Executive": DETNERAT_CEO,
    "Ending, Obsessed Villain": ENDING,
    "Slide'n'Go, Pro Hero": SLIDE_N_GO,
    "Yoroi Musha, Armored Hero": YOROI_MUSHA,
    "Bubble Girl, Sidekick": BUBBLE_GIRL,
    "Centipeder, Sidekick": CENTIPEDER,
    "Shindo, Quake Hero": SHINDO,
    "Nakagame, Shield Hero": NAKAGAME,
    "Ms. Joke, Smile Hero": MS_JOKE,

    # ADDITIONAL INSTANTS
    "Half-Cold": HALF_COLD,
    "Half-Hot": HALF_HOT,
    "Recipro Burst": RECIPRO_BURST,
    "Zero Gravity": ZERO_GRAVITY,
    "Dark Shadow Strike": DARK_SHADOW_STRIKE,
    "Flashfire Fist": FLASHFIRE_FIST,
    "Prominence Burn": PROMINENCE_BURN,
    "Fierce Wings": FIERCE_WINGS,
}

print(f"Loaded {len(MY_HERO_ACADEMIA_CARDS)} My Hero Academia: Heroes Rising cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    ALL_MIGHT,
    ENDEAVOR,
    HAWKS,
    ERASERHEAD,
    BEST_JEANIST,
    MIRKO,
    RESCUE_HERO,
    SIDEKICK,
    UA_TEACHER,
    POLICE_OFFICER,
    RESCUE_SQUAD,
    SUPPORT_COURSE_STUDENT,
    HERO_INTERN,
    NIGHTEYE_AGENCY_MEMBER,
    SELKIE,
    GANG_ORCA,
    THIRTEEN,
    MIDNIGHT,
    PRESENT_MIC,
    CEMENTOSS,
    SNIPE,
    PLUS_ULTRA_SMASH,
    HEROIC_RESCUE,
    SYMBOL_OF_PEACE,
    FEAR_NOT,
    EMERGENCY_EVACUATION,
    UNITED_STATES_OF_SMASH,
    HERO_ARRIVAL,
    QUIRK_SUPPRESSION,
    HERO_RECRUITMENT,
    PEACE_SUMMIT,
    UA_TRAINING_SESSION,
    SYMBOL_OF_HOPE,
    HERO_LICENSE,
    PROVISIONAL_LICENSE,
    NEZU,
    SIR_NIGHTEYE,
    SHINSO,
    MANDALAY,
    RAGDOLL,
    TIGER,
    ANALYST_HERO,
    INFORMATION_BROKER,
    UA_ROBOT,
    ERASURE_AGENT,
    TACTICAL_SUPPORT,
    STRATEGY_STUDENT,
    HATSUME_MEI,
    POWER_LOADER,
    TACTICAL_ANALYSIS,
    COUNTER_STRATEGY,
    QUIRK_ANALYSIS,
    BRAINWASH,
    FORESIGHT,
    MIND_TRICK,
    TELEPATHIC_LINK,
    INFORMATION_GATHERING,
    STRATEGIC_PLANNING,
    HERO_ANALYSIS,
    QUIRK_RESEARCH,
    BATTLE_STRATEGY,
    ALL_FOR_ONE,
    SHIGARAKI,
    DABI,
    TOGA,
    STAIN,
    OVERHAUL,
    TWICE,
    MR_COMPRESS,
    KUROGIRI,
    MUSCULAR,
    MOONFISH,
    GIGANTOMACHIA,
    LEAGUE_GRUNT,
    NOMU,
    HIGH_END_NOMU,
    YAKUZA_THUG,
    TRIGGER_DEALER,
    META_LIBERATION_SOLDIER,
    SKEPTIC,
    TRUMPET,
    RE_DESTRO,
    CURIOUS,
    GETEN,
    DECAY_TOUCH,
    VILLAIN_AMBUSH,
    BLOOD_DRAIN,
    DARK_REUNION,
    QUIRK_ERASURE,
    ASSASSINATION,
    WARP_GATE,
    VILLAIN_RECRUITMENT,
    LIBERATION_MARCH,
    DECAY_WAVE,
    LEAGUE_HIDEOUT,
    TRIGGER_DRUG,
    QUIRK_SINGULARITY,
    BAKUGO,
    KIRISHIMA,
    KAMINARI,
    TETSUTETSU,
    MINA,
    FATGUM,
    RYUKYU,
    CRIMSON_RIOT,
    EXPLOSION_STUDENT,
    COMBAT_HERO,
    POWER_TYPE_STUDENT,
    RAGING_HERO,
    FIERY_SIDEKICK,
    BATTLE_STUDENT,
    BERSERKER_HERO,
    EXPLOSION,
    AP_SHOT,
    HOWITZER_IMPACT,
    STUN_GRENADE,
    BATTLE_FURY,
    PLUS_ULTRA_RUSH,
    HELLFIRE,
    CREMATION,
    EXPLOSIVE_RAMPAGE,
    TOTAL_DESTRUCTION,
    GROUND_ZERO,
    FIGHTING_SPIRIT,
    UNBREAKABLE_WILL,
    EXPLOSIVE_POWER,
    DEKU,
    URARAKA,
    IIDA,
    TODOROKI,
    TSUYU,
    MOMO,
    TOKOYAMI,
    SERO,
    SHOJI,
    KODA,
    OJIRO,
    SATO,
    GROWTH_STUDENT,
    ONE_FOR_ALL_HEIR,
    NATURE_HERO,
    MUTANT_STUDENT,
    HEALING_HERO,
    FOREST_GUARDIAN,
    WILD_PUSSYCAT,
    DETROIT_SMASH,
    DELAWARE_SMASH,
    MANCHESTER_SMASH,
    FULL_COWLING,
    SHOOT_STYLE,
    BLACKWHIP,
    GROWTH_SURGE,
    ONE_FOR_ALL_100,
    QUIRK_EVOLUTION,
    TRAINING_ARC,
    FOREST_TRAINING_CAMP,
    QUIRK_AWAKENING,
    ONE_FOR_ALL,
    FULL_COWLING_AURA,
    QUIRK_TRAINING,
    JIRO,
    MINETA,
    KENDO,
    MONOMA,
    MIRIO,
    TAMAKI,
    NEJIRE,
    AOYAMA,
    HAGAKURE,
    WASH,
    EDGESHOT,
    KAMUI_WOODS,
    MT_LADY,
    DEATH_ARMS,
    NATIVE,
    FOURTH_KIND,
    MANUAL,
    DEKU_MASK,
    BAKUGO_GAUNTLETS,
    CAPTURE_SCARF,
    IIDA_ENGINES,
    TODOROKI_COSTUME,
    URARAKA_BOOTS,
    SUPPORT_GEAR,
    HERO_COSTUME,
    POWER_SUIT,
    JETPACK_GEAR,
    RECORDING_GEAR,
    SHOCK_GAUNTLETS,
    GRAPPLING_HOOK,
    UA_BARRIER,
    TRAINING_GROUND,
    RECOVERY_TANK,
    VILLAIN_MONITOR,
    NOMU_TANK,
    TRIGGER_VIAL,
    UA_HIGH,
    HEIGHTS_ALLIANCE,
    TRAINING_GROUND_LAND,
    GROUND_BETA,
    VILLAIN_BAR,
    TARTARUS,
    JAKKU_HOSPITAL,
    DEIKA_CITY,
    NABU_ISLAND,
    HOSU_CITY,
    KAMINO_WARD,
    MUSUTAFU,
    ENDEAVOR_AGENCY,
    SHIKETSU_HIGH,
    PLAINS_MHA,
    ISLAND_MHA,
    SWAMP_MHA,
    MOUNTAIN_MHA,
    FOREST_MHA,
    PIXIE_BOB,
    RECOVERY_GIRL,
    VLAD_KING,
    ECTOPLASM,
    HOUND_DOG,
    LUNCH_RUSH,
    INGENIUM,
    INASA,
    CAMIE,
    SEIJI,
    GENTLE_CRIMINAL,
    LA_BRAVA,
    SPINNER,
    MAGNE,
    MUSTARD,
    REDESTRO_HAND,
    DETNERAT_CEO,
    ENDING,
    SLIDE_N_GO,
    YOROI_MUSHA,
    BUBBLE_GIRL,
    CENTIPEDER,
    SHINDO,
    NAKAGAME,
    MS_JOKE,
    HALF_COLD,
    HALF_HOT,
    RECIPRO_BURST,
    ZERO_GRAVITY,
    DARK_SHADOW_STRIKE,
    FLASHFIRE_FIST,
    PROMINENCE_BURN,
    FIERCE_WINGS
]
