"""
Jujutsu Kaisen: Cursed Clash (JJK) Card Implementations

Set featuring ~250 cards.
Mechanics: Cursed Energy (life payment), Domain Expansion (enchantments), Binding Vow (trade-offs)
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
# JUJUTSU KAISEN KEYWORD MECHANICS
# =============================================================================

def make_cursed_energy(source_obj: GameObject, life_cost: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Cursed Energy - Pay N life to activate this ability.
    """
    def cursed_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'cursed_energy')

    def cursed_handler(event: Event, state: GameState) -> InterceptorResult:
        life_payment = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -life_cost},
            source=source_obj.id
        )
        effect_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_payment] + effect_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cursed_filter,
        handler=cursed_handler,
        duration='while_on_battlefield'
    )


def make_binding_vow(source_obj: GameObject, life_cost: int, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """
    Binding Vow - Pay N life: This creature gets +X/+Y until end of turn.
    Trade power for life.
    """
    def vow_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': source_obj.id,
                'counter_type': 'binding_vow_boost',
                'power': power_bonus,
                'toughness': toughness_bonus,
                'duration': 'end_of_turn'
            },
            source=source_obj.id
        )]

    return [make_cursed_energy(source_obj, life_cost, vow_effect)]


def make_domain_expansion_aura(source_obj: GameObject, effect_filter: Callable[[GameObject, GameState], bool],
                                power_mod: int = 0, toughness_mod: int = 0,
                                keywords: list[str] = None) -> list[Interceptor]:
    """
    Domain Expansion static effects for enchantments.
    """
    interceptors = []
    if power_mod != 0 or toughness_mod != 0:
        interceptors.extend(make_static_pt_boost(source_obj, power_mod, toughness_mod, effect_filter))
    if keywords:
        interceptors.append(make_keyword_grant(source_obj, keywords, effect_filter))
    return interceptors


def make_reverse_cursed_technique(source_obj: GameObject, heal_amount: int) -> Interceptor:
    """
    Reverse Cursed Technique - When this creature deals combat damage, gain that much life.
    """
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': heal_amount if heal_amount else amount},
            source=source_obj.id
        )]
    return make_damage_trigger(source_obj, damage_effect, combat_only=True)


def sorcerer_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Sorcerer creatures you control."""
    return creatures_with_subtype(source, "Sorcerer")


def curse_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Curse creatures you control."""
    return creatures_with_subtype(source, "Curse")


def shikigami_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Shikigami creatures you control."""
    return creatures_with_subtype(source, "Shikigami")


def student_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Student creatures you control."""
    return creatures_with_subtype(source, "Student")


# =============================================================================
# WHITE CARDS - JUJUTSU SORCERERS, PROTECTION, EXORCISM
# =============================================================================

# --- Legendary Creatures ---

def yuji_itadori_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sukuna's Vessel - Can have Sukuna cards attached. Binding Vow for power boost."""
    interceptors = []
    interceptors.extend(make_binding_vow(obj, 2, 2, 0))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': event.payload.get('defending_player'), 'amount': 1, 'source': obj.id},
            source=obj.id
        )]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

YUJI_ITADORI = make_creature(
    name="Yuji Itadori, Sukuna's Vessel",
    power=3, toughness=3,
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="Haste. Whenever Yuji attacks, he deals 1 damage to defending player. Binding Vow - Pay 2 life: Yuji gets +2/+0 until end of turn.",
    setup_interceptors=yuji_itadori_setup
)


def megumi_fushiguro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ten Shadows Technique - ETB create a Shikigami token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Divine Dog', 'power': 2, 'toughness': 2, 'colors': {Color.GREEN}, 'subtypes': {'Shikigami', 'Dog'}}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

MEGUMI_FUSHIGURO = make_creature(
    name="Megumi Fushiguro, Ten Shadows",
    power=2, toughness=3,
    mana_cost="{1}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="When Megumi enters, create a 2/2 green Shikigami Dog creature token named Divine Dog. Shikigami you control get +1/+0.",
    setup_interceptors=megumi_fushiguro_setup
)


def nobara_kugisaki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Straw Doll Technique - deals damage when she attacks"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'any_target', 'amount': 2, 'source': obj.id},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

NOBARA_KUGISAKI = make_creature(
    name="Nobara Kugisaki, Straw Doll",
    power=3, toughness=2,
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="First strike. Whenever Nobara attacks, she deals 2 damage to any target.",
    setup_interceptors=nobara_kugisaki_setup
)


def satoru_gojo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Infinity - Hexproof, can't be blocked by creatures with power less than his toughness"""
    interceptors = []

    def infinity_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id

    interceptors.append(make_keyword_grant(obj, ['hexproof'], infinity_filter))
    return interceptors

SATORU_GOJO = make_creature(
    name="Satoru Gojo, The Strongest",
    power=6, toughness=6,
    mana_cost="{3}{W}{U}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="Hexproof, flying. Infinity - Gojo can't be blocked by creatures with power 3 or less. Cursed Energy 3: Exile target creature.",
    setup_interceptors=satoru_gojo_setup
)


def aoi_todo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Boogie Woogie - swap positions with another creature when attacking"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

AOI_TODO = make_creature(
    name="Aoi Todo, Best Friend",
    power=5, toughness=4,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="Trample. Whenever Todo attacks, put a +1/+1 counter on him. Boogie Woogie - {2}: Exchange Todo with target creature you control. Activate only during combat.",
    setup_interceptors=aoi_todo_setup
)


# --- Regular White Creatures ---

def jujutsu_first_year_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB gain 2 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

JUJUTSU_FIRST_YEAR = make_creature(
    name="Jujutsu High First Year",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"},
    text="When Jujutsu High First Year enters, you gain 2 life.",
    setup_interceptors=jujutsu_first_year_setup
)


KYOTO_STUDENT = make_creature(
    name="Kyoto Jujutsu Student",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"},
    text="Vigilance."
)


def exorcist_sorcerer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Protection from Curses"""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['protection_curse'], self_filter)]

EXORCIST_SORCERER = make_creature(
    name="Exorcist Sorcerer",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="Protection from Curses.",
    setup_interceptors=exorcist_sorcerer_setup
)


def window_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Sorcerers get +0/+1"""
    return make_static_pt_boost(obj, 0, 1, other_creatures_with_subtype(obj, "Sorcerer"))

WINDOW_GUARDIAN = make_creature(
    name="Window Guardian",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="Defender. Other Sorcerer creatures you control get +0/+1.",
    setup_interceptors=window_guardian_setup
)


BARRIER_TECHNICIAN = make_creature(
    name="Barrier Technician",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="Creatures you control have ward {1}."
)


def temple_priest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lifelink"""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['lifelink'], self_filter)]

TEMPLE_PRIEST = make_creature(
    name="Temple Priest",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="Lifelink.",
    setup_interceptors=temple_priest_setup
)


CURSED_SPEECH_STUDENT = make_creature(
    name="Cursed Speech Student",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"},
    text="Cursed Energy 1: Tap target creature."
)


def holy_ward_monk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, exile target Curse"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={'target_type': 'Curse', 'to_zone_type': ZoneType.EXILE},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

HOLY_WARD_MONK = make_creature(
    name="Holy Ward Monk",
    power=2, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="When Holy Ward Monk enters, exile target Curse creature.",
    setup_interceptors=holy_ward_monk_setup
)


JUJUTSU_INSTRUCTOR = make_creature(
    name="Jujutsu High Instructor",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="Student creatures you control get +1/+1."
)


GUARDIAN_SHIKIGAMI = make_creature(
    name="Guardian Shikigami",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Shikigami"},
    text="Defender, vigilance."
)


def reverse_technique_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reverse Cursed Technique healing"""
    return [make_reverse_cursed_technique(obj, 0)]

REVERSE_TECHNIQUE_MASTER = make_creature(
    name="Reverse Technique Master",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="Lifelink. Whenever Reverse Technique Master deals combat damage, you gain that much life.",
    setup_interceptors=reverse_technique_master_setup
)


BINDING_OATH_ENFORCER = make_creature(
    name="Binding Oath Enforcer",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="When Binding Oath Enforcer enters, each player sacrifices an enchantment."
)


