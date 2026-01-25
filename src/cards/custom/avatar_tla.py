"""
Avatar: The Last Airbender - Custom Card Set

Custom/fan-made set with 286 cards.
Features mechanics: Airbend, Waterbend, Earthbend, Firebend, Lesson spells, Allies

NOTE: This is a custom set. A real "Avatar: The Last Airbender" MTG set was released
after my knowledge cutoff and may have different cards.
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
# AVATAR TLA KEYWORD HELPERS
# =============================================================================

from src.cards.interceptor_helpers import (
    make_etb_trigger, make_attack_trigger, make_spell_cast_trigger,
    make_static_pt_boost, make_keyword_grant, make_life_gain_trigger,
    make_death_trigger, make_damage_trigger, make_tap_trigger,
    make_upkeep_trigger, make_end_step_trigger,
    other_creatures_you_control, creatures_with_subtype, all_opponents
)


def make_airbend_etb(source_obj: GameObject, num_targets: int = 1) -> Interceptor:
    """
    Airbend — When this permanent enters, return up to N target nonland permanents to their owners' hands.

    Note: Full implementation requires targeting system.
    """
    def airbend_effect(event: Event, state: GameState) -> list[Event]:
        # Would create ZONE_CHANGE events to return targets to hand
        return []  # Targeting system fills this in

    return make_etb_trigger(source_obj, airbend_effect)


def make_airbend_attack(source_obj: GameObject) -> Interceptor:
    """
    Airbend — Whenever this creature attacks, you may return target nonland permanent to its owner's hand.
    """
    def airbend_effect(event: Event, state: GameState) -> list[Event]:
        # Would create ZONE_CHANGE event to bounce target
        return []  # Targeting system fills this in

    return make_attack_trigger(source_obj, airbend_effect)


def make_waterbend_etb(source_obj: GameObject, life_amount: int = 0, prevent_damage: int = 0) -> Interceptor:
    """
    Waterbend — When this permanent enters, gain N life and/or prevent next N damage.

    Args:
        source_obj: The permanent with waterbend
        life_amount: Life to gain
        prevent_damage: Damage to prevent
    """
    def waterbend_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        if life_amount > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': source_obj.controller, 'amount': life_amount},
                source=source_obj.id
            ))
        # Damage prevention would need a PREVENT interceptor
        return events

    return make_etb_trigger(source_obj, waterbend_effect)


def make_earthbend_etb(source_obj: GameObject, num_walls: int = 1) -> Interceptor:
    """
    Earthbend — When this permanent enters, create N 0/3 Wall creature tokens with defender.
    """
    def earthbend_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(num_walls):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': source_obj.controller,
                    'name': 'Wall',
                    'power': 0,
                    'toughness': 3,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Wall'},
                    'abilities': ['defender'],
                    'is_token': True
                },
                source=source_obj.id
            ))
        return events

    return make_etb_trigger(source_obj, earthbend_effect)


def make_firebend_etb(source_obj: GameObject, damage: int) -> Interceptor:
    """
    Firebend — When this permanent enters, deal N damage to any target.

    Note: If lethal, exile instead of destroy (full firebend flavor).
    """
    def firebend_effect(event: Event, state: GameState) -> list[Event]:
        # Would target and create DAMAGE event
        return []  # Targeting system fills this in

    return make_etb_trigger(source_obj, firebend_effect)


def make_firebend_attack(source_obj: GameObject, damage: int) -> Interceptor:
    """
    Firebend — Whenever this creature attacks, deal N damage to any target.
    """
    def firebend_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system fills this in

    return make_attack_trigger(source_obj, firebend_effect)


def make_lesson_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]]
) -> Interceptor:
    """
    Trigger whenever you cast a Lesson spell.

    Args:
        source_obj: The permanent with the lesson trigger
        effect_fn: Effect to trigger when a lesson spell is cast
    """
    def lesson_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        # Check if spell has Lesson subtype
        subtypes = event.payload.get('subtypes', set())
        return 'Lesson' in subtypes

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: lesson_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(e, s)
        ),
        duration='while_on_battlefield'
    )


def make_ally_etb_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]]
) -> Interceptor:
    """
    Whenever another Ally enters under your control, trigger effect.
    """
    def ally_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Check if it's an Ally that entered (not self)
        entered_id = event.payload.get('object_id')
        if entered_id == obj.id:
            return False
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        if entered_obj.controller != obj.controller:
            return False
        return 'Ally' in entered_obj.characteristics.subtypes

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: ally_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(e, s)
        ),
        duration='while_on_battlefield'
    )


# =============================================================================
# WHITE CARDS
# =============================================================================

def aangs_iceberg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, exile up to one other target nonland permanent until this enchantment leaves."""
    def exile_effect(event: Event, state: GameState) -> list[Event]:
        # Would create exile event (targeting system fills in target)
        return []
    return [make_etb_trigger(obj, exile_effect)]

AANGS_ICEBERG = make_enchantment(
    name="Aang's Iceberg",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Flash. When this enchantment enters, exile up to one other target nonland permanent until this enchantment leaves the battlefield.",
    setup_interceptors=aangs_iceberg_setup
)

def aang_the_last_airbender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Airbend on attack + Lesson spell trigger for lifelink."""
    def lesson_effect(event: Event, state: GameState) -> list[Event]:
        # Grant lifelink until end of turn
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'lifelink', 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [
        make_airbend_attack(obj),
        make_lesson_trigger(obj, lesson_effect)
    ]

AANG_THE_LAST_AIRBENDER = make_creature(
    name="Aang, the Last Airbender",
    power=3,
    toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Aang attacks, you may return target nonland permanent to its owner's hand. Whenever you cast a Lesson spell, Aang gains lifelink until end of turn.",
    setup_interceptors=aang_the_last_airbender_setup
)

def airbender_ascension_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Airbend ETB - return creature to hand."""
    return [make_airbend_etb(obj, 1)]

AIRBENDER_ASCENSION = make_enchantment(
    name="Airbender Ascension",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, airbend up to one target creature. (Return it to its owner's hand.)",
    setup_interceptors=airbender_ascension_setup
)

AIRBENDERS_REVERSAL = make_instant(
    name="Airbender's Reversal",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Lesson — Choose one: Destroy target creature with flying; or return target nonland permanent you control to its owner's hand."
)

AIRBENDING_LESSON = make_instant(
    name="Airbending Lesson",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Lesson — Airbend target nonland permanent. Draw a card."
)

def appa_loyal_sky_bison_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two 1/1 Ally tokens. Attack: Allies get +1/+1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Ally',
                    'power': 1,
                    'toughness': 1,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Ally'},
                    'colors': {Color.WHITE},
                    'is_token': True
                },
                source=obj.id
            ))
        return events

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Grant +1/+1 to all Allies until end of turn
        events = []
        for obj_id, game_obj in state.objects.items():
            if (game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                'Ally' in game_obj.characteristics.subtypes and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.GRANT_PT_MODIFIER,
                    payload={'object_id': obj_id, 'power': 1, 'toughness': 1, 'duration': 'end_of_turn'},
                    source=obj.id
                ))
        return events

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]

APPA_LOYAL_SKY_BISON = make_creature(
    name="Appa, Loyal Sky Bison",
    power=4,
    toughness=4,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Bison", "Ally"},
    supertypes={"Legendary"},
    text="Flying. When Appa enters, create two 1/1 white Ally creature tokens. Whenever Appa attacks, Allies you control get +1/+1 until end of turn.",
    setup_interceptors=appa_loyal_sky_bison_setup
)

def appa_steadfast_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Airbend any number of your own nonland permanents."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles multiple targets
        return []
    return [make_etb_trigger(obj, etb_effect)]

APPA_STEADFAST_GUARDIAN = make_creature(
    name="Appa, Steadfast Guardian",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Bison", "Ally"},
    supertypes={"Legendary"},
    text="Flash. Flying. When Appa enters, airbend any number of other target nonland permanents you control.",
    setup_interceptors=appa_steadfast_guardian_setup
)

def avatar_enthusiasts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ally ETB trigger: put +1/+1 counter on self."""
    def ally_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_ally_etb_trigger(obj, ally_effect)]

AVATAR_ENTHUSIASTS = make_creature(
    name="Avatar Enthusiasts",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant", "Ally"},
    text="Whenever another Ally enters under your control, put a +1/+1 counter on Avatar Enthusiasts.",
    setup_interceptors=avatar_enthusiasts_setup
)

AVATARS_WRATH = make_sorcery(
    name="Avatar's Wrath",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Choose up to one target creature, then return all other creatures to their owners' hands."
)

def compassionate_healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap trigger: gain 1 life and scry 1."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_tap_trigger(obj, tap_effect)]

COMPASSIONATE_HEALER = make_creature(
    name="Compassionate Healer",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric", "Ally"},
    text="Whenever this creature becomes tapped, you gain 1 life and scry 1.",
    setup_interceptors=compassionate_healer_setup
)

def curious_farm_animals_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger: gain 3 life."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

CURIOUS_FARM_ANIMALS = make_creature(
    name="Curious Farm Animals",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Boar", "Elk", "Bird", "Ox"},
    text="When this creature dies, you gain 3 life.",
    setup_interceptors=curious_farm_animals_setup
)

DESTINED_CONFRONTATION = make_sorcery(
    name="Destined Confrontation",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Each player chooses any number of creatures they control with total power 4 or less, then sacrifices the rest."
)

def earth_kingdom_jailer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: exile target permanent with MV 3+ until leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles exile
        return []
    return [make_etb_trigger(obj, etb_effect)]

EARTH_KINGDOM_JAILER = make_creature(
    name="Earth Kingdom Jailer",
    power=3,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Ally"},
    text="When this creature enters, exile up to one target artifact, creature, or enchantment an opponent controls with mana value 3 or greater until this creature leaves the battlefield.",
    setup_interceptors=earth_kingdom_jailer_setup
)

EARTH_KINGDOM_PROTECTORS = make_creature(
    name="Earth Kingdom Protectors",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Ally"},
    text="Vigilance. Sacrifice this creature: Another target Ally you control gains indestructible until end of turn."
)

ENTER_THE_AVATAR_STATE = make_instant(
    name="Enter the Avatar State",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Lesson — Until end of turn, target creature becomes an Avatar in addition to its other types and gains flying, first strike, lifelink, and hexproof."
)

FANCY_FOOTWORK = make_instant(
    name="Fancy Footwork",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Lesson — Untap one or two target creatures. They each get +2/+2 until end of turn."
)

GATHER_THE_WHITE_LOTUS = make_sorcery(
    name="Gather the White Lotus",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Create a 1/1 white Ally creature token for each Plains you control. Scry 2."
)

def glider_kids_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

GLIDER_KIDS = make_creature(
    name="Glider Kids",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot", "Ally"},
    text="Flying. When this creature enters, scry 1.",
    setup_interceptors=glider_kids_setup
)

def glider_staff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: airbend one creature."""
    return [make_airbend_etb(obj, 1)]

GLIDER_STAFF = make_artifact(
    name="Glider Staff",
    mana_cost="{2}{W}",
    subtypes={"Equipment"},
    text="When this Equipment enters, airbend up to one target creature. Equipped creature gets +1/+1 and has flying. Equip {2}",
    setup_interceptors=glider_staff_setup
)

HAKODA_SELFLESS_COMMANDER = make_creature(
    name="Hakoda, Selfless Commander",
    power=3,
    toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance. You may look at the top card of your library any time. You may cast Ally spells from the top of your library."
)

def invasion_reinforcements_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create 1/1 white Ally token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Ally',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Ally'},
                'colors': {Color.WHITE},
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

INVASION_REINFORCEMENTS = make_creature(
    name="Invasion Reinforcements",
    power=1,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    text="Flash. When this creature enters, create a 1/1 white Ally creature token.",
    setup_interceptors=invasion_reinforcements_setup
)

def jeong_jeongs_deserters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: put +1/+1 counter on target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system fills in target
        return []
    return [make_etb_trigger(obj, etb_effect)]

JEONG_JEONGS_DESERTERS = make_creature(
    name="Jeong Jeong's Deserters",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Ally"},
    text="When this creature enters, put a +1/+1 counter on target creature you control.",
    setup_interceptors=jeong_jeongs_deserters_setup
)

def katara_waterbending_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Waterbend: on instant/sorcery cast, tap or untap target creature."""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles tap/untap choice
        return []
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

KATARA_WATERBENDING_MASTER = make_creature(
    name="Katara, Waterbending Master",
    power=2,
    toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Ward {2}. Waterbend — Whenever you cast an instant or sorcery spell, you may tap or untap target creature.",
    setup_interceptors=katara_waterbending_master_setup
)

def sokka_swordsman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: draw a card."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # Check if target is a player
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

SOKKA_SWORDSMAN = make_creature(
    name="Sokka, Swordsman",
    power=3,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike. Whenever Sokka deals combat damage to a player, draw a card.",
    setup_interceptors=sokka_swordsman_setup
)

def suki_kyoshi_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Warriors +1/+0. Warrior ETB: Suki gains indestructible."""
    def warrior_filter(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Warrior' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    def warrior_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        if entered_id == source.id:
            return False
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        if entered_obj.controller != source.controller:
            return False
        return 'Warrior' in entered_obj.characteristics.subtypes

    def warrior_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
            source=obj.id
        )]

    interceptors = make_static_pt_boost(obj, 1, 0, warrior_filter)

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: warrior_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=warrior_effect(e, s)
        ),
        duration='while_on_battlefield'
    ))
    return interceptors

SUKI_KYOSHI_WARRIOR = make_creature(
    name="Suki, Kyoshi Warrior",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike. Other Warrior creatures you control get +1/+0. Whenever another Warrior enters under your control, Suki gains indestructible until end of turn.",
    setup_interceptors=suki_kyoshi_warrior_setup
)

def uncle_iroh_tea_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if you gained life, draw card. Tap: gain 2 life."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Check if controller gained life this turn (tracked in game state)
        if state.turn_data.get(f'{obj.controller}_gained_life', False):
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]

UNCLE_IROH_TEA_MASTER = make_creature(
    name="Uncle Iroh, Tea Master",
    power=2,
    toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Advisor", "Ally"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if you gained life this turn, draw a card. {T}: You gain 2 life.",
    setup_interceptors=uncle_iroh_tea_master_setup
)

def white_lotus_member_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Look at top 3, may reveal Ally to hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LOOK_AT_TOP,
            payload={'player': obj.controller, 'amount': 3, 'reveal_subtype': 'Ally'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

WHITE_LOTUS_MEMBER = make_creature(
    name="White Lotus Member",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Ally"},
    text="When this creature enters, look at the top three cards of your library. You may reveal an Ally card from among them and put it into your hand. Put the rest on the bottom of your library in any order.",
    setup_interceptors=white_lotus_member_setup
)


# =============================================================================
# BLUE CARDS
# =============================================================================

def aang_swift_savior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: airbend creature OR counter spell MV 2 or less."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Modal ability - targeting system handles
        return []
    return [make_etb_trigger(obj, etb_effect)]

AANG_SWIFT_SAVIOR = make_creature(
    name="Aang, Swift Savior",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flash. Flying. When Aang enters, airbend up to one other target creature or counter target spell with mana value 2 or less.",
    setup_interceptors=aang_swift_savior_setup
)

ABANDON_ATTACHMENTS = make_instant(
    name="Abandon Attachments",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Lesson — You may discard a card. If you do, draw two cards."
)

ACCUMULATE_WISDOM = make_instant(
    name="Accumulate Wisdom",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Lesson — Look at the top three cards of your library. Put one into your hand and the rest on the bottom of your library in any order."
)

def benevolent_river_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

BENEVOLENT_RIVER_SPIRIT = make_creature(
    name="Benevolent River Spirit",
    power=4,
    toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying, ward {2}. When this creature enters, scry 2.",
    setup_interceptors=benevolent_river_spirit_setup
)

BOOMERANG_BASICS = make_sorcery(
    name="Boomerang Basics",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Lesson — Return target nonland permanent to its owner's hand. If you controlled it, draw a card."
)

def knowledge_seeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: draw a card, then discard a card (loot)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, etb_effect)]

KNOWLEDGE_SEEKER = make_creature(
    name="Knowledge Seeker",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, draw a card, then discard a card.",
    setup_interceptors=knowledge_seeker_setup
)

