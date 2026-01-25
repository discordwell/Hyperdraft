"""
Wilds of Eldraine (WOE) Card Implementations

Set released September 8, 2023. ~266 cards.
Features mechanics: Adventure, Bargain, Role tokens, Celebration
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


def make_aura(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create aura enchantment card definitions."""
    base_subtypes = {"Aura"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes=base_subtypes,
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_saga(name: str, mana_cost: str, colors: set, text: str, supertypes: set = None, setup_interceptors=None):
    """Helper to create saga enchantment card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes={"Saga"},
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# WILDS OF ELDRAINE KEYWORD MECHANICS
# =============================================================================

def make_adventure(source_obj: GameObject, adventure_name: str, adventure_cost: str, adventure_effect: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Adventure - A spell that can be cast as either a creature or an instant/sorcery.
    When cast as the adventure, exile it instead of putting it in graveyard.
    """
    def adventure_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        return (event.payload.get('spell_id') == source_obj.id and
                event.payload.get('mode') == 'adventure')

    def adventure_handler(event: Event, state: GameState) -> InterceptorResult:
        effect_events = adventure_effect(event, state)
        # After resolving, exile to adventure zone
        exile_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': source_obj.id,
                'to_zone_type': ZoneType.EXILE,
                'adventure_exiled': True
            },
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_events + [exile_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=adventure_filter,
        handler=adventure_handler,
        duration='until_leaves'
    )


def make_bargain_bonus(source_obj: GameObject, base_effect: Callable[[Event, GameState], list[Event]], bonus_effect: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Bargain - You may sacrifice an artifact, enchantment, or token as you cast this spell.
    If bargained, get a bonus effect.
    """
    def bargain_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('object_id') == source_obj.id and
                event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)

    def bargain_handler(event: Event, state: GameState) -> InterceptorResult:
        was_bargained = event.payload.get('bargained', False)
        base_events = base_effect(event, state)
        if was_bargained:
            bonus_events = bonus_effect(event, state)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=base_events + bonus_events
            )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=base_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=bargain_filter,
        handler=bargain_handler,
        duration='while_on_battlefield'
    )


def make_celebration_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Celebration - Triggers if two or more nonland permanents entered the battlefield under your control this turn.
    """
    def celebration_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('object_id') != source_obj.id:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Check celebration condition
        permanents_entered = state.turn_data.get('permanents_entered_this_turn', {})
        controller_count = permanents_entered.get(source_obj.controller, 0)
        return controller_count >= 2

    def celebration_handler(event: Event, state: GameState) -> InterceptorResult:
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
        filter=celebration_filter,
        handler=celebration_handler,
        duration='while_on_battlefield'
    )


def make_role_token(source_obj: GameObject, role_type: str, target_id: str) -> Event:
    """
    Create a Role token that enchants a creature.
    Role types: Cursed, Monster, Royal, Sorcerer, Wicked, Young Hero
    """
    role_effects = {
        'Cursed': {'power': 0, 'toughness': 0, 'text': 'Enchanted creature has base power and toughness 1/1.'},
        'Monster': {'power': 1, 'toughness': 1, 'text': 'Enchanted creature gets +1/+1 and has trample.'},
        'Royal': {'power': 1, 'toughness': 1, 'text': 'Enchanted creature gets +1/+1 and has ward {1}.'},
        'Sorcerer': {'power': 1, 'toughness': 1, 'text': 'Enchanted creature gets +1/+1 and has "Whenever this creature attacks, scry 1."'},
        'Wicked': {'power': 1, 'toughness': 0, 'text': 'Enchanted creature gets +1/+0. When this Aura is put into a graveyard, each opponent loses 1 life.'},
        'Young Hero': {'power': 0, 'toughness': 0, 'text': 'Enchanted creature has "Whenever this creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it."'}
    }
    effect = role_effects.get(role_type, {'power': 0, 'toughness': 0, 'text': ''})
    return Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': source_obj.controller,
            'token': {
                'name': f'{role_type} Role',
                'types': {CardType.ENCHANTMENT},
                'subtypes': {'Aura', 'Role'},
                'colors': set(),
                'attached_to': target_id,
                'effect': effect
            }
        },
        source=source_obj.id
    )


def faerie_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Faerie creatures you control."""
    return creatures_with_subtype(source, "Faerie")


def knight_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Knight creatures you control."""
    return creatures_with_subtype(source, "Knight")


def rat_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Rat creatures you control."""
    return creatures_with_subtype(source, "Rat")


def food_count(state: GameState, controller: str) -> int:
    """Count Food tokens a player controls."""
    count = 0
    for obj in state.objects.values():
        if (obj.controller == controller and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.ARTIFACT in obj.characteristics.types and
            'Food' in obj.characteristics.subtypes):
            count += 1
    return count


# =============================================================================
# WHITE CARDS
# =============================================================================

# --- Legendary Creatures ---

def kellan_the_fae_blooded_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike, when deals combat damage to a player, look at top card, may exile it"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LOOK_TOP,
            payload={'player': obj.controller, 'count': 1, 'may_exile': True},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

KELLAN_THE_FAE_BLOODED = make_creature(
    name="Kellan, the Fae-Blooded",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Faerie"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Kellan deals combat damage to a player, look at the top card of your library. You may exile it. You may cast spells exiled with Kellan.",
    setup_interceptors=kellan_the_fae_blooded_setup
)


def eriette_of_the_charmed_apple_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of end step, each opponent loses X life where X = enchanted creatures they control"""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opponent in all_opponents(obj, state):
            enchanted_count = 0
            for o in state.objects.values():
                if (o.controller == opponent and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types and
                    hasattr(o.state, 'enchanted_by') and o.state.enchanted_by):
                    enchanted_count += 1
            if enchanted_count > 0:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opponent, 'amount': -enchanted_count},
                    source=obj.id
                ))
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': enchanted_count},
                    source=obj.id
                ))
        return events
    return [make_end_step_trigger(obj, end_step_effect, controller_only=True)]

ERIETTE_OF_THE_CHARMED_APPLE = make_creature(
    name="Eriette of the Charmed Apple",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, each opponent loses X life and you gain X life, where X is the number of creatures they control with Auras you control attached to them.",
    setup_interceptors=eriette_of_the_charmed_apple_setup
)


IMODANE_THE_PYROHAMMER = make_creature(
    name="Imodane, the Pyrohammer",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever an instant or sorcery spell you control deals damage to exactly one creature, Imodane deals that much damage to that creature's controller."
)


def moonshaker_cavalry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Creatures you control gain flying and get +X/+X where X is number of creatures you control"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        creature_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller
                           and o.zone == ZoneType.BATTLEFIELD
                           and CardType.CREATURE in o.characteristics.types)
        return [Event(
            type=EventType.BOOST_UNTIL_EOT,
            payload={
                'target': 'all_creatures_you_control',
                'controller': obj.controller,
                'power': creature_count,
                'toughness': creature_count,
                'keywords': ['flying']
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

MOONSHAKER_CAVALRY = make_creature(
    name="Moonshaker Cavalry",
    power=6, toughness=6,
    mana_cost="{5}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Knight"},
    text="Flying. When Moonshaker Cavalry enters, creatures you control gain flying and get +X/+X until end of turn, where X is the number of creatures you control.",
    setup_interceptors=moonshaker_cavalry_setup
)


# --- Regular Creatures ---

def archon_of_the_wild_rose_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control with Auras attached get +2/+1"""
    def aura_filter(target: GameObject, gs: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return hasattr(target.state, 'enchanted_by') and len(target.state.enchanted_by) > 0
    return make_static_pt_boost(obj, 2, 1, aura_filter)

ARCHON_OF_THE_WILD_ROSE = make_creature(
    name="Archon of the Wild Rose",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Archon"},
    text="Flying. Other creatures you control with Auras attached to them get +2/+1.",
    setup_interceptors=archon_of_the_wild_rose_setup
)


def armored_armadillo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, create a Food token"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Food', 'types': {CardType.ARTIFACT}, 'subtypes': {'Food'}}
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

ARMORED_ARMADILLO = make_creature(
    name="Armored Armadillo",
    power=0, toughness=4,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Armadillo"},
    text="Vigilance. When Armored Armadillo dies, create a Food token.",
    setup_interceptors=armored_armadillo_setup
)


BESOTTED_KNIGHT = make_creature(
    name="Besotted Knight",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Lifelink. Adventure - Betroth the Beast: {1}{W} Sorcery - Create a Royal Role token attached to target creature you control."
)


BREAK_THE_SPELL = make_instant(
    name="Break the Spell",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Destroy target enchantment. If an Aura with enchant creature was destroyed this way, draw a card."
)


CHARMED_CLOTHIER = make_creature(
    name="Charmed Clothier",
    power=3, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="When Charmed Clothier enters, create a Royal Role token attached to target creature you control."
)


def cooped_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchanted creature can't attack or block"""
    return []  # Aura effect handled by enchantment system

COOPED_UP = make_aura(
    name="Cooped Up",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature. Enchanted creature can't attack or block. {4}{W}: Exile enchanted creature.",
    setup_interceptors=cooped_up_setup
)


CURSED_COURTIER = make_creature(
    name="Cursed Courtier",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="Vigilance. When Cursed Courtier enters, create a Cursed Role token attached to it."
)


DUTIFUL_GRIFFIN = make_creature(
    name="Dutiful Griffin",
    power=3, toughness=2,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Griffin"},
    text="Flying. When Dutiful Griffin enters, return target enchantment card from your graveyard to your hand."
)


def faerie_guidemother_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Adventure - Gift of the Fae: Target creature gets +2/+1 and flying until end of turn"""
    def adventure_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.BOOST_UNTIL_EOT,
            payload={'target': event.payload.get('target'), 'power': 2, 'toughness': 1, 'keywords': ['flying']},
            source=obj.id
        )]
    return [make_adventure(obj, "Gift of the Fae", "{W}", adventure_effect)]

FAERIE_GUIDEMOTHER = make_creature(
    name="Faerie Guidemother",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Faerie"},
    text="Flying. Adventure - Gift of the Fae: {W} Sorcery - Target creature gets +2/+1 and gains flying until end of turn.",
    setup_interceptors=faerie_guidemother_setup
)


GRAND_BALL_GUEST = make_creature(
    name="Grand Ball Guest",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="Lifelink. Celebration - At the beginning of your end step, if two or more nonland permanents entered the battlefield under your control this turn, Grand Ball Guest gets +2/+0 until your next turn."
)


HOPEFUL_VIGIL = make_enchantment(
    name="Hopeful Vigil",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When Hopeful Vigil enters, create a 2/2 white Knight creature token with vigilance. {2}{W}, Sacrifice Hopeful Vigil: Draw a card."
)


def kellan_daring_traveler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell with mana value 5 or greater, draw a card"""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    def big_spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        return event.payload.get('mana_value', 0) >= 5

    return [make_spell_cast_trigger(obj, spell_cast_effect, filter_fn=big_spell_filter)]

KELLAN_DARING_TRAVELER = make_creature(
    name="Kellan, Daring Traveler",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Faerie"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell with mana value 5 or greater, draw a card. Adventure - Kellan's Lightblades: {1}{W} Instant - Target creature gets +2/+2 until end of turn.",
    setup_interceptors=kellan_daring_traveler_setup
)


KNIGHT_OF_DOVES = make_creature(
    name="Knight of Doves",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever an enchantment you control is put into your graveyard from the battlefield, create a 1/1 white Bird creature token with flying."
)


PLUNGE_INTO_WINTER = make_instant(
    name="Plunge into Winter",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Tap target creature. Create a Food token."
)


REGAL_BUNNICORN = make_creature(
    name="Regal Bunnicorn",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Unicorn"},
    text="Regal Bunnicorn's power and toughness are each equal to the number of nonland permanents you control."
)


def stockpiling_celebrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Celebration - when enters, draw a card"""
    def celebration_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_celebration_trigger(obj, celebration_effect)]

STOCKPILING_CELEBRANT = make_creature(
    name="Stockpiling Celebrant",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="Celebration - When Stockpiling Celebrant enters, if two or more nonland permanents entered the battlefield under your control this turn, draw a card.",
    setup_interceptors=stockpiling_celebrant_setup
)


WEREFOX_BODYGUARD = make_creature(
    name="Werefox Bodyguard",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Elf", "Fox", "Knight"},
    text="Flash. When Werefox Bodyguard enters, exile up to one other target non-Fox creature until Werefox Bodyguard leaves the battlefield. When Werefox Bodyguard leaves, create a Food token."
)


WITCH_DEFIANCE = make_instant(
    name="Witch's Defiance",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+0 until end of turn. If you control an enchantment, creatures you control also gain first strike until end of turn."
)


# =============================================================================
# BLUE CARDS
# =============================================================================

# --- Legendary Creatures ---

def talion_the_kindly_lord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Choose a number 1-10. Whenever opponent casts spell with that mana value, draw and they lose 2 life"""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        chosen = obj.state.counters.get('chosen_number', 3)
        if event.payload.get('mana_value') == chosen and event.payload.get('caster') != obj.controller:
            return [
                Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
                Event(type=EventType.LIFE_CHANGE, payload={'player': event.payload.get('caster'), 'amount': -2}, source=obj.id)
            ]
        return []

    return [make_spell_cast_trigger(obj, spell_effect, controller_only=False)]

TALION_THE_KINDLY_LORD = make_creature(
    name="Talion, the Kindly Lord",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Faerie", "Noble"},
    supertypes={"Legendary"},
    text="Flying. As Talion enters, choose a number between 1 and 10. Whenever an opponent casts a spell with mana value, power, or toughness equal to the chosen number, that player loses 2 life and you draw a card.",
    setup_interceptors=talion_the_kindly_lord_setup
)


def hylda_of_the_icy_crown_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you tap an opponent's creature, pay 1 to choose mode"""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if target and target.controller != obj.controller:
            return [Event(
                type=EventType.MODAL_CHOICE,
                payload={
                    'controller': obj.controller,
                    'modes': ['4/4 token', 'scry 2 draw', '+1/+1 counters'],
                    'cost': '{1}'
                },
                source=obj.id
            )]
        return []

    def tap_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        return (target and
                target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=tap_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=tap_effect(e, s)),
        duration='while_on_battlefield'
    )]