HEAVENLY_RESTRICTION_WARRIOR = make_creature(
    name="Heavenly Restriction Warrior",
    power=4, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="Heavenly Restriction Warrior can't be the target of spells or abilities you control. First strike."
)


# =============================================================================
# BLUE CARDS - GOJO, INFINITY, TECHNIQUE MASTERY
# =============================================================================

# --- Legendary Creatures ---

def yuta_okkotsu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Copy - can use abilities of other Sorcerers"""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, spell_cast_effect)]

YUTA_OKKOTSU = make_creature(
    name="Yuta Okkotsu, Rika's Beloved",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, put a +1/+1 counter on Yuta. Copy - {2}{U}: Copy target activated ability of a Sorcerer you control.",
    setup_interceptors=yuta_okkotsu_setup
)


def toge_inumaki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cursed Speech - tap ability"""
    def cursed_speech_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP,
            payload={'target_type': 'creature'},
            source=obj.id
        )]
    return [make_cursed_energy(obj, 2, cursed_speech_effect)]

TOGE_INUMAKI = make_creature(
    name="Toge Inumaki, Cursed Speech",
    power=2, toughness=2,
    mana_cost="{1}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="Cursed Speech - Cursed Energy 2: Tap target creature. It doesn't untap during its controller's next untap step.",
    setup_interceptors=toge_inumaki_setup
)


def geto_suguru_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Curse Manipulation - gains control of Curses"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Absorbed Curse', 'power': 2, 'toughness': 2, 'colors': {Color.BLACK}, 'subtypes': {'Curse'}}
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

GETO_SUGURU = make_creature(
    name="Geto Suguru, Curse Manipulator",
    power=4, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="When a Curse creature dies, create a 2/2 black Curse creature token. Curse Manipulation - {3}: Gain control of target Curse creature.",
    setup_interceptors=geto_suguru_setup
)


MASAMICHI_YAGA = make_creature(
    name="Masamichi Yaga, Principal",
    power=3, toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="Cursed Corpse creatures you control get +1/+1. {2}{U}: Create a 2/2 colorless Cursed Corpse artifact creature token."
)


KENTO_NANAMI = make_creature(
    name="Kento Nanami, Ratio Technique",
    power=4, toughness=3,
    mana_cost="{2}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="First strike. Ratio Technique - Whenever Nanami deals combat damage, that damage is doubled if it's exactly 7."
)


# --- Regular Blue Creatures ---

def technique_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB scry 2"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

TECHNIQUE_ANALYST = make_creature(
    name="Technique Analyst",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="When Technique Analyst enters, scry 2.",
    setup_interceptors=technique_analyst_setup
)


INFINITY_APPRENTICE = make_creature(
    name="Infinity Apprentice",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer", "Student"},
    text="Hexproof from creatures with power 4 or greater."
)


def cursed_energy_sensor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Draws when opponent casts a spell"""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        if event.payload.get('caster') != obj.controller:
            return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
        return []
    return [make_spell_cast_trigger(obj, spell_effect, controller_only=False)]

CURSED_ENERGY_SENSOR = make_creature(
    name="Cursed Energy Sensor",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Whenever an opponent casts a spell, you may draw a card.",
    setup_interceptors=cursed_energy_sensor_setup
)


SIX_EYES_PRODIGY = make_creature(
    name="Six Eyes Prodigy",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Your spells cost {1} less to cast. You may look at the top card of your library at any time."
)


ILLUSION_CASTER = make_creature(
    name="Illusion Caster",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="When Illusion Caster enters, create a token that's a copy of it. Exile that token at end of turn."
)


CURSED_TECHNIQUE_THIEF = make_creature(
    name="Cursed Technique Thief",
    power=3, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="When Cursed Technique Thief deals combat damage to a player, copy target instant or sorcery spell that player cast this turn."
)


DOMAIN_RESEARCHER = make_creature(
    name="Domain Researcher",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Enchantments you control have hexproof."
)


LIMITLESS_STUDENT = make_creature(
    name="Limitless Student",
    power=2, toughness=2,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer", "Student"},
    text="Limitless Student can't be blocked."
)


SPATIAL_MANIPULATOR = make_creature(
    name="Spatial Manipulator",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="{U}, {T}: Return target creature to its owner's hand."
)


TECHNIQUE_REVERSAL_MAGE = make_creature(
    name="Technique Reversal Mage",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Flash. When Technique Reversal Mage enters, counter target ability."
)


NEW_SHADOW_PRACTITIONER = make_creature(
    name="New Shadow Practitioner",
    power=3, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="New Shadow Style - {2}: New Shadow Practitioner gets +2/+0 until end of turn."
)


SIMPLE_DOMAIN_MASTER = make_creature(
    name="Simple Domain Master",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Simple Domain - Domain Expansion enchantments don't affect Simple Domain Master."
)


# =============================================================================
# BLACK CARDS - CURSES, SUKUNA, MALEVOLENCE
# =============================================================================

# --- Legendary Creatures ---

def ryomen_sukuna_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """King of Curses - Incredibly powerful, ETB destroy creatures"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DESTROY,
            payload={'target_type': 'creature', 'amount': 2},
            source=obj.id
        )]
    interceptors = [make_etb_trigger(obj, etb_effect)]
    interceptors.extend(make_binding_vow(obj, 3, 4, 0))
    return interceptors

RYOMEN_SUKUNA = make_creature(
    name="Ryomen Sukuna, King of Curses",
    power=7, toughness=6,
    mana_cost="{4}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Avatar"},
    supertypes={"Legendary"},
    text="Double strike. When Sukuna enters, destroy up to two target creatures. Binding Vow - Pay 3 life: Sukuna gets +4/+0 until end of turn.",
    setup_interceptors=ryomen_sukuna_setup
)


def mahito_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Idle Transfiguration - can transform creatures"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'target': event.payload.get('target'), 'counter_type': '-1/-1', 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect)]

MAHITO = make_creature(
    name="Mahito, Soul Sculptor",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    supertypes={"Legendary"},
    text="Idle Transfiguration - Whenever Mahito deals damage to a creature, put a -1/-1 counter on that creature. {2}{B}: Transform target creature you control into a 3/3 black Horror.",
    setup_interceptors=mahito_setup
)


def jogo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fire curse - deals damage on attack"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'each_opponent', 'amount': 2, 'source': obj.id},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

JOGO = make_creature(
    name="Jogo, Volcano Curse",
    power=5, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Elemental"},
    supertypes={"Legendary"},
    text="Haste. Whenever Jogo attacks, he deals 2 damage to each opponent. Cursed Energy 2: Jogo deals 3 damage to any target.",
    setup_interceptors=jogo_setup
)


def hanami_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Nature curse - regenerates"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]

HANAMI = make_creature(
    name="Hanami, Forest Curse",
    power=4, toughness=5,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Curse", "Elemental"},
    supertypes={"Legendary"},
    text="Reach. At the beginning of your upkeep, put a +1/+1 counter on Hanami. {G}: Regenerate Hanami.",
    setup_interceptors=hanami_setup
)


