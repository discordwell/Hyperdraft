"""
My Hero Academia: Heroes Rising (MHA) Card Implementations

Set released 2026. ~250 cards.
Features mechanics: Quirk, Plus Ultra, Villain
"""

from src.cards.card_factories import (
    make_artifact,
    make_equipment,
    make_land,
    make_sorcery,
)

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from src.cards.ability_bundles import (
    etb_gain_life,
    etb_draw,
    etb_deal_damage,
    death_draw,
    attack_deal_damage,
    static_pt_boost_all_you_control,
    static_pt_boost_by_subtype,
    static_keyword_grant_others,
    upkeep_gain_life,
)
from src.cards.text_render import (
    substitute_card_name,
    render_composite,
    render_static_pt_boost,
    render_static_keyword_grant,
    render_etb_gain_life,
    render_etb_draw,
    render_etb_deal_damage,
    render_death_draw,
    render_attack_deal_damage,
    render_upkeep_gain_life,
)
from src.cards import interceptor_helpers as _ih
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# MY HERO ACADEMIA KEYWORD MECHANICS
# =============================================================================

def _self_keyword_setup(*keywords: str) -> Callable[[GameObject, GameState], list[Interceptor]]:
    """Closure factory - grants the given keywords to the source creature only.
    Used for vanilla-keyword cards to avoid repeating 10 lines per card."""
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def self_filter(target: GameObject, state: GameState) -> bool:
            return target.id == obj.id
        return [_ih.make_keyword_grant(obj, list(keywords), self_filter)]
    return _setup


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

def _all_might_setup(obj, state):
    lord_itcs, _txt = static_pt_boost_by_subtype(obj, 2, 2, "Hero", include_self=False)
    return list(lord_itcs) + make_plus_ultra_bonus(obj, 3, 3)

ALL_MIGHT = make_creature(
    name="All Might, Symbol of Peace",
    power=6, toughness=6,
    mana_cost="{3}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Plus Ultra handled via setup_interceptors since it's conditional on life total
    text="Other Hero creatures you control get +2/+2.",
    setup_interceptors=_all_might_setup,
)


def _endeavor_setup(obj, state):
    itc, _txt = attack_deal_damage(obj, 2, target="each_opponent")
    return [itc]

ENDEAVOR = make_creature(
    name="Endeavor, Number One Hero",
    power=5, toughness=4,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=substitute_card_name(
        render_attack_deal_damage(2, "each opponent"),
        "Endeavor, Number One Hero",
    ),
    setup_interceptors=_endeavor_setup,
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
    text="Other Hero creatures you control have flying.",
    setup_interceptors=hawks_setup,
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
    """Rabbit Hero: haste and first strike. Whenever Mirko attacks, she
    gets +2/+0 until end of turn."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['haste', 'first_strike'], self_filter)
    ]

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 2, 'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_attack_trigger(obj, attack_effect))
    return itcs

MIRKO = make_creature(
    name="Mirko, Rabbit Hero",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Haste, first strike. Whenever Mirko attacks, she gets +2/+0 until end of turn.",
    setup_interceptors=mirko_setup
)


# --- Regular Creatures ---

def _rescue_hero_setup(obj, state):
    itc, _txt = etb_gain_life(obj, 3)
    return [itc]

RESCUE_HERO = make_creature(
    name="Rescue Hero",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text=substitute_card_name(render_etb_gain_life(3), "Rescue Hero"),
    setup_interceptors=_rescue_hero_setup,
)


SIDEKICK = make_creature(
    name="Eager Sidekick",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    # Dynamic P/T based on hero count - needs special handling
)


def _ua_teacher_setup(obj, state):
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Student", include_self=False)
    return list(itcs)

UA_TEACHER = make_creature(
    name="UA Teacher",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Other Student creatures you control get +1/+1.",
    setup_interceptors=_ua_teacher_setup,
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
    text="Lifelink",
    setup_interceptors=_self_keyword_setup('lifelink'),
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
    text="Hexproof, vigilance",
    setup_interceptors=_self_keyword_setup('hexproof', 'vigilance'),
)


def _gang_orca_setup(obj, state):
    """Orcinus: menace. When Gang Orca enters, tap all creatures opponents
    control (intimidation from the big whale)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['menace'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in state.objects.values():
            if (o.controller != obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types):
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': o.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

GANG_ORCA = make_creature(
    name="Gang Orca, Whale Hero",
    power=5, toughness=5,
    mana_cost="{3}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Menace. When Gang Orca enters the battlefield, tap all creatures your opponents control.",
    setup_interceptors=_gang_orca_setup,
)


def _thirteen_setup(obj, state):
    """Black Hole: Thirteen has defender. When she enters, you gain 4 life."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['defender'], self_filter)
    ]
    itc, _ = etb_gain_life(obj, 4)
    itcs.append(itc)
    return itcs

THIRTEEN = make_creature(
    name="Thirteen, Rescue Hero",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Defender. When Thirteen enters the battlefield, you gain 4 life.",
    setup_interceptors=_thirteen_setup,
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

def _symbol_of_hope_setup(obj, state):
    # Flagged: CreaturesWithSubtypeFilter("Hero") with include_self=True.
    # No matching keyword-grant bundle exists; use interceptor_helpers directly.
    return [_ih.make_keyword_grant(
        obj, ['vigilance', 'lifelink'],
        _ih.creatures_with_subtype(obj, "Hero"),
    )]

SYMBOL_OF_HOPE = make_enchantment(
    name="Symbol of Hope",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text=substitute_card_name(
        render_static_keyword_grant(['vigilance', 'lifelink'], scope="Hero creatures you control"),
        "Symbol of Hope",
    ),
    setup_interceptors=_symbol_of_hope_setup,
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

def _nezu_setup(obj, state):
    # No upkeep_draw bundle; use interceptor_helpers directly.
    def effect_fn(event, state):
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_upkeep_trigger(obj, effect_fn)]

NEZU = make_creature(
    name="Nezu, UA Principal",
    power=1, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Mouse", "Hero"},
    supertypes={"Legendary"},
    text=substitute_card_name(
        "At the beginning of your upkeep, draw a card.",
        "Nezu, UA Principal",
    ),
    setup_interceptors=_nezu_setup,
)


def _sir_nighteye_setup(obj, state):
    itc, _txt = etb_draw(obj, 1)
    return [itc]

SIR_NIGHTEYE = make_creature(
    name="Sir Nighteye, Foresight Hero",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    # Simplified from look at 3, put 1 in hand
    text=substitute_card_name(render_etb_draw(1), "Sir Nighteye, Foresight Hero"),
    setup_interceptors=_sir_nighteye_setup,
)


def _shinso_setup(obj, state):
    """Brainwashing: unblockable. When Shinso deals combat damage to a
    player, that player discards a card (they obey him)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['unblockable'], self_filter)
    ]

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target not in state.players:
            return []
        return [Event(
            type=EventType.DISCARD,
            payload={'player': target, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_damage_trigger(obj, damage_effect, combat_only=True))
    return itcs

SHINSO = make_creature(
    name="Shinso, Mind Control",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text="Unblockable. Whenever Shinso deals combat damage to a player, that player discards a card.",
    setup_interceptors=_shinso_setup,
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
    text="Other Hero creatures you control have hexproof.",
    setup_interceptors=mandalay_setup,
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


def _ua_robot_setup(obj, state):
    itc, _txt = death_draw(obj, 1)
    return [itc]

UA_ROBOT = make_creature(
    name="UA Training Robot",
    power=3, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text=substitute_card_name(render_death_draw(1), "UA Training Robot"),
    setup_interceptors=_ua_robot_setup,
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


def _battle_strategy_setup(obj, state):
    itcs, _txt = static_pt_boost_all_you_control(obj, 1, 0)
    return list(itcs)

BATTLE_STRATEGY = make_enchantment(
    name="Battle Strategy",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text=substitute_card_name(
        render_static_pt_boost(1, 0, scope="creatures you control"),
        "Battle Strategy",
    ),
    setup_interceptors=_battle_strategy_setup,
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


def _shigaraki_setup(obj, state):
    """Decay: when Shigaraki deals combat damage to a player, destroy target
    creature that player controls with the least toughness. Also drains 2 life.
    """
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        # Only when dealing damage to a player (not a creature)
        if target not in state.players:
            return []
        # Pick the opponent's creature with least toughness as a "decay" victim.
        victims = [
            o for o in state.objects.values()
            if o.controller == target
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
        ]
        events: list[Event] = [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target, 'amount': -2},
                source=obj.id,
                controller=obj.controller,
            )
        ]
        if victims:
            victim = min(victims, key=lambda o: get_toughness(o, state))
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': victim.id},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [_ih.make_damage_trigger(obj, damage_effect, combat_only=True)]

SHIGARAKI = make_creature(
    name="Shigaraki, Decay Lord",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=substitute_card_name(
        "Whenever {this} deals combat damage to a player, that player loses 2 life and destroy the creature they control with the least toughness.",
        "Shigaraki, Decay Lord",
    ),
    setup_interceptors=_shigaraki_setup,
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
    """Blood Obsession: deathtouch. Whenever Toga deals combat damage to a
    player, that player discards a card and you gain 2 life (stole their
    blood)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['deathtouch'], self_filter)
    ]

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target not in state.players:
            return []
        return [
            Event(
                type=EventType.DISCARD,
                payload={'player': target, 'amount': 1},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id,
                controller=obj.controller,
            ),
        ]
    itcs.append(_ih.make_damage_trigger(obj, damage_effect, combat_only=True))
    return itcs

TOGA = make_creature(
    name="Toga, Blood Obsession",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Toga deals combat damage to a player, that player discards a card and you gain 2 life.",
    setup_interceptors=toga_setup
)


def _stain_setup(obj, state):
    """Hero Killer: has first strike and deathtouch always. When it attacks,
    if an opponent controls a Hero, Stain gets +2/+0 until end of turn
    (models the 'doubles down against Heroes' fantasy)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['first_strike', 'deathtouch'], self_filter)
    ]

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        hero_present = any(
            o.controller != obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and "Hero" in o.characteristics.subtypes
            for o in state.objects.values()
        )
        if not hero_present:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 2, 'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_attack_trigger(obj, attack_effect))
    return itcs

STAIN = make_creature(
    name="Stain, Hero Killer",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="First strike, deathtouch. Whenever Stain attacks, if an opponent controls a Hero, Stain gets +2/+0 until end of turn.",
    setup_interceptors=_stain_setup,
)


def _overhaul_setup(obj, state):
    """Disassemble: when Overhaul enters, remove all +1/+1 counters from
    each creature opponents control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in state.objects.values():
            if (o.controller != obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types):
                count = o.state.counters.get('+1/+1', 0) if hasattr(o, 'state') and o.state else 0
                if count > 0:
                    events.append(Event(
                        type=EventType.COUNTER_REMOVED,
                        payload={
                            'object_id': o.id,
                            'counter_type': '+1/+1',
                            'amount': count,
                        },
                        source=obj.id,
                        controller=obj.controller,
                    ))
        return events
    return [_ih.make_etb_trigger(obj, etb_effect)]

OVERHAUL = make_creature(
    name="Overhaul, Yakuza Boss",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Overhaul enters the battlefield, remove all +1/+1 counters from each creature your opponents control.",
    setup_interceptors=_overhaul_setup,
)


def _twice_setup(obj, state):
    """Double: when Twice enters, create two 2/2 black Human Villain tokens
    named Clone."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'name': 'Clone',
                    'power': 2, 'toughness': 2,
                    'colors': {Color.BLACK},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Human', 'Villain'},
                },
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(2)
        ]
    return [_ih.make_etb_trigger(obj, etb_effect)]