def library_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant/sorcery cast: scry 1."""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

LIBRARY_GUARDIAN = make_creature(
    name="Library Guardian",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. Whenever you cast an instant or sorcery spell, scry 1.",
    setup_interceptors=library_guardian_setup
)

MASTER_PAKKU = make_creature(
    name="Master Pakku",
    power=3,
    toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Waterbend — {U}, {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)

MOON_SPIRIT_BLESSING = make_instant(
    name="Moon Spirit Blessing",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Target creature gains hexproof until end of turn. Draw a card."
)

def northern_water_tribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: tap target opponent's creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles tap
        return []
    return [make_etb_trigger(obj, etb_effect)]

NORTHERN_WATER_TRIBE = make_creature(
    name="Northern Water Tribe",
    power=2,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    text="When this creature enters, tap up to one target creature an opponent controls.",
    setup_interceptors=northern_water_tribe_setup
)

OCEAN_SPIRIT_FURY = make_sorcery(
    name="Ocean Spirit Fury",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands."
)

def princess_yue_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: may exile to create 4/4 blue Spirit token with flying."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Player may choose to exile - creates Moon Spirit token
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Moon Spirit',
                'power': 4,
                'toughness': 4,
                'types': {CardType.CREATURE},
                'subtypes': {'Spirit'},
                'colors': {Color.BLUE},
                'abilities': ['flying'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

PRINCESS_YUE = make_creature(
    name="Princess Yue",
    power=1,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="When Princess Yue dies, you may exile her. If you do, create a 4/4 blue Spirit creature token with flying named Moon Spirit.",
    setup_interceptors=princess_yue_setup
)

def spirit_library_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: draw 2. Lesson cast: draw 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]

    def lesson_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_lesson_trigger(obj, lesson_effect)
    ]

SPIRIT_LIBRARY = make_enchantment(
    name="Spirit Library",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="When Spirit Library enters, draw two cards. Whenever you cast a Lesson spell, draw a card.",
    setup_interceptors=spirit_library_setup
)

WATERBENDING_LESSON = make_instant(
    name="Waterbending Lesson",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Lesson — Tap up to two target creatures. Those creatures don't untap during their controllers' next untap steps."
)

def wan_shi_tong_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Noncreature cast: draw. End step: if drew 3+, opponents mill 5."""
    def spell_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != o.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        cards_drawn = state.turn_data.get(f'{obj.controller}_cards_drawn', 0)
        if cards_drawn >= 3:
            events = []
            for player_id in state.players.keys():
                if player_id != obj.controller:
                    events.append(Event(
                        type=EventType.MILL,
                        payload={'player': player_id, 'amount': 5},
                        source=obj.id
                    ))
            return events
        return []

    spell_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: spell_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=spell_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    return [spell_trigger, make_end_step_trigger(obj, end_step_effect)]

WAN_SHI_TONG = make_creature(
    name="Wan Shi Tong",
    power=4,
    toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Owl"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast a noncreature spell, draw a card. At the beginning of your end step, if you drew three or more cards this turn, each opponent mills five cards.",
    setup_interceptors=wan_shi_tong_setup
)


# =============================================================================
# BLACK CARDS
# =============================================================================

AZULA_ALWAYS_LIES = make_instant(
    name="Azula Always Lies",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Lesson — Choose one or both: Target creature gets -1/-1 until end of turn; and/or put a +1/+1 counter on target creature."
)

def azula_cunning_usurper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: Firebend 2 (exile top 2 cards, may cast them)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles exile and cast permission
        return []
    return [make_firebend_attack(obj, 2)]

AZULA_CUNNING_USURPER = make_creature(
    name="Azula, Cunning Usurper",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Noble", "Rogue"},
    supertypes={"Legendary"},
    text="Firebend 2 — Whenever Azula attacks, exile the top two cards of target opponent's library. You may cast spells from among those cards this turn, and mana of any type can be spent to cast them.",
    setup_interceptors=azula_cunning_usurper_setup
)

def azula_on_the_hunt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: lose 1 life, create Clue. Firebend 2."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': -1},
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Clue',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Clue'},
                    'is_token': True
                },
                source=obj.id
            )
        ]
    return [
        make_firebend_attack(obj, 2),
        make_attack_trigger(obj, attack_effect)
    ]

AZULA_ON_THE_HUNT = make_creature(
    name="Azula, On the Hunt",
    power=4,
    toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 2 — Whenever Azula attacks, you lose 1 life and create a Clue token. Menace.",
    setup_interceptors=azula_on_the_hunt_setup
)

def beetle_headed_merchants_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: may sac creature/artifact to draw and +1/+1 counter."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Sacrifice choice and effects handled by targeting system
        return []
    return [make_attack_trigger(obj, attack_effect)]

BEETLE_HEADED_MERCHANTS = make_creature(
    name="Beetle-Headed Merchants",
    power=5,
    toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Citizen"},
    text="Whenever this creature attacks, you may sacrifice another creature or artifact. If you do, draw a card and put a +1/+1 counter on this creature.",
    setup_interceptors=beetle_headed_merchants_setup
)

def boiling_rock_rioter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 1 ETB."""
    return [make_firebend_etb(obj, 1)]

BOILING_ROCK_RIOTER = make_creature(
    name="Boiling Rock Rioter",
    power=3,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Ally"},
    text="Firebend 1. {T}, Tap two other untapped Allies you control: Exile target card from a graveyard. You may cast Ally spells from among cards exiled with this creature.",
    setup_interceptors=boiling_rock_rioter_setup
)

def buzzard_wasp_colony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: may sac to draw. Death trigger: move counters."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Sacrifice choice handled by targeting system
        return []

    def death_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        died_id = event.payload.get('object_id')
        if died_id == o.id:
            return False
        died_obj = state.objects.get(died_id)
        if not died_obj:
            return False
        if died_obj.controller != o.controller:
            return False
        if CardType.CREATURE not in died_obj.characteristics.types:
            return False
        # Check if it had counters
        return bool(died_obj.counters)

    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Move counters from dying creature
        died_id = event.payload.get('object_id')
        died_obj = state.objects.get(died_id)
        if died_obj and died_obj.counters:
            events = []
            for counter_type, amount in died_obj.counters.items():
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': counter_type, 'amount': amount},
                    source=obj.id
                ))
            return events
        return []

    death_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=death_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    return [make_etb_trigger(obj, etb_effect), death_trigger]

BUZZARD_WASP_COLONY = make_creature(
    name="Buzzard-Wasp Colony",
    power=2,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Bird", "Insect"},
    text="Flying. When this creature enters, you may sacrifice an artifact or creature. If you do, draw a card. Whenever another creature you control dies, if it had counters on it, move those counters onto this creature.",
    setup_interceptors=buzzard_wasp_colony_setup
)

def canyon_crawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Food',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Food'},
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

CANYON_CRAWLER = make_creature(
    name="Canyon Crawler",
    power=6,
    toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spider", "Beast"},
    text="Deathtouch. When this creature enters, create a Food token. Swampcycling {2}",
    setup_interceptors=canyon_crawler_setup
)

def corrupt_court_official_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent discards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles which opponent
        return []
    return [make_etb_trigger(obj, etb_effect)]

CORRUPT_COURT_OFFICIAL = make_creature(
    name="Corrupt Court Official",
    power=1,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    text="When this creature enters, target opponent discards a card.",
    setup_interceptors=corrupt_court_official_setup
)

def cruel_administrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Raid: ETB with +1/+1 if attacked. Attack: create 1/1 Soldier attacking."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        if state.turn_data.get(f'{obj.controller}_attacked', False):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        return []

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Soldier',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Soldier'},
                'colors': {Color.RED},
                'is_token': True,
                'tapped': True,
                'attacking': True
            },
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]

CRUEL_ADMINISTRATOR = make_creature(
    name="Cruel Administrator",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Soldier"},
    text="Raid — This creature enters with a +1/+1 counter on it if you attacked this turn. Whenever this creature attacks, create a 1/1 red Soldier creature token that's tapped and attacking.",
    setup_interceptors=cruel_administrator_setup
)

DAI_LI_INDOCTRINATION = make_sorcery(
    name="Dai Li Indoctrination",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Lesson — Choose one: Target opponent discards a card; or earthbend 2."
)

DAY_OF_BLACK_SUN = make_sorcery(
    name="Day of Black Sun",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="All creatures with mana value X or less lose all abilities until end of turn, then destroy all creatures with mana value X or less."
)

DEADLY_PRECISION = make_sorcery(
    name="Deadly Precision",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, pay {4} or sacrifice a nonland permanent. Destroy target creature."
)

EPIC_DOWNFALL = make_sorcery(
    name="Epic Downfall",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Exile target creature with mana value 3 or greater."
)

FATAL_FISSURE = make_instant(
    name="Fatal Fissure",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. When that creature dies this turn, earthbend 4."
)

def fire_lord_ozai_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 3 ETB. End step: deal power damage to each opponent."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        power = obj.characteristics.power or 0
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': power, 'source': obj.id},
                    source=obj.id
                ))
        return events

    return [
        make_firebend_etb(obj, 3),
        make_end_step_trigger(obj, end_step_effect)
    ]

FIRE_LORD_OZAI = make_creature(
    name="Fire Lord Ozai",
    power=5,
    toughness=5,
    mana_cost="{3}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 3. Menace. At the beginning of your end step, Fire Lord Ozai deals damage equal to its power to each opponent.",
    setup_interceptors=fire_lord_ozai_setup
)

def long_feng_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 2 ETB. Upkeep: opponents lose life for +1/+1 countered creatures."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        counter_count = 0
        for game_obj in state.objects.values():
            if (game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.counters.get('+1/+1', 0) > 0):
                counter_count += 1

        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -counter_count},
                    source=obj.id
                ))
        return events

    return [
        make_earthbend_etb(obj, 2),
        make_upkeep_trigger(obj, upkeep_effect)
    ]

LONG_FENG = make_creature(
    name="Long Feng",
    power=3,
    toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="Earthbend 2. At the beginning of your upkeep, each opponent loses 1 life for each creature you control with a +1/+1 counter on it.",
    setup_interceptors=long_feng_setup
)

def mai_knives_expert_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: they discard."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.DISCARD,
                payload={'player': target, 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

MAI_KNIVES_EXPERT = make_creature(
    name="Mai, Knives Expert",
    power=2,
    toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Mai deals combat damage to a player, that player discards a card.",
    setup_interceptors=mai_knives_expert_setup
)


# =============================================================================
# RED CARDS
# =============================================================================

def boar_q_pine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Noncreature spell cast: +1/+1 counter."""
    def spell_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != o.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
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
        filter=lambda e, s: spell_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=spell_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

BOAR_Q_PINE = make_creature(
    name="Boar-q-pine",
    power=2,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Boar", "Porcupine"},
    text="Whenever you cast a noncreature spell, put a +1/+1 counter on this creature.",
    setup_interceptors=boar_q_pine_setup
)

BUMI_BASH = make_sorcery(
    name="Bumi Bash",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Choose one — Bumi Bash deals damage equal to the number of lands you control to target creature; or destroy target land creature or nonbasic land."
)

def combustion_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: destroy permanent unless controller takes power damage."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Choice handled by targeting system
        return []
    return [make_attack_trigger(obj, attack_effect)]

COMBUSTION_MAN = make_creature(
    name="Combustion Man",
    power=4,
    toughness=6,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="Whenever Combustion Man attacks, destroy target permanent unless its controller has Combustion Man deal damage to them equal to his power.",
    setup_interceptors=combustion_man_setup
)

COMBUSTION_TECHNIQUE = make_instant(
    name="Combustion Technique",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lesson — Combustion Technique deals damage equal to 2 plus the number of Lesson cards in your graveyard to target creature. If that creature would die this turn, exile it instead."
)

def fated_firepower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: enter with X fire counters. Damage modification (static effect)."""
    def damage_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if not source_obj or source_obj.controller != o.controller:
            return False
        target = event.payload.get('target')
        # Check if target is opponent or opponent's permanent
        if target in state.players and target != o.controller:
            return True
        target_obj = state.objects.get(target)
        return target_obj and target_obj.controller != o.controller

    def damage_modify(event: Event, state: GameState) -> InterceptorResult:
        fire_counters = obj.counters.get('fire', 0)
        if fire_counters > 0:
            new_amount = event.payload.get('amount', 0) + fire_counters
            new_payload = dict(event.payload)
            new_payload['amount'] = new_amount
            return InterceptorResult(
                action=InterceptorAction.MODIFY,
                modified_event=Event(type=event.type, payload=new_payload, source=event.source)
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.MODIFY,
        filter=lambda e, s: damage_filter(e, s, obj),
        handler=lambda e, s: damage_modify(e, s),
        duration='while_on_battlefield'
    )]

FATED_FIREPOWER = make_enchantment(
    name="Fated Firepower",
    mana_cost="{X}{R}{R}{R}",
    colors={Color.RED},
    text="Flash. This enchantment enters with X fire counters on it. If a source you control would deal damage to an opponent or a permanent an opponent controls, it deals that much damage plus the number of fire counters on this enchantment instead.",
    setup_interceptors=fated_firepower_setup
)

FIREBENDING_LESSON = make_instant(
    name="Firebending Lesson",
    mana_cost="{R}",
    colors={Color.RED},
    text="Lesson — Kicker {4}. Firebending Lesson deals 2 damage to target creature. If this spell was kicked, it deals 5 damage instead."
)

FIREBENDING_STUDENT = make_creature(
    name="Firebending Student",
    power=1,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    text="Prowess. Firebend X, where X is this creature's power."
)

FIRE_NATION_ATTACKS = make_instant(
    name="Fire Nation Attacks",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Create two 2/2 red Soldier creature tokens with firebend 1. Flashback {8}{R}."
)

FIRE_NATION_CADETS = make_creature(
    name="Fire Nation Cadets",
    power=1,
    toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="This creature has firebend 2 as long as there's a Lesson card in your graveyard. {2}: This creature gets +1/+0 until end of turn."
)

def fire_nation_warship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2 on attack."""
    return [make_firebend_attack(obj, 2)]

FIRE_NATION_WARSHIP = make_artifact(
    name="Fire Nation Warship",
    mana_cost="{4}{R}",
    subtypes={"Vehicle"},
    text="Flying. Firebend 2 — Whenever this Vehicle attacks, it deals 2 damage to any target. Crew 2",
    setup_interceptors=fire_nation_warship_setup
)

def jeong_jeong_the_deserter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 3. End step: if dealt 5+ damage, draw."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        damage_dealt = state.turn_data.get(f'{obj.controller}_damage_dealt', 0)
        if damage_dealt >= 5:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        return []

    return [
        make_firebend_etb(obj, 3),
        make_end_step_trigger(obj, end_step_effect)
    ]

JEONG_JEONG_THE_DESERTER = make_creature(
    name="Jeong Jeong, the Deserter",
    power=3,
    toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 3. At the beginning of your end step, if a source you controlled dealt 5 or more damage this turn, draw a card.",
    setup_interceptors=jeong_jeong_the_deserter_setup
)

def prince_zuko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2. Attack: may discard to draw (rummage)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Optional discard/draw handled by choice system
        return []
    return [
        make_firebend_etb(obj, 2),
        make_attack_trigger(obj, attack_effect)
    ]

PRINCE_ZUKO = make_creature(
    name="Prince Zuko",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 2. Whenever Prince Zuko attacks, you may discard a card. If you do, draw a card.",
    setup_interceptors=prince_zuko_setup
)

def zuko_redeemed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2. Combat damage: +1/+1 on another Ally."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles counter placement
        return []
    return [
        make_firebend_etb(obj, 2),
        make_damage_trigger(obj, damage_effect, combat_only=True)
    ]

ZUKO_REDEEMED = make_creature(
    name="Zuko, Redeemed",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 2. First strike. Whenever Zuko deals combat damage, put a +1/+1 counter on another target Ally you control.",
    setup_interceptors=zuko_redeemed_setup
)


# =============================================================================
# GREEN CARDS
# =============================================================================

ALLIES_AT_LAST = make_instant(
    name="Allies at Last",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Affinity for Allies. Up to two target creatures you control each deal damage equal to their power to target creature an opponent controls."
)

AVATAR_DESTINY = make_enchantment(
    name="Avatar Destiny",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Enchant creature. Enchanted creature gets +1/+1 for each creature card in your graveyard and is an Avatar in addition to its other types. When enchanted creature dies, mill cards equal to its power."
)

def badgermole_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 2 ETB. Grant trample to creatures with +1/+1 counters."""
    def counter_creature_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD and
                target.counters.get('+1/+1', 0) > 0)

    interceptors = [make_earthbend_etb(obj, 2)]
    interceptors.append(make_keyword_grant(obj, ['trample'], counter_creature_filter))
    return interceptors

BADGERMOLE = make_creature(
    name="Badgermole",
    power=4,
    toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Mole"},
    text="When this creature enters, earthbend 2. Creatures you control with +1/+1 counters on them have trample.",
    setup_interceptors=badgermole_setup
)

def badgermole_cub_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 1 ETB. Mana dork tap: add extra G."""
    return [make_earthbend_etb(obj, 1)]

BADGERMOLE_CUB = make_creature(
    name="Badgermole Cub",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Mole"},
    text="When this creature enters, earthbend 1. Whenever you tap a creature for mana, add an additional {G}.",
    setup_interceptors=badgermole_cub_setup
)

def bumi_king_of_three_trials_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: modal choice based on Lesson cards in graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice system handles selections based on Lesson count
        return []
    return [make_etb_trigger(obj, etb_effect)]

BUMI_KING_OF_THREE_TRIALS = make_creature(
    name="Bumi, King of Three Trials",
    power=4,
    toughness=4,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="When Bumi enters, choose up to X, where X is the number of Lesson cards in your graveyard: Put three +1/+1 counters on Bumi; target player scries 3; earthbend 3.",
    setup_interceptors=bumi_king_of_three_trials_setup
)

CYCLE_OF_RENEWAL = make_instant(
    name="Cycle of Renewal",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Lesson — Sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle."
)