HYLDA_OF_THE_ICY_CROWN = make_creature(
    name="Hylda of the Icy Crown",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you tap an untapped creature an opponent controls, you may pay {1}. If you do, choose one: Create a 4/4 white and blue Elemental token. Scry 2, then draw. Put a +1/+1 counter on each creature you control.",
    setup_interceptors=hylda_of_the_icy_crown_setup
)


HORNED_LOCH_WHALE = make_creature(
    name="Horned Loch-Whale",
    power=6, toughness=6,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Whale"},
    text="Flash. Horned Loch-Whale enters tapped. When Horned Loch-Whale enters, you may return target nonland permanent to its owner's hand. Adventure - Lagoon Breach: {1}{U} Instant - Tap target creature."
)


# --- Regular Creatures ---

AQUATIC_ALCHEMIST = make_creature(
    name="Aquatic Alchemist",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="When Aquatic Alchemist enters, return target instant or sorcery card from your graveyard to your hand, then discard a card."
)


def faerie_fencing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Target creature gets -X/-0 where X is number of Faeries you control"""
    return []

FAERIE_FENCING = make_instant(
    name="Faerie Fencing",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -X/-0 until end of turn, where X is the number of Faeries you control."
)


def frolicking_familiar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage, draw and discard"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

FROLICKING_FAMILIAR = make_creature(
    name="Frolicking Familiar",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="Whenever Frolicking Familiar deals combat damage to a player, draw a card, then discard a card. Adventure - Blow Off Steam: {U} Instant - Target creature gets +1/-1 until end of turn.",
    setup_interceptors=frolicking_familiar_setup
)


GADWICK_THE_WIZENED = make_creature(
    name="Gadwick, the Wizened",
    power=3, toughness=3,
    mana_cost="{X}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Gadwick enters, draw X cards. Whenever you cast a blue spell, tap target nonland permanent an opponent controls."
)


ICE_OUT = make_instant(
    name="Ice Out",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Bargain - If this spell was bargained, scry 2."
)


Johann_APPRENTICE_SORCERER = make_creature(
    name="Johann, Apprentice Sorcerer",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if you've cast an instant or sorcery spell this turn, create a Young Hero Role token attached to Johann. {3}{U}: Draw a card."
)


MALKAVIAN_JESTER = make_creature(
    name="Malkavian Jester",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying. Whenever you draw your second card each turn, create a 1/1 blue Faerie creature token with flying."
)


def merfolk_coralsmith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks, create a map token"""
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Map', 'types': {CardType.ARTIFACT}, 'subtypes': {'Map'}}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect), make_attack_trigger(obj, effect)]

MERFOLK_CORALSMITH = make_creature(
    name="Merfolk Coralsmith",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="When Merfolk Coralsmith enters or attacks, create a Map token.",
    setup_interceptors=merfolk_coralsmith_setup
)


MISLEADING_MOTES = make_instant(
    name="Misleading Motes",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands. Adventure - Terrors of Faedom: {1}{U} Instant - Target creature gets -X/-0 until end of turn, where X is 3."
)


OBYRA_DREAMING_DUELIST = make_creature(
    name="Obyra, Dreaming Duelist",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Knight"},
    supertypes={"Legendary"},
    text="Flash, flying. Whenever another Faerie enters the battlefield under your control, each opponent loses 1 life."
)


QUICK_STUDY = make_instant(
    name="Quick Study",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards."
)


def sleight_of_hand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []

SLEIGHT_OF_HAND = make_sorcery(
    name="Sleight of Hand",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top two cards of your library. Put one of them into your hand and the other on the bottom of your library."
)


SNAREMASTER_SPRITE = make_creature(
    name="Snaremaster Sprite",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying. When Snaremaster Sprite enters, if you control three or more creatures, draw a card."
)


SPELL_STUTTER = make_instant(
    name="Spell Stutter",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {1} for each Faerie you control. Create a 1/1 blue Faerie creature token with flying."
)


SUCCUMB_TO_THE_COLD = make_instant(
    name="Succumb to the Cold",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap up to two target creatures. Draw a card."
)


TEMPEST_HART = make_creature(
    name="Tempest Hart",
    power=4, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Elk"},
    text="Flying. When Tempest Hart enters, if it was cast, each player draws two cards."
)


WATER_WINGS = make_instant(
    name="Water Wings",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature gets +1/+3 and gains flying until end of turn."
)


# =============================================================================
# BLACK CARDS
# =============================================================================

# --- Legendary Creatures ---

def rankle_master_of_pranks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage, may choose modes"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MODAL_CHOICE,
            payload={
                'controller': obj.controller,
                'modes': ['each player discards', 'each player loses 1 life', 'each player sacs creature'],
                'may_choose_multiple': True
            },
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

RANKLE_MASTER_OF_PRANKS = make_creature(
    name="Rankle, Master of Pranks",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    supertypes={"Legendary"},
    text="Flying, haste. Whenever Rankle deals combat damage to a player, choose any number: Each player discards a card. Each player loses 1 life and draws a card. Each player sacrifices a creature.",
    setup_interceptors=rankle_master_of_pranks_setup
)


