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
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, creatures_with_subtype,
    make_spell_cast_trigger, make_upkeep_trigger, make_end_step_trigger,
    make_life_gain_trigger, make_life_loss_trigger, creatures_you_control,
    other_creatures_with_subtype, all_opponents
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


def hero_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Hero creatures you control."""
    return creatures_with_subtype(source, "Hero")


def villain_type_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Villain creatures you control."""
    return creatures_with_subtype(source, "Villain")


def student_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Student creatures you control."""
    return creatures_with_subtype(source, "Student")


# =============================================================================
# WHITE CARDS - HEROES, SYMBOL OF PEACE, RESCUE
# =============================================================================

# --- Legendary Creatures ---

def all_might_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Symbol of Peace - Other Heroes get +2/+2. Plus Ultra bonus."""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 2, 2, other_creatures_with_subtype(obj, "Hero")))
    interceptors.extend(make_plus_ultra_bonus(obj, 3, 3))
    return interceptors

ALL_MIGHT = make_creature(
    name="All Might, Symbol of Peace",
    power=6, toughness=6,
    mana_cost="{3}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Vigilance, indestructible. Other Hero creatures you control get +2/+2. Plus Ultra - All Might gets +3/+3 as long as you have 5 or less life.",
    setup_interceptors=all_might_setup
)


def endeavor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, deal 2 damage to any target"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        if opponents:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': opponents[0], 'amount': 2, 'source': obj.id},
                source=obj.id
            )]
        return []
    return [make_attack_trigger(obj, attack_effect)]

ENDEAVOR = make_creature(
    name="Endeavor, Number One Hero",
    power=5, toughness=4,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="First strike. Whenever Endeavor attacks, he deals 2 damage to any target. Quirk - {R}: Endeavor gets +2/+0 until end of turn.",
    setup_interceptors=endeavor_setup
)


def hawks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Heroes have flying"""
    return [make_keyword_grant(obj, ['flying'], other_creatures_with_subtype(obj, "Hero"))]

HAWKS = make_creature(
    name="Hawks, Number Two Hero",
    power=3, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Flying, haste. Other Hero creatures you control have flying. Quirk - {U}: Scry 1.",
    setup_interceptors=hawks_setup
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
    text="Flash. Creatures your opponents control lose all abilities. Quirk - {T}: Target creature loses all abilities until end of turn.",
    setup_interceptors=eraserhead_setup
)


def best_jeanist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures opponents control enter tapped"""
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
    text="Creatures your opponents control enter the battlefield tapped. Quirk - {W}, {T}: Tap target creature.",
    setup_interceptors=best_jeanist_setup
)


def mirko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike when attacking alone"""
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
    text="Haste. Mirko has double strike as long as she's attacking alone.",
    setup_interceptors=mirko_setup
)


# --- Regular Creatures ---

def rescue_hero_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 3 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

RESCUE_HERO = make_creature(
    name="Rescue Hero",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="When Rescue Hero enters, you gain 3 life.",
    setup_interceptors=rescue_hero_setup
)


def sidekick_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +1/+1 for each Hero you control"""
    def hero_count_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id

    def count_heroes(state: GameState) -> int:
        count = 0
        for o in state.objects.values():
            if (o.controller == obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                "Hero" in o.characteristics.subtypes):
                count += 1
        return count

    # This would need a dynamic query handler
    return []

SIDEKICK = make_creature(
    name="Eager Sidekick",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Eager Sidekick gets +1/+1 for each Hero you control."
)


UA_TEACHER = make_creature(
    name="UA Teacher",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Other Student creatures you control get +1/+1."
)


POLICE_OFFICER = make_creature(
    name="Hero Public Safety Officer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. When Hero Public Safety Officer enters, detain target creature an opponent controls."
)


RESCUE_SQUAD = make_creature(
    name="Rescue Squad",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Defender. When Rescue Squad enters, you gain 2 life for each creature you control."
)


SUPPORT_COURSE_STUDENT = make_creature(
    name="Support Course Student",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Student", "Artificer"},
    text="When Support Course Student enters, create a colorless Equipment artifact token named Support Item with 'Equipped creature gets +1/+1. Equip {1}'."
)


HERO_INTERN = make_creature(
    name="Hero Intern",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Student"},
    text="Lifelink"
)