def dagon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ocean curse - unblockable"""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['unblockable'], self_filter)]

DAGON = make_creature(
    name="Dagon, Ocean Curse",
    power=5, toughness=5,
    mana_cost="{3}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Curse", "Elemental"},
    supertypes={"Legendary"},
    text="Dagon can't be blocked. When Dagon enters, return up to two target creatures to their owners' hands.",
    setup_interceptors=dagon_setup
)


# --- Regular Black Creatures ---

def finger_bearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB each player loses 2 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': player_id, 'amount': -2}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]

FINGER_BEARER = make_creature(
    name="Finger Bearer",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="When Finger Bearer enters, each player loses 2 life.",
    setup_interceptors=finger_bearer_setup
)


CURSED_WOMB = make_creature(
    name="Cursed Womb",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="When Cursed Womb dies, create two 1/1 black Curse creature tokens."
)


VENGEFUL_SPIRIT = make_creature(
    name="Vengeful Cursed Spirit",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Curse"},
    text="Menace. When Vengeful Cursed Spirit dies, target player loses 2 life."
)


DISEASE_CURSE = make_creature(
    name="Disease Curse",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="Deathtouch. Other Curse creatures you control have deathtouch."
)


GRASSHOPPER_CURSE = make_creature(
    name="Grasshopper Curse",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Curse", "Insect"},
    text="Flying. When Grasshopper Curse dies, each opponent loses 1 life."
)


FLY_HEAD_CURSE = make_creature(
    name="Fly Head Curse",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="Flying, haste. At the beginning of your end step, sacrifice Fly Head Curse."
)


RESENTFUL_CURSE = make_creature(
    name="Resentful Curse",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="When Resentful Curse enters, target opponent discards a card."
)


SPECIAL_GRADE_CURSE = make_creature(
    name="Special Grade Curse",
    power=6, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="Menace. Other Curse creatures you control get +1/+1."
)


MALEVOLENT_SHRINE_KEEPER = make_creature(
    name="Malevolent Shrine Keeper",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse", "Cleric"},
    text="At the beginning of your upkeep, you may pay 2 life. If you do, draw a card."
)


IDLE_TRANSFIGURATION_VICTIM = make_creature(
    name="Transfigured Human",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Curse", "Horror"},
    text="Transfigured Human can't block."
)


CURSED_CORPSE = make_creature(
    name="Cursed Corpse",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct"},
    text="Cursed Corpse is all colors."
)


GRADE_ONE_CURSE = make_creature(
    name="Grade One Curse",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="Binding Vow - Pay 2 life: Grade One Curse gets +2/+0 until end of turn."
)


SMALLPOX_CURSE = make_creature(
    name="Smallpox Curse",
    power=2, toughness=1,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="When Smallpox Curse enters, each player sacrifices a creature and discards a card."
)


CURSE_USER = make_creature(
    name="Curse User",
    power=2, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When Curse User enters, you may search your library for a Curse creature card, reveal it, and put it into your hand."
)


# =============================================================================
# RED CARDS - COMBAT TECHNIQUES, DESTRUCTION
# =============================================================================

# --- Legendary Creatures ---

def maki_zenin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Heavenly Restriction - no cursed energy but enhanced physical"""
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['first_strike', 'vigilance'], self_filter)]

MAKI_ZENIN = make_creature(
    name="Maki Zenin, Heavenly Pact",
    power=4, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Maki Zenin can't be the target of Cursed Energy abilities. Equipped creatures you control get +1/+0.",
    setup_interceptors=maki_zenin_setup
)


def choso_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Blood Manipulation - deals damage based on life paid"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'defending_player', 'amount': 2, 'source': obj.id},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

CHOSO = make_creature(
    name="Choso, Death Painting",
    power=4, toughness=4,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Curse", "Human"},
    supertypes={"Legendary"},
    text="Blood Manipulation - Whenever Choso attacks, he deals 2 damage to defending player. Cursed Energy 3: Choso deals 3 damage to any target.",
    setup_interceptors=choso_setup
)


def toji_fushiguro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sorcerer Killer - bonus against Sorcerers"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'boost', 'power': 3, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

TOJI_FUSHIGURO = make_creature(
    name="Toji Fushiguro, Sorcerer Killer",
    power=5, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="First strike. Toji gets +3/+0 when attacking a player who controls a Sorcerer. Heavenly Restriction - Toji can't be targeted by abilities that cost life to activate.",
    setup_interceptors=toji_fushiguro_setup
)


NAOBITO_ZENIN = make_creature(
    name="Naobito Zenin, Projection",
    power=4, toughness=3,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="Haste. Projection Sorcery - {R}: Naobito can't be blocked this turn. Activate only once per turn."
)


KAMO_NORITOSHI = make_creature(
    name="Kamo Noritoshi, Blood Wielder",
    power=3, toughness=3,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="Cursed Energy 1: Kamo deals 1 damage to any target. This damage can't be prevented."
)


# --- Regular Red Creatures ---

def berserker_sorcerer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +2/+0 when attacking"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'boost', 'power': 2, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

BERSERKER_SORCERER = make_creature(
    name="Berserker Sorcerer",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="Whenever Berserker Sorcerer attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=berserker_sorcerer_setup
)


CURSED_TECHNIQUE_STRIKER = make_creature(
    name="Cursed Technique Striker",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="Haste. Cursed Energy 1: Cursed Technique Striker gets +2/+0 until end of turn."
)


BLACK_FLASH_USER = make_creature(
    name="Black Flash User",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="Black Flash - Whenever Black Flash User deals combat damage, it deals that much damage again to the same target."
)


DISASTER_FLAME_CASTER = make_creature(
    name="Disaster Flame Caster",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Curse", "Shaman"},
    text="When Disaster Flame Caster enters, it deals 3 damage to any target."
)


BLOOD_ARROW_ARCHER = make_creature(
    name="Blood Arrow Archer",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="{T}, Pay 1 life: Blood Arrow Archer deals 2 damage to any target."
)


ZENIN_CLAN_WARRIOR = make_creature(
    name="Zenin Clan Warrior",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="First strike. Zenin Clan Warrior can't block."
)


PLAYFUL_CLOUD_WIELDER = make_creature(
    name="Playful Cloud Wielder",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Trample. Equipped with Playful Cloud, this creature gets +2/+2."
)


CURSED_ENERGY_BOMB = make_creature(
    name="Cursed Energy Bomb",
    power=4, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Curse", "Elemental"},
    text="When Cursed Energy Bomb dies, it deals 4 damage to target creature or player."
)


MAXIMUM_OUTPUT_FIGHTER = make_creature(
    name="Maximum Output Fighter",
    power=5, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="Binding Vow - Pay 3 life: Maximum Output Fighter gets +3/+0 and gains trample until end of turn."
)


CLEAVE_PRACTITIONER = make_creature(
    name="Cleave Practitioner",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="Cleave - {R}: Target creature gets -X/-0 until end of turn, where X is Cleave Practitioner's power."
)


METEOR_CURSE = make_creature(
    name="Meteor Curse",
    power=5, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Curse", "Elemental"},
    text="Trample. When Meteor Curse enters, it deals 2 damage to each creature."
)


DOMAIN_AMPLIFIER = make_creature(
    name="Domain Amplifier",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="Domain Expansion enchantments you control have 'At the beginning of your upkeep, this deals 1 damage to each opponent.'"
)


# =============================================================================
# GREEN CARDS - SHIKIGAMI, SUMMONING, NATURE CURSES
# =============================================================================

# --- Legendary Creatures ---

def panda_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Core switching - can change forms"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

PANDA = make_creature(
    name="Panda, Cursed Corpse",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Construct", "Panda"},
    supertypes={"Legendary"},
    text="Trample. Whenever Panda deals combat damage, put a +1/+1 counter on it. Gorilla Mode - {2}{G}: Panda gets +3/+0 until end of turn.",
    setup_interceptors=panda_setup
)