def ashiok_wicked_manipulator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Replacement - if you would pay life, exile that many from top of library instead"""
    return []

ASHIOK_WICKED_MANIPULATOR = make_creature(
    name="Ashiok, Wicked Manipulator",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    supertypes={"Legendary"},
    text="If you would pay life, exile that many cards from the top of your library instead. Whenever one or more cards are exiled from your library, create a 1/1 black Nightmare creature token with 'This creature's power and toughness are each equal to the number of cards in exile that were exiled from libraries.'"
)


THE_WITCH_S_VANITY = make_saga(
    name="The Witch's Vanity",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="I - Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. II - You lose 1 life. III - Return target creature card from your graveyard to your hand."
)


# --- Regular Creatures ---

BACK_FOR_SECONDS = make_sorcery(
    name="Back for Seconds",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. Bargain - If this spell was bargained, you may return up to three creature cards instead."
)


def barrow_naughty_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - target opponent loses life equal to Faeries you control"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        faerie_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and o.zone == ZoneType.BATTLEFIELD
                         and 'Faerie' in o.characteristics.subtypes)
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': event.payload.get('target_opponent'), 'amount': -faerie_count},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

BARROW_NAUGHTY = make_creature(
    name="Barrow Naughty",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying. When Barrow Naughty enters, target opponent loses life equal to the number of Faeries you control.",
    setup_interceptors=barrow_naughty_setup
)


CANDY_TRAIL = make_artifact(
    name="Candy Trail",
    mana_cost="{1}",
    text="When Candy Trail enters, you gain 1 life. {1}, {T}, Sacrifice Candy Trail: Draw a card and create a Food token."
)


CONCEITED_WITCH = make_creature(
    name="Conceited Witch",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Menace. Adventure - Price of Beauty: {B} Instant - You draw a card and you lose 1 life."
)


CRUEL_SOMNOPHAGE = make_creature(
    name="Cruel Somnophage",
    power=4, toughness=4,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Cruel Somnophage's power and toughness are each equal to the number of creature cards in all graveyards. Adventure - Can't Wake Up: {1}{B} Sorcery - Mill four cards."
)


DURESS = make_sorcery(
    name="Duress",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a noncreature, nonland card from it. That player discards that card."
)


EMERGENCY_CALL_UP = make_sorcery(
    name="Emergency Call-Up",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Create three 1/1 black Rat creature tokens with 'This creature can't block.' Bargain - If this spell was bargained, those tokens enter with a +1/+1 counter on them."
)


def faerie_dreamthief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - look at top 2, put one in graveyard"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LOOK_TOP,
            payload={'player': obj.controller, 'count': 2, 'put_one_in_graveyard': True},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

FAERIE_DREAMTHIEF = make_creature(
    name="Faerie Dreamthief",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying. When Faerie Dreamthief enters, look at the top two cards of your library. Put one of them into your graveyard.",
    setup_interceptors=faerie_dreamthief_setup
)


FEED_THE_CAULDRON = make_sorcery(
    name="Feed the Cauldron",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with mana value 3 or less. Create a Food token."
)


FESTIVE_FUNERAL = make_instant(
    name="Festive Funeral",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Target creature gets -X/-X until end of turn, where X is the number of cards in your graveyard."
)


GUMDROP_POISONER = make_creature(
    name="Gumdrop Poisoner",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When Gumdrop Poisoner enters, you gain 2 life. Then you may pay life equal to target creature's toughness. If you do, destroy it. Bargain - This ability costs {0} to activate instead of life."
)


HIGH_FAEBORN = make_creature(
    name="High Faeborn",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Noble"},
    text="Flying. Whenever High Faeborn deals combat damage to a player, you may sacrifice another creature. If you do, draw two cards."
)


LORD_SKITTER_SEWER_KING = make_creature(
    name="Lord Skitter, Sewer King",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Noble"},
    supertypes={"Legendary"},
    text="Other Rats you control get +1/+1. At the beginning of combat on your turn, create a 1/1 black Rat creature token with 'This creature can't block.'"
)


def lords_of_the_pit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - sacrifice a creature or lose 7 life"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.FORCED_SACRIFICE,
            payload={'controller': obj.controller, 'type': 'creature', 'or_lose_life': 7},
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]

LORD_OF_THE_PIT = make_creature(
    name="Lord of the Pit",
    power=7, toughness=7,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying, trample. At the beginning of your upkeep, sacrifice a creature other than Lord of the Pit. If you can't, Lord of the Pit deals 7 damage to you.",
    setup_interceptors=lords_of_the_pit_setup
)


MINTSTROSITY = make_creature(
    name="Mintstrosity",
    power=3, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Sacrifice a Food: Draw a card."
)


RATCATCHER_TRAINEE = make_creature(
    name="Ratcatcher Trainee",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Peasant"},
    text="When Ratcatcher Trainee enters, create a 1/1 black Rat creature token with 'This creature can't block.' Adventure - Stag Your Claim: {B} Sorcery - Target opponent discards a card."
)


ROWAN_SOULFIRE = make_creature(
    name="Rowan, Soulfire Grand Master",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Instant and sorcery spells you control have lifelink. {2}{U}{R}: Whenever you cast an instant or sorcery spell this turn, copy it. You may choose new targets for the copy."
)


SCREAM_PUFF = make_creature(
    name="Scream Puff",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental"},
    text="Sacrifice a Food: Scream Puff gains deathtouch until end of turn. When Scream Puff dies, create a Food token."
)


SHATTER_THE_OATH = make_instant(
    name="Shatter the Oath",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or planeswalker. You lose life equal to its mana value."
)


def specter_of_mortality_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - each opponent mills 2, you draw equal to cards milled"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        total_milled = 0
        for opponent in all_opponents(obj, state):
            events.append(Event(type=EventType.MILL, payload={'player': opponent, 'amount': 2}, source=obj.id))
            total_milled += 2
        events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': total_milled}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]

SPECTER_OF_MORTALITY = make_creature(
    name="Specter of Mortality",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Specter"},
    text="Flying. When Specter of Mortality enters, each opponent mills two cards. You draw a card for each creature card milled this way.",
    setup_interceptors=specter_of_mortality_setup
)


STINGBLADE_ASSASSIN = make_creature(
    name="Stingblade Assassin",
    power=3, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Assassin"},
    text="Flying. When Stingblade Assassin enters, destroy target creature that was dealt damage this turn."
)


TAKEN_BY_NIGHTMARES = make_aura(
    name="Taken by Nightmares",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Enchant creature. When Taken by Nightmares enters, create a Wicked Role token attached to enchanted creature. Enchanted creature gets -2/-2."
)


THE_END = make_instant(
    name="The End",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature or planeswalker. Search its controller's graveyard, hand, and library for any number of cards with the same name as that permanent and exile them. That player shuffles, then draws a card for each card exiled from their hand this way."
)


VIRTUE_OF_PERSISTENCE = make_enchantment(
    name="Virtue of Persistence",
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, put target creature card from a graveyard onto the battlefield under your control. Adventure - Locthwain Scorn: {1}{B} Instant - Target creature gets -3/-3 until end of turn. You gain 2 life."
)


WICKED_VISITOR = make_creature(
    name="Wicked Visitor",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Whenever an enchantment enters the battlefield under your control, each opponent loses 1 life."
)


# =============================================================================
# RED CARDS
# =============================================================================

# --- Legendary Creatures ---

def will_scion_of_peace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage to player, copy target instant or sorcery spell"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COPY_SPELL,
            payload={'controller': obj.controller, 'may_choose_new_targets': True},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

WILL_SCION_OF_PEACE = make_creature(
    name="Will, Scion of Peace",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Vigilance. {T}: The next spell you cast this turn that's white and/or blue costs {X} less to cast, where X is the amount of life you gained this turn.",
    setup_interceptors=will_scion_of_peace_setup
)


ROWAN_SCION_OF_WAR = make_creature(
    name="Rowan, Scion of War",
    power=4, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Menace. {T}: Spells you cast this turn that are black and/or red cost {X} less to cast, where X is the amount of life you've lost this turn."
)


GODDRIC_CLOAKED_REVELER = make_creature(
    name="Goddric, Cloaked Reveler",
    power=4, toughness=4,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Haste. Celebration - As long as two or more nonland permanents entered the battlefield under your control this turn, Goddric is a Dragon with flying and '{R}: Goddric gets +1/+0 until end of turn.'"
)


AGATHA_OF_THE_VILE_CAULDRON = make_creature(
    name="Agatha of the Vile Cauldron",
    power=1, toughness=1,
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Activated abilities of creatures you control cost {X} less to activate, where X is Agatha's power. This effect can't reduce the mana in that cost to less than one mana. {X}{R}{G}: Target creature gets +X/+X until end of turn."
)


# --- Regular Creatures ---

ARCHERY_TRAINING = make_aura(
    name="Archery Training",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchant creature. At the beginning of your upkeep, put an arrow counter on Archery Training. Enchanted creature has '{T}: This creature deals damage equal to the number of arrow counters on Archery Training to target player.'"
)


BOUNDARY_LANDS_RANGER = make_creature(
    name="Boundary Lands Ranger",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Peasant"},
    text="When Boundary Lands Ranger enters or dies, create a Young Hero Role token attached to target creature you control."
)


def broom_rider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Celebration - when enters, create a 1/1 Rat"""
    def celebration_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Rat', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Rat'}}
            },
            source=obj.id
        )]
    return [make_celebration_trigger(obj, celebration_effect)]

BROOM_RIDER = make_creature(
    name="Broom Rider",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Peasant"},
    text="Menace. Celebration - When Broom Rider enters, if two or more nonland permanents entered the battlefield under your control this turn, create a 1/1 black Rat creature token with 'This creature can't block.'",
    setup_interceptors=broom_rider_setup
)


CHEEKY_HOUSE_MOUSE = make_creature(
    name="Cheeky House-Mouse",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Mouse"},
    text="Adventure - Squeak By: {R} Sorcery - Target creature can't block this turn."
)


CROSSBOW_MARKSMAN = make_creature(
    name="Crossbow Marksman",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="When Crossbow Marksman enters, target creature you control gets +1/+0 and gains first strike until end of turn."
)


DRAGON_MANTLE = make_aura(
    name="Dragon Mantle",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchant creature. When Dragon Mantle enters, draw a card. Enchanted creature has '{R}: This creature gets +1/+0 until end of turn.'"
)


EDGEWALL_PACK = make_creature(
    name="Edgewall Pack",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Wolf"},
    text="Menace. Adventure - Prey Upon the Weak: {1}{R} Sorcery - Target creature you control deals damage equal to its power to target creature you don't control."
)


EMBERETH_VETERAN = make_creature(
    name="Embereth Veteran",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    text="When Embereth Veteran enters, target creature gets +1/+0 until end of turn."
)


FLAMEBREAKER = make_sorcery(
    name="Flamebreaker",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Flamebreaker deals 4 damage to target creature or planeswalker. Bargain - If this spell was bargained, it deals 4 damage to each creature your opponents control instead."
)


FRENZIED_GOLEM = make_artifact_creature(
    name="Frenzied Golem",
    power=4, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Golem"},
    text="Frenzied Golem can't block. {1}{R}: Frenzied Golem gains first strike until end of turn."
)


GRUFF_TRIPLETS = make_creature(
    name="Gruff Triplets",
    power=3, toughness=3,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Goat", "Warrior"},
    text="Trample. When Gruff Triplets enters, create two tokens that are copies of it. When Gruff Triplets dies, put a number of +1/+1 counters equal to its power on each Goat you control."
)


HARRIED_SPEARGUARD = make_creature(
    name="Harried Spearguard",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Haste. When Harried Spearguard dies, create a 1/1 white Human creature token."
)


MONSTROUS_RAGE = make_instant(
    name="Monstrous Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains trample until end of turn. Create a Monster Role token attached to it."
)


RATTY_FEAST = make_sorcery(
    name="Ratty Feast",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Create three 1/1 black Rat creature tokens with 'This creature can't block.' Then Rats you control get +1/+0 and gain haste until end of turn."
)


REDCAP_GUTTER_DWELLER = make_creature(
    name="Redcap Gutter-Dweller",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Ward {2}. When Redcap Gutter-Dweller enters, create a Treasure token. Whenever a Treasure you control is put into a graveyard from the battlefield, target creature can't block this turn."
)


STONESPLITTER_BOLT = make_instant(
    name="Stonesplitter Bolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Stonesplitter Bolt deals 3 damage to target creature with flying."
)


TORCH_THE_TOWER = make_instant(
    name="Torch the Tower",
    mana_cost="{R}",
    colors={Color.RED},
    text="Bargain. Torch the Tower deals 2 damage to target creature or planeswalker. If this spell was bargained, it deals 3 damage instead."
)


VIRTUE_OF_COURAGE = make_enchantment(
    name="Virtue of Courage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Whenever a source you control deals noncombat damage to an opponent, exile the top card of your library. You may play that card this turn. Adventure - Erupting Flames: {2}{R} Instant - Erupting Flames deals 2 damage to any target."
)


WITCHSTALKER_FRENZY = make_instant(
    name="Witchstalker Frenzy",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="This spell costs {2} less to cast if you control a creature with power 4 or greater. Witchstalker Frenzy deals 5 damage to target creature."
)


# =============================================================================
# GREEN CARDS
# =============================================================================

# --- Legendary Creatures ---