NIGHTEYE_AGENCY_MEMBER = make_creature(
    name="Nighteye Agency Member",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="When Nighteye Agency Member enters, scry 2."
)


SELKIE = make_creature(
    name="Selkie, Water Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Hexproof. Selkie can't be blocked by creatures with power 2 or less."
)


GANG_ORCA = make_creature(
    name="Gang Orca, Whale Hero",
    power=5, toughness=5,
    mana_cost="{3}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Menace. When Gang Orca enters, destroy target creature with power 3 or less."
)


THIRTEEN = make_creature(
    name="Thirteen, Rescue Hero",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Defender. Quirk - {T}: Exile target attacking creature. Return it to the battlefield at end of turn."
)


MIDNIGHT = make_creature(
    name="Midnight, R-Rated Hero",
    power=3, toughness=2,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)


PRESENT_MIC = make_creature(
    name="Present Mic, Voice Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Haste. Quirk - {R}, {T}: Present Mic deals 2 damage to each opponent."
)


CEMENTOSS = make_creature(
    name="Cementoss, Concrete Hero",
    power=1, toughness=6,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Defender. Quirk - {1}{W}: Create a 0/3 white Wall creature token with defender."
)


SNIPE = make_creature(
    name="Snipe, Shooting Hero",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Reach. Quirk - {T}: Snipe deals 1 damage to target creature or planeswalker."
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

def symbol_aura_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Heroes you control have vigilance and lifelink"""
    interceptors = []
    interceptors.append(make_keyword_grant(obj, ['vigilance', 'lifelink'], creatures_with_subtype(obj, "Hero")))
    return interceptors

SYMBOL_OF_HOPE = make_enchantment(
    name="Symbol of Hope",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Hero creatures you control have vigilance and lifelink.",
    setup_interceptors=symbol_aura_setup
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

def nezu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Draw a card at upkeep"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

NEZU = make_creature(
    name="Nezu, UA Principal",
    power=1, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Mouse", "Hero"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, draw a card. Quirk - {U}, {T}: Scry 3.",
    setup_interceptors=nezu_setup
)


def sir_nighteye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - look at top 3 cards, put 1 in hand"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1, 'look_extra': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

SIR_NIGHTEYE = make_creature(
    name="Sir Nighteye, Foresight Hero",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="When Sir Nighteye enters, look at the top three cards of your library. Put one into your hand and the rest on the bottom. Quirk - {T}: Look at the top card of target player's library.",
    setup_interceptors=sir_nighteye_setup
)


def shinso_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be blocked by creatures with power 3 or greater"""
    return []

SHINSO = make_creature(
    name="Shinso, Mind Control",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text="Shinso can't be blocked by creatures with power 3 or greater. Quirk - {U}{U}, {T}: Gain control of target creature with power less than Shinso's power until end of turn."
)


def mandalay_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Heroes have hexproof from instants"""
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
    text="Other Hero creatures you control have hexproof. Quirk - {T}: Target player reveals their hand.",
    setup_interceptors=mandalay_setup
)


RAGDOLL = make_creature(
    name="Ragdoll, Wild Wild Pussycats",
    power=2, toughness=2,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {T}: Search your library for a creature card, reveal it, then shuffle. Put that card on top."
)


TIGER = make_creature(
    name="Tiger, Wild Wild Pussycats",
    power=3, toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Quirk - {G}: Tiger gets +2/+2 until end of turn. Activate only once each turn."
)


# --- Regular Creatures ---

ANALYST_HERO = make_creature(
    name="Analyst Hero",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    text="When Analyst Hero enters, scry 2."
)


INFORMATION_BROKER = make_creature(
    name="Hero Information Broker",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="{T}: Look at the top card of target player's library."
)


UA_ROBOT = make_creature(
    name="UA Training Robot",
    power=3, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text="When UA Training Robot dies, draw a card."
)


ERASURE_AGENT = make_creature(
    name="Erasure Agent",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    text="Flash. When Erasure Agent enters, counter target activated ability."
)


TACTICAL_SUPPORT = make_creature(
    name="Tactical Support Hero",
    power=1, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    text="Flying. Whenever you cast an instant or sorcery spell, scry 1."
)


STRATEGY_STUDENT = make_creature(
    name="Strategy Student",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    text="When Strategy Student enters, draw a card, then discard a card."
)


HATSUME_MEI = make_creature(
    name="Hatsume Mei, Inventor",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student", "Artificer"},
    supertypes={"Legendary"},
    text="When Hatsume Mei enters, create two colorless artifact tokens named Baby with '{T}, Sacrifice this artifact: Add {C}{C}.'"
)


POWER_LOADER = make_creature(
    name="Power Loader, Support Teacher",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero", "Artificer"},
    supertypes={"Legendary"},
    text="Artifacts you control have hexproof. Quirk - {T}: Untap target artifact."
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
    text="Creatures you control get +1/+0. Whenever a creature you control deals combat damage to a player, scry 1."
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
    text="Indestructible. Villain - Whenever an opponent loses life, put a +1/+1 counter on All For One. Quirk - {B}{B}, {T}: Destroy target creature. All For One gains all activated abilities of that creature.",
    setup_interceptors=all_for_one_setup
)


def shigaraki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage, destroy target permanent"""
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
    text="Menace. Whenever Shigaraki deals combat damage to a player, destroy target nonland permanent. Quirk - {2}{B}: Destroy target artifact or enchantment.",
    setup_interceptors=shigaraki_setup
)


