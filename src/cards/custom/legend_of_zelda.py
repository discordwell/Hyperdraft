"""
Legend of Zelda: Hyrule Chronicles (LOZ) Card Implementations

Set released January 2026. ~250 cards.
Features mechanics: Dungeon, Triforce, Heart Container
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


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set, text: str,
                           subtypes: set = None, supertypes: set = None, setup_interceptors=None):
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
# ZELDA KEYWORD MECHANICS
# =============================================================================

def make_dungeon_trigger(source_obj: GameObject, room_count: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Dungeon N - When this creature attacks, venture through the dungeon.
    After N rooms, trigger the effect.
    """
    def dungeon_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == source_obj.id)

    def dungeon_handler(event: Event, state: GameState) -> InterceptorResult:
        dungeon_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': source_obj.id, 'counter_type': 'dungeon_room', 'amount': 1},
            source=source_obj.id
        )
        current_rooms = source_obj.state.counters.get('dungeon_room', 0)
        if current_rooms + 1 >= room_count:
            effect_events = effect_fn(event, state)
            reset_event = Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': source_obj.id, 'counter_type': 'dungeon_room', 'amount': room_count},
                source=source_obj.id
            )
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[dungeon_event, reset_event] + effect_events)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[dungeon_event])

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=dungeon_filter,
        handler=dungeon_handler,
        duration='while_on_battlefield'
    )


def make_triforce_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int, pieces_required: int = 3) -> list[Interceptor]:
    """
    Triforce - This creature gets +X/+Y as long as you control N or more artifacts with 'Triforce' in their name.
    """
    def triforce_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        triforce_count = sum(1 for obj in state.objects.values()
                            if obj.controller == source_obj.controller
                            and obj.zone == ZoneType.BATTLEFIELD
                            and CardType.ARTIFACT in obj.characteristics.types
                            and 'Triforce' in obj.characteristics.name)
        return triforce_count >= pieces_required

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, triforce_filter)