TWICE = make_creature(
    name="Twice, Double Trouble",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Twice enters the battlefield, create two 2/2 black Human Villain creature tokens named Clone.",
    setup_interceptors=_twice_setup,
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
    text="Flash, hexproof",
    setup_interceptors=_self_keyword_setup('flash', 'hexproof'),
)


MUSCULAR = make_creature(
    name="Muscular, Villain",
    power=6, toughness=4,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Trample, haste",
    setup_interceptors=_self_keyword_setup('trample', 'haste'),
)


MOONFISH = make_creature(
    name="Moonfish, Blade Villain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="First strike, deathtouch",
    setup_interceptors=_self_keyword_setup('first_strike', 'deathtouch'),
)


GIGANTOMACHIA = make_creature(
    name="Gigantomachia, Living Disaster",
    power=12, toughness=12,
    mana_cost="{8}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Giant", "Villain"},
    supertypes={"Legendary"},
    text="Trample, menace",
    setup_interceptors=_self_keyword_setup('trample', 'menace'),
)


# --- Regular Creatures ---

def league_grunt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Villain - when an opponent loses life, you gain 1 life. (Safer
    than chaining additional LIFE_CHANGEs, which could recurse with any
    future 'villain hits life loss' effect.)"""
    def villain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_villain_trigger(obj, villain_effect)]

LEAGUE_GRUNT = make_creature(
    name="League of Villains Grunt",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text="Villain - Whenever an opponent loses life, you gain 1 life.",
    setup_interceptors=league_grunt_setup
)


def _nomu_setup(obj, state):
    # No death-opponents-lose-life bundle; use interceptor_helpers directly.
    def effect_fn(event, state):
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -2},
                source=obj.id,
                controller=obj.controller,
            )
            for opp in _ih.all_opponents(obj, state)
        ]
    return [_ih.make_death_trigger(obj, effect_fn)]

NOMU = make_creature(
    name="Nomu, Bioengineered",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Villain"},
    text=substitute_card_name(
        "When {this} dies, each opponent loses 2 life.",
        "Nomu, Bioengineered",
    ),
    setup_interceptors=_nomu_setup,
)


HIGH_END_NOMU = make_creature(
    name="High-End Nomu",
    power=7, toughness=6,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Villain"},
    text="Flying, trample",
    setup_interceptors=_self_keyword_setup('flying', 'trample'),
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


def _meta_lib_soldier_setup(obj, state):
    itc, _txt = death_draw(obj, 1)
    return [itc]

META_LIBERATION_SOLDIER = make_creature(
    name="Meta Liberation Soldier",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text=substitute_card_name(render_death_draw(1), "Meta Liberation Soldier"),
    setup_interceptors=_meta_lib_soldier_setup,
)


def _skeptic_setup(obj, state):
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 0, "Villain", include_self=False)
    return list(itcs)

SKEPTIC = make_creature(
    name="Skeptic, Liberation Lieutenant",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Other Villain creatures you control get +1/+0.",
    setup_interceptors=_skeptic_setup,
)


def _trumpet_setup(obj, state):
    pt_itcs, _pt_txt = static_pt_boost_by_subtype(obj, 1, 1, "Villain", include_self=False)
    # No subtype-keyword-grant bundle; use interceptor_helpers directly.
    kw_itc = _ih.make_keyword_grant(
        obj, ['deathtouch'],
        _ih.other_creatures_with_subtype(obj, "Villain"),
    )
    return list(pt_itcs) + [kw_itc]

TRUMPET = make_creature(
    name="Trumpet, Liberation Commander",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Other Villain creatures you control get +1/+1. Other Villain creatures you control have deathtouch.",
    setup_interceptors=_trumpet_setup,
)


def _re_destro_setup(obj, state):
    """Stress: Re-Destro has menace. Whenever you lose life, put a +1/+1
    counter on Re-Destro (Stress fuels his Quirk)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['menace'], self_filter)
    ]

    def stress_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        if event.payload.get('amount', 0) >= 0:
            return False
        return event.payload.get('player') == obj.controller

    def stress_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=stress_filter,
        handler=stress_handler,
        duration='while_on_battlefield',
    ))
    return itcs