def dabi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - deal 1 damage to self and each opponent"""
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
    text="At the beginning of your upkeep, Dabi deals 1 damage to you and 2 damage to each opponent. Quirk - {R}: Dabi deals 1 damage to any target.",
    setup_interceptors=dabi_setup
)


def toga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage to player, copy target creature"""
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
    text="Deathtouch. Whenever Toga deals combat damage to a player, create a token that's a copy of target creature that player controls. Sacrifice it at end of turn.",
    setup_interceptors=toga_setup
)


def stain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike, deathtouch. Extra combat vs Heroes"""
    return []

STAIN = make_creature(
    name="Stain, Hero Killer",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="First strike, deathtouch. Stain has double strike as long as it's attacking a Hero. Quirk - {B}: Target creature can't block this turn."
)


def overhaul_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - destroy target creature, then return creature from grave"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DESTROY,
            payload={'target': 'any_creature'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

OVERHAUL = make_creature(
    name="Overhaul, Yakuza Boss",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Overhaul enters, destroy target creature. Then you may return a creature card from your graveyard to your hand. Quirk - {1}{B}: Regenerate Overhaul.",
    setup_interceptors=overhaul_setup
)


def twice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create copy of self"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Twice Double', 'power': 2, 'toughness': 2,
                         'colors': {Color.BLACK}, 'subtypes': {'Human', 'Villain'}}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

TWICE = make_creature(
    name="Twice, Double Trouble",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Twice enters, create a token that's a copy of Twice, except it's not legendary.",
    setup_interceptors=twice_setup
)


MR_COMPRESS = make_creature(
    name="Mr. Compress, Showman",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Quirk - {T}: Exile target creature you control. Return it at the beginning of your next upkeep."
)


KUROGIRI = make_creature(
    name="Kurogiri, Warp Gate",
    power=1, toughness=4,
    mana_cost="{1}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Elemental", "Villain"},
    supertypes={"Legendary"},
    text="Flash. Quirk - {T}: Exile target creature you control, then return it to the battlefield under your control."
)


MUSCULAR = make_creature(
    name="Muscular, Villain",
    power=6, toughness=4,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Trample, haste. Muscular attacks each combat if able."
)


MOONFISH = make_creature(
    name="Moonfish, Blade Villain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="First strike. Whenever Moonfish deals combat damage to a creature, destroy that creature."
)


GIGANTOMACHIA = make_creature(
    name="Gigantomachia, Living Disaster",
    power=12, toughness=12,
    mana_cost="{8}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Giant", "Villain"},
    supertypes={"Legendary"},
    text="Trample, vigilance. Gigantomachia can't be blocked by creatures with power 3 or less. When Gigantomachia enters, destroy all other creatures."
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
    text="Villain - Whenever an opponent loses life, you may pay {1}. If you do, draw a card."
)


NOMU = make_creature(
    name="Nomu, Bioengineered",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Villain"},
    text="Trample. Nomu can't be regenerated. When Nomu dies, each opponent loses 2 life."
)


HIGH_END_NOMU = make_creature(
    name="High-End Nomu",
    power=7, toughness=6,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Villain"},
    text="Flying, trample, regenerate {B}{B}. When High-End Nomu enters, it fights target creature."
)


YAKUZA_THUG = make_creature(
    name="Shie Hassaikai Thug",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text="When Shie Hassaikai Thug dies, target opponent discards a card."
)


TRIGGER_DEALER = make_creature(
    name="Trigger Dealer",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text="{T}, Pay 2 life: Target creature gets +2/+2 until end of turn."
)


META_LIBERATION_SOLDIER = make_creature(
    name="Meta Liberation Soldier",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text="Menace. When Meta Liberation Soldier dies, draw a card."
)


SKEPTIC = make_creature(
    name="Skeptic, Liberation Lieutenant",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Other Villain creatures you control get +1/+0. When a Villain you control dies, each opponent loses 1 life."
)


TRUMPET = make_creature(
    name="Trumpet, Liberation Commander",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Other Villain creatures you control get +1/+1 and have deathtouch."
)


RE_DESTRO = make_creature(
    name="Re-Destro, Liberation Leader",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Menace. Re-Destro gets +X/+0, where X is the amount of life you've lost this turn. Quirk - {2}{B}: Re-Destro deals damage to any target equal to the amount of life you've lost this turn."
)


CURIOUS = make_creature(
    name="Curious, Information Master",
    power=2, toughness=2,
    mana_cost="{1}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Curious enters, target opponent reveals their hand. You choose a nonland card from it. That player discards that card."
)


GETEN = make_creature(
    name="Geten, Ice Villain",
    power=3, toughness=4,
    mana_cost="{2}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Quirk - {U}{U}: Tap target creature. It doesn't untap during its controller's next untap step."
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

def league_hideout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Villains get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, creatures_with_subtype(obj, "Villain"))

LEAGUE_HIDEOUT = make_enchantment(
    name="League Hideout",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Villain creatures you control get +1/+1.",
    setup_interceptors=league_hideout_setup
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
    text="Haste. Whenever Bakugo attacks, he deals 1 damage to each creature defending player controls. Plus Ultra - Bakugo gets +2/+2 as long as you have 5 or less life. Quirk - {R}: Bakugo gets +2/+0 until end of turn.",
    setup_interceptors=bakugo_setup
)


def kirishima_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Indestructible while attacking"""
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
    text="Kirishima has indestructible as long as he's attacking. Plus Ultra - Kirishima gets +2/+2 as long as you have 5 or less life. Quirk - {R}: Kirishima gets +0/+3 until end of turn.",
    setup_interceptors=kirishima_setup
)


