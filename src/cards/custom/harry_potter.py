"""
Harry Potter: Wizarding World (HPW) Card Implementations

~250 cards featuring the Wizarding World.
Mechanics: Spell Mastery, House, Patronus
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
# HARRY POTTER KEYWORD MECHANICS
# =============================================================================

def count_instants_sorceries_cast(state: GameState, controller: str) -> int:
    """Count instants/sorceries cast this game by controller."""
    return state.players.get(controller, {}).get('spells_cast_this_game', 0)


def has_spell_mastery(state: GameState, controller: str) -> bool:
    """Check if controller has Spell Mastery (3+ instants/sorceries cast this game)."""
    return count_instants_sorceries_cast(state, controller) >= 3


def make_spell_mastery_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """Spell Mastery - Gets +X/+Y if you've cast 3+ instants/sorceries this game."""
    def mastery_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return has_spell_mastery(state, source_obj.controller)
    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, mastery_filter)


def make_house_bonus(source_obj: GameObject, house: str, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """House - Gets +X/+Y for each other creature you control with the same house subtype."""
    def house_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        count = sum(1 for obj in state.objects.values()
                   if obj.id != source_obj.id
                   and obj.controller == source_obj.controller
                   and CardType.CREATURE in obj.characteristics.types
                   and house in obj.characteristics.subtypes
                   and obj.zone == ZoneType.BATTLEFIELD)
        return count > 0
    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, house_filter)


def make_patronus_token(controller: str, source_id: str, creature_type: str = "Spirit") -> Event:
    """Create a Patronus token - 2/2 white Spirit with flying and protection from black."""
    return Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': controller,
            'token': {
                'name': f'Patronus {creature_type}',
                'power': 2,
                'toughness': 2,
                'colors': {Color.WHITE},
                'subtypes': {'Spirit', 'Patronus'},
                'keywords': ['flying', 'protection_from_black']
            }
        },
        source=source_id
    )


def gryffindor_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Gryffindor")

def slytherin_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Slytherin")

def ravenclaw_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Ravenclaw")

def hufflepuff_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Hufflepuff")

def wizard_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Wizard")

def death_eater_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Death Eater")


# =============================================================================
# WHITE CARDS - GRYFFINDOR, PROTECTION, LIGHT MAGIC
# =============================================================================

# --- Legendary Creatures ---

def harry_potter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, create Patronus token. House bonus."""
    interceptors = []
    interceptors.extend(make_house_bonus(obj, "Gryffindor", 1, 1))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [make_patronus_token(obj.controller, obj.id, "Stag")]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

HARRY_POTTER_THE_CHOSEN_ONE = make_creature(
    name="Harry Potter, the Chosen One",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Vigilance. House - Harry gets +1/+1 for each other Gryffindor you control. Whenever Harry attacks, create a 2/2 white Spirit Patronus token with flying and protection from black.",
    setup_interceptors=harry_potter_setup
)


def hermione_granger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell Mastery - draw when casting instants/sorceries."""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        if has_spell_mastery(state, obj.controller):
            return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
        return []
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

HERMIONE_GRANGER = make_creature(
    name="Hermione Granger, Brightest Witch",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Spell Mastery - Whenever you cast an instant or sorcery, if you've cast 3+ instants/sorceries this game, draw a card.",
    setup_interceptors=hermione_granger_setup
)


def dumbledore_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Wizards get +1/+1 and hexproof."""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Wizard")))
    interceptors.append(make_keyword_grant(obj, ['hexproof'], other_creatures_with_subtype(obj, "Wizard")))
    return interceptors

ALBUS_DUMBLEDORE = make_creature(
    name="Albus Dumbledore, Headmaster",
    power=4, toughness=5,
    mana_cost="{3}{W}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flying. Other Wizard creatures you control get +1/+1 and have hexproof. {2}{W}: Create a 2/2 white Spirit Patronus token with flying.",
    setup_interceptors=dumbledore_setup
)


def mcgonagall_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Gryffindors have vigilance."""
    return [make_keyword_grant(obj, ['vigilance'], other_creatures_with_subtype(obj, "Gryffindor"))]

MINERVA_MCGONAGALL = make_creature(
    name="Minerva McGonagall, Transfiguration Master",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Vigilance. Other Gryffindor creatures you control have vigilance. {1}{W}: Target creature becomes a 1/1 Cat until end of turn.",
    setup_interceptors=mcgonagall_setup
)


def neville_longbottom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +2/+2 when blocking."""
    def block_filter(event: Event, state: GameState, source: GameObject) -> bool:
        return (event.type == EventType.BLOCK_DECLARED and
                event.payload.get('blocker_id') == source.id)

    def block_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': 'temporary_boost',
            'power': 2, 'toughness': 2, 'duration': 'end_of_turn'
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: block_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=block_effect(e, s)),
        duration='while_on_battlefield'
    )]

NEVILLE_LONGBOTTOM = make_creature(
    name="Neville Longbottom, Brave Heart",
    power=2, toughness=3,
    mana_cost="{1}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Whenever Neville blocks, he gets +2/+2 until end of turn. {T}: Destroy target enchantment.",
    setup_interceptors=neville_longbottom_setup
)


# --- Regular White Creatures ---

def gryffindor_prefect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Gryffindors get +1/+0."""
    return make_static_pt_boost(obj, 1, 0, other_creatures_with_subtype(obj, "Gryffindor"))

GRYFFINDOR_PREFECT = make_creature(
    name="Gryffindor Prefect",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    text="Other Gryffindor creatures you control get +1/+0.",
    setup_interceptors=gryffindor_prefect_setup
)


def auror_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

AUROR_RECRUIT = make_creature(
    name="Auror Recruit",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Auror"},
    text="When Auror Recruit enters, you gain 2 life.",
    setup_interceptors=auror_recruit_setup
)


HOGWARTS_DEFENDER = make_creature(
    name="Hogwarts Defender",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="Defender. Whenever Hogwarts Defender blocks, you gain 2 life."
)


ORDER_PHOENIX_MEMBER = make_creature(
    name="Order of the Phoenix Member",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="First strike. Protection from black."
)


MINISTRY_AUROR = make_creature(
    name="Ministry Auror",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Auror"},
    text="Vigilance. {1}{W}: Ministry Auror gains lifelink until end of turn."
)