def mahoraga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Adapts to threats"""
    def damage_taken_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'adaptation', 'amount': 1},
            source=obj.id
        )]
    # Simplified - triggers when this creature takes damage
    return []

MAHORAGA = make_creature(
    name="Mahoraga, Eight-Handled Sword",
    power=8, toughness=8,
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Divine"},
    supertypes={"Legendary"},
    text="Trample, indestructible. Adaptation - Whenever Mahoraga survives damage, put an adaptation counter on it. Mahoraga has protection from sources that have dealt damage to it.",
    setup_interceptors=mahoraga_setup
)


def divine_dog_totality_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combined form of Divine Dogs"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'any', 'amount': 2, 'source': obj.id},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

DIVINE_DOG_TOTALITY = make_creature(
    name="Divine Dog: Totality",
    power=5, toughness=4,
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Shikigami", "Dog"},
    supertypes={"Legendary"},
    text="Menace. Whenever Divine Dog: Totality attacks, it deals 2 damage to target creature.",
    setup_interceptors=divine_dog_totality_setup
)


NUE_SHIKIGAMI = make_creature(
    name="Nue, Thunder Shikigami",
    power=3, toughness=2,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Shikigami", "Bird"},
    supertypes={"Legendary"},
    text="Flying. When Nue enters, tap target creature an opponent controls."
)


RABBIT_ESCAPE = make_creature(
    name="Rabbit Escape Swarm",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Rabbit"},
    supertypes={"Legendary"},
    text="When Rabbit Escape Swarm enters, create three 1/1 green Shikigami Rabbit creature tokens."
)


# --- Regular Green Creatures ---

def divine_dog_white_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB search for another Dog"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH,
            payload={'player': obj.controller, 'type': 'Dog'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

DIVINE_DOG_WHITE = make_creature(
    name="Divine Dog: White",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Dog"},
    text="When Divine Dog: White enters, you may search your library for a Dog creature card and reveal it.",
    setup_interceptors=divine_dog_white_setup
)


DIVINE_DOG_BLACK = make_creature(
    name="Divine Dog: Black",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Dog"},
    text="When Divine Dog: Black dies, you may return target Shikigami card from your graveyard to your hand."
)


TOAD_SHIKIGAMI = make_creature(
    name="Toad Shikigami",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Frog"},
    text="Reach. {G}: Toad Shikigami gets +1/+0 until end of turn."
)


MAX_ELEPHANT = make_creature(
    name="Max Elephant",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Elephant"},
    text="Trample. When Max Elephant enters, you may have it deal 3 damage to target creature."
)


GREAT_SERPENT = make_creature(
    name="Great Serpent Shikigami",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Snake"},
    text="Deathtouch. Great Serpent Shikigami can block creatures with flying."
)


def shikigami_summoner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shikigami get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, creatures_with_subtype(obj, "Shikigami"))

SHIKIGAMI_SUMMONER = make_creature(
    name="Shikigami Summoner",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    text="Shikigami creatures you control get +1/+1.",
    setup_interceptors=shikigami_summoner_setup
)


FOREST_SPIRIT_CURSE = make_creature(
    name="Forest Spirit Curse",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Spirit"},
    text="Hexproof. {G}: Forest Spirit Curse gets +1/+1 until end of turn."
)


CURSED_BUD = make_creature(
    name="Cursed Bud",
    power=0, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Plant"},
    text="Defender. {T}: Add {G}. At the beginning of your upkeep, put a +1/+1 counter on Cursed Bud."
)


NATURE_CURSE_SPAWN = make_creature(
    name="Nature Curse Spawn",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Elemental"},
    text="When Nature Curse Spawn dies, create a 1/1 green Curse creature token."
)


CHIMERA_DEATH_PAINTING = make_creature(
    name="Chimera Death Painting",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Chimera"},
    text="Trample. Chimera Death Painting has all creature types in addition to its other types."
)


WHEEL_SHIKIGAMI = make_creature(
    name="Wheel Shikigami",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Construct"},
    text="Whenever another Shikigami enters under your control, untap Wheel Shikigami."
)


ROUND_DEER = make_creature(
    name="Round Deer Shikigami",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Elk"},
    text="Healing - When Round Deer enters, you gain 4 life."
)


TIGER_FUNERAL = make_creature(
    name="Tiger Funeral Shikigami",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Cat"},
    text="Haste. When Tiger Funeral dies, draw a card."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

SUKUNA_FINGER = make_creature(
    name="Sukuna's Finger",
    power=0, toughness=1,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Horror"},
    text="Indestructible. {3}{B}{R}, Sacrifice Sukuna's Finger: Target creature you control gets +4/+4 and gains menace until end of turn."
)


RIKA_ORIMOTO = make_creature(
    name="Rika Orimoto, Cursed Queen",
    power=6, toughness=6,
    mana_cost="{4}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Spirit", "Curse"},
    supertypes={"Legendary"},
    text="Flying. Whenever Rika deals combat damage, you may copy target instant or sorcery spell. You may choose new targets for the copy."
)


DOMAIN_CLASHING_SORCERERS = make_creature(
    name="Domain-Clashing Sorcerers",
    power=4, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Sorcerer"},
    text="Whenever an enchantment enters under your control, Domain-Clashing Sorcerers deals 2 damage to any target."
)


MEI_MEI = make_creature(
    name="Mei Mei, Crow Controller",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="Flying. Black Bird Manipulation - {3}: Create a 1/1 black Bird creature token with flying. When this token dies, draw a card."
)


SUGURU_GETO_CORRUPTED = make_creature(
    name="Kenjaku, Brain Stealer",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="When Kenjaku enters, gain control of target creature until end of turn. Untap it. It gains haste. At end of turn, sacrifice it."
)


URAUME = make_creature(
    name="Uraume, Ice Servant",
    power=3, toughness=4,
    mana_cost="{2}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="Ice Formation - {2}{U}: Tap target creature. It doesn't untap during its controller's next untap step."
)


# =============================================================================
# INSTANTS - CURSED TECHNIQUES
# =============================================================================

DIVERGENT_FIST = make_instant(
    name="Divergent Fist",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 until end of turn. If you control a Sorcerer, that creature also gains first strike until end of turn."
)


BLACK_FLASH = make_instant(
    name="Black Flash",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Target creature deals damage equal to twice its power to any target."
)


HOLLOW_PURPLE = make_instant(
    name="Hollow Purple",
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Exile target creature. Hollow Purple deals 5 damage to that creature's controller."
)


REVERSAL_RED = make_instant(
    name="Reversal: Red",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Deal 4 damage to target creature or planeswalker. If it would die this turn, exile it instead."
)


LAPSE_BLUE = make_instant(
    name="Lapse: Blue",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. That player can't cast creature spells until end of turn."
)


DOMAIN_AMPLIFICATION = make_instant(
    name="Domain Amplification",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}. If you control an enchantment, counter that spell instead."
)


CURSED_ENERGY_DRAIN = make_instant(
    name="Cursed Energy Drain",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. You gain 2 life."
)


IDLE_TRANSFIGURATION = make_instant(
    name="Idle Transfiguration",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller creates a 3/3 black Horror creature token."
)


CLEAVE = make_instant(
    name="Cleave",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy target creature with toughness 3 or less."
)


DISMANTLE = make_instant(
    name="Dismantle",
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy target creature. Its controller loses life equal to that creature's power."
)


EXORCISM_RITE = make_instant(
    name="Exorcism Rite",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Exile target Curse creature. You gain life equal to its power."
)


SIMPLE_DOMAIN = make_instant(
    name="Simple Domain",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Until end of turn, enchantments don't affect creatures you control. Draw a card."
)


FALLING_BLOSSOM_EMOTION = make_instant(
    name="Falling Blossom Emotion",
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Counter target spell that targets a creature you control. Draw a card."
)


MAXIMUM_UZUMAKI = make_instant(
    name="Maximum: Uzumaki",
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    text="Sacrifice any number of Curse creatures. For each creature sacrificed this way, destroy target creature."
)


RESONANCE = make_instant(
    name="Resonance",
    mana_cost="{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Deal 3 damage to target creature or player. If you control a Sorcerer, deal 4 damage instead."
)


HAIRPIN = make_instant(
    name="Hairpin",
    mana_cost="{R}",
    colors={Color.RED},
    text="Hairpin deals 2 damage to target creature. If that creature would die this turn, exile it instead."
)


STRAW_DOLL_TECHNIQUE = make_instant(
    name="Straw Doll Technique",
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Deal 3 damage to target creature. That creature's controller takes 3 damage."
)


BLOOD_MANIPULATION = make_instant(
    name="Blood Manipulation",
    mana_cost="{R}{B}",
    colors={Color.RED, Color.BLACK},
    text="Pay any amount of life. Deal that much damage to target creature."
)


SUPERNOVA = make_instant(
    name="Maximum: Meteor",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Deal 6 damage to each creature and each player."
)


TEN_SHADOWS_SUMMON = make_instant(
    name="Ten Shadows: Summon",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a 2/2 green Shikigami creature token. If you control Megumi, create two tokens instead."
)


INHERITED_TECHNIQUE = make_instant(
    name="Inherited Technique",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If it's a Shikigami, it also gains trample."
)


CURSED_BUD_GROWTH = make_instant(
    name="Cursed Bud Growth",
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    text="Create two 1/1 green Curse Plant creature tokens with 'Sacrifice this creature: Add {G}.'"
)


REVERSE_CURSED_TECHNIQUE = make_instant(
    name="Reverse Cursed Technique",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. If you have 10 or less life, gain 6 life instead."
)


BINDING_VOW_INSTANT = make_instant(
    name="Binding Vow",
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="As an additional cost, pay 3 life. Target creature gets +4/+4 until end of turn."
)


CURSED_TECHNIQUE_LAPSE = make_instant(
    name="Cursed Technique Lapse",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target activated ability. If that ability's source is a Curse, exile it."
)


DOMAIN_NEGATION = make_instant(
    name="Domain Negation",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. If it was an enchantment spell, draw a card."
)


CURSE_ABSORPTION = make_instant(
    name="Curse Absorption",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target Curse creature. Create a 2/2 black Curse creature token."
)


PROJECTION_SORCERY = make_instant(
    name="Projection Sorcery",
    mana_cost="{R}{U}",
    colors={Color.RED, Color.BLUE},
    text="Target creature gains haste and can't be blocked this turn. Draw a card."
)


# =============================================================================
# SORCERIES
# =============================================================================

SHIBUYA_INCIDENT = make_sorcery(
    name="Shibuya Incident",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Each player sacrifices two creatures. Create a 4/4 black Curse creature token."
)


CULLING_GAME = make_sorcery(
    name="Culling Game",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each player sacrifices a creature. If a Sorcerer was sacrificed this way, draw two cards."
)


NIGHT_PARADE = make_sorcery(
    name="Night Parade of a Hundred Demons",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Create X 2/2 black Curse creature tokens, where X is the number of Curses you control."
)


JUJUTSU_HIGH_TRAINING = make_sorcery(
    name="Jujutsu High Training",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on each Sorcerer creature you control. You gain 2 life."
)


KYOTO_GOODWILL_EVENT = make_sorcery(
    name="Kyoto Goodwill Event",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Draw three cards, then discard two cards. Create a 2/2 white Sorcerer Student creature token."
)


CURSE_PURIFICATION = make_sorcery(
    name="Curse Purification",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Exile all Curse creatures. You gain 2 life for each creature exiled this way."
)


DOMAIN_COLLAPSE = make_sorcery(
    name="Domain Collapse",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Destroy all enchantments. For each enchantment destroyed, its controller draws a card."
)


UNLIMITED_VOID_BURST = make_sorcery(
    name="Unlimited Void Burst",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Tap all creatures. Those creatures don't untap during their controllers' next untap steps."
)


SHIKIGAMI_ARMY = make_sorcery(
    name="Shikigami Army",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Create four 2/2 green Shikigami creature tokens."
)


CURSE_GENESIS = make_sorcery(
    name="Curse Genesis",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two Curse creature cards from your graveyard to your hand."
)


MASSACRE = make_sorcery(
    name="Divine Flame",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Deal 4 damage to each creature. If you control Jogo, deal 6 damage instead."
)


TECHNIQUE_MASTERY = make_sorcery(
    name="Technique Mastery",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Scry 3, then draw two cards."
)


SOUL_MULTIPLICITY = make_sorcery(
    name="Soul Multiplicity",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Create X 2/2 black Curse creature tokens. You lose X life."
)


# =============================================================================
# ENCHANTMENTS - DOMAIN EXPANSIONS
# =============================================================================

def malevolent_shrine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sukuna's Domain - deals damage to all creatures each upkeep"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, target in state.objects.items():
            if CardType.CREATURE in target.characteristics.types and target.zone == ZoneType.BATTLEFIELD:
                if target.controller != obj.controller:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': obj_id, 'amount': 2, 'source': obj.id},
                        source=obj.id
                    ))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

MALEVOLENT_SHRINE = make_enchantment(
    name="Malevolent Shrine",
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Domain"},
    text="Domain Expansion - At the beginning of your upkeep, Malevolent Shrine deals 2 damage to each creature your opponents control.",
    setup_interceptors=malevolent_shrine_setup
)


def unlimited_void_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gojo's Domain - opponents can't cast spells during your turn"""
    return []

