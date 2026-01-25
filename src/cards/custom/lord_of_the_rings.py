"""
Lord of the Rings: War of the Ring (LOTR) Card Implementations

Set featuring Middle-earth. ~250 cards.
Features mechanics: Fellowship, Ring-bearer, Corruption
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


# =============================================================================
# LORD OF THE RINGS KEYWORD MECHANICS
# =============================================================================

def count_legendary_creatures(controller: str, state: GameState) -> int:
    """Count legendary creatures a player controls."""
    count = 0
    for obj in state.objects.values():
        if (obj.controller == controller and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            "Legendary" in obj.characteristics.supertypes):
            count += 1
    return count


def make_fellowship_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int, threshold: int = 3) -> list[Interceptor]:
    """
    Fellowship - This creature gets +X/+Y as long as you control 3+ legendary creatures.
    """
    def fellowship_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return count_legendary_creatures(source_obj.controller, state) >= threshold

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, fellowship_filter)


def make_fellowship_keyword(source_obj: GameObject, keywords: list[str], threshold: int = 3) -> Interceptor:
    """
    Fellowship - This creature gains keywords as long as you control 3+ legendary creatures.
    """
    def fellowship_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return count_legendary_creatures(source_obj.controller, state) >= threshold

    return make_keyword_grant(source_obj, keywords, fellowship_filter)


def make_ring_bearer_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """
    Ring-bearer - Equipped creature gets bonuses when equipped with The One Ring.
    Checks for 'Ring' subtype equipment attached.
    """
    def ring_bearer_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        # Check if equipped with a Ring
        for obj in state.objects.values():
            if (obj.zone == ZoneType.BATTLEFIELD and
                'Ring' in obj.characteristics.subtypes and
                'Equipment' in obj.characteristics.subtypes and
                obj.state.attached_to == source_obj.id):
                return True
        return False

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, ring_bearer_filter)


def make_corruption_upkeep(source_obj: GameObject) -> Interceptor:
    """
    Corruption - At the beginning of your upkeep, put a corruption counter on this creature.
    If it has 3+ corruption counters, sacrifice it.
    """
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': source_obj.id, 'counter_type': 'corruption', 'amount': 1},
            source=source_obj.id
        )]
        # Check current corruption count
        current = source_obj.state.counters.get('corruption', 0)
        if current >= 2:  # Will be 3 after adding
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={'object_id': source_obj.id},
                source=source_obj.id
            ))
        return events

    return make_upkeep_trigger(source_obj, upkeep_effect)


def make_corruption_death_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Trigger when a creature with corruption counters dies.
    """
    def corruption_death_filter(event: Event, state: GameState, obj: GameObject) -> bool:
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
        return dying.state.counters.get('corruption', 0) > 0

    return make_death_trigger(source_obj, effect_fn, filter_fn=corruption_death_filter)


# Subtype filters
def hobbit_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Hobbit creatures you control."""
    return creatures_with_subtype(source, "Hobbit")


def elf_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Elf creatures you control."""
    return creatures_with_subtype(source, "Elf")


def dwarf_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Dwarf creatures you control."""
    return creatures_with_subtype(source, "Dwarf")


def orc_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Orc creatures you control."""
    return creatures_with_subtype(source, "Orc")


def human_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Human creatures you control."""
    return creatures_with_subtype(source, "Human")


def wizard_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Wizard creatures you control."""
    return creatures_with_subtype(source, "Wizard")


# =============================================================================
# WHITE CARDS - GONDOR, ROHAN, MEN OF THE WEST
# =============================================================================

# --- Legendary Creatures ---

def aragorn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fellowship bonus + when attacks, other Humans get +1/+1"""
    interceptors = []
    interceptors.extend(make_fellowship_bonus(obj, 2, 2))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'boost': 'humans_plus_one', 'controller': obj.controller, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

ARAGORN_KING_OF_GONDOR = make_creature(
    name="Aragorn, King of Gondor",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Ranger"},
    supertypes={"Legendary"},
    text="Vigilance, lifelink. Fellowship - Aragorn gets +2/+2 as long as you control three or more legendary creatures. Whenever Aragorn attacks, other Human creatures you control get +1/+1 until end of turn.",
    setup_interceptors=aragorn_setup
)


def boromir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - creatures you control gain indestructible"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_ABILITY,
            payload={'target': 'creatures_you_control', 'ability': 'indestructible', 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

BOROMIR_CAPTAIN_OF_GONDOR = make_creature(
    name="Boromir, Captain of Gondor",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance. When Boromir dies, creatures you control gain indestructible until end of turn.",
    setup_interceptors=boromir_setup
)


def faramir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a Human enters, scry 1"""
    def human_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                'Human' in entering.characteristics.subtypes)

    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_etb_trigger(obj, scry_effect, filter_fn=human_etb_filter)]

FARAMIR_RANGER_OF_ITHILIEN = make_creature(
    name="Faramir, Ranger of Ithilien",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Ranger"},
    supertypes={"Legendary"},
    text="First strike. Whenever a Human enters the battlefield under your control, scry 1.",
    setup_interceptors=faramir_setup
)


def theoden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Humans get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Human"))

THEODEN_KING_OF_ROHAN = make_creature(
    name="Theoden, King of Rohan",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Knight"},
    supertypes={"Legendary"},
    text="Other Human creatures you control get +1/+1. {2}{W}: Create a 2/2 white Human Knight creature token with first strike.",
    setup_interceptors=theoden_setup
)