def patronus_caster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create Patronus token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [make_patronus_token(obj.controller, obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

PATRONUS_CASTER = make_creature(
    name="Patronus Caster",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="When Patronus Caster enters, create a 2/2 white Spirit Patronus token with flying and protection from black.",
    setup_interceptors=patronus_caster_setup
)


HOGWARTS_FIRST_YEAR = make_creature(
    name="Hogwarts First Year",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="When Hogwarts First Year dies, you gain 2 life."
)


DUMBLEDORES_ARMY_RECRUIT = make_creature(
    name="Dumbledore's Army Recruit",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    text="House - Dumbledore's Army Recruit gets +1/+1 as long as you control another Gryffindor."
)


WEASLEY_MATRIARCH = make_creature(
    name="Weasley Matriarch",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="When Weasley Matriarch enters, create two 1/1 red Human Wizard creature tokens."
)


HOGWARTS_GHOST = make_creature(
    name="Hogwarts Ghost",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying. Hogwarts Ghost can block creatures with menace as though it didn't have menace."
)


QUIDDITCH_REFEREE = make_creature(
    name="Quidditch Referee",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="Flying. Creatures can't attack you unless their controller pays {1} for each creature attacking you."
)


HEALING_WITCH = make_creature(
    name="Healing Witch",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Cleric"},
    text="{T}: Prevent the next 2 damage that would be dealt to target creature this turn."
)


ST_MUNGOS_HEALER = make_creature(
    name="St. Mungo's Healer",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Cleric"},
    text="When St. Mungo's Healer enters, you gain 3 life. {T}: You gain 1 life."
)


PHOENIX_GUARDIAN = make_creature(
    name="Phoenix Guardian",
    power=3, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Phoenix"},
    text="Flying. When Phoenix Guardian dies, return it to its owner's hand at the beginning of the next end step."
)


# --- White Instants ---

EXPECTO_PATRONUM = make_instant(
    name="Expecto Patronum",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Create a 2/2 white Spirit Patronus token with flying and protection from black. Spell Mastery - If you've cast 3+ instants/sorceries this game, create two tokens instead."
)


PROTEGO = make_instant(
    name="Protego",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to target creature this turn. Draw a card."
)


SHIELD_CHARM = make_instant(
    name="Shield Charm",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn."
)


COUNTER_CURSE = make_instant(
    name="Counter-Curse",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target enchantment. You gain 2 life."
)


PRIORI_INCANTATEM = make_instant(
    name="Priori Incantatem",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Exile target creature. Its controller creates a 1/1 white Spirit creature token."
)


HEALING_SPELL = make_instant(
    name="Healing Spell",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="You gain 4 life."
)


DISILLUSIONMENT_CHARM = make_instant(
    name="Disillusionment Charm",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gains hexproof and can't be blocked until end of turn."
)


# --- White Sorceries ---

CALL_THE_ORDER = make_sorcery(
    name="Call the Order",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 2/2 white Human Wizard creature tokens. You gain 1 life for each Wizard you control."
)


SORTING_CEREMONY = make_sorcery(
    name="Sorting Ceremony",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature becomes a Gryffindor in addition to its other types. Put a +1/+1 counter on it."
)


OBLIVIATE = make_sorcery(
    name="Obliviate",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature an opponent controls. Its controller draws a card."
)


# --- White Enchantments ---

def light_magic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant, gain 1 life."""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT})]

LIGHT_MAGIC = make_enchantment(
    name="Light Magic",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever you cast an instant spell, you gain 1 life.",
    setup_interceptors=light_magic_setup
)


DUMBLEDORES_PROTECTION = make_enchantment(
    name="Dumbledore's Protection",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control have hexproof and can't be sacrificed."
)


GRYFFINDOR_BANNER = make_enchantment(
    name="Gryffindor Banner",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Gryffindor creatures you control get +1/+1. At the beginning of your end step, if you control 3+ Gryffindors, draw a card."
)


# =============================================================================
# BLUE CARDS - RAVENCLAW, KNOWLEDGE, DIVINATION
# =============================================================================

# --- Legendary Creatures ---

def luna_lovegood_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you scry, draw a card."""
    def scry_effect(event: Event, state: GameState) -> list[Event]:
        if event.type == EventType.SCRY and event.payload.get('player') == obj.controller:
            return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
        return []

    def scry_filter(event: Event, state: GameState) -> bool:
        return event.type == EventType.SCRY and event.payload.get('player') == obj.controller

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=scry_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=scry_effect(e, s)),
        duration='while_on_battlefield'
    )]

LUNA_LOVEGOOD = make_creature(
    name="Luna Lovegood, Seer of Truth",
    power=1, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    supertypes={"Legendary"},
    text="Whenever you scry, draw a card. {U}: Scry 1.",
    setup_interceptors=luna_lovegood_setup
)


def filius_flitwick_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instants cost 1 less."""
    def cost_reduce_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        return CardType.INSTANT in set(event.payload.get('types', []))

    def cost_reduce_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current_reduction = new_event.payload.get('cost_reduction', 0)
        new_event.payload['cost_reduction'] = current_reduction + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=cost_reduce_filter,
        handler=cost_reduce_handler,
        duration='while_on_battlefield'
    )]

FILIUS_FLITWICK = make_creature(
    name="Filius Flitwick, Charms Master",
    power=1, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Goblin", "Wizard", "Ravenclaw"},
    supertypes={"Legendary"},
    text="Instant spells you cast cost {1} less. Other Ravenclaw creatures you control have hexproof.",
    setup_interceptors=filius_flitwick_setup
)


def cho_chang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

CHO_CHANG = make_creature(
    name="Cho Chang, Seeker",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    supertypes={"Legendary"},
    text="Flying. When Cho Chang enters, scry 2.",
    setup_interceptors=cho_chang_setup
)


def moaning_myrtle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, draw 2 cards."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

MOANING_MYRTLE = make_creature(
    name="Moaning Myrtle",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying. When Moaning Myrtle dies, draw two cards.",
    setup_interceptors=moaning_myrtle_setup
)


# --- Regular Blue Creatures ---

def ravenclaw_prefect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - draw a card, then discard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

RAVENCLAW_PREFECT = make_creature(
    name="Ravenclaw Prefect",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    text="When Ravenclaw Prefect enters, draw a card, then discard a card.",
    setup_interceptors=ravenclaw_prefect_setup
)


HOGWARTS_SCHOLAR = make_creature(
    name="Hogwarts Scholar",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{T}: Scry 1."
)


DIVINATION_STUDENT = make_creature(
    name="Divination Student",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Divination Student enters, scry 1."
)


LIBRARY_RESEARCHER = make_creature(
    name="Library Researcher",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Defender. {T}, Discard a card: Draw two cards."
)


SPELL_THEORIST = make_creature(
    name="Spell Theorist",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    text="Spell Mastery - Spell Theorist has flying as long as you've cast 3+ instants/sorceries this game."
)


HOGWARTS_LIBRARIAN = make_creature(
    name="Hogwarts Librarian",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you draw your second card each turn, scry 2."
)


UNSPEAKABLE = make_creature(
    name="Unspeakable",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Hexproof. When Unspeakable enters, look at the top 3 cards of your library. Put one into your hand and the rest on the bottom."
)


PENSIEVE_KEEPER = make_creature(
    name="Pensieve Keeper",
    power=1, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{2}{U}, {T}: Draw a card. Activate only as a sorcery."
)


THESTRAL = make_creature(
    name="Thestral",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Beast"},
    text="Flying. Thestral can't be blocked. Thestral has hexproof as long as a creature died this turn."
)


TIME_TURNER_USER = make_creature(
    name="Time-Turner User",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{2}{U}{U}, Sacrifice Time-Turner User: Take an extra turn after this one."
)


MEMORY_CHARM_SPECIALIST = make_creature(
    name="Memory Charm Specialist",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Memory Charm Specialist enters, target opponent reveals their hand. You choose a nonland card from it. That player shuffles it into their library."
)


# --- Blue Instants ---

STUPEFY = make_instant(
    name="Stupefy",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)


ACCIO = make_instant(
    name="Accio",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Search your library for an artifact card, reveal it, and put it into your hand. Shuffle."
)


CONFUNDO = make_instant(
    name="Confundo",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}."
)


PETRIFICUS_TOTALUS = make_instant(
    name="Petrificus Totalus",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It becomes an artifact in addition to its other types and loses all abilities until your next turn."
)


LEGILIMENS = make_instant(
    name="Legilimens",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target opponent reveals their hand. You draw a card."
)


AGUAMENTI = make_instant(
    name="Aguamenti",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Tap or untap target permanent. Draw a card."
)


FINITE_INCANTATEM = make_instant(
    name="Finite Incantatem",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Spell Mastery - If you've cast 3+ instants/sorceries this game, draw a card."
)


# --- Blue Sorceries ---

DIVINATION_SPELL = make_sorcery(
    name="Divination",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards."
)


CRYSTAL_BALL_READING = make_sorcery(
    name="Crystal Ball Reading",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Scry 3, then draw a card."
)


MEMORY_WIPE = make_sorcery(
    name="Memory Wipe",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Each opponent shuffles their hand into their library, then draws that many cards minus one."
)


TRANSFIGURATION = make_sorcery(
    name="Transfiguration",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Until end of turn, target creature becomes a copy of another target creature."
)


# --- Blue Enchantments ---

LIBRARY_OF_HOGWARTS = make_enchantment(
    name="Library of Hogwarts",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1. Whenever you scry, you may pay {1}. If you do, draw a card."
)


RAVENCLAW_BANNER = make_enchantment(
    name="Ravenclaw Banner",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Ravenclaw creatures you control get +0/+1 and have '{T}: Scry 1.'"
)


# =============================================================================
# BLACK CARDS - SLYTHERIN, DARK ARTS, DEATH EATERS
# =============================================================================

# --- Legendary Creatures ---

def voldemort_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature dies, put a +1/+1 counter on Voldemort."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        return dying_id != source.id

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=death_effect(e, s)),
        duration='while_on_battlefield'
    )]

LORD_VOLDEMORT = make_creature(
    name="Lord Voldemort, the Dark Lord",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flying, deathtouch. Whenever another creature dies, put a +1/+1 counter on Lord Voldemort. {2}{B}: Each opponent loses 2 life.",
    setup_interceptors=voldemort_setup
)


def snape_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - deal damage to target creature."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'target_creature', 'amount': 3, 'source': obj.id
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

SEVERUS_SNAPE = make_creature(
    name="Severus Snape, Double Agent",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Slytherin"},
    supertypes={"Legendary"},
    text="Deathtouch. When Severus Snape dies, he deals 3 damage to target creature. {1}{B}: Target creature gets -1/-1 until end of turn.",
    setup_interceptors=snape_setup
)


def bellatrix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, opponent sacrifices a creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SACRIFICE, payload={
            'player': 'opponent', 'type': 'creature'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

BELLATRIX_LESTRANGE = make_creature(
    name="Bellatrix Lestrange, Mad Servant",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Death Eater"},
    supertypes={"Legendary"},
    text="Menace. Whenever Bellatrix attacks, defending player sacrifices a creature.",
    setup_interceptors=bellatrix_setup
)


def draco_malfoy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Slytherins get +1/+0."""
    return make_static_pt_boost(obj, 1, 0, other_creatures_with_subtype(obj, "Slytherin"))