def questing_druid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When casts adventure spell, put +1/+1 counter on this"""
    def adventure_cast_effect(event: Event, state: GameState) -> list[Event]:
        if event.payload.get('mode') == 'adventure':
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        return []

    def adventure_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        return event.payload.get('mode') == 'adventure'

    return [make_spell_cast_trigger(obj, adventure_cast_effect, filter_fn=adventure_filter)]

QUESTING_DRUID = make_creature(
    name="Questing Druid",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="Whenever you cast a spell that has an Adventure, put a +1/+1 counter on Questing Druid. Adventure - Seek the Beast: {2}{G} Sorcery - Look at the top five cards of your library. You may reveal a creature card from among them and put it into your hand. Put the rest on the bottom in a random order.",
    setup_interceptors=questing_druid_setup
)


TROYAN_GUTSY_EXPLORER = make_creature(
    name="Troyan, Gutsy Explorer",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, look at the top card of your library. You may put it on the bottom. {T}: Add {G}. If you control a creature with power 4 or greater, add {G}{G} instead."
)


GRETA_SWEETTOOTH_SCOURGE = make_creature(
    name="Greta, Sweettooth Scourge",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Peasant", "Warlock"},
    supertypes={"Legendary"},
    text="{G}, Sacrifice a Food: Put a +1/+1 counter on target creature. Activate only as a sorcery. {B}, Sacrifice a Food: Draw a card."
)


def old_flitterbark_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance. ETB and attack - create X 1/1 Faerie tokens where X = enchantments you control"""
    def token_effect(event: Event, state: GameState) -> list[Event]:
        enchantment_count = sum(1 for o in state.objects.values()
                               if o.controller == obj.controller
                               and o.zone == ZoneType.BATTLEFIELD
                               and CardType.ENCHANTMENT in o.characteristics.types)
        events = []
        for _ in range(enchantment_count):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {'name': 'Faerie', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Faerie'}, 'keywords': ['flying']}
                },
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, token_effect), make_attack_trigger(obj, token_effect)]

OLD_FLITTERBARK = make_creature(
    name="Old Flitterbark",
    power=6, toughness=5,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    supertypes={"Legendary"},
    text="Vigilance. When Old Flitterbark enters and whenever it attacks, create X 1/1 green Faerie creature tokens with flying, where X is the number of enchantments you control.",
    setup_interceptors=old_flitterbark_setup
)


# --- Regular Creatures ---

BEANSTALK_WURM = make_creature(
    name="Beanstalk Wurm",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wurm"},
    text="Adventure - Reach the Skies: {1}{G} Sorcery - Create a 1/1 green Peasant creature token with '{T}: Add {G}.'"
)


CURSE_OF_LEECHES = make_aura(
    name="Curse of Leeches",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="Enchant player. At the beginning of enchanted player's upkeep, they lose 1 life and you gain 1 life."
)


ELF_VORACIOUS_READER = make_creature(
    name="Elf, Voracious Reader",
    power=4, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="Reach. When Elf, Voracious Reader enters, you may sacrifice an artifact or enchantment. If you do, draw two cards."
)


FEROCIOUS_WEREFOX = make_creature(
    name="Ferocious Werefox",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Fox"},
    text="Adventure - Gorge Glutton: {3}{G}{G} Creature - Giant - 7/6. Trample."
)


FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach. When Forest Guardian enters, you may destroy target artifact or enchantment."
)


GIANT_KILLER = make_creature(
    name="Giant Killer",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="Adventure - Chop Down: {2}{W} Instant - Destroy target creature with power 4 or greater."
)


GRACEFUL_TAKEDOWN = make_instant(
    name="Graceful Takedown",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature with flying you don't control."
)


INNKEEPER_S_TALENT = make_aura(
    name="Innkeeper's Talent",
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Class"},
    text="Enchant creature. Enchanted creature has '{T}: Add {G}.' Level 2 - {2}{G}: Enchanted creature gets +2/+2. Level 3 - {3}{G}: Whenever enchanted creature becomes tapped, create a Food token."
)


RETURN_FROM_THE_WILDS = make_sorcery(
    name="Return from the Wilds",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Create a Food token."
)


def royal_treatment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []

ROYAL_TREATMENT = make_instant(
    name="Royal Treatment",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gains hexproof and indestructible until end of turn. Create a Royal Role token attached to it."
)


def stormkeld_vanguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, put two +1/+1 counters on another creature you control"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'target': 'another_creature_you_control', 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

STORMKELD_VANGUARD = make_creature(
    name="Stormkeld Vanguard",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Warrior"},
    text="When Stormkeld Vanguard enters, put two +1/+1 counters on another target creature you control.",
    setup_interceptors=stormkeld_vanguard_setup
)


TOUGH_COOKIE = make_artifact_creature(
    name="Tough Cookie",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Food", "Golem"},
    text="When Tough Cookie enters, create a Food token. {2}{G}: Target noncreature artifact you control becomes a 4/4 artifact creature until end of turn."
)


UTOPIA_SPRAWL = make_aura(
    name="Utopia Sprawl",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchant Forest. As Utopia Sprawl enters, choose a color. Whenever enchanted Forest is tapped for mana, its controller adds an additional one mana of the chosen color."
)


VIRTUE_OF_STRENGTH = make_enchantment(
    name="Virtue of Strength",
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    text="Whenever you tap a land for mana, add an additional mana of any type that land produced. Adventure - Garenbrig Growth: {G} Sorcery - Target creature gets +2/+2 until end of turn."
)