def eowyn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike, can block creatures with greater power"""
    return []

EOWYN_SHIELDMAIDEN = make_creature(
    name="Eowyn, Shieldmaiden of Rohan",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="First strike. Eowyn can block an additional creature each combat. Whenever Eowyn blocks a legendary creature, she gets +3/+3 until end of turn.",
    setup_interceptors=eowyn_setup
)


def eomer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste, when attacks alone gets +2/+0"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'boost': '+2/+0', 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

EOMER_MARSHAL_OF_ROHAN = make_creature(
    name="Eomer, Marshal of Rohan",
    power=4, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Noble", "Knight"},
    supertypes={"Legendary"},
    text="Haste. Whenever Eomer attacks alone, he gets +2/+0 until end of turn.",
    setup_interceptors=eomer_setup
)


# --- Regular Creatures ---

def gondor_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 1 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

GONDOR_SOLDIER = make_creature(
    name="Soldier of Gondor",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Soldier of Gondor enters, you gain 1 life.",
    setup_interceptors=gondor_soldier_setup
)


TOWER_GUARD = make_creature(
    name="Tower Guard of Minas Tirith",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. Other Soldiers you control have vigilance."
)


RIDER_OF_ROHAN = make_creature(
    name="Rider of Rohan",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike. When Rider of Rohan enters, create a 1/1 white Human Soldier creature token."
)


def knights_of_dol_amroth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, other Knights get +1/+0"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'boost': 'knights_plus_one', 'controller': obj.controller, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

KNIGHTS_OF_DOL_AMROTH = make_creature(
    name="Knights of Dol Amroth",
    power=3, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike. Whenever Knights of Dol Amroth attacks, other Knight creatures you control get +1/+0 until end of turn.",
    setup_interceptors=knights_of_dol_amroth_setup
)


CITADEL_CASTELLAN = make_creature(
    name="Citadel Castellan",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender. {T}: Prevent the next 2 damage that would be dealt to target creature this turn."
)


ROHIRRIM_LANCER = make_creature(
    name="Rohirrim Lancer",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Haste. First strike as long as it's your turn."
)


BEACON_WARDEN = make_creature(
    name="Beacon Warden",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="{T}, Sacrifice Beacon Warden: Creatures you control gain vigilance until end of turn."
)


PELENNOR_DEFENDER = make_creature(
    name="Pelennor Defender",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever Pelennor Defender blocks, you gain 2 life."
)


OSGILIATH_VETERAN = make_creature(
    name="Osgiliath Veteran",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever another Human enters the battlefield under your control, Osgiliath Veteran gets +1/+1 until end of turn."
)


DUNEDAIN_HEALER = make_creature(
    name="Dunedain Healer",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="{T}: You gain 2 life. {2}{W}, {T}: Prevent all damage that would be dealt to target creature this turn."
)


MINAS_TIRITH_RECRUIT = make_creature(
    name="Minas Tirith Recruit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Minas Tirith Recruit dies, create a 1/1 white Human Soldier creature token."
)


HELM_S_DEEP_GUARD = make_creature(
    name="Helm's Deep Guard",
    power=0, toughness=5,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender. When Helm's Deep Guard enters, create a 1/1 white Human Soldier creature token."
)


# --- Instants ---

SHIELD_OF_THE_WEST = make_instant(
    name="Shield of the West",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. If it's a Human, you also gain 3 life."
)


CHARGE_OF_THE_ROHIRRIM = make_instant(
    name="Charge of the Rohirrim",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+1 and gain first strike until end of turn."
)


GONDORIAN_DISCIPLINE = make_instant(
    name="Gondorian Discipline",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. If you control a legendary Human, it also gains vigilance."
)


RALLY_THE_WEST = make_instant(
    name="Rally the West",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Create two 1/1 white Human Soldier creature tokens. You gain 1 life for each Human you control."
)


ELENDIL_S_COURAGE = make_instant(
    name="Elendil's Courage",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +1/+3 until end of turn. Fellowship - If you control three or more legendary creatures, that creature also gains lifelink."
)


VALIANT_STAND = make_instant(
    name="Valiant Stand",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control gain vigilance and lifelink until end of turn."
)


# --- Sorceries ---

MUSTERING_OF_GONDOR = make_sorcery(
    name="Mustering of Gondor",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 white Human Soldier creature tokens. You gain 1 life for each creature you control."
)


RIDE_TO_RUIN = make_sorcery(
    name="Ride to Ruin",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures with power 4 or greater. You gain 2 life for each creature destroyed this way."
)


RESTORATION_OF_THE_KING = make_sorcery(
    name="Restoration of the King",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Return target legendary creature card from your graveyard to the battlefield. You gain life equal to its toughness."
)


DAWN_OF_HOPE = make_sorcery(
    name="Dawn Over Minas Tirith",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. If you control a legendary Human, draw a card."
)


# --- Enchantments ---

def banner_of_gondor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Humans get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, creatures_with_subtype(obj, "Human"))

BANNER_OF_GONDOR = make_enchantment(
    name="Banner of Gondor",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Human creatures you control get +1/+1. At the beginning of your end step, if you control four or more Humans, create a 1/1 white Human Soldier creature token.",
    setup_interceptors=banner_of_gondor_setup
)


OATH_OF_EORL = make_enchantment(
    name="Oath of Eorl",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control attacks alone, it gets +2/+2 until end of turn."
)


THE_WHITE_TREE = make_enchantment(
    name="The White Tree",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="At the beginning of your upkeep, if you control a legendary Human, create a 1/1 white Human Soldier creature token."
)


# =============================================================================
# BLUE CARDS - ELVES, WISDOM, FORESIGHT
# =============================================================================

# --- Legendary Creatures ---

def galadriel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Elves have hexproof, scry on upkeep"""
    interceptors = []
    interceptors.append(make_keyword_grant(obj, ['hexproof'], other_creatures_with_subtype(obj, "Elf")))

    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    interceptors.append(make_upkeep_trigger(obj, upkeep_effect))
    return interceptors

GALADRIEL_LADY_OF_LIGHT = make_creature(
    name="Galadriel, Lady of Light",
    power=2, toughness=5,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="Other Elf creatures you control have hexproof. At the beginning of your upkeep, scry 2.",
    setup_interceptors=galadriel_setup
)


def elrond_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - draw cards equal to legendary creatures"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        count = count_legendary_creatures(obj.controller, state)
        if count > 0:
            return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': min(count, 3)}, source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]

ELROND_LORD_OF_RIVENDELL = make_creature(
    name="Elrond, Lord of Rivendell",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="When Elrond enters, draw cards equal to the number of legendary creatures you control, up to three. Elves you control have 'When this creature enters, scry 1.'",
    setup_interceptors=elrond_setup
)


def arwen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lifelink, can give creature hexproof"""
    return []

ARWEN_EVENSTAR = make_creature(
    name="Arwen, Evenstar",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="Lifelink. {U}: Target creature gains hexproof until end of turn. Activate only once each turn.",
    setup_interceptors=arwen_setup
)


def legolas_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach, fellowship gives flying"""
    interceptors = []
    interceptors.append(make_fellowship_keyword(obj, ['flying']))
    return interceptors

LEGOLAS_PRINCE_OF_MIRKWOOD = make_creature(
    name="Legolas, Prince of Mirkwood",
    power=3, toughness=3,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Elf", "Archer", "Noble"},
    supertypes={"Legendary"},
    text="Reach. Fellowship - Legolas has flying as long as you control three or more legendary creatures. Whenever Legolas deals combat damage to a player, draw a card.",
    setup_interceptors=legolas_setup
)


def celeborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Elves get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Elf"))

CELEBORN_LORD_OF_LORIEN = make_creature(
    name="Celeborn, Lord of Lorien",
    power=2, toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="Other Elf creatures you control get +1/+1. {T}: Add one mana of any color. Spend this mana only to cast Elf spells.",
    setup_interceptors=celeborn_setup
)


# --- Regular Creatures ---

def lorien_sentinel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 1"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

LORIEN_SENTINEL = make_creature(
    name="Lorien Sentinel",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Scout"},
    text="When Lorien Sentinel enters, scry 1.",
    setup_interceptors=lorien_sentinel_setup
)


RIVENDELL_SCHOLAR = make_creature(
    name="Rivendell Scholar",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"},
    text="{T}: Draw a card, then discard a card."
)


MIRKWOOD_ARCHER = make_creature(
    name="Mirkwood Archer",
    power=2, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Archer"},
    text="Reach. {U}: Mirkwood Archer gains hexproof until end of turn."
)


GREY_HAVENS_NAVIGATOR = make_creature(
    name="Grey Havens Navigator",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Sailor"},
    text="When Grey Havens Navigator enters, scry 2. {2}{U}: Return Grey Havens Navigator to its owner's hand."
)


ELVISH_SEER = make_creature(
    name="Elvish Seer",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"},
    text="{T}: Look at the top card of your library. You may put it on the bottom."
)


SILVAN_TRACKER = make_creature(
    name="Silvan Tracker",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Scout"},
    text="Whenever Silvan Tracker deals combat damage to a player, scry 1, then draw a card."
)


NOLDOR_LOREMASTER = make_creature(
    name="Noldor Loremaster",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"},
    text="When Noldor Loremaster enters, draw two cards. Instant and sorcery spells you cast cost {1} less."
)


IMLADRIS_GUARDIAN = make_creature(
    name="Imladris Guardian",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Soldier"},
    text="Flash. When Imladris Guardian enters, you may return target creature to its owner's hand."
)


MIRROR_OF_GALADRIEL = make_creature(
    name="Keeper of the Mirror",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"},
    text="{T}: Scry 2. {2}{U}{U}, {T}: Look at the top five cards of your library. Put one into your hand and the rest on the bottom."
)


CIRDAN_THE_SHIPWRIGHT = make_creature(
    name="Cirdan the Shipwright",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Artificer"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if you drew two or more cards this turn, create a 1/1 blue Elf creature token."
)