DRACO_MALFOY = make_creature(
    name="Draco Malfoy, Cunning Heir",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Slytherin"},
    supertypes={"Legendary"},
    text="Other Slytherin creatures you control get +1/+0. {1}{B}, Sacrifice another creature: Draw a card.",
    setup_interceptors=draco_malfoy_setup
)


def lucius_malfoy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - opponent discards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DISCARD, payload={'player': 'opponent', 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

LUCIUS_MALFOY = make_creature(
    name="Lucius Malfoy, Dark Aristocrat",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Death Eater"},
    supertypes={"Legendary"},
    text="When Lucius Malfoy enters, target opponent discards a card. Death Eaters you control have menace.",
    setup_interceptors=lucius_malfoy_setup
)


# --- Regular Black Creatures ---

SLYTHERIN_PREFECT = make_creature(
    name="Slytherin Prefect",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Slytherin"},
    text="Deathtouch."
)


DEATH_EATER_INITIATE = make_creature(
    name="Death Eater Initiate",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Death Eater"},
    text="When Death Eater Initiate dies, target player loses 1 life."
)


DEMENTOR = make_creature(
    name="Dementor",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flying. Whenever Dementor deals combat damage to a player, that player discards a card and you draw a card."
)


DEMENTOR_SWARM = make_creature(
    name="Dementor Swarm",
    power=5, toughness=5,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flying. When Dementor Swarm enters, each opponent discards two cards."
)


INFERIUS = make_creature(
    name="Inferius",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Inferius can't block. When Inferius dies, create a 2/2 black Zombie creature token."
)


DARK_WIZARD = make_creature(
    name="Dark Wizard",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="Menace. {B}, Pay 2 life: Dark Wizard gains deathtouch until end of turn."
)


KNOCKTURN_ALLEY_VENDOR = make_creature(
    name="Knockturn Alley Vendor",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="{T}, Pay 1 life: Add {B}."
)


BASILISK = make_creature(
    name="Basilisk",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Serpent"},
    text="Deathtouch. Whenever Basilisk deals damage to a creature, destroy that creature."
)


ACROMANTULA = make_creature(
    name="Acromantula",
    power=4, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spider"},
    text="Reach, deathtouch. When Acromantula dies, create two 1/1 black Spider creature tokens with reach."
)


NAGINI = make_creature(
    name="Nagini",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Snake"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Nagini deals combat damage to a player, you may return target creature card from your graveyard to your hand."
)


AZKABAN_GUARD = make_creature(
    name="Azkaban Guard",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="Lifelink. Other creatures you control have lifelink."
)


GREYBACK = make_creature(
    name="Fenrir Greyback",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Werewolf"},
    supertypes={"Legendary"},
    text="First strike. Whenever Fenrir Greyback deals combat damage to a creature, put two -1/-1 counters on that creature."
)


# --- Black Instants ---

AVADA_KEDAVRA = make_instant(
    name="Avada Kedavra",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. It can't be regenerated. Its controller loses 2 life."
)


CRUCIO = make_instant(
    name="Crucio",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn."
)


IMPERIO = make_instant(
    name="Imperio",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Gain control of target creature until end of turn. Untap it. It gains haste until end of turn."
)


SECTUMSEMPRA = make_instant(
    name="Sectumsempra",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. You lose 2 life."
)


MORSMORDRE = make_instant(
    name="Morsmordre",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Create a 4/4 black Horror creature token with flying."
)


DARK_MARK = make_instant(
    name="Dark Mark",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets +2/+0 and gains menace until end of turn."
)


# --- Black Sorceries ---

CURSE_OF_THE_BOGIES = make_sorcery(
    name="Curse of the Bogies",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target player discards a card. Spell Mastery - If you've cast 3+ instants/sorceries this game, that player discards two cards instead."
)


SUMMON_INFERI = make_sorcery(
    name="Summon Inferi",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Return up to two creature cards from your graveyard to the battlefield. They gain haste. Exile them at the beginning of the next end step."
)


DARK_RITUAL_SPELL = make_sorcery(
    name="Dark Ritual",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Add {B}{B}{B}."
)


FIENDFYRE = make_sorcery(
    name="Fiendfyre",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. You lose 3 life."
)


# --- Black Enchantments ---

def dark_arts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature you control dies, each opponent loses 1 life."""
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
        return dying.controller == source.controller and CardType.CREATURE in dying.characteristics.types

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={
            'player': 'each_opponent', 'amount': -1
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=death_effect(e, s)),
        duration='while_on_battlefield'
    )]

THE_DARK_ARTS = make_enchantment(
    name="The Dark Arts",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Whenever a creature you control dies, each opponent loses 1 life.",
    setup_interceptors=dark_arts_setup
)


SLYTHERIN_BANNER = make_enchantment(
    name="Slytherin Banner",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Slytherin creatures you control get +1/+1 and have deathtouch."
)


HORCRUX_CURSE = make_enchantment(
    name="Horcrux Curse",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life. When you would lose the game, if you have 7 or more life, you may pay 7 life instead. If you do, exile Horcrux Curse."
)


# =============================================================================
# RED CARDS - WEASLEYS, CHAOS, FIRE SPELLS
# =============================================================================

# --- Legendary Creatures ---

def ron_weasley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +1/+1 for each other Gryffindor."""
    return make_house_bonus(obj, "Gryffindor", 1, 1)

RON_WEASLEY = make_creature(
    name="Ron Weasley, Loyal Friend",
    power=2, toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="First strike. House - Ron gets +1/+1 for each other Gryffindor you control.",
    setup_interceptors=ron_weasley_setup
)


def fred_and_george_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, create a copy token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Weasley Twin', 'power': 2, 'toughness': 2, 'colors': {Color.RED},
                     'subtypes': {'Human', 'Wizard', 'Gryffindor'}, 'keywords': ['haste'],
                     'exile_eot': True}
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

