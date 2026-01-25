"""
Marvel Avengers Card Set for Hyperdraft

~250 cards featuring Marvel heroes and villains.
Mechanics: Assemble, Infinity Stone, Super Strength
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
        name=name, mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY}, subtypes=subtypes or set(),
            supertypes=supertypes or set(), colors=colors, mana_cost=mana_cost
        ),
        text=text, resolve=resolve
    )

def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    return CardDefinition(
        name=name, mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT}, subtypes=subtypes or set(),
            supertypes=supertypes or set(), mana_cost=mana_cost
        ),
        text=text, setup_interceptors=setup_interceptors
    )

def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    base_subtypes = {"Equipment"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name, mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT}, subtypes=base_subtypes,
            supertypes=supertypes or set(), mana_cost=mana_cost
        ),
        text=f"{text}\nEquip {equip_cost}", setup_interceptors=setup_interceptors
    )

def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None):
    return CardDefinition(
        name=name, mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND}, subtypes=subtypes or set(),
            supertypes=supertypes or set(), mana_cost=""
        ),
        text=text
    )


# =============================================================================
# MARVEL KEYWORD MECHANICS
# =============================================================================

def count_avengers(controller: str, state: GameState) -> int:
    """Count Avengers creatures controlled by a player."""
    count = 0
    for obj in state.objects.values():
        if (obj.controller == controller and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            "Avenger" in obj.characteristics.subtypes):
            count += 1
    return count

def make_assemble_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """Assemble - Gets +X/+Y as long as you control 2+ Avengers."""
    def assemble_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return count_avengers(source_obj.controller, state) >= 2
    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, assemble_filter)

def make_assemble_keyword(source_obj: GameObject, keywords: list[str]) -> Interceptor:
    """Assemble - Gains keywords as long as you control 2+ Avengers."""
    def assemble_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return count_avengers(source_obj.controller, state) >= 2
    return make_keyword_grant(source_obj, keywords, assemble_filter)

def make_super_strength(source_obj: GameObject, power_bonus: int = 2) -> list[Interceptor]:
    """Super Strength - Trample and +X/+0."""
    interceptors = []
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id
    interceptors.extend(make_static_pt_boost(source_obj, power_bonus, 0, self_filter))
    interceptors.append(make_keyword_grant(source_obj, ['trample'], self_filter))
    return interceptors

def avenger_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Avenger")

def guardian_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Guardian")

def mutant_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Mutant")

def villain_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Villain")


# =============================================================================
# WHITE CARDS - CAPTAIN AMERICA, HONOR, TEAMWORK
# =============================================================================

def captain_america_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Avenger")))
    return interceptors

CAPTAIN_AMERICA = make_creature(
    name="Captain America, First Avenger",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avenger", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance. Assemble - Captain America gets +2/+2 as long as you control two or more Avengers. Other Avengers you control get +1/+1.",
    setup_interceptors=captain_america_setup
)

def falcon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_assemble_bonus(obj, 1, 1)

FALCON = make_creature(
    name="Falcon, Winged Warrior",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Flying. Assemble - Falcon gets +1/+1 as long as you control two or more Avengers.",
    setup_interceptors=falcon_setup
)

def bucky_barnes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Soldier', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Soldier'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

BUCKY_BARNES = make_creature(
    name="Bucky Barnes, Winter Soldier",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Avenger", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. When Bucky Barnes enters, create a 1/1 white Human Soldier creature token.",
    setup_interceptors=bucky_barnes_setup
)

def peggy_carter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(obj, ['vigilance'], other_creatures_with_subtype(obj, "Soldier"))]

PEGGY_CARTER = make_creature(
    name="Peggy Carter, Agent of SHIELD",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Spy"},
    supertypes={"Legendary"},
    text="Other Soldiers you control have vigilance. {T}: Create a 1/1 white Human Soldier creature token.",
    setup_interceptors=peggy_carter_setup
)

SHIELD_AGENT = make_creature(
    name="SHIELD Agent",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Spy"},
    text="Vigilance"
)

def shield_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SHIELD_RECRUIT = make_creature(
    name="SHIELD Recruit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When SHIELD Recruit enters, you gain 2 life.",
    setup_interceptors=shield_recruit_setup
)

def war_machine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_assemble_bonus(obj, 2, 0)

WAR_MACHINE = make_creature(
    name="War Machine, Iron Patriot",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avenger", "Soldier"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Assemble - War Machine gets +2/+0 as long as you control two or more Avengers.",
    setup_interceptors=war_machine_setup
)

ASGARDIAN_WARRIOR = make_creature(
    name="Asgardian Warrior",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Warrior"},
    text="First strike"
)

def valkyrie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

VALKYRIE = make_creature(
    name="Valkyrie, Chooser of the Slain",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Warrior", "Avenger"},
    supertypes={"Legendary"},
    text="Flying. When Valkyrie dies, you gain 3 life.",
    setup_interceptors=valkyrie_setup
)

EINHERJAR_SOLDIER = make_creature(
    name="Einherjar Soldier",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Soldier", "Spirit"},
    text="Vigilance, lifelink"
)

def lady_sif_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'boost': 'warriors_vigilance', 'controller': obj.controller, 'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

LADY_SIF = make_creature(
    name="Lady Sif, Shield Maiden",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Warrior"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Lady Sif attacks, other Warriors you control gain vigilance until end of turn.",
    setup_interceptors=lady_sif_setup
)

WAKANDAN_GUARD = make_creature(
    name="Wakandan Guard",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wakandan"},
    text="Defender, reach"
)

def okoye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(obj, ['first_strike'], creatures_with_subtype(obj, "Wakandan"))]

OKOYE = make_creature(
    name="Okoye, Dora Milaje General",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wakandan"},
    supertypes={"Legendary"},
    text="First strike. Other Wakandan creatures you control have first strike.",
    setup_interceptors=okoye_setup
)

DORA_MILAJE = make_creature(
    name="Dora Milaje",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wakandan"},
    text="First strike"
)

SHIELD_HELICARRIER_CREW = make_creature(
    name="SHIELD Helicarrier Crew",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender. {T}: Add {C}."
)

AVENGERS_MEDIC = make_creature(
    name="Avengers Medic",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="{T}: You gain 1 life."
)

NOVA_CORPS_OFFICER = make_creature(
    name="Nova Corps Officer",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Alien", "Soldier"},
    text="Flying, vigilance"
)

RAVAGER_SCOUT = make_creature(
    name="Ravager Scout",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Alien", "Pirate"},
    text="When Ravager Scout enters, scry 1."
)


# =============================================================================
# BLUE CARDS - IRON MAN, TECH, STRATEGY
# =============================================================================

def iron_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT}))
    return interceptors

IRON_MAN = make_creature(
    name="Iron Man, Genius Inventor",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Avenger", "Artificer"},
    supertypes={"Legendary"},
    text="Flying. Assemble - Iron Man gets +2/+2 as long as you control two or more Avengers. Whenever you cast an artifact spell, draw a card.",
    setup_interceptors=iron_man_setup
)

def spider_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 1, 1))
    return interceptors

SPIDER_MAN = make_creature(
    name="Spider-Man, Friendly Neighborhood",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Flash, reach. Assemble - Spider-Man gets +1/+1 as long as you control two or more Avengers. Spider-Man can block an additional creature each combat.",
    setup_interceptors=spider_man_setup
)

def doctor_strange_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

DOCTOR_STRANGE = make_creature(
    name="Doctor Strange, Sorcerer Supreme",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Avenger", "Wizard"},
    supertypes={"Legendary"},
    text="Flash, hexproof. Whenever you cast an instant or sorcery spell, scry 2.",
    setup_interceptors=doctor_strange_setup
)

def vision_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['hexproof'], self_filter)]

VISION = make_creature(
    name="Vision, Synthetic Avenger",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Construct", "Avenger"},
    supertypes={"Legendary"},
    text="Flying, hexproof. Vision can't be blocked by creatures with power 2 or less.",
    setup_interceptors=vision_setup
)

def mr_fantastic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

MR_FANTASTIC = make_creature(
    name="Mr. Fantastic, Reed Richards",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, scry 1. {2}{U}: Draw a card, then discard a card.",
    setup_interceptors=mr_fantastic_setup
)

STARK_INDUSTRIES_DRONE = make_creature(
    name="Stark Industries Drone",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="Flying. When Stark Industries Drone dies, draw a card."
)

def friday_ai_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

FRIDAY_AI = make_creature(
    name="FRIDAY, Stark AI",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    supertypes={"Legendary"},
    text="Defender. When FRIDAY enters, scry 2. {T}: Target artifact you control gains hexproof until end of turn.",
    setup_interceptors=friday_ai_setup
)

SHIELD_TECH_SPECIALIST = make_creature(
    name="SHIELD Tech Specialist",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="{T}: Untap target artifact."
)

def hank_pym_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Ant', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Insect'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

HANK_PYM = make_creature(
    name="Hank Pym, Size Shifter",
    power=2, toughness=2,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Scientist", "Avenger"},
    supertypes={"Legendary"},
    text="When Hank Pym enters, create a 1/1 green Insect creature token. {2}: Hank Pym gets +3/+3 or -2/-2 until end of turn.",
    setup_interceptors=hank_pym_setup
)

QUANTUM_REALM_EXPLORER = make_creature(
    name="Quantum Realm Explorer",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    text="When Quantum Realm Explorer dies, scry 2."
)

PYM_PARTICLE_RESEARCHER = make_creature(
    name="Pym Particle Researcher",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    text="{T}, Pay 1 life: Draw a card, then discard a card."
)

def rocket_raccoon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'any_target', 'amount': 1, 'source': obj.id
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT})]

ROCKET_RACCOON = make_creature(
    name="Rocket Raccoon, Weapons Expert",
    power=2, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Raccoon", "Guardian", "Artificer"},
    supertypes={"Legendary"},
    text="Whenever you cast an artifact spell, Rocket deals 1 damage to any target.",
    setup_interceptors=rocket_raccoon_setup
)

def star_lord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Guardian")))
    return interceptors

STAR_LORD = make_creature(
    name="Star-Lord, Legendary Outlaw",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Guardian", "Pirate"},
    supertypes={"Legendary"},
    text="Flying. Other Guardians you control get +1/+1.",
    setup_interceptors=star_lord_setup
)

KREE_SENTRY = make_creature(
    name="Kree Sentry",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Kree", "Soldier"},
    text="Flying. When Kree Sentry enters, tap target creature an opponent controls."
)

SKRULL_INFILTRATOR = make_creature(
    name="Skrull Infiltrator",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Skrull", "Shapeshifter"},
    text="You may have Skrull Infiltrator enter as a copy of any creature on the battlefield."
)

KNOWHERE_MERCHANT = make_creature(
    name="Knowhere Merchant",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Alien", "Rogue"},
    text="When Knowhere Merchant enters, draw a card, then discard a card."
)

RAVAGER_ENGINEER = make_creature(
    name="Ravager Engineer",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Alien", "Pirate", "Artificer"},
    text="Artifacts you control have '{T}: Add {C}.'"
)

XANDARIAN_PILOT = make_creature(
    name="Xandarian Pilot",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Alien", "Pilot"},
    text="Flying. When Xandarian Pilot enters, scry 1."
)


# =============================================================================
# BLACK CARDS - BLACK WIDOW, ESPIONAGE, ANTIHEROES
# =============================================================================

def black_widow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 1, 1))
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    return interceptors

BLACK_WIDOW = make_creature(
    name="Black Widow, Master Spy",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Avenger", "Spy", "Assassin"},
    supertypes={"Legendary"},
    text="Deathtouch. Assemble - Black Widow gets +1/+1 as long as you control two or more Avengers. Whenever Black Widow deals combat damage to a player, draw a card.",
    setup_interceptors=black_widow_setup
)

def hawkeye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 1, 1))
    return interceptors

HAWKEYE = make_creature(
    name="Hawkeye, Never Miss",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Avenger", "Archer"},
    supertypes={"Legendary"},
    text="Reach, deathtouch. Assemble - Hawkeye gets +1/+1 as long as you control two or more Avengers.",
    setup_interceptors=hawkeye_setup
)

def nick_fury_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'SHIELD Agent', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Human', 'Spy'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'SHIELD Agent', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Human', 'Spy'}}
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

NICK_FURY = make_creature(
    name="Nick Fury, Director of SHIELD",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Spy"},
    supertypes={"Legendary"},
    text="Menace. When Nick Fury enters, create two 1/1 black Human Spy creature tokens. Spies you control have menace.",
    setup_interceptors=nick_fury_setup
)

def punisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_trigger_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'any_target', 'amount': 2, 'source': obj.id
        }, source=obj.id)]
    def other_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == source.controller and
                CardType.CREATURE in dying_obj.characteristics.types and
                dying_obj.id != source.id)
    return [make_death_trigger(obj, death_trigger_effect, other_death_filter)]

PUNISHER = make_creature(
    name="The Punisher, Frank Castle",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Vigilante"},
    supertypes={"Legendary"},
    text="Menace. Whenever another creature you control dies, The Punisher deals 2 damage to any target.",
    setup_interceptors=punisher_setup
)

def gamora_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if target and CardType.CREATURE in target.characteristics.types:
            return [Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=obj.id)]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

GAMORA = make_creature(
    name="Gamora, Deadliest Woman",
    power=3, toughness=2,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Guardian", "Assassin"},
    supertypes={"Legendary"},
    text="First strike, deathtouch. Whenever Gamora deals combat damage to a creature, destroy that creature.",
    setup_interceptors=gamora_setup
)

def loki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Illusion', 'power': 0, 'toughness': 0, 'colors': {Color.BLUE}, 'subtypes': {'Illusion'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

LOKI = make_creature(
    name="Loki, God of Mischief",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Asgardian", "God", "Villain"},
    supertypes={"Legendary"},
    text="Flash. When Loki enters, create a token that's a copy of target creature, except it's an Illusion and has 'When this creature becomes the target of a spell, sacrifice it.'",
    setup_interceptors=loki_setup
)

HYDRA_AGENT = make_creature(
    name="HYDRA Agent",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Spy", "Villain"},
    text="When HYDRA Agent dies, create a 1/1 black Human Spy creature token."
)

HYDRA_ENFORCER = make_creature(
    name="HYDRA Enforcer",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Villain"},
    text="Menace"
)

def winter_soldier_asset_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TAP, payload={'object_id': 'target_creature'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

WINTER_SOLDIER_ASSET = make_creature(
    name="Winter Soldier Asset",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Assassin"},
    text="Menace. When Winter Soldier Asset enters, tap target creature an opponent controls.",
    setup_interceptors=winter_soldier_asset_setup
)

HAND_ASSASSIN = make_creature(
    name="Hand Assassin",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Assassin"},
    text="Deathtouch"
)

KINGPIN_ENFORCER = make_creature(
    name="Kingpin's Enforcer",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    text="Menace. When Kingpin's Enforcer enters, each opponent discards a card."
)

def nebula_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

NEBULA = make_creature(
    name="Nebula, Cybernetic Assassin",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Assassin", "Villain"},
    supertypes={"Legendary"},
    text="Menace. Whenever Nebula attacks, put a +1/+1 counter on her.",
    setup_interceptors=nebula_setup
)

CROSSBONES = make_creature(
    name="Crossbones",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Mercenary", "Villain"},
    supertypes={"Legendary"},
    text="Menace. When Crossbones dies, it deals 3 damage to target creature or planeswalker."
)

TASKMASTER = make_creature(
    name="Taskmaster",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Mercenary", "Villain"},
    supertypes={"Legendary"},
    text="First strike. Taskmaster has all activated abilities of creatures your opponents control."
)

GHOST = make_creature(
    name="Ghost, Phasing Thief",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="Ghost can't be blocked. Whenever Ghost deals combat damage to a player, that player discards a card."
)

ZEMO = make_creature(
    name="Baron Zemo, Vengeful Noble",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Noble", "Villain"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever an Avenger an opponent controls dies, draw a card."
)

MANTIS = make_creature(
    name="Mantis, Empath",
    power=1, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Guardian"},
    supertypes={"Legendary"},
    text="When Mantis enters, tap target creature and it doesn't untap during its controller's next untap step."
)

DRAX = make_creature(
    name="Drax the Destroyer",
    power=4, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Guardian", "Warrior"},
    supertypes={"Legendary"},
    text="Trample. Drax must attack each combat if able. Drax gets +2/+2 as long as an opponent controls a Villain."
)

DARK_ELF_WARRIOR = make_creature(
    name="Dark Elf Warrior",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warrior"},
    text="When Dark Elf Warrior enters, target creature gets -1/-1 until end of turn."
)


# =============================================================================
# RED CARDS - THOR, POWER, DESTRUCTION
# =============================================================================

def thor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'any_target', 'amount': 3, 'source': obj.id, 'type': 'lightning'
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors

THOR = make_creature(
    name="Thor, God of Thunder",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Asgardian", "God", "Avenger"},
    supertypes={"Legendary"},
    text="Flying, trample. Assemble - Thor gets +2/+2 as long as you control two or more Avengers. When Thor enters, he deals 3 damage to any target.",
    setup_interceptors=thor_setup
)

def scarlet_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'each_opponent', 'amount': 1, 'source': obj.id
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

SCARLET_WITCH = make_creature(
    name="Scarlet Witch, Reality Warper",
    power=2, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Avenger", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, Scarlet Witch deals 1 damage to each opponent.",
    setup_interceptors=scarlet_witch_setup
)

def captain_marvel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    return interceptors

CAPTAIN_MARVEL = make_creature(
    name="Captain Marvel, Binary",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Avenger", "Warrior"},
    supertypes={"Legendary"},
    text="Flying, haste, trample. Assemble - Captain Marvel gets +2/+2 as long as you control two or more Avengers.",
    setup_interceptors=captain_marvel_setup
)

def hela_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1
        }, source=obj.id)]
    def any_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)
    return [make_death_trigger(obj, death_effect, any_death_filter)]

HELA = make_creature(
    name="Hela, Goddess of Death",
    power=5, toughness=5,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Asgardian", "God", "Villain"},
    supertypes={"Legendary"},
    text="Menace, deathtouch. Whenever a creature dies, put a +1/+1 counter on Hela.",
    setup_interceptors=hela_setup
)

def surtur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'each_creature', 'amount': 2, 'source': obj.id
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

SURTUR = make_creature(
    name="Surtur, Fire Giant",
    power=7, toughness=7,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Villain"},
    supertypes={"Legendary"},
    text="Trample. Whenever Surtur attacks, he deals 2 damage to each other creature.",
    setup_interceptors=surtur_setup
)

def ultron_prime_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Ultron Drone', 'power': 2, 'toughness': 2, 'subtypes': {'Construct', 'Villain'}}
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

ULTRON_PRIME = make_creature(
    name="Ultron Prime",
    power=5, toughness=5,
    mana_cost="{4}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Construct", "Villain"},
    supertypes={"Legendary"},
    text="Flying, indestructible. At the beginning of your upkeep, create a 2/2 colorless Construct Villain creature token.",
    setup_interceptors=ultron_prime_setup
)

ULTRON_DRONE = make_creature(
    name="Ultron Drone",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct", "Villain"},
    text="When Ultron Drone dies, it deals 1 damage to any target."
)

FIRE_DEMON = make_creature(
    name="Fire Demon",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Demon"},
    text="Haste. When Fire Demon enters, it deals 1 damage to any target."
)

ASGARDIAN_BERSERKER = make_creature(
    name="Asgardian Berserker",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Asgardian", "Warrior", "Berserker"},
    text="Haste, trample. Asgardian Berserker attacks each combat if able."
)

CHITAURI_SOLDIER = make_creature(
    name="Chitauri Soldier",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Soldier", "Villain"},
    text="Haste"
)

CHITAURI_CHARGER = make_creature(
    name="Chitauri Charger",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Warrior", "Villain"},
    text="Haste, menace"
)

def leviathan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_super_strength(obj, 3))
    return interceptors

LEVIATHAN = make_creature(
    name="Chitauri Leviathan",
    power=6, toughness=6,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Leviathan", "Villain"},
    text="Super Strength - Trample and +3/+0. When Chitauri Leviathan attacks, create two 2/1 red Alien Soldier creature tokens attacking.",
    setup_interceptors=leviathan_setup
)

NOVA_PRIME = make_creature(
    name="Nova Prime",
    power=4, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Flying, haste. When Nova Prime enters, it deals damage equal to its power to target creature."
)

DESTROYER_ARMOR = make_creature(
    name="Destroyer Armor",
    power=6, toughness=6,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Construct"},
    text="Indestructible. {R}: Destroyer Armor deals 2 damage to target creature or player."
)

RONAN_ACCUSER = make_creature(
    name="Ronan the Accuser",
    power=4, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Kree", "Warrior", "Villain"},
    supertypes={"Legendary"},
    text="Menace. When Ronan enters, destroy target creature with power 3 or less."
)

SAKAARAN_GLADIATOR = make_creature(
    name="Sakaaran Gladiator",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Warrior"},
    text="Haste. When Sakaaran Gladiator dies, it deals 2 damage to target player."
)

GRANDMASTER_CHAMPION = make_creature(
    name="Grandmaster's Champion",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Warrior"},
    text="Trample. Grandmaster's Champion gets +2/+0 as long as it's attacking."
)

HUMAN_TORCH = make_creature(
    name="Human Torch, Johnny Storm",
    power=3, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Elemental"},
    supertypes={"Legendary"},
    text="Flying, haste. {R}: Human Torch gets +1/+0 until end of turn. {R}, {T}: Human Torch deals 2 damage to any target."
)


# =============================================================================
# GREEN CARDS - HULK, RAW STRENGTH, NATURE
# =============================================================================

def hulk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 3, 3))
    interceptors.extend(make_super_strength(obj, 2))
    return interceptors

HULK = make_creature(
    name="Hulk, Strongest Avenger",
    power=6, toughness=6,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Super Strength - Trample and +2/+0. Assemble - Hulk gets +3/+3 as long as you control two or more Avengers. Indestructible.",
    setup_interceptors=hulk_setup
)

def she_hulk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    interceptors.extend(make_super_strength(obj, 1))
    return interceptors

SHE_HULK = make_creature(
    name="She-Hulk, Jennifer Walters",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger", "Lawyer"},
    supertypes={"Legendary"},
    text="Super Strength - Trample and +1/+0. Assemble - She-Hulk gets +2/+2 as long as you control two or more Avengers.",
    setup_interceptors=she_hulk_setup
)

def groot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Baby Groot', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Plant', 'Guardian'}}
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

GROOT = make_creature(
    name="Groot, I Am Groot",
    power=4, toughness=6,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Guardian"},
    supertypes={"Legendary"},
    text="Trample, reach. When Groot dies, create a 1/1 green Plant Guardian creature token named Baby Groot.",
    setup_interceptors=groot_setup
)

def black_panther_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ADD_MANA, payload={
            'player': obj.controller, 'mana': '{G}{G}'
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors

BLACK_PANTHER = make_creature(
    name="Black Panther, King of Wakanda",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger", "Noble", "Wakandan"},
    supertypes={"Legendary"},
    text="Deathtouch, hexproof. Assemble - Black Panther gets +2/+2 as long as you control two or more Avengers. When Black Panther enters, add {G}{G}.",
    setup_interceptors=black_panther_setup
)

def ant_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        tokens = []
        for _ in range(3):
            tokens.append(Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Ant', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Insect'}}
            }, source=obj.id))
        return tokens
    return [make_etb_trigger(obj, etb_effect)]

ANT_MAN = make_creature(
    name="Ant-Man, Scott Lang",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="When Ant-Man enters, create three 1/1 green Insect creature tokens. {2}{G}: Ant-Man gets +4/+4 until end of turn.",
    setup_interceptors=ant_man_setup
)

def wasp_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Ant', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Insect'}}
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

WASP = make_creature(
    name="Wasp, Hope Van Dyne",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Flying. Whenever Wasp deals combat damage to a player, create a 1/1 green Insect creature token.",
    setup_interceptors=wasp_setup
)

ANT_SWARM = make_creature(
    name="Ant Swarm",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Ant Swarm gets +1/+1 for each other Insect you control."
)

VIBRANIUM_RHINO = make_creature(
    name="Vibranium Rhino",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino", "Wakandan"},
    text="Trample. Vibranium Rhino has indestructible as long as it's attacking."
)

WAKANDAN_WAR_RHINO = make_creature(
    name="Wakandan War Rhino",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino", "Wakandan"},
    text="Trample. When Wakandan War Rhino enters, it fights target creature you don't control."
)

def shuri_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'controller': obj.controller, 'counter_type': '+1/+1', 'target': 'creature_you_control'
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT})]

SHURI = make_creature(
    name="Shuri, Wakandan Genius",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Artificer", "Wakandan"},
    supertypes={"Legendary"},
    text="Whenever you cast an artifact spell, put a +1/+1 counter on target creature you control.",
    setup_interceptors=shuri_setup
)

WAKANDAN_BORDER_TRIBE = make_creature(
    name="Wakandan Border Tribe",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior", "Wakandan"},
    text="Reach. Wakandan Border Tribe gets +1/+1 as long as you control a legendary Wakandan."
)

THING = make_creature(
    name="The Thing, Ben Grimm",
    power=5, toughness=6,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Mutate"},
    supertypes={"Legendary"},
    text="Trample. The Thing has indestructible as long as it's blocking."
)

ABOMINATION = make_creature(
    name="Abomination",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Mutant", "Villain"},
    supertypes={"Legendary"},
    text="Trample. Whenever Abomination deals combat damage to a player, put two +1/+1 counters on it."
)

SAVAGE_LAND_RAPTOR = make_creature(
    name="Savage Land Raptor",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Haste. Savage Land Raptor gets +2/+0 as long as it's attacking."
)

SAVAGE_LAND_REX = make_creature(
    name="Savage Land Rex",
    power=6, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample. When Savage Land Rex enters, it fights target creature you don't control."
)

FOREST_TROLL = make_creature(
    name="Forest Troll",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Troll"},
    text="Trample. At the beginning of your upkeep, regenerate Forest Troll."
)

def korg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Miek', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Insect', 'Warrior'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

KORG = make_creature(
    name="Korg, Revolutionary",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Kronan", "Warrior"},
    supertypes={"Legendary"},
    text="Trample. When Korg enters, create a 1/1 green Insect Warrior creature token named Miek.",
    setup_interceptors=korg_setup
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def thanos_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SACRIFICE, payload={
            'controller': 'each_player', 'count': 'half_creatures'
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

THANOS = make_creature(
    name="Thanos, The Mad Titan",
    power=7, toughness=7,
    mana_cost="{3}{B}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Eternal", "Villain"},
    supertypes={"Legendary"},
    text="Indestructible. When Thanos enters, each player sacrifices half of their creatures, rounded up.",
    setup_interceptors=thanos_setup
)

RED_SKULL = make_creature(
    name="Red Skull, HYDRA Supreme",
    power=4, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Menace. At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life."
)

def quicksilver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP, payload={'object_id': obj.id}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

QUICKSILVER = make_creature(
    name="Quicksilver, Pietro Maximoff",
    power=2, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Avenger", "Mutant"},
    supertypes={"Legendary"},
    text="Haste. Whenever Quicksilver attacks, untap it. Quicksilver can attack twice each combat.",
    setup_interceptors=quicksilver_setup
)

EBONY_MAW = make_creature(
    name="Ebony Maw",
    power=2, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Alien", "Villain"},
    supertypes={"Legendary"},
    text="Flying. When Ebony Maw enters, gain control of target creature with power 2 or less until Ebony Maw leaves the battlefield."
)

PROXIMA_MIDNIGHT = make_creature(
    name="Proxima Midnight",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Alien", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, menace. Whenever Proxima Midnight deals combat damage to a player, that player discards a card."
)

CORVUS_GLAIVE = make_creature(
    name="Corvus Glaive",
    power=3, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink. Corvus Glaive can't be destroyed by damage."
)

CULL_OBSIDIAN = make_creature(
    name="Cull Obsidian",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Alien", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Trample. Cull Obsidian gets +2/+2 as long as you control another Villain."
)

def wong_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

WONG = make_creature(
    name="Wong, Sorcerer of Kamar-Taj",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, you gain 1 life.",
    setup_interceptors=wong_setup
)

MORDO = make_creature(
    name="Baron Mordo",
    power=3, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard", "Villain"},
    supertypes={"Legendary"},
    text="Flash. When Baron Mordo enters, counter target spell unless its controller pays {3}."
)

DORMAMMU = make_creature(
    name="Dormammu, Lord of the Dark Dimension",
    power=8, toughness=8,
    mana_cost="{5}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "Villain"},
    supertypes={"Legendary"},
    text="Flying, trample. Dormammu can't be countered. At the beginning of your upkeep, each opponent loses 3 life."
)


# =============================================================================
# X-MEN REPRESENTATIVES
# =============================================================================

def wolverine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

WOLVERINE = make_creature(
    name="Wolverine, Logan",
    power=3, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="First strike, regenerate {1}{G}. Whenever Wolverine deals combat damage to a creature, you gain 2 life.",
    setup_interceptors=wolverine_setup
)

def storm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TAP, payload={'target': 'all_creatures_opponents'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

STORM = make_creature(
    name="Storm, Weather Witch",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flying. When Storm enters, tap all creatures your opponents control.",
    setup_interceptors=storm_setup
)

def cyclops_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Mutant")))
    return interceptors

CYCLOPS = make_creature(
    name="Cyclops, X-Men Leader",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="{T}: Cyclops deals 3 damage to target creature. Other Mutants you control get +1/+1.",
    setup_interceptors=cyclops_setup
)

def jean_grey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

JEAN_GREY = make_creature(
    name="Jean Grey, Phoenix",
    power=3, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast an instant or sorcery spell, draw a card. When Jean Grey dies, she deals 5 damage to each creature and each player.",
    setup_interceptors=jean_grey_setup
)

PROFESSOR_X = make_creature(
    name="Professor X, Charles Xavier",
    power=1, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Hexproof. Other Mutants you control have hexproof. {T}: Look at target opponent's hand."
)

MAGNETO = make_creature(
    name="Magneto, Master of Magnetism",
    power=4, toughness=4,
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Mutant", "Villain"},
    supertypes={"Legendary"},
    text="Flying. When Magneto enters, gain control of all Equipment. Equipped creatures opponents control get -2/-0."
)

ROGUE = make_creature(
    name="Rogue, Power Absorber",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flying. Whenever Rogue deals combat damage to a creature, she gains all abilities of that creature until end of turn."
)

BEAST = make_creature(
    name="Beast, Hank McCoy",
    power=3, toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Mutant", "Scientist"},
    supertypes={"Legendary"},
    text="Reach. {T}: Add one mana of any color. When Beast enters, draw a card."
)

ICEMAN = make_creature(
    name="Iceman, Bobby Drake",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Hexproof. When Iceman enters, tap target creature. It doesn't untap during its controller's next untap step."
)

NIGHTCRAWLER = make_creature(
    name="Nightcrawler",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flash. Nightcrawler can't be blocked. When Nightcrawler enters, you may return another creature you control to its owner's hand."
)

COLOSSUS = make_creature(
    name="Colossus, Piotr Rasputin",
    power=5, toughness=6,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Trample. Colossus has indestructible as long as it's attacking or blocking."
)


# =============================================================================
# ARTIFACTS - INFINITY STONES, EQUIPMENT
# =============================================================================

def mind_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

MIND_STONE_INFINITY = make_artifact(
    name="Mind Stone",
    mana_cost="{4}",
    text="Infinity Stone - At the beginning of your upkeep, scry 1. {T}: Add {U}. You have no maximum hand size.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=mind_stone_setup
)

def space_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.controller == obj.controller and CardType.CREATURE in target.characteristics.types
    return [make_keyword_grant(obj, ['flying'], self_filter)]

SPACE_STONE = make_artifact(
    name="Space Stone",
    mana_cost="{4}",
    text="Infinity Stone - Creatures you control have flying. {T}: Add {W}. {3}, {T}: Exile target creature you control, then return it to the battlefield.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=space_stone_setup
)

def time_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP, payload={'target': 'all_permanents_you_control'}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

TIME_STONE = make_artifact(
    name="Time Stone",
    mana_cost="{5}",
    text="Infinity Stone - At the beginning of your upkeep, untap all permanents you control. {T}: Add {U}. Take an extra turn after this one. Exile Time Stone.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=time_stone_setup
)

def power_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.controller == obj.controller and CardType.CREATURE in target.characteristics.types
    return make_static_pt_boost(obj, 2, 2, self_filter)

POWER_STONE_INFINITY = make_artifact(
    name="Power Stone",
    mana_cost="{5}",
    text="Infinity Stone - Creatures you control get +2/+2. {T}: Add {R}{R}.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=power_stone_setup
)

def reality_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

REALITY_STONE = make_artifact(
    name="Reality Stone",
    mana_cost="{4}",
    text="Infinity Stone - When Reality Stone enters, draw two cards. {T}: Add {R}. {2}, {T}: Exile target permanent, then return it to the battlefield under your control.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=reality_stone_setup
)

def soul_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    def any_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)
    return [make_death_trigger(obj, death_effect, any_death_filter)]

SOUL_STONE = make_artifact(
    name="Soul Stone",
    mana_cost="{4}",
    text="Infinity Stone - Whenever a creature dies, you gain 1 life. {T}: Add {B}. {3}, {T}: Return target creature card from your graveyard to the battlefield.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=soul_stone_setup
)

MJOLNIR = make_equipment(
    name="Mjolnir",
    mana_cost="{3}",
    text="Equipped creature gets +3/+3 and has flying and trample. If equipped creature is named Thor, it has indestructible. Equip {3}. Equip Thor {0}.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)

STORMBREAKER = make_equipment(
    name="Stormbreaker",
    mana_cost="{4}",
    text="Equipped creature gets +4/+4 and has flying, trample, and first strike. {T}: Stormbreaker deals 3 damage to any target.",
    equip_cost="{4}",
    supertypes={"Legendary"}
)

CAPTAIN_AMERICAS_SHIELD = make_equipment(
    name="Captain America's Shield",
    mana_cost="{2}",
    text="Equipped creature gets +1/+3 and has vigilance and indestructible. If equipped creature is named Captain America, it has double strike.",
    equip_cost="{2}",
    supertypes={"Legendary"}
)

IRON_MAN_ARMOR_MK_L = make_equipment(
    name="Iron Man Armor Mk. L",
    mana_cost="{4}",
    text="Equipped creature gets +3/+3 and has flying and hexproof. {2}: Equipped creature deals 2 damage to any target.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)

IRON_MAN_ARMOR_MK_LXXXV = make_equipment(
    name="Iron Man Armor Mk. LXXXV",
    mana_cost="{5}",
    text="Equipped creature gets +4/+4 and has flying, hexproof, and indestructible. {R}: Equipped creature gets +1/+0 until end of turn.",
    equip_cost="{4}",
    supertypes={"Legendary"}
)

HULKBUSTER_ARMOR = make_equipment(
    name="Hulkbuster Armor",
    mana_cost="{6}",
    text="Equipped creature gets +5/+5 and has trample. Equipped creature can't be blocked by creatures with power 3 or less.",
    equip_cost="{4}",
    supertypes={"Legendary"}
)

INFINITY_GAUNTLET = make_artifact(
    name="Infinity Gauntlet",
    mana_cost="{6}",
    text="Infinity Gauntlet enters with six charge counters. {T}, Remove a charge counter: Choose one - Draw a card; Add three mana of any color; Destroy target permanent; Exile target creature; Take an extra turn; Each opponent loses half their life.",
    subtypes={"Equipment"},
    supertypes={"Legendary"}
)

WEB_SHOOTERS = make_equipment(
    name="Web-Shooters",
    mana_cost="{1}",
    text="Equipped creature gets +1/+1 and has reach. {T}: Tap target creature. It doesn't untap during its controller's next untap step.",
    equip_cost="{1}"
)

YAKA_ARROW = make_equipment(
    name="Yaka Arrow",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0 and has '{T}: This creature deals 2 damage to target creature.'",
    equip_cost="{2}"
)

VIBRANIUM_SPEAR = make_equipment(
    name="Vibranium Spear",
    mana_cost="{2}",
    text="Equipped creature gets +2/+1 and has first strike. If equipped creature is Wakandan, it gets +3/+2 instead.",
    equip_cost="{2}"
)

PANTHER_HABIT = make_equipment(
    name="Panther Habit",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2 and has deathtouch and hexproof. Whenever equipped creature is dealt damage, it deals that much damage to target creature.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)

NANO_GAUNTLET = make_equipment(
    name="Nano Gauntlet",
    mana_cost="{3}",
    text="Equipped creature gets +1/+1 for each artifact you control. {3}, {T}: Destroy target artifact or enchantment.",
    equip_cost="{2}"
)

CHITAURI_SCEPTER = make_equipment(
    name="Chitauri Scepter",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has 'Whenever this creature deals combat damage to a player, gain control of target creature that player controls until end of turn.'",
    equip_cost="{3}"
)

CLOAK_OF_LEVITATION = make_equipment(
    name="Cloak of Levitation",
    mana_cost="{2}",
    text="Equipped creature gets +1/+2, has flying, and can't be blocked by creatures with flying. Flash - You may cast this spell as though it had flash.",
    equip_cost="{1}",
    supertypes={"Legendary"}
)

TESSERACT = make_artifact(
    name="Tesseract",
    mana_cost="{4}",
    text="{T}: Add {U}{U}. {4}, {T}: Exile target creature you control. Return it to the battlefield at the beginning of your next upkeep.",
    supertypes={"Legendary"}
)

EYE_OF_AGAMOTTO = make_artifact(
    name="Eye of Agamotto",
    mana_cost="{3}",
    text="{T}: Scry 2. {2}, {T}: Return target permanent to its owner's hand. {4}, {T}: Take an extra turn after this one. Exile Eye of Agamotto.",
    supertypes={"Legendary"}
)

QUINJET = make_artifact(
    name="Quinjet",
    mana_cost="{3}",
    text="Crew 2. Flying. When Quinjet attacks, you may search your library for an Avenger card, reveal it, put it into your hand, then shuffle.",
    subtypes={"Vehicle"}
)

MILANO = make_artifact(
    name="The Milano",
    mana_cost="{4}",
    text="Crew 2. Flying. When The Milano attacks, Guardians you control get +2/+0 until end of turn.",
    subtypes={"Vehicle"},
    supertypes={"Legendary"}
)

HELICARRIER = make_artifact(
    name="SHIELD Helicarrier",
    mana_cost="{6}",
    text="Crew 4. Flying. SHIELD Helicarrier has '{T}: Draw a card' and '{2}, {T}: SHIELD Helicarrier deals 3 damage to any target.'",
    subtypes={"Vehicle"},
    supertypes={"Legendary"}
)

BENATAR = make_artifact(
    name="The Benatar",
    mana_cost="{4}",
    text="Crew 2. Flying. Whenever The Benatar attacks, create a 1/1 colorless Construct creature token.",
    subtypes={"Vehicle"},
    supertypes={"Legendary"}
)


# =============================================================================
# INSTANTS AND SORCERIES
# =============================================================================

REPULSOR_BLAST = make_instant(
    name="Repulsor Blast",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Repulsor Blast deals 3 damage to target creature. If you control an artifact, draw a card."
)

SHIELD_THROW = make_instant(
    name="Shield Throw",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Shield Throw deals 2 damage to target creature. If that creature dies this turn, Shield Throw deals 2 damage to another target creature."
)

AVENGERS_ASSEMBLE = make_sorcery(
    name="Avengers Assemble",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 2/2 white Human Avenger creature tokens with vigilance. Avengers you control get +1/+1 until end of turn."
)

HULK_SMASH = make_sorcery(
    name="Hulk Smash",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature you don't control. If the creature you control is Hulk, it deals double that damage instead."
)

LIGHTNING_STRIKE_THOR = make_instant(
    name="Call the Bifrost",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Call the Bifrost deals 4 damage divided as you choose among any number of targets. If you control Thor, search your library for an Asgardian card, reveal it, put it into your hand, then shuffle."
)

WIDOW_STING = make_instant(
    name="Widow's Sting",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If you control Black Widow, that creature gets -5/-5 instead."
)

CHAOS_MAGIC = make_instant(
    name="Chaos Magic",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Chaos Magic deals 3 damage to any target. If you control Scarlet Witch, Chaos Magic deals 5 damage instead."
)

PORTAL_SLING_RING = make_instant(
    name="Sling Ring Portal",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Exile target creature you control, then return it to the battlefield. You may have it enter tapped."
)

TIME_REVERSAL = make_instant(
    name="Time Reversal",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands. If you control Doctor Strange, instead exile all creatures, then return them to the battlefield under their owners' control."
)

SNAP_FINGERS = make_sorcery(
    name="Snap",
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    text="Each player sacrifices half of their creatures, rounded up. If you control Thanos, you may instead have each opponent sacrifice half of their permanents, rounded up."
)

GAMMA_RADIATION = make_sorcery(
    name="Gamma Radiation",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature. It gains trample until end of turn. If that creature is Hulk, put four +1/+1 counters on it instead."
)

SHRINK_RAY = make_instant(
    name="Pym Particles",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature gets -4/-0 or +4/+4 until end of turn. You choose."
)

ARROW_VOLLEY = make_sorcery(
    name="Arrow Volley",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Arrow Volley deals 1 damage to each creature your opponents control. If you control Hawkeye, Arrow Volley deals 2 damage to each creature your opponents control instead."
)

WAKANDA_FOREVER = make_sorcery(
    name="Wakanda Forever",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Creatures you control get +2/+2 and gain indestructible until end of turn. If you control Black Panther, put a +1/+1 counter on each creature you control."
)

MYSTIC_ARTS = make_instant(
    name="Mystic Arts",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}. If you control Doctor Strange, counter that spell instead."
)

BLITZ_ATTACK = make_instant(
    name="Blitz Attack",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains haste until end of turn. If you control Quicksilver, that creature gets +4/+0 instead."
)

TACTICAL_GENIUS = make_instant(
    name="Tactical Genius",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1 until end of turn. If you control Captain America, they also gain vigilance until end of turn."
)

COSMIC_AWARENESS = make_sorcery(
    name="Cosmic Awareness",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards. If you control an Infinity Stone, draw four cards instead."
)

BERSERKER_RAGE = make_instant(
    name="Berserker Rage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains trample until end of turn. That creature attacks this turn if able."
)

STEALTH_MISSION = make_sorcery(
    name="Stealth Mission",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gains deathtouch and can't be blocked this turn. Draw a card."
)

HEROIC_SACRIFICE = make_instant(
    name="Heroic Sacrifice",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Sacrifice a creature. If you do, you gain life equal to its toughness and draw a card."
)

SUPER_SOLDIER_SERUM = make_sorcery(
    name="Super Soldier Serum",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put three +1/+1 counters on target creature. It gains vigilance and trample until end of turn."
)

REALITY_WARP = make_sorcery(
    name="Reality Warp",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Exile all artifacts and enchantments. Each player who controlled a permanent exiled this way draws a card for each permanent they owned that was exiled."
)

IMPALE = make_instant(
    name="Impale",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses 2 life."
)


# =============================================================================
# ENCHANTMENTS
# =============================================================================

def avengers_initiative_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def self_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                "Avenger" in target.characteristics.subtypes)
    return make_static_pt_boost(obj, 1, 1, self_filter)

AVENGERS_INITIATIVE = make_enchantment(
    name="Avengers Initiative",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Avengers you control get +1/+1. Whenever an Avenger enters under your control, scry 1.",
    setup_interceptors=avengers_initiative_setup
)

def stark_industries_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Thopter', 'power': 1, 'toughness': 1, 'subtypes': {'Construct'}}
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT})]

STARK_INDUSTRIES = make_enchantment(
    name="Stark Industries",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an artifact spell, create a 1/1 colorless Thopter artifact creature token with flying.",
    setup_interceptors=stark_industries_setup
)

def shield_headquarters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

SHIELD_HEADQUARTERS = make_enchantment(
    name="SHIELD Headquarters",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="At the beginning of your upkeep, scry 1. Spy creatures you control have menace.",
    setup_interceptors=shield_headquarters_setup
)

def guardians_bond_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def self_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                "Guardian" in target.characteristics.subtypes)
    interceptors = make_static_pt_boost(obj, 1, 1, self_filter)
    interceptors.append(make_keyword_grant(obj, ['vigilance'], self_filter))
    return interceptors

GUARDIANS_BOND = make_enchantment(
    name="Guardians of the Galaxy United",
    mana_cost="{2}{G}{R}",
    colors={Color.GREEN, Color.RED},
    text="Guardians you control get +1/+1 and have vigilance.",
    setup_interceptors=guardians_bond_setup
)

def hydra_influence_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'HYDRA Agent', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Human', 'Spy'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'HYDRA Agent', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Human', 'Spy'}}
            }, source=obj.id)
        ]
    def villain_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == source.controller and
                CardType.CREATURE in dying_obj.characteristics.types and
                "Villain" in dying_obj.characteristics.subtypes)
    return [make_death_trigger(obj, death_effect, villain_death_filter)]

HYDRA_INFLUENCE = make_enchantment(
    name="HYDRA's Influence",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Whenever a Villain you control dies, create two 1/1 black Human Spy creature tokens.",
    setup_interceptors=hydra_influence_setup
)

ASGARDIAN_MIGHT = make_enchantment(
    name="Asgardian Might",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Asgardian creatures you control get +2/+1 and have trample."
)

MUTANT_UPRISING = make_enchantment(
    name="Mutant Uprising",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Mutant creatures you control get +1/+1 and have haste."
)

COSMIC_CONVERGENCE = make_enchantment(
    name="Cosmic Convergence",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Whenever you cast a spell, if it's the second spell you cast this turn, copy it. You may choose new targets for the copy."
)

def dark_dimension_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={
            'player': 'each_opponent', 'amount': -2
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

DARK_DIMENSION = make_enchantment(
    name="Dark Dimension",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, each opponent loses 2 life. Demons and Villains you control have menace.",
    setup_interceptors=dark_dimension_setup
)

VIBRANIUM_MINES = make_enchantment(
    name="Vibranium Mines",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever a Wakandan creature enters under your control, add {G}. Wakandan creatures you control have +0/+1."
)


# =============================================================================
# LANDS
# =============================================================================

AVENGERS_TOWER = make_land(
    name="Avengers Tower",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Avenger spells or activate abilities of Avengers.",
    supertypes={"Legendary"}
)

STARK_TOWER = make_land(
    name="Stark Tower",
    text="{T}: Add {C}. {1}, {T}: Add {U}{U}. Activate only if you control an artifact.",
    supertypes={"Legendary"}
)

WAKANDA = make_land(
    name="Wakanda",
    text="{T}: Add {G} or {W}. Wakanda enters tapped unless you control a Wakandan creature.",
    supertypes={"Legendary"}
)

ASGARD = make_land(
    name="Asgard, Realm Eternal",
    text="{T}: Add {R} or {W}. {3}, {T}: Create a 2/2 white Asgardian Warrior creature token.",
    supertypes={"Legendary"}
)

SANCTUM_SANCTORUM = make_land(
    name="Sanctum Sanctorum",
    text="{T}: Add {U}. {2}, {T}: Scry 2. Activate only if you control a Wizard.",
    supertypes={"Legendary"}
)

KNOWHERE = make_land(
    name="Knowhere",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Guardian spells.",
    supertypes={"Legendary"}
)

XAVIERS_SCHOOL = make_land(
    name="Xavier's School for Gifted Youngsters",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Mutant spells.",
    supertypes={"Legendary"}
)

HYDRA_BASE = make_land(
    name="HYDRA Base",
    text="{T}: Add {B}. When HYDRA Base enters, you may pay 2 life. If you don't, HYDRA Base enters tapped."
)

SHIELD_FACILITY = make_land(
    name="SHIELD Facility",
    text="{T}: Add {W} or {U}. SHIELD Facility enters tapped."
)

TITAN = make_land(
    name="Titan",
    text="{T}: Add {B} or {G}. {4}, {T}, Sacrifice Titan: Search your library for a Villain card, reveal it, put it into your hand, then shuffle.",
    supertypes={"Legendary"}
)

VORMIR = make_land(
    name="Vormir",
    text="{T}: Add {B}. {2}, {T}, Sacrifice a creature: Draw two cards.",
    supertypes={"Legendary"}
)

SAKAAR = make_land(
    name="Sakaar",
    text="{T}: Add {R} or {G}. Sakaar enters tapped. When Sakaar enters, create a 1/1 red Alien Warrior creature token.",
    supertypes={"Legendary"}
)

CONTRAXIA = make_land(
    name="Contraxia",
    text="{T}: Add {U} or {R}. Contraxia enters tapped unless you control a Pirate."
)

HALA = make_land(
    name="Hala",
    text="{T}: Add {U}. {3}, {T}: Create a 2/2 blue Kree Soldier creature token.",
    supertypes={"Legendary"}
)

NIDAVELLIR = make_land(
    name="Nidavellir",
    text="{T}: Add {C}{C}. Spend this mana only to cast artifact spells or activate abilities of artifacts.",
    supertypes={"Legendary"}
)

GENOSHA = make_land(
    name="Genosha",
    text="{T}: Add {R} or {G}. Mutant creatures you control have '{T}: Add one mana of any color.'",
    supertypes={"Legendary"}
)


# =============================================================================
# EXPORT
# =============================================================================

MARVEL_AVENGERS_CARDS = {
    # White - Captain America, Honor, Teamwork
    "Captain America, First Avenger": CAPTAIN_AMERICA,
    "Falcon, Winged Warrior": FALCON,
    "Bucky Barnes, Winter Soldier": BUCKY_BARNES,
    "Peggy Carter, Agent of SHIELD": PEGGY_CARTER,
    "SHIELD Agent": SHIELD_AGENT,
    "SHIELD Recruit": SHIELD_RECRUIT,
    "War Machine, Iron Patriot": WAR_MACHINE,
    "Asgardian Warrior": ASGARDIAN_WARRIOR,
    "Valkyrie, Chooser of the Slain": VALKYRIE,
    "Einherjar Soldier": EINHERJAR_SOLDIER,
    "Lady Sif, Shield Maiden": LADY_SIF,
    "Wakandan Guard": WAKANDAN_GUARD,
    "Okoye, Dora Milaje General": OKOYE,
    "Dora Milaje": DORA_MILAJE,
    "SHIELD Helicarrier Crew": SHIELD_HELICARRIER_CREW,
    "Avengers Medic": AVENGERS_MEDIC,
    "Nova Corps Officer": NOVA_CORPS_OFFICER,
    "Ravager Scout": RAVAGER_SCOUT,

    # Blue - Iron Man, Tech, Strategy
    "Iron Man, Genius Inventor": IRON_MAN,
    "Spider-Man, Friendly Neighborhood": SPIDER_MAN,
    "Doctor Strange, Sorcerer Supreme": DOCTOR_STRANGE,
    "Vision, Synthetic Avenger": VISION,
    "Mr. Fantastic, Reed Richards": MR_FANTASTIC,
    "Stark Industries Drone": STARK_INDUSTRIES_DRONE,
    "FRIDAY, Stark AI": FRIDAY_AI,
    "SHIELD Tech Specialist": SHIELD_TECH_SPECIALIST,
    "Hank Pym, Size Shifter": HANK_PYM,
    "Quantum Realm Explorer": QUANTUM_REALM_EXPLORER,
    "Pym Particle Researcher": PYM_PARTICLE_RESEARCHER,
    "Rocket Raccoon, Weapons Expert": ROCKET_RACCOON,
    "Star-Lord, Legendary Outlaw": STAR_LORD,
    "Kree Sentry": KREE_SENTRY,
    "Skrull Infiltrator": SKRULL_INFILTRATOR,
    "Knowhere Merchant": KNOWHERE_MERCHANT,
    "Ravager Engineer": RAVAGER_ENGINEER,
    "Xandarian Pilot": XANDARIAN_PILOT,

    # Black - Black Widow, Espionage, Antiheroes
    "Black Widow, Master Spy": BLACK_WIDOW,
    "Hawkeye, Never Miss": HAWKEYE,
    "Nick Fury, Director of SHIELD": NICK_FURY,
    "The Punisher, Frank Castle": PUNISHER,
    "Gamora, Deadliest Woman": GAMORA,
    "Loki, God of Mischief": LOKI,
    "HYDRA Agent": HYDRA_AGENT,
    "HYDRA Enforcer": HYDRA_ENFORCER,
    "Winter Soldier Asset": WINTER_SOLDIER_ASSET,
    "Hand Assassin": HAND_ASSASSIN,
    "Kingpin's Enforcer": KINGPIN_ENFORCER,
    "Nebula, Cybernetic Assassin": NEBULA,
    "Crossbones": CROSSBONES,
    "Taskmaster": TASKMASTER,
    "Ghost, Phasing Thief": GHOST,
    "Baron Zemo, Vengeful Noble": ZEMO,
    "Mantis, Empath": MANTIS,
    "Drax the Destroyer": DRAX,
    "Dark Elf Warrior": DARK_ELF_WARRIOR,

    # Red - Thor, Power, Destruction
    "Thor, God of Thunder": THOR,
    "Scarlet Witch, Reality Warper": SCARLET_WITCH,
    "Captain Marvel, Binary": CAPTAIN_MARVEL,
    "Hela, Goddess of Death": HELA,
    "Surtur, Fire Giant": SURTUR,
    "Ultron Prime": ULTRON_PRIME,
    "Ultron Drone": ULTRON_DRONE,
    "Fire Demon": FIRE_DEMON,
    "Asgardian Berserker": ASGARDIAN_BERSERKER,
    "Chitauri Soldier": CHITAURI_SOLDIER,
    "Chitauri Charger": CHITAURI_CHARGER,
    "Chitauri Leviathan": LEVIATHAN,
    "Nova Prime": NOVA_PRIME,
    "Destroyer Armor": DESTROYER_ARMOR,
    "Ronan the Accuser": RONAN_ACCUSER,
    "Sakaaran Gladiator": SAKAARAN_GLADIATOR,
    "Grandmaster's Champion": GRANDMASTER_CHAMPION,
    "Human Torch, Johnny Storm": HUMAN_TORCH,

    # Green - Hulk, Raw Strength, Nature
    "Hulk, Strongest Avenger": HULK,
    "She-Hulk, Jennifer Walters": SHE_HULK,
    "Groot, I Am Groot": GROOT,
    "Black Panther, King of Wakanda": BLACK_PANTHER,
    "Ant-Man, Scott Lang": ANT_MAN,
    "Wasp, Hope Van Dyne": WASP,
    "Ant Swarm": ANT_SWARM,
    "Vibranium Rhino": VIBRANIUM_RHINO,
    "Wakandan War Rhino": WAKANDAN_WAR_RHINO,
    "Shuri, Wakandan Genius": SHURI,
    "Wakandan Border Tribe": WAKANDAN_BORDER_TRIBE,
    "The Thing, Ben Grimm": THING,
    "Abomination": ABOMINATION,
    "Savage Land Raptor": SAVAGE_LAND_RAPTOR,
    "Savage Land Rex": SAVAGE_LAND_REX,
    "Forest Troll": FOREST_TROLL,
    "Korg, Revolutionary": KORG,

    # Multicolor
    "Thanos, The Mad Titan": THANOS,
    "Red Skull, HYDRA Supreme": RED_SKULL,
    "Quicksilver, Pietro Maximoff": QUICKSILVER,
    "Ebony Maw": EBONY_MAW,
    "Proxima Midnight": PROXIMA_MIDNIGHT,
    "Corvus Glaive": CORVUS_GLAIVE,
    "Cull Obsidian": CULL_OBSIDIAN,
    "Wong, Sorcerer of Kamar-Taj": WONG,
    "Baron Mordo": MORDO,
    "Dormammu, Lord of the Dark Dimension": DORMAMMU,

    # X-Men
    "Wolverine, Logan": WOLVERINE,
    "Storm, Weather Witch": STORM,
    "Cyclops, X-Men Leader": CYCLOPS,
    "Jean Grey, Phoenix": JEAN_GREY,
    "Professor X, Charles Xavier": PROFESSOR_X,
    "Magneto, Master of Magnetism": MAGNETO,
    "Rogue, Power Absorber": ROGUE,
    "Beast, Hank McCoy": BEAST,
    "Iceman, Bobby Drake": ICEMAN,
    "Nightcrawler": NIGHTCRAWLER,
    "Colossus, Piotr Rasputin": COLOSSUS,

    # Artifacts - Infinity Stones
    "Mind Stone": MIND_STONE_INFINITY,
    "Space Stone": SPACE_STONE,
    "Time Stone": TIME_STONE,
    "Power Stone": POWER_STONE_INFINITY,
    "Reality Stone": REALITY_STONE,
    "Soul Stone": SOUL_STONE,

    # Artifacts - Equipment
    "Mjolnir": MJOLNIR,
    "Stormbreaker": STORMBREAKER,
    "Captain America's Shield": CAPTAIN_AMERICAS_SHIELD,
    "Iron Man Armor Mk. L": IRON_MAN_ARMOR_MK_L,
    "Iron Man Armor Mk. LXXXV": IRON_MAN_ARMOR_MK_LXXXV,
    "Hulkbuster Armor": HULKBUSTER_ARMOR,
    "Infinity Gauntlet": INFINITY_GAUNTLET,
    "Web-Shooters": WEB_SHOOTERS,
    "Yaka Arrow": YAKA_ARROW,
    "Vibranium Spear": VIBRANIUM_SPEAR,
    "Panther Habit": PANTHER_HABIT,
    "Nano Gauntlet": NANO_GAUNTLET,
    "Chitauri Scepter": CHITAURI_SCEPTER,
    "Cloak of Levitation": CLOAK_OF_LEVITATION,
    "Tesseract": TESSERACT,
    "Eye of Agamotto": EYE_OF_AGAMOTTO,

    # Artifacts - Vehicles
    "Quinjet": QUINJET,
    "The Milano": MILANO,
    "SHIELD Helicarrier": HELICARRIER,
    "The Benatar": BENATAR,

    # Instants
    "Repulsor Blast": REPULSOR_BLAST,
    "Shield Throw": SHIELD_THROW,
    "Call the Bifrost": LIGHTNING_STRIKE_THOR,
    "Widow's Sting": WIDOW_STING,
    "Chaos Magic": CHAOS_MAGIC,
    "Sling Ring Portal": PORTAL_SLING_RING,
    "Time Reversal": TIME_REVERSAL,
    "Pym Particles": SHRINK_RAY,
    "Mystic Arts": MYSTIC_ARTS,
    "Blitz Attack": BLITZ_ATTACK,
    "Tactical Genius": TACTICAL_GENIUS,
    "Berserker Rage": BERSERKER_RAGE,
    "Stealth Mission": STEALTH_MISSION,
    "Heroic Sacrifice": HEROIC_SACRIFICE,
    "Impale": IMPALE,

    # Sorceries
    "Avengers Assemble": AVENGERS_ASSEMBLE,
    "Hulk Smash": HULK_SMASH,
    "Snap": SNAP_FINGERS,
    "Gamma Radiation": GAMMA_RADIATION,
    "Arrow Volley": ARROW_VOLLEY,
    "Wakanda Forever": WAKANDA_FOREVER,
    "Cosmic Awareness": COSMIC_AWARENESS,
    "Super Soldier Serum": SUPER_SOLDIER_SERUM,
    "Reality Warp": REALITY_WARP,

    # Enchantments
    "Avengers Initiative": AVENGERS_INITIATIVE,
    "Stark Industries": STARK_INDUSTRIES,
    "SHIELD Headquarters": SHIELD_HEADQUARTERS,
    "Guardians of the Galaxy United": GUARDIANS_BOND,
    "HYDRA's Influence": HYDRA_INFLUENCE,
    "Asgardian Might": ASGARDIAN_MIGHT,
    "Mutant Uprising": MUTANT_UPRISING,
    "Cosmic Convergence": COSMIC_CONVERGENCE,
    "Dark Dimension": DARK_DIMENSION,
    "Vibranium Mines": VIBRANIUM_MINES,

    # Lands
    "Avengers Tower": AVENGERS_TOWER,
    "Stark Tower": STARK_TOWER,
    "Wakanda": WAKANDA,
    "Asgard, Realm Eternal": ASGARD,
    "Sanctum Sanctorum": SANCTUM_SANCTORUM,
    "Knowhere": KNOWHERE,
    "Xavier's School for Gifted Youngsters": XAVIERS_SCHOOL,
    "HYDRA Base": HYDRA_BASE,
    "SHIELD Facility": SHIELD_FACILITY,
    "Titan": TITAN,
    "Vormir": VORMIR,
    "Sakaar": SAKAAR,
    "Contraxia": CONTRAXIA,
    "Hala": HALA,
    "Nidavellir": NIDAVELLIR,
    "Genosha": GENOSHA,
}