# --- Instants ---

FORESIGHT_OF_ELVES = make_instant(
    name="Foresight of the Elves",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Scry 3, then draw a card."
)


ELVEN_WISDOM = make_instant(
    name="Elven Wisdom",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. If you control an Elf, scry 1."
)


MISTS_OF_LORIEN = make_instant(
    name="Mists of Lorien",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature phases out. If it's an opponent's creature, it doesn't phase in during its controller's next untap step."
)


VISIONS_OF_THE_PALANTIR = make_instant(
    name="Visions of the Palantir",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 2. If you control a legendary creature, draw a card."
)


COUNTERSPELL_OF_THE_WISE = make_instant(
    name="Elrond's Rejection",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. If you control an Elf, scry 1."
)


SILVER_FLOW = make_instant(
    name="Silver Flow",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Return up to two target creatures to their owners' hands. Draw a card."
)


# --- Sorceries ---

COUNCIL_OF_ELROND = make_sorcery(
    name="Council of Elrond",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Draw three cards. If you control three or more legendary creatures, draw four cards instead."
)


WORDS_OF_THE_ELDAR = make_sorcery(
    name="Words of the Eldar",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Scry 4, then draw two cards."
)


SAILING_TO_VALINOR = make_sorcery(
    name="Sailing to Valinor",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Exile all creatures. Each player draws cards equal to the number of creatures they controlled that were exiled this way."
)


MEMORY_OF_AGES = make_sorcery(
    name="Memory of Ages",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target instant or sorcery card from your graveyard to your hand. If you control an Elf, scry 2."
)


# --- Enchantments ---

MIRROR_POOL = make_enchantment(
    name="Mirror of Galadriel",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1. {2}{U}, {T}: Look at target player's hand."
)


LIGHT_OF_EARENDIL = make_enchantment(
    name="Light of Earendil",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever you scry, if you put one or more cards on the bottom of your library, draw a card."
)


ELVEN_SANCTUARY = make_enchantment(
    name="Elven Sanctuary",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Elf creatures you control have hexproof. At the beginning of your end step, if you control three or more Elves, draw a card."
)


# =============================================================================
# BLACK CARDS - MORDOR, SAURON, CORRUPTION
# =============================================================================

# --- Legendary Creatures ---

def sauron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures get -1/-1, death trigger draws card"""
    interceptors = []

    def enemy_creatures_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors.extend(make_static_pt_boost(obj, -1, -1, enemy_creatures_filter))
    return interceptors

SAURON_THE_DARK_LORD = make_creature(
    name="Sauron, the Dark Lord",
    power=7, toughness=7,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Horror"},
    supertypes={"Legendary"},
    text="Menace, trample. Other creatures get -1/-1. Whenever a creature an opponent controls dies, you draw a card and lose 1 life.",
    setup_interceptors=sauron_setup
)


def witch_king_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, can't be blocked except by legendary creatures"""
    return []

WITCH_KING_OF_ANGMAR = make_creature(
    name="Witch-king of Angmar",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith", "Noble"},
    supertypes={"Legendary"},
    text="Flying. Witch-king of Angmar can't be blocked except by legendary creatures. When Witch-king deals combat damage to a player, that player discards a card.",
    setup_interceptors=witch_king_setup
)


def saruman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When casts instant/sorcery, create orc token"""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Orc', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Orc', 'Soldier'}}
        }, source=obj.id)]

    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

SARUMAN_THE_WHITE = make_creature(
    name="Saruman, Voice of Isengard",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, create a 1/1 black Orc Soldier creature token. {2}: Copy target instant or sorcery spell you control. You may choose new targets for the copy.",
    setup_interceptors=saruman_setup
)


def mouth_of_sauron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - opponent discards"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        events = []
        for opp in opponents:
            events.append(Event(type=EventType.DISCARD, payload={'player': opp, 'amount': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]

MOUTH_OF_SAURON = make_creature(
    name="Mouth of Sauron",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="Menace. When Mouth of Sauron enters, each opponent discards a card. Whenever an opponent discards a card, you gain 1 life.",
    setup_interceptors=mouth_of_sauron_setup
)


def grima_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap to make creature unable to block"""
    return []

GRIMA_WORMTONGUE = make_creature(
    name="Grima Wormtongue",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="{T}: Target creature can't block this turn. {1}{B}, {T}: Target creature gets -2/-2 until end of turn.",
    setup_interceptors=grima_setup
)


# --- Regular Creatures ---

def nazgul_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, when deals damage put corruption counter"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if target and CardType.CREATURE in target.characteristics.types:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': target_id, 'counter_type': 'corruption', 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect)]

NAZGUL = make_creature(
    name="Nazgul",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith"},
    text="Flying. Whenever Nazgul deals combat damage to a creature, put a corruption counter on that creature.",
    setup_interceptors=nazgul_setup
)


ORC_WARRIOR = make_creature(
    name="Orc Warrior",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Warrior"},
    text="Menace."
)


URUK_HAI_BERSERKER = make_creature(
    name="Uruk-hai Berserker",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Berserker"},
    text="When Uruk-hai Berserker dies, it deals 2 damage to target creature."
)


MORDOR_SIEGE_TOWER = make_creature(
    name="Mordor Siege Engine",
    power=4, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Construct"},
    text="Trample. Whenever Mordor Siege Engine attacks, defending player sacrifices a creature."
)


HARADRIM_ASSASSIN = make_creature(
    name="Haradrim Assassin",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Deathtouch. When Haradrim Assassin enters, target creature gets -1/-1 until end of turn."
)


def moria_orc_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, create orc token"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Orc', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Orc', 'Soldier'}}
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

MORIA_ORC = make_creature(
    name="Moria Orc",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Soldier"},
    text="When Moria Orc dies, create a 1/1 black Orc Soldier creature token.",
    setup_interceptors=moria_orc_setup
)


CORSAIR_OF_UMBAR = make_creature(
    name="Corsair of Umbar",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When Corsair of Umbar enters, target player loses 2 life and you gain 2 life."
)


EASTERLING_SOLDIER = make_creature(
    name="Easterling Soldier",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="When Easterling Soldier dies, each opponent loses 1 life."
)


ORC_CHIEFTAIN = make_creature(
    name="Orc Chieftain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Warrior"},
    text="Other Orc creatures you control get +1/+0."
)


MORGUL_KNIGHT = make_creature(
    name="Morgul Knight",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith", "Knight"},
    text="Whenever Morgul Knight attacks, defending player loses 1 life and you gain 1 life."
)


SHELOB_SPAWN = make_creature(
    name="Spawn of Shelob",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spider"},
    text="Reach, deathtouch."
)


# --- Instants ---

SHADOW_OF_MORDOR = make_instant(
    name="Shadow of Mordor",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. If a creature would die this turn, exile it instead."
)


CORRUPTION_SPREADS = make_instant(
    name="Corruption Spreads",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Put a corruption counter on target creature. That creature gets -1/-1 for each corruption counter on it until end of turn."
)


MORGUL_BLADE = make_instant(
    name="Morgul Blade",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. Put a corruption counter on it."
)


DARK_WHISPERS = make_instant(
    name="Dark Whispers",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target player discards two cards. You gain life equal to the total mana value of cards discarded this way."
)


TREACHERY_OF_ISENGARD = make_instant(
    name="Treachery of Isengard",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses life equal to that creature's power."
)


SAURON_S_COMMAND = make_instant(
    name="Sauron's Command",
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    text="Target creature gets -4/-4 until end of turn. If it would die this turn, you create a 1/1 black Orc Soldier creature token."
)


# --- Sorceries ---