def earthbender_ascension_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: earthbend 2 and search land. Landfall: quest counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        # Earthbend 2
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Wall',
                    'power': 0,
                    'toughness': 3,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Wall'},
                    'abilities': ['defender'],
                    'is_token': True
                },
                source=obj.id
            ))
        # Search land
        events.append(Event(
            type=EventType.SEARCH_LIBRARY,
            payload={'player': obj.controller, 'type': 'basic_land', 'to_zone': 'battlefield', 'tapped': True},
            source=obj.id
        ))
        return events

    def landfall_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        if entered_obj.controller != o.controller:
            return False
        return CardType.LAND in entered_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'quest', 'amount': 1},
            source=obj.id
        )]

    landfall_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: landfall_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=landfall_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    return [make_etb_trigger(obj, etb_effect), landfall_trigger]

EARTHBENDER_ASCENSION = make_enchantment(
    name="Earthbender Ascension",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, earthbend 2. Then search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Landfall — Whenever a land you control enters, put a quest counter on this enchantment.",
    setup_interceptors=earthbender_ascension_setup
)

EARTHBENDING_LESSON = make_sorcery(
    name="Earthbending Lesson",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Lesson — Earthbend 4. (Target land you control becomes a 0/0 creature with haste that's still a land. Put four +1/+1 counters on it.)"
)

def earth_kingdom_general_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 2 ETB. Counter placement: may gain life (once/turn)."""
    def counter_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        if event.payload.get('counter_type') != '+1/+1':
            return False
        # Check once per turn
        if state.turn_data.get(f'{o.id}_life_from_counter', False):
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return target.controller == o.controller

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 1)
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id
        )]

    counter_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: counter_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=counter_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    return [make_earthbend_etb(obj, 2), counter_trigger]

EARTH_KINGDOM_GENERAL = make_creature(
    name="Earth Kingdom General",
    power=2,
    toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Soldier", "Ally"},
    text="When this creature enters, earthbend 2. Whenever you put one or more +1/+1 counters on a creature, you may gain that much life. Do this only once each turn.",
    setup_interceptors=earth_kingdom_general_setup
)

EARTH_RUMBLE = make_sorcery(
    name="Earth Rumble",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Earthbend 2. When you do, up to one target creature you control fights target creature an opponent controls."
)

def toph_beifong_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 3 ETB. Creatures with +1/+1 get trample and hexproof."""
    def counter_creature_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD and
                target.counters.get('+1/+1', 0) > 0)

    return [
        make_earthbend_etb(obj, 3),
        make_keyword_grant(obj, ['trample', 'hexproof'], counter_creature_filter)
    ]

TOPH_BEIFONG = make_creature(
    name="Toph Beifong",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Earthbend 3. Creatures you control with +1/+1 counters have trample and hexproof.",
    setup_interceptors=toph_beifong_setup
)

def toph_metalbender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 4 ETB. Artifact creatures get +2/+2."""
    def artifact_creature_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                CardType.ARTIFACT in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors = [make_earthbend_etb(obj, 4)]
    interceptors.extend(make_static_pt_boost(obj, 2, 2, artifact_creature_filter))
    return interceptors

TOPH_METALBENDER = make_creature(
    name="Toph, Metalbender",
    power=4,
    toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Earthbend 4. You may cast artifact spells as though they had flash. Artifact creatures you control get +2/+2.",
    setup_interceptors=toph_metalbender_setup
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def aang_and_la_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: bounce all opponent creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for game_obj in state.objects.values():
            if (game_obj.controller != obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': game_obj.id,
                        'from_zone_type': ZoneType.BATTLEFIELD,
                        'to_zone_type': ZoneType.HAND,
                        'to_owner': game_obj.owner
                    },
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]

AANG_AND_LA = make_creature(
    name="Aang and La, Ocean's Fury",
    power=5,
    toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Avatar", "Spirit", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Hexproof. When this creature enters, return all creatures your opponents control to their owners' hands.",
    setup_interceptors=aang_and_la_setup
)

def beifongs_bounty_hunters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creature death: earthbend X where X is power."""
    def death_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        died_id = event.payload.get('object_id')
        if died_id == o.id:
            return False
        died_obj = state.objects.get(died_id)
        if not died_obj:
            return False
        if died_obj.controller != o.controller:
            return False
        if CardType.CREATURE not in died_obj.characteristics.types:
            return False
        return not getattr(died_obj, 'is_token', False)

    def death_effect(event: Event, state: GameState) -> list[Event]:
        died_id = event.payload.get('object_id')
        died_obj = state.objects.get(died_id)
        if died_obj:
            power = died_obj.characteristics.power or 0
            events = []
            for _ in range(power):
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'controller': obj.controller,
                        'name': 'Wall',
                        'power': 0,
                        'toughness': 3,
                        'types': {CardType.CREATURE},
                        'subtypes': {'Wall'},
                        'abilities': ['defender'],
                        'is_token': True
                    },
                    source=obj.id
                ))
            return events
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=death_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

BEIFONGS_BOUNTY_HUNTERS = make_creature(
    name="Beifong's Bounty Hunters",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Mercenary"},
    text="Whenever a nontoken creature you control dies, earthbend X, where X is that creature's power.",
    setup_interceptors=beifongs_bounty_hunters_setup
)

def bitter_work_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack with power 4+ creature: draw a card."""
    def attack_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.DECLARE_ATTACKERS:
            return False
        if event.payload.get('controller') != o.controller:
            return False
        # Check if any attacker has power 4+
        attackers = event.payload.get('attackers', [])
        for attacker_id in attackers:
            attacker = state.objects.get(attacker_id)
            if attacker and (attacker.characteristics.power or 0) >= 4:
                return True
        return False

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: attack_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=attack_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

BITTER_WORK = make_enchantment(
    name="Bitter Work",
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Whenever you attack a player with one or more creatures with power 4 or greater, draw a card. Exhaust — {4}: Earthbend 4.",
    setup_interceptors=bitter_work_setup
)

def bumi_unleashed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 4 ETB. Combat damage: untap lands, extra combat."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [
                Event(
                    type=EventType.UNTAP_ALL,
                    payload={'controller': obj.controller, 'type': 'land'},
                    source=obj.id
                ),
                Event(
                    type=EventType.EXTRA_COMBAT,
                    payload={'player': obj.controller},
                    source=obj.id
                )
            ]
        return []
    return [
        make_earthbend_etb(obj, 4),
        make_damage_trigger(obj, damage_effect, combat_only=True)
    ]

BUMI_UNLEASHED = make_creature(
    name="Bumi, Unleashed",
    power=5,
    toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Trample. When Bumi enters, earthbend 4. Whenever Bumi deals combat damage to a player, untap all lands you control. After this phase, there is an additional combat phase.",
    setup_interceptors=bumi_unleashed_setup
)

def dai_li_agents_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: earthbend 1, then earthbend 1. Attack: drain for +1/+1 creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Wall',
                    'power': 0,
                    'toughness': 3,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Wall'},
                    'abilities': ['defender'],
                    'is_token': True
                },
                source=obj.id
            ))
        return events

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        counter_count = 0
        for game_obj in state.objects.values():
            if (game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.counters.get('+1/+1', 0) > 0):
                counter_count += 1

        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -counter_count},
                    source=obj.id
                ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': counter_count},
            source=obj.id
        ))
        return events

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]

DAI_LI_AGENTS = make_creature(
    name="Dai Li Agents",
    power=3,
    toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, earthbend 1, then earthbend 1. Whenever this creature attacks, each opponent loses X life and you gain X life, where X is the number of creatures you control with +1/+1 counters on them.",
    setup_interceptors=dai_li_agents_setup
)

def fire_lord_azula_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2 ETB. Instant/sorcery while attacking: copy spell."""
    def spell_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != o.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        if not (CardType.INSTANT in spell_types or CardType.SORCERY in spell_types):
            return False
        # Check if controller is attacking
        return state.combat_data.get(f'{o.controller}_is_attacking', False)

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COPY_SPELL,
            payload={'spell_id': event.payload.get('spell_id')},
            source=obj.id
        )]

    spell_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: spell_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=spell_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    return [make_firebend_etb(obj, 2), spell_trigger]

FIRE_LORD_AZULA = make_creature(
    name="Fire Lord Azula",
    power=4,
    toughness=4,
    mana_cost="{1}{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 2. Whenever you cast an instant or sorcery spell while attacking, copy that spell. You may choose new targets for the copy.",
    setup_interceptors=fire_lord_azula_setup
)

def fire_lord_zuko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell cast from exile: put +1/+1 counter on self."""
    def cast_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != o.controller:
            return False
        # Check if cast from exile
        return event.payload.get('from_zone') == ZoneType.EXILE

    def cast_effect(event: Event, state: GameState) -> list[Event]:
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
        filter=lambda e, s: cast_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=cast_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

FIRE_LORD_ZUKO = make_creature(
    name="Fire Lord Zuko",
    power=2,
    toughness=4,
    mana_cost="{R}{W}{B}",
    colors={Color.RED, Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Firebend X, where X is the number of cards you've cast from exile this turn. Whenever you cast a spell from exile, put a +1/+1 counter on Fire Lord Zuko.",
    setup_interceptors=fire_lord_zuko_setup
)

def team_avatar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: modal - airbend, waterbend, earthbend 3, firebend 3."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Modal ability with any number of choices - targeting handles this
        return []
    return [make_etb_trigger(obj, etb_effect)]

TEAM_AVATAR = make_creature(
    name="Team Avatar",
    power=4,
    toughness=4,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying, vigilance, trample. When Team Avatar enters, choose any number: Airbend up to one creature; waterbend (tap target creature, it doesn't untap); earthbend 3; firebend 3.",
    setup_interceptors=team_avatar_setup
)

def ty_lee_acrobat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to creature: tap + freeze."""
    def damage_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != o.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target = event.payload.get('target')
        target_obj = state.objects.get(target)
        return target_obj and CardType.CREATURE in target_obj.characteristics.types

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        return [
            Event(
                type=EventType.TAP,
                payload={'object_id': target},
                source=obj.id
            ),
            Event(
                type=EventType.FREEZE,
                payload={'object_id': target},
                source=obj.id
            )
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=damage_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

TY_LEE_ACROBAT = make_creature(
    name="Ty Lee, Acrobat",
    power=2,
    toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Ty Lee deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step.",
    setup_interceptors=ty_lee_acrobat_setup
)


# =============================================================================
# ARTIFACT CARDS
# =============================================================================

def aang_statue_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create 1/1 Ally token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Ally',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Ally'},
                'colors': {Color.WHITE},
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

AANG_STATUE = make_artifact(
    name="Aang Statue",
    mana_cost="{3}",
    text="When Aang Statue enters, create a 1/1 white Ally creature token. {T}: Add one mana of any color. Spend this mana only to cast Ally spells.",
    setup_interceptors=aang_statue_setup
)

def earth_kingdom_tank_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: +1/+1 counter on land creature you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles which land creature
        return []
    return [make_attack_trigger(obj, attack_effect)]

EARTH_KINGDOM_TANK = make_artifact(
    name="Earth Kingdom Tank",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    text="Trample. Earthbend 1 — Whenever this Vehicle attacks, put a +1/+1 counter on target land creature you control. Crew 2",
    setup_interceptors=earth_kingdom_tank_setup
)

METEORITE_SWORD = make_artifact(
    name="Meteorite Sword",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+1 and has first strike. Whenever equipped creature deals combat damage to a player, you may search your library for an Equipment card, reveal it, put it into your hand, then shuffle. Equip {2}"
)

SPIRIT_OASIS = make_artifact(
    name="Spirit Oasis",
    mana_cost="{3}",
    text="At the beginning of your upkeep, you gain 1 life. {T}: Add one mana of any color. {3}, {T}, Sacrifice Spirit Oasis: Create a 4/4 blue Spirit creature token with flying."
)


# =============================================================================
# LAND CARDS
# =============================================================================

AIR_TEMPLE = make_land(
    name="Air Temple",
    text="Air Temple enters tapped. {T}: Add {W}. {T}: Add {U}. Activate only if you control an Ally."
)

BA_SING_SE = make_land(
    name="Ba Sing Se",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {G} or {W}. Activate only if you control a creature with a +1/+1 counter on it."
)

FIRE_NATION_CAPITAL = make_land(
    name="Fire Nation Capital",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {B} or {R}. Activate only if a source you controlled dealt damage to an opponent this turn."
)

SPIRIT_WORLD_GATE = make_land(
    name="Spirit World Gate",
    text="Spirit World Gate enters tapped. When Spirit World Gate enters, scry 1. {T}: Add one mana of any color."
)

WATER_TRIBE_VILLAGE = make_land(
    name="Water Tribe Village",
    text="Water Tribe Village enters tapped. {T}: Add {W} or {U}."
)

FIRE_NATION_OUTPOST = make_land(
    name="Fire Nation Outpost",
    text="Fire Nation Outpost enters tapped. {T}: Add {B} or {R}."
)

EARTH_KINGDOM_FORTRESS = make_land(
    name="Earth Kingdom Fortress",
    text="Earth Kingdom Fortress enters tapped. {T}: Add {G}. {1}{G}, {T}, Sacrifice this land: Earthbend 2."
)

OMASHU = make_land(
    name="Omashu",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {G}. Activate only if you control a legendary creature."
)

EMBER_ISLAND = make_land(
    name="Ember Island",
    text="Ember Island enters tapped. {T}: Add {R}. Firebend 1 — {3}{R}, {T}: Put a +1/+1 counter on target creature you control."
)

FOG_OF_LOST_SOULS = make_land(
    name="Fog of Lost Souls",
    text="{T}: Add {C}. {2}, {T}: Target creature gets -2/-0 until end of turn."
)


# =============================================================================
# ADDITIONAL WHITE CARDS
# =============================================================================

def kyoshi_island_defender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Warriors have vigilance."""
    def other_warrior_filter(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Warrior' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['vigilance'], other_warrior_filter)]

KYOSHI_ISLAND_DEFENDER = make_creature(
    name="Kyoshi Island Defender",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    text="First strike. Other Warrior creatures you control have vigilance.",
    setup_interceptors=kyoshi_island_defender_setup
)

def meelo_the_troublemaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Airbend on ETB or attack (power 2 or less creatures)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles power 2 or less restriction
        return []
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []
    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]

MEELO_THE_TROUBLEMAKER = make_creature(
    name="Meelo, the Troublemaker",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Airbend — When Meelo enters or attacks, you may airbend target creature with power 2 or less.",
    setup_interceptors=meelo_the_troublemaker_setup
)

def momo_loyal_companion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ally ETB: scry 1."""
    def ally_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_ally_etb_trigger(obj, ally_effect)]

MOMO_LOYAL_COMPANION = make_creature(
    name="Momo, Loyal Companion",
    power=1,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Bat", "Lemur", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever another Ally you control enters, scry 1.",
    setup_interceptors=momo_loyal_companion_setup
)

def airbender_initiate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lesson cast: +1/+1 until end of turn."""
    def lesson_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_PT_MODIFIER,
            payload={'object_id': obj.id, 'power': 1, 'toughness': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_lesson_trigger(obj, lesson_effect)]

AIRBENDER_INITIATE = make_creature(
    name="Airbender Initiate",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Flying. Whenever you cast a Lesson spell, Airbender Initiate gets +1/+1 until end of turn.",
    setup_interceptors=airbender_initiate_setup
)

def cabbage_merchant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: create 3 Food tokens."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(3):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Food',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Food'},
                    'is_token': True
                },
                source=obj.id
            ))
        return events
    return [make_death_trigger(obj, death_effect)]

CABBAGE_MERCHANT = make_creature(
    name="Cabbage Merchant",
    power=0,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="When Cabbage Merchant dies, create three Food tokens. 'MY CABBAGES!'",
    setup_interceptors=cabbage_merchant_setup
)

MONASTIC_DISCIPLINE = make_instant(
    name="Monastic Discipline",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Lesson — Target creature you control gains indestructible until end of turn. Untap it."
)

WINDS_OF_CHANGE = make_sorcery(
    name="Winds of Change",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Airbend up to two target creatures."
)

def avatar_korra_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: modal choice of airbend or waterbend."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice handled by choice system
        return []
    return [make_attack_trigger(obj, attack_effect)]

AVATAR_KORRA_SPIRIT = make_creature(
    name="Avatar Korra, Spirit Bridge",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever Avatar Korra attacks, you may airbend or waterbend target creature.",
    setup_interceptors=avatar_korra_spirit_setup
)

PEACEFUL_SANCTUARY = make_enchantment(
    name="Peaceful Sanctuary",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures can't attack you unless their controller pays {2} for each creature attacking you."
)

GURU_PATHIK = make_creature(
    name="Guru Pathik",
    power=0,
    toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="{T}: Target Avatar you control gains hexproof and lifelink until end of turn. Scry 1."
)

LION_TURTLE_BLESSING = make_instant(
    name="Lion Turtle Blessing",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Target creature becomes an Avatar in addition to its other types and gains flying, first strike, vigilance, trample, and lifelink until end of turn."
)

def gyatso_wise_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lesson cast: create 1/1 Ally token."""
    def lesson_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Ally',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Ally'},
                'colors': {Color.WHITE},
                'is_token': True
            },
            source=obj.id
        )]
    return [make_lesson_trigger(obj, lesson_effect)]

GYATSO_WISE_MENTOR = make_creature(
    name="Gyatso, Wise Mentor",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Whenever you cast a Lesson spell, create a 1/1 white Ally creature token.",
    setup_interceptors=gyatso_wise_mentor_setup
)