def kaminari_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Quirk deals damage but taps self"""
    return []

KAMINARI = make_creature(
    name="Kaminari, Chargebolt",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Haste. Quirk - {R}, {T}: Kaminari deals 3 damage to any target and 1 damage to himself."
)


TETSUTETSU = make_creature(
    name="Tetsutetsu, Real Steel",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Quirk - {R}{R}: Tetsutetsu gains indestructible until end of turn."
)


MINA = make_creature(
    name="Mina Ashido, Pinky",
    power=2, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="First strike. Quirk - {G}: Target creature can't block this turn."
)


FATGUM = make_creature(
    name="Fat Gum, BMI Hero",
    power=2, toughness=7,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Defender. Quirk - Remove all damage from Fat Gum: Fat Gum deals damage equal to the damage removed to target creature."
)


RYUKYU = make_creature(
    name="Ryukyu, Dragon Hero",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero", "Dragon"},
    supertypes={"Legendary"},
    text="Flying, trample. Quirk - {R}{R}: Ryukyu gets +2/+0 and gains first strike until end of turn."
)


CRIMSON_RIOT = make_creature(
    name="Crimson Riot, Legendary Hero",
    power=4, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Indestructible. Whenever Crimson Riot attacks, other attacking creatures get +1/+0 until end of turn."
)


# --- Regular Creatures ---

EXPLOSION_STUDENT = make_creature(
    name="Explosion Student",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    text="Haste. When Explosion Student enters, it deals 1 damage to any target."
)


COMBAT_HERO = make_creature(
    name="Combat Hero",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="First strike, haste."
)


POWER_TYPE_STUDENT = make_creature(
    name="Power-Type Student",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    text="Trample. {R}: Power-Type Student gets +1/+0 until end of turn."
)


RAGING_HERO = make_creature(
    name="Raging Hero",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="Trample, haste. Raging Hero attacks each combat if able."
)


FIERY_SIDEKICK = make_creature(
    name="Fiery Sidekick",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="Haste"
)


BATTLE_STUDENT = make_creature(
    name="Battle Course Student",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Student"},
    text="First strike"
)


BERSERKER_HERO = make_creature(
    name="Berserker Hero",
    power=5, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Hero"},
    text="Trample. Whenever Berserker Hero deals combat damage to a player, it deals 2 damage to you."
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
    text="Creatures you control get +1/+0 and have haste."
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
    text="At the beginning of your upkeep, put a +1/+1 counter on Deku. Plus Ultra - Deku gets +3/+3 as long as you have 5 or less life. Quirk - {G}: Deku gains trample until end of turn.",
    setup_interceptors=deku_setup
)


def uraraka_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Makes creatures fly"""
    return []