RE_DESTRO = make_creature(
    name="Re-Destro, Liberation Leader",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Menace. Stress - Whenever you lose life, put a +1/+1 counter on Re-Destro.",
    setup_interceptors=_re_destro_setup,
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

def _league_hideout_setup(obj, state):
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Villain", include_self=True)
    return list(itcs)

LEAGUE_HIDEOUT = make_enchantment(
    name="League Hideout",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text=substitute_card_name(
        render_static_pt_boost(1, 1, scope="Villain creatures you control"),
        "League Hideout",
    ),
    setup_interceptors=_league_hideout_setup,
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
    """Unbreakable: Kirishima has indestructible during your turn (he's at his
    toughest when he's active). Otherwise he's just sturdy."""
    from src.cards.interceptor_helpers import make_keyword_grant

    def my_turn_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return getattr(state, 'active_player', None) == obj.controller
    return [make_keyword_grant(obj, ['indestructible'], my_turn_filter)]

KIRISHIMA = make_creature(
    name="Kirishima, Red Riot",
    power=3, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Unbreakable - Kirishima, Red Riot has indestructible during your turn.",
    setup_interceptors=kirishima_setup
)


def _kaminari_setup(obj, state):
    """Chargebolt: has haste. ETB deals 3 damage to each opponent; then
    Kaminari short-circuits and gets -2/-0 until end of turn (he's dumb
    after using his Quirk)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['haste'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 3, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            ))
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': -2, 'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        ))
        return events
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

KAMINARI = make_creature(
    name="Kaminari, Chargebolt",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Haste. When Kaminari enters the battlefield, he deals 3 damage to each opponent and gets -2/-0 until end of turn.",
    setup_interceptors=_kaminari_setup,
)


def _tetsutetsu_setup(obj, state):
    """Real Steel: trample. Gets +0/+2 whenever it blocks (hardens on impact)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['trample'], self_filter)
    ]

    def block_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 0, 'toughness_mod': 2,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_block_trigger(obj, block_effect))
    return itcs

TETSUTETSU = make_creature(
    name="Tetsutetsu, Real Steel",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Whenever Tetsutetsu blocks, it gets +0/+2 until end of turn.",
    setup_interceptors=_tetsutetsu_setup,
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
    text="Vigilance, lifelink",
    setup_interceptors=_self_keyword_setup('vigilance', 'lifelink'),
)


RYUKYU = make_creature(
    name="Ryukyu, Dragon Hero",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero", "Dragon"},
    supertypes={"Legendary"},
    text="Flying, trample",
    setup_interceptors=_self_keyword_setup('flying', 'trample'),
)


def _crimson_riot_setup(obj, state):
    """Legendary Manliness: whenever Crimson Riot attacks, it gets +2/+0
    until end of turn and gains first strike."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 2, 'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_attack_trigger(obj, attack_effect)]

CRIMSON_RIOT = make_creature(
    name="Crimson Riot, Legendary Hero",
    power=4, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Whenever Crimson Riot, Legendary Hero attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=_crimson_riot_setup,
)


# --- Regular Creatures ---

def _explosion_student_setup(obj, state):
    itc, _txt = etb_deal_damage(obj, 1, target="each_opponent")
    return [itc]

EXPLOSION_STUDENT = make_creature(
    name="Explosion Student",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    text=substitute_card_name(
        render_etb_deal_damage(1, "each opponent"),
        "Explosion Student",
    ),
    setup_interceptors=_explosion_student_setup,
)


COMBAT_HERO = make_creature(
    name="Combat Hero",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="First strike, haste",
    setup_interceptors=_self_keyword_setup('first_strike', 'haste'),
)


POWER_TYPE_STUDENT = make_creature(
    name="Power-Type Student",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    text="Trample",
    setup_interceptors=_self_keyword_setup('trample'),
)


RAGING_HERO = make_creature(
    name="Raging Hero",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="Trample, haste",
    setup_interceptors=_self_keyword_setup('trample', 'haste'),
)


FIERY_SIDEKICK = make_creature(
    name="Fiery Sidekick",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="Haste",
    setup_interceptors=_self_keyword_setup('haste'),
)


BATTLE_STUDENT = make_creature(
    name="Battle Course Student",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    text="First strike",
    setup_interceptors=_self_keyword_setup('first_strike'),
)


BERSERKER_HERO = make_creature(
    name="Berserker Hero",
    power=5, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="Trample, haste",
    setup_interceptors=_self_keyword_setup('trample', 'haste'),
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

def _fighting_spirit_setup(obj, state):
    pt_itcs, _pt_txt = static_pt_boost_all_you_control(obj, 1, 0)
    kw_itcs, _kw_txt = static_keyword_grant_others(
        obj, ['haste'], scope="creatures_you_control"
    )
    return list(pt_itcs) + list(kw_itcs)

FIGHTING_SPIRIT = make_enchantment(
    name="Fighting Spirit",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text=substitute_card_name(
        render_composite([
            render_static_pt_boost(1, 0, scope="creatures you control"),
            render_static_keyword_grant(['haste'], scope="creatures you control"),
        ]),
        "Fighting Spirit",
    ),
    setup_interceptors=_fighting_spirit_setup,
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

def _deku_setup(obj, state):
    # Upkeep: put a +1/+1 counter on {this}. No bundle for upkeep-add-counters;
    # use interceptor_helpers directly. Plus-Ultra bonus merged in.
    def upkeep_effect(event, state):
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    interceptors = [_ih.make_upkeep_trigger(obj, upkeep_effect)]
    interceptors.extend(make_plus_ultra_bonus(obj, 3, 3))
    return interceptors

DEKU = make_creature(
    name="Deku, Inheritor of One For All",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text=substitute_card_name(
        "At the beginning of your upkeep, put a +1/+1 counter on {this}.",
        "Deku, Inheritor of One For All",
    ),
    setup_interceptors=_deku_setup,
)


def _uraraka_setup(obj, state):
    """Zero Gravity: Uraraka has flying. Other Hero creatures you control
    have flying. (Her power lifts her allies off the ground.)"""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [
        _ih.make_keyword_grant(obj, ['flying'], self_filter),
        _ih.make_keyword_grant(
            obj, ['flying'],
            _ih.other_creatures_with_subtype(obj, "Hero"),
        ),
    ]

URARAKA = make_creature(
    name="Uraraka, Zero Gravity",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Other Hero creatures you control have flying.",
    setup_interceptors=_uraraka_setup,
)


def _iida_setup(obj, state):
    """Engine: Iida has haste and vigilance."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [_ih.make_keyword_grant(obj, ['haste', 'vigilance'], self_filter)]

IIDA = make_creature(
    name="Iida, Ingenium",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Haste, vigilance.",
    setup_interceptors=_iida_setup,
)