# =============================================================================
# ADDITIONAL BLUE CARDS
# =============================================================================

HAMA_BLOODBENDER = make_creature(
    name="Hama, Bloodbender",
    power=2,
    toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Waterbend — {2}{U}{B}, {T}: Gain control of target creature until end of turn. Untap it. It gains haste."
)

SERPENTS_PASS_HORROR = make_creature(
    name="Serpent's Pass Horror",
    power=6,
    toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="Hexproof. Serpent's Pass Horror can't be blocked except by creatures with flying."
)

def southern_water_tribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: draw, then discard (loot)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, etb_effect)]

SOUTHERN_WATER_TRIBE = make_creature(
    name="Southern Water Tribe",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    text="When this creature enters, draw a card, then discard a card.",
    setup_interceptors=southern_water_tribe_setup
)

def foggy_swamp_waterbender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: waterbend (tap + freeze) target creature."""
    return [make_waterbend_etb(obj, 0, 0)]

FOGGY_SWAMP_WATERBENDER = make_creature(
    name="Foggy Swamp Waterbender",
    power=3,
    toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flash. When this creature enters, waterbend up to one target creature. (Tap it. It doesn't untap during its controller's next untap step.)",
    setup_interceptors=foggy_swamp_waterbender_setup
)

def spirit_fox_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

SPIRIT_FOX = make_creature(
    name="Spirit Fox",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fox", "Spirit"},
    text="When Spirit Fox enters, scry 2.",
    setup_interceptors=spirit_fox_setup
)

UNAGI_ATTACK = make_instant(
    name="Unagi Attack",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Create a 4/3 blue Serpent creature token with 'When this creature dies, draw a card.'"
)

WISDOM_OF_AGES = make_sorcery(
    name="Wisdom of Ages",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Draw three cards. If you control an Avatar, draw four cards instead."
)

def avatar_roku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2. ETB: return instant/sorcery from graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles graveyard retrieval
        return []
    return [
        make_firebend_etb(obj, 2),
        make_etb_trigger(obj, etb_effect)
    ]

AVATAR_ROKU = make_creature(
    name="Avatar Roku",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Flying. Firebend 2. When Avatar Roku enters, you may return target instant or sorcery card from your graveyard to your hand.",
    setup_interceptors=avatar_roku_setup
)

def spirit_world_wanderer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: scry 2."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

SPIRIT_WORLD_WANDERER = make_creature(
    name="Spirit World Wanderer",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. Whenever Spirit World Wanderer deals combat damage to a player, scry 2.",
    setup_interceptors=spirit_world_wanderer_setup
)

WATER_TRIBE_HEALER = make_creature(
    name="Water Tribe Healer",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Cleric", "Ally"},
    text="{T}: Prevent the next 2 damage that would be dealt to target creature this turn."
)

def tui_and_la_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creature ETB: tap or untap target permanent."""
    def creature_etb_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        if entered_obj.controller != o.controller:
            return False
        return CardType.CREATURE in entered_obj.characteristics.types

    def creature_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles tap/untap choice
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=creature_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

TUI_AND_LA = make_creature(
    name="Tui and La",
    power=4,
    toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Spirit"},
    supertypes={"Legendary"},
    text="Hexproof. Waterbend — Whenever a creature enters under your control, you may tap or untap target permanent.",
    setup_interceptors=tui_and_la_setup
)

MIST_VEIL = make_instant(
    name="Mist Veil",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof until end of turn. Draw a card."
)


# =============================================================================
# ADDITIONAL BLACK CARDS
# =============================================================================

def zhao_the_conqueror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2. Attack: destroy lowest toughness creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles destruction
        return []
    return [
        make_firebend_etb(obj, 2),
        make_attack_trigger(obj, attack_effect)
    ]

ZHAO_THE_CONQUEROR = make_creature(
    name="Zhao, the Conqueror",
    power=4,
    toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Menace. Firebend 2. Whenever Zhao attacks, destroy target creature with the least toughness among creatures you don't control.",
    setup_interceptors=zhao_the_conqueror_setup
)

def dai_li_enforcer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 1 ETB. Attack: opponent discards."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles which opponent
        return []
    return [
        make_earthbend_etb(obj, 1),
        make_attack_trigger(obj, attack_effect)
    ]

DAI_LI_ENFORCER = make_creature(
    name="Dai Li Enforcer",
    power=2,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Earthbend 1. Whenever this creature attacks, target opponent discards a card.",
    setup_interceptors=dai_li_enforcer_setup
)

SPIRIT_CORRUPTION = make_enchantment(
    name="Spirit Corruption",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Enchant creature. Enchanted creature gets -3/-3. When enchanted creature dies, create a 2/2 black Spirit creature token with flying."
)

BLOODBENDING_LESSON = make_instant(
    name="Bloodbending Lesson",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Lesson — Gain control of target creature until end of turn. Untap it. It gains haste and 'At end of turn, sacrifice this creature.'"
)

SHADOW_OF_THE_PAST = make_sorcery(
    name="Shadow of the Past",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. You lose 2 life."
)

FIRE_NATION_PRISON = make_enchantment(
    name="Fire Nation Prison",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="When Fire Nation Prison enters, exile target creature an opponent controls until Fire Nation Prison leaves the battlefield. That creature's controller creates a Food token."
)

CRUEL_AMBITION = make_sorcery(
    name="Cruel Ambition",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. You draw a card for each creature sacrificed this way."
)

def spirit_of_revenge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: opponents lose 2 life."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -2},
                    source=obj.id
                ))
        return events
    return [make_death_trigger(obj, death_effect)]

SPIRIT_OF_REVENGE = make_creature(
    name="Spirit of Revenge",
    power=3,
    toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying, deathtouch. When Spirit of Revenge dies, each opponent loses 2 life.",
    setup_interceptors=spirit_of_revenge_setup
)

def war_balloon_crew_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 1 ETB. Death: opponents lose 2 life."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -2},
                    source=obj.id
                ))
        return events
    return [
        make_firebend_etb(obj, 1),
        make_death_trigger(obj, death_effect)
    ]

WAR_BALLOON_CREW = make_creature(
    name="War Balloon Crew",
    power=2,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Flying. Firebend 1. When War Balloon Crew dies, each opponent loses 2 life.",
    setup_interceptors=war_balloon_crew_setup
)

LAKE_LAOGAI = make_enchantment(
    name="Lake Laogai",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="When Lake Laogai enters, exile target creature. For as long as Lake Laogai remains on the battlefield, that creature's controller may cast that card. When they do, sacrifice Lake Laogai."
)


# =============================================================================
# ADDITIONAL RED CARDS
# =============================================================================

def fire_nation_commander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2 ETB."""
    return [make_firebend_etb(obj, 2)]

FIRE_NATION_COMMANDER = make_creature(
    name="Fire Nation Commander",
    power=4,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Firebend 2. Other creatures you control have firebend 1.",
    setup_interceptors=fire_nation_commander_setup
)

def iroh_dragon_of_the_west_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 3 ETB. Upkeep: may pay R to deal 2."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Cost and targeting handled by choice system
        return []
    return [
        make_firebend_etb(obj, 3),
        make_upkeep_trigger(obj, upkeep_effect)
    ]

IROH_DRAGON_OF_THE_WEST = make_creature(
    name="Iroh, Dragon of the West",
    power=4,
    toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 3. At the beginning of your upkeep, you may pay {R}. If you do, Iroh deals 2 damage to any target.",
    setup_interceptors=iroh_dragon_of_the_west_setup
)

LIGHTNING_REDIRECTION = make_instant(
    name="Lightning Redirection",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lesson — Change the target of target spell or ability with a single target to a new target."
)

SOZINS_COMET = make_sorcery(
    name="Sozin's Comet",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Until end of turn, if a red source you control would deal damage, it deals double that damage instead. Creatures you control with firebend get +3/+0 until end of turn."
)

AGNI_KAI = make_sorcery(
    name="Agni Kai",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control fights target creature you don't control. If your creature wins, firebend 2."
)

DRAGON_DANCE = make_instant(
    name="Dragon Dance",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Lesson — Target creature gets +3/+0 and gains first strike until end of turn. If it's an Avatar, it also gains trample."
)

def ran_and_shaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 4 ETB + deal 4 damage divided."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Damage division handled by targeting system
        return []
    return [
        make_firebend_etb(obj, 4),
        make_etb_trigger(obj, etb_effect)
    ]

RAN_AND_SHAW = make_creature(
    name="Ran and Shaw",
    power=6,
    toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying. Firebend 4. When Ran and Shaw enters, you may have it deal 4 damage divided as you choose among any number of targets.",
    setup_interceptors=ran_and_shaw_setup
)

def fire_lily_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 1 ETB. End step: sacrifice."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SACRIFICE,
            payload={'object_id': obj.id},
            source=obj.id
        )]
    return [
        make_firebend_etb(obj, 1),
        make_end_step_trigger(obj, end_step_effect)
    ]

FIRE_LILY = make_creature(
    name="Fire Lily",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. Firebend 1. At the beginning of your end step, sacrifice Fire Lily.",
    setup_interceptors=fire_lily_setup
)

VOLCANIC_ERUPTION = make_sorcery(
    name="Volcanic Eruption",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Volcanic Eruption deals X damage to each creature without flying. Earthbend X."
)

def phoenix_reborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: may pay 2R to return at next end step."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Cost payment and delayed trigger handled by choice system
        return []
    return [make_death_trigger(obj, death_effect)]

PHOENIX_REBORN = make_creature(
    name="Phoenix Reborn",
    power=3,
    toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Phoenix"},
    text="Flying, haste. When Phoenix Reborn dies, you may pay {2}{R}. If you do, return it to the battlefield at the beginning of the next end step.",
    setup_interceptors=phoenix_reborn_setup
)


# =============================================================================
# ADDITIONAL GREEN CARDS
# =============================================================================

def swampbender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create 2/2 Plant token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Plant',
                'power': 2,
                'toughness': 2,
                'types': {CardType.CREATURE},
                'subtypes': {'Plant'},
                'colors': {Color.GREEN},
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

SWAMPBENDER = make_creature(
    name="Swampbender",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard"},
    text="Reach. When Swampbender enters, create a 2/2 green Plant creature token.",
    setup_interceptors=swampbender_setup
)

def flying_bison_herd_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two 1/1 flying Ally tokens."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Ally',
                    'power': 1,
                    'toughness': 1,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Ally'},
                    'colors': {Color.WHITE},
                    'abilities': ['flying'],
                    'is_token': True
                },
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]

FLYING_BISON_HERD = make_creature(
    name="Flying Bison Herd",
    power=5,
    toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bison"},
    text="Flying. When Flying Bison Herd enters, create two 1/1 white Ally creature tokens with flying.",
    setup_interceptors=flying_bison_herd_setup
)

def avatar_kyoshi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 3 ETB + create Kyoshi's Fans artifact."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        # Earthbend 3
        for _ in range(3):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Wall',
                    'power': 0,
                    'toughness': 3,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Wall'},
                    'abilities': ['defender'],
                    'is_token': True
                },
                source=obj.id
            ))
        # Create Kyoshi's Fans
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': "Kyoshi's Fans",
                'types': {CardType.ARTIFACT},
                'supertypes': {'Legendary'},
                'is_token': True
            },
            source=obj.id
        ))
        return events
    return [make_etb_trigger(obj, etb_effect)]

AVATAR_KYOSHI = make_creature(
    name="Avatar Kyoshi",
    power=4,
    toughness=5,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Avatar", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance. Earthbend 3. When Avatar Kyoshi enters, create a legendary artifact token named Kyoshi's Fans with '{T}: Target creature you control gains +2/+0 and first strike until end of turn.'",
    setup_interceptors=avatar_kyoshi_setup
)

def forest_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: search basic land to hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={'player': obj.controller, 'type': 'basic_land', 'to_zone': 'hand'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

FOREST_SPIRIT = make_creature(
    name="Forest Spirit",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Treefolk"},
    text="Reach. When Forest Spirit enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=forest_spirit_setup
)

def catgator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: draw."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

CATGATOR = make_creature(
    name="Catgator",
    power=3,
    toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Crocodile"},
    text="Whenever Catgator deals combat damage to a player, draw a card.",
    setup_interceptors=catgator_setup
)

def swamp_giant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: return creature from graveyard to hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles graveyard selection
        return []
    return [make_etb_trigger(obj, etb_effect)]

SWAMP_GIANT = make_creature(
    name="Swamp Giant",
    power=7,
    toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Giant"},
    text="Trample. When Swamp Giant enters, you may return target creature card from your graveyard to your hand.",
    setup_interceptors=swamp_giant_setup
)

EARTH_KINGDOM_FARMER = make_creature(
    name="Earth Kingdom Farmer",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Peasant"},
    text="{T}: Add {G}. {2}{G}, {T}: Earthbend 1."
)

def natural_harmony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Land ETB: gain 1 life. Creature with +1/+1 ETB: draw."""
    def land_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        if entered_obj.controller != o.controller:
            return False
        return CardType.LAND in entered_obj.characteristics.types

    def land_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    def creature_counter_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        if entered_obj.controller != o.controller:
            return False
        if CardType.CREATURE not in entered_obj.characteristics.types:
            return False
        return entered_obj.counters.get('+1/+1', 0) > 0

    def creature_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    land_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: land_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=land_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    creature_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_counter_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=creature_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    return [land_trigger, creature_trigger]

NATURAL_HARMONY = make_enchantment(
    name="Natural Harmony",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever a land enters under your control, you gain 1 life. Whenever a creature with a +1/+1 counter enters under your control, draw a card.",
    setup_interceptors=natural_harmony_setup
)

PRIMAL_FURY = make_instant(
    name="Primal Fury",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Lesson — Target creature gets +3/+3 and gains trample until end of turn."
)

def platypus_bear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: create Food."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Food',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Food'},
                    'is_token': True
                },
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

PLATYPUS_BEAR = make_creature(
    name="Platypus Bear",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Bear", "Platypus"},
    text="Trample. Whenever Platypus Bear deals combat damage to a player, create a Food token.",
    setup_interceptors=platypus_bear_setup
)

SPIRIT_VINE = make_creature(
    name="Spirit Vine",
    power=0,
    toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spirit"},
    text="Defender. {T}: Add one mana of any color. {4}{G}, {T}: Put three +1/+1 counters on Spirit Vine. It loses defender."
)


# =============================================================================
# ADDITIONAL MULTICOLOR CARDS
# =============================================================================

def sokka_and_suki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: target attacking Warrior gets +2/+2."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles Warrior selection
        return []
    return [make_attack_trigger(obj, attack_effect)]

SOKKA_AND_SUKI = make_creature(
    name="Sokka and Suki",
    power=3,
    toughness=4,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Whenever Sokka and Suki attacks, up to one other target attacking Warrior gets +2/+2 until end of turn.",
    setup_interceptors=sokka_and_suki_setup
)

def zuko_and_iroh_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2 ETB. End step: if dealt damage, draw and gain 2."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if state.turn_data.get(f'{obj.controller}_dealt_damage_to_opponent', False):
            return [
                Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id
                ),
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': 2},
                    source=obj.id
                )
            ]
        return []
    return [
        make_firebend_etb(obj, 2),
        make_end_step_trigger(obj, end_step_effect)
    ]

ZUKO_AND_IROH = make_creature(
    name="Zuko and Iroh",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 2. At the beginning of your end step, if you dealt damage to an opponent this turn, draw a card and you gain 2 life.",
    setup_interceptors=zuko_and_iroh_setup
)

def katara_and_aang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: airbend or waterbend target."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice handled by targeting system
        return []
    return [make_attack_trigger(obj, attack_effect)]

KATARA_AND_AANG = make_creature(
    name="Katara and Aang",
    power=3,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever Katara and Aang attacks, choose one — Airbend target creature; or waterbend target creature.",
    setup_interceptors=katara_and_aang_setup
)

def azula_and_dai_li_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 2 ETB. Attack: opponent sacrifices creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles which opponent
        return []
    return [
        make_earthbend_etb(obj, 2),
        make_attack_trigger(obj, attack_effect)
    ]

AZULA_AND_DAI_LI = make_creature(
    name="Azula and Dai Li",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Menace. Earthbend 2. Whenever Azula and Dai Li attacks, target opponent sacrifices a creature.",
    setup_interceptors=azula_and_dai_li_setup
)

def spirit_world_portal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]

SPIRIT_WORLD_PORTAL = make_enchantment(
    name="Spirit World Portal",
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="At the beginning of your upkeep, scry 1. {2}{G}{U}: Create a 2/2 blue Spirit creature token with flying.",
    setup_interceptors=spirit_world_portal_setup
)

def firelord_sozin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 3 ETB + destroy MV 3 or less permanent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles destruction
        return []
    return [
        make_firebend_etb(obj, 3),
        make_etb_trigger(obj, etb_effect)
    ]

FIRELORD_SOZIN = make_creature(
    name="Firelord Sozin",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 3. Menace. When Firelord Sozin enters, destroy target nonland permanent an opponent controls with mana value 3 or less.",
    setup_interceptors=firelord_sozin_setup
)