UNLIMITED_VOID = make_enchantment(
    name="Unlimited Void",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Domain"},
    text="Domain Expansion - Opponents can't cast spells during your turn. Creatures your opponents control don't untap during their controllers' untap steps.",
    setup_interceptors=unlimited_void_setup
)


def chimera_shadow_garden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Megumi's Domain - Shikigami get +2/+2"""
    return make_static_pt_boost(obj, 2, 2, creatures_with_subtype(obj, "Shikigami"))

CHIMERA_SHADOW_GARDEN = make_enchantment(
    name="Chimera Shadow Garden",
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Domain"},
    text="Domain Expansion - Shikigami creatures you control get +2/+2 and have deathtouch.",
    setup_interceptors=chimera_shadow_garden_setup
)


def self_embodiment_of_perfection_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mahito's Domain - can transform creatures"""
    return []

SELF_EMBODIMENT_OF_PERFECTION = make_enchantment(
    name="Self-Embodiment of Perfection",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Domain"},
    text="Domain Expansion - Creatures your opponents control get -1/-1. {2}{B}: Target creature becomes a 1/1 black Horror with no abilities.",
    setup_interceptors=self_embodiment_of_perfection_setup
)


def coffin_of_the_iron_mountain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jogo's Domain - deals damage when creatures enter"""
    def etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return True

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        creature_id = event.payload.get('object_id')
        creature = state.objects.get(creature_id)
        if creature and creature.controller != obj.controller:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': creature_id, 'amount': 3, 'source': obj.id},
                source=obj.id
            )]
        return []

    return [make_etb_trigger(obj, effect_fn, etb_filter)]

COFFIN_OF_THE_IRON_MOUNTAIN = make_enchantment(
    name="Coffin of the Iron Mountain",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Domain"},
    text="Domain Expansion - Whenever a creature enters the battlefield under an opponent's control, Coffin of the Iron Mountain deals 3 damage to it.",
    setup_interceptors=coffin_of_the_iron_mountain_setup
)


def horizon_of_the_captivating_skandha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dagon's Domain - creates Fish tokens"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Shikigami Fish', 'power': 1, 'toughness': 1, 'colors': {Color.BLUE}, 'subtypes': {'Shikigami', 'Fish'}}
            },
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]

HORIZON_OF_CAPTIVATING_SKANDHA = make_enchantment(
    name="Horizon of the Captivating Skandha",
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Domain"},
    text="Domain Expansion - At the beginning of your upkeep, create a 1/1 blue Shikigami Fish creature token. Fish creatures you control can't be blocked.",
    setup_interceptors=horizon_of_the_captivating_skandha_setup
)


def shining_sea_of_flowers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hanami's Domain - creates Plant tokens"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

SHINING_SEA_OF_FLOWERS = make_enchantment(
    name="Shining Sea of Flowers",
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Domain"},
    text="Domain Expansion - At the beginning of your upkeep, you gain 2 life. Creatures you control have hexproof.",
    setup_interceptors=shining_sea_of_flowers_setup
)


AUTHENTIC_MUTUAL_LOVE = make_enchantment(
    name="Authentic Mutual Love",
    mana_cost="{4}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Domain"},
    text="Domain Expansion - Creatures you control have 'Whenever this creature deals damage to a creature, copy target instant or sorcery spell.'"
)


TIME_CELL_MOON_PALACE = make_enchantment(
    name="Time Cell Moon Palace",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Domain"},
    text="Domain Expansion - At the beginning of each opponent's upkeep, that player skips their combat phase."
)


DEADLY_SENTENCING = make_enchantment(
    name="Deadly Sentencing",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Domain"},
    text="Domain Expansion - Whenever a creature deals combat damage to you, destroy that creature."
)


# --- Other Enchantments ---

CURSED_ENERGY_FLOW = make_enchantment(
    name="Cursed Energy Flow",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, you may pay 1 life. If you do, draw a card."
)


BINDING_CONTRACT = make_enchantment(
    name="Binding Contract",
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="When Binding Contract enters, each player chooses a creature they control. Those creatures can't attack or block as long as Binding Contract remains on the battlefield."
)


HEAVENLY_RESTRICTION = make_enchantment(
    name="Heavenly Restriction",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature. Enchanted creature gets +3/+3 but can't be the target of spells or abilities."
)


CURSED_SPEECH_SEAL = make_enchantment(
    name="Cursed Speech Seal",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature. Enchanted creature can't attack or block. {2}: Return Cursed Speech Seal to its owner's hand."
)


BARRIER_TECHNIQUE = make_enchantment(
    name="Barrier Technique",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control have hexproof from black."
)


CURSED_WOMB_DEATH_PAINTING = make_enchantment(
    name="Cursed Womb: Death Painting",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, create a 1/1 black Curse creature token. You lose 1 life."
)