FRED_AND_GEORGE = make_creature(
    name="Fred and George Weasley, Pranksters",
    power=2, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Haste. Whenever Fred and George attack, create a 2/2 red Human Wizard token with haste. Exile it at end of turn.",
    setup_interceptors=fred_and_george_setup
)


def ginny_weasley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell Mastery - has double strike."""
    def mastery_check(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return has_spell_mastery(state, obj.controller)
    return [make_keyword_grant(obj, ['double_strike'], mastery_check)]

GINNY_WEASLEY = make_creature(
    name="Ginny Weasley, Fierce Duelist",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="First strike. Spell Mastery - Ginny has double strike if you've cast 3+ instants/sorceries this game.",
    setup_interceptors=ginny_weasley_setup
)


def sirius_black_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attacks each combat if able."""
    return []  # Forced attack handled by engine

SIRIUS_BLACK = make_creature(
    name="Sirius Black, Escaped Convict",
    power=4, toughness=3,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Haste. Sirius Black attacks each combat if able. Whenever Sirius deals combat damage to a player, draw a card.",
    setup_interceptors=sirius_black_setup
)


def molly_weasley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - deal 3 damage to creature that killed her."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'damage_source', 'amount': 5, 'source': obj.id
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

MOLLY_WEASLEY = make_creature(
    name="Molly Weasley, Protective Mother",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Molly Weasley dies, she deals 5 damage to target creature.",
    setup_interceptors=molly_weasley_setup
)


# --- Regular Red Creatures ---

WEASLEY_TWIN_PRANKSTER = make_creature(
    name="Weasley Twin Prankster",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Gryffindor"},
    text="Haste. When Weasley Twin Prankster enters, it deals 1 damage to any target."
)


QUIDDITCH_BEATER = make_creature(
    name="Quidditch Beater",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="Haste. {R}: Quidditch Beater gets +1/+0 until end of turn."
)


DRAGON_HANDLER = make_creature(
    name="Dragon Handler",
    power=2, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="Dragon creatures you control get +1/+0 and have haste."
)


HUNGARIAN_HORNTAIL = make_creature(
    name="Hungarian Horntail",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, haste. Whenever Hungarian Horntail attacks, it deals 2 damage to each creature defending player controls."
)


NORWEGIAN_RIDGEBACK = make_creature(
    name="Norwegian Ridgeback",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying. {R}: Norwegian Ridgeback gets +1/+0 until end of turn."
)


CHINESE_FIREBALL = make_creature(
    name="Chinese Fireball",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying. When Chinese Fireball enters, it deals 3 damage to target creature or player."
)


COMMON_WELSH_GREEN = make_creature(
    name="Common Welsh Green",
    power=4, toughness=5,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Dragon"},
    text="Flying. Whenever Common Welsh Green deals combat damage to a player, add {R}{G}."
)


GOBLIN_BANKER = make_creature(
    name="Gringotts Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="{T}: Add {R}. Spend this mana only to cast instant or sorcery spells."
)


FIENDFYRE_ELEMENTAL = make_creature(
    name="Fiendfyre Elemental",
    power=5, toughness=1,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample, haste. At the beginning of your end step, sacrifice Fiendfyre Elemental."
)


BLAST_ENDED_SKREWT = make_creature(
    name="Blast-Ended Skrewt",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="When Blast-Ended Skrewt dies, it deals 2 damage to each creature."
)


ERUMPENT = make_creature(
    name="Erumpent",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="Trample. When Erumpent dies, it deals 4 damage to target creature or player."
)


# --- Red Instants ---

INCENDIO = make_instant(
    name="Incendio",
    mana_cost="{R}",
    colors={Color.RED},
    text="Incendio deals 2 damage to any target."
)


CONFRINGO = make_instant(
    name="Confringo",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Confringo deals 3 damage to target creature or planeswalker."
)


BOMBARDA = make_instant(
    name="Bombarda",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Destroy target artifact. Bombarda deals 2 damage to that artifact's controller."
)


REDUCTO = make_instant(
    name="Reducto",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Reducto deals 4 damage to target creature."
)


EXPULSO = make_instant(
    name="Expulso",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Expulso deals 5 damage divided as you choose among any number of target creatures."
)


DRAGONS_BREATH = make_instant(
    name="Dragon's Breath",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains first strike until end of turn."
)


WEASLEY_FIREWORK = make_instant(
    name="Weasley Firework",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Weasley Firework deals 1 damage to each creature your opponents control."
)


# --- Red Sorceries ---

DRAGONS_FIRE = make_sorcery(
    name="Dragon's Fire",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Dragon's Fire deals 4 damage to each creature. If you control a Dragon, it deals 5 damage instead."
)


PYROTECHNICS = make_sorcery(
    name="Pyrotechnics",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Pyrotechnics deals 3 damage divided as you choose among one, two, or three targets."
)


SUMMON_DRAGON = make_sorcery(
    name="Summon Dragon",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Create a 5/5 red Dragon creature token with flying and haste."
)


# --- Red Enchantments ---

WEASLEYS_WIZARD_WHEEZES = make_enchantment(
    name="Weasleys' Wizard Wheezes",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever you cast an instant or sorcery spell, Weasleys' Wizard Wheezes deals 1 damage to each opponent."
)


GRYFFINDOR_COURAGE = make_enchantment(
    name="Gryffindor Courage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0 and have haste."
)


# =============================================================================
# GREEN CARDS - HERBOLOGY, MAGICAL CREATURES, HUFFLEPUFF
# =============================================================================

# --- Legendary Creatures ---