def avatar_yangchen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: airbend up to 2 creatures."""
    return [make_airbend_attack(obj)]

AVATAR_YANGCHEN = make_creature(
    name="Avatar Yangchen",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Avatar Yangchen attacks, airbend up to two target creatures.",
    setup_interceptors=avatar_yangchen_setup
)

def avatar_kuruk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: tap/untap up to 2 permanents."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles tap/untap choice
        return []
    return [make_attack_trigger(obj, attack_effect)]

AVATAR_KURUK = make_creature(
    name="Avatar Kuruk",
    power=4,
    toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Waterbend — Whenever Avatar Kuruk attacks, you may tap or untap up to two target permanents.",
    setup_interceptors=avatar_kuruk_setup
)

def lion_turtle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target becomes Avatar with hexproof."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles type/hexproof grant
        return []
    return [make_etb_trigger(obj, etb_effect)]

LION_TURTLE = make_creature(
    name="Lion Turtle",
    power=8,
    toughness=8,
    mana_cost="{6}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Turtle", "Spirit"},
    supertypes={"Legendary"},
    text="Hexproof. Islandwalk. When Lion Turtle enters, target creature becomes an Avatar in addition to its other types and gains hexproof until end of turn.",
    setup_interceptors=lion_turtle_setup
)

def koizilla_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: bounce all other creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for game_obj in state.objects.values():
            if (game_obj.id != obj.id and
                CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': game_obj.id,
                        'from_zone_type': ZoneType.BATTLEFIELD,
                        'to_zone_type': ZoneType.HAND,
                        'to_owner': game_obj.owner
                    },
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]

KOIZILLA = make_creature(
    name="Koizilla",
    power=10,
    toughness=10,
    mana_cost="{5}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Avatar", "Spirit", "Fish"},
    supertypes={"Legendary"},
    text="This spell costs {2} less to cast if you control an Avatar. Trample, hexproof. When Koizilla enters, return all other creatures to their owners' hands.",
    setup_interceptors=koizilla_setup
)

def hei_bai_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create Saplings or destroy small creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice handled by choice system
        return []
    return [make_etb_trigger(obj, etb_effect)]

HEIBAIFACED_SPIRIT = make_creature(
    name="Hei Bai, Forest Spirit",
    power=4,
    toughness=4,
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Spirit", "Panda"},
    supertypes={"Legendary"},
    text="When Hei Bai enters, choose one — Create two 1/1 green Sapling creature tokens; or destroy target creature with mana value 3 or less.",
    setup_interceptors=hei_bai_setup
)


# =============================================================================
# ADDITIONAL ARTIFACTS
# =============================================================================

def war_balloon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: firebend 1."""
    return [make_firebend_attack(obj, 1)]

WAR_BALLOON = make_artifact(
    name="War Balloon",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    text="Flying. Whenever War Balloon attacks, firebend 1. Crew 2",
    setup_interceptors=war_balloon_setup
)

AZULAS_CROWN = make_artifact(
    name="Azula's Crown",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+1 and has menace. Whenever equipped creature deals combat damage to a player, that player discards a card. Equip {3}"
)

WATER_POUCH = make_artifact(
    name="Water Pouch",
    mana_cost="{1}",
    text="Water Pouch enters with three water counters on it. {T}, Remove a water counter: Add {U}. {T}, Remove a water counter: Target creature doesn't untap during its controller's next untap step."
)

FIRE_NATION_HELM = make_artifact(
    name="Fire Nation Helm",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1 and has firebend 1. Equip {2}"
)

AANGS_STAFF = make_artifact(
    name="Aang's Staff",
    mana_cost="{3}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +2/+0 and has flying. Whenever equipped creature attacks, airbend target creature. Equip Avatar {1}. Equip {3}"
)

TOPHS_BRACELET = make_artifact(
    name="Toph's Bracelet",
    mana_cost="{2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +1/+2 and has earthbend 2. Equip {2}"
)

SUNSTONE = make_artifact(
    name="Sunstone",
    mana_cost="{3}",
    text="{T}: Add {R}{R}. {3}, {T}: Firebending Lesson deals 3 damage to any target."
)

MOONSTONE = make_artifact(
    name="Moonstone",
    mana_cost="{3}",
    text="{T}: Add {U}{U}. {3}, {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)

def lotus_tile_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

LOTUS_TILE = make_artifact(
    name="Lotus Tile",
    mana_cost="{2}",
    text="When Lotus Tile enters, scry 2. {T}: Add one mana of any color. {2}, {T}, Sacrifice Lotus Tile: Draw a card.",
    setup_interceptors=lotus_tile_setup
)

DRILL = make_artifact(
    name="The Drill",
    mana_cost="{6}",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    text="Trample. Whenever The Drill deals combat damage to a player, destroy target land that player controls. Crew 4"
)


# =============================================================================
# ADDITIONAL INSTANTS AND SORCERIES
# =============================================================================

BLUE_SPIRIT_STRIKE = make_instant(
    name="Blue Spirit Strike",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature you control gets +2/+0 and gains deathtouch until end of turn. If that creature is an Ally, it also gains hexproof until end of turn."
)

SIEGE_OF_THE_NORTH = make_sorcery(
    name="Siege of the North",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy all creatures. Then firebend 3 for each creature destroyed this way."
)

CROSSROADS_OF_DESTINY = make_instant(
    name="Crossroads of Destiny",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Choose one — Exile target creature; or return target creature card from your graveyard to the battlefield."
)

FINAL_AGNI_KAI = make_sorcery(
    name="Final Agni Kai",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Two target creatures fight each other. Then if a creature died this way, firebend 3."
)

BLOODBENDING = make_instant(
    name="Bloodbending",
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Gain control of target creature until end of turn. Untap it. It gains haste. At end of turn, tap it. It doesn't untap during its controller's next untap step."
)

ECLIPSE_DARKNESS = make_instant(
    name="Eclipse Darkness",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Until end of turn, all creatures lose all abilities and become black."
)

AVATAR_STATE_FURY = make_instant(
    name="Avatar State Fury",
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    text="Target Avatar you control gains +5/+5 and gains flying, first strike, vigilance, trample, lifelink, and hexproof until end of turn. It can't be blocked this turn."
)

INVASION_DAY = make_sorcery(
    name="Invasion Day",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Ally creature tokens. Then put a +1/+1 counter on each Ally you control."
)

TUNNEL_THROUGH = make_instant(
    name="Tunnel Through",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Earthbend 2. Target creature you control can't be blocked this turn."
)

SPIRIT_BOMB = make_sorcery(
    name="Spirit Bomb",
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    text="Return X target nonland permanents to their owners' hands. If X is 5 or more, draw a card for each permanent returned this way."
)


# =============================================================================
# MORE WHITE CARDS
# =============================================================================

def jinora_spiritual_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lesson cast: scry 2, then draw."""
    def lesson_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_lesson_trigger(obj, lesson_effect)]

JINORA_SPIRITUAL_GUIDE = make_creature(
    name="Jinora, Spiritual Guide",
    power=2,
    toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast a Lesson spell, scry 2, then draw a card.",
    setup_interceptors=jinora_spiritual_guide_setup
)

def korra_avatar_unleashed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: modal choice of airbend, waterbend, or firebend 2."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice system handles selections
        return []
    return [make_attack_trigger(obj, attack_effect)]

KORRA_AVATAR_UNLEASHED = make_creature(
    name="Korra, Avatar Unleashed",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Whenever Korra attacks, choose any number: Airbend target creature; waterbend target creature; firebend 2.",
    setup_interceptors=korra_avatar_unleashed_setup
)

def airbending_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if returned a permanent this turn, draw."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if state.turn_data.get(f'{obj.controller}_returned_permanent', False):
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]

AIRBENDING_MASTER = make_creature(
    name="Airbending Master",
    power=2,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Flying. Airbend — At the beginning of your end step, if you returned a permanent to its owner's hand this turn, draw a card.",
    setup_interceptors=airbending_master_setup
)

def nomad_musician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 2 life per Ally."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        ally_count = 0
        for game_obj in state.objects.values():
            if (game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                'Ally' in game_obj.characteristics.subtypes and
                game_obj.zone == ZoneType.BATTLEFIELD):
                ally_count += 1
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2 * ally_count},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

NOMAD_MUSICIAN = make_creature(
    name="Nomad Musician",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Bard", "Ally"},
    text="When Nomad Musician enters, you gain 2 life for each Ally you control.",
    setup_interceptors=nomad_musician_setup
)

AIR_ACOLYTE = make_creature(
    name="Air Acolyte",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Lifelink. {2}{W}: Air Acolyte gains flying until end of turn."
)

RESTORATION_RITUAL = make_sorcery(
    name="Restoration Ritual",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Return up to two target permanent cards with mana value 3 or less from your graveyard to the battlefield."
)

def spiritual_guidance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack alone: +2/+2 and lifelink."""
    def attack_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.DECLARE_ATTACKERS:
            return False
        if event.payload.get('controller') != o.controller:
            return False
        attackers = event.payload.get('attackers', [])
        return len(attackers) == 1

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        attackers = event.payload.get('attackers', [])
        if attackers:
            attacker_id = attackers[0]
            return [
                Event(
                    type=EventType.GRANT_PT_MODIFIER,
                    payload={'object_id': attacker_id, 'power': 2, 'toughness': 2, 'duration': 'end_of_turn'},
                    source=obj.id
                ),
                Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': attacker_id, 'keyword': 'lifelink', 'duration': 'end_of_turn'},
                    source=obj.id
                )
            ]
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: attack_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=attack_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

SPIRITUAL_GUIDANCE = make_enchantment(
    name="Spiritual Guidance",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control attacks alone, it gets +2/+2 and gains lifelink until end of turn.",
    setup_interceptors=spiritual_guidance_setup
)


# =============================================================================
# MORE BLUE CARDS
# =============================================================================

def kanna_gran_gran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ally ETB: scry 1."""
    def ally_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_ally_etb_trigger(obj, ally_effect)]

KANNA_GRAN_GRAN = make_creature(
    name="Kanna, Gran Gran",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor", "Ally"},
    supertypes={"Legendary"},
    text="Whenever another Ally enters under your control, scry 1. {T}: Target Ally you control gains hexproof until end of turn.",
    setup_interceptors=kanna_gran_gran_setup
)

def ocean_depths_leviathan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: bounce up to 2 nonland permanents."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles bouncing
        return []
    return [make_etb_trigger(obj, etb_effect)]

OCEAN_DEPTHS_LEVIATHAN = make_creature(
    name="Ocean Depths Leviathan",
    power=8,
    toughness=8,
    mana_cost="{6}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Leviathan"},
    text="This spell costs {1} less to cast for each Island you control. Hexproof. When Ocean Depths Leviathan enters, return up to two target nonland permanents to their owners' hands.",
    setup_interceptors=ocean_depths_leviathan_setup
)

THOUGHT_MANIPULATION = make_instant(
    name="Thought Manipulation",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Its controller draws a card."
)

SPIRIT_VISION = make_sorcery(
    name="Spirit Vision",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Look at the top five cards of your library. Put two of them into your hand and the rest on the bottom of your library in any order."
)

WATER_WHIP = make_instant(
    name="Water Whip",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Waterbend target creature. (Tap it. It doesn't untap during its controller's next untap step.)"
)

CRASHING_WAVES = make_sorcery(
    name="Crashing Waves",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Return up to two target nonland permanents to their owners' hands. Draw a card."
)

ICE_SHIELD = make_instant(
    name="Ice Shield",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +0/+4 and gains hexproof until end of turn."
)


# =============================================================================
# MORE BLACK CARDS
# =============================================================================

def kuvira_great_uniter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 2 ETB. Attack: may sacrifice for +3/+3 and indestructible."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Sacrifice choice handled by choice system
        return []
    return [
        make_earthbend_etb(obj, 2),
        make_attack_trigger(obj, attack_effect)
    ]

KUVIRA_GREAT_UNITER = make_creature(
    name="Kuvira, Great Uniter",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Earthbend 2. Menace. Whenever Kuvira attacks, you may sacrifice another creature. If you do, Kuvira gets +3/+3 and gains indestructible until end of turn.",
    setup_interceptors=kuvira_great_uniter_setup
)

def shadow_operative_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: they discard."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.DISCARD,
                payload={'player': target, 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

SHADOW_OPERATIVE = make_creature(
    name="Shadow Operative",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Deathtouch. When Shadow Operative deals combat damage to a player, that player discards a card.",
    setup_interceptors=shadow_operative_setup
)

DARK_SPIRITS_BLESSING = make_enchantment(
    name="Dark Spirit's Blessing",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchanted creature gets +2/+1 and has deathtouch and 'When this creature dies, each opponent loses 2 life.'"
)

MIND_BREAK = make_sorcery(
    name="Mind Break",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. You lose life equal to that card's mana value."
)

def corrupt_official_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: opponent sacrifices least toughness creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles selection
        return []
    return [make_etb_trigger(obj, etb_effect)]

CORRUPT_OFFICIAL = make_creature(
    name="Corrupt Official",
    power=2,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    text="When Corrupt Official enters, target opponent sacrifices a creature with the least toughness among creatures they control.",
    setup_interceptors=corrupt_official_setup
)

DEATH_BY_LIGHTNING = make_instant(
    name="Death by Lightning",
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy target creature. Firebend 2."
)

PRISON_BREAK = make_sorcery(
    name="Prison Break",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. You gain 2 life for each card returned this way."
)


# =============================================================================
# MORE RED CARDS
# =============================================================================

def piandao_sword_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: may discard to draw 2."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Discard choice handled by choice system
        return []
    return [make_attack_trigger(obj, attack_effect)]

PIANDAO_SWORD_MASTER = make_creature(
    name="Piandao, Sword Master",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike. Whenever Piandao attacks, you may discard a card. If you do, draw two cards.",
    setup_interceptors=piandao_sword_master_setup
)

def fire_nation_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 1 ETB."""
    return [make_firebend_etb(obj, 1)]

FIRE_NATION_SOLDIER = make_creature(
    name="Fire Nation Soldier",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Firebend 1.",
    setup_interceptors=fire_nation_soldier_setup
)

RAGE_OF_FIRE = make_instant(
    name="Rage of Fire",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Rage of Fire deals X damage to any target. If X is 5 or more, firebend X."
)

LIGHTNING_BOLT_LESSON = make_instant(
    name="Lightning Bolt Lesson",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lesson — Lightning Bolt Lesson deals 3 damage to any target."
)

FIRE_WALL = make_enchantment(
    name="Fire Wall",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures can't attack you unless their controller pays {2} for each creature attacking you. Whenever an opponent attacks you, Fire Wall deals 1 damage to each attacking creature."
)

COMET_ENHANCED = make_instant(
    name="Comet Enhanced",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. That creature gains trample until end of turn if you control an Avatar."
)

CALDERA_ERUPTION = make_sorcery(
    name="Caldera Eruption",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Caldera Eruption deals 5 damage to each creature. Firebend 3."
)


# =============================================================================
# MORE GREEN CARDS
# =============================================================================

def due_the_earth_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 2 ETB. Counter on land: draw."""
    def counter_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        if event.payload.get('counter_type') != '+1/+1':
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return CardType.LAND in target.characteristics.types

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    counter_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: counter_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=counter_effect(e, s)
        ),
        duration='while_on_battlefield'
    )

    return [make_earthbend_etb(obj, 2), counter_trigger]

DUE_THE_EARTH_SPIRIT = make_creature(
    name="Due, the Earth Spirit",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Badger"},
    supertypes={"Legendary"},
    text="Hexproof. Earthbend 2. Whenever you put one or more +1/+1 counters on a land, draw a card.",
    setup_interceptors=due_the_earth_spirit_setup
)

def forest_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: search basic land to battlefield tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={'player': obj.controller, 'type': 'basic_land', 'to_zone': 'battlefield', 'tapped': True},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=5,
    toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Bear"},
    text="Trample. Reach. When Forest Guardian enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=forest_guardian_setup
)

OASIS_HERMIT = make_creature(
    name="Oasis Hermit",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="{T}: Add {G}. {T}: Target land you control becomes a 0/0 creature with haste that's still a land. Put a +1/+1 counter on it."
)

WILD_GROWTH = make_enchantment(
    name="Wild Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchant land. Whenever enchanted land is tapped for mana, its controller adds an additional {G}."
)

BEAST_SUMMONS = make_sorcery(
    name="Beast Summons",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create two 3/3 green Beast creature tokens with trample."
)

NATURE_RECLAMATION = make_instant(
    name="Nature Reclamation",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. You gain 3 life."
)

STANDING_TALL = make_instant(
    name="Standing Tall",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. If it has a +1/+1 counter on it, it also gains trample until end of turn."
)


# =============================================================================
# MORE MULTICOLOR CARDS
# =============================================================================

def mai_and_ty_lee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: they discard, you draw."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [
                Event(
                    type=EventType.DISCARD,
                    payload={'player': target, 'amount': 1},
                    source=obj.id
                ),
                Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id
                )
            ]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

MAI_AND_TY_LEE = make_creature(
    name="Mai and Ty Lee",
    power=3,
    toughness=3,
    mana_cost="{1}{R}{W}{B}",
    colors={Color.RED, Color.WHITE, Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, deathtouch. Whenever Mai and Ty Lee deals combat damage to a player, that player discards a card and you draw a card.",
    setup_interceptors=mai_and_ty_lee_setup
)

def amon_the_equalist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target loses abilities until your next turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles ability removal
        return []
    return [make_etb_trigger(obj, etb_effect)]

AMON_THE_EQUALIST = make_creature(
    name="Amon, the Equalist",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flash. When Amon enters, target creature loses all abilities until your next turn. {2}{U}{B}: Target creature loses all abilities until your next turn.",
    setup_interceptors=amon_the_equalist_setup
)

def unalaq_dark_avatar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: waterbend. Death: opponents lose 5."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles tap/freeze
        return []

    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -5},
                    source=obj.id
                ))
        return events

    return [
        make_upkeep_trigger(obj, upkeep_effect),
        make_death_trigger(obj, death_effect)
    ]

UNALAQ_DARK_AVATAR = make_creature(
    name="Unalaq, Dark Avatar",
    power=5,
    toughness=5,
    mana_cost="{3}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Flying. Waterbend — At the beginning of your upkeep, tap up to one target creature. It doesn't untap during its controller's next untap step. When Unalaq dies, each opponent loses 5 life.",
    setup_interceptors=unalaq_dark_avatar_setup
)

def spirit_of_raava_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Spirits +1/+1. End step: if gained life, create Spirit."""
    def spirit_filter(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Spirit' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if state.turn_data.get(f'{obj.controller}_gained_life', False):
            return [Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Spirit',
                    'power': 2,
                    'toughness': 2,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Spirit'},
                    'colors': {Color.WHITE},
                    'abilities': ['flying'],
                    'is_token': True
                },
                source=obj.id
            )]
        return []

    interceptors = make_static_pt_boost(obj, 1, 1, spirit_filter)
    interceptors.append(make_end_step_trigger(obj, end_step_effect))
    return interceptors