JUJUTSU_REGULATIONS = make_enchantment(
    name="Jujutsu Regulations",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Players can't cast more than two spells each turn. Whenever a player casts a third spell, counter it."
)


VEIL_TECHNIQUE = make_enchantment(
    name="Veil Technique",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Creatures you control can't be blocked by creatures with power 3 or greater."
)


CURSE_PURGE = make_enchantment(
    name="Curse Purge",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Whenever a Curse creature dies, exile it. You gain 1 life."
)


# =============================================================================
# EQUIPMENT - CURSED TOOLS
# =============================================================================

def inverted_spear_of_heaven_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Nullifies cursed techniques"""
    return []

INVERTED_SPEAR_OF_HEAVEN = make_equipment(
    name="Inverted Spear of Heaven",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has 'Damage dealt by this creature can't be prevented.' Equipped creature has protection from instants.",
    equip_cost="{2}",
    subtypes={"Cursed"},
    setup_interceptors=inverted_spear_of_heaven_setup
)


PLAYFUL_CLOUD = make_equipment(
    name="Playful Cloud",
    mana_cost="{2}",
    text="Equipped creature gets +3/+0. Whenever equipped creature deals combat damage, untap it.",
    equip_cost="{1}",
    subtypes={"Cursed"}
)


SLAUGHTER_DEMON = make_equipment(
    name="Slaughter Demon",
    mana_cost="{4}",
    text="Equipped creature gets +4/+0 and has first strike. At the beginning of your upkeep, you lose 1 life.",
    equip_cost="{2}",
    subtypes={"Cursed"}
)


SPLIT_SOUL_KATANA = make_equipment(
    name="Split Soul Katana",
    mana_cost="{2}",
    text="Equipped creature gets +2/+1. Whenever equipped creature deals combat damage to a player, that player discards a card.",
    equip_cost="{1}",
    subtypes={"Cursed"}
)


DRAGON_BONE = make_equipment(
    name="Dragon-Bone",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2 and has reach. {2}: Equipped creature deals 1 damage to target creature with flying.",
    equip_cost="{2}",
    subtypes={"Cursed"}
)


FESTERING_LIFE_SWORD = make_equipment(
    name="Festering Life Sword",
    mana_cost="{2}{B}",
    text="Equipped creature gets +2/+0 and has deathtouch. Whenever equipped creature deals damage, you gain that much life.",
    equip_cost="{2}",
    subtypes={"Cursed"}
)


BLACK_ROPE = make_equipment(
    name="Black Rope",
    mana_cost="{1}",
    text="Equipped creature gets +1/+0 and has 'Whenever this creature deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step.'",
    equip_cost="{1}",
    subtypes={"Cursed"}
)


GLASSES_OF_PERCEPTION = make_equipment(
    name="Glasses of Perception",
    mana_cost="{1}",
    text="Equipped creature has 'You may look at the top card of your library at any time.' {T}: Scry 1.",
    equip_cost="{1}"
)


MEGUMI_KNIFE = make_equipment(
    name="Megumi's Knife",
    mana_cost="{1}",
    text="Equipped creature gets +1/+1. If equipped creature is a Shikigami, it gets +2/+2 instead.",
    equip_cost="{1}"
)


MAKI_GLASSES = make_equipment(
    name="Maki's Glasses",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1 and can block creatures with hexproof as though they didn't have hexproof.",
    equip_cost="{1}"
)


CURSED_TOOL_COLLECTION = make_equipment(
    name="Cursed Tool Collection",
    mana_cost="{3}",
    text="Equipped creature gets +1/+1 for each Equipment attached to creatures you control.",
    equip_cost="{2}",
    subtypes={"Cursed"}
)


# =============================================================================
# ARTIFACTS
# =============================================================================

PRISON_REALM = make_artifact(
    name="Prison Realm",
    mana_cost="{5}",
    text="{T}, Pay 5 life: Exile target creature. It can't be returned to the battlefield as long as Prison Realm is on the battlefield.",
    subtypes={"Cursed"}
)


FINGER_COLLECTION = make_artifact(
    name="Sukuna's Finger Collection",
    mana_cost="{3}",
    text="{T}, Pay 1 life: Add one mana of any color. Whenever you cast a Curse spell, put a charge counter on Sukuna's Finger Collection."
)


CURSED_ENERGY_DETECTOR = make_artifact(
    name="Cursed Energy Detector",
    mana_cost="{2}",
    text="{T}: Scry 1. If you control a Sorcerer, scry 2 instead."
)


JUJUTSU_HIGH_EMBLEM = make_artifact(
    name="Jujutsu High Emblem",
    mana_cost="{2}",
    text="Student and Sorcerer creatures you control get +0/+1. {T}: Add one mana of any color. Spend this mana only to cast Sorcerer or Student creature spells."
)


VEIL_GENERATOR = make_artifact(
    name="Veil Generator",
    mana_cost="{3}",
    text="{2}, {T}: Target creature gains hexproof until end of turn."
)


CURSED_SPEECH_RICE_BALL = make_artifact(
    name="Cursed Speech Rice Ball",
    mana_cost="{1}",
    text="{T}, Sacrifice Cursed Speech Rice Ball: Tap target creature. It doesn't untap during its controller's next untap step."
)


# =============================================================================
# LANDS
# =============================================================================

JUJUTSU_HIGH = make_land(
    name="Jujutsu High",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Sorcerer or Student spells."
)


SHIBUYA_STATION = make_land(
    name="Shibuya Station",
    text="{T}: Add {C}. {2}, {T}: Target creature can't be blocked this turn. Activate only if you control a Curse."
)


KYOTO_SCHOOL = make_land(
    name="Kyoto Jujutsu School",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a Student."
)


CURSED_GROUNDS = make_land(
    name="Cursed Grounds",
    text="{T}: Add {C}. Whenever a Curse creature enters the battlefield under your control, you may pay 1 life. If you do, draw a card."
)


FINGER_SHRINE = make_land(
    name="Finger Shrine",
    text="{T}: Add {C}. {T}: Add {B} or {R}. Activate only if you control a Curse."
)


HIDDEN_INVENTORY = make_land(
    name="Hidden Inventory",
    text="{T}: Add {C}. {3}, {T}: Search your library for an Equipment card, reveal it, put it into your hand, then shuffle."
)


TOKYO_TOWER = make_land(
    name="Tokyo Tower",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast legendary spells."
)


DOMAIN_BATTLEFIELD = make_land(
    name="Domain Battlefield",
    text="{T}: Add {C}. Domain Expansion enchantments you control have 'At the beginning of your upkeep, scry 1.'"
)


# =============================================================================
# ADDITIONAL CREATURES TO REACH ~250 CARDS
# =============================================================================

CURSE_BREAKER = make_creature(
    name="Curse Breaker",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="When Curse Breaker enters, destroy target enchantment an opponent controls."
)


ZENIN_CLAN_ELDER = make_creature(
    name="Zenin Clan Elder",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text="Other Sorcerer creatures you control get +1/+1."
)


AUXILIARY_MANAGER = make_creature(
    name="Auxiliary Manager",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text="When Auxiliary Manager enters, scry 2."
)


CURSE_COLLECTOR = make_creature(
    name="Curse Collector",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Whenever a Curse you control dies, draw a card."
)


DEATH_PAINTING_WOMB = make_creature(
    name="Death Painting Womb",
    power=0, toughness=4,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="Defender. At the beginning of your end step, you may sacrifice Death Painting Womb. If you do, create two 2/2 black Curse creature tokens."
)


BLOOD_MANIPULATION_EXPERT = make_creature(
    name="Blood Manipulation Expert",
    power=3, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Sorcerer"},
    text="Pay 1 life: Blood Manipulation Expert gets +1/+0 until end of turn."
)


TECHNIQUE_PRODIGY = make_creature(
    name="Technique Prodigy",
    power=2, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Sorcerer", "Student"},
    text="Prowess. Whenever you cast an instant or sorcery spell, Technique Prodigy gets +1/+1 until end of turn."
)


SHIKIGAMI_CRAFTER = make_creature(
    name="Shikigami Crafter",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    text="{3}{G}, {T}: Create a 2/2 green Shikigami creature token."
)


VENGEFUL_ANCESTOR = make_creature(
    name="Vengeful Ancestor Spirit",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Curse"},
    text="When Vengeful Ancestor Spirit enters, each opponent loses 2 life and you gain 2 life."
)


DOMAIN_OBSERVER = make_creature(
    name="Domain Observer",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Whenever an enchantment enters the battlefield, draw a card."
)


CURSED_ENERGY_WELL = make_creature(
    name="Cursed Energy Well",
    power=0, toughness=5,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text="Defender. {T}, Pay 2 life: Add {B}{B}."
)


SORCERER_HUNTER = make_creature(
    name="Sorcerer Hunter",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste. Sorcerer Hunter gets +2/+0 when attacking a player who controls a Sorcerer."
)


SHIKIGAMI_TRAINER = make_creature(
    name="Shikigami Trainer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    text="When Shikigami Trainer enters, target Shikigami you control gets +2/+2 until end of turn."
)


DOMAIN_AMPLIFICATION_MAGE = make_creature(
    name="Domain Amplification Mage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Domain Expansion enchantments you control enter the battlefield with an additional effect counter."
)


CURSE_CYCLE_SPIRIT = make_creature(
    name="Curse Cycle Spirit",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spirit", "Curse"},
    text="When Curse Cycle Spirit dies, you may return another Curse creature card from your graveyard to your hand."
)


BINDING_VOW_WITNESS = make_creature(
    name="Binding Vow Witness",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Cleric"},
    text="Whenever you pay life, Binding Vow Witness gets +1/+1 until end of turn."
)


TECHNIQUE_INHERITANCE = make_creature(
    name="Technique Inheritance Master",
    power=3, toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    text="Whenever a Shikigami you control dies, you may draw a card."
)


SPECIAL_GRADE_SORCERER = make_creature(
    name="Special Grade Sorcerer",
    power=5, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Hexproof. Other Sorcerers you control have hexproof."
)


FINGER_GUARDIAN = make_creature(
    name="Sukuna's Finger Guardian",
    power=4, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Warrior"},
    text="Menace. When Sukuna's Finger Guardian enters, each opponent sacrifices a creature."
)


DOMAIN_MASTER = make_creature(
    name="Domain Master",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text="Whenever you cast an enchantment spell, draw a card."
)


# =============================================================================
# EXPORT
# =============================================================================

JUJUTSU_KAISEN_CARDS = {
    # White Legendaries
    "Yuji Itadori, Sukuna's Vessel": YUJI_ITADORI,
    "Megumi Fushiguro, Ten Shadows": MEGUMI_FUSHIGURO,
    "Nobara Kugisaki, Straw Doll": NOBARA_KUGISAKI,
    "Satoru Gojo, The Strongest": SATORU_GOJO,
    "Aoi Todo, Best Friend": AOI_TODO,

    # White Creatures
    "Jujutsu High First Year": JUJUTSU_FIRST_YEAR,
    "Kyoto Jujutsu Student": KYOTO_STUDENT,
    "Exorcist Sorcerer": EXORCIST_SORCERER,
    "Window Guardian": WINDOW_GUARDIAN,
    "Barrier Technician": BARRIER_TECHNICIAN,
    "Temple Priest": TEMPLE_PRIEST,
    "Cursed Speech Student": CURSED_SPEECH_STUDENT,
    "Holy Ward Monk": HOLY_WARD_MONK,
    "Jujutsu High Instructor": JUJUTSU_INSTRUCTOR,
    "Guardian Shikigami": GUARDIAN_SHIKIGAMI,
    "Reverse Technique Master": REVERSE_TECHNIQUE_MASTER,
    "Binding Oath Enforcer": BINDING_OATH_ENFORCER,
    "Heavenly Restriction Warrior": HEAVENLY_RESTRICTION_WARRIOR,

    # Blue Legendaries
    "Yuta Okkotsu, Rika's Beloved": YUTA_OKKOTSU,
    "Toge Inumaki, Cursed Speech": TOGE_INUMAKI,
    "Geto Suguru, Curse Manipulator": GETO_SUGURU,
    "Masamichi Yaga, Principal": MASAMICHI_YAGA,
    "Kento Nanami, Ratio Technique": KENTO_NANAMI,

    # Blue Creatures
    "Technique Analyst": TECHNIQUE_ANALYST,
    "Infinity Apprentice": INFINITY_APPRENTICE,
    "Cursed Energy Sensor": CURSED_ENERGY_SENSOR,
    "Six Eyes Prodigy": SIX_EYES_PRODIGY,
    "Illusion Caster": ILLUSION_CASTER,
    "Cursed Technique Thief": CURSED_TECHNIQUE_THIEF,
    "Domain Researcher": DOMAIN_RESEARCHER,
    "Limitless Student": LIMITLESS_STUDENT,
    "Spatial Manipulator": SPATIAL_MANIPULATOR,
    "Technique Reversal Mage": TECHNIQUE_REVERSAL_MAGE,
    "New Shadow Practitioner": NEW_SHADOW_PRACTITIONER,
    "Simple Domain Master": SIMPLE_DOMAIN_MASTER,

    # Black Legendaries
    "Ryomen Sukuna, King of Curses": RYOMEN_SUKUNA,
    "Mahito, Soul Sculptor": MAHITO,
    "Jogo, Volcano Curse": JOGO,
    "Hanami, Forest Curse": HANAMI,
    "Dagon, Ocean Curse": DAGON,

    # Black Creatures
    "Finger Bearer": FINGER_BEARER,
    "Cursed Womb": CURSED_WOMB,
    "Vengeful Cursed Spirit": VENGEFUL_SPIRIT,
    "Disease Curse": DISEASE_CURSE,
    "Grasshopper Curse": GRASSHOPPER_CURSE,
    "Fly Head Curse": FLY_HEAD_CURSE,
    "Resentful Curse": RESENTFUL_CURSE,
    "Special Grade Curse": SPECIAL_GRADE_CURSE,
    "Malevolent Shrine Keeper": MALEVOLENT_SHRINE_KEEPER,
    "Transfigured Human": IDLE_TRANSFIGURATION_VICTIM,
    "Cursed Corpse": CURSED_CORPSE,
    "Grade One Curse": GRADE_ONE_CURSE,
    "Smallpox Curse": SMALLPOX_CURSE,
    "Curse User": CURSE_USER,

    # Red Legendaries
    "Maki Zenin, Heavenly Pact": MAKI_ZENIN,
    "Choso, Death Painting": CHOSO,
    "Toji Fushiguro, Sorcerer Killer": TOJI_FUSHIGURO,
    "Naobito Zenin, Projection": NAOBITO_ZENIN,
    "Kamo Noritoshi, Blood Wielder": KAMO_NORITOSHI,

    # Red Creatures
    "Berserker Sorcerer": BERSERKER_SORCERER,
    "Cursed Technique Striker": CURSED_TECHNIQUE_STRIKER,
    "Black Flash User": BLACK_FLASH_USER,
    "Disaster Flame Caster": DISASTER_FLAME_CASTER,
    "Blood Arrow Archer": BLOOD_ARROW_ARCHER,
    "Zenin Clan Warrior": ZENIN_CLAN_WARRIOR,
    "Playful Cloud Wielder": PLAYFUL_CLOUD_WIELDER,
    "Cursed Energy Bomb": CURSED_ENERGY_BOMB,
    "Maximum Output Fighter": MAXIMUM_OUTPUT_FIGHTER,
    "Cleave Practitioner": CLEAVE_PRACTITIONER,
    "Meteor Curse": METEOR_CURSE,
    "Domain Amplifier": DOMAIN_AMPLIFIER,

    # Green Legendaries
    "Panda, Cursed Corpse": PANDA,
    "Mahoraga, Eight-Handled Sword": MAHORAGA,
    "Divine Dog: Totality": DIVINE_DOG_TOTALITY,
    "Nue, Thunder Shikigami": NUE_SHIKIGAMI,
    "Rabbit Escape Swarm": RABBIT_ESCAPE,

    # Green Creatures
    "Divine Dog: White": DIVINE_DOG_WHITE,
    "Divine Dog: Black": DIVINE_DOG_BLACK,
    "Toad Shikigami": TOAD_SHIKIGAMI,
    "Max Elephant": MAX_ELEPHANT,
    "Great Serpent Shikigami": GREAT_SERPENT,
    "Shikigami Summoner": SHIKIGAMI_SUMMONER,
    "Forest Spirit Curse": FOREST_SPIRIT_CURSE,
    "Cursed Bud": CURSED_BUD,
    "Nature Curse Spawn": NATURE_CURSE_SPAWN,
    "Chimera Death Painting": CHIMERA_DEATH_PAINTING,
    "Wheel Shikigami": WHEEL_SHIKIGAMI,
    "Round Deer Shikigami": ROUND_DEER,
    "Tiger Funeral Shikigami": TIGER_FUNERAL,

    # Multicolor
    "Sukuna's Finger": SUKUNA_FINGER,
    "Rika Orimoto, Cursed Queen": RIKA_ORIMOTO,
    "Domain-Clashing Sorcerers": DOMAIN_CLASHING_SORCERERS,
    "Mei Mei, Crow Controller": MEI_MEI,
    "Kenjaku, Brain Stealer": SUGURU_GETO_CORRUPTED,
    "Uraume, Ice Servant": URAUME,

    # Instants
    "Divergent Fist": DIVERGENT_FIST,
    "Black Flash": BLACK_FLASH,
    "Hollow Purple": HOLLOW_PURPLE,
    "Reversal: Red": REVERSAL_RED,
    "Lapse: Blue": LAPSE_BLUE,
    "Domain Amplification": DOMAIN_AMPLIFICATION,
    "Cursed Energy Drain": CURSED_ENERGY_DRAIN,
    "Idle Transfiguration": IDLE_TRANSFIGURATION,
    "Cleave": CLEAVE,
    "Dismantle": DISMANTLE,
    "Exorcism Rite": EXORCISM_RITE,
    "Simple Domain": SIMPLE_DOMAIN,
    "Falling Blossom Emotion": FALLING_BLOSSOM_EMOTION,
    "Maximum: Uzumaki": MAXIMUM_UZUMAKI,
    "Resonance": RESONANCE,
    "Hairpin": HAIRPIN,
    "Straw Doll Technique": STRAW_DOLL_TECHNIQUE,
    "Blood Manipulation": BLOOD_MANIPULATION,
    "Maximum: Meteor": SUPERNOVA,
    "Ten Shadows: Summon": TEN_SHADOWS_SUMMON,
    "Inherited Technique": INHERITED_TECHNIQUE,
    "Cursed Bud Growth": CURSED_BUD_GROWTH,
    "Reverse Cursed Technique": REVERSE_CURSED_TECHNIQUE,
    "Binding Vow": BINDING_VOW_INSTANT,
    "Cursed Technique Lapse": CURSED_TECHNIQUE_LAPSE,
    "Domain Negation": DOMAIN_NEGATION,
    "Curse Absorption": CURSE_ABSORPTION,
    "Projection Sorcery": PROJECTION_SORCERY,

    # Sorceries
    "Shibuya Incident": SHIBUYA_INCIDENT,
    "Culling Game": CULLING_GAME,
    "Night Parade of a Hundred Demons": NIGHT_PARADE,
    "Jujutsu High Training": JUJUTSU_HIGH_TRAINING,
    "Kyoto Goodwill Event": KYOTO_GOODWILL_EVENT,
    "Curse Purification": CURSE_PURIFICATION,
    "Domain Collapse": DOMAIN_COLLAPSE,
    "Unlimited Void Burst": UNLIMITED_VOID_BURST,
    "Shikigami Army": SHIKIGAMI_ARMY,
    "Curse Genesis": CURSE_GENESIS,
    "Divine Flame": MASSACRE,
    "Technique Mastery": TECHNIQUE_MASTERY,
    "Soul Multiplicity": SOUL_MULTIPLICITY,

    # Domain Expansion Enchantments
    "Malevolent Shrine": MALEVOLENT_SHRINE,
    "Unlimited Void": UNLIMITED_VOID,
    "Chimera Shadow Garden": CHIMERA_SHADOW_GARDEN,
    "Self-Embodiment of Perfection": SELF_EMBODIMENT_OF_PERFECTION,
    "Coffin of the Iron Mountain": COFFIN_OF_THE_IRON_MOUNTAIN,
    "Horizon of the Captivating Skandha": HORIZON_OF_CAPTIVATING_SKANDHA,
    "Shining Sea of Flowers": SHINING_SEA_OF_FLOWERS,
    "Authentic Mutual Love": AUTHENTIC_MUTUAL_LOVE,
    "Time Cell Moon Palace": TIME_CELL_MOON_PALACE,
    "Deadly Sentencing": DEADLY_SENTENCING,

    # Other Enchantments
    "Cursed Energy Flow": CURSED_ENERGY_FLOW,
    "Binding Contract": BINDING_CONTRACT,
    "Heavenly Restriction": HEAVENLY_RESTRICTION,
    "Cursed Speech Seal": CURSED_SPEECH_SEAL,
    "Barrier Technique": BARRIER_TECHNIQUE,
    "Cursed Womb: Death Painting": CURSED_WOMB_DEATH_PAINTING,
    "Jujutsu Regulations": JUJUTSU_REGULATIONS,
    "Veil Technique": VEIL_TECHNIQUE,
    "Curse Purge": CURSE_PURGE,

    # Equipment
    "Inverted Spear of Heaven": INVERTED_SPEAR_OF_HEAVEN,
    "Playful Cloud": PLAYFUL_CLOUD,
    "Slaughter Demon": SLAUGHTER_DEMON,
    "Split Soul Katana": SPLIT_SOUL_KATANA,
    "Dragon-Bone": DRAGON_BONE,
    "Festering Life Sword": FESTERING_LIFE_SWORD,
    "Black Rope": BLACK_ROPE,
    "Glasses of Perception": GLASSES_OF_PERCEPTION,
    "Megumi's Knife": MEGUMI_KNIFE,
    "Maki's Glasses": MAKI_GLASSES,
    "Cursed Tool Collection": CURSED_TOOL_COLLECTION,

    # Artifacts
    "Prison Realm": PRISON_REALM,
    "Sukuna's Finger Collection": FINGER_COLLECTION,
    "Cursed Energy Detector": CURSED_ENERGY_DETECTOR,
    "Jujutsu High Emblem": JUJUTSU_HIGH_EMBLEM,
    "Veil Generator": VEIL_GENERATOR,
    "Cursed Speech Rice Ball": CURSED_SPEECH_RICE_BALL,

    # Lands
    "Jujutsu High": JUJUTSU_HIGH,
    "Shibuya Station": SHIBUYA_STATION,
    "Kyoto Jujutsu School": KYOTO_SCHOOL,
    "Cursed Grounds": CURSED_GROUNDS,
    "Finger Shrine": FINGER_SHRINE,
    "Hidden Inventory": HIDDEN_INVENTORY,
    "Tokyo Tower": TOKYO_TOWER,
    "Domain Battlefield": DOMAIN_BATTLEFIELD,

    # Additional Creatures
    "Curse Breaker": CURSE_BREAKER,
    "Zenin Clan Elder": ZENIN_CLAN_ELDER,
    "Auxiliary Manager": AUXILIARY_MANAGER,
    "Curse Collector": CURSE_COLLECTOR,
    "Death Painting Womb": DEATH_PAINTING_WOMB,
    "Blood Manipulation Expert": BLOOD_MANIPULATION_EXPERT,
    "Technique Prodigy": TECHNIQUE_PRODIGY,
    "Shikigami Crafter": SHIKIGAMI_CRAFTER,
    "Vengeful Ancestor Spirit": VENGEFUL_ANCESTOR,
    "Domain Observer": DOMAIN_OBSERVER,
    "Cursed Energy Well": CURSED_ENERGY_WELL,
    "Sorcerer Hunter": SORCERER_HUNTER,
    "Shikigami Trainer": SHIKIGAMI_TRAINER,
    "Domain Amplification Mage": DOMAIN_AMPLIFICATION_MAGE,
    "Curse Cycle Spirit": CURSE_CYCLE_SPIRIT,
    "Binding Vow Witness": BINDING_VOW_WITNESS,
    "Technique Inheritance Master": TECHNIQUE_INHERITANCE,
    "Special Grade Sorcerer": SPECIAL_GRADE_SORCERER,
    "Sukuna's Finger Guardian": FINGER_GUARDIAN,
    "Domain Master": DOMAIN_MASTER,
}