URARAKA = make_creature(
    name="Uraraka, Zero Gravity",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Quirk - {W}: Target creature gains flying until end of turn."
)


def iida_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste, first strike when attacking"""
    return []

IIDA = make_creature(
    name="Iida, Ingenium",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Haste, vigilance. Iida has first strike as long as he's attacking. Quirk - {G}: Iida gets +2/+0 until end of turn."
)


def todoroki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Half-Cold Half-Hot - versatile abilities"""
    return []

TODOROKI = make_creature(
    name="Todoroki, Half-Cold Half-Hot",
    power=4, toughness=4,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {R}: Todoroki deals 2 damage to any target. Quirk - {U}: Tap target creature. It doesn't untap during its controller's next untap step."
)


def tsuyu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash, can't be blocked"""
    return []

TSUYU = make_creature(
    name="Tsuyu, Froppy",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flash, hexproof. Tsuyu can't be blocked by creatures with power 3 or greater. Quirk - {U}: Return Tsuyu to your hand."
)


def momo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creates equipment tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Created Equipment', 'type': 'Equipment'}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

MOMO = make_creature(
    name="Momo, Creation Hero",
    power=2, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="When Momo enters, create a colorless Equipment artifact token with 'Equipped creature gets +2/+2. Equip {2}'. Quirk - {2}, Pay 2 life: Create a token that's a copy of target Equipment you control.",
    setup_interceptors=momo_setup
)


def tokoyami_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Shadow - gets stronger at low life"""
    interceptors = []
    interceptors.extend(make_plus_ultra_bonus(obj, 4, 0))
    return interceptors

TOKOYAMI = make_creature(
    name="Tokoyami, Dark Shadow",
    power=3, toughness=3,
    mana_cost="{2}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Plus Ultra - Tokoyami gets +4/+0 as long as you have 5 or less life. Quirk - {B}: Tokoyami gains menace until end of turn.",
    setup_interceptors=tokoyami_setup
)


SERO = make_creature(
    name="Sero, Cellophane",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Reach. Quirk - {G}, {T}: Tap target creature with power 3 or less."
)


SHOJI = make_creature(
    name="Shoji, Tentacole",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Vigilance. Shoji can block an additional creature each combat."
)


KODA = make_creature(
    name="Koda, Anima",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {G}: Create a 1/1 green Bird creature token with flying."
)


OJIRO = make_creature(
    name="Ojiro, Tailman",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="First strike. Quirk - {G}: Ojiro gets +1/+1 until end of turn."
)


SATO = make_creature(
    name="Sato, Sugarman",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Quirk - {G}, Pay 2 life: Sato gets +3/+3 until end of turn."
)


# --- Regular Creatures ---

def growth_student_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - put +1/+1 counter on target creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

GROWTH_STUDENT = make_creature(
    name="Growth-Type Student",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    text="When Growth-Type Student enters, put a +1/+1 counter on target creature you control.",
    setup_interceptors=growth_student_setup
)


ONE_FOR_ALL_HEIR = make_creature(
    name="One For All Heir",
    power=2, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    text="Trample. {G}: One For All Heir gets +1/+1 until end of turn."
)


NATURE_HERO = make_creature(
    name="Nature Hero",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    text="Reach, trample."
)


MUTANT_STUDENT = make_creature(
    name="Mutant-Type Student",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Student"},
    text="Trample"
)


HEALING_HERO = make_creature(
    name="Healing Hero",
    power=1, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Lifelink. {T}: Regenerate target creature."
)


FOREST_GUARDIAN = make_creature(
    name="Forest Guardian Hero",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    text="Vigilance, reach."
)


WILD_PUSSYCAT = make_creature(
    name="Wild Wild Pussycat Member",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    text="When Wild Wild Pussycat Member enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle."
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

def one_for_all_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchanted creature gets +3/+3 and grows"""
    return []

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
    text="Quirk - {T}: Jiro deals 1 damage to each opponent. Whenever you cast an instant or sorcery spell, Jiro deals 1 damage to any target."
)