SPIRIT_OF_RAAVA = make_creature(
    name="Spirit of Raava",
    power=5,
    toughness=6,
    mana_cost="{4}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Other Spirits you control get +1/+1. At the beginning of your end step, if you gained life this turn, create a 2/2 white Spirit creature token with flying.",
    setup_interceptors=spirit_of_raava_setup
)

def spirit_of_vaatu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: deal 2 to each opponent, draw if opponent lost life."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        # Deal 2 to each opponent
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 2, 'source': obj.id},
                    source=obj.id
                ))
        # Check if any opponent lost life
        for player_id in state.players.keys():
            if player_id != obj.controller:
                if state.turn_data.get(f'{player_id}_lost_life', False):
                    events.append(Event(
                        type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id
                    ))
                    break
        return events
    return [make_end_step_trigger(obj, end_step_effect)]

SPIRIT_OF_VAATU = make_creature(
    name="Spirit of Vaatu",
    power=6,
    toughness=5,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying, menace. At the beginning of your end step, Spirit of Vaatu deals 2 damage to each opponent. If an opponent lost life this turn, draw a card.",
    setup_interceptors=spirit_of_vaatu_setup
)

def red_lotus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: they sacrifice a permanent."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.SACRIFICE,
                payload={'player': target, 'count': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

RED_LOTUS = make_creature(
    name="Red Lotus",
    power=3,
    toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Assassin"},
    text="Haste, menace. Whenever Red Lotus deals combat damage to a player, that player sacrifices a permanent.",
    setup_interceptors=red_lotus_setup
)

def white_lotus_grandmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Allies +1/+1 and vigilance. Upkeep: modal bending choice."""
    def ally_filter(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Ally' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice handled by choice system
        return []

    interceptors = make_static_pt_boost(obj, 1, 1, ally_filter)
    interceptors.append(make_keyword_grant(obj, ['vigilance'], ally_filter))
    interceptors.append(make_upkeep_trigger(obj, upkeep_effect))
    return interceptors

WHITE_LOTUS_GRANDMASTER = make_creature(
    name="White Lotus Grandmaster",
    power=3,
    toughness=4,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance, hexproof. Other Allies you control get +1/+1 and have vigilance. At the beginning of your upkeep, you may airbend, waterbend, earthbend 2, or firebend 2.",
    setup_interceptors=white_lotus_grandmaster_setup
)


# =============================================================================
# MORE ARTIFACTS
# =============================================================================

BOOMERANG_ARTIFACT = make_artifact(
    name="Sokka's Boomerang",
    mana_cost="{2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +1/+1. Whenever equipped creature deals combat damage to a player, return up to one target nonland permanent to its owner's hand. Equip {1}"
)

CACTUS_JUICE = make_artifact(
    name="Cactus Juice",
    mana_cost="{1}",
    text="{T}, Sacrifice Cactus Juice: Draw two cards, then discard a card at random. 'It's the quenchiest!'"
)

def firebending_scroll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: firebend 1."""
    return [make_firebend_etb(obj, 1)]

FIREBENDING_SCROLL = make_artifact(
    name="Firebending Scroll",
    mana_cost="{2}",
    text="When Firebending Scroll enters, firebend 1. {2}, {T}, Sacrifice Firebending Scroll: Firebend 2 and draw a card.",
    setup_interceptors=firebending_scroll_setup
)

def earthbending_scroll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: earthbend 1."""
    return [make_earthbend_etb(obj, 1)]

EARTHBENDING_SCROLL = make_artifact(
    name="Earthbending Scroll",
    mana_cost="{2}",
    text="When Earthbending Scroll enters, earthbend 1. {2}, {T}, Sacrifice Earthbending Scroll: Earthbend 2 and draw a card.",
    setup_interceptors=earthbending_scroll_setup
)

def waterbending_scroll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: waterbend target creature."""
    return [make_waterbend_etb(obj, 0, 0)]

WATERBENDING_SCROLL = make_artifact(
    name="Waterbending Scroll",
    mana_cost="{2}",
    text="When Waterbending Scroll enters, waterbend target creature. {2}, {T}, Sacrifice Waterbending Scroll: Waterbend up to two target creatures. Draw a card.",
    setup_interceptors=waterbending_scroll_setup
)

def airbending_scroll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: airbend target creature."""
    return [make_airbend_etb(obj, 1)]

AIRBENDING_SCROLL = make_artifact(
    name="Airbending Scroll",
    mana_cost="{2}",
    text="When Airbending Scroll enters, airbend target creature. {2}, {T}, Sacrifice Airbending Scroll: Airbend up to two target creatures. Draw a card.",
    setup_interceptors=airbending_scroll_setup
)

SUBMARINE = make_artifact(
    name="Fire Nation Submarine",
    mana_cost="{5}",
    subtypes={"Vehicle"},
    text="Islandwalk. Firebend 2 — Whenever this Vehicle deals combat damage to a player, draw a card. Crew 3"
)

CHI_BLOCKER_GLOVES = make_artifact(
    name="Chi Blocker Gloves",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+0 and has 'Whenever this creature deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step and loses all abilities until your next turn.' Equip {2}"
)


# =============================================================================
# MORE LANDS
# =============================================================================

SOUTHERN_AIR_TEMPLE = make_land(
    name="Southern Air Temple",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {W}. Activate only if you control a creature with flying."
)

WESTERN_AIR_TEMPLE = make_land(
    name="Western Air Temple",
    text="Western Air Temple enters tapped. {T}: Add {W} or {U}. {2}, {T}: Target creature gains flying until end of turn."
)

KYOSHI_ISLAND = make_land(
    name="Kyoshi Island",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {G} or {W}. Activate only if you control a Warrior."
)

BOILING_ROCK_PRISON = make_land(
    name="Boiling Rock Prison",
    text="Boiling Rock Prison enters tapped. {T}: Add {B} or {R}. {3}, {T}: Target creature can't attack or block this turn."
)

SERPENTS_PASS = make_land(
    name="Serpent's Pass",
    text="Serpent's Pass enters tapped. {T}: Add {U} or {G}. {4}, {T}: Create a 4/3 blue Serpent creature token."
)

FOGGY_SWAMP = make_land(
    name="Foggy Swamp",
    text="Foggy Swamp enters tapped. {T}: Add {U} or {G}. {2}, {T}: Create a 2/2 green Plant creature token."
)

SI_WONG_DESERT = make_land(
    name="Si Wong Desert",
    text="{T}: Add {C}. {2}, {T}: Add two mana of any one color. You lose 1 life."
)

NORTHERN_WATER_TRIBE_CAPITAL = make_land(
    name="Northern Water Tribe Capital",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {U}{U}. Activate only if you control two or more creatures with waterbend."
)


# =============================================================================
# LEGEND OF KORRA ERA CARDS
# =============================================================================

REPUBLIC_CITY = make_land(
    name="Republic City",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add one mana of any color. Activate only if you control creatures of three or more different colors."
)

PRO_BENDING_ARENA = make_land(
    name="Pro-Bending Arena",
    text="Pro-Bending Arena enters tapped. {T}: Add {R}, {U}, or {G}. {3}, {T}: Target creature you control fights target creature an opponent controls."
)

def mako_firebender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 2. Combat damage: may pay R to deal 2."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            # Cost and targeting handled by choice system
            return []
        return []
    return [
        make_firebend_etb(obj, 2),
        make_damage_trigger(obj, damage_effect, combat_only=True)
    ]

MAKO_FIREBENDER = make_creature(
    name="Mako, Firebender",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 2. Whenever Mako deals combat damage to a player, you may pay {R}. If you do, Mako deals 2 damage to any target.",
    setup_interceptors=mako_firebender_setup
)

def bolin_lavabender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 2 ETB + 3 damage. Attack: earthbend 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        # Earthbend 2
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Wall',
                    'power': 0,
                    'toughness': 3,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Wall'},
                    'abilities': ['defender'],
                    'is_token': True
                },
                source=obj.id
            ))
        # 3 damage to target creature - targeting system handles
        return events

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Wall',
                'power': 0,
                'toughness': 3,
                'types': {CardType.CREATURE},
                'subtypes': {'Wall'},
                'abilities': ['defender'],
                'is_token': True
            },
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]

BOLIN_LAVABENDER = make_creature(
    name="Bolin, Lavabender",
    power=3,
    toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Earthbend 2. When Bolin enters, he deals 3 damage to target creature you don't control. Whenever Bolin attacks, earthbend 1.",
    setup_interceptors=bolin_lavabender_setup
)

def asami_sato_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Static: artifacts get tap for colorless mana ability."""
    # The mana ability is an activated ability, not a triggered one.
    # Static effects for granting abilities would need a different approach.
    return []

ASAMI_SATO = make_creature(
    name="Asami Sato",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Artificer", "Ally"},
    supertypes={"Legendary"},
    text="Artifacts you control have '{T}: Add {C}.' {2}, {T}: Create a Clue token.",
    setup_interceptors=asami_sato_setup
)

def lin_beifong_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Earthbend 3. Attack: target can't block."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles can't block
        return []
    return [
        make_earthbend_etb(obj, 3),
        make_attack_trigger(obj, attack_effect)
    ]

LIN_BEIFONG = make_creature(
    name="Lin Beifong",
    power=4,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Soldier", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance. Earthbend 3. Whenever Lin attacks, target creature an opponent controls can't block this turn.",
    setup_interceptors=lin_beifong_setup
)

def tenzin_airbending_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Airbend on attack. Lesson: create flying Ally."""
    def lesson_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Ally',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Ally'},
                'colors': {Color.WHITE},
                'abilities': ['flying'],
                'is_token': True
            },
            source=obj.id
        )]
    return [
        make_airbend_attack(obj),
        make_lesson_trigger(obj, lesson_effect)
    ]

TENZIN_AIRBENDING_MASTER = make_creature(
    name="Tenzin, Airbending Master",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Tenzin attacks, airbend up to one target creature. Whenever you cast a Lesson spell, create a 1/1 white Ally creature token with flying.",
    setup_interceptors=tenzin_airbending_master_setup
)

def zaheer_red_lotus_leader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: they sacrifice a permanent."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.SACRIFICE,
                payload={'player': target, 'count': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

ZAHEER_RED_LOTUS_LEADER = make_creature(
    name="Zaheer, Red Lotus Leader",
    power=4,
    toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Zaheer deals combat damage to a player, that player sacrifices a permanent.",
    setup_interceptors=zaheer_red_lotus_leader_setup
)

def pli_combustion_bender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firebend 3 ETB."""
    return [make_firebend_etb(obj, 3)]

PLI_COMBUSTION_BENDER = make_creature(
    name="P'Li, Combustion Bender",
    power=3,
    toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Reach. Firebend 3. {T}: P'Li deals 3 damage to target creature or planeswalker.",
    setup_interceptors=pli_combustion_bender_setup
)

def ghazan_lavabender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: destroy land + earthbend 2. Trample with 4+ lands."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        # Earthbend 2
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Wall',
                    'power': 0,
                    'toughness': 3,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Wall'},
                    'abilities': ['defender'],
                    'is_token': True
                },
                source=obj.id
            ))
        # Destroy land handled by targeting
        return events

    def land_count_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        land_count = 0
        for game_obj in state.objects.values():
            if (game_obj.controller == obj.controller and
                CardType.LAND in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD):
                land_count += 1
        return land_count >= 4

    interceptors = [make_etb_trigger(obj, etb_effect)]
    interceptors.append(make_keyword_grant(obj, ['trample'], land_count_filter))
    return interceptors

GHAZAN_LAVABENDER = make_creature(
    name="Ghazan, Lavabender",
    power=4,
    toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Ghazan enters, destroy target land. Earthbend 2. Ghazan has trample as long as you control four or more lands.",
    setup_interceptors=ghazan_lavabender_setup
)

def ming_hua_waterbender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """No triggered abilities - activated ability only."""
    return []

MING_HUA_WATERBENDER = make_creature(
    name="Ming-Hua, Armless Waterbender",
    power=3,
    toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flash. Double strike. Waterbend — {U}: Ming-Hua gets +1/+0 until end of turn.",
    setup_interceptors=ming_hua_waterbender_setup
)

def naga_polar_bear_dog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: target Ally gets +2/+2."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles which Ally
        return []
    return [make_attack_trigger(obj, attack_effect)]

NAGA_POLAR_BEAR_DOG = make_creature(
    name="Naga, Polar Bear Dog",
    power=4,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Dog", "Bear", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance. Whenever Naga attacks, target Ally you control gets +2/+2 until end of turn.",
    setup_interceptors=naga_polar_bear_dog_setup
)

def pabu_fire_ferret_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ally ETB: Pabu gets +1/+1 until end of turn."""
    def ally_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_PT_MODIFIER,
            payload={'object_id': obj.id, 'power': 1, 'toughness': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_ally_etb_trigger(obj, ally_effect)]

PABU_FIRE_FERRET = make_creature(
    name="Pabu the Fire Ferret",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Ferret", "Ally"},
    supertypes={"Legendary"},
    text="Haste. Whenever another Ally enters under your control, Pabu gets +1/+1 until end of turn.",
    setup_interceptors=pabu_fire_ferret_setup
)

def varrick_industrialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact ETB: create Treasure."""
    def artifact_etb_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        if entered_obj.controller != o.controller:
            return False
        return CardType.ARTIFACT in entered_obj.characteristics.types

    def artifact_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Treasure'},
                'is_token': True
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: artifact_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=artifact_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

VARRICK_INDUSTRIALIST = make_creature(
    name="Varrick, Industrialist",
    power=2,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    supertypes={"Legendary"},
    text="Whenever an artifact enters under your control, create a Treasure token. {T}: Create a 0/1 colorless Construct artifact creature token.",
    setup_interceptors=varrick_industrialist_setup
)

def zhu_li_assistant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap trigger: loot."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_tap_trigger(obj, tap_effect)]

ZHU_LI_ASSISTANT = make_creature(
    name="Zhu Li, Personal Assistant",
    power=1,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="Whenever Zhu Li becomes tapped, draw a card, then discard a card. Partner with Varrick, Industrialist.",
    setup_interceptors=zhu_li_assistant_setup
)

def tarrlok_bloodbender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """No triggered abilities - activated ability only."""
    return []

TARRLOK_BLOODBENDER = make_creature(
    name="Tarrlok, Bloodbender",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard", "Noble"},
    supertypes={"Legendary"},
    text="Waterbend — {2}{U}{B}, {T}: Gain control of target creature until end of turn. Untap it. It gains haste.",
    setup_interceptors=tarrlok_bloodbender_setup
)

def noatak_amon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: remove abilities. Combat damage: remove abilities."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting system handles ability removal
        return []

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            # Choice system handles creature selection
            return []
        return []

    return [
        make_etb_trigger(obj, etb_effect),
        make_damage_trigger(obj, damage_effect, combat_only=True)
    ]

NOATAK_AMON = make_creature(
    name="Noatak (Amon)",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flash. When Noatak enters, target creature loses all abilities permanently. Whenever Noatak deals combat damage to a player, choose a creature that player controls. It loses all abilities permanently.",
    setup_interceptors=noatak_amon_setup
)