WILD_WANDERER = make_creature(
    name="Wild Wanderer",
    power=3, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="When Wild Wanderer enters, you may search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

FAUNSBANE_TROLL = make_creature(
    name="Faunsbane Troll",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Troll"},
    text="When Faunsbane Troll enters, create a Monster Role token attached to it. Whenever Faunsbane Troll attacks, you may sacrifice an Aura attached to it. If you do, it deals damage equal to its power to target creature defending player controls."
)


FROLICKING_FAUNLINGS = make_creature(
    name="Frolicking Faunlings",
    power=4, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Faerie"},
    text="Trample. When Frolicking Faunlings enters, create a 1/1 green Faerie creature token with flying. Whenever a creature token you control dies, you gain 1 life."
)


def gingerbread_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Create a Food token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Food', 'types': {CardType.ARTIFACT}, 'subtypes': {'Food'}}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

GINGERBREAD_HUNTER = make_creature(
    name="Gingerbread Hunter",
    power=4, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Giant"},
    text="When Gingerbread Hunter enters, create a Food token. Adventure - Trail of Crumbs: {1}{G} Sorcery - Sacrifice a Food: Draw a card.",
    setup_interceptors=gingerbread_hunter_setup
)


NEVA_STALKED_BY_NIGHTMARES = make_creature(
    name="Neva, Stalked by Nightmares",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Whenever Neva or an enchantment you control is put into a graveyard from the battlefield, put a +1/+1 counter on each creature you control. {3}{W}{B}: Return Neva or target enchantment card from your graveyard to the battlefield."
)


RUBY_THE_BOLD_BEAUTY = make_creature(
    name="Ruby, the Bold Beauty",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Peasant"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Whenever you sacrifice an artifact or enchantment, draw a card. This ability triggers only once each turn."
)


def syr_ginger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hexproof from planeswalkers. Whenever an artifact you control is put into graveyard, +1/+1 counter"""
    def artifact_death_effect(event: Event, state: GameState) -> list[Event]:
        artifact_id = event.payload.get('object_id')
        artifact = state.objects.get(artifact_id)
        if (artifact and
            artifact.controller == obj.controller and
            CardType.ARTIFACT in artifact.characteristics.types and
            event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
            event.payload.get('to_zone_type') == ZoneType.GRAVEYARD):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        return []

    def artifact_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        artifact_id = event.payload.get('object_id')
        artifact = state.objects.get(artifact_id)
        return (artifact and
                artifact.controller == obj.controller and
                CardType.ARTIFACT in artifact.characteristics.types and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=artifact_death_effect(e, s)),
        duration='while_on_battlefield'
    )]

SYR_GINGER = make_creature(
    name="Syr Ginger, the Meal Ender",
    power=3, toughness=3,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Food", "Knight"},
    supertypes={"Legendary"},
    text="Hexproof from planeswalkers. Whenever an artifact you control is put into a graveyard from the battlefield, put a +1/+1 counter on Syr Ginger. {2}, {T}, Remove three +1/+1 counters: Destroy target planeswalker.",
    setup_interceptors=syr_ginger_setup
)


THE_GOOSE_MOTHER = make_creature(
    name="The Goose Mother",
    power=2, toughness=2,
    mana_cost="{X}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bird", "Hydra"},
    supertypes={"Legendary"},
    text="Flying. The Goose Mother enters with X +1/+1 counters. When it enters, create half X Food tokens. Whenever The Goose Mother attacks, you may sacrifice a Food. If you do, draw a card."
)


WITCHSTALKER = make_creature(
    name="Witchstalker",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="Hexproof. Whenever an opponent casts a blue or black spell during your turn, put a +1/+1 counter on Witchstalker."
)


# =============================================================================
# ARTIFACTS
# =============================================================================

CRYSTAL_SLIPPER = make_equipment(
    name="Crystal Slipper",
    mana_cost="{1}{R}",
    text="Equipped creature gets +1/+0 and has haste.",
    equip_cost="{1}"
)


ENCHANTED_CARRIAGE = make_artifact(
    name="Enchanted Carriage",
    mana_cost="{5}",
    text="When Enchanted Carriage enters, create two 1/1 white Mouse creature tokens. Crew 2. 4/4 Vehicle."
)


FOOD_TOKEN = make_artifact(
    name="Food Token",
    mana_cost="{0}",
    text="{2}, {T}, Sacrifice this artifact: You gain 3 life.",
    subtypes={"Food"}
)


GINGERBRUTE = make_artifact_creature(
    name="Gingerbrute",
    power=1, toughness=1,
    mana_cost="{1}",
    colors=set(),
    subtypes={"Food", "Golem"},
    text="Haste. Gingerbrute can't be blocked except by creatures with haste. {2}, {T}, Sacrifice Gingerbrute: You gain 3 life."
)


GLASS_CASKET = make_artifact(
    name="Glass Casket",
    mana_cost="{1}{W}",
    text="When Glass Casket enters, exile target creature an opponent controls with mana value 3 or less until Glass Casket leaves the battlefield."
)


GOLDEN_EGG = make_artifact(
    name="Golden Egg",
    mana_cost="{2}",
    text="When Golden Egg enters, draw a card. {1}, {T}, Sacrifice Golden Egg: Add one mana of any color. {2}, {T}, Sacrifice Golden Egg: You gain 3 life.",
    subtypes={"Food"}
)


PROPHETIC_PRISM = make_artifact(
    name="Prophetic Prism",
    mana_cost="{2}",
    text="When Prophetic Prism enters, draw a card. {1}, {T}: Add one mana of any color."
)


SPINNING_WHEEL = make_artifact(
    name="Spinning Wheel",
    mana_cost="{3}",
    text="{T}: Add one mana of any color. {5}, {T}: Tap target creature."
)


THE_IRENCRAG = make_artifact(
    name="The Irencrag",
    mana_cost="{2}",
    text="Legendary Artifact. {T}: Add {R}{R}. Spend this mana only to cast spells.",
    supertypes={"Legendary"}
)


WITCH_S_OVEN = make_artifact(
    name="Witch's Oven",
    mana_cost="{1}",
    text="{T}, Sacrifice a creature: Create a Food token. If the sacrificed creature's toughness was 4 or greater, create two Food tokens instead."
)


# =============================================================================
# ADDITIONAL WHITE CARDS
# =============================================================================

ASTONSHING_DISAPPEARANCE = make_instant(
    name="Astonishing Disappearance",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step."
)


CALL_TO_ARMS = make_sorcery(
    name="Call to Arms",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Create two 2/2 white Knight creature tokens with vigilance."
)


DAWN_S_TRUCE = make_instant(
    name="Dawn's Truce",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Prevent all combat damage that would be dealt this turn. Create a Food token."
)


EDGEWALL_PROTECTOR = make_creature(
    name="Edgewall Protector",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Vigilance. When Edgewall Protector enters, create a Young Hero Role token attached to target creature you control."
)


FAERIE_DREAMKEEPER = make_creature(
    name="Faerie Dreamkeeper",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Faerie"},
    text="Flying. {T}: Prevent the next 1 damage that would be dealt to any target this turn."
)


GALLANT_PIE_WIELDER = make_creature(
    name="Gallant Pie-Wielder",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="First strike. When Gallant Pie-Wielder enters, create a Food token."
)


NOBLE_KNIGHT_OF_ELDEN = make_creature(
    name="Noble Knight of Elden",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Lifelink. Whenever you cast an enchantment spell, Noble Knight of Elden gets +1/+1 until end of turn."
)


ROYAL_DECREE = make_enchantment(
    name="Royal Decree",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="At the beginning of your end step, create a 1/1 white Human creature token. Sacrifice Royal Decree if you control four or more creatures."
)


STEADFAST_UNICORN = make_creature(
    name="Steadfast Unicorn",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Unicorn"},
    text="Whenever a creature you control becomes enchanted, put a +1/+1 counter on Steadfast Unicorn."
)


TOWER_GUARD = make_creature(
    name="Tower Guard",
    power=1, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender, vigilance. {3}{W}: Tower Guard can attack this turn as though it didn't have defender."
)


# =============================================================================
# ADDITIONAL BLUE CARDS
# =============================================================================

BARGAIN_COLLECTOR = make_creature(
    name="Bargain Collector",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying. Whenever you sacrifice an artifact or enchantment, draw a card. This ability triggers only once each turn."
)


BEWITCHING_LEESE = make_aura(
    name="Bewitching Leese",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature. You control enchanted creature. At the beginning of your upkeep, enchanted creature's owner may pay {2}. If they do, destroy Bewitching Leese."
)


COUNTER_MAGIC = make_instant(
    name="Counter Magic",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell."
)


DREAMSHAPER_FAE = make_creature(
    name="Dreamshaper Fae",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash, flying. When Dreamshaper Fae enters, scry 2."
)


ILLUSORY_DUPLICANT = make_creature(
    name="Illusory Duplicant",
    power=0, toughness=0,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter"},
    text="You may have Illusory Duplicant enter as a copy of any creature on the battlefield, except it's an Illusion in addition to its other types."
)


MIST_DANCER = make_creature(
    name="Mist Dancer",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Dancer"},
    text="Flying. Whenever Mist Dancer attacks, target creature can't block this turn."
)


NYMPH_OF_LOCHTHWAIN = make_creature(
    name="Nymph of Locthwain",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Nymph"},
    text="When Nymph of Locthwain enters, draw a card, then discard a card."
)


PIXIE_ILLUSIONIST = make_creature(
    name="Pixie Illusionist",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying. {1}{U}: Target creature you control gains hexproof until end of turn."
)


RIVER_SERPENT = make_creature(
    name="River Serpent",
    power=5, toughness=5,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="River Serpent can't attack unless you control an Island. Cycling {2}"
)


THOUGHT_COLLECTOR = make_creature(
    name="Thought Collector",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying. Whenever you scry, you may pay {1}. If you do, draw a card."
)


# =============================================================================
# ADDITIONAL BLACK CARDS
# =============================================================================

BLIGHTED_AGENT = make_creature(
    name="Blighted Agent",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Deathtouch. When Blighted Agent deals combat damage to a player, that player discards a card."
)


CAULDRON_WITCH = make_creature(
    name="Cauldron Witch",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When Cauldron Witch enters, sacrifice a creature. If you do, draw two cards."
)


CURSE_BRINGER = make_creature(
    name="Curse Bringer",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When Curse Bringer enters, create a Cursed Role token attached to target creature an opponent controls."
)


DARK_BARGAIN = make_instant(
    name="Dark Bargain",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Look at the top three cards of your library. Put two of them into your hand and the other into your graveyard. You lose 2 life."
)


GRIM_BOUNTY = make_sorcery(
    name="Grim Bounty",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or planeswalker. Create a Treasure token."
)


HAGS_CACKLING = make_instant(
    name="Hag's Cackling",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. If a creature died this turn, it gets -4/-4 instead."
)


NIGHTMARE_SHEPHERD = make_creature(
    name="Nightmare Shepherd",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Flying. Whenever another nontoken creature you control dies, you may exile it. If you do, create a token that's a copy of that creature, except it's 1/1."
)


RAT_SWARM = make_creature(
    name="Rat Swarm",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="When Rat Swarm enters, create two 1/1 black Rat creature tokens with 'This creature can't block.'"
)


SINISTER_HEIRLOOM = make_artifact(
    name="Sinister Heirloom",
    mana_cost="{2}",
    text="Whenever a creature you control dies, put a soul counter on Sinister Heirloom. {3}, {T}, Remove three soul counters: Return target creature card from your graveyard to your hand."
)


WITCH_S_CURSE = make_aura(
    name="Witch's Curse",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature. Enchanted creature gets -2/-2. When enchanted creature dies, create a Food token."
)


# =============================================================================
# ADDITIONAL RED CARDS
# =============================================================================

BLAZING_VOLLEY = make_sorcery(
    name="Blazing Volley",
    mana_cost="{R}",
    colors={Color.RED},
    text="Blazing Volley deals 1 damage to each creature your opponents control."
)


DRAGON_WHIP = make_equipment(
    name="Dragon Whip",
    mana_cost="{1}{R}",
    text="Equipped creature gets +2/+1 and has first strike. {2}{R}: Dragon Whip becomes a 2/2 Dragon creature with flying and haste until end of turn.",
    equip_cost="{2}"
)


FIRE_JUGGLER = make_creature(
    name="Fire Juggler",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Performer"},
    text="When Fire Juggler enters, it deals 1 damage to any target."
)


GIANT_RAMPAGE = make_instant(
    name="Giant's Rampage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control gets +4/+0 and gains trample until end of turn."
)


GOBLIN_ARSONIST = make_creature(
    name="Goblin Arsonist",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="When Goblin Arsonist dies, you may have it deal 1 damage to any target."
)


KINDLED_FURY = make_instant(
    name="Kindled Fury",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +1/+0 and gains first strike until end of turn."
)


OGRE_BATTLEDRIVER = make_creature(
    name="Ogre Battledriver",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Ogre", "Warrior"},
    text="Whenever another creature enters the battlefield under your control, that creature gets +2/+0 and gains haste until end of turn."
)


RAGING_FIRE_BOLT = make_instant(
    name="Raging Fire Bolt",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Raging Fire Bolt deals 4 damage to target creature or planeswalker."
)


WILD_CELEBRANT = make_creature(
    name="Wild Celebrant",
    power=3, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Peasant"},
    text="Haste. Celebration - When Wild Celebrant enters, if two or more nonland permanents entered the battlefield under your control this turn, it deals 2 damage to any target."
)


RECKLESS_OGRE = make_creature(
    name="Reckless Ogre",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Ogre", "Warrior"},
    text="Haste. Reckless Ogre attacks each combat if able."
)


# =============================================================================
# ADDITIONAL GREEN CARDS
# =============================================================================

BEANSTALK_GIANT = make_creature(
    name="Beanstalk Giant",
    power=0, toughness=0,
    mana_cost="{6}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="Beanstalk Giant's power and toughness are each equal to the number of lands you control. Adventure - Fertile Footsteps: {2}{G} Sorcery - Search your library for a basic land card, put it onto the battlefield, then shuffle."
)


BEAST_TRAINER = make_creature(
    name="Beast Trainer",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="At the beginning of your end step, if a creature entered the battlefield under your control this turn, put a +1/+1 counter on Beast Trainer."
)


FERTILE_GROUND = make_aura(
    name="Fertile Ground",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchant land. Whenever enchanted land is tapped for mana, its controller adds an additional one mana of any color."
)


FIERCE_WITCHSTALKER = make_creature(
    name="Fierce Witchstalker",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="Trample. When Fierce Witchstalker enters, create a Food token."
)


GARENBRIG_PALADIN = make_creature(
    name="Garenbrig Paladin",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Knight"},
    text="Adamant - If at least three green mana was spent to cast this spell, Garenbrig Paladin enters with a +1/+1 counter on it. Garenbrig Paladin can't be blocked by creatures with power 2 or less."
)


GIFT_OF_THE_WOODS = make_instant(
    name="Gift of the Woods",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. Create a Monster Role token attached to it."
)


HOWLING_GIANT = make_creature(
    name="Howling Giant",
    power=5, toughness=4,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Druid"},
    text="Reach. When Howling Giant enters, create two 2/2 green Wolf creature tokens."
)


MOSS_VIA_TROLL = make_creature(
    name="Moss-Pit Skeleton",
    power=2, toughness=2,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Skeleton"},
    text="At the beginning of your upkeep, if there are four or more creature cards in your graveyard, you may return Moss-Pit Skeleton from your graveyard to your hand."
)


NATURE_S_LORE = make_sorcery(
    name="Nature's Lore",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Search your library for a Forest card, put that card onto the battlefield, then shuffle."
)


OUTMUSCLE = make_sorcery(
    name="Outmuscle",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control, then it fights target creature you don't control. Adamant - If at least three green mana was spent, the creature gains indestructible until end of turn."
)


# =============================================================================
# ADDITIONAL MULTICOLOR
# =============================================================================

AGATHA_S_CHAMPION = make_creature(
    name="Agatha's Champion",
    power=5, toughness=5,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Giant", "Warrior"},
    text="Trample. Whenever Agatha's Champion attacks, it gets +1/+1 for each activated ability of creatures you control."
)


DIMIR_CUTPURSE = make_creature(
    name="Dimir Cutpurse",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Spirit"},
    text="Whenever Dimir Cutpurse deals combat damage to a player, that player discards a card and you draw a card."
)


ENCHANTRESS_OF_THE_WILDS = make_creature(
    name="Enchantress of the Wilds",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Druid"},
    text="Whenever you cast an enchantment spell, draw a card."
)


KNIGHT_OF_TWO_COURTS = make_creature(
    name="Knight of Two Courts",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Faerie", "Knight"},
    text="Flying, vigilance. When Knight of Two Courts enters, create a Royal Role token attached to target creature you control."
)


QUESTING_BEAST = make_creature(
    name="Questing Beast",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    supertypes={"Legendary"},
    text="Vigilance, deathtouch, haste. Questing Beast can't be blocked by creatures with power 2 or less. Combat damage that would be dealt by creatures you control can't be prevented. Whenever Questing Beast deals combat damage to an opponent, it deals that much damage to target planeswalker that player controls."
)


RESTLESS_APPARITION = make_creature(
    name="Restless Apparition",
    power=2, toughness=2,
    mana_cost="{W/B}{W/B}{W/B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Spirit"},
    text="Flying. Persist. {W/B}{W/B}{W/B}: Restless Apparition gets +3/+3 until end of turn."
)


SELESNYA_LOCKET = make_artifact(
    name="Selesnya Locket",
    mana_cost="{3}",
    text="{T}: Add {G} or {W}. {G/W}{G/W}{G/W}{G/W}, {T}, Sacrifice Selesnya Locket: Draw two cards."
)


WILDBORN_PRESERVER = make_creature(
    name="Wildborn Preserver",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Archer"},
    text="Flash, reach. Whenever another non-Human creature enters the battlefield under your control, you may pay {X}. When you do, put X +1/+1 counters on Wildborn Preserver."
)


# =============================================================================
# ADDITIONAL ARTIFACTS
# =============================================================================

CAULDRON_FAMILIAR = make_creature(
    name="Cauldron Familiar",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Cat"},
    text="When Cauldron Familiar enters, each opponent loses 1 life and you gain 1 life. Sacrifice a Food: Return Cauldron Familiar from your graveyard to the battlefield."
)


CLOCKWORK_AUTOMATON = make_artifact_creature(
    name="Clockwork Automaton",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct"},
    text="When Clockwork Automaton enters, put two charge counters on it. Remove a charge counter from Clockwork Automaton: It gains vigilance until end of turn."
)


ENCHANTED_MIRROR = make_artifact(
    name="Enchanted Mirror",
    mana_cost="{3}",
    text="{T}: Add one mana of any color. {3}, {T}: Scry 1."
)


GOLEM_FOUNDRY = make_artifact(
    name="Golem Foundry",
    mana_cost="{3}",
    text="Whenever you cast an artifact spell, you may put a charge counter on Golem Foundry. Remove three charge counters from Golem Foundry: Create a 3/3 colorless Golem artifact creature token."
)


HERALDIC_BANNER = make_artifact(
    name="Heraldic Banner",
    mana_cost="{3}",
    text="As Heraldic Banner enters, choose a color. Creatures you control of the chosen color get +1/+0. {T}: Add one mana of the chosen color."
)


LUCKY_CLOVER = make_artifact(
    name="Lucky Clover",
    mana_cost="{2}",
    text="Whenever you cast an Adventure instant or sorcery spell, copy it. You may choose new targets for the copy."
)


MAGIC_MIRROR = make_artifact(
    name="Magic Mirror",
    mana_cost="{6}{U}{U}{U}",
    text="This spell costs {1} less to cast for each instant and sorcery card in your graveyard. You have no maximum hand size. At the beginning of your upkeep, put a knowledge counter on Magic Mirror, then draw a card for each knowledge counter on it.",
    supertypes={"Legendary"}
)


ROWAN_S_BATTLEGUARD = make_artifact_creature(
    name="Rowan's Battleguard",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Knight"},
    text="First strike. As long as you control a Rowan planeswalker, Rowan's Battleguard gets +3/+0."
)


SORCERERS_BROOM = make_artifact_creature(
    name="Sorcerer's Broom",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Spirit"},
    text="Whenever you sacrifice another permanent, you may pay {3}. If you do, create a token that's a copy of Sorcerer's Broom."
)


WILL_S_VANGUARD = make_artifact_creature(
    name="Will's Vanguard",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Knight"},
    text="Vigilance. As long as you control a Will planeswalker, Will's Vanguard gets +2/+0 and has flying."
)


# =============================================================================
# ADDITIONAL COMMONS/UNCOMMONS
# =============================================================================

WISHING_WELL = make_artifact(
    name="Wishing Well",
    mana_cost="{2}",
    text="{1}, {T}: Scry 1. {5}, {T}: Draw a card."
)


EDGEWALL_INNKEEPER = make_creature(
    name="Edgewall Innkeeper",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Peasant"},
    text="Whenever you cast a creature spell that has an Adventure, draw a card."
)


MURDEROUS_RIDER = make_creature(
    name="Murderous Rider",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Knight"},
    text="Lifelink. When Murderous Rider dies, put it on the bottom of its owner's library. Adventure - Swift End: {1}{B}{B} Instant - Destroy target creature or planeswalker. You lose 2 life."
)


BONECRUSHER_GIANT = make_creature(
    name="Bonecrusher Giant",
    power=4, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Whenever Bonecrusher Giant becomes the target of a spell, Bonecrusher Giant deals 2 damage to that spell's controller. Adventure - Stomp: {1}{R} Instant - Damage can't be prevented this turn. Stomp deals 2 damage to any target."
)


BRAZEN_BORROWER = make_creature(
    name="Brazen Borrower",
    power=3, toughness=1,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flash, flying. Brazen Borrower can block only creatures with flying. Adventure - Petty Theft: {1}{U} Instant - Return target nonland permanent an opponent controls to its owner's hand."
)


LOVESTRUCK_BEAST = make_creature(
    name="Lovestruck Beast",
    power=5, toughness=5,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Noble"},
    text="Lovestruck Beast can't attack unless you control a 1/1 creature. Adventure - Heart's Desire: {G} Sorcery - Create a 1/1 white Human creature token."
)


REALM_CLOAKED_GIANT = make_creature(
    name="Realm-Cloaked Giant",
    power=7, toughness=7,
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Giant"},
    text="Vigilance. Adventure - Cast Off: {3}{W}{W} Sorcery - Destroy all non-Giant creatures."
)


ONCE_UPON_A_TIME = make_instant(
    name="Once Upon a Time",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="If this spell is the first spell you've cast this game, you may cast it without paying its mana cost. Look at the top five cards of your library. You may reveal a creature or land card from among them and put it into your hand. Put the rest on the bottom in a random order."
)


THE_GREAT_HENGE = make_artifact(
    name="The Great Henge",
    mana_cost="{7}{G}{G}",
    text="This spell costs {X} less to cast, where X is the greatest power among creatures you control. {T}: Add {G}{G}. You gain 2 life. Whenever a nontoken creature enters the battlefield under your control, put a +1/+1 counter on it and draw a card.",
    supertypes={"Legendary"}
)


EMBERCLEAVE = make_equipment(
    name="Embercleave",
    mana_cost="{4}{R}{R}",
    text="Flash. This spell costs {1} less to cast for each attacking creature you control. When Embercleave enters, attach it to target creature you control. Equipped creature gets +1/+1 and has double strike and trample.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)


DOOM_FORETOLD = make_enchantment(
    name="Doom Foretold",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="At the beginning of each player's upkeep, that player sacrifices a nonland, nontoken permanent. If they can't, they discard a card, lose 2 life, you draw a card, gain 2 life, and create a 2/2 white Knight creature token. Then sacrifice Doom Foretold."
)


YORION_SKY_NOMAD = make_creature(
    name="Yorion, Sky Nomad",
    power=4, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Bird", "Serpent"},
    supertypes={"Legendary"},
    text="Companion - Your starting deck contains at least twenty cards more than the minimum. Flying. When Yorion enters, exile any number of other nonland permanents you own and control. Return them at the beginning of the next end step."
)


FABLED_PASSAGE = make_land(
    name="Fabled Passage",
    text="{T}, Sacrifice Fabled Passage: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control four or more lands, untap that land."
)


MYSTIC_SANCTUARY = make_land(
    name="Mystic Sanctuary",
    text="Mystic Sanctuary enters tapped unless you control three or more other Islands. When Mystic Sanctuary enters untapped, you may put target instant or sorcery card from your graveyard on top of your library.",
    subtypes={"Island"}
)


WITCH_S_COTTAGE = make_land(
    name="Witch's Cottage",
    text="Witch's Cottage enters tapped unless you control three or more other Swamps. When Witch's Cottage enters untapped, you may put target creature card from your graveyard on top of your library.",
    subtypes={"Swamp"}
)


DWARVEN_MINE = make_land(
    name="Dwarven Mine",
    text="Dwarven Mine enters tapped unless you control three or more other Mountains. When Dwarven Mine enters untapped, create a 1/1 red Dwarf creature token.",
    subtypes={"Mountain"}
)


GINGERBREAD_CABIN = make_land(
    name="Gingerbread Cabin",
    text="Gingerbread Cabin enters tapped unless you control three or more other Forests. When Gingerbread Cabin enters untapped, create a Food token.",
    subtypes={"Forest"}
)


# =============================================================================
# ENCHANTING TALES - BONUS SHEET
# =============================================================================

ANIMATE_DEAD = make_aura(
    name="Animate Dead",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature card in a graveyard. When Animate Dead enters, return enchanted creature card to the battlefield under your control. It gets -1/-0. When Animate Dead leaves the battlefield, destroy that creature."
)


BITTERBLOSSOM = CardDefinition(
    name="Bitterblossom",
    mana_cost="{1}{B}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Tribal", "Faerie"},
        colors={Color.BLACK},
        mana_cost="{1}{B}"
    ),
    text="At the beginning of your upkeep, you lose 1 life and create a 1/1 black Faerie Rogue creature token with flying."
)


BLOOD_MOON = make_enchantment(
    name="Blood Moon",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Nonbasic lands are Mountains."
)


DOUBLING_SEASON = make_enchantment(
    name="Doubling Season",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead. If an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead."
)


GREATER_AURAMANCY = make_enchantment(
    name="Greater Auramancy",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchantments you control have shroud. Enchanted creatures you control have shroud."
)


INTANGIBLE_VIRTUE = make_enchantment(
    name="Intangible Virtue",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creature tokens you control get +1/+1 and have vigilance."
)


LAND_TAX = make_enchantment(
    name="Land Tax",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="At the beginning of your upkeep, if an opponent controls more lands than you, you may search your library for up to three basic land cards, reveal them, put them into your hand, then shuffle."
)


NECROPOTENCE = make_enchantment(
    name="Necropotence",
    mana_cost="{B}{B}{B}",
    colors={Color.BLACK},
    text="Skip your draw step. Whenever you discard a card, exile that card. Pay 1 life: Exile the top card of your library face down. At the beginning of your end step, put that card into your hand."
)


OMNISCIENCE = make_enchantment(
    name="Omniscience",
    mana_cost="{7}{U}{U}{U}",
    colors={Color.BLUE},
    text="You may cast spells from your hand without paying their mana costs."
)


PARALLEL_LIVES = make_enchantment(
    name="Parallel Lives",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead."
)


PRISMATIC_OMEN = make_enchantment(
    name="Prismatic Omen",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Lands you control are every basic land type in addition to their other types."
)


PROTECTION_OF_THE_HEKMA = make_enchantment(
    name="Protection of the Hekma",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="If a source an opponent controls would deal damage to you, prevent 1 of that damage."
)


RHYSTIC_STUDY = make_enchantment(
    name="Rhystic Study",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever an opponent casts a spell, you may draw a card unless that player pays {1}."
)


REST_IN_PEACE = make_enchantment(
    name="Rest in Peace",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When Rest in Peace enters, exile all graveyards. If a card or token would be put into a graveyard from anywhere, exile it instead."
)


SMOTHERING_TITHE = make_enchantment(
    name="Smothering Tithe",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Whenever an opponent draws a card, that player may pay {2}. If the player doesn't, you create a Treasure token."
)


SNEAK_ATTACK = make_enchantment(
    name="Sneak Attack",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="{R}: You may put a creature card from your hand onto the battlefield. That creature gains haste. Sacrifice it at the beginning of the next end step."
)


SPREADING_SEAS = make_aura(
    name="Spreading Seas",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant land. When Spreading Seas enters, draw a card. Enchanted land is an Island."
)


STONY_SILENCE = make_enchantment(
    name="Stony Silence",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Activated abilities of artifacts can't be activated."
)


SULFURIC_VORTEX = make_enchantment(
    name="Sulfuric Vortex",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="At the beginning of each player's upkeep, Sulfuric Vortex deals 2 damage to that player. If a player would gain life, that player gains no life instead."
)


SURVIVAL_OF_THE_FITTEST = make_enchantment(
    name="Survival of the Fittest",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="{G}, Discard a creature card: Search your library for a creature card, reveal it, put it into your hand, then shuffle."
)


# =============================================================================
# LANDS
# =============================================================================

CASTLE_ARDENVALE = make_land(
    name="Castle Ardenvale",
    text="Castle Ardenvale enters tapped unless you control a Plains. {T}: Add {W}. {2}{W}{W}, {T}: Create a 1/1 white Human creature token."
)


CASTLE_EMBERETH = make_land(
    name="Castle Embereth",
    text="Castle Embereth enters tapped unless you control a Mountain. {T}: Add {R}. {1}{R}{R}, {T}: Creatures you control get +1/+0 until end of turn."
)


CASTLE_GARENBRIG = make_land(
    name="Castle Garenbrig",
    text="Castle Garenbrig enters tapped unless you control a Forest. {T}: Add {G}. {2}{G}{G}, {T}: Add six {G}. Spend this mana only to cast creature spells or activate abilities of creatures."
)


CASTLE_LOCTHWAIN = make_land(
    name="Castle Locthwain",
    text="Castle Locthwain enters tapped unless you control a Swamp. {T}: Add {B}. {1}{B}{B}, {T}: Draw a card, then you lose life equal to the number of cards in your hand."
)


CASTLE_VANTRESS = make_land(
    name="Castle Vantress",
    text="Castle Vantress enters tapped unless you control an Island. {T}: Add {U}. {2}{U}{U}, {T}: Scry 2."
)


EDGEWALL_INNKEEPER_VILLAGE = make_land(
    name="Edgewall Innkeeper's Village",
    text="{T}: Add {C}. {T}, Pay 1 life: Add one mana of any color."
)


RESTLESS_COTTAGE = make_land(
    name="Restless Cottage",
    text="Restless Cottage enters tapped. {T}: Add {B} or {G}. {2}{B}{G}: Until end of turn, Restless Cottage becomes a 4/4 black and green Horror creature with menace and 'Whenever this creature attacks, create a Food token.' It's still a land."
)


RESTLESS_FORTRESS = make_land(
    name="Restless Fortress",
    text="Restless Fortress enters tapped. {T}: Add {W} or {B}. {2}{W}{B}: Until end of turn, Restless Fortress becomes a 1/4 white and black Gargoyle creature with flying. It's still a land."
)


RESTLESS_SPIRE = make_land(
    name="Restless Spire",
    text="Restless Spire enters tapped. {T}: Add {U} or {R}. {1}{U}{R}: Until end of turn, Restless Spire becomes a 2/1 blue and red Elemental creature with first strike and haste. It's still a land."
)


RESTLESS_VINESTALK = make_land(
    name="Restless Vinestalk",
    text="Restless Vinestalk enters tapped. {T}: Add {G} or {U}. {1}{G}{U}: Until end of turn, Restless Vinestalk becomes a 5/5 green and blue Plant Elemental creature. It's still a land. Whenever Restless Vinestalk attacks, another target land you control becomes a 3/3 Elemental creature with haste until end of turn."
)


# Basic Lands
PLAINS_WOE = make_land(name="Plains", text="{T}: Add {W}.", subtypes={"Plains"}, supertypes={"Basic"})
ISLAND_WOE = make_land(name="Island", text="{T}: Add {U}.", subtypes={"Island"}, supertypes={"Basic"})
SWAMP_WOE = make_land(name="Swamp", text="{T}: Add {B}.", subtypes={"Swamp"}, supertypes={"Basic"})
MOUNTAIN_WOE = make_land(name="Mountain", text="{T}: Add {R}.", subtypes={"Mountain"}, supertypes={"Basic"})
FOREST_WOE = make_land(name="Forest", text="{T}: Add {G}.", subtypes={"Forest"}, supertypes={"Basic"})


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

WILDS_OF_ELDRAINE_CARDS = {
    # WHITE LEGENDARIES
    "Kellan, the Fae-Blooded": KELLAN_THE_FAE_BLOODED,
    "Eriette of the Charmed Apple": ERIETTE_OF_THE_CHARMED_APPLE,
    "Imodane, the Pyrohammer": IMODANE_THE_PYROHAMMER,
    "Moonshaker Cavalry": MOONSHAKER_CAVALRY,

    # WHITE CREATURES
    "Archon of the Wild Rose": ARCHON_OF_THE_WILD_ROSE,
    "Armored Armadillo": ARMORED_ARMADILLO,
    "Besotted Knight": BESOTTED_KNIGHT,
    "Charmed Clothier": CHARMED_CLOTHIER,
    "Cursed Courtier": CURSED_COURTIER,
    "Dutiful Griffin": DUTIFUL_GRIFFIN,
    "Faerie Guidemother": FAERIE_GUIDEMOTHER,
    "Grand Ball Guest": GRAND_BALL_GUEST,
    "Knight of Doves": KNIGHT_OF_DOVES,
    "Regal Bunnicorn": REGAL_BUNNICORN,
    "Stockpiling Celebrant": STOCKPILING_CELEBRANT,
    "Werefox Bodyguard": WEREFOX_BODYGUARD,
    "Kellan, Daring Traveler": KELLAN_DARING_TRAVELER,

    # WHITE SPELLS
    "Break the Spell": BREAK_THE_SPELL,
    "Cooped Up": COOPED_UP,
    "Hopeful Vigil": HOPEFUL_VIGIL,
    "Plunge into Winter": PLUNGE_INTO_WINTER,
    "Witch's Defiance": WITCH_DEFIANCE,

    # BLUE LEGENDARIES
    "Talion, the Kindly Lord": TALION_THE_KINDLY_LORD,
    "Hylda of the Icy Crown": HYLDA_OF_THE_ICY_CROWN,
    "Horned Loch-Whale": HORNED_LOCH_WHALE,
    "Gadwick, the Wizened": GADWICK_THE_WIZENED,
    "Johann, Apprentice Sorcerer": Johann_APPRENTICE_SORCERER,
    "Obyra, Dreaming Duelist": OBYRA_DREAMING_DUELIST,

    # BLUE CREATURES
    "Aquatic Alchemist": AQUATIC_ALCHEMIST,
    "Frolicking Familiar": FROLICKING_FAMILIAR,
    "Malkavian Jester": MALKAVIAN_JESTER,
    "Merfolk Coralsmith": MERFOLK_CORALSMITH,
    "Snaremaster Sprite": SNAREMASTER_SPRITE,
    "Tempest Hart": TEMPEST_HART,

    # BLUE SPELLS
    "Faerie Fencing": FAERIE_FENCING,
    "Ice Out": ICE_OUT,
    "Misleading Motes": MISLEADING_MOTES,
    "Quick Study": QUICK_STUDY,
    "Sleight of Hand": SLEIGHT_OF_HAND,
    "Spell Stutter": SPELL_STUTTER,
    "Succumb to the Cold": SUCCUMB_TO_THE_COLD,
    "Water Wings": WATER_WINGS,

    # BLACK LEGENDARIES
    "Rankle, Master of Pranks": RANKLE_MASTER_OF_PRANKS,
    "Ashiok, Wicked Manipulator": ASHIOK_WICKED_MANIPULATOR,
    "Lord Skitter, Sewer King": LORD_SKITTER_SEWER_KING,
    "Lord of the Pit": LORD_OF_THE_PIT,

    # BLACK CREATURES
    "Barrow Naughty": BARROW_NAUGHTY,
    "Conceited Witch": CONCEITED_WITCH,
    "Cruel Somnophage": CRUEL_SOMNOPHAGE,
    "Faerie Dreamthief": FAERIE_DREAMTHIEF,
    "Gumdrop Poisoner": GUMDROP_POISONER,
    "High Faeborn": HIGH_FAEBORN,
    "Mintstrosity": MINTSTROSITY,
    "Ratcatcher Trainee": RATCATCHER_TRAINEE,
    "Scream Puff": SCREAM_PUFF,
    "Specter of Mortality": SPECTER_OF_MORTALITY,
    "Stingblade Assassin": STINGBLADE_ASSASSIN,
    "Wicked Visitor": WICKED_VISITOR,

    # BLACK SPELLS
    "Back for Seconds": BACK_FOR_SECONDS,
    "Candy Trail": CANDY_TRAIL,
    "Duress": DURESS,
    "Emergency Call-Up": EMERGENCY_CALL_UP,
    "Feed the Cauldron": FEED_THE_CAULDRON,
    "Festive Funeral": FESTIVE_FUNERAL,
    "Shatter the Oath": SHATTER_THE_OATH,
    "Taken by Nightmares": TAKEN_BY_NIGHTMARES,
    "The End": THE_END,
    "The Witch's Vanity": THE_WITCH_S_VANITY,
    "Virtue of Persistence": VIRTUE_OF_PERSISTENCE,

    # RED LEGENDARIES
    "Rowan, Scion of War": ROWAN_SCION_OF_WAR,
    "Will, Scion of Peace": WILL_SCION_OF_PEACE,
    "Goddric, Cloaked Reveler": GODDRIC_CLOAKED_REVELER,
    "Agatha of the Vile Cauldron": AGATHA_OF_THE_VILE_CAULDRON,
    "Rowan, Soulfire Grand Master": ROWAN_SOULFIRE,

    # RED CREATURES
    "Boundary Lands Ranger": BOUNDARY_LANDS_RANGER,
    "Broom Rider": BROOM_RIDER,
    "Cheeky House-Mouse": CHEEKY_HOUSE_MOUSE,
    "Crossbow Marksman": CROSSBOW_MARKSMAN,
    "Edgewall Pack": EDGEWALL_PACK,
    "Embereth Veteran": EMBERETH_VETERAN,
    "Frenzied Golem": FRENZIED_GOLEM,
    "Harried Spearguard": HARRIED_SPEARGUARD,
    "Redcap Gutter-Dweller": REDCAP_GUTTER_DWELLER,

    # RED SPELLS
    "Archery Training": ARCHERY_TRAINING,
    "Dragon Mantle": DRAGON_MANTLE,
    "Flamebreaker": FLAMEBREAKER,
    "Monstrous Rage": MONSTROUS_RAGE,
    "Ratty Feast": RATTY_FEAST,
    "Stonesplitter Bolt": STONESPLITTER_BOLT,
    "Torch the Tower": TORCH_THE_TOWER,
    "Virtue of Courage": VIRTUE_OF_COURAGE,
    "Witchstalker Frenzy": WITCHSTALKER_FRENZY,

    # GREEN LEGENDARIES
    "Questing Druid": QUESTING_DRUID,
    "Troyan, Gutsy Explorer": TROYAN_GUTSY_EXPLORER,
    "Greta, Sweettooth Scourge": GRETA_SWEETTOOTH_SCOURGE,
    "Old Flitterbark": OLD_FLITTERBARK,

    # GREEN CREATURES
    "Beanstalk Wurm": BEANSTALK_WURM,
    "Ferocious Werefox": FEROCIOUS_WEREFOX,
    "Forest Guardian": FOREST_GUARDIAN,
    "Giant Killer": GIANT_KILLER,
    "Gruff Triplets": GRUFF_TRIPLETS,
    "Stormkeld Vanguard": STORMKELD_VANGUARD,
    "Tough Cookie": TOUGH_COOKIE,
    "Wild Wanderer": WILD_WANDERER,
    "Witchstalker": WITCHSTALKER,

    # GREEN SPELLS
    "Curse of Leeches": CURSE_OF_LEECHES,
    "Graceful Takedown": GRACEFUL_TAKEDOWN,
    "Innkeeper's Talent": INNKEEPER_S_TALENT,
    "Return from the Wilds": RETURN_FROM_THE_WILDS,
    "Royal Treatment": ROYAL_TREATMENT,
    "Utopia Sprawl": UTOPIA_SPRAWL,
    "Virtue of Strength": VIRTUE_OF_STRENGTH,

    # MULTICOLOR
    "Faunsbane Troll": FAUNSBANE_TROLL,
    "Frolicking Faunlings": FROLICKING_FAUNLINGS,
    "Gingerbread Hunter": GINGERBREAD_HUNTER,
    "Neva, Stalked by Nightmares": NEVA_STALKED_BY_NIGHTMARES,
    "Ruby, the Bold Beauty": RUBY_THE_BOLD_BEAUTY,
    "Syr Ginger, the Meal Ender": SYR_GINGER,
    "The Goose Mother": THE_GOOSE_MOTHER,
    "Elf, Voracious Reader": ELF_VORACIOUS_READER,

    # ARTIFACTS
    "Crystal Slipper": CRYSTAL_SLIPPER,
    "Enchanted Carriage": ENCHANTED_CARRIAGE,
    "Food Token": FOOD_TOKEN,
    "Gingerbrute": GINGERBRUTE,
    "Glass Casket": GLASS_CASKET,
    "Golden Egg": GOLDEN_EGG,
    "Prophetic Prism": PROPHETIC_PRISM,
    "Spinning Wheel": SPINNING_WHEEL,
    "The Irencrag": THE_IRENCRAG,
    "Witch's Oven": WITCH_S_OVEN,

    # ENCHANTING TALES - BONUS SHEET
    "Animate Dead": ANIMATE_DEAD,
    "Bitterblossom": BITTERBLOSSOM,
    "Blood Moon": BLOOD_MOON,
    "Doubling Season": DOUBLING_SEASON,
    "Greater Auramancy": GREATER_AURAMANCY,
    "Intangible Virtue": INTANGIBLE_VIRTUE,
    "Land Tax": LAND_TAX,
    "Necropotence": NECROPOTENCE,
    "Omniscience": OMNISCIENCE,
    "Parallel Lives": PARALLEL_LIVES,
    "Prismatic Omen": PRISMATIC_OMEN,
    "Protection of the Hekma": PROTECTION_OF_THE_HEKMA,
    "Rest in Peace": REST_IN_PEACE,
    "Rhystic Study": RHYSTIC_STUDY,
    "Smothering Tithe": SMOTHERING_TITHE,
    "Sneak Attack": SNEAK_ATTACK,
    "Spreading Seas": SPREADING_SEAS,
    "Stony Silence": STONY_SILENCE,
    "Sulfuric Vortex": SULFURIC_VORTEX,
    "Survival of the Fittest": SURVIVAL_OF_THE_FITTEST,

    # LANDS
    "Castle Ardenvale": CASTLE_ARDENVALE,
    "Castle Embereth": CASTLE_EMBERETH,
    "Castle Garenbrig": CASTLE_GARENBRIG,
    "Castle Locthwain": CASTLE_LOCTHWAIN,
    "Castle Vantress": CASTLE_VANTRESS,
    "Edgewall Innkeeper's Village": EDGEWALL_INNKEEPER_VILLAGE,
    "Restless Cottage": RESTLESS_COTTAGE,
    "Restless Fortress": RESTLESS_FORTRESS,
    "Restless Spire": RESTLESS_SPIRE,
    "Restless Vinestalk": RESTLESS_VINESTALK,

    # BASIC LANDS
    "Plains": PLAINS_WOE,
    "Island": ISLAND_WOE,
    "Swamp": SWAMP_WOE,
    "Mountain": MOUNTAIN_WOE,
    "Forest": FOREST_WOE,

    # ADDITIONAL WHITE
    "Astonishing Disappearance": ASTONSHING_DISAPPEARANCE,
    "Call to Arms": CALL_TO_ARMS,
    "Dawn's Truce": DAWN_S_TRUCE,
    "Edgewall Protector": EDGEWALL_PROTECTOR,
    "Faerie Dreamkeeper": FAERIE_DREAMKEEPER,
    "Gallant Pie-Wielder": GALLANT_PIE_WIELDER,
    "Noble Knight of Elden": NOBLE_KNIGHT_OF_ELDEN,
    "Royal Decree": ROYAL_DECREE,
    "Steadfast Unicorn": STEADFAST_UNICORN,
    "Tower Guard": TOWER_GUARD,

    # ADDITIONAL BLUE
    "Bargain Collector": BARGAIN_COLLECTOR,
    "Bewitching Leese": BEWITCHING_LEESE,
    "Counter Magic": COUNTER_MAGIC,
    "Dreamshaper Fae": DREAMSHAPER_FAE,
    "Illusory Duplicant": ILLUSORY_DUPLICANT,
    "Mist Dancer": MIST_DANCER,
    "Nymph of Locthwain": NYMPH_OF_LOCHTHWAIN,
    "Pixie Illusionist": PIXIE_ILLUSIONIST,
    "River Serpent": RIVER_SERPENT,
    "Thought Collector": THOUGHT_COLLECTOR,

    # ADDITIONAL BLACK
    "Blighted Agent": BLIGHTED_AGENT,
    "Cauldron Witch": CAULDRON_WITCH,
    "Curse Bringer": CURSE_BRINGER,
    "Dark Bargain": DARK_BARGAIN,
    "Grim Bounty": GRIM_BOUNTY,
    "Hag's Cackling": HAGS_CACKLING,
    "Nightmare Shepherd": NIGHTMARE_SHEPHERD,
    "Rat Swarm": RAT_SWARM,
    "Sinister Heirloom": SINISTER_HEIRLOOM,
    "Witch's Curse": WITCH_S_CURSE,

    # ADDITIONAL RED
    "Blazing Volley": BLAZING_VOLLEY,
    "Dragon Whip": DRAGON_WHIP,
    "Fire Juggler": FIRE_JUGGLER,
    "Giant's Rampage": GIANT_RAMPAGE,
    "Goblin Arsonist": GOBLIN_ARSONIST,
    "Kindled Fury": KINDLED_FURY,
    "Ogre Battledriver": OGRE_BATTLEDRIVER,
    "Raging Fire Bolt": RAGING_FIRE_BOLT,
    "Wild Celebrant": WILD_CELEBRANT,
    "Reckless Ogre": RECKLESS_OGRE,

    # ADDITIONAL GREEN
    "Beanstalk Giant": BEANSTALK_GIANT,
    "Beast Trainer": BEAST_TRAINER,
    "Fertile Ground": FERTILE_GROUND,
    "Fierce Witchstalker": FIERCE_WITCHSTALKER,
    "Garenbrig Paladin": GARENBRIG_PALADIN,
    "Gift of the Woods": GIFT_OF_THE_WOODS,
    "Howling Giant": HOWLING_GIANT,
    "Moss-Pit Skeleton": MOSS_VIA_TROLL,
    "Nature's Lore": NATURE_S_LORE,
    "Outmuscle": OUTMUSCLE,

    # ADDITIONAL MULTICOLOR
    "Agatha's Champion": AGATHA_S_CHAMPION,
    "Dimir Cutpurse": DIMIR_CUTPURSE,
    "Enchantress of the Wilds": ENCHANTRESS_OF_THE_WILDS,
    "Knight of Two Courts": KNIGHT_OF_TWO_COURTS,
    "Questing Beast": QUESTING_BEAST,
    "Restless Apparition": RESTLESS_APPARITION,
    "Selesnya Locket": SELESNYA_LOCKET,
    "Wildborn Preserver": WILDBORN_PRESERVER,

    # ADDITIONAL ARTIFACTS
    "Cauldron Familiar": CAULDRON_FAMILIAR,
    "Clockwork Automaton": CLOCKWORK_AUTOMATON,
    "Enchanted Mirror": ENCHANTED_MIRROR,
    "Golem Foundry": GOLEM_FOUNDRY,
    "Heraldic Banner": HERALDIC_BANNER,
    "Lucky Clover": LUCKY_CLOVER,
    "Magic Mirror": MAGIC_MIRROR,
    "Rowan's Battleguard": ROWAN_S_BATTLEGUARD,
    "Sorcerer's Broom": SORCERERS_BROOM,
    "Will's Vanguard": WILL_S_VANGUARD,

    # ADDITIONAL COMMONS/UNCOMMONS
    "Wishing Well": WISHING_WELL,
    "Edgewall Innkeeper": EDGEWALL_INNKEEPER,
    "Murderous Rider": MURDEROUS_RIDER,
    "Bonecrusher Giant": BONECRUSHER_GIANT,
    "Brazen Borrower": BRAZEN_BORROWER,
    "Lovestruck Beast": LOVESTRUCK_BEAST,
    "Realm-Cloaked Giant": REALM_CLOAKED_GIANT,
    "Once Upon a Time": ONCE_UPON_A_TIME,
    "The Great Henge": THE_GREAT_HENGE,
    "Embercleave": EMBERCLEAVE,
    "Doom Foretold": DOOM_FORETOLD,
    "Yorion, Sky Nomad": YORION_SKY_NOMAD,
    "Fabled Passage": FABLED_PASSAGE,
    "Mystic Sanctuary": MYSTIC_SANCTUARY,
    "Witch's Cottage": WITCH_S_COTTAGE,
    "Dwarven Mine": DWARVEN_MINE,
    "Gingerbread Cabin": GINGERBREAD_CABIN,
}

print(f"Loaded {len(WILDS_OF_ELDRAINE_CARDS)} Wilds of Eldraine cards")