MARCH_OF_THE_ORCS = make_sorcery(
    name="March of the Orcs",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Create four 1/1 black Orc Soldier creature tokens. Each opponent loses 1 life for each Orc you control."
)


HARVEST_OF_SOULS = make_sorcery(
    name="Harvest of Souls",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. You lose life equal to the number of creatures destroyed this way."
)


CORRUPTION_OF_POWER = make_sorcery(
    name="Corruption of Power",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Put two corruption counters on target creature. If it has three or more corruption counters, sacrifice it and draw two cards."
)


RITUAL_OF_MORGOTH = make_sorcery(
    name="Ritual of Morgoth",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. You lose 2 life."
)


# --- Enchantments ---

def eye_of_sauron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep, opponent reveals hand"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        return [Event(type=EventType.REVEAL_HAND, payload={'player': opp}, source=obj.id) for opp in opponents]
    return [make_upkeep_trigger(obj, upkeep_effect)]

EYE_OF_SAURON = make_enchantment(
    name="Eye of Sauron",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, target opponent reveals their hand. Whenever an opponent discards a card, they lose 1 life.",
    setup_interceptors=eye_of_sauron_setup
)


SHADOW_OF_THE_EAST = make_enchantment(
    name="Shadow of the East",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Creatures with corruption counters on them get -1/-1 for each corruption counter on them."
)


THE_RING_TEMPTS = make_enchantment(
    name="The Ring Tempts You",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, you may put a corruption counter on target creature you control. If you do, draw a card."
)


# =============================================================================
# RED CARDS - DWARVES, BATTLE, FIRE
# =============================================================================

# --- Legendary Creatures ---

def gimli_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +1/+0 for each Dwarf, fellowship gives double strike"""
    interceptors = []
    interceptors.append(make_fellowship_keyword(obj, ['double_strike']))
    return interceptors

GIMLI_SON_OF_GLOIN = make_creature(
    name="Gimli, Son of Gloin",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"},
    supertypes={"Legendary"},
    text="First strike. Gimli gets +1/+0 for each Dwarf you control. Fellowship - Gimli has double strike as long as you control three or more legendary creatures.",
    setup_interceptors=gimli_setup
)


def thorin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Dwarves get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Dwarf"))

THORIN_OAKENSHIELD = make_creature(
    name="Thorin Oakenshield",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="Haste. Other Dwarf creatures you control get +1/+1. When Thorin attacks, create a Treasure token.",
    setup_interceptors=thorin_setup
)


def dain_ironfoot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dwarves have haste"""
    return [make_keyword_grant(obj, ['haste'], creatures_with_subtype(obj, "Dwarf"))]

DAIN_IRONFOOT = make_creature(
    name="Dain Ironfoot",
    power=3, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="Dwarf creatures you control have haste. Whenever you attack with three or more Dwarves, they get +2/+0 until end of turn.",
    setup_interceptors=dain_ironfoot_setup
)


def balrog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, deal 2 damage to each creature"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for target in state.objects.values():
            if (target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                target.id != obj.id):
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': target.id, 'amount': 2, 'source': obj.id},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]

BALROG_OF_MORIA = make_creature(
    name="Balrog of Moria",
    power=8, toughness=8,
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying, trample. Whenever Balrog of Moria attacks, it deals 2 damage to each other creature.",
    setup_interceptors=balrog_setup
)


# --- Regular Creatures ---

IRON_HILLS_WARRIOR = make_creature(
    name="Iron Hills Warrior",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"},
    text="Haste. When Iron Hills Warrior enters, it deals 1 damage to target creature or player."
)


DWARF_BERSERKER = make_creature(
    name="Dwarf Berserker",
    power=3, toughness=1,
    mana_cost="{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Berserker"},
    text="Haste. Dwarf Berserker attacks each turn if able."
)


EREBOR_SMITH = make_creature(
    name="Erebor Smith",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Artificer"},
    text="When Erebor Smith enters, create a Treasure token. {T}, Sacrifice an artifact: Erebor Smith deals 2 damage to any target."
)


def dwarf_miner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, create treasure"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

DWARF_MINER = make_creature(
    name="Dwarf Miner",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Citizen"},
    text="Whenever Dwarf Miner attacks, create a Treasure token.",
    setup_interceptors=dwarf_miner_setup
)


MOUNTAIN_GUARD = make_creature(
    name="Mountain Guard",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Soldier"},
    text="First strike. Whenever Mountain Guard blocks, it gets +1/+1 until end of turn."
)


CAVE_TROLL = make_creature(
    name="Cave Troll",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Troll"},
    text="Trample. Cave Troll can't block."
)


WARG_RIDER = make_creature(
    name="Warg Rider",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Knight"},
    text="Haste. When Warg Rider attacks, target creature can't block this turn."
)


DRAGON_OF_THE_NORTH = make_creature(
    name="Dragon of the North",
    power=5, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying. When Dragon of the North enters, it deals 3 damage to any target."
)


KHAZAD_DUM_VETERAN = make_creature(
    name="Khazad-dum Veteran",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"},
    text="When Khazad-dum Veteran enters, Dwarves you control get +1/+0 and gain first strike until end of turn."
)


FIRE_DRAKE = make_creature(
    name="Fire Drake",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Drake"},
    text="Flying. {R}: Fire Drake gets +1/+0 until end of turn."
)


MORIA_GOBLIN = make_creature(
    name="Moria Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Haste. When Moria Goblin dies, it deals 1 damage to any target."
)


# --- Instants ---

FLAME_OF_ANOR = make_instant(
    name="Flame of Anor",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Flame of Anor deals 4 damage to target creature. If you control a Wizard, draw a card."
)


DWARVEN_RAGE = make_instant(
    name="Dwarven Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 until end of turn. If it's a Dwarf, it also gains first strike."
)


DRAGON_S_BREATH = make_instant(
    name="Dragon's Breath",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Dragon's Breath deals 3 damage to any target. If it's a creature, it can't block this turn."
)


FORGE_FIRE = make_instant(
    name="Forge Fire",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Forge Fire deals 2 damage to each creature. You gain 1 life for each Dwarf that survives."
)


BATTLE_CRY = make_instant(
    name="Battle Cry of Erebor",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn."
)


SMASH_THE_GATE = make_instant(
    name="Smash the Gate",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Destroy target artifact. Smash the Gate deals damage to that artifact's controller equal to its mana value."
)


# --- Sorceries ---

SIEGE_OF_EREBOR = make_sorcery(
    name="Siege of Erebor",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Siege of Erebor deals 5 damage to each creature and each player."
)


DRAGON_FIRE = make_sorcery(
    name="Dragon Fire",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Dragon Fire deals 4 damage to any target. If that target is destroyed, Dragon Fire deals 2 damage to each other creature that player controls."
)


CALL_OF_THE_MOUNTAIN = make_sorcery(
    name="Call of the Mountain",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Create two 2/2 red Dwarf Warrior creature tokens with haste."
)


MINES_OF_MORIA = make_sorcery(
    name="Delving the Mines",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Create three Treasure tokens. You may sacrifice a Treasure: Deal 2 damage to any target."
)


# --- Enchantments ---

def forge_of_erebor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dwarves get +1/+0"""
    return make_static_pt_boost(obj, 1, 0, creatures_with_subtype(obj, "Dwarf"))

FORGE_OF_EREBOR = make_enchantment(
    name="Forge of Erebor",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Dwarf creatures you control get +1/+0. {2}{R}, {T}: Create a 2/2 red Dwarf Warrior creature token.",
    setup_interceptors=forge_of_erebor_setup
)


FIRES_OF_MOUNT_DOOM = make_enchantment(
    name="Fires of Mount Doom",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, Fires of Mount Doom deals 1 damage to each creature and each player."
)


WRATH_OF_THE_DWARVES = make_enchantment(
    name="Wrath of the Dwarves",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a Dwarf you control dies, Wrath of the Dwarves deals 1 damage to any target."
)


# =============================================================================
# GREEN CARDS - HOBBITS, ENTS, NATURE
# =============================================================================

# --- Legendary Creatures ---

def frodo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be blocked, ring-bearer bonus"""
    interceptors = []
    interceptors.extend(make_ring_bearer_bonus(obj, 2, 2))
    return interceptors