MINETA = make_creature(
    name="Mineta, Grape Rush",
    power=1, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text="Quirk - {T}: Target creature can't attack or block until your next turn."
)


KENDO = make_creature(
    name="Kendo, Battle Fist",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Vigilance. Other Student creatures you control get +1/+1."
)


MONOMA = make_creature(
    name="Monoma, Copy Cat",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text="Whenever Monoma deals combat damage to a player, choose target creature that player controls. Until end of turn, Monoma becomes a copy of that creature."
)


MIRIO = make_creature(
    name="Mirio, Lemillion",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Mirio can't be blocked. Quirk - {U}: Mirio gains hexproof and indestructible until end of turn. You may have Mirio deal no combat damage this turn."
)


TAMAKI = make_creature(
    name="Tamaki, Suneater",
    power=3, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {G}: Tamaki gets +2/+0 until end of turn. Quirk - {U}: Tamaki gains flying until end of turn. Quirk - {B}: Tamaki gains deathtouch until end of turn."
)


NEJIRE = make_creature(
    name="Nejire, Nejire Wave",
    power=3, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Quirk - {U}{U}: Nejire deals 3 damage to target creature with flying."
)


AOYAMA = make_creature(
    name="Aoyama, Navel Laser",
    power=2, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="First strike. Quirk - {1}, {T}: Aoyama deals 2 damage to target creature. Aoyama doesn't untap during your next untap step."
)


HAGAKURE = make_creature(
    name="Hagakure, Invisible Girl",
    power=1, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Hagakure can't be blocked. Quirk - {W}: Hagakure gains hexproof until end of turn."
)


# --- Pro Hero Multicolor ---

WASH = make_creature(
    name="Wash, Cleansing Hero",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="When Wash enters, return target creature to its owner's hand."
)


EDGESHOT = make_creature(
    name="Edgeshot, Ninja Hero",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Flash, deathtouch. Edgeshot can't be blocked by creatures with power 2 or greater."
)


KAMUI_WOODS = make_creature(
    name="Kamui Woods, Tree Hero",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Reach. Quirk - {G}{G}, {T}: Tap all creatures target opponent controls."
)


MT_LADY = make_creature(
    name="Mt. Lady, Gigantification",
    power=6, toughness=6,
    mana_cost="{4}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Quirk - Mt. Lady enters with three -1/-1 counters. At the beginning of your upkeep, remove a -1/-1 counter from Mt. Lady."
)


DEATH_ARMS = make_creature(
    name="Death Arms, Punching Hero",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="First strike. Whenever Death Arms deals combat damage to a creature, destroy that creature."
)


NATIVE = make_creature(
    name="Native, Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Vigilance. When Native enters, you gain 3 life."
)


FOURTH_KIND = make_creature(
    name="Fourth Kind, Hero",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Menace. Fourth Kind can block an additional creature each combat."
)


MANUAL = make_creature(
    name="Manual, Water Hero",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {U}: Target creature gains hexproof until end of turn."
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
    text="When Pixie-Bob enters, create two 1/1 green Beast creature tokens. Quirk - {G}: Target Beast gets +1/+1 until end of turn."
)


RECOVERY_GIRL = make_creature(
    name="Recovery Girl, Healing Hero",
    power=0, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {T}: Regenerate target creature. You gain 1 life. {W}{W}, {T}: Remove all damage from target creature. That creature's controller gains life equal to its toughness."
)


VLAD_KING = make_creature(
    name="Vlad King, Blood Hero",
    power=3, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Menace. Quirk - {B}, Pay 1 life: Vlad King gets +2/+0 until end of turn."
)