def make_heart_container(source_obj: GameObject, life_amount: int) -> Interceptor:
    """
    Heart Container - When this permanent enters, you gain N life.
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': source_obj.controller, 'amount': life_amount}, source=source_obj.id)]
    return make_etb_trigger(source_obj, etb_effect)


def hylian_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Hylian")

def zora_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Zora")

def goron_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Goron")

def gerudo_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Gerudo")

def kokiri_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Kokiri")

def sheikah_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Sheikah")

def rito_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Rito")


# =============================================================================
# WHITE CARDS - LIGHT, SHEIKAH, PROTECTION
# =============================================================================

# --- Legendary Creatures ---

def zelda_princess_of_hyrule_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_triforce_bonus(obj, 2, 2, 2))
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors

ZELDA_PRINCESS_OF_HYRULE = make_creature(
    name="Zelda, Princess of Hyrule",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance. Triforce - Zelda gets +2/+2 as long as you control two or more Triforce artifacts. When Zelda enters, you gain 3 life.",
    setup_interceptors=zelda_princess_of_hyrule_setup
)


def zelda_wielder_of_wisdom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, controller_only=True)]

ZELDA_WIELDER_OF_WISDOM = make_creature(
    name="Zelda, Wielder of Wisdom",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Hylian", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, draw a card.",
    setup_interceptors=zelda_wielder_of_wisdom_setup
)


def impa_sheikah_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(obj, ['hexproof'], other_creatures_with_subtype(obj, "Sheikah"))]

IMPA_SHEIKAH_GUARDIAN = make_creature(
    name="Impa, Sheikah Guardian",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    supertypes={"Legendary"},
    text="Flash. Other Sheikah creatures you control have hexproof.",
    setup_interceptors=impa_sheikah_guardian_setup
)


def rauru_sage_of_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

RAURU_SAGE_OF_LIGHT = make_creature(
    name="Rauru, Sage of Light",
    power=2, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you gain 2 life.",
    setup_interceptors=rauru_sage_of_light_setup
)


def hylia_goddess_of_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_you_control(obj)))
    return interceptors

HYLIA_GODDESS_OF_LIGHT = make_creature(
    name="Hylia, Goddess of Light",
    power=4, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Other creatures you control get +1/+1.",
    setup_interceptors=hylia_goddess_of_light_setup
)


# --- Regular Creatures ---

def sheikah_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SHEIKAH_WARRIOR = make_creature(
    name="Sheikah Warrior",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    text="When Sheikah Warrior enters, you gain 2 life.",
    setup_interceptors=sheikah_warrior_setup
)


HYRULE_KNIGHT = make_creature(
    name="Hyrule Knight",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
    text="Vigilance, first strike."
)


def temple_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_heart_container(obj, 3)]

TEMPLE_GUARDIAN = make_creature(
    name="Temple Guardian",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Soldier"},
    text="Defender. Heart Container - When Temple Guardian enters, you gain 3 life.",
    setup_interceptors=temple_guardian_setup
)


CASTLE_GUARD = make_creature(
    name="Castle Guard",
    power=2, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
    text="Vigilance."
)


LIGHT_SPIRIT = make_creature(
    name="Light Spirit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying. When Light Spirit dies, you gain 2 life."
)


HYLIAN_PRIESTESS = make_creature(
    name="Hylian Priestess",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Cleric"},
    text="Lifelink. {T}: You gain 1 life."
)


def sheikah_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SHEIKAH_SCOUT = make_creature(
    name="Sheikah Scout",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Scout"},
    text="When Sheikah Scout enters, scry 2.",
    setup_interceptors=sheikah_scout_setup
)


COURAGE_FAIRY = make_creature(
    name="Courage Fairy",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
    text="Flying. Sacrifice Courage Fairy: Target creature gains indestructible until end of turn."
)


HYRULE_CAPTAIN = make_creature(
    name="Hyrule Captain",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
    text="First strike. Other Soldier and Knight creatures you control get +1/+0."
)


GREAT_FAIRY = make_creature(
    name="Great Fairy",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
    text="Flying. When Great Fairy enters, you gain 5 life and create two 1/1 white Fairy creature tokens with flying."
)


SACRED_REALM_GUARDIAN = make_creature(
    name="Sacred Realm Guardian",
    power=4, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, vigilance. Prevent all damage that would be dealt to other creatures you control."
)


# --- Instants/Sorceries ---

DINS_FIRE_SHIELD = make_instant(
    name="Din's Fire Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to you and creatures you control this turn."
)


LIGHT_ARROW = make_instant(
    name="Light Arrow",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature. Its controller gains life equal to its toughness."
)


NAYRUS_LOVE = make_instant(
    name="Nayru's Love",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control gain hexproof and indestructible until end of turn."
)


SONG_OF_HEALING = make_sorcery(
    name="Song of Healing",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. If you control an artifact, you gain 6 life instead."
)


BLESSING_OF_HYLIA = make_sorcery(
    name="Blessing of Hylia",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+2 until end of turn. You gain 1 life for each creature you control."
)


# =============================================================================
# BLUE CARDS - ZORA, WATER, WISDOM
# =============================================================================

# --- Legendary Creatures ---

def mipha_zora_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

MIPHA_ZORA_CHAMPION = make_creature(
    name="Mipha, Zora Champion",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Champion"},
    supertypes={"Legendary"},
    text="Lifelink. At the beginning of your upkeep, you gain 2 life. {2}{U}: Return target creature to its owner's hand.",
    setup_interceptors=mipha_zora_champion_setup
)


def ruto_zora_princess_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Zora")))
    return interceptors

RUTO_ZORA_PRINCESS = make_creature(
    name="Ruto, Zora Princess",
    power=3, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble"},
    supertypes={"Legendary"},
    text="Other Zora creatures you control get +1/+1. Zora creatures you control can't be blocked.",
    setup_interceptors=ruto_zora_princess_setup
)


def king_zora_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

KING_ZORA = make_creature(
    name="King Zora, Domain Ruler",
    power=2, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble"},
    supertypes={"Legendary"},
    text="When King Zora enters, draw two cards. Zora creatures you control have '{T}: Add {U}.'",
    setup_interceptors=king_zora_setup
)


def nayru_oracle_of_wisdom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_draw_trigger(obj, draw_effect)]

NAYRU_ORACLE_OF_WISDOM = make_creature(
    name="Nayru, Oracle of Wisdom",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you draw a card, scry 1.",
    setup_interceptors=nayru_oracle_of_wisdom_setup
)


def sidon_zora_prince_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

SIDON_ZORA_PRINCE = make_creature(
    name="Sidon, Zora Prince",
    power=4, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever Sidon attacks, draw a card.",
    setup_interceptors=sidon_zora_prince_setup
)


# --- Regular Creatures ---

ZORA_WARRIOR = make_creature(
    name="Zora Warrior",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Warrior"},
    text="Zora Warrior can't be blocked."
)


def zora_scholar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ZORA_SCHOLAR = make_creature(
    name="Zora Scholar",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Wizard"},
    text="When Zora Scholar enters, draw a card.",
    setup_interceptors=zora_scholar_setup
)


RIVER_ZORA = make_creature(
    name="River Zora",
    power=2, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Zora"},
    text="River Zora can't be blocked as long as defending player controls an Island."
)


WATER_SPIRIT = make_creature(
    name="Water Spirit",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Spirit"},
    text="Hexproof."
)


OCTOROK = make_creature(
    name="Octorok",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Beast"},
    text="{T}: Octorok deals 1 damage to target creature or planeswalker."
)


LIKE_LIKE = make_creature(
    name="Like-Like",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Ooze"},
    text="Whenever Like-Like deals combat damage to a player, you may attach target Equipment that player controls to Like-Like."
)


GYORG = make_creature(
    name="Gyorg",
    power=4, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fish"},
    text="Islandwalk. Whenever Gyorg deals combat damage to a player, draw a card."
)


ZORA_DIVER = make_creature(
    name="Zora Diver",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Scout"},
    text="When Zora Diver enters, scry 2."
)


ZORA_SPEARMAN = make_creature(
    name="Zora Spearman",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Warrior"},
    text="Reach. Zora Spearman can block creatures with flying."
)


def zora_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect)]

ZORA_SAGE = make_creature(
    name="Zora Sage",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Wizard"},
    text="Whenever you cast a spell, scry 1.",
    setup_interceptors=zora_sage_setup
)


# --- Instants/Sorceries ---

ZORAS_SAPPHIRE_BLESSING = make_instant(
    name="Zora's Sapphire Blessing",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gains hexproof until end of turn. Draw a card."
)


TORRENTIAL_WAVE = make_instant(
    name="Torrential Wave",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Return all nonland permanents to their owners' hands."
)


WATER_TEMPLE_FLOOD = make_sorcery(
    name="Water Temple Flood",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Tap all creatures your opponents control. Those creatures don't untap during their controllers' next untap step."
)


WISDOM_OF_AGES = make_sorcery(
    name="Wisdom of Ages",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card."
)


COUNTER_MAGIC = make_instant(
    name="Counter Magic",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell."
)


# =============================================================================
# BLACK CARDS - GANON, TWILIGHT, DARKNESS
# =============================================================================

# --- Legendary Creatures ---

def ganondorf_king_of_evil_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_triforce_bonus(obj, 3, 3, 1))
    def death_effect(event: Event, state: GameState) -> list[Event]:
        for p_id in all_opponents(obj, state):
            return [Event(type=EventType.LIFE_CHANGE, payload={'player': p_id, 'amount': -3}, source=obj.id)]
        return []
    interceptors.append(make_death_trigger(obj, death_effect))
    return interceptors

GANONDORF_KING_OF_EVIL = make_creature(
    name="Ganondorf, King of Evil",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Gerudo", "Warlock"},
    supertypes={"Legendary"},
    text="Menace. Triforce - Ganondorf gets +3/+3 as long as you control a Triforce artifact. When Ganondorf dies, each opponent loses 3 life.",
    setup_interceptors=ganondorf_king_of_evil_setup
)


def ganon_calamity_incarnate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': p_id, 'amount': 1}, source=obj.id))
        return events
    return [make_attack_trigger(obj, attack_effect)]

GANON_CALAMITY_INCARNATE = make_creature(
    name="Ganon, Calamity Incarnate",
    power=7, toughness=7,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Beast"},
    supertypes={"Legendary"},
    text="Trample, menace. Whenever Ganon attacks, each opponent discards a card.",
    setup_interceptors=ganon_calamity_incarnate_setup
)


def zant_twilight_usurper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DESTROY, payload={'target': 'creature', 'controller': 'opponent'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ZANT_TWILIGHT_USURPER = make_creature(
    name="Zant, Twilight Usurper",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Twili", "Warlock"},
    supertypes={"Legendary"},
    text="When Zant enters, destroy target creature an opponent controls.",
    setup_interceptors=zant_twilight_usurper_setup
)


def midna_twilight_princess_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

MIDNA_TWILIGHT_PRINCESS = make_creature(
    name="Midna, Twilight Princess",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Twili", "Noble"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Midna deals combat damage to a player, draw a card.",
    setup_interceptors=midna_twilight_princess_setup
)


def vaati_wind_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': p_id, 'amount': -1}, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

VAATI_WIND_MAGE = make_creature(
    name="Vaati, Wind Mage",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Minish", "Warlock"},
    supertypes={"Legendary"},
    text="Flying. At the beginning of your upkeep, each opponent loses 1 life.",
    setup_interceptors=vaati_wind_mage_setup
)


# --- Regular Creatures ---

def shadow_beast_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Shadow', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Shadow'}}
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

SHADOW_BEAST = make_creature(
    name="Shadow Beast",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Shadow"},
    text="When Shadow Beast dies, create a 1/1 black Shadow creature token.",
    setup_interceptors=shadow_beast_setup
)


STALFOS_WARRIOR = make_creature(
    name="Stalfos Warrior",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Warrior"},
    text="When Stalfos Warrior dies, return it to the battlefield tapped at the beginning of the next end step."
)


REDEAD = make_creature(
    name="ReDead",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When ReDead enters, tap target creature an opponent controls. That creature doesn't untap during its controller's next untap step."
)


GIBDO = make_creature(
    name="Gibdo",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Lifelink. Other Zombie creatures you control have lifelink."
)


POES = make_creature(
    name="Poe",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying. When Poe dies, each opponent loses 1 life and you gain 1 life."
)


DARK_NUT = make_creature(
    name="Darknut",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Knight"},
    text="First strike. Darknut can't be the target of spells or abilities your opponents control."
)


PHANTOM = make_creature(
    name="Phantom",
    power=3, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Knight"},
    text="Defender, menace. {2}{B}: Phantom can attack this turn as though it didn't have defender."
)


FLOORMASTER = make_creature(
    name="Floormaster",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When Floormaster deals combat damage to a player, that player sacrifices a creature."
)


DEAD_HAND = make_creature(
    name="Dead Hand",
    power=1, toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Horror"},
    text="Defender. Whenever a creature blocks Dead Hand, tap that creature. It doesn't untap during its controller's next untap step."
)


WALLMASTER = make_creature(
    name="Wallmaster",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flying. When Wallmaster deals combat damage to a player, exile target creature that player controls until Wallmaster leaves the battlefield."
)


# --- Instants/Sorceries ---

TWILIGHT_CURSE = make_instant(
    name="Twilight Curse",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn."
)


DARKNESS_FALLS = make_sorcery(
    name="Darkness Falls",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures with power 2 or less."
)


MALICE_SPREAD = make_sorcery(
    name="Malice Spread",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. You gain life equal to the total power of creatures sacrificed this way."
)


SOUL_HARVEST = make_instant(
    name="Soul Harvest",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Destroy target creature that was dealt damage this turn."
)


GANONS_WRATH = make_sorcery(
    name="Ganon's Wrath",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. You lose 1 life for each creature destroyed this way."
)


# =============================================================================
# RED CARDS - GORON, FIRE, POWER
# =============================================================================

# --- Legendary Creatures ---

def daruk_goron_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': event.payload.get('defending_player', ''),
            'amount': 2,
            'source': obj.id
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

DARUK_GORON_CHAMPION = make_creature(
    name="Daruk, Goron Champion",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Champion"},
    supertypes={"Legendary"},
    text="Trample. Whenever Daruk deals combat damage to a player, Daruk deals 2 damage to that player.",
    setup_interceptors=daruk_goron_champion_setup
)


def darunia_goron_chief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Goron")))
    return interceptors

DARUNIA_GORON_CHIEF = make_creature(
    name="Darunia, Goron Chief",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    supertypes={"Legendary"},
    text="Other Goron creatures you control get +1/+1. Goron creatures you control have haste.",
    setup_interceptors=darunia_goron_chief_setup
)


def din_oracle_of_power_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': 'any', 'amount': 2}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

DIN_ORACLE_OF_POWER = make_creature(
    name="Din, Oracle of Power",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Haste. Whenever Din attacks, she deals 2 damage to any target.",
    setup_interceptors=din_oracle_of_power_setup
)


def volvagia_fire_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': 'each_opponent_creature', 'amount': 1}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

VOLVAGIA_FIRE_DRAGON = make_creature(
    name="Volvagia, Fire Dragon",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying, haste. Whenever Volvagia attacks, it deals 1 damage to each creature defending player controls.",
    setup_interceptors=volvagia_fire_dragon_setup
)


def yunobo_goron_descendant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': 'any', 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

YUNOBO_GORON_DESCENDANT = make_creature(
    name="Yunobo, Goron Descendant",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    supertypes={"Legendary"},
    text="When Yunobo enters, he deals 3 damage to any target.",
    setup_interceptors=yunobo_goron_descendant_setup
)


# --- Regular Creatures ---

GORON_WARRIOR = make_creature(
    name="Goron Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    text="Trample."
)


def goron_smith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Equipment Token', 'types': {CardType.ARTIFACT}, 'subtypes': {'Equipment'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

GORON_SMITH = make_creature(
    name="Goron Smith",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Artificer"},
    text="When Goron Smith enters, create a colorless Equipment artifact token with 'Equipped creature gets +1/+1. Equip {1}.'",
    setup_interceptors=goron_smith_setup
)


DODONGO = make_creature(
    name="Dodongo",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Trample. Dodongo can't be dealt damage by red sources."
)


FIRE_KEESE = make_creature(
    name="Fire Keese",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Bat"},
    text="Flying, haste. When Fire Keese deals combat damage to a creature, destroy that creature at end of turn."
)


LIZALFOS = make_creature(
    name="Lizalfos",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="First strike. {R}: Lizalfos gets +1/+0 until end of turn."
)


LYNEL = make_creature(
    name="Lynel",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Beast", "Warrior"},
    text="Trample, haste. When Lynel attacks, it deals 2 damage to target creature or planeswalker."
)


MOBLIN = make_creature(
    name="Moblin",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Menace."
)


HINOX = make_creature(
    name="Hinox",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Trample. Hinox must attack each combat if able."
)


GORON_ELDER = make_creature(
    name="Goron Elder",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Cleric"},
    text="Other Goron creatures you control have trample."
)


FIRE_SPIRIT = make_creature(
    name="Fire Spirit",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Spirit"},
    text="Haste. When Fire Spirit dies, it deals 2 damage to any target."
)


# --- Instants/Sorceries ---

DINS_FIRE = make_instant(
    name="Din's Fire",
    mana_cost="{R}",
    colors={Color.RED},
    text="Din's Fire deals 2 damage to any target."
)


FIRE_ARROW = make_instant(
    name="Fire Arrow",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Fire Arrow deals 3 damage to target creature. If that creature dies this turn, exile it."
)


VOLCANIC_ERUPTION = make_sorcery(
    name="Volcanic Eruption",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Volcanic Eruption deals 4 damage to each creature and each player."
)


GORON_RAGE = make_instant(
    name="Goron Rage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains trample until end of turn."
)


BOMB_BARRAGE = make_sorcery(
    name="Bomb Barrage",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Bomb Barrage deals 1 damage to each creature and each opponent. If you control a Goron, it deals 2 damage instead."
)


# =============================================================================
# GREEN CARDS - KOKIRI, FOREST, COURAGE
# =============================================================================

# --- Legendary Creatures ---

def link_hero_of_time_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_triforce_bonus(obj, 2, 2, 1))
    def dungeon_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_dungeon_trigger(obj, 3, dungeon_effect))
    return interceptors

LINK_HERO_OF_TIME = make_creature(
    name="Link, Hero of Time",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hylian", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance. Triforce - Link gets +2/+2 as long as you control a Triforce artifact. Dungeon 3 - Whenever Link attacks, add a dungeon counter. At 3 counters, draw a card and reset.",
    setup_interceptors=link_hero_of_time_setup
)


def link_champion_of_hyrule_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'boost': 'link_boost', 'controller': obj.controller, 'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

LINK_CHAMPION_OF_HYRULE = make_creature(
    name="Link, Champion of Hyrule",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hylian", "Champion"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Link attacks, other creatures you control get +1/+1 until end of turn.",
    setup_interceptors=link_champion_of_hyrule_setup
)


def saria_forest_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Kokiri")))
    return interceptors

SARIA_FOREST_SAGE = make_creature(
    name="Saria, Forest Sage",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri", "Druid"},
    supertypes={"Legendary"},
    text="Other Kokiri creatures you control get +1/+1. {T}: Add {G}{G}.",
    setup_interceptors=saria_forest_sage_setup
)


def revali_rito_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TAP, payload={'target': 'creature'}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

REVALI_RITO_CHAMPION = make_creature(
    name="Revali, Rito Champion",
    power=3, toughness=3,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Rito", "Champion"},
    supertypes={"Legendary"},
    text="Flying. Whenever Revali attacks, tap target creature an opponent controls.",
    setup_interceptors=revali_rito_champion_setup
)


def great_deku_tree_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Deku Sprout', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Plant'}}
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

GREAT_DEKU_TREE = make_creature(
    name="Great Deku Tree",
    power=0, toughness=8,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"},
    supertypes={"Legendary"},
    text="Defender. At the beginning of your upkeep, create a 1/1 green Plant creature token. {T}: Add {G} for each Plant you control.",
    setup_interceptors=great_deku_tree_setup
)


def farore_oracle_of_courage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spirit', 'power': 2, 'toughness': 2, 'colors': {Color.GREEN}, 'subtypes': {'Spirit'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

FARORE_ORACLE_OF_COURAGE = make_creature(
    name="Farore, Oracle of Courage",
    power=3, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    supertypes={"Legendary"},
    text="When Farore enters, create a 2/2 green Spirit creature token. Creatures you control have trample.",
    setup_interceptors=farore_oracle_of_courage_setup
)


# --- Regular Creatures ---

KOKIRI_CHILD = make_creature(
    name="Kokiri Child",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri"},
    text="When Kokiri Child enters, add {G}."
)


KOKIRI_WARRIOR = make_creature(
    name="Kokiri Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri", "Warrior"},
    text="Forestwalk."
)


SKULL_KID = make_creature(
    name="Skull Kid",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="When Skull Kid enters, target creature can't block this turn."
)


DEKU_SCRUB = make_creature(
    name="Deku Scrub",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="{T}: Deku Scrub deals 1 damage to target creature with flying."
)


FOREST_FAIRY = make_creature(
    name="Forest Fairy",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fairy"},
    text="Flying. {T}: Add {G}."
)


WOLFOS = make_creature(
    name="Wolfos",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="Vigilance. Wolfos gets +1/+1 as long as you control a Forest."
)


FOREST_TEMPLE_GUARDIAN = make_creature(
    name="Forest Temple Guardian",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
    text="Vigilance, reach."
)


DEKU_BABA = make_creature(
    name="Deku Baba",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Reach. When Deku Baba dies, create a 1/1 green Plant creature token."
)


RITO_WARRIOR = make_creature(
    name="Rito Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Warrior"},
    text="Flying."
)


KOROKS = make_creature(
    name="Korok",
    power=0, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spirit"},
    text="When Korok enters, look at the top card of your library. You may put it on the bottom."
)


# --- Instants/Sorceries ---

FARORES_WIND = make_instant(
    name="Farore's Wind",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gains hexproof and indestructible until end of turn. Untap it."
)


FOREST_BLESSING = make_sorcery(
    name="Forest Blessing",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic Forest card and put it onto the battlefield tapped. Create a 1/1 green Plant creature token."
)


NATURES_FURY = make_sorcery(
    name="Nature's Fury",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +2/+2 and gain trample until end of turn."
)


DEKU_NUT_STUN = make_instant(
    name="Deku Nut Stun",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)


WILD_GROWTH = make_enchantment(
    name="Wild Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchant land. Enchanted land has '{T}: Add {G}{G}.'"
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def urbosa_gerudo_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': 'each_creature_opponent', 'amount': 2}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

URBOSA_GERUDO_CHAMPION = make_creature(
    name="Urbosa, Gerudo Champion",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Gerudo", "Champion"},
    supertypes={"Legendary"},
    text="Haste. Whenever Urbosa attacks, she deals 2 damage to each creature defending player controls.",
    setup_interceptors=urbosa_gerudo_champion_setup
)


def fi_sword_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect)]

FI_SWORD_SPIRIT = make_creature(
    name="Fi, Sword Spirit",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast a spell, scry 1. {T}: Target Equipment becomes attached to target creature you control.",
    setup_interceptors=fi_sword_spirit_setup
)


def nabooru_spirit_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TAP, payload={'target': 'artifact'}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

NABOORU_SPIRIT_SAGE = make_creature(
    name="Nabooru, Spirit Sage",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Gerudo", "Cleric"},
    supertypes={"Legendary"},
    text="First strike. Whenever Nabooru attacks, tap target artifact or creature.",
    setup_interceptors=nabooru_spirit_sage_setup
)


def skull_kid_masked_menace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': p_id, 'amount': 1, 'random': True}, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

SKULL_KID_MASKED_MENACE = make_creature(
    name="Skull Kid, Masked Menace",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Menace. At the beginning of your upkeep, each opponent discards a card at random.",
    setup_interceptors=skull_kid_masked_menace_setup
)


def tetra_pirate_princess_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

TETRA_PIRATE_PRINCESS = make_creature(
    name="Tetra, Pirate Princess",
    power=3, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Hylian", "Pirate"},
    supertypes={"Legendary"},
    text="First strike. Whenever Tetra deals combat damage to a player, create a Treasure token.",
    setup_interceptors=tetra_pirate_princess_setup
)


def groose_skyloft_hero_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.PUMP, payload={'object_id': obj.id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

GROOSE_SKYLOFT_HERO = make_creature(
    name="Groose, Skyloft Hero",
    power=3, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Hylian", "Warrior"},
    supertypes={"Legendary"},
    text="Flying. Whenever Groose attacks, he gets +2/+0 until end of turn.",
    setup_interceptors=groose_skyloft_hero_setup
)


MALON_RANCH_KEEPER = make_creature(
    name="Malon, Ranch Keeper",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hylian", "Druid"},
    supertypes={"Legendary"},
    text="When Malon enters, create two 1/1 green Horse creature tokens. Horses you control get +1/+1."
)


# =============================================================================
# ARTIFACTS - TRIFORCE, DIVINE BEASTS, ITEMS
# =============================================================================

# --- Triforce Pieces ---

TRIFORCE_OF_POWER = make_artifact(
    name="Triforce of Power",
    mana_cost="{3}",
    text="Creatures you control get +1/+0. {T}: Target creature gets +3/+0 until end of turn.",
    supertypes={"Legendary"}
)


TRIFORCE_OF_WISDOM = make_artifact(
    name="Triforce of Wisdom",
    mana_cost="{3}",
    text="Whenever you draw a card, you may pay {1}. If you do, scry 1. {T}: Draw a card, then discard a card.",
    supertypes={"Legendary"}
)


TRIFORCE_OF_COURAGE = make_artifact(
    name="Triforce of Courage",
    mana_cost="{3}",
    text="Creatures you control have vigilance. {T}: Target creature gains indestructible until end of turn.",
    supertypes={"Legendary"}
)


# --- Divine Beasts ---

def divine_beast_vah_ruta_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

DIVINE_BEAST_VAH_RUTA = make_artifact(
    name="Divine Beast Vah Ruta",
    mana_cost="{5}",
    text="At the beginning of your upkeep, you gain 2 life. {3}, {T}: Return target creature to its owner's hand.",
    supertypes={"Legendary"},
    setup_interceptors=divine_beast_vah_ruta_setup
)


def divine_beast_vah_rudania_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': 'any', 'amount': 2}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

DIVINE_BEAST_VAH_RUDANIA = make_artifact(
    name="Divine Beast Vah Rudania",
    mana_cost="{5}",
    text="At the beginning of your upkeep, Divine Beast Vah Rudania deals 2 damage to any target. {3}, {T}: It deals 3 damage to target creature.",
    supertypes={"Legendary"},
    setup_interceptors=divine_beast_vah_rudania_setup
)


def divine_beast_vah_medoh_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

DIVINE_BEAST_VAH_MEDOH = make_artifact(
    name="Divine Beast Vah Medoh",
    mana_cost="{5}",
    text="At the beginning of your upkeep, scry 2. {3}, {T}: Target creature gains flying until end of turn.",
    supertypes={"Legendary"},
    setup_interceptors=divine_beast_vah_medoh_setup
)


def divine_beast_vah_naboris_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': 'each_opponent', 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

DIVINE_BEAST_VAH_NABORIS = make_artifact(
    name="Divine Beast Vah Naboris",
    mana_cost="{5}",
    text="At the beginning of your upkeep, Vah Naboris deals 1 damage to each opponent. {3}, {T}: Tap target creature.",
    supertypes={"Legendary"},
    setup_interceptors=divine_beast_vah_naboris_setup
)


# --- Equipment ---

MASTER_SWORD = make_equipment(
    name="Master Sword",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has vigilance. If equipped creature is legendary, it also has indestructible.",
    supertypes={"Legendary"}
)


HYLIAN_SHIELD = make_equipment(
    name="Hylian Shield",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +0/+3 and has hexproof.",
    supertypes={"Legendary"}
)


HEROS_BOW = make_equipment(
    name="Hero's Bow",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has '{T}: This creature deals 2 damage to target creature with flying.'"
)


BIGGORONS_SWORD = make_equipment(
    name="Biggoron's Sword",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +5/+0 and has trample. Equipped creature can't block.",
    supertypes={"Legendary"}
)


MIRROR_SHIELD = make_equipment(
    name="Mirror Shield",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2. Whenever equipped creature is dealt damage by a source, that source's controller loses that much life."
)


ANCIENT_BOW = make_equipment(
    name="Ancient Bow",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+1 and has '{T}: This creature deals 3 damage to any target.'"
)


KOKIRI_SWORD = make_equipment(
    name="Kokiri Sword",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1."
)


# --- Masks ---

MAJORAS_MASK = make_equipment(
    name="Majora's Mask",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has menace. At the beginning of your upkeep, you lose 1 life.",
    subtypes={"Mask"},
    supertypes={"Legendary"}
)


FIERCE_DEITY_MASK = make_equipment(
    name="Fierce Deity Mask",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +4/+4 and has double strike. Equip only to a legendary creature.",
    subtypes={"Mask"},
    supertypes={"Legendary"}
)


DEKU_MASK = make_equipment(
    name="Deku Mask",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature has '{T}: Add {G}.' and is a Plant in addition to its other types.",
    subtypes={"Mask"}
)


GORON_MASK = make_equipment(
    name="Goron Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+2, has trample, and is a Goron in addition to its other types.",
    subtypes={"Mask"}
)


ZORA_MASK = make_equipment(
    name="Zora Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2, can't be blocked, and is a Zora in addition to its other types.",
    subtypes={"Mask"}
)


BUNNY_HOOD = make_equipment(
    name="Bunny Hood",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+0 and has haste.",
    subtypes={"Mask"}
)


STONE_MASK = make_equipment(
    name="Stone Mask",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has hexproof and can't attack or block.",
    subtypes={"Mask"}
)


# --- Other Artifacts ---

OCARINA_OF_TIME = make_artifact(
    name="Ocarina of Time",
    mana_cost="{3}",
    text="{2}, {T}: Choose one - Return target creature to its owner's hand; or untap all creatures you control; or scry 3.",
    supertypes={"Legendary"}
)


SHEIKAH_SLATE = make_artifact(
    name="Sheikah Slate",
    mana_cost="{2}",
    text="{T}: Look at the top card of your library. {1}, {T}: Scry 2.",
    supertypes={"Legendary"}
)


BOMB_BAG = make_artifact(
    name="Bomb Bag",
    mana_cost="{2}",
    text="{2}, {T}: Bomb Bag deals 2 damage to any target."
)


FAIRY_BOTTLE = make_artifact(
    name="Fairy Bottle",
    mana_cost="{1}",
    text="Sacrifice Fairy Bottle: You gain 5 life."
)


MAGIC_BOOMERANG = make_artifact(
    name="Magic Boomerang",
    mana_cost="{2}",
    text="{1}, {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)


HOOKSHOT = make_artifact(
    name="Hookshot",
    mana_cost="{2}",
    text="{2}, {T}: Put target creature you control on top of its owner's library. Draw a card."
)


HEART_CONTAINER_ARTIFACT = make_artifact(
    name="Heart Container",
    mana_cost="{2}",
    text="When Heart Container enters, you gain 4 life. Sacrifice Heart Container: You gain 2 life."
)


LENS_OF_TRUTH = make_artifact(
    name="Lens of Truth",
    mana_cost="{2}",
    text="{1}, {T}: Look at target player's hand. You may look at face-down cards on the battlefield."
)


ANCIENT_CORE = make_artifact(
    name="Ancient Core",
    mana_cost="{3}",
    text="{T}: Add {C}{C}. Activate only if you control an artifact creature."
)


GUARDIAN_PARTS = make_artifact(
    name="Guardian Parts",
    mana_cost="{1}",
    text="Sacrifice Guardian Parts: Add {C}{C}. Spend this mana only to cast artifact spells or activate abilities of artifacts."
)


# =============================================================================
# ENCHANTMENTS
# =============================================================================

SACRED_PROTECTION = make_enchantment(
    name="Sacred Protection",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control have hexproof."
)


ZORAS_DOMAIN = make_enchantment(
    name="Zora's Domain",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Creatures you control can't be blocked."
)


TWILIGHT_REALM = make_enchantment(
    name="Twilight Realm",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Whenever a creature dies, each opponent loses 1 life and you gain 1 life."
)


GORON_STRENGTH = make_enchantment(
    name="Goron Strength",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0 and have trample."
)


KOKIRI_FOREST = make_enchantment(
    name="Kokiri Forest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, create a 1/1 green Plant creature token."
)


HYLIA_BLESSING = make_enchantment(
    name="Hylia's Blessing",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchant creature. Enchanted creature gets +1/+2 and has lifelink."
)


ANCIENT_TECHNOLOGY = make_enchantment(
    name="Ancient Technology",
    mana_cost="{2}",
    colors=set(),
    text="Artifact spells you cast cost {1} less to cast."
)


SPIRIT_TRACKS = make_enchantment(
    name="Spirit Tracks",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Creatures you control have vigilance. Whenever a creature you control attacks, scry 1."
)


# =============================================================================
# LANDS
# =============================================================================

HYRULE_CASTLE = make_land(
    name="Hyrule Castle",
    text="{T}: Add {W}. {2}, {T}: Create a 1/1 white Soldier creature token.",
    supertypes={"Legendary"}
)


DEATH_MOUNTAIN = make_land(
    name="Death Mountain",
    text="{T}: Add {R}. {T}: Add {R}{R}. Spend this mana only to cast Goron spells.",
    supertypes={"Legendary"}
)


ZORAS_DOMAIN_LAND = make_land(
    name="Zora's Domain",
    text="{T}: Add {U}. {2}, {T}: Target creature can't be blocked this turn.",
    supertypes={"Legendary"}
)


LOST_WOODS = make_land(
    name="Lost Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast Kokiri or Plant spells.",
    supertypes={"Legendary"}
)


GERUDO_DESERT = make_land(
    name="Gerudo Desert",
    text="{T}: Add {R} or {B}.",
    supertypes={"Legendary"}
)


TEMPLE_OF_TIME = make_land(
    name="Temple of Time",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast legendary spells.",
    supertypes={"Legendary"}
)


KAKARIKO_VILLAGE = make_land(
    name="Kakariko Village",
    text="{T}: Add {W}. When Kakariko Village enters, you gain 1 life."
)


LAKE_HYLIA = make_land(
    name="Lake Hylia",
    text="{T}: Add {U}. {2}, {T}: Draw a card, then discard a card."
)


LON_LON_RANCH = make_land(
    name="Lon Lon Ranch",
    text="{T}: Add {G} or {W}."
)


GREAT_PLATEAU = make_land(
    name="Great Plateau",
    text="{T}: Add {C}. {3}, {T}: Add one mana of any color."
)


AKKALA_CITADEL = make_land(
    name="Akkala Citadel",
    text="{T}: Add {R} or {W}."
)


FARON_WOODS = make_land(
    name="Faron Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast creature spells."
)


ELDIN_VOLCANO = make_land(
    name="Eldin Volcano",
    text="{T}: Add {R}. Eldin Volcano enters tapped unless you control a Goron."
)


LANAYRU_WETLANDS = make_land(
    name="Lanayru Wetlands",
    text="{T}: Add {U}. Lanayru Wetlands enters tapped unless you control a Zora."
)


LURELIN_VILLAGE = make_land(
    name="Lurelin Village",
    text="{T}: Add {U} or {G}."
)


SKYLOFT = make_land(
    name="Skyloft",
    text="{T}: Add {W} or {U}. {T}: Add {C}. Spend this mana only to activate abilities.",
    supertypes={"Legendary"}
)


SHADOW_TEMPLE = make_land(
    name="Shadow Temple",
    text="{T}: Add {B}. {1}{B}, {T}: Target creature gets -1/-1 until end of turn."
)


FIRE_TEMPLE = make_land(
    name="Fire Temple",
    text="{T}: Add {R}. {1}{R}, {T}: Fire Temple deals 1 damage to any target."
)


WATER_TEMPLE = make_land(
    name="Water Temple",
    text="{T}: Add {U}. {1}{U}, {T}: Tap target creature."
)


FOREST_TEMPLE = make_land(
    name="Forest Temple",
    text="{T}: Add {G}. {1}{G}, {T}: Target creature gets +1/+1 until end of turn."
)


SPIRIT_TEMPLE = make_land(
    name="Spirit Temple",
    text="{T}: Add {W} or {R}. {2}, {T}: Exile target card from a graveyard."
)


# --- Basic Lands ---

PLAINS_LOZ = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"}
)


ISLAND_LOZ = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"}
)


SWAMP_LOZ = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"}
)


MOUNTAIN_LOZ = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"}
)


FOREST_LOZ = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"}
)


# =============================================================================
# ADDITIONAL CREATURES TO REACH ~250
# =============================================================================

# More White
FAIRY_COMPANION = make_creature(
    name="Fairy Companion",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
    text="Flying. Sacrifice Fairy Companion: Prevent the next 3 damage that would be dealt to target creature this turn."
)

HYRULE_SOLDIER = make_creature(
    name="Hyrule Soldier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
    text="First strike."
)

LIGHT_SAGE = make_creature(
    name="Light Sage",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    text="When Light Sage enters, you gain 3 life."
)

SACRED_KNIGHT = make_creature(
    name="Sacred Knight",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
    text="Vigilance, lifelink."
)

# More Blue
ZORA_GUARD = make_creature(
    name="Zora Guard",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Soldier"},
    text="Flash. When Zora Guard enters, tap target creature an opponent controls."
)

DEEP_SEA_ZORA = make_creature(
    name="Deep Sea Zora",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora"},
    text="Islandwalk. Whenever Deep Sea Zora deals combat damage to a player, draw two cards."
)

WISDOM_FAIRY = make_creature(
    name="Wisdom Fairy",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fairy"},
    text="Flying. When Wisdom Fairy enters, scry 2."
)

RIVER_GUARDIAN = make_creature(
    name="River Guardian",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Hexproof. River Guardian can block any number of creatures."
)

# More Black
SHADOW_LINK = make_creature(
    name="Shadow Link",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Hylian", "Shadow"},
    text="Deathtouch. Shadow Link can't be blocked except by legendary creatures."
)

DARK_INTERLOPERS = make_creature(
    name="Dark Interlopers",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When Dark Interlopers enters, each opponent sacrifices a creature."
)

TWILIGHT_MESSENGER = make_creature(
    name="Twilight Messenger",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying. When Twilight Messenger dies, target opponent discards a card."
)

CURSED_BOKOBLIN = make_creature(
    name="Cursed Bokoblin",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Skeleton"},
    text="When Cursed Bokoblin dies, return it to the battlefield tapped at the beginning of the next end step."
)

# More Red
FIRE_TEMPLE_GORON = make_creature(
    name="Fire Temple Goron",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    text="Trample. Fire Temple Goron can't be dealt damage by red sources."
)

BOKOBLIN_HORDE = make_creature(
    name="Bokoblin Horde",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="When Bokoblin Horde attacks, create two 1/1 red Goblin creature tokens that are tapped and attacking."
)

VOLCANIC_KEESE = make_creature(
    name="Volcanic Keese",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bat"},
    text="Flying, haste. When Volcanic Keese dies, it deals 2 damage to any target."
)

TALUS = make_creature(
    name="Stone Talus",
    power=6, toughness=6,
    mana_cost="{5}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Giant"},
    text="Trample. When Stone Talus dies, create two Treasure tokens."
)

# More Green
FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
    text="Vigilance, reach. Other green creatures you control get +1/+1."
)

DEKU_TREE_SPROUT = make_creature(
    name="Deku Tree Sprout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"},
    text="When Deku Tree Sprout enters, create a 1/1 green Plant creature token."
)

WILD_HORSE = make_creature(
    name="Wild Horse",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    text="Haste. When Wild Horse enters, target creature you control gets +1/+1 until end of turn."
)

RITO_ELDER = make_creature(
    name="Rito Elder",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Druid"},
    text="Flying. Other Rito creatures you control get +1/+1."
)

MASTER_KOHGA = make_creature(
    name="Master Kohga",
    power=2, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="When Master Kohga enters, create two 1/1 red and black Yiga Clan creature tokens with menace."
)

GHIRAHIM_DEMON_LORD = make_creature(
    name="Ghirahim, Demon Lord",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="First strike, menace. Whenever Ghirahim deals combat damage to a player, that player discards a card."
)

DEMISE_DEMON_KING = make_creature(
    name="Demise, Demon King",
    power=7, toughness=6,
    mana_cost="{4}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "God"},
    supertypes={"Legendary"},
    text="Trample, menace. When Demise enters, destroy all other creatures."
)

KING_RHOAM = make_creature(
    name="King Rhoam Bosphoramus",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Noble", "Spirit"},
    supertypes={"Legendary"},
    text="Other Hylian creatures you control get +1/+1. When King Rhoam enters, search your library for a Champion creature card, reveal it, and put it into your hand."
)

KASS_RITO_BARD = make_creature(
    name="Kass, Rito Bard",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Rito", "Bard"},
    supertypes={"Legendary"},
    text="Flying. At the beginning of your end step, if you cast two or more spells this turn, draw a card."
)

BEEDLE_TRAVELING_MERCHANT = make_creature(
    name="Beedle, Traveling Merchant",
    power=1, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Human", "Merchant"},
    supertypes={"Legendary"},
    text="When Beedle enters, create a Treasure token. {T}: You may pay {2}. If you do, create a Treasure token."
)

PURAH_SHEIKAH_RESEARCHER = make_creature(
    name="Purah, Sheikah Researcher",
    power=1, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Sheikah", "Artificer"},
    supertypes={"Legendary"},
    text="Artifact spells you cast cost {1} less. When Purah enters, create a colorless Equipment artifact token named Ancient Gear with 'Equipped creature gets +2/+0. Equip {2}.'"
)

ROBBIE_ANCIENT_TECH = make_creature(
    name="Robbie, Ancient Tech Expert",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Sheikah", "Artificer"},
    supertypes={"Legendary"},
    text="When Robbie enters, look at the top five cards of your library. You may reveal an artifact card from among them and put it into your hand. Put the rest on the bottom in any order."
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

LEGEND_OF_ZELDA_CARDS = {
    # WHITE LEGENDARIES
    "Zelda, Princess of Hyrule": ZELDA_PRINCESS_OF_HYRULE,
    "Zelda, Wielder of Wisdom": ZELDA_WIELDER_OF_WISDOM,
    "Impa, Sheikah Guardian": IMPA_SHEIKAH_GUARDIAN,
    "Rauru, Sage of Light": RAURU_SAGE_OF_LIGHT,
    "Hylia, Goddess of Light": HYLIA_GODDESS_OF_LIGHT,

    # WHITE CREATURES
    "Sheikah Warrior": SHEIKAH_WARRIOR,
    "Hyrule Knight": HYRULE_KNIGHT,
    "Temple Guardian": TEMPLE_GUARDIAN,
    "Castle Guard": CASTLE_GUARD,
    "Light Spirit": LIGHT_SPIRIT,
    "Hylian Priestess": HYLIAN_PRIESTESS,
    "Sheikah Scout": SHEIKAH_SCOUT,
    "Courage Fairy": COURAGE_FAIRY,
    "Hyrule Captain": HYRULE_CAPTAIN,
    "Great Fairy": GREAT_FAIRY,
    "Sacred Realm Guardian": SACRED_REALM_GUARDIAN,
    "Fairy Companion": FAIRY_COMPANION,
    "Hyrule Soldier": HYRULE_SOLDIER,
    "Light Sage": LIGHT_SAGE,
    "Sacred Knight": SACRED_KNIGHT,
    "King Rhoam Bosphoramus": KING_RHOAM,

    # WHITE SPELLS
    "Din's Fire Shield": DINS_FIRE_SHIELD,
    "Light Arrow": LIGHT_ARROW,
    "Nayru's Love": NAYRUS_LOVE,
    "Song of Healing": SONG_OF_HEALING,
    "Blessing of Hylia": BLESSING_OF_HYLIA,

    # BLUE LEGENDARIES
    "Mipha, Zora Champion": MIPHA_ZORA_CHAMPION,
    "Ruto, Zora Princess": RUTO_ZORA_PRINCESS,
    "King Zora, Domain Ruler": KING_ZORA,
    "Nayru, Oracle of Wisdom": NAYRU_ORACLE_OF_WISDOM,
    "Sidon, Zora Prince": SIDON_ZORA_PRINCE,

    # BLUE CREATURES
    "Zora Warrior": ZORA_WARRIOR,
    "Zora Scholar": ZORA_SCHOLAR,
    "River Zora": RIVER_ZORA,
    "Water Spirit": WATER_SPIRIT,
    "Octorok": OCTOROK,
    "Like-Like": LIKE_LIKE,
    "Gyorg": GYORG,
    "Zora Diver": ZORA_DIVER,
    "Zora Spearman": ZORA_SPEARMAN,
    "Zora Sage": ZORA_SAGE,
    "Zora Guard": ZORA_GUARD,
    "Deep Sea Zora": DEEP_SEA_ZORA,
    "Wisdom Fairy": WISDOM_FAIRY,
    "River Guardian": RIVER_GUARDIAN,
    "Robbie, Ancient Tech Expert": ROBBIE_ANCIENT_TECH,

    # BLUE SPELLS
    "Zora's Sapphire Blessing": ZORAS_SAPPHIRE_BLESSING,
    "Torrential Wave": TORRENTIAL_WAVE,
    "Water Temple Flood": WATER_TEMPLE_FLOOD,
    "Wisdom of Ages": WISDOM_OF_AGES,
    "Counter Magic": COUNTER_MAGIC,

    # BLACK LEGENDARIES
    "Ganondorf, King of Evil": GANONDORF_KING_OF_EVIL,
    "Ganon, Calamity Incarnate": GANON_CALAMITY_INCARNATE,
    "Zant, Twilight Usurper": ZANT_TWILIGHT_USURPER,
    "Midna, Twilight Princess": MIDNA_TWILIGHT_PRINCESS,
    "Vaati, Wind Mage": VAATI_WIND_MAGE,

    # BLACK CREATURES
    "Shadow Beast": SHADOW_BEAST,
    "Stalfos Warrior": STALFOS_WARRIOR,
    "ReDead": REDEAD,
    "Gibdo": GIBDO,
    "Poe": POES,
    "Darknut": DARK_NUT,
    "Phantom": PHANTOM,
    "Floormaster": FLOORMASTER,
    "Dead Hand": DEAD_HAND,
    "Wallmaster": WALLMASTER,
    "Shadow Link": SHADOW_LINK,
    "Dark Interlopers": DARK_INTERLOPERS,
    "Twilight Messenger": TWILIGHT_MESSENGER,
    "Cursed Bokoblin": CURSED_BOKOBLIN,

    # BLACK SPELLS
    "Twilight Curse": TWILIGHT_CURSE,
    "Darkness Falls": DARKNESS_FALLS,
    "Malice Spread": MALICE_SPREAD,
    "Soul Harvest": SOUL_HARVEST,
    "Ganon's Wrath": GANONS_WRATH,

    # RED LEGENDARIES
    "Daruk, Goron Champion": DARUK_GORON_CHAMPION,
    "Darunia, Goron Chief": DARUNIA_GORON_CHIEF,
    "Din, Oracle of Power": DIN_ORACLE_OF_POWER,
    "Volvagia, Fire Dragon": VOLVAGIA_FIRE_DRAGON,
    "Yunobo, Goron Descendant": YUNOBO_GORON_DESCENDANT,

    # RED CREATURES
    "Goron Warrior": GORON_WARRIOR,
    "Goron Smith": GORON_SMITH,
    "Dodongo": DODONGO,
    "Fire Keese": FIRE_KEESE,
    "Lizalfos": LIZALFOS,
    "Lynel": LYNEL,
    "Moblin": MOBLIN,
    "Hinox": HINOX,
    "Goron Elder": GORON_ELDER,
    "Fire Spirit": FIRE_SPIRIT,
    "Fire Temple Goron": FIRE_TEMPLE_GORON,
    "Bokoblin Horde": BOKOBLIN_HORDE,
    "Volcanic Keese": VOLCANIC_KEESE,
    "Stone Talus": TALUS,

    # RED SPELLS
    "Din's Fire": DINS_FIRE,
    "Fire Arrow": FIRE_ARROW,
    "Volcanic Eruption": VOLCANIC_ERUPTION,
    "Goron Rage": GORON_RAGE,
    "Bomb Barrage": BOMB_BARRAGE,

    # GREEN LEGENDARIES
    "Link, Hero of Time": LINK_HERO_OF_TIME,
    "Link, Champion of Hyrule": LINK_CHAMPION_OF_HYRULE,
    "Saria, Forest Sage": SARIA_FOREST_SAGE,
    "Revali, Rito Champion": REVALI_RITO_CHAMPION,
    "Great Deku Tree": GREAT_DEKU_TREE,
    "Farore, Oracle of Courage": FARORE_ORACLE_OF_COURAGE,

    # GREEN CREATURES
    "Kokiri Child": KOKIRI_CHILD,
    "Kokiri Warrior": KOKIRI_WARRIOR,
    "Skull Kid": SKULL_KID,
    "Deku Scrub": DEKU_SCRUB,
    "Forest Fairy": FOREST_FAIRY,
    "Wolfos": WOLFOS,
    "Forest Temple Guardian": FOREST_TEMPLE_GUARDIAN,
    "Deku Baba": DEKU_BABA,
    "Rito Warrior": RITO_WARRIOR,
    "Korok": KOROKS,
    "Forest Guardian": FOREST_GUARDIAN,
    "Deku Tree Sprout": DEKU_TREE_SPROUT,
    "Wild Horse": WILD_HORSE,
    "Rito Elder": RITO_ELDER,

    # GREEN SPELLS
    "Farore's Wind": FARORES_WIND,
    "Forest Blessing": FOREST_BLESSING,
    "Nature's Fury": NATURES_FURY,
    "Deku Nut Stun": DEKU_NUT_STUN,
    "Wild Growth": WILD_GROWTH,

    # MULTICOLOR LEGENDARIES
    "Urbosa, Gerudo Champion": URBOSA_GERUDO_CHAMPION,
    "Fi, Sword Spirit": FI_SWORD_SPIRIT,
    "Nabooru, Spirit Sage": NABOORU_SPIRIT_SAGE,
    "Skull Kid, Masked Menace": SKULL_KID_MASKED_MENACE,
    "Tetra, Pirate Princess": TETRA_PIRATE_PRINCESS,
    "Groose, Skyloft Hero": GROOSE_SKYLOFT_HERO,
    "Malon, Ranch Keeper": MALON_RANCH_KEEPER,
    "Master Kohga": MASTER_KOHGA,
    "Ghirahim, Demon Lord": GHIRAHIM_DEMON_LORD,
    "Demise, Demon King": DEMISE_DEMON_KING,
    "Kass, Rito Bard": KASS_RITO_BARD,
    "Purah, Sheikah Researcher": PURAH_SHEIKAH_RESEARCHER,

    # TRIFORCE ARTIFACTS
    "Triforce of Power": TRIFORCE_OF_POWER,
    "Triforce of Wisdom": TRIFORCE_OF_WISDOM,
    "Triforce of Courage": TRIFORCE_OF_COURAGE,

    # DIVINE BEASTS
    "Divine Beast Vah Ruta": DIVINE_BEAST_VAH_RUTA,
    "Divine Beast Vah Rudania": DIVINE_BEAST_VAH_RUDANIA,
    "Divine Beast Vah Medoh": DIVINE_BEAST_VAH_MEDOH,
    "Divine Beast Vah Naboris": DIVINE_BEAST_VAH_NABORIS,

    # EQUIPMENT
    "Master Sword": MASTER_SWORD,
    "Hylian Shield": HYLIAN_SHIELD,
    "Hero's Bow": HEROS_BOW,
    "Biggoron's Sword": BIGGORONS_SWORD,
    "Mirror Shield": MIRROR_SHIELD,
    "Ancient Bow": ANCIENT_BOW,
    "Kokiri Sword": KOKIRI_SWORD,

    # MASKS
    "Majora's Mask": MAJORAS_MASK,
    "Fierce Deity Mask": FIERCE_DEITY_MASK,
    "Deku Mask": DEKU_MASK,
    "Goron Mask": GORON_MASK,
    "Zora Mask": ZORA_MASK,
    "Bunny Hood": BUNNY_HOOD,
    "Stone Mask": STONE_MASK,

    # OTHER ARTIFACTS
    "Ocarina of Time": OCARINA_OF_TIME,
    "Sheikah Slate": SHEIKAH_SLATE,
    "Bomb Bag": BOMB_BAG,
    "Fairy Bottle": FAIRY_BOTTLE,
    "Magic Boomerang": MAGIC_BOOMERANG,
    "Hookshot": HOOKSHOT,
    "Heart Container": HEART_CONTAINER_ARTIFACT,
    "Lens of Truth": LENS_OF_TRUTH,
    "Ancient Core": ANCIENT_CORE,
    "Guardian Parts": GUARDIAN_PARTS,
    "Beedle, Traveling Merchant": BEEDLE_TRAVELING_MERCHANT,

    # ENCHANTMENTS
    "Sacred Protection": SACRED_PROTECTION,
    "Zora's Domain (Enchantment)": ZORAS_DOMAIN,
    "Twilight Realm": TWILIGHT_REALM,
    "Goron Strength": GORON_STRENGTH,
    "Kokiri Forest (Enchantment)": KOKIRI_FOREST,
    "Hylia's Blessing": HYLIA_BLESSING,
    "Ancient Technology": ANCIENT_TECHNOLOGY,
    "Spirit Tracks": SPIRIT_TRACKS,

    # LANDS
    "Hyrule Castle": HYRULE_CASTLE,
    "Death Mountain": DEATH_MOUNTAIN,
    "Zora's Domain (Land)": ZORAS_DOMAIN_LAND,
    "Lost Woods": LOST_WOODS,
    "Gerudo Desert": GERUDO_DESERT,
    "Temple of Time": TEMPLE_OF_TIME,
    "Kakariko Village": KAKARIKO_VILLAGE,
    "Lake Hylia": LAKE_HYLIA,
    "Lon Lon Ranch": LON_LON_RANCH,
    "Great Plateau": GREAT_PLATEAU,
    "Akkala Citadel": AKKALA_CITADEL,
    "Faron Woods": FARON_WOODS,
    "Eldin Volcano": ELDIN_VOLCANO,
    "Lanayru Wetlands": LANAYRU_WETLANDS,
    "Lurelin Village": LURELIN_VILLAGE,
    "Skyloft": SKYLOFT,
    "Shadow Temple": SHADOW_TEMPLE,
    "Fire Temple": FIRE_TEMPLE,
    "Water Temple": WATER_TEMPLE,
    "Forest Temple": FOREST_TEMPLE,
    "Spirit Temple": SPIRIT_TEMPLE,

    # BASIC LANDS
    "Plains": PLAINS_LOZ,
    "Island": ISLAND_LOZ,
    "Swamp": SWAMP_LOZ,
    "Mountain": MOUNTAIN_LOZ,
    "Forest": FOREST_LOZ,
}

print(f"Loaded {len(LEGEND_OF_ZELDA_CARDS)} Legend of Zelda: Hyrule Chronicles cards")