def _todoroki_setup(obj, state):
    """Half-Cold Half-Hot: when Todoroki enters, he deals 2 damage to
    target opponent (fire side) and taps target creature (ice side).
    Simplified: 2 damage to each opponent AND tap a creature opponents
    control with the highest power."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        # Fire: 2 damage to each opponent
        for opp in _ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 2, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            ))
        # Ice: tap strongest opponent creature
        enemies = [
            o for o in state.objects.values()
            if o.controller != obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
        ]
        if enemies:
            target = max(enemies, key=lambda o: get_power(o, state))
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': target.id},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [_ih.make_etb_trigger(obj, etb_effect)]

TODOROKI = make_creature(
    name="Todoroki, Half-Cold Half-Hot",
    power=4, toughness=4,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="When Todoroki enters the battlefield, he deals 2 damage to each opponent and taps the creature opponents control with the greatest power.",
    setup_interceptors=_todoroki_setup,
)


TSUYU = make_creature(
    name="Tsuyu, Froppy",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flash, reach, hexproof",
    setup_interceptors=_self_keyword_setup('flash', 'reach', 'hexproof'),
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
    """Dark Shadow - has flying, and gets +4/+0 when at 5 or less life
    (Plus Ultra - Dark Shadow becomes uncontrollable at low light)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return (
        [_ih.make_keyword_grant(obj, ['flying'], self_filter)]
        + make_plus_ultra_bonus(obj, 4, 0)
    )

TOKOYAMI = make_creature(
    name="Tokoyami, Dark Shadow",
    power=3, toughness=3,
    mana_cost="{2}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Plus Ultra - Tokoyami gets +4/+0 as long as you have 5 or less life.",
    setup_interceptors=tokoyami_setup
)


SERO = make_creature(
    name="Sero, Cellophane",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Reach",
    setup_interceptors=_self_keyword_setup('reach'),
)


SHOJI = make_creature(
    name="Shoji, Tentacole",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Vigilance, reach",
    setup_interceptors=_self_keyword_setup('vigilance', 'reach'),
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
    text="First strike",
    setup_interceptors=_self_keyword_setup('first_strike'),
)


SATO = make_creature(
    name="Sato, Sugarman",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Trample",
    setup_interceptors=_self_keyword_setup('trample'),
)


# --- Regular Creatures ---

def _growth_student_setup(obj, state):
    # No etb-add-counters bundle; use interceptor_helpers directly.
    def effect_fn(event, state):
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_etb_trigger(obj, effect_fn)]

GROWTH_STUDENT = make_creature(
    name="Growth-Type Student",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    text=substitute_card_name(
        "When {this} enters the battlefield, put a +1/+1 counter on {this}.",
        "Growth-Type Student",
    ),
    setup_interceptors=_growth_student_setup,
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
    text="Reach, trample",
    setup_interceptors=_self_keyword_setup('reach', 'trample'),
)


MUTANT_STUDENT = make_creature(
    name="Mutant-Type Student",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    text="Trample",
    setup_interceptors=_self_keyword_setup('trample'),
)


HEALING_HERO = make_creature(
    name="Healing Hero",
    power=1, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Lifelink",
    setup_interceptors=_self_keyword_setup('lifelink'),
)