def equalist_chi_blocker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to creature: tap, freeze, remove abilities."""
    def damage_filter(event: Event, state: GameState, o: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != o.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target = event.payload.get('target')
        target_obj = state.objects.get(target)
        return target_obj and CardType.CREATURE in target_obj.characteristics.types

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        return [
            Event(
                type=EventType.TAP,
                payload={'object_id': target},
                source=obj.id
            ),
            Event(
                type=EventType.FREEZE,
                payload={'object_id': target},
                source=obj.id
            ),
            Event(
                type=EventType.REMOVE_ABILITIES,
                payload={'object_id': target, 'duration': 'until_your_next_turn'},
                source=obj.id
            )
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=damage_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

EQUALIST_CHI_BLOCKER = make_creature(
    name="Equalist Chi Blocker",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Equalist Chi Blocker deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step and loses all abilities until your next turn.",
    setup_interceptors=equalist_chi_blocker_setup
)

def mecha_tank_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: create Treasure."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Treasure',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                    'is_token': True
                },
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

MECHA_TANK = make_artifact(
    name="Mecha Tank",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    text="Trample. When Mecha Tank deals combat damage to a player, create a Treasure token. Crew 2",
    setup_interceptors=mecha_tank_setup
)

def spirit_wilds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: create 2/2 Spirit with flying."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Spirit',
                'power': 2,
                'toughness': 2,
                'types': {CardType.CREATURE},
                'subtypes': {'Spirit'},
                'colors': {Color.GREEN, Color.BLUE},
                'abilities': ['flying'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]

SPIRIT_WILDS = make_enchantment(
    name="Spirit Wilds",
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="At the beginning of your upkeep, create a 2/2 green and blue Spirit creature token with flying.",
    setup_interceptors=spirit_wilds_setup
)

HARMONIC_CONVERGENCE = make_sorcery(
    name="Harmonic Convergence",
    mana_cost="{3}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    text="Return all creatures from all graveyards to the battlefield under their owners' control. Each player draws cards equal to the number of creatures they control."
)

AIR_NATION_RESTORED = make_sorcery(
    name="Air Nation Restored",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Ally creature tokens with flying. You gain 3 life for each creature you control with flying."
)

PRO_BENDING_MATCH = make_instant(
    name="Pro-Bending Match",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Three target creatures you control each deal damage equal to their power to up to three different target creatures you don't control."
)

PLATINUM_MECH_SUIT = make_artifact(
    name="Platinum Mech Suit",
    mana_cost="{6}",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    text="Trample, hexproof. Whenever Platinum Mech Suit deals combat damage to a player, destroy target land that player controls. Crew 4"
)

SPIRIT_CANNON = make_artifact(
    name="Spirit Cannon",
    mana_cost="{6}",
    supertypes={"Legendary"},
    text="{T}: Spirit Cannon deals 5 damage to any target. If a permanent is destroyed this way, its controller loses 5 life."
)

AIRBENDERS_FLIGHT = make_instant(
    name="Airbender's Flight",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains flying and hexproof until end of turn. Scry 1."
)

LAVABENDING = make_sorcery(
    name="Lavabending",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Destroy target land. Earthbend 3."
)

METALBENDING_CABLE = make_artifact(
    name="Metalbending Cable",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1 and has reach. Whenever equipped creature attacks, tap target creature an opponent controls. Equip {2}"
)

SPIRIT_PORTAL = make_land(
    name="Spirit Portal",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {5}, {T}: Create a 3/3 blue Spirit creature token with flying and hexproof."
)

def korra_and_asami_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: choose 2 modes (modal ability)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice system handles the 2 selections
        return []
    return [make_attack_trigger(obj, attack_effect)]

KORRA_AND_ASAMI = make_creature(
    name="Korra and Asami",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Whenever Korra and Asami attacks, choose two: Airbend target creature; waterbend target creature; create a Treasure token; target Ally gets +2/+2 until end of turn.",
    setup_interceptors=korra_and_asami_setup
)


# =============================================================================
# BASIC LANDS
# =============================================================================

PLAINS_TLA = make_land(
    name="Plains",
    subtypes={"Plains"},
    supertypes={"Basic"},
    text="({T}: Add {W}.)"
)

ISLAND_TLA = make_land(
    name="Island",
    subtypes={"Island"},
    supertypes={"Basic"},
    text="({T}: Add {U}.)"
)

SWAMP_TLA = make_land(
    name="Swamp",
    subtypes={"Swamp"},
    supertypes={"Basic"},
    text="({T}: Add {B}.)"
)

MOUNTAIN_TLA = make_land(
    name="Mountain",
    subtypes={"Mountain"},
    supertypes={"Basic"},
    text="({T}: Add {R}.)"
)

FOREST_TLA = make_land(
    name="Forest",
    subtypes={"Forest"},
    supertypes={"Basic"},
    text="({T}: Add {G}.)"
)


# =============================================================================
# REGISTRY
# =============================================================================

AVATAR_TLA_CUSTOM_CARDS = {
    # WHITE
    "Aang's Iceberg": AANGS_ICEBERG,
    "Aang, the Last Airbender": AANG_THE_LAST_AIRBENDER,
    "Airbender Ascension": AIRBENDER_ASCENSION,
    "Airbender's Reversal": AIRBENDERS_REVERSAL,
    "Airbending Lesson": AIRBENDING_LESSON,
    "Appa, Loyal Sky Bison": APPA_LOYAL_SKY_BISON,
    "Appa, Steadfast Guardian": APPA_STEADFAST_GUARDIAN,
    "Avatar Enthusiasts": AVATAR_ENTHUSIASTS,
    "Avatar's Wrath": AVATARS_WRATH,
    "Compassionate Healer": COMPASSIONATE_HEALER,
    "Curious Farm Animals": CURIOUS_FARM_ANIMALS,
    "Destined Confrontation": DESTINED_CONFRONTATION,
    "Earth Kingdom Jailer": EARTH_KINGDOM_JAILER,
    "Earth Kingdom Protectors": EARTH_KINGDOM_PROTECTORS,
    "Enter the Avatar State": ENTER_THE_AVATAR_STATE,
    "Fancy Footwork": FANCY_FOOTWORK,
    "Gather the White Lotus": GATHER_THE_WHITE_LOTUS,
    "Glider Kids": GLIDER_KIDS,
    "Glider Staff": GLIDER_STAFF,
    "Hakoda, Selfless Commander": HAKODA_SELFLESS_COMMANDER,
    "Invasion Reinforcements": INVASION_REINFORCEMENTS,
    "Jeong Jeong's Deserters": JEONG_JEONGS_DESERTERS,
    "Katara, Waterbending Master": KATARA_WATERBENDING_MASTER,
    "Sokka, Swordsman": SOKKA_SWORDSMAN,
    "Suki, Kyoshi Warrior": SUKI_KYOSHI_WARRIOR,
    "Uncle Iroh, Tea Master": UNCLE_IROH_TEA_MASTER,
    "White Lotus Member": WHITE_LOTUS_MEMBER,
    "Kyoshi Island Defender": KYOSHI_ISLAND_DEFENDER,
    "Meelo, the Troublemaker": MEELO_THE_TROUBLEMAKER,
    "Momo, Loyal Companion": MOMO_LOYAL_COMPANION,
    "Airbender Initiate": AIRBENDER_INITIATE,
    "Cabbage Merchant": CABBAGE_MERCHANT,
    "Monastic Discipline": MONASTIC_DISCIPLINE,
    "Winds of Change": WINDS_OF_CHANGE,
    "Avatar Korra, Spirit Bridge": AVATAR_KORRA_SPIRIT,
    "Peaceful Sanctuary": PEACEFUL_SANCTUARY,
    "Guru Pathik": GURU_PATHIK,
    "Lion Turtle Blessing": LION_TURTLE_BLESSING,
    "Gyatso, Wise Mentor": GYATSO_WISE_MENTOR,
    "Jinora, Spiritual Guide": JINORA_SPIRITUAL_GUIDE,
    "Korra, Avatar Unleashed": KORRA_AVATAR_UNLEASHED,
    "Airbending Master": AIRBENDING_MASTER,
    "Nomad Musician": NOMAD_MUSICIAN,
    "Air Acolyte": AIR_ACOLYTE,
    "Restoration Ritual": RESTORATION_RITUAL,
    "Spiritual Guidance": SPIRITUAL_GUIDANCE,

    # BLUE
    "Aang, Swift Savior": AANG_SWIFT_SAVIOR,
    "Abandon Attachments": ABANDON_ATTACHMENTS,
    "Accumulate Wisdom": ACCUMULATE_WISDOM,
    "Benevolent River Spirit": BENEVOLENT_RIVER_SPIRIT,
    "Boomerang Basics": BOOMERANG_BASICS,
    "Knowledge Seeker": KNOWLEDGE_SEEKER,
    "Library Guardian": LIBRARY_GUARDIAN,
    "Master Pakku": MASTER_PAKKU,
    "Moon Spirit Blessing": MOON_SPIRIT_BLESSING,
    "Northern Water Tribe": NORTHERN_WATER_TRIBE,
    "Ocean Spirit Fury": OCEAN_SPIRIT_FURY,
    "Princess Yue": PRINCESS_YUE,
    "Spirit Library": SPIRIT_LIBRARY,
    "Waterbending Lesson": WATERBENDING_LESSON,
    "Wan Shi Tong": WAN_SHI_TONG,
    "Hama, Bloodbender": HAMA_BLOODBENDER,
    "Serpent's Pass Horror": SERPENTS_PASS_HORROR,
    "Southern Water Tribe": SOUTHERN_WATER_TRIBE,
    "Foggy Swamp Waterbender": FOGGY_SWAMP_WATERBENDER,
    "Spirit Fox": SPIRIT_FOX,
    "Unagi Attack": UNAGI_ATTACK,
    "Wisdom of Ages": WISDOM_OF_AGES,
    "Avatar Roku": AVATAR_ROKU,
    "Spirit World Wanderer": SPIRIT_WORLD_WANDERER,
    "Water Tribe Healer": WATER_TRIBE_HEALER,
    "Tui and La": TUI_AND_LA,
    "Mist Veil": MIST_VEIL,
    "Kanna, Gran Gran": KANNA_GRAN_GRAN,
    "Ocean Depths Leviathan": OCEAN_DEPTHS_LEVIATHAN,
    "Thought Manipulation": THOUGHT_MANIPULATION,
    "Spirit Vision": SPIRIT_VISION,
    "Water Whip": WATER_WHIP,
    "Crashing Waves": CRASHING_WAVES,
    "Ice Shield": ICE_SHIELD,

    # BLACK
    "Azula Always Lies": AZULA_ALWAYS_LIES,
    "Azula, Cunning Usurper": AZULA_CUNNING_USURPER,
    "Azula, On the Hunt": AZULA_ON_THE_HUNT,
    "Beetle-Headed Merchants": BEETLE_HEADED_MERCHANTS,
    "Boiling Rock Rioter": BOILING_ROCK_RIOTER,
    "Buzzard-Wasp Colony": BUZZARD_WASP_COLONY,
    "Canyon Crawler": CANYON_CRAWLER,
    "Corrupt Court Official": CORRUPT_COURT_OFFICIAL,
    "Cruel Administrator": CRUEL_ADMINISTRATOR,
    "Dai Li Indoctrination": DAI_LI_INDOCTRINATION,
    "Day of Black Sun": DAY_OF_BLACK_SUN,
    "Deadly Precision": DEADLY_PRECISION,
    "Epic Downfall": EPIC_DOWNFALL,
    "Fatal Fissure": FATAL_FISSURE,
    "Fire Lord Ozai": FIRE_LORD_OZAI,
    "Long Feng": LONG_FENG,
    "Mai, Knives Expert": MAI_KNIVES_EXPERT,
    "Zhao, the Conqueror": ZHAO_THE_CONQUEROR,
    "Dai Li Enforcer": DAI_LI_ENFORCER,
    "Spirit Corruption": SPIRIT_CORRUPTION,
    "Bloodbending Lesson": BLOODBENDING_LESSON,
    "Shadow of the Past": SHADOW_OF_THE_PAST,
    "Fire Nation Prison": FIRE_NATION_PRISON,
    "Cruel Ambition": CRUEL_AMBITION,
    "Spirit of Revenge": SPIRIT_OF_REVENGE,
    "War Balloon Crew": WAR_BALLOON_CREW,
    "Lake Laogai": LAKE_LAOGAI,
    "Kuvira, Great Uniter": KUVIRA_GREAT_UNITER,
    "Shadow Operative": SHADOW_OPERATIVE,
    "Dark Spirit's Blessing": DARK_SPIRITS_BLESSING,
    "Mind Break": MIND_BREAK,
    "Corrupt Official": CORRUPT_OFFICIAL,
    "Death by Lightning": DEATH_BY_LIGHTNING,
    "Prison Break": PRISON_BREAK,

    # RED
    "Boar-q-pine": BOAR_Q_PINE,
    "Bumi Bash": BUMI_BASH,
    "Combustion Man": COMBUSTION_MAN,
    "Combustion Technique": COMBUSTION_TECHNIQUE,
    "Fated Firepower": FATED_FIREPOWER,
    "Firebending Lesson": FIREBENDING_LESSON,
    "Firebending Student": FIREBENDING_STUDENT,
    "Fire Nation Attacks": FIRE_NATION_ATTACKS,
    "Fire Nation Cadets": FIRE_NATION_CADETS,
    "Fire Nation Warship": FIRE_NATION_WARSHIP,
    "Jeong Jeong, the Deserter": JEONG_JEONG_THE_DESERTER,
    "Prince Zuko": PRINCE_ZUKO,
    "Zuko, Redeemed": ZUKO_REDEEMED,
    "Fire Nation Commander": FIRE_NATION_COMMANDER,
    "Iroh, Dragon of the West": IROH_DRAGON_OF_THE_WEST,
    "Lightning Redirection": LIGHTNING_REDIRECTION,
    "Sozin's Comet": SOZINS_COMET,
    "Agni Kai": AGNI_KAI,
    "Dragon Dance": DRAGON_DANCE,
    "Ran and Shaw": RAN_AND_SHAW,
    "Fire Lily": FIRE_LILY,
    "Volcanic Eruption": VOLCANIC_ERUPTION,
    "Phoenix Reborn": PHOENIX_REBORN,
    "Piandao, Sword Master": PIANDAO_SWORD_MASTER,
    "Fire Nation Soldier": FIRE_NATION_SOLDIER,
    "Rage of Fire": RAGE_OF_FIRE,
    "Lightning Bolt Lesson": LIGHTNING_BOLT_LESSON,
    "Fire Wall": FIRE_WALL,
    "Comet Enhanced": COMET_ENHANCED,
    "Caldera Eruption": CALDERA_ERUPTION,

    # GREEN
    "Allies at Last": ALLIES_AT_LAST,
    "Avatar Destiny": AVATAR_DESTINY,
    "Badgermole": BADGERMOLE,
    "Badgermole Cub": BADGERMOLE_CUB,
    "Bumi, King of Three Trials": BUMI_KING_OF_THREE_TRIALS,
    "Cycle of Renewal": CYCLE_OF_RENEWAL,
    "Earthbender Ascension": EARTHBENDER_ASCENSION,
    "Earthbending Lesson": EARTHBENDING_LESSON,
    "Earth Kingdom General": EARTH_KINGDOM_GENERAL,
    "Earth Rumble": EARTH_RUMBLE,
    "Toph Beifong": TOPH_BEIFONG,
    "Toph, Metalbender": TOPH_METALBENDER,
    "Swampbender": SWAMPBENDER,
    "Flying Bison Herd": FLYING_BISON_HERD,
    "Avatar Kyoshi": AVATAR_KYOSHI,
    "Forest Spirit": FOREST_SPIRIT,
    "Catgator": CATGATOR,
    "Swamp Giant": SWAMP_GIANT,
    "Earth Kingdom Farmer": EARTH_KINGDOM_FARMER,
    "Natural Harmony": NATURAL_HARMONY,
    "Primal Fury": PRIMAL_FURY,
    "Platypus Bear": PLATYPUS_BEAR,
    "Spirit Vine": SPIRIT_VINE,
    "Due, the Earth Spirit": DUE_THE_EARTH_SPIRIT,
    "Forest Guardian": FOREST_GUARDIAN,
    "Oasis Hermit": OASIS_HERMIT,
    "Wild Growth": WILD_GROWTH,
    "Beast Summons": BEAST_SUMMONS,
    "Nature Reclamation": NATURE_RECLAMATION,
    "Standing Tall": STANDING_TALL,

    # MULTICOLOR
    "Aang and La, Ocean's Fury": AANG_AND_LA,
    "Beifong's Bounty Hunters": BEIFONGS_BOUNTY_HUNTERS,
    "Bitter Work": BITTER_WORK,
    "Bumi, Unleashed": BUMI_UNLEASHED,
    "Dai Li Agents": DAI_LI_AGENTS,
    "Fire Lord Azula": FIRE_LORD_AZULA,
    "Fire Lord Zuko": FIRE_LORD_ZUKO,
    "Team Avatar": TEAM_AVATAR,
    "Ty Lee, Acrobat": TY_LEE_ACROBAT,
    "Sokka and Suki": SOKKA_AND_SUKI,
    "Zuko and Iroh": ZUKO_AND_IROH,
    "Katara and Aang": KATARA_AND_AANG,
    "Azula and Dai Li": AZULA_AND_DAI_LI,
    "Spirit World Portal": SPIRIT_WORLD_PORTAL,
    "Firelord Sozin": FIRELORD_SOZIN,
    "Avatar Yangchen": AVATAR_YANGCHEN,
    "Avatar Kuruk": AVATAR_KURUK,
    "Lion Turtle": LION_TURTLE,
    "Koizilla": KOIZILLA,
    "Hei Bai, Forest Spirit": HEIBAIFACED_SPIRIT,
    "Mai and Ty Lee": MAI_AND_TY_LEE,
    "Amon, the Equalist": AMON_THE_EQUALIST,
    "Unalaq, Dark Avatar": UNALAQ_DARK_AVATAR,
    "Spirit of Raava": SPIRIT_OF_RAAVA,
    "Spirit of Vaatu": SPIRIT_OF_VAATU,
    "Red Lotus": RED_LOTUS,
    "White Lotus Grandmaster": WHITE_LOTUS_GRANDMASTER,

    # ARTIFACTS
    "Aang Statue": AANG_STATUE,
    "Earth Kingdom Tank": EARTH_KINGDOM_TANK,
    "Meteorite Sword": METEORITE_SWORD,
    "Spirit Oasis": SPIRIT_OASIS,
    "War Balloon": WAR_BALLOON,
    "Azula's Crown": AZULAS_CROWN,
    "Water Pouch": WATER_POUCH,
    "Fire Nation Helm": FIRE_NATION_HELM,
    "Aang's Staff": AANGS_STAFF,
    "Toph's Bracelet": TOPHS_BRACELET,
    "Sunstone": SUNSTONE,
    "Moonstone": MOONSTONE,
    "Lotus Tile": LOTUS_TILE,
    "The Drill": DRILL,
    "Sokka's Boomerang": BOOMERANG_ARTIFACT,
    "Cactus Juice": CACTUS_JUICE,
    "Firebending Scroll": FIREBENDING_SCROLL,
    "Earthbending Scroll": EARTHBENDING_SCROLL,
    "Waterbending Scroll": WATERBENDING_SCROLL,
    "Airbending Scroll": AIRBENDING_SCROLL,
    "Fire Nation Submarine": SUBMARINE,
    "Chi Blocker Gloves": CHI_BLOCKER_GLOVES,

    # LANDS
    "Air Temple": AIR_TEMPLE,
    "Ba Sing Se": BA_SING_SE,
    "Fire Nation Capital": FIRE_NATION_CAPITAL,
    "Spirit World Gate": SPIRIT_WORLD_GATE,
    "Water Tribe Village": WATER_TRIBE_VILLAGE,
    "Fire Nation Outpost": FIRE_NATION_OUTPOST,
    "Earth Kingdom Fortress": EARTH_KINGDOM_FORTRESS,
    "Omashu": OMASHU,
    "Ember Island": EMBER_ISLAND,
    "Fog of Lost Souls": FOG_OF_LOST_SOULS,
    "Southern Air Temple": SOUTHERN_AIR_TEMPLE,
    "Western Air Temple": WESTERN_AIR_TEMPLE,
    "Kyoshi Island": KYOSHI_ISLAND,
    "Boiling Rock Prison": BOILING_ROCK_PRISON,
    "Serpent's Pass": SERPENTS_PASS,
    "Foggy Swamp": FOGGY_SWAMP,
    "Si Wong Desert": SI_WONG_DESERT,
    "Northern Water Tribe Capital": NORTHERN_WATER_TRIBE_CAPITAL,

    # FINAL BATCH
    "Republic City": REPUBLIC_CITY,
    "Pro-Bending Arena": PRO_BENDING_ARENA,
    "Mako, Firebender": MAKO_FIREBENDER,
    "Bolin, Lavabender": BOLIN_LAVABENDER,
    "Asami Sato": ASAMI_SATO,
    "Lin Beifong": LIN_BEIFONG,
    "Tenzin, Airbending Master": TENZIN_AIRBENDING_MASTER,
    "Zaheer, Red Lotus Leader": ZAHEER_RED_LOTUS_LEADER,
    "P'Li, Combustion Bender": PLI_COMBUSTION_BENDER,
    "Ghazan, Lavabender": GHAZAN_LAVABENDER,
    "Ming-Hua, Armless Waterbender": MING_HUA_WATERBENDER,
    "Naga, Polar Bear Dog": NAGA_POLAR_BEAR_DOG,
    "Pabu the Fire Ferret": PABU_FIRE_FERRET,
    "Varrick, Industrialist": VARRICK_INDUSTRIALIST,
    "Zhu Li, Personal Assistant": ZHU_LI_ASSISTANT,
    "Tarrlok, Bloodbender": TARRLOK_BLOODBENDER,
    "Noatak (Amon)": NOATAK_AMON,
    "Equalist Chi Blocker": EQUALIST_CHI_BLOCKER,
    "Mecha Tank": MECHA_TANK,
    "Spirit Wilds": SPIRIT_WILDS,
    "Harmonic Convergence": HARMONIC_CONVERGENCE,
    "Air Nation Restored": AIR_NATION_RESTORED,
    "Pro-Bending Match": PRO_BENDING_MATCH,
    "Platinum Mech Suit": PLATINUM_MECH_SUIT,
    "Spirit Cannon": SPIRIT_CANNON,
    "Airbender's Flight": AIRBENDERS_FLIGHT,
    "Lavabending": LAVABENDING,
    "Metalbending Cable": METALBENDING_CABLE,
    "Spirit Portal": SPIRIT_PORTAL,
    "Korra and Asami": KORRA_AND_ASAMI,

    # BASIC LANDS
    "Plains": PLAINS_TLA,
    "Island": ISLAND_TLA,
    "Swamp": SWAMP_TLA,
    "Mountain": MOUNTAIN_TLA,
    "Forest": FOREST_TLA,

    # INSTANTS & SORCERIES
    "Blue Spirit Strike": BLUE_SPIRIT_STRIKE,
    "Siege of the North": SIEGE_OF_THE_NORTH,
    "Crossroads of Destiny": CROSSROADS_OF_DESTINY,
    "Final Agni Kai": FINAL_AGNI_KAI,
    "Bloodbending": BLOODBENDING,
    "Eclipse Darkness": ECLIPSE_DARKNESS,
    "Avatar State Fury": AVATAR_STATE_FURY,
    "Invasion Day": INVASION_DAY,
    "Tunnel Through": TUNNEL_THROUGH,
    "Spirit Bomb": SPIRIT_BOMB,
}

print(f"Loaded {len(AVATAR_TLA_CUSTOM_CARDS)} Avatar: The Last Airbender cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    AANGS_ICEBERG,
    AANG_THE_LAST_AIRBENDER,
    AIRBENDER_ASCENSION,
    AIRBENDERS_REVERSAL,
    AIRBENDING_LESSON,
    APPA_LOYAL_SKY_BISON,
    APPA_STEADFAST_GUARDIAN,
    AVATAR_ENTHUSIASTS,
    AVATARS_WRATH,
    COMPASSIONATE_HEALER,
    CURIOUS_FARM_ANIMALS,
    DESTINED_CONFRONTATION,
    EARTH_KINGDOM_JAILER,
    EARTH_KINGDOM_PROTECTORS,
    ENTER_THE_AVATAR_STATE,
    FANCY_FOOTWORK,
    GATHER_THE_WHITE_LOTUS,
    GLIDER_KIDS,
    GLIDER_STAFF,
    HAKODA_SELFLESS_COMMANDER,
    INVASION_REINFORCEMENTS,
    JEONG_JEONGS_DESERTERS,
    KATARA_WATERBENDING_MASTER,
    SOKKA_SWORDSMAN,
    SUKI_KYOSHI_WARRIOR,
    UNCLE_IROH_TEA_MASTER,
    WHITE_LOTUS_MEMBER,
    AANG_SWIFT_SAVIOR,
    ABANDON_ATTACHMENTS,
    ACCUMULATE_WISDOM,
    BENEVOLENT_RIVER_SPIRIT,
    BOOMERANG_BASICS,
    KNOWLEDGE_SEEKER,
    LIBRARY_GUARDIAN,
    MASTER_PAKKU,
    MOON_SPIRIT_BLESSING,
    NORTHERN_WATER_TRIBE,
    OCEAN_SPIRIT_FURY,
    PRINCESS_YUE,
    SPIRIT_LIBRARY,
    WATERBENDING_LESSON,
    WAN_SHI_TONG,
    AZULA_ALWAYS_LIES,
    AZULA_CUNNING_USURPER,
    AZULA_ON_THE_HUNT,
    BEETLE_HEADED_MERCHANTS,
    BOILING_ROCK_RIOTER,
    BUZZARD_WASP_COLONY,
    CANYON_CRAWLER,
    CORRUPT_COURT_OFFICIAL,
    CRUEL_ADMINISTRATOR,
    DAI_LI_INDOCTRINATION,
    DAY_OF_BLACK_SUN,
    DEADLY_PRECISION,
    EPIC_DOWNFALL,
    FATAL_FISSURE,
    FIRE_LORD_OZAI,
    LONG_FENG,
    MAI_KNIVES_EXPERT,
    BOAR_Q_PINE,
    BUMI_BASH,
    COMBUSTION_MAN,
    COMBUSTION_TECHNIQUE,
    FATED_FIREPOWER,
    FIREBENDING_LESSON,
    FIREBENDING_STUDENT,
    FIRE_NATION_ATTACKS,
    FIRE_NATION_CADETS,
    FIRE_NATION_WARSHIP,
    JEONG_JEONG_THE_DESERTER,
    PRINCE_ZUKO,
    ZUKO_REDEEMED,
    ALLIES_AT_LAST,
    AVATAR_DESTINY,
    BADGERMOLE,
    BADGERMOLE_CUB,
    BUMI_KING_OF_THREE_TRIALS,
    CYCLE_OF_RENEWAL,
    EARTHBENDER_ASCENSION,
    EARTHBENDING_LESSON,
    EARTH_KINGDOM_GENERAL,
    EARTH_RUMBLE,
    TOPH_BEIFONG,
    TOPH_METALBENDER,
    AANG_AND_LA,
    BEIFONGS_BOUNTY_HUNTERS,
    BITTER_WORK,
    BUMI_UNLEASHED,
    DAI_LI_AGENTS,
    FIRE_LORD_AZULA,
    FIRE_LORD_ZUKO,
    TEAM_AVATAR,
    TY_LEE_ACROBAT,
    AANG_STATUE,
    EARTH_KINGDOM_TANK,
    METEORITE_SWORD,
    SPIRIT_OASIS,
    AIR_TEMPLE,
    BA_SING_SE,
    FIRE_NATION_CAPITAL,
    SPIRIT_WORLD_GATE,
    WATER_TRIBE_VILLAGE,
    FIRE_NATION_OUTPOST,
    EARTH_KINGDOM_FORTRESS,
    OMASHU,
    EMBER_ISLAND,
    FOG_OF_LOST_SOULS,
    KYOSHI_ISLAND_DEFENDER,
    MEELO_THE_TROUBLEMAKER,
    MOMO_LOYAL_COMPANION,
    AIRBENDER_INITIATE,
    CABBAGE_MERCHANT,
    MONASTIC_DISCIPLINE,
    WINDS_OF_CHANGE,
    AVATAR_KORRA_SPIRIT,
    PEACEFUL_SANCTUARY,
    GURU_PATHIK,
    LION_TURTLE_BLESSING,
    GYATSO_WISE_MENTOR,
    HAMA_BLOODBENDER,
    SERPENTS_PASS_HORROR,
    SOUTHERN_WATER_TRIBE,
    FOGGY_SWAMP_WATERBENDER,
    SPIRIT_FOX,
    UNAGI_ATTACK,
    WISDOM_OF_AGES,
    AVATAR_ROKU,
    SPIRIT_WORLD_WANDERER,
    WATER_TRIBE_HEALER,
    TUI_AND_LA,
    MIST_VEIL,
    ZHAO_THE_CONQUEROR,
    DAI_LI_ENFORCER,
    SPIRIT_CORRUPTION,
    BLOODBENDING_LESSON,
    SHADOW_OF_THE_PAST,
    FIRE_NATION_PRISON,
    CRUEL_AMBITION,
    SPIRIT_OF_REVENGE,
    WAR_BALLOON_CREW,
    LAKE_LAOGAI,
    FIRE_NATION_COMMANDER,
    IROH_DRAGON_OF_THE_WEST,
    LIGHTNING_REDIRECTION,
    SOZINS_COMET,
    AGNI_KAI,
    DRAGON_DANCE,
    RAN_AND_SHAW,
    FIRE_LILY,
    VOLCANIC_ERUPTION,
    PHOENIX_REBORN,
    SWAMPBENDER,
    FLYING_BISON_HERD,
    AVATAR_KYOSHI,
    FOREST_SPIRIT,
    CATGATOR,
    SWAMP_GIANT,
    EARTH_KINGDOM_FARMER,
    NATURAL_HARMONY,
    PRIMAL_FURY,
    PLATYPUS_BEAR,
    SPIRIT_VINE,
    SOKKA_AND_SUKI,
    ZUKO_AND_IROH,
    KATARA_AND_AANG,
    AZULA_AND_DAI_LI,
    SPIRIT_WORLD_PORTAL,
    FIRELORD_SOZIN,
    AVATAR_YANGCHEN,
    AVATAR_KURUK,
    LION_TURTLE,
    KOIZILLA,
    HEIBAIFACED_SPIRIT,
    WAR_BALLOON,
    AZULAS_CROWN,
    WATER_POUCH,
    FIRE_NATION_HELM,
    AANGS_STAFF,
    TOPHS_BRACELET,
    SUNSTONE,
    MOONSTONE,
    LOTUS_TILE,
    DRILL,
    BLUE_SPIRIT_STRIKE,
    SIEGE_OF_THE_NORTH,
    CROSSROADS_OF_DESTINY,
    FINAL_AGNI_KAI,
    BLOODBENDING,
    ECLIPSE_DARKNESS,
    AVATAR_STATE_FURY,
    INVASION_DAY,
    TUNNEL_THROUGH,
    SPIRIT_BOMB,
    JINORA_SPIRITUAL_GUIDE,
    KORRA_AVATAR_UNLEASHED,
    AIRBENDING_MASTER,
    NOMAD_MUSICIAN,
    AIR_ACOLYTE,
    RESTORATION_RITUAL,
    SPIRITUAL_GUIDANCE,
    KANNA_GRAN_GRAN,
    OCEAN_DEPTHS_LEVIATHAN,
    THOUGHT_MANIPULATION,
    SPIRIT_VISION,
    WATER_WHIP,
    CRASHING_WAVES,
    ICE_SHIELD,
    KUVIRA_GREAT_UNITER,
    SHADOW_OPERATIVE,
    DARK_SPIRITS_BLESSING,
    MIND_BREAK,
    CORRUPT_OFFICIAL,
    DEATH_BY_LIGHTNING,
    PRISON_BREAK,
    PIANDAO_SWORD_MASTER,
    FIRE_NATION_SOLDIER,
    RAGE_OF_FIRE,
    LIGHTNING_BOLT_LESSON,
    FIRE_WALL,
    COMET_ENHANCED,
    CALDERA_ERUPTION,
    DUE_THE_EARTH_SPIRIT,
    FOREST_GUARDIAN,
    OASIS_HERMIT,
    WILD_GROWTH,
    BEAST_SUMMONS,
    NATURE_RECLAMATION,
    STANDING_TALL,
    MAI_AND_TY_LEE,
    AMON_THE_EQUALIST,
    UNALAQ_DARK_AVATAR,
    SPIRIT_OF_RAAVA,
    SPIRIT_OF_VAATU,
    RED_LOTUS,
    WHITE_LOTUS_GRANDMASTER,
    BOOMERANG_ARTIFACT,
    CACTUS_JUICE,
    FIREBENDING_SCROLL,
    EARTHBENDING_SCROLL,
    WATERBENDING_SCROLL,
    AIRBENDING_SCROLL,
    SUBMARINE,
    CHI_BLOCKER_GLOVES,
    SOUTHERN_AIR_TEMPLE,
    WESTERN_AIR_TEMPLE,
    KYOSHI_ISLAND,
    BOILING_ROCK_PRISON,
    SERPENTS_PASS,
    FOGGY_SWAMP,
    SI_WONG_DESERT,
    NORTHERN_WATER_TRIBE_CAPITAL,
    REPUBLIC_CITY,
    PRO_BENDING_ARENA,
    MAKO_FIREBENDER,
    BOLIN_LAVABENDER,
    ASAMI_SATO,
    LIN_BEIFONG,
    TENZIN_AIRBENDING_MASTER,
    ZAHEER_RED_LOTUS_LEADER,
    PLI_COMBUSTION_BENDER,
    GHAZAN_LAVABENDER,
    MING_HUA_WATERBENDER,
    NAGA_POLAR_BEAR_DOG,
    PABU_FIRE_FERRET,
    VARRICK_INDUSTRIALIST,
    ZHU_LI_ASSISTANT,
    TARRLOK_BLOODBENDER,
    NOATAK_AMON,
    EQUALIST_CHI_BLOCKER,
    MECHA_TANK,
    SPIRIT_WILDS,
    HARMONIC_CONVERGENCE,
    AIR_NATION_RESTORED,
    PRO_BENDING_MATCH,
    PLATINUM_MECH_SUIT,
    SPIRIT_CANNON,
    AIRBENDERS_FLIGHT,
    LAVABENDING,
    METALBENDING_CABLE,
    SPIRIT_PORTAL,
    KORRA_AND_ASAMI,
    PLAINS_TLA,
    ISLAND_TLA,
    SWAMP_TLA,
    MOUNTAIN_TLA,
    FOREST_TLA
]