FRODO_RING_BEARER = make_creature(
    name="Frodo, the Ring-bearer",
    power=1, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Scout"},
    supertypes={"Legendary"},
    text="Frodo can't be blocked by creatures with power 3 or greater. Ring-bearer - Frodo gets +2/+2 as long as he's equipped with an Equipment named The One Ring.",
    setup_interceptors=frodo_setup
)


def samwise_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Frodo attacks, Sam can tap to give +2/+2"""
    return []

SAMWISE_THE_BRAVE = make_creature(
    name="Samwise, the Brave",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"},
    supertypes={"Legendary"},
    text="Whenever a legendary Hobbit you control attacks, Samwise gets +1/+1 until end of turn. {T}: Target Hobbit you control gains hexproof until end of turn.",
    setup_interceptors=samwise_setup
)


def merry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hobbits get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, creatures_with_subtype(obj, "Hobbit"))

MERRY_BRANDYBUCK = make_creature(
    name="Merry, Esquire of Rohan",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hobbit", "Knight"},
    supertypes={"Legendary"},
    text="Other Hobbit creatures you control get +1/+1. Whenever Merry attacks, create a Food token.",
    setup_interceptors=merry_setup
)


def pippin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - draw a card"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

PIPPIN_GUARD_OF_THE_CITADEL = make_creature(
    name="Pippin, Guard of the Citadel",
    power=1, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hobbit", "Soldier"},
    supertypes={"Legendary"},
    text="When Pippin enters, draw a card. {T}: Target creature you control gains vigilance until end of turn.",
    setup_interceptors=pippin_setup
)


def treebeard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach, other Treefolk get +2/+2"""
    return make_static_pt_boost(obj, 2, 2, other_creatures_with_subtype(obj, "Treefolk"))

TREEBEARD_ELDEST_OF_ENTS = make_creature(
    name="Treebeard, Eldest of Ents",
    power=5, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    supertypes={"Legendary"},
    text="Reach, vigilance. Other Treefolk creatures you control get +2/+2. {G}{G}: Create a 2/4 green Treefolk creature token with reach.",
    setup_interceptors=treebeard_setup
)


def tom_bombadil_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be targeted by opponents, when enters gain life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 4}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

TOM_BOMBADIL = make_creature(
    name="Tom Bombadil",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Tom Bombadil can't be the target of spells or abilities your opponents control. When Tom Bombadil enters, you gain 4 life and create a Food token.",
    setup_interceptors=tom_bombadil_setup
)


# --- Regular Creatures ---

def shire_hobbit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create food"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Food', 'types': {CardType.ARTIFACT}, 'subtypes': {'Food'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SHIRE_HOBBIT = make_creature(
    name="Shire Hobbit",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"},
    text="When Shire Hobbit enters, create a Food token.",
    setup_interceptors=shire_hobbit_setup
)


ENT_SAPLING = make_creature(
    name="Ent Sapling",
    power=0, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Defender, reach. At the beginning of your upkeep, put a +1/+1 counter on Ent Sapling."
)


HOBBITON_GARDENER = make_creature(
    name="Hobbiton Gardener",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"},
    text="{T}: Add {G}. {T}, Sacrifice Hobbiton Gardener: You gain 3 life."
)


FANGORN_GUARDIAN = make_creature(
    name="Fangorn Guardian",
    power=4, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach, trample. When Fangorn Guardian enters, destroy target artifact or enchantment."
)


def great_eagle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, when enters return creature to hand"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.BOUNCE, payload={'target_type': 'creature'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

GREAT_EAGLE = make_creature(
    name="Great Eagle",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="Flying. When Great Eagle enters, you may return target creature to its owner's hand.",
    setup_interceptors=great_eagle_setup
)


GWAIHIR_WIND_LORD = make_creature(
    name="Gwaihir, Wind Lord",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    supertypes={"Legendary"},
    text="Flying. When Gwaihir enters, return target creature to its owner's hand. Whenever Gwaihir attacks, other Birds you control get +1/+1 until end of turn."
)


OLD_MAN_WILLOW = make_creature(
    name="Old Man Willow",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach. When Old Man Willow enters, tap target creature an opponent controls. It doesn't untap during its controller's next untap step."
)


QUICKBEAM = make_creature(
    name="Quickbeam, Bregalad",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    supertypes={"Legendary"},
    text="Haste. Whenever Quickbeam attacks, untap target Treefolk you control."
)


BUCKLAND_SHIRRIFF = make_creature(
    name="Buckland Shirriff",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Scout"},
    text="When Buckland Shirriff enters, look at the top three cards of your library. Put one into your hand and the rest on the bottom."
)


OLIPHAUNT = make_creature(
    name="Oliphaunt",
    power=6, toughness=6,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    text="Trample. When Oliphaunt enters, it fights target creature an opponent controls."
)


RADAGAST_S_COMPANION = make_creature(
    name="Radagast's Companion",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="Flying. Whenever Radagast's Companion deals combat damage to a player, look at the top card of your library. If it's a creature, you may reveal it and put it into your hand."
)


HUORN = make_creature(
    name="Huorn",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="When Huorn enters, target creature can't attack or block until your next turn."
)


# --- Instants ---

STRENGTH_OF_NATURE = make_instant(
    name="Strength of Nature",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If it's a Treefolk, it also gains trample."
)


HOBBIT_S_CUNNING = make_instant(
    name="Hobbit's Cunning",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control can't be blocked this turn. If it's a Hobbit, draw a card."
)


ENTISH_FURY = make_instant(
    name="Entish Fury",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 and gains trample until end of turn. It must be blocked this turn if able."
)


GIFT_OF_THE_SHIRE = make_instant(
    name="Gift of the Shire",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create two Food tokens. You gain 2 life."
)


EAGLES_ARE_COMING = make_instant(
    name="The Eagles Are Coming",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create three 2/2 green Bird creature tokens with flying."
)


NATURE_S_RECLAMATION = make_instant(
    name="Nature's Reclamation",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. You gain 3 life."
)


# --- Sorceries ---

LAST_MARCH_OF_THE_ENTS = make_sorcery(
    name="Last March of the Ents",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    text="Create three 4/4 green Treefolk creature tokens with reach. They gain haste until end of turn."
)


SHIRE_HARVEST = make_sorcery(
    name="Shire Harvest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Create a Food token."
)


PARTY_IN_THE_SHIRE = make_sorcery(
    name="Party in the Shire",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Create three 1/1 green Hobbit Citizen creature tokens. Create a Food token for each Hobbit you control."
)


ISENGARD_UNLEASHED = make_sorcery(
    name="Isengard Unleashed",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Destroy all artifacts and enchantments. For each permanent destroyed this way, create a 2/2 green Treefolk creature token."
)


# --- Enchantments ---

def party_tree_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hobbits get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, creatures_with_subtype(obj, "Hobbit"))

PARTY_TREE = make_enchantment(
    name="The Party Tree",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Hobbit creatures you control get +1/+1. At the beginning of your end step, create a Food token.",
    setup_interceptors=party_tree_setup
)


FANGORN_FOREST = make_enchantment(
    name="Heart of Fangorn",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Treefolk creatures you control have vigilance and trample. At the beginning of your upkeep, create a 2/4 green Treefolk creature token with reach."
)