def hagrid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures get +1/+1."""
    return make_static_pt_boost(obj, 1, 1, other_creatures_you_control(obj))

RUBEUS_HAGRID = make_creature(
    name="Rubeus Hagrid, Keeper of Keys",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Wizard"},
    supertypes={"Legendary"},
    text="Trample. Other creatures you control get +1/+1. {2}{G}: Create a 3/3 green Beast creature token.",
    setup_interceptors=hagrid_setup
)


def pomona_sprout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - put +1/+1 counter on target creature."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'target': 'target_creature', 'counter_type': '+1/+1', 'amount': 1
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

POMONA_SPROUT = make_creature(
    name="Pomona Sprout, Herbology Master",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control. Other Hufflepuff creatures you control have hexproof.",
    setup_interceptors=pomona_sprout_setup
)


def cedric_diggory_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """House bonus + lifelink."""
    return make_house_bonus(obj, "Hufflepuff", 1, 1)

CEDRIC_DIGGORY = make_creature(
    name="Cedric Diggory, True Champion",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    supertypes={"Legendary"},
    text="Lifelink. House - Cedric gets +1/+1 for each other Hufflepuff you control.",
    setup_interceptors=cedric_diggory_setup
)


def newt_scamander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beast creatures cost 1 less."""
    def cost_reduce_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        subtypes = set(event.payload.get('subtypes', []))
        return 'Beast' in subtypes

    def cost_reduce_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current_reduction = new_event.payload.get('cost_reduction', 0)
        new_event.payload['cost_reduction'] = current_reduction + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=cost_reduce_filter,
        handler=cost_reduce_handler,
        duration='while_on_battlefield'
    )]

NEWT_SCAMANDER = make_creature(
    name="Newt Scamander, Magizoologist",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    supertypes={"Legendary"},
    text="Beast creature spells you cast cost {1} less. Whenever a Beast enters under your control, draw a card.",
    setup_interceptors=newt_scamander_setup
)


# --- Regular Green Creatures ---

HUFFLEPUFF_PREFECT = make_creature(
    name="Hufflepuff Prefect",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    text="Other Hufflepuff creatures you control get +0/+1."
)


MANDRAKE = make_creature(
    name="Mandrake",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="When Mandrake dies, tap all creatures your opponents control."
)


VENOMOUS_TENTACULA = make_creature(
    name="Venomous Tentacula",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Reach, deathtouch."
)


BOWTRUCKLE = make_creature(
    name="Bowtruckle",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Hexproof. {T}: Add {G}. Spend this mana only to cast creature spells."
)


HIPPOGRIFF = make_creature(
    name="Hippogriff",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Hippogriff"},
    text="Flying. Hippogriff can't be blocked by creatures with power 2 or less."
)


BUCKBEAK = make_creature(
    name="Buckbeak",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hippogriff"},
    supertypes={"Legendary"},
    text="Flying, trample. Buckbeak can't be blocked by more than one creature."
)


FAWKES_THE_PHOENIX = make_creature(
    name="Fawkes the Phoenix",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Phoenix"},
    supertypes={"Legendary"},
    text="Flying. When Fawkes dies, return it to the battlefield at the beginning of the next end step. Whenever Fawkes enters, you gain 3 life."
)


UNICORN = make_creature(
    name="Unicorn",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Unicorn"},
    text="Vigilance. {T}: You gain 1 life."
)


CENTAUR_ARCHER = make_creature(
    name="Centaur Archer",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Archer"},
    text="Reach. {G}: Centaur Archer deals 1 damage to target creature with flying."
)


FORBIDDEN_FOREST_SPIDER = make_creature(
    name="Forbidden Forest Spider",
    power=2, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach. When Forbidden Forest Spider dies, create two 1/1 green Spider creature tokens with reach."
)


NIFFLER = make_creature(
    name="Niffler",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When Niffler enters, you may search your library for an artifact card, reveal it, and put it into your hand. Shuffle."
)


THESTRAL_HERD = make_creature(
    name="Thestral Herd",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Flying. Thestral Herd has hexproof as long as a creature died this turn."
)


WHOMPING_WILLOW = make_creature(
    name="Whomping Willow",
    power=5, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Defender, reach. Whenever a creature attacks you, Whomping Willow deals 2 damage to it."
)


GIANT_SQUID = make_creature(
    name="Giant Squid of the Black Lake",
    power=6, toughness=6,
    mana_cost="{4}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Kraken"},
    text="Hexproof. Giant Squid can't attack unless defending player controls an Island or you pay {2}."
)


# --- Green Instants ---

HERBIVICUS = make_instant(
    name="Herbivicus",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn."
)


WILD_GROWTH_SPELL = make_instant(
    name="Wild Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature."
)


ENGORGIO = make_instant(
    name="Engorgio",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 and gains trample until end of turn."
)


BEASTS_FURY = make_instant(
    name="Beast's Fury",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control."
)


NATURES_PROTECTION = make_instant(
    name="Nature's Protection",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gains hexproof and indestructible until end of turn."
)


# --- Green Sorceries ---

GREENHOUSE_HARVEST = make_sorcery(
    name="Greenhouse Harvest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal them, put one onto the battlefield tapped and the other into your hand. Shuffle."
)


CREATURE_SUMMONING = make_sorcery(
    name="Creature Summoning",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create two 3/3 green Beast creature tokens."
)


MANDRAKE_RESTORATIVE = make_sorcery(
    name="Mandrake Restorative",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="You gain 5 life. You may return target creature card from your graveyard to your hand."
)


# --- Green Enchantments ---

HERBOLOGY_CLASSROOM = make_enchantment(
    name="Herbology Classroom",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control."
)


HUFFLEPUFF_BANNER = make_enchantment(
    name="Hufflepuff Banner",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Hufflepuff creatures you control get +1/+1. Whenever a Hufflepuff enters under your control, you gain 1 life."
)


FORBIDDEN_FOREST = make_enchantment(
    name="Forbidden Forest",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Creature spells you cast cost {1} less. Creatures you control have trample."
)


# =============================================================================
# ARTIFACTS
# =============================================================================