ECTOPLASM = make_creature(
    name="Ectoplasm, Clone Hero",
    power=2, toughness=2,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {U}{B}: Create a token that's a copy of Ectoplasm, except it's not legendary. Sacrifice it at end of turn."
)


HOUND_DOG = make_creature(
    name="Hound Dog, Detection Hero",
    power=3, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Vigilance. Quirk - {T}: Look at target opponent's hand."
)


LUNCH_RUSH = make_creature(
    name="Lunch Rush, Cook Hero",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you gain 1 life. If you have 15 or more life, draw a card instead."
)


INGENIUM = make_creature(
    name="Tensei Iida, Ingenium",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Haste, vigilance. Other Hero creatures you control have vigilance."
)


INASA = make_creature(
    name="Inasa Yoarashi, Gale Force",
    power=4, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Flying. Quirk - {U}{R}: All creatures lose flying until end of turn. Inasa deals 2 damage to each creature that lost flying this way."
)


CAMIE = make_creature(
    name="Camie, Illusion Girl",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text="Quirk - {U}, {T}: Create a token that's a copy of target creature, except it's an Illusion in addition to its other types. Sacrifice it at end of turn."
)


SEIJI = make_creature(
    name="Seiji Shishikura, Meatball",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Student"},
    supertypes={"Legendary"},
    text="Quirk - {U}{U}, {T}: Exile target creature with power 2 or less. Return it to the battlefield at the beginning of your next upkeep."
)


GENTLE_CRIMINAL = make_creature(
    name="Gentle Criminal",
    power=2, toughness=3,
    mana_cost="{1}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying. Quirk - {U}: Target creature gains flying until end of turn. Whenever Gentle Criminal deals combat damage to a player, draw a card."
)


LA_BRAVA = make_creature(
    name="La Brava, Love",
    power=1, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Quirk - {T}: Target creature gets +5/+5 until end of turn. Activate only once each turn and only if that creature is named Gentle Criminal or you control Gentle Criminal."
)


SPINNER = make_creature(
    name="Spinner, League Member",
    power=3, toughness=2,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="First strike. Spinner gets +1/+1 for each other Villain you control."
)


MAGNE = make_creature(
    name="Magne, Big Sis Magne",
    power=4, toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Haste. Quirk - {R}: Target creature must attack this turn if able. {B}: Target creature can't block this turn."
)


MUSTARD = make_creature(
    name="Mustard, Gas Villain",
    power=2, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Villain"},
    text="When Mustard enters, put a -1/-1 counter on each creature your opponents control."
)


REDESTRO_HAND = make_creature(
    name="Meta Liberation Hand",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text="When Meta Liberation Hand dies, target opponent discards a card."
)


DETNERAT_CEO = make_creature(
    name="Detnerat Executive",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text="Whenever another Villain enters under your control, each opponent loses 1 life."
)


ENDING = make_creature(
    name="Ending, Obsessed Villain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    text="Menace. Ending gets +2/+0 as long as an opponent controls a legendary creature."
)


SLIDE_N_GO = make_creature(
    name="Slide'n'Go, Pro Hero",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Whenever Slide'n'Go attacks, tap target creature defending player controls."
)


YOROI_MUSHA = make_creature(
    name="Yoroi Musha, Armored Hero",
    power=2, toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Hero"},
    text="Vigilance. Yoroi Musha gets +2/+0 as long as it's equipped."
)


BUBBLE_GIRL = make_creature(
    name="Bubble Girl, Sidekick",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    text="Quirk - {T}: Tap target creature with power 1 or less."
)


CENTIPEDER = make_creature(
    name="Centipeder, Sidekick",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Hero"},
    text="When Centipeder enters, scry 1."
)


SHINDO = make_creature(
    name="Shindo, Quake Hero",
    power=3, toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Trample. Quirk - {R}{G}, {T}: Shindo deals 2 damage to each creature without flying."
)


NAKAGAME = make_creature(
    name="Nakagame, Shield Hero",
    power=1, toughness=5,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Student", "Hero"},
    supertypes={"Legendary"},
    text="Defender. Quirk - {W}: Target creature gains indestructible until end of turn."
)


MS_JOKE = make_creature(
    name="Ms. Joke, Smile Hero",
    power=2, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text="Quirk - {T}: Target creature can't attack or block until your next turn."
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