SECOND_BREAKFAST = make_enchantment(
    name="Second Breakfast",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Whenever you sacrifice a Food, you gain 1 life and draw a card."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# --- Legendary Creatures ---

def gandalf_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash, when enters draw and deal damage"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            Event(type=EventType.DAMAGE, payload={'target': 'any', 'amount': 3, 'source': obj.id}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

GANDALF_THE_GREY = make_creature(
    name="Gandalf the Grey",
    power=3, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Avatar", "Wizard"},
    supertypes={"Legendary"},
    text="Flash. When Gandalf the Grey enters, draw two cards and Gandalf deals 3 damage to any target.",
    setup_interceptors=gandalf_setup
)


def gandalf_white_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures get +1/+1, spells cost less"""
    return make_static_pt_boost(obj, 1, 1, creatures_you_control(obj))

GANDALF_THE_WHITE = make_creature(
    name="Gandalf the White",
    power=4, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Avatar", "Wizard"},
    supertypes={"Legendary"},
    text="Vigilance. Creatures you control get +1/+1. Instant and sorcery spells you cast cost {1} less.",
    setup_interceptors=gandalf_white_setup
)


def shelob_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch, reach, when kills creature create food"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Food', 'types': {CardType.ARTIFACT}, 'subtypes': {'Food'}}
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect)]

SHELOB_CHILD_OF_UNGOLIANT = make_creature(
    name="Shelob, Child of Ungoliant",
    power=5, toughness=6,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spider"},
    supertypes={"Legendary"},
    text="Reach, deathtouch. Whenever Shelob deals damage to a creature, create a Food token. Whenever you sacrifice a Food, target creature gets -2/-2 until end of turn.",
    setup_interceptors=shelob_setup
)


def elrond_arwen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain life and draw"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

ELROND_AND_ARWEN = make_creature(
    name="Elrond and Arwen, United",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}{G}",
    colors={Color.WHITE, Color.BLUE, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="When Elrond and Arwen enters, you gain 3 life and draw a card. Other Elves you control have hexproof and lifelink.",
    setup_interceptors=elrond_arwen_setup
)


def aragorn_arwen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, create token"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Human Soldier', 'power': 2, 'toughness': 2, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Soldier'}}
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

ARAGORN_AND_ARWEN = make_creature(
    name="Aragorn and Arwen, Reunited",
    power=5, toughness=5,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Elf", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance, lifelink. Whenever Aragorn and Arwen attacks, create a 2/2 white Human Soldier creature token.",
    setup_interceptors=aragorn_arwen_setup
)


# =============================================================================
# ARTIFACTS
# =============================================================================

def one_ring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature has shroud, at upkeep lose 1 life per corruption"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        corruption = obj.state.counters.get('corruption', 0) + 1
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': 'corruption', 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -corruption}, source=obj.id)
        ]
    return [make_upkeep_trigger(obj, upkeep_effect)]

THE_ONE_RING = make_equipment(
    name="The One Ring",
    mana_cost="{4}",
    text="Equipped creature has shroud and can't be blocked. At the beginning of your upkeep, put a burden counter on The One Ring, then lose 1 life for each burden counter on it.",
    equip_cost="{2}",
    subtypes={"Ring"},
    supertypes={"Legendary"},
    setup_interceptors=one_ring_setup
)


STING = make_equipment(
    name="Sting, Blade of Bilbo",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1. Equipped creature has first strike as long as it's blocking or being blocked by an Orc or Goblin. Whenever equipped creature deals combat damage to a player, scry 1.",
    equip_cost="{1}",
    supertypes={"Legendary"},
)


GLAMDRING = make_equipment(
    name="Glamdring, Foe-hammer",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has first strike. Whenever equipped creature deals combat damage to a player, draw a card.",
    equip_cost="{2}",
    supertypes={"Legendary"},
)


ANDURIL = make_equipment(
    name="Anduril, Flame of the West",
    mana_cost="{3}",
    text="Equipped creature gets +3/+1. Whenever equipped creature attacks, create two 1/1 white Human Soldier creature tokens that are tapped and attacking.",
    equip_cost="{2}",
    supertypes={"Legendary"},
)


NENYA = make_equipment(
    name="Nenya, Ring of Adamant",
    mana_cost="{2}",
    text="Equipped creature gets +1/+2 and has hexproof. {T}: Add {G} or {U}.",
    equip_cost="{1}",
    subtypes={"Ring"},
    supertypes={"Legendary"},
)


VILYA = make_equipment(
    name="Vilya, Ring of Air",
    mana_cost="{2}",
    text="Equipped creature gets +1/+2 and has vigilance. At the beginning of your upkeep, scry 2.",
    equip_cost="{1}",
    subtypes={"Ring"},
    supertypes={"Legendary"},
)


NARYA = make_equipment(
    name="Narya, Ring of Fire",
    mana_cost="{2}",
    text="Equipped creature gets +2/+1 and has haste. {T}: Add {R}. Target creature you control gets +1/+0 until end of turn.",
    equip_cost="{1}",
    subtypes={"Ring"},
    supertypes={"Legendary"},
)


PHIAL_OF_GALADRIEL = make_artifact(
    name="Phial of Galadriel",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. {2}, {T}, Sacrifice Phial of Galadriel: Target creature gains protection from the color of your choice until end of turn.",
    supertypes={"Legendary"},
)


PALANTIR_OF_ORTHANC = make_artifact(
    name="Palantir of Orthanc",
    mana_cost="{3}",
    text="{2}, {T}: Scry 2. Any opponent may have you draw a card. If no opponent does, you lose 2 life.",
    supertypes={"Legendary"},
)


MITHRIL_COAT = make_equipment(
    name="Mithril Coat",
    mana_cost="{3}",
    text="Equipped creature gets +0/+3 and has indestructible.",
    equip_cost="{3}",
    supertypes={"Legendary"},
)


HORN_OF_GONDOR = make_artifact(
    name="Horn of Gondor",
    mana_cost="{3}",
    text="{2}, {T}: Create a 1/1 white Human Soldier creature token. {4}, {T}, Sacrifice Horn of Gondor: Creatures you control get +2/+0 until end of turn.",
    supertypes={"Legendary"},
)


RING_OF_BARAHIR = make_equipment(
    name="Ring of Barahir",
    mana_cost="{1}",
    text="Equipped creature gets +1/+1. Equipped creature has 'Whenever this creature attacks, you gain 1 life.'",
    equip_cost="{1}",
)


MORGUL_SWORD = make_equipment(
    name="Morgul Sword",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0. Whenever equipped creature deals combat damage to a creature, put a corruption counter on that creature.",
    equip_cost="{2}",
)


DWARVEN_AXE = make_equipment(
    name="Dwarven Axe",
    mana_cost="{2}",
    text="Equipped creature gets +2/+1. If equipped creature is a Dwarf, it also has first strike.",
    equip_cost="{1}",
)


ELVEN_BOW = make_equipment(
    name="Elven Bow",
    mana_cost="{1}",
    text="Equipped creature gets +1/+0 and has reach. If equipped creature is an Elf, it gets +2/+0 instead.",
    equip_cost="{1}",
)


ORC_BLADE = make_equipment(
    name="Orc Blade",
    mana_cost="{1}",
    text="Equipped creature gets +1/+0. Equipped creature has menace.",
    equip_cost="{1}",
)


# =============================================================================
# LANDS
# =============================================================================

RIVENDELL = make_land(
    name="Rivendell",
    text="{T}: Add {C}. {T}: Add {U}. Activate only if you control an Elf. When Rivendell enters, scry 1.",
    supertypes={"Legendary"},
)


THE_SHIRE = make_land(
    name="The Shire",
    text="{T}: Add {C}. {T}: Add {G}. Activate only if you control a Hobbit. When The Shire enters, create a Food token.",
    supertypes={"Legendary"},
)


MINAS_TIRITH = make_land(
    name="Minas Tirith",
    text="{T}: Add {C}. {T}: Add {W}. Activate only if you control a Human. {3}{W}, {T}: Create a 1/1 white Human Soldier creature token.",
    supertypes={"Legendary"},
)


MORDOR = make_land(
    name="Mordor, Land of Shadow",
    text="{T}: Add {C}. {T}: Add {B}. Activate only if you control an Orc or Wraith. Mordor enters tapped.",
    supertypes={"Legendary"},
)


EREBOR = make_land(
    name="Erebor, the Lonely Mountain",
    text="{T}: Add {C}. {T}: Add {R}. Activate only if you control a Dwarf. When Erebor enters, create a Treasure token.",
    supertypes={"Legendary"},
)


HELMS_DEEP = make_land(
    name="Helm's Deep",
    text="{T}: Add {C}. {2}{W}, {T}: Target creature you control gains indestructible until end of turn.",
    supertypes={"Legendary"},
)


ISENGARD = make_land(
    name="Isengard",
    text="{T}: Add {C}. {2}{B}, {T}: Create a 1/1 black Orc Soldier creature token.",
    supertypes={"Legendary"},
)


LOTHLORIEN = make_land(
    name="Lothlorien",
    text="{T}: Add {G} or {U}. Lothlorien enters tapped unless you control an Elf.",
)


FANGORN = make_land(
    name="Fangorn Forest",
    text="{T}: Add {G}. {4}{G}{G}, {T}: Create a 2/4 green Treefolk creature token with reach.",
)


MOUNT_DOOM = make_land(
    name="Mount Doom",
    text="{T}: Add {B} or {R}. {3}{B}{R}, {T}, Sacrifice Mount Doom and a legendary artifact: Destroy all creatures.",
    supertypes={"Legendary"},
)


WEATHERTOP = make_land(
    name="Weathertop",
    text="{T}: Add {C}. {2}, {T}: Weathertop deals 1 damage to any target. Activate only during your turn."
)


OSGILIATH = make_land(
    name="Osgiliath, Fallen City",
    text="{T}: Add {W} or {B}. Osgiliath enters tapped."
)


GREY_HAVENS = make_land(
    name="Grey Havens",
    text="{T}: Add {U}. {3}{U}, {T}: Return target creature to its owner's hand."
)


MORIA = make_land(
    name="Mines of Moria",
    text="{T}: Add {B} or {R}. {2}, {T}: Create a Treasure token. Activate only if a creature died this turn."
)


EDORAS = make_land(
    name="Edoras",
    text="{T}: Add {W} or {R}. When Edoras enters, if you control a Knight, create a 1/1 white Human Soldier creature token."
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

LORD_OF_THE_RINGS_CARDS = {
    # WHITE - GONDOR, ROHAN, MEN OF THE WEST
    "Aragorn, King of Gondor": ARAGORN_KING_OF_GONDOR,
    "Boromir, Captain of Gondor": BOROMIR_CAPTAIN_OF_GONDOR,
    "Faramir, Ranger of Ithilien": FARAMIR_RANGER_OF_ITHILIEN,
    "Theoden, King of Rohan": THEODEN_KING_OF_ROHAN,
    "Eowyn, Shieldmaiden of Rohan": EOWYN_SHIELDMAIDEN,
    "Eomer, Marshal of Rohan": EOMER_MARSHAL_OF_ROHAN,
    "Soldier of Gondor": GONDOR_SOLDIER,
    "Tower Guard of Minas Tirith": TOWER_GUARD,
    "Rider of Rohan": RIDER_OF_ROHAN,
    "Knights of Dol Amroth": KNIGHTS_OF_DOL_AMROTH,
    "Citadel Castellan": CITADEL_CASTELLAN,
    "Rohirrim Lancer": ROHIRRIM_LANCER,
    "Beacon Warden": BEACON_WARDEN,
    "Pelennor Defender": PELENNOR_DEFENDER,
    "Osgiliath Veteran": OSGILIATH_VETERAN,
    "Dunedain Healer": DUNEDAIN_HEALER,
    "Minas Tirith Recruit": MINAS_TIRITH_RECRUIT,
    "Helm's Deep Guard": HELM_S_DEEP_GUARD,
    "Shield of the West": SHIELD_OF_THE_WEST,
    "Charge of the Rohirrim": CHARGE_OF_THE_ROHIRRIM,
    "Gondorian Discipline": GONDORIAN_DISCIPLINE,
    "Rally the West": RALLY_THE_WEST,
    "Elendil's Courage": ELENDIL_S_COURAGE,
    "Valiant Stand": VALIANT_STAND,
    "Mustering of Gondor": MUSTERING_OF_GONDOR,
    "Ride to Ruin": RIDE_TO_RUIN,
    "Restoration of the King": RESTORATION_OF_THE_KING,
    "Dawn Over Minas Tirith": DAWN_OF_HOPE,
    "Banner of Gondor": BANNER_OF_GONDOR,
    "Oath of Eorl": OATH_OF_EORL,
    "The White Tree": THE_WHITE_TREE,

    # BLUE - ELVES, WISDOM, FORESIGHT
    "Galadriel, Lady of Light": GALADRIEL_LADY_OF_LIGHT,
    "Elrond, Lord of Rivendell": ELROND_LORD_OF_RIVENDELL,
    "Arwen, Evenstar": ARWEN_EVENSTAR,
    "Legolas, Prince of Mirkwood": LEGOLAS_PRINCE_OF_MIRKWOOD,
    "Celeborn, Lord of Lorien": CELEBORN_LORD_OF_LORIEN,
    "Cirdan the Shipwright": CIRDAN_THE_SHIPWRIGHT,
    "Lorien Sentinel": LORIEN_SENTINEL,
    "Rivendell Scholar": RIVENDELL_SCHOLAR,
    "Mirkwood Archer": MIRKWOOD_ARCHER,
    "Grey Havens Navigator": GREY_HAVENS_NAVIGATOR,
    "Elvish Seer": ELVISH_SEER,
    "Silvan Tracker": SILVAN_TRACKER,
    "Noldor Loremaster": NOLDOR_LOREMASTER,
    "Imladris Guardian": IMLADRIS_GUARDIAN,
    "Keeper of the Mirror": MIRROR_OF_GALADRIEL,
    "Foresight of the Elves": FORESIGHT_OF_ELVES,
    "Elven Wisdom": ELVEN_WISDOM,
    "Mists of Lorien": MISTS_OF_LORIEN,
    "Visions of the Palantir": VISIONS_OF_THE_PALANTIR,
    "Elrond's Rejection": COUNTERSPELL_OF_THE_WISE,
    "Silver Flow": SILVER_FLOW,
    "Council of Elrond": COUNCIL_OF_ELROND,
    "Words of the Eldar": WORDS_OF_THE_ELDAR,
    "Sailing to Valinor": SAILING_TO_VALINOR,
    "Memory of Ages": MEMORY_OF_AGES,
    "Mirror of Galadriel": MIRROR_POOL,
    "Light of Earendil": LIGHT_OF_EARENDIL,
    "Elven Sanctuary": ELVEN_SANCTUARY,

    # BLACK - MORDOR, SAURON, CORRUPTION
    "Sauron, the Dark Lord": SAURON_THE_DARK_LORD,
    "Witch-king of Angmar": WITCH_KING_OF_ANGMAR,
    "Saruman, Voice of Isengard": SARUMAN_THE_WHITE,
    "Mouth of Sauron": MOUTH_OF_SAURON,
    "Grima Wormtongue": GRIMA_WORMTONGUE,
    "Nazgul": NAZGUL,
    "Orc Warrior": ORC_WARRIOR,
    "Uruk-hai Berserker": URUK_HAI_BERSERKER,
    "Mordor Siege Engine": MORDOR_SIEGE_TOWER,
    "Haradrim Assassin": HARADRIM_ASSASSIN,
    "Moria Orc": MORIA_ORC,
    "Corsair of Umbar": CORSAIR_OF_UMBAR,
    "Easterling Soldier": EASTERLING_SOLDIER,
    "Orc Chieftain": ORC_CHIEFTAIN,
    "Morgul Knight": MORGUL_KNIGHT,
    "Spawn of Shelob": SHELOB_SPAWN,
    "Shadow of Mordor": SHADOW_OF_MORDOR,
    "Corruption Spreads": CORRUPTION_SPREADS,
    "Morgul Blade": MORGUL_BLADE,
    "Dark Whispers": DARK_WHISPERS,
    "Treachery of Isengard": TREACHERY_OF_ISENGARD,
    "Sauron's Command": SAURON_S_COMMAND,
    "March of the Orcs": MARCH_OF_THE_ORCS,
    "Harvest of Souls": HARVEST_OF_SOULS,
    "Corruption of Power": CORRUPTION_OF_POWER,
    "Ritual of Morgoth": RITUAL_OF_MORGOTH,
    "Eye of Sauron": EYE_OF_SAURON,
    "Shadow of the East": SHADOW_OF_THE_EAST,
    "The Ring Tempts You": THE_RING_TEMPTS,

    # RED - DWARVES, BATTLE, FIRE
    "Gimli, Son of Gloin": GIMLI_SON_OF_GLOIN,
    "Thorin Oakenshield": THORIN_OAKENSHIELD,
    "Dain Ironfoot": DAIN_IRONFOOT,
    "Balrog of Moria": BALROG_OF_MORIA,
    "Iron Hills Warrior": IRON_HILLS_WARRIOR,
    "Dwarf Berserker": DWARF_BERSERKER,
    "Erebor Smith": EREBOR_SMITH,
    "Dwarf Miner": DWARF_MINER,
    "Mountain Guard": MOUNTAIN_GUARD,
    "Cave Troll": CAVE_TROLL,
    "Warg Rider": WARG_RIDER,
    "Dragon of the North": DRAGON_OF_THE_NORTH,
    "Khazad-dum Veteran": KHAZAD_DUM_VETERAN,
    "Fire Drake": FIRE_DRAKE,
    "Moria Goblin": MORIA_GOBLIN,
    "Flame of Anor": FLAME_OF_ANOR,
    "Dwarven Rage": DWARVEN_RAGE,
    "Dragon's Breath": DRAGON_S_BREATH,
    "Forge Fire": FORGE_FIRE,
    "Battle Cry of Erebor": BATTLE_CRY,
    "Smash the Gate": SMASH_THE_GATE,
    "Siege of Erebor": SIEGE_OF_EREBOR,
    "Dragon Fire": DRAGON_FIRE,
    "Call of the Mountain": CALL_OF_THE_MOUNTAIN,
    "Delving the Mines": MINES_OF_MORIA,
    "Forge of Erebor": FORGE_OF_EREBOR,
    "Fires of Mount Doom": FIRES_OF_MOUNT_DOOM,
    "Wrath of the Dwarves": WRATH_OF_THE_DWARVES,

    # GREEN - HOBBITS, ENTS, NATURE
    "Frodo, the Ring-bearer": FRODO_RING_BEARER,
    "Samwise, the Brave": SAMWISE_THE_BRAVE,
    "Merry, Esquire of Rohan": MERRY_BRANDYBUCK,
    "Pippin, Guard of the Citadel": PIPPIN_GUARD_OF_THE_CITADEL,
    "Treebeard, Eldest of Ents": TREEBEARD_ELDEST_OF_ENTS,
    "Tom Bombadil": TOM_BOMBADIL,
    "Gwaihir, Wind Lord": GWAIHIR_WIND_LORD,
    "Quickbeam, Bregalad": QUICKBEAM,
    "Shire Hobbit": SHIRE_HOBBIT,
    "Ent Sapling": ENT_SAPLING,
    "Hobbiton Gardener": HOBBITON_GARDENER,
    "Fangorn Guardian": FANGORN_GUARDIAN,
    "Great Eagle": GREAT_EAGLE,
    "Old Man Willow": OLD_MAN_WILLOW,
    "Buckland Shirriff": BUCKLAND_SHIRRIFF,
    "Oliphaunt": OLIPHAUNT,
    "Radagast's Companion": RADAGAST_S_COMPANION,
    "Huorn": HUORN,
    "Strength of Nature": STRENGTH_OF_NATURE,
    "Hobbit's Cunning": HOBBIT_S_CUNNING,
    "Entish Fury": ENTISH_FURY,
    "Gift of the Shire": GIFT_OF_THE_SHIRE,
    "The Eagles Are Coming": EAGLES_ARE_COMING,
    "Nature's Reclamation": NATURE_S_RECLAMATION,
    "Last March of the Ents": LAST_MARCH_OF_THE_ENTS,
    "Shire Harvest": SHIRE_HARVEST,
    "Party in the Shire": PARTY_IN_THE_SHIRE,
    "Isengard Unleashed": ISENGARD_UNLEASHED,
    "The Party Tree": PARTY_TREE,
    "Heart of Fangorn": FANGORN_FOREST,
    "Second Breakfast": SECOND_BREAKFAST,

    # MULTICOLOR
    "Gandalf the Grey": GANDALF_THE_GREY,
    "Gandalf the White": GANDALF_THE_WHITE,
    "Shelob, Child of Ungoliant": SHELOB_CHILD_OF_UNGOLIANT,
    "Elrond and Arwen, United": ELROND_AND_ARWEN,
    "Aragorn and Arwen, Reunited": ARAGORN_AND_ARWEN,

    # ARTIFACTS
    "The One Ring": THE_ONE_RING,
    "Sting, Blade of Bilbo": STING,
    "Glamdring, Foe-hammer": GLAMDRING,
    "Anduril, Flame of the West": ANDURIL,
    "Nenya, Ring of Adamant": NENYA,
    "Vilya, Ring of Air": VILYA,
    "Narya, Ring of Fire": NARYA,
    "Phial of Galadriel": PHIAL_OF_GALADRIEL,
    "Palantir of Orthanc": PALANTIR_OF_ORTHANC,
    "Mithril Coat": MITHRIL_COAT,
    "Horn of Gondor": HORN_OF_GONDOR,
    "Ring of Barahir": RING_OF_BARAHIR,
    "Morgul Sword": MORGUL_SWORD,
    "Dwarven Axe": DWARVEN_AXE,
    "Elven Bow": ELVEN_BOW,
    "Orc Blade": ORC_BLADE,

    # LANDS
    "Rivendell": RIVENDELL,
    "The Shire": THE_SHIRE,
    "Minas Tirith": MINAS_TIRITH,
    "Mordor, Land of Shadow": MORDOR,
    "Erebor, the Lonely Mountain": EREBOR,
    "Helm's Deep": HELMS_DEEP,
    "Isengard": ISENGARD,
    "Lothlorien": LOTHLORIEN,
    "Fangorn Forest": FANGORN,
    "Mount Doom": MOUNT_DOOM,
    "Weathertop": WEATHERTOP,
    "Osgiliath, Fallen City": OSGILIATH,
    "Grey Havens": GREY_HAVENS,
    "Mines of Moria": MORIA,
    "Edoras": EDORAS,
}