ELDER_WAND = make_equipment(
    name="Elder Wand",
    mana_cost="{3}",
    text="Equipped creature gets +3/+0 and has first strike. Whenever equipped creature deals combat damage to a player, draw a card.",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


RESURRECTION_STONE = make_artifact(
    name="Resurrection Stone",
    mana_cost="{2}",
    text="{3}, {T}, Sacrifice Resurrection Stone: Return target creature card from your graveyard to the battlefield.",
    supertypes={"Legendary"}
)


INVISIBILITY_CLOAK = make_equipment(
    name="Invisibility Cloak",
    mana_cost="{2}",
    text="Equipped creature has hexproof and can't be blocked.",
    equip_cost="{1}",
    supertypes={"Legendary"}
)


SWORD_OF_GRYFFINDOR = make_equipment(
    name="Sword of Gryffindor",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2 and has protection from black. Whenever equipped creature deals combat damage to a player, destroy target artifact or enchantment.",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


MARAUDERS_MAP = make_artifact(
    name="Marauder's Map",
    mana_cost="{2}",
    text="{T}: Scry 2. {2}, {T}: Look at target opponent's hand.",
    supertypes={"Legendary"}
)


SORTING_HAT = make_artifact(
    name="Sorting Hat",
    mana_cost="{1}",
    text="{T}: Target creature becomes Gryffindor, Slytherin, Ravenclaw, or Hufflepuff in addition to its other types until end of turn.",
    supertypes={"Legendary"}
)


HORCRUX_DIARY = make_artifact(
    name="Tom Riddle's Diary",
    mana_cost="{2}",
    text="{1}, {T}, Pay 2 life: Draw a card. When Tom Riddle's Diary is put into a graveyard from the battlefield, you lose 5 life.",
    supertypes={"Legendary"}
)


HORCRUX_LOCKET = make_artifact(
    name="Slytherin's Locket",
    mana_cost="{3}",
    text="At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life. {2}, Sacrifice Slytherin's Locket: Draw two cards.",
    supertypes={"Legendary"}
)


HORCRUX_CUP = make_artifact(
    name="Hufflepuff's Cup",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. When Hufflepuff's Cup is put into a graveyard from the battlefield, each opponent draws a card.",
    supertypes={"Legendary"}
)


HORCRUX_DIADEM = make_artifact(
    name="Ravenclaw's Diadem",
    mana_cost="{3}",
    text="Instant and sorcery spells you cast cost {1} less. {2}, Sacrifice Ravenclaw's Diadem: Draw three cards.",
    supertypes={"Legendary"}
)


HORCRUX_RING = make_artifact(
    name="Gaunt Family Ring",
    mana_cost="{2}",
    text="{T}: Add {B}. {3}, {T}, Sacrifice Gaunt Family Ring: Return target creature card from your graveyard to your hand.",
    supertypes={"Legendary"}
)


FIREBOLT_BROOM = make_artifact(
    name="Firebolt",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has flying and haste.\nEquip {2}"
)


NIMBUS_2000 = make_artifact(
    name="Nimbus 2000",
    mana_cost="{2}",
    text="Equipped creature gets +1/+0 and has flying.\nEquip {1}"
)


WAND_OF_PHOENIX_FEATHER = make_equipment(
    name="Wand of Phoenix Feather",
    mana_cost="{1}",
    text="Equipped creature has '{T}: This creature deals 1 damage to any target.'",
    equip_cost="{1}"
)


WAND_OF_DRAGON_HEARTSTRING = make_equipment(
    name="Wand of Dragon Heartstring",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1 and has '{T}: Add {R}.'",
    equip_cost="{1}"
)


WAND_OF_UNICORN_HAIR = make_equipment(
    name="Wand of Unicorn Hair",
    mana_cost="{1}",
    text="Equipped creature has '{T}: You gain 1 life.'",
    equip_cost="{1}"
)


PENSIEVE = make_artifact(
    name="Pensieve",
    mana_cost="{3}",
    text="{2}, {T}: Look at the top 3 cards of your library. Put one into your hand and the rest on the bottom in any order."
)


GOLDEN_SNITCH = make_artifact(
    name="Golden Snitch",
    mana_cost="{1}",
    text="Flying. {T}, Sacrifice Golden Snitch: Draw two cards.",
    supertypes={"Legendary"}
)


QUAFFLE = make_artifact(
    name="Quaffle",
    mana_cost="{1}",
    text="{1}, {T}: Target creature gets +1/+0 and gains first strike until end of turn."
)


BLUDGER = make_artifact(
    name="Bludger",
    mana_cost="{2}",
    text="{2}, {T}: Bludger deals 2 damage to target creature."
)


TIME_TURNER = make_artifact(
    name="Time-Turner",
    mana_cost="{4}",
    text="{T}, Sacrifice Time-Turner: Take an extra turn after this one. Activate only as a sorcery.",
    supertypes={"Legendary"}
)


DELUMINATOR = make_artifact(
    name="Deluminator",
    mana_cost="{1}",
    text="{T}: Tap target creature. It doesn't untap during its controller's next untap step.",
    supertypes={"Legendary"}
)


PORTKEY = make_artifact(
    name="Portkey",
    mana_cost="{2}",
    text="{3}, {T}, Sacrifice Portkey: Return target creature to its owner's hand."
)


FLOO_POWDER = make_artifact(
    name="Floo Powder",
    mana_cost="{1}",
    text="{1}, Sacrifice Floo Powder: Add two mana of any one color."
)


GOBLET_OF_FIRE = make_artifact(
    name="Goblet of Fire",
    mana_cost="{4}",
    text="At the beginning of your upkeep, put a flame counter on Goblet of Fire. Then if there are 3 or more flame counters on it, sacrifice it and create a 5/5 red Dragon creature token with flying.",
    supertypes={"Legendary"}
)


MIRROR_OF_ERISED = make_artifact(
    name="Mirror of Erised",
    mana_cost="{3}",
    text="{2}, {T}: Look at the top card of your library. You may put it into your graveyard.",
    supertypes={"Legendary"}
)


VANISHING_CABINET = make_artifact(
    name="Vanishing Cabinet",
    mana_cost="{3}",
    text="{2}, {T}: Exile target creature you control. Return it to the battlefield at the beginning of the next end step."
)


# =============================================================================
# LANDS
# =============================================================================

HOGWARTS_CASTLE = make_land(
    name="Hogwarts Castle",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Wizard spells.",
    supertypes={"Legendary"}
)


GRYFFINDOR_COMMON_ROOM = make_land(
    name="Gryffindor Common Room",
    text="Gryffindor Common Room enters tapped. {T}: Add {R} or {W}. {2}, {T}: Target Gryffindor creature gets +1/+1 until end of turn."
)


SLYTHERIN_DUNGEON = make_land(
    name="Slytherin Dungeon",
    text="Slytherin Dungeon enters tapped. {T}: Add {B} or {U}. {2}, {T}: Target Slytherin creature gains deathtouch until end of turn."
)


RAVENCLAW_TOWER = make_land(
    name="Ravenclaw Tower",
    text="Ravenclaw Tower enters tapped. {T}: Add {U} or {W}. {2}, {T}: Scry 1."
)


HUFFLEPUFF_BASEMENT = make_land(
    name="Hufflepuff Basement",
    text="Hufflepuff Basement enters tapped. {T}: Add {G} or {W}. {2}, {T}: You gain 1 life."
)


DIAGON_ALLEY = make_land(
    name="Diagon Alley",
    text="{T}: Add {C}. {1}, {T}: Add one mana of any color. Spend this mana only to cast artifact spells."
)


HOGSMEADE_VILLAGE = make_land(
    name="Hogsmeade Village",
    text="{T}: Add {C}. {T}, Pay 1 life: Add one mana of any color."
)


FORBIDDEN_FOREST_LAND = make_land(
    name="The Forbidden Forest",
    text="{T}: Add {G}. {2}{G}, {T}: Create a 2/2 green Beast creature token."
)


MINISTRY_OF_MAGIC = make_land(
    name="Ministry of Magic",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Spend this mana only to cast instant or sorcery spells.",
    supertypes={"Legendary"}
)


AZKABAN = make_land(
    name="Azkaban",
    text="{T}: Add {B}. {2}{B}, {T}: Each opponent discards a card.",
    supertypes={"Legendary"}
)


GODRICS_HOLLOW = make_land(
    name="Godric's Hollow",
    text="{T}: Add {W}. When Godric's Hollow enters, you may pay 2 life. If you do, draw a card."
)


GRIMMAULD_PLACE = make_land(
    name="12 Grimmauld Place",
    text="{T}: Add {B}. {1}{B}, {T}: Target creature gains menace until end of turn.",
    supertypes={"Legendary"}
)


THE_BURROW = make_land(
    name="The Burrow",
    text="{T}: Add {R} or {G}. Whenever you cast a creature spell, you may pay {1}. If you do, you gain 1 life.",
    supertypes={"Legendary"}
)


MALFOY_MANOR = make_land(
    name="Malfoy Manor",
    text="{T}: Add {B}. {2}{B}, {T}: Put a -1/-1 counter on target creature.",
    supertypes={"Legendary"}
)


KNOCKTURN_ALLEY = make_land(
    name="Knockturn Alley",
    text="{T}: Add {B}. {T}, Pay 1 life: Add {B}{B}. Activate only once per turn."
)


GRINGOTTS = make_land(
    name="Gringotts Bank",
    text="{T}: Add {C}{C}. Activate only if you control an artifact.",
    supertypes={"Legendary"}
)


QUIDDITCH_PITCH = make_land(
    name="Quidditch Pitch",
    text="{T}: Add {C}. {3}, {T}: Target creature gains flying until end of turn."
)


ROOM_OF_REQUIREMENT = make_land(
    name="Room of Requirement",
    text="{T}: Add {C}. {2}, {T}: Add one mana of any color.",
    supertypes={"Legendary"}
)


SHRIEKING_SHACK = make_land(
    name="Shrieking Shack",
    text="{T}: Add {B} or {G}. {2}, {T}: Target creature can't block this turn."
)


PLATFORM_NINE_THREE_QUARTERS = make_land(
    name="Platform Nine and Three-Quarters",
    text="{T}: Add {C}. {T}, Sacrifice Platform Nine and Three-Quarters: Search your library for a basic land card, put it onto the battlefield, then shuffle.",
    supertypes={"Legendary"}
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

HARRY_POTTER_CARDS = {
    # White Legendaries
    "Harry Potter, the Chosen One": HARRY_POTTER_THE_CHOSEN_ONE,
    "Hermione Granger, Brightest Witch": HERMIONE_GRANGER,
    "Albus Dumbledore, Headmaster": ALBUS_DUMBLEDORE,
    "Minerva McGonagall, Transfiguration Master": MINERVA_MCGONAGALL,
    "Neville Longbottom, Brave Heart": NEVILLE_LONGBOTTOM,

    # White Creatures
    "Gryffindor Prefect": GRYFFINDOR_PREFECT,
    "Auror Recruit": AUROR_RECRUIT,
    "Hogwarts Defender": HOGWARTS_DEFENDER,
    "Order of the Phoenix Member": ORDER_PHOENIX_MEMBER,
    "Ministry Auror": MINISTRY_AUROR,
    "Patronus Caster": PATRONUS_CASTER,
    "Hogwarts First Year": HOGWARTS_FIRST_YEAR,
    "Dumbledore's Army Recruit": DUMBLEDORES_ARMY_RECRUIT,
    "Weasley Matriarch": WEASLEY_MATRIARCH,
    "Hogwarts Ghost": HOGWARTS_GHOST,
    "Quidditch Referee": QUIDDITCH_REFEREE,
    "Healing Witch": HEALING_WITCH,
    "St. Mungo's Healer": ST_MUNGOS_HEALER,
    "Phoenix Guardian": PHOENIX_GUARDIAN,

    # White Spells
    "Expecto Patronum": EXPECTO_PATRONUM,
    "Protego": PROTEGO,
    "Shield Charm": SHIELD_CHARM,
    "Counter-Curse": COUNTER_CURSE,
    "Priori Incantatem": PRIORI_INCANTATEM,
    "Healing Spell": HEALING_SPELL,
    "Disillusionment Charm": DISILLUSIONMENT_CHARM,
    "Call the Order": CALL_THE_ORDER,
    "Sorting Ceremony": SORTING_CEREMONY,
    "Obliviate": OBLIVIATE,

    # White Enchantments
    "Light Magic": LIGHT_MAGIC,
    "Dumbledore's Protection": DUMBLEDORES_PROTECTION,
    "Gryffindor Banner": GRYFFINDOR_BANNER,

    # Blue Legendaries
    "Luna Lovegood, Seer of Truth": LUNA_LOVEGOOD,
    "Filius Flitwick, Charms Master": FILIUS_FLITWICK,
    "Cho Chang, Seeker": CHO_CHANG,
    "Moaning Myrtle": MOANING_MYRTLE,

    # Blue Creatures
    "Ravenclaw Prefect": RAVENCLAW_PREFECT,
    "Hogwarts Scholar": HOGWARTS_SCHOLAR,
    "Divination Student": DIVINATION_STUDENT,
    "Library Researcher": LIBRARY_RESEARCHER,
    "Spell Theorist": SPELL_THEORIST,
    "Hogwarts Librarian": HOGWARTS_LIBRARIAN,
    "Unspeakable": UNSPEAKABLE,
    "Pensieve Keeper": PENSIEVE_KEEPER,
    "Thestral": THESTRAL,
    "Time-Turner User": TIME_TURNER_USER,
    "Memory Charm Specialist": MEMORY_CHARM_SPECIALIST,

    # Blue Spells
    "Stupefy": STUPEFY,
    "Accio": ACCIO,
    "Confundo": CONFUNDO,
    "Petrificus Totalus": PETRIFICUS_TOTALUS,
    "Legilimens": LEGILIMENS,
    "Aguamenti": AGUAMENTI,
    "Finite Incantatem": FINITE_INCANTATEM,
    "Divination": DIVINATION_SPELL,
    "Crystal Ball Reading": CRYSTAL_BALL_READING,
    "Memory Wipe": MEMORY_WIPE,
    "Transfiguration": TRANSFIGURATION,

    # Blue Enchantments
    "Library of Hogwarts": LIBRARY_OF_HOGWARTS,
    "Ravenclaw Banner": RAVENCLAW_BANNER,

    # Black Legendaries
    "Lord Voldemort, the Dark Lord": LORD_VOLDEMORT,
    "Severus Snape, Double Agent": SEVERUS_SNAPE,
    "Bellatrix Lestrange, Mad Servant": BELLATRIX_LESTRANGE,
    "Draco Malfoy, Cunning Heir": DRACO_MALFOY,
    "Lucius Malfoy, Dark Aristocrat": LUCIUS_MALFOY,
    "Nagini": NAGINI,
    "Fenrir Greyback": GREYBACK,

    # Black Creatures
    "Slytherin Prefect": SLYTHERIN_PREFECT,
    "Death Eater Initiate": DEATH_EATER_INITIATE,
    "Dementor": DEMENTOR,
    "Dementor Swarm": DEMENTOR_SWARM,
    "Inferius": INFERIUS,
    "Dark Wizard": DARK_WIZARD,
    "Knockturn Alley Vendor": KNOCKTURN_ALLEY_VENDOR,
    "Basilisk": BASILISK,
    "Acromantula": ACROMANTULA,
    "Azkaban Guard": AZKABAN_GUARD,

    # Black Spells
    "Avada Kedavra": AVADA_KEDAVRA,
    "Crucio": CRUCIO,
    "Imperio": IMPERIO,
    "Sectumsempra": SECTUMSEMPRA,
    "Morsmordre": MORSMORDRE,
    "Dark Mark": DARK_MARK,
    "Curse of the Bogies": CURSE_OF_THE_BOGIES,
    "Summon Inferi": SUMMON_INFERI,
    "Dark Ritual": DARK_RITUAL_SPELL,
    "Fiendfyre": FIENDFYRE,

    # Black Enchantments
    "The Dark Arts": THE_DARK_ARTS,
    "Slytherin Banner": SLYTHERIN_BANNER,
    "Horcrux Curse": HORCRUX_CURSE,

    # Red Legendaries
    "Ron Weasley, Loyal Friend": RON_WEASLEY,
    "Fred and George Weasley, Pranksters": FRED_AND_GEORGE,
    "Ginny Weasley, Fierce Duelist": GINNY_WEASLEY,
    "Sirius Black, Escaped Convict": SIRIUS_BLACK,
    "Molly Weasley, Protective Mother": MOLLY_WEASLEY,

    # Red Creatures
    "Weasley Twin Prankster": WEASLEY_TWIN_PRANKSTER,
    "Quidditch Beater": QUIDDITCH_BEATER,
    "Dragon Handler": DRAGON_HANDLER,
    "Hungarian Horntail": HUNGARIAN_HORNTAIL,
    "Norwegian Ridgeback": NORWEGIAN_RIDGEBACK,
    "Chinese Fireball": CHINESE_FIREBALL,
    "Common Welsh Green": COMMON_WELSH_GREEN,
    "Gringotts Goblin": GOBLIN_BANKER,
    "Fiendfyre Elemental": FIENDFYRE_ELEMENTAL,
    "Blast-Ended Skrewt": BLAST_ENDED_SKREWT,
    "Erumpent": ERUMPENT,

    # Red Spells
    "Incendio": INCENDIO,
    "Confringo": CONFRINGO,
    "Bombarda": BOMBARDA,
    "Reducto": REDUCTO,
    "Expulso": EXPULSO,
    "Dragon's Breath": DRAGONS_BREATH,
    "Weasley Firework": WEASLEY_FIREWORK,
    "Dragon's Fire": DRAGONS_FIRE,
    "Pyrotechnics": PYROTECHNICS,
    "Summon Dragon": SUMMON_DRAGON,

    # Red Enchantments
    "Weasleys' Wizard Wheezes": WEASLEYS_WIZARD_WHEEZES,
    "Gryffindor Courage": GRYFFINDOR_COURAGE,

    # Green Legendaries
    "Rubeus Hagrid, Keeper of Keys": RUBEUS_HAGRID,
    "Pomona Sprout, Herbology Master": POMONA_SPROUT,
    "Cedric Diggory, True Champion": CEDRIC_DIGGORY,
    "Newt Scamander, Magizoologist": NEWT_SCAMANDER,
    "Buckbeak": BUCKBEAK,
    "Fawkes the Phoenix": FAWKES_THE_PHOENIX,

    # Green Creatures
    "Hufflepuff Prefect": HUFFLEPUFF_PREFECT,
    "Mandrake": MANDRAKE,
    "Venomous Tentacula": VENOMOUS_TENTACULA,
    "Bowtruckle": BOWTRUCKLE,
    "Hippogriff": HIPPOGRIFF,
    "Unicorn": UNICORN,
    "Centaur Archer": CENTAUR_ARCHER,
    "Forbidden Forest Spider": FORBIDDEN_FOREST_SPIDER,
    "Niffler": NIFFLER,
    "Thestral Herd": THESTRAL_HERD,
    "Whomping Willow": WHOMPING_WILLOW,
    "Giant Squid of the Black Lake": GIANT_SQUID,

    # Green Spells
    "Herbivicus": HERBIVICUS,
    "Wild Growth": WILD_GROWTH_SPELL,
    "Engorgio": ENGORGIO,
    "Beast's Fury": BEASTS_FURY,
    "Nature's Protection": NATURES_PROTECTION,
    "Greenhouse Harvest": GREENHOUSE_HARVEST,
    "Creature Summoning": CREATURE_SUMMONING,
    "Mandrake Restorative": MANDRAKE_RESTORATIVE,

    # Green Enchantments
    "Herbology Classroom": HERBOLOGY_CLASSROOM,
    "Hufflepuff Banner": HUFFLEPUFF_BANNER,
    "Forbidden Forest": FORBIDDEN_FOREST,

    # Artifacts - Deathly Hallows
    "Elder Wand": ELDER_WAND,
    "Resurrection Stone": RESURRECTION_STONE,
    "Invisibility Cloak": INVISIBILITY_CLOAK,

    # Artifacts - Legendary Items
    "Sword of Gryffindor": SWORD_OF_GRYFFINDOR,
    "Marauder's Map": MARAUDERS_MAP,
    "Sorting Hat": SORTING_HAT,
    "Golden Snitch": GOLDEN_SNITCH,
    "Time-Turner": TIME_TURNER,
    "Goblet of Fire": GOBLET_OF_FIRE,
    "Mirror of Erised": MIRROR_OF_ERISED,
    "Deluminator": DELUMINATOR,

    # Artifacts - Horcruxes
    "Tom Riddle's Diary": HORCRUX_DIARY,
    "Slytherin's Locket": HORCRUX_LOCKET,
    "Hufflepuff's Cup": HORCRUX_CUP,
    "Ravenclaw's Diadem": HORCRUX_DIADEM,
    "Gaunt Family Ring": HORCRUX_RING,

    # Artifacts - Brooms and Equipment
    "Firebolt": FIREBOLT_BROOM,
    "Nimbus 2000": NIMBUS_2000,
    "Wand of Phoenix Feather": WAND_OF_PHOENIX_FEATHER,
    "Wand of Dragon Heartstring": WAND_OF_DRAGON_HEARTSTRING,
    "Wand of Unicorn Hair": WAND_OF_UNICORN_HAIR,

    # Artifacts - Misc
    "Pensieve": PENSIEVE,
    "Quaffle": QUAFFLE,
    "Bludger": BLUDGER,
    "Portkey": PORTKEY,
    "Floo Powder": FLOO_POWDER,
    "Vanishing Cabinet": VANISHING_CABINET,

    # Lands - Hogwarts
    "Hogwarts Castle": HOGWARTS_CASTLE,
    "Gryffindor Common Room": GRYFFINDOR_COMMON_ROOM,
    "Slytherin Dungeon": SLYTHERIN_DUNGEON,
    "Ravenclaw Tower": RAVENCLAW_TOWER,
    "Hufflepuff Basement": HUFFLEPUFF_BASEMENT,
    "Room of Requirement": ROOM_OF_REQUIREMENT,
    "Quidditch Pitch": QUIDDITCH_PITCH,

    # Lands - Locations
    "Diagon Alley": DIAGON_ALLEY,
    "Hogsmeade Village": HOGSMEADE_VILLAGE,
    "The Forbidden Forest": FORBIDDEN_FOREST_LAND,
    "Ministry of Magic": MINISTRY_OF_MAGIC,
    "Azkaban": AZKABAN,
    "Godric's Hollow": GODRICS_HOLLOW,
    "12 Grimmauld Place": GRIMMAULD_PLACE,
    "The Burrow": THE_BURROW,
    "Malfoy Manor": MALFOY_MANOR,
    "Knockturn Alley": KNOCKTURN_ALLEY,
    "Gringotts Bank": GRINGOTTS,
    "Shrieking Shack": SHRIEKING_SHACK,
    "Platform Nine and Three-Quarters": PLATFORM_NINE_THREE_QUARTERS,
}