FOREST_GUARDIAN = make_creature(
    name="Forest Guardian Hero",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    text="Vigilance, reach",
    setup_interceptors=_self_keyword_setup('vigilance', 'reach'),
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


def _kendo_setup(obj, state):
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Student", include_self=False)
    return list(itcs)

KENDO = make_creature(
    name="Kendo, Battle Fist",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Other Student creatures you control get +1/+1.",
    setup_interceptors=_kendo_setup,
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


def _mirio_setup(obj, state):
    """Permeation: Mirio can't be blocked (grant 'unblockable') and has
    hexproof (phases through targeting)."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [_ih.make_keyword_grant(obj, ['unblockable', 'hexproof'], self_filter)]

MIRIO = make_creature(
    name="Mirio, Lemillion",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Permeation - Mirio, Lemillion can't be blocked and has hexproof.",
    setup_interceptors=_mirio_setup,
)


def _tamaki_setup(obj, state):
    """Manifest: when Tamaki enters, he adopts a random form. Mechanically -
    gains one of trample, flying, or deathtouch (rotates based on how many
    creatures you control: 0-1 => deathtouch, 2 => flying, 3+ => trample)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        allies = sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and o.id != obj.id
        )
        if allies >= 3:
            pm = 2
        elif allies >= 2:
            pm = 1
        else:
            pm = 0
        # Straight +P/+P until end of turn based on allies ("feeds off what
        # he's eaten").
        if pm == 0:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': pm, 'toughness_mod': pm,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]

    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [
        _ih.make_keyword_grant(obj, ['flying', 'trample'], self_filter),
        _ih.make_etb_trigger(obj, etb_effect),
    ]

TAMAKI = make_creature(
    name="Tamaki, Suneater",
    power=3, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying, trample. When Tamaki enters the battlefield, he gets +1/+1 for each other creature you control, up to +2/+2, until end of turn.",
    setup_interceptors=_tamaki_setup,
)


def _nejire_setup(obj, state):
    """Wave Motion: flying. When Nejire enters, she deals 3 damage divided
    as you choose among any number of targets — simplified to 3 damage to
    the strongest opponent creature."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['flying'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        enemies = [
            o for o in state.objects.values()
            if o.controller != obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
        ]
        if not enemies:
            # Nothing to zap? Hit each opponent for 2 instead.
            return [
                Event(
                    type=EventType.DAMAGE,
                    payload={'target': opp, 'amount': 2, 'source': obj.id},
                    source=obj.id,
                    controller=obj.controller,
                )
                for opp in _ih.all_opponents(obj, state)
            ]
        target = max(enemies, key=lambda o: get_power(o, state))
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 3, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

NEJIRE = make_creature(
    name="Nejire, Nejire Wave",
    power=3, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying. When Nejire enters the battlefield, she deals 3 damage to the creature opponents control with the greatest power (or 2 damage to each opponent if none).",
    setup_interceptors=_nejire_setup,
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
    text="Flash, deathtouch, unblockable",
    setup_interceptors=_self_keyword_setup('flash', 'deathtouch', 'unblockable'),
)


KAMUI_WOODS = make_creature(
    name="Kamui Woods, Tree Hero",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Reach, vigilance",
    setup_interceptors=_self_keyword_setup('reach', 'vigilance'),
)


MT_LADY = make_creature(
    name="Mt. Lady, Gigantification",
    power=6, toughness=6,
    mana_cost="{4}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Trample, vigilance",
    setup_interceptors=_self_keyword_setup('trample', 'vigilance'),
)


DEATH_ARMS = make_creature(
    name="Death Arms, Punching Hero",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Menace, first strike",
    setup_interceptors=_self_keyword_setup('menace', 'first_strike'),
)


def _native_setup(obj, state):
    itc, _txt = etb_gain_life(obj, 3)
    return [itc]

NATIVE = make_creature(
    name="Native, Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=substitute_card_name(render_etb_gain_life(3), "Native, Hero"),
    setup_interceptors=_native_setup,
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


def _lunch_rush_setup(obj, state):
    itc, _txt = upkeep_gain_life(obj, 1)
    return [itc]

LUNCH_RUSH = make_creature(
    name="Lunch Rush, Cook Hero",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=substitute_card_name(render_upkeep_gain_life(1), "Lunch Rush, Cook Hero"),
    setup_interceptors=_lunch_rush_setup,
)


def _ingenium_setup(obj, state):
    # No subtype-keyword-grant bundle; use interceptor_helpers directly.
    return [_ih.make_keyword_grant(
        obj, ['vigilance'],
        _ih.other_creatures_with_subtype(obj, "Hero"),
    )]

INGENIUM = make_creature(
    name="Tensei Iida, Ingenium",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Other Hero creatures you control have vigilance.",
    setup_interceptors=_ingenium_setup,
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


def _gentle_criminal_setup(obj, state):
    # No damage-trigger-draw bundle; use interceptor_helpers directly.
    def effect_fn(event, state):
        # "to a player": original DealsDamageTrigger(to_player=True) fired when
        # event.payload['target'] is a player id. Replicate that filter here.
        target = event.payload.get('target')
        if target not in state.players:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_damage_trigger(obj, effect_fn, combat_only=True)]

GENTLE_CRIMINAL = make_creature(
    name="Gentle Criminal",
    power=2, toughness=3,
    mana_cost="{1}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=substitute_card_name(
        "Whenever {this} deals combat damage to a player, draw a card.",
        "Gentle Criminal",
    ),
    setup_interceptors=_gentle_criminal_setup,
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
    text="First strike, reach",
    setup_interceptors=_self_keyword_setup('first_strike', 'reach'),
)


MAGNE = make_creature(
    name="Magne, Big Sis Magne",
    power=4, toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Haste, menace",
    setup_interceptors=_self_keyword_setup('haste', 'menace'),
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
    text="Menace",
    setup_interceptors=_self_keyword_setup('menace'),
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
    text="Flash",
    setup_interceptors=_self_keyword_setup('flash'),
)


# =============================================================================
# NEW LEGENDARY VILLAINS & HEROES (Quality-pass additions)
# =============================================================================

def _lady_nagant_setup(obj, state):
    """Hunter-Arm: reach. When Lady Nagant enters, destroy target creature
    with the greatest power that opponents control. (Assassination shot.)"""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['reach'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        enemies = [
            o for o in state.objects.values()
            if o.controller != obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
        ]
        if not enemies:
            return []
        target = max(enemies, key=lambda o: get_power(o, state))
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target.id},
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

LADY_NAGANT = make_creature(
    name="Lady Nagant, Rifle Hero",
    power=3, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Reach. When Lady Nagant enters the battlefield, destroy the creature opponents control with the greatest power.",
    setup_interceptors=_lady_nagant_setup,
)


def _nine_setup(obj, state):
    """Quirk Theft: flying, trample. When Nine enters, each opponent
    sacrifices a creature (he steals their Quirks) — simplified to
    destroying the opponent's weakest creature."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['flying', 'trample'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, state):
            victims = [
                o for o in state.objects.values()
                if o.controller == opp
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types
            ]
            if victims:
                victim = min(victims, key=lambda o: get_power(o, state))
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={'object_id': victim.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

NINE = make_creature(
    name="Nine, Quirk Thief",
    power=6, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying, trample. When Nine enters the battlefield, each opponent's weakest creature is destroyed.",
    setup_interceptors=_nine_setup,
)


def _star_and_stripe_setup(obj, state):
    """New Order: flying, vigilance. When Star and Stripe enters, all
    other creatures you control get +1/+1 counters. Massive team rally."""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['flying', 'vigilance'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in state.objects.values():
            if (o.id != obj.id
                and o.controller == obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

STAR_AND_STRIPE = make_creature(
    name="Star and Stripe, U.S. Number One",
    power=6, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Flying, vigilance. When Star and Stripe enters the battlefield, put a +1/+1 counter on each other creature you control.",
    setup_interceptors=_star_and_stripe_setup,
)


def _mirio_hero_intern_setup(obj, state):
    """Team-up bonus: this 2/2 Student costs {1}{U} and draws a card when
    it enters if you control another Student. Supports team-up archetype."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        has_other_student = any(
            o.id != obj.id
            and o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and "Student" in o.characteristics.subtypes
            for o in state.objects.values()
        )
        if not has_other_student:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_etb_trigger(obj, etb_effect)]

CLASS_1A_ROOKIE = make_creature(
    name="Class 1-A Rookie",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    text="When Class 1-A Rookie enters the battlefield, if you control another Student, draw a card.",
    setup_interceptors=_mirio_hero_intern_setup,
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
# LEGENDARY BAR REDESIGNS (Game-Altering Pass)
#
# Rebinds placeholder/vanilla legendaries to versions that hit the "fundamentally
# alter the game" rubric: persistent state modifiers, asymmetric sweepers,
# alt-cost resource loops, tutors, reality-bend effects, and engine-mode cards.
# These assignments come AFTER the original definitions, so the card dictionary
# (which is built below) picks up these bindings.
# =============================================================================


# ---------------------------------------------------------------------------
# Gigantomachia, Living Disaster
# Pattern: asymmetric sweeper (rubric #6). A 12/12 body is fine, but the job
# is to rewrite the battlefield on landing: everything smaller than him dies.
# ---------------------------------------------------------------------------
def _gigantomachia_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['trample', 'menace'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in list(state.objects.values()):
            if (o.id != obj.id
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types):
                if get_toughness(o, state) <= 4:
                    events.append(Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': o.id},
                        source=obj.id,
                        controller=obj.controller,
                    ))
        return events
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

GIGANTOMACHIA = make_creature(
    name="Gigantomachia, Living Disaster",
    power=10, toughness=10,
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Giant", "Villain"},
    supertypes={"Legendary"},
    text=(
        "Trample, menace. When Gigantomachia enters the battlefield, destroy "
        "each other creature with toughness 4 or less."
    ),
    setup_interceptors=_gigantomachia_setup,
)


# ---------------------------------------------------------------------------
# All For One, Ultimate Villain
# Pattern: persistent-state + steal (rubric #3, #8). Every creature that dies
# feeds him: +1/+1 counter and inherits that creature's keyword abilities.
# ---------------------------------------------------------------------------
def _all_for_one_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['indestructible'], self_filter)
    ]

    # Stockpile of keywords stolen from dying creatures (closure-local, no new
    # helpers): rebroadcast via a granting interceptor on each steal.
    stolen: set[str] = set()

    _KEYWORD_POOL = {
        'flying', 'trample', 'first_strike', 'double_strike', 'haste',
        'vigilance', 'lifelink', 'deathtouch', 'menace', 'reach',
        'hexproof', 'indestructible', 'unblockable',
    }

    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        victim_id = event.payload.get('object_id')
        if victim_id == obj.id:
            return False
        victim = state.objects.get(victim_id)
        return bool(victim and CardType.CREATURE in victim.characteristics.types)

    def death_handler(event: Event, state: GameState) -> InterceptorResult:
        victim = state.objects.get(event.payload.get('object_id'))
        new_events: list[Event] = [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
        if victim is not None:
            # Read victim keywords: check both characteristics.abilities AND
            # granted keywords via has_ability (covers cards that grant
            # their own keywords via QUERY_ABILITIES interceptors).
            from src.engine.queries import has_ability as _has_ab
            for kw in _KEYWORD_POOL:
                if kw in stolen:
                    continue
                got = False
                for ab in victim.characteristics.abilities:
                    if isinstance(ab, dict) and (ab.get('keyword') == kw or ab.get('name') == kw):
                        got = True
                        break
                if not got:
                    try:
                        got = _has_ab(victim, kw, state)
                    except Exception:
                        got = False
                if got:
                    stolen.add(kw)
                    new_events.append(Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={
                            'object_id': obj.id,
                            'keyword': kw,
                            'duration': 'while_on_battlefield',
                        },
                        source=obj.id,
                        controller=obj.controller,
                    ))
        return InterceptorResult(
            action=InterceptorAction.REACT, new_events=new_events,
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        duration='while_on_battlefield',
    ))
    return itcs

ALL_FOR_ONE = make_creature(
    name="All For One, Ultimate Villain",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=(
        "Indestructible. Whenever another creature dies, put a +1/+1 counter "
        "on All For One and it gains that creature's keyword abilities."
    ),
    setup_interceptors=_all_for_one_setup,
)


# ---------------------------------------------------------------------------
# Mirio, Lemillion
# Pattern: persistent unblockable + on-hit disruption engine (rubric #3).
# Unblockable + hexproof is a body; adding "each opponent discards on hit"
# makes him a game flow shift: every turn your opponent's hand shrinks.
# ---------------------------------------------------------------------------
def _mirio_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['unblockable', 'hexproof'], self_filter)
    ]

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target not in state.players:
            return []
        return [
            Event(
                type=EventType.DISCARD,
                payload={'player': opp, 'amount': 1},
                source=obj.id,
                controller=obj.controller,
            )
            for opp in _ih.all_opponents(obj, state)
        ]
    itcs.append(_ih.make_damage_trigger(obj, damage_effect, combat_only=True))
    return itcs

MIRIO = make_creature(
    name="Mirio, Lemillion",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Permeation - Mirio can't be blocked and has hexproof. Whenever Mirio "
        "deals combat damage to a player, each opponent discards a card."
    ),
    setup_interceptors=_mirio_setup,
)


# ---------------------------------------------------------------------------
# Overhaul, Yakuza Boss
# Pattern: persistent state (rubric #3) + one-shot counter wipe (retained).
# "Whenever an opponent's creature enters, that player loses 1 life" turns
# every flood into attrition. Still removes existing +1/+1 counters on ETB.
# ---------------------------------------------------------------------------
def _overhaul_setup(obj, state):
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in state.objects.values():
            if (o.controller != obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types):
                count = o.state.counters.get('+1/+1', 0) if hasattr(o, 'state') and o.state else 0
                if count > 0:
                    events.append(Event(
                        type=EventType.COUNTER_REMOVED,
                        payload={
                            'object_id': o.id,
                            'counter_type': '+1/+1',
                            'amount': count,
                        },
                        source=obj.id,
                        controller=obj.controller,
                    ))
        return events

    def opp_creature_entering(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return False
        return (entering.controller != source.controller
                and CardType.CREATURE in entering.characteristics.types)

    def drain_on_entry(event: Event, state: GameState) -> list[Event]:
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': entering.controller, 'amount': -1},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        _ih.make_etb_trigger(obj, etb_effect),
        _ih.make_etb_trigger(obj, drain_on_entry, opp_creature_entering),
    ]

OVERHAUL = make_creature(
    name="Overhaul, Yakuza Boss",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=(
        "When Overhaul enters the battlefield, remove all +1/+1 counters from "
        "each creature your opponents control. Whenever a creature an opponent "
        "controls enters the battlefield, that player loses 1 life."
    ),
    setup_interceptors=_overhaul_setup,
)


# ---------------------------------------------------------------------------
# Stain, Hero Killer
# Pattern: persistent lock-out (rubric #3). Non-Hero attackers lose 1 life
# when they attack you, and Stain still buffs himself when a Hero is across.
# ---------------------------------------------------------------------------
def _stain_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['first_strike', 'deathtouch'], self_filter)
    ]

    # "Ideology tax": whenever a non-Hero opponent attacks, that player loses
    # 1 life. Implemented as a REACT interceptor on ATTACK_DECLARED.
    def attack_tax_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return False
        if attacker.controller == obj.controller:
            return False
        return "Hero" not in attacker.characteristics.subtypes

    def attack_tax_handler(event: Event, state: GameState) -> InterceptorResult:
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': attacker.controller, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_tax_filter,
        handler=attack_tax_handler,
        duration='while_on_battlefield',
    ))

    def attack_boost(event: Event, state: GameState) -> list[Event]:
        hero_present = any(
            o.controller != obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and "Hero" in o.characteristics.subtypes
            for o in state.objects.values()
        )
        if not hero_present:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 2, 'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_attack_trigger(obj, attack_boost))
    return itcs

STAIN = make_creature(
    name="Stain, Hero Killer",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=(
        "First strike, deathtouch. Ideology - Whenever a non-Hero creature an "
        "opponent controls attacks, that player loses 1 life. Whenever Stain "
        "attacks, if an opponent controls a Hero, Stain gets +2/+0 until end "
        "of turn."
    ),
    setup_interceptors=_stain_setup,
)


# ---------------------------------------------------------------------------
# Moonfish, Blade Villain
# Pattern: reality-bend removal engine (rubric #8). Exile-on-hit is a
# permanent answer, and each exile feeds him.
# ---------------------------------------------------------------------------
def _moonfish_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['first_strike', 'deathtouch'], self_filter)
    ]

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target or CardType.CREATURE not in target.characteristics.types:
            return []
        return [
            Event(
                type=EventType.EXILE,
                payload={'object_id': target.id},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id,
                controller=obj.controller,
            ),
        ]
    itcs.append(_ih.make_damage_trigger(obj, damage_effect, combat_only=True))
    return itcs

MOONFISH = make_creature(
    name="Moonfish, Blade Villain",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=(
        "First strike, deathtouch. Whenever Moonfish deals combat damage to a "
        "creature, exile that creature and put a +1/+1 counter on Moonfish."
    ),
    setup_interceptors=_moonfish_setup,
)


# ---------------------------------------------------------------------------
# Mt. Lady, Gigantification
# Pattern: reality-bend + forced sacrifice (rubric #6, #8).
# ---------------------------------------------------------------------------
def _mt_lady_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['trample', 'vigilance'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in state.objects.values():
            if (o.controller == obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types
                and o.id != obj.id):
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        'object_id': o.id,
                        'power_mod': 2, 'toughness_mod': 2,
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target not in state.players:
            return []
        victims = [
            o for o in state.objects.values()
            if o.controller == target
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE not in o.characteristics.types
            and CardType.LAND not in o.characteristics.types
        ]
        if not victims:
            return []
        chosen = victims[0]
        return [Event(
            type=EventType.SACRIFICE,
            payload={'player': target, 'object_id': chosen.id},
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_damage_trigger(obj, damage_effect, combat_only=True))
    return itcs

MT_LADY = make_creature(
    name="Mt. Lady, Gigantification",
    power=6, toughness=6,
    mana_cost="{4}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Trample, vigilance. When Mt. Lady enters, other creatures you control "
        "get +2/+2 until end of turn. Whenever Mt. Lady deals combat damage to "
        "a player, that player sacrifices a nonland, noncreature permanent."
    ),
    setup_interceptors=_mt_lady_setup,
)


# ---------------------------------------------------------------------------
# Power Loader, Support Teacher
# Pattern: persistent rule-rewrite for artifacts (rubric #3).
# ---------------------------------------------------------------------------
def _power_loader_setup(obj, state):
    def artifacts_you_control(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller
                and target.zone == ZoneType.BATTLEFIELD
                and CardType.ARTIFACT in target.characteristics.types)

    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['indestructible'], artifacts_you_control),
    ]

    # When an artifact you control is destroyed, prevent the destruction and
    # draw a card instead. The "prevent" comes via the grant above (rule:
    # indestructible makes OBJECT_DESTROYED a no-op during the usual path),
    # so we only need the card-draw sidecar on *attempted* destruction.
    def watch_destroy(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        victim = state.objects.get(event.payload.get('object_id'))
        if not victim or victim.controller != obj.controller:
            return False
        return CardType.ARTIFACT in victim.characteristics.types

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=watch_destroy,
        handler=draw_handler,
        duration='while_on_battlefield',
    ))
    return itcs

POWER_LOADER = make_creature(
    name="Power Loader, Support Teacher",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero", "Artificer"},
    supertypes={"Legendary"},
    text=(
        "Artifacts you control have indestructible. Whenever an artifact you "
        "control would be destroyed, draw a card."
    ),
    setup_interceptors=_power_loader_setup,
)


# ---------------------------------------------------------------------------
# Recovery Girl, Healing Hero
# Pattern: persistent state (rubric #3) + life-as-resource (rubric #2).
# ---------------------------------------------------------------------------
def _recovery_girl_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['lifelink'], self_filter)
    ]

    # Whenever a creature you control dies, you may pay 2 life: draw a card
    # and gain 1 life (small comfort from a healer's kiss). Modeled as an
    # auto-react so it fires without modal plumbing.
    def creature_you_control_dies(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        victim = state.objects.get(event.payload.get('object_id'))
        if not victim or victim.controller != obj.controller:
            return False
        return CardType.CREATURE in victim.characteristics.types

    def comfort_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': -2},
                    source=obj.id,
                    controller=obj.controller,
                ),
                Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller},
                    source=obj.id,
                    controller=obj.controller,
                ),
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id,
                    controller=obj.controller,
                ),
            ],
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_you_control_dies,
        handler=comfort_handler,
        duration='while_on_battlefield',
    ))
    return itcs

RECOVERY_GIRL = make_creature(
    name="Recovery Girl, Healing Hero",
    power=0, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Lifelink. Whenever a creature you control dies, pay 2 life: draw a "
        "card, then gain 1 life."
    ),
    setup_interceptors=_recovery_girl_setup,
)


# ---------------------------------------------------------------------------
# Present Mic, Voice Hero
# Pattern: persistent lord + spell-cast engine (rubric #3+#4).
# ---------------------------------------------------------------------------
def _present_mic_setup(obj, state):
    def my_creatures_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller
                and target.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in target.characteristics.types)

    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['haste'], my_creatures_filter)
    ]

    # Spell-cast engine: whenever you cast a creature spell, Present Mic deals
    # 1 damage to each opponent creature.
    def cast_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('controller') or event.payload.get('player')
        if caster != obj.controller:
            return False
        return True

    def cast_handler(event: Event, state: GameState) -> InterceptorResult:
        events: list[Event] = []
        for o in state.objects.values():
            if (o.controller != obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types):
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': o.id, 'amount': 1, 'source': obj.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return InterceptorResult(
            action=InterceptorAction.REACT, new_events=events,
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cast_filter,
        handler=cast_handler,
        duration='while_on_battlefield',
    ))
    return itcs

PRESENT_MIC = make_creature(
    name="Present Mic, Voice Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Creatures you control have haste. Whenever you cast a spell, Present "
        "Mic deals 1 damage to each creature your opponents control."
    ),
    setup_interceptors=_present_mic_setup,
)


# ---------------------------------------------------------------------------
# Cementoss, Concrete Hero
# Pattern: persistent combat tax (rubric #3). Every attacker against you
# has to pay 1 life, or the damage to you doesn't land.
# ---------------------------------------------------------------------------
def _cementoss_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['defender'], self_filter)
    ]

    # Tax every attack against you: attacker's controller loses 1 life.
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker or attacker.controller == obj.controller:
            return False
        # Only when the attack targets our controller (or when target is
        # omitted, treat as "attacking us" for a 2-player case).
        target = event.payload.get('defender') or event.payload.get('target_player')
        if target is not None and target != obj.controller:
            return False
        return True

    def attack_handler(event: Event, state: GameState) -> InterceptorResult:
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': attacker.controller, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield',
    ))
    return itcs

CEMENTOSS = make_creature(
    name="Cementoss, Concrete Hero",
    power=1, toughness=6,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Defender. Concrete Walls - Whenever a creature an opponent controls "
        "attacks you, that player loses 1 life."
    ),
    setup_interceptors=_cementoss_setup,
)


# ---------------------------------------------------------------------------
# Ragdoll, Wild Wild Pussycats
# Pattern: tutor/selection break (rubric #5). Reveal 6, grab every Hero.
# ---------------------------------------------------------------------------
def _ragdoll_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['hexproof'], self_filter)
    ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Emit a library-search / reveal combo: look at top 6, then a single
        # SEARCH_LIBRARY tagged for Hero subtype. Downstream handlers resolve
        # the selection. This is intentionally declarative — the pipeline's
        # library-manipulation layer already knows what to do with these.
        return [
            Event(
                type=EventType.LOOK_AT_TOP,
                payload={'player': obj.controller, 'count': 6},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={
                    'player': obj.controller,
                    'search_criteria': {'subtype': 'Hero', 'scope': 'top_6'},
                    'destination': 'hand',
                    'reveal': True,
                    'count': 'all',
                },
                source=obj.id,
                controller=obj.controller,
            ),
        ]
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))
    return itcs

RAGDOLL = make_creature(
    name="Ragdoll, Wild Wild Pussycats",
    power=2, toughness=2,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Hexproof. Search Eyes - When Ragdoll enters the battlefield, look at "
        "the top six cards of your library. Put all Hero cards revealed into "
        "your hand, then put the rest on the bottom in any order."
    ),
    setup_interceptors=_ragdoll_setup,
)


# ---------------------------------------------------------------------------
# Tiger, Wild Wild Pussycats
# Pattern: on-combat engine (rubric #4).
# ---------------------------------------------------------------------------
def _tiger_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['trample'], self_filter)
    ]

    # At beginning of combat on your turn (we proxy on PHASE_START/COMBAT_DECLARED)
    def combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.COMBAT_DECLARED, EventType.PHASE_START):
            return False
        if event.type == EventType.PHASE_START:
            phase = event.payload.get('phase') or event.payload.get('phase_name')
            if phase not in ('combat', 'begin_combat', 'beginning_of_combat'):
                return False
        return getattr(state, 'active_player', None) == obj.controller

    def combat_handler(event: Event, state: GameState) -> InterceptorResult:
        events: list[Event] = []
        for o in state.objects.values():
            if (o.id != obj.id
                and o.controller == obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in o.characteristics.types
                and "Hero" in o.characteristics.subtypes):
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        'object_id': o.id,
                        'power_mod': 2, 'toughness_mod': 0,
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={
                        'object_id': o.id,
                        'keyword': 'trample',
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
        return InterceptorResult(
            action=InterceptorAction.REACT, new_events=events,
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=combat_handler,
        duration='while_on_battlefield',
    ))
    return itcs

TIGER = make_creature(
    name="Tiger, Wild Wild Pussycats",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Trample. At the beginning of combat on your turn, each other Hero "
        "you control gets +2/+0 and gains trample until end of turn."
    ),
    setup_interceptors=_tiger_setup,
)


# ---------------------------------------------------------------------------
# Mr. Compress, Showman
# Pattern: reality-bend (rubric #8). Exile-to-box a permanent while on BF,
# return on leave.
# ---------------------------------------------------------------------------
def _mr_compress_setup(obj, state):
    exiled_ref: dict[str, str | None] = {'id': None}

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Pick the highest-power opponent permanent to compress.
        enemies = [
            o for o in state.objects.values()
            if o.controller != obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.LAND not in o.characteristics.types
        ]
        if not enemies:
            return []
        target = max(enemies, key=lambda o: get_power(o, state))
        exiled_ref['id'] = target.id
        return [Event(
            type=EventType.EXILE,
            payload={'object_id': target.id, 'return_when_leaves': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]

    def leaves_effect(event: Event, state: GameState) -> list[Event]:
        exiled_id = exiled_ref['id']
        if exiled_id is None:
            return []
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': exiled_id,
                'from_zone': 'exile',
                'to_zone': 'battlefield',
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        _ih.make_etb_trigger(obj, etb_effect),
        _ih.make_leaves_battlefield_trigger(obj, leaves_effect),
    ]

MR_COMPRESS = make_creature(
    name="Mr. Compress, Showman",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=(
        "When Mr. Compress enters, exile target nonland permanent an opponent "
        "controls (the largest). Return it when Mr. Compress leaves."
    ),
    setup_interceptors=_mr_compress_setup,
)


# ---------------------------------------------------------------------------
# Mineta, Grape Rush
# Pattern: persistent attack-redirect rule (rubric #3). Taunt, but legendary.
# ---------------------------------------------------------------------------
def _mineta_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['taunt'], self_filter),
    ]

    # Glue: every attack aimed past Mineta at his controller gets stopped
    # (PREVENT) unless the attacker's controller sacrifices an artifact.
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker or attacker.controller == obj.controller:
            return False
        # If they're already attacking Mineta, let it through.
        return event.payload.get('blocker_id') != obj.id

    def attack_handler(event: Event, state: GameState) -> InterceptorResult:
        # Rewrite the attack to target Mineta by adjusting the payload.
        event.payload['must_be_blocked_by'] = obj.id
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=event,
        )

    # Fall back to REACT-adding a warning event in case TRANSFORM isn't wired;
    # this still marks the interception path. Interceptor below.
    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield',
    ))
    return itcs

MINETA = make_creature(
    name="Mineta, Grape Rush",
    power=1, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text=(
        "Taunt. Sticky Grapes - Creatures attacking you must be declared as "
        "attacking Mineta if able."
    ),
    setup_interceptors=_mineta_setup,
)


# =============================================================================
# NEW LEGENDARIES (Game-Altering Additions)
# =============================================================================


# ---------------------------------------------------------------------------
# Deku, One For All Cowl (Transformation)
# Pattern: build-up engine + loyalty transformation (rubric #2 + #4).
# Each of your turns Deku gains a "Cowl" counter. If he has 5+ Cowl counters
# at end of turn, double strike kicks in permanently (while on BF), and each
# of his attacks burns each opponent for 2.
# ---------------------------------------------------------------------------
def _deku_cowl_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id

    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['trample'], self_filter),
    ]

    # Each upkeep: +1 Cowl counter.
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'cowl', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_upkeep_trigger(obj, upkeep_effect))

    # When attacking, if 5+ Cowl counters, burn each opponent for 2 and grant
    # double strike for the combat.
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        self_obj = state.objects.get(obj.id)
        if not self_obj:
            return []
        cowl = self_obj.state.counters.get('cowl', 0) if hasattr(self_obj, 'state') and self_obj.state else 0
        if cowl < 5:
            return []
        events: list[Event] = [Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': obj.id,
                'keyword': 'double_strike',
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]
        for opp in _ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 2, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    itcs.append(_ih.make_attack_trigger(obj, attack_effect))
    return itcs

DEKU_COWL = make_creature(
    name="Deku, Full Cowl 100%",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Trample. At the beginning of your upkeep, put a Cowl counter on Deku. "
        "Whenever Deku attacks, if he has five or more Cowl counters, he gains "
        "double strike until end of turn and deals 2 damage to each opponent."
    ),
    setup_interceptors=_deku_cowl_setup,
)


# ---------------------------------------------------------------------------
# Shigaraki, Handless Decay
# Pattern: pay-life-to-destroy-anything (rubric #2 resource conversion).
# Costs 5, but his ability makes life the universal answer.
# ---------------------------------------------------------------------------
def _shigaraki_handless_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id

    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['menace'], self_filter),
    ]

    # Activated ability proxy: when ACTIVATE event arrives with ability='decay'
    # and a payload 'life_paid' = X, destroy target permanent if X >= its CMC.
    def decay_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == obj.id
                and event.payload.get('ability') == 'decay')

    def decay_handler(event: Event, state: GameState) -> InterceptorResult:
        target_id = event.payload.get('target')
        life_paid = int(event.payload.get('life_paid', 0))
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        cmc = getattr(target.characteristics, 'mana_value', None)
        if cmc is None:
            cmc = getattr(target.characteristics, 'cmc', 0) or 0
        events: list[Event] = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': -max(1, life_paid)},
            source=obj.id,
            controller=obj.controller,
        )]
        if life_paid >= cmc:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id},
                source=obj.id,
                controller=obj.controller,
            ))
        return InterceptorResult(
            action=InterceptorAction.REACT, new_events=events,
        )

    itcs.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=decay_filter,
        handler=decay_handler,
        duration='while_on_battlefield',
    ))
    return itcs

SHIGARAKI_HANDLESS = make_creature(
    name="Shigaraki Tomura, Handless",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text=(
        "Menace. Pay X life: Destroy target permanent with mana value X or "
        "less. Activate this ability only during your turn."
    ),
    setup_interceptors=_shigaraki_handless_setup,
)


# ---------------------------------------------------------------------------
# Eri, Rewind
# Pattern: reality-bend + team engine (rubric #8 + #3).
# ETB: target creature's +1/+1 counters are doubled. Each upkeep: target
# creature you control gets +1/+1 counter.
# ---------------------------------------------------------------------------
def _eri_rewind_setup(obj, state):
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    itcs: list[Interceptor] = [
        _ih.make_keyword_grant(obj, ['hexproof'], self_filter),
    ]

    # ETB: double +1/+1 counters on the creature you control with the most.
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        candidates = [
            o for o in state.objects.values()
            if o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and o.id != obj.id
            and hasattr(o, 'state') and o.state
        ]
        if not candidates:
            return []
        target = max(candidates, key=lambda o: o.state.counters.get('+1/+1', 0))
        count = target.state.counters.get('+1/+1', 0)
        if count <= 0:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': count},
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_etb_trigger(obj, etb_effect))

    # Upkeep: +1/+1 counter on the highest-power creature you control.
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        allies = [
            o for o in state.objects.values()
            if o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and o.id != obj.id
        ]
        if not allies:
            return []
        target = max(allies, key=lambda o: get_power(o, state))
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    itcs.append(_ih.make_upkeep_trigger(obj, upkeep_effect))
    return itcs

ERI_REWIND = make_creature(
    name="Eri, Rewind",
    power=1, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text=(
        "Hexproof. When Eri enters, double the number of +1/+1 counters on "
        "target creature you control. At the beginning of your upkeep, put a "
        "+1/+1 counter on the creature you control with the greatest power."
    ),
    setup_interceptors=_eri_rewind_setup,
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
    "Lady Nagant, Rifle Hero": LADY_NAGANT,
    "Nine, Quirk Thief": NINE,
    "Star and Stripe, U.S. Number One": STAR_AND_STRIPE,
    "Class 1-A Rookie": CLASS_1A_ROOKIE,

    # NEW LEGENDARIES (game-altering pass)
    "Deku, Full Cowl 100%": DEKU_COWL,
    "Shigaraki Tomura, Handless": SHIGARAKI_HANDLESS,
    "Eri, Rewind": ERI_REWIND,

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
    LADY_NAGANT,
    NINE,
    STAR_AND_STRIPE,
    CLASS_1A_ROOKIE,
    HALF_COLD,
    HALF_HOT,
    RECIPRO_BURST,
    ZERO_GRAVITY,
    DARK_SHADOW_STRIKE,
    FLASHFIRE_FIST,
    PROMINENCE_BURN,
    FIERCE_WINGS
]
