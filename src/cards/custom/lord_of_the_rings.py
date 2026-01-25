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
    new_id, get_power, get_toughness,
    # New ability system
    TriggeredAbility, StaticAbility, KeywordAbility,
    ETBTrigger, DeathTrigger, AttackTrigger, DealsDamageTrigger, UpkeepTrigger,
    GainLife, LoseLife, DrawCards, DiscardCards, DealDamage, AddCounters, Scry,
    CreateToken, CompositeEffect,
    PTBoost, KeywordGrant,
    SelfTarget, AnotherCreature, AnotherCreatureYouControl, CreatureWithSubtype,
    OtherCreaturesYouControlFilter, CreaturesWithSubtypeFilter, CreaturesYouControlFilter,
    OpponentCreaturesFilter, EachOpponentTarget,
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

def make_sorcery(name: str, mana_cost: str, colors: set, subtypes: set = None, supertypes: set = None, resolve=None):
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
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, subtypes: set = None, supertypes: set = None, abilities=None):
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
        abilities=abilities
    )


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                           subtypes: set = None, supertypes: set = None, abilities=None):
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
        abilities=abilities
    )


def make_equipment(name: str, mana_cost: str, equip_cost: str, subtypes: set = None, supertypes: set = None, abilities=None):
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
        abilities=abilities
    )


def make_land(name: str, subtypes: set = None, supertypes: set = None):
    """Helper to create land card definitions."""
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        )
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


# =============================================================================
# WHITE CARDS - GONDOR, ROHAN, MEN OF THE WEST
# =============================================================================

# --- Legendary Creatures ---

# Aragorn needs Fellowship (set-specific mechanic) + attack trigger
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
    setup_interceptors=aragorn_setup
)


BOROMIR_CAPTAIN_OF_GONDOR = make_creature(
    name="Boromir, Captain of Gondor",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Soldier"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Vigilance")
        # Death trigger to grant indestructible requires setup_interceptors
    ]
)


# Faramir has a complex filter (Human ETB) - keep old style
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
    setup_interceptors=faramir_setup
)


THEODEN_KING_OF_ROHAN = make_creature(
    name="Theoden, King of Rohan",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Knight"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Human", include_self=False)
        )
    ]
)


EOWYN_SHIELDMAIDEN = make_creature(
    name="Eowyn, Shieldmaiden of Rohan",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="First strike")
    ]
)


EOMER_MARSHAL_OF_ROHAN = make_creature(
    name="Eomer, Marshal of Rohan",
    power=4, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Noble", "Knight"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Haste")
        # Attack trigger for +2/+0 when attacks alone requires setup_interceptors
    ]
)


# --- Regular Creatures ---

GONDOR_SOLDIER = make_creature(
    name="Soldier of Gondor",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(1)
        )
    ]
)


TOWER_GUARD = make_creature(
    name="Tower Guard of Minas Tirith",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    abilities=[
        KeywordAbility(keyword="Vigilance"),
        StaticAbility(
            effect=KeywordGrant(["vigilance"]),
            filter=CreaturesWithSubtypeFilter(subtype="Soldier", include_self=False)
        )
    ]
)


RIDER_OF_ROHAN = make_creature(
    name="Rider of Rohan",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    abilities=[
        KeywordAbility(keyword="First strike"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CreateToken(name="Human Soldier", power=1, toughness=1, colors={"W"}, subtypes={"Human", "Soldier"})
        )
    ]
)


KNIGHTS_OF_DOL_AMROTH = make_creature(
    name="Knights of Dol Amroth",
    power=3, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    abilities=[
        KeywordAbility(keyword="First strike")
        # Attack trigger for Knights +1/+0 requires setup_interceptors
    ]
)


CITADEL_CASTELLAN = make_creature(
    name="Citadel Castellan",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    abilities=[
        KeywordAbility(keyword="Defender")
    ]
)


ROHIRRIM_LANCER = make_creature(
    name="Rohirrim Lancer",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    abilities=[
        KeywordAbility(keyword="Haste")
    ]
)


BEACON_WARDEN = make_creature(
    name="Beacon Warden",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"}
)


PELENNOR_DEFENDER = make_creature(
    name="Pelennor Defender",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"}
)


OSGILIATH_VETERAN = make_creature(
    name="Osgiliath Veteran",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"}
)


DUNEDAIN_HEALER = make_creature(
    name="Dunedain Healer",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"}
)


MINAS_TIRITH_RECRUIT = make_creature(
    name="Minas Tirith Recruit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=CreateToken(name="Human Soldier", power=1, toughness=1, colors={"W"}, subtypes={"Human", "Soldier"})
        )
    ]
)


HELM_S_DEEP_GUARD = make_creature(
    name="Helm's Deep Guard",
    power=0, toughness=5,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    abilities=[
        KeywordAbility(keyword="Defender"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CreateToken(name="Human Soldier", power=1, toughness=1, colors={"W"}, subtypes={"Human", "Soldier"})
        )
    ]
)


# --- Instants ---

SHIELD_OF_THE_WEST = make_instant(
    name="Shield of the West",
    mana_cost="{1}{W}",
    colors={Color.WHITE}
)


CHARGE_OF_THE_ROHIRRIM = make_instant(
    name="Charge of the Rohirrim",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE}
)


GONDORIAN_DISCIPLINE = make_instant(
    name="Gondorian Discipline",
    mana_cost="{W}",
    colors={Color.WHITE}
)


RALLY_THE_WEST = make_instant(
    name="Rally the West",
    mana_cost="{1}{W}",
    colors={Color.WHITE}
)


ELENDIL_S_COURAGE = make_instant(
    name="Elendil's Courage",
    mana_cost="{W}",
    colors={Color.WHITE}
)


VALIANT_STAND = make_instant(
    name="Valiant Stand",
    mana_cost="{2}{W}",
    colors={Color.WHITE}
)


# --- Sorceries ---

MUSTERING_OF_GONDOR = make_sorcery(
    name="Mustering of Gondor",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE}
)


RIDE_TO_RUIN = make_sorcery(
    name="Ride to Ruin",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE}
)


RESTORATION_OF_THE_KING = make_sorcery(
    name="Restoration of the King",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE}
)


DAWN_OF_HOPE = make_sorcery(
    name="Dawn Over Minas Tirith",
    mana_cost="{2}{W}",
    colors={Color.WHITE}
)


# --- Enchantments ---

BANNER_OF_GONDOR = make_enchantment(
    name="Banner of Gondor",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Human")
        )
    ]
)


OATH_OF_EORL = make_enchantment(
    name="Oath of Eorl",
    mana_cost="{1}{W}",
    colors={Color.WHITE}
)


THE_WHITE_TREE = make_enchantment(
    name="The White Tree",
    mana_cost="{2}{W}",
    colors={Color.WHITE}
)


# =============================================================================
# BLUE CARDS - ELVES, WISDOM, FORESIGHT
# =============================================================================

# --- Legendary Creatures ---

# Galadriel has complex abilities (keyword grant + upkeep scry) - keep old style
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
    setup_interceptors=galadriel_setup
)


# Elrond has complex ETB (draw equal to legendary count) - keep old style
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
    setup_interceptors=elrond_setup
)


ARWEN_EVENSTAR = make_creature(
    name="Arwen, Evenstar",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Lifelink")
    ]
)


# Legolas has Fellowship keyword mechanic - keep old style
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
    setup_interceptors=legolas_setup
)


CELEBORN_LORD_OF_LORIEN = make_creature(
    name="Celeborn, Lord of Lorien",
    power=2, toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Elf", include_self=False)
        )
    ]
)


# --- Regular Creatures ---

LORIEN_SENTINEL = make_creature(
    name="Lorien Sentinel",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Scout"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=Scry(1)
        )
    ]
)


RIVENDELL_SCHOLAR = make_creature(
    name="Rivendell Scholar",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"}
)


MIRKWOOD_ARCHER = make_creature(
    name="Mirkwood Archer",
    power=2, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Archer"},
    abilities=[
        KeywordAbility(keyword="Reach")
    ]
)


GREY_HAVENS_NAVIGATOR = make_creature(
    name="Grey Havens Navigator",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Sailor"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=Scry(2)
        )
    ]
)


ELVISH_SEER = make_creature(
    name="Elvish Seer",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"}
)


SILVAN_TRACKER = make_creature(
    name="Silvan Tracker",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Scout"}
)


NOLDOR_LOREMASTER = make_creature(
    name="Noldor Loremaster",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(2)
        )
    ]
)


IMLADRIS_GUARDIAN = make_creature(
    name="Imladris Guardian",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Soldier"},
    abilities=[
        KeywordAbility(keyword="Flash")
    ]
)


MIRROR_OF_GALADRIEL = make_creature(
    name="Keeper of the Mirror",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"}
)


CIRDAN_THE_SHIPWRIGHT = make_creature(
    name="Cirdan the Shipwright",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Artificer"},
    supertypes={"Legendary"}
)


# --- Instants ---

FORESIGHT_OF_ELVES = make_instant(
    name="Foresight of the Elves",
    mana_cost="{1}{U}",
    colors={Color.BLUE}
)


ELVEN_WISDOM = make_instant(
    name="Elven Wisdom",
    mana_cost="{2}{U}",
    colors={Color.BLUE}
)


MISTS_OF_LORIEN = make_instant(
    name="Mists of Lorien",
    mana_cost="{1}{U}",
    colors={Color.BLUE}
)


VISIONS_OF_THE_PALANTIR = make_instant(
    name="Visions of the Palantir",
    mana_cost="{U}",
    colors={Color.BLUE}
)


COUNTERSPELL_OF_THE_WISE = make_instant(
    name="Elrond's Rejection",
    mana_cost="{U}{U}",
    colors={Color.BLUE}
)


SILVER_FLOW = make_instant(
    name="Silver Flow",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE}
)


# --- Sorceries ---

COUNCIL_OF_ELROND = make_sorcery(
    name="Council of Elrond",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE}
)


WORDS_OF_THE_ELDAR = make_sorcery(
    name="Words of the Eldar",
    mana_cost="{3}{U}",
    colors={Color.BLUE}
)


SAILING_TO_VALINOR = make_sorcery(
    name="Sailing to Valinor",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE}
)


MEMORY_OF_AGES = make_sorcery(
    name="Memory of Ages",
    mana_cost="{1}{U}",
    colors={Color.BLUE}
)


# --- Enchantments ---

MIRROR_POOL = make_enchantment(
    name="Mirror of Galadriel",
    mana_cost="{2}{U}",
    colors={Color.BLUE}
)


LIGHT_OF_EARENDIL = make_enchantment(
    name="Light of Earendil",
    mana_cost="{1}{U}",
    colors={Color.BLUE}
)


ELVEN_SANCTUARY = make_enchantment(
    name="Elven Sanctuary",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE}
)


# =============================================================================
# BLACK CARDS - MORDOR, SAURON, CORRUPTION
# =============================================================================

# --- Legendary Creatures ---

SAURON_THE_DARK_LORD = make_creature(
    name="Sauron, the Dark Lord",
    power=7, toughness=7,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Horror"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Menace"),
        KeywordAbility(keyword="Trample"),
        StaticAbility(
            effect=PTBoost(-1, -1),
            filter=OpponentCreaturesFilter()
        )
    ]
)


WITCH_KING_OF_ANGMAR = make_creature(
    name="Witch-king of Angmar",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Flying")
    ]
)


# Saruman has complex spell cast trigger - keep old style
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
    setup_interceptors=saruman_setup
)


MOUTH_OF_SAURON = make_creature(
    name="Mouth of Sauron",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Menace"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DiscardCards(1, target=EachOpponentTarget())
        )
    ]
)


GRIMA_WORMTONGUE = make_creature(
    name="Grima Wormtongue",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"}
)


# --- Regular Creatures ---

# Nazgul has complex damage trigger - keep old style
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
    setup_interceptors=nazgul_setup
)


ORC_WARRIOR = make_creature(
    name="Orc Warrior",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Warrior"},
    abilities=[
        KeywordAbility(keyword="Menace")
    ]
)


URUK_HAI_BERSERKER = make_creature(
    name="Uruk-hai Berserker",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Berserker"}
)


MORDOR_SIEGE_TOWER = make_creature(
    name="Mordor Siege Engine",
    power=4, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Construct"},
    abilities=[
        KeywordAbility(keyword="Trample")
    ]
)


HARADRIM_ASSASSIN = make_creature(
    name="Haradrim Assassin",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    abilities=[
        KeywordAbility(keyword="Deathtouch")
    ]
)


MORIA_ORC = make_creature(
    name="Moria Orc",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Soldier"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=CreateToken(name="Orc", power=1, toughness=1, colors={"B"}, subtypes={"Orc", "Soldier"})
        )
    ]
)


CORSAIR_OF_UMBAR = make_creature(
    name="Corsair of Umbar",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CompositeEffect([
                LoseLife(2, target=EachOpponentTarget()),
                GainLife(2)
            ])
        )
    ]
)


EASTERLING_SOLDIER = make_creature(
    name="Easterling Soldier",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=LoseLife(1, target=EachOpponentTarget())
        )
    ]
)


ORC_CHIEFTAIN = make_creature(
    name="Orc Chieftain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Warrior"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesWithSubtypeFilter(subtype="Orc", include_self=False)
        )
    ]
)


MORGUL_KNIGHT = make_creature(
    name="Morgul Knight",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith", "Knight"}
)


SHELOB_SPAWN = make_creature(
    name="Spawn of Shelob",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spider"},
    abilities=[
        KeywordAbility(keyword="Reach"),
        KeywordAbility(keyword="Deathtouch")
    ]
)


# --- Instants ---

SHADOW_OF_MORDOR = make_instant(
    name="Shadow of Mordor",
    mana_cost="{1}{B}",
    colors={Color.BLACK}
)


CORRUPTION_SPREADS = make_instant(
    name="Corruption Spreads",
    mana_cost="{B}",
    colors={Color.BLACK}
)


MORGUL_BLADE = make_instant(
    name="Morgul Blade",
    mana_cost="{1}{B}",
    colors={Color.BLACK}
)


DARK_WHISPERS = make_instant(
    name="Dark Whispers",
    mana_cost="{2}{B}",
    colors={Color.BLACK}
)


TREACHERY_OF_ISENGARD = make_instant(
    name="Treachery of Isengard",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK}
)


SAURON_S_COMMAND = make_instant(
    name="Sauron's Command",
    mana_cost="{B}{B}",
    colors={Color.BLACK}
)


# --- Sorceries ---

MARCH_OF_THE_ORCS = make_sorcery(
    name="March of the Orcs",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK}
)


HARVEST_OF_SOULS = make_sorcery(
    name="Harvest of Souls",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK}
)


CORRUPTION_OF_POWER = make_sorcery(
    name="Corruption of Power",
    mana_cost="{2}{B}",
    colors={Color.BLACK}
)


RITUAL_OF_MORGOTH = make_sorcery(
    name="Ritual of Morgoth",
    mana_cost="{3}{B}",
    colors={Color.BLACK}
)


# --- Enchantments ---

# Eye of Sauron has upkeep trigger - keep old style
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
    setup_interceptors=eye_of_sauron_setup
)


SHADOW_OF_THE_EAST = make_enchantment(
    name="Shadow of the East",
    mana_cost="{1}{B}",
    colors={Color.BLACK}
)


THE_RING_TEMPTS = make_enchantment(
    name="The Ring Tempts You",
    mana_cost="{2}{B}",
    colors={Color.BLACK}
)


# =============================================================================
# RED CARDS - DWARVES, BATTLE, FIRE
# =============================================================================

# --- Legendary Creatures ---

# Gimli has Fellowship mechanic - keep old style
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
    setup_interceptors=gimli_setup
)


THORIN_OAKENSHIELD = make_creature(
    name="Thorin Oakenshield",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Noble", "Warrior"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Haste"),
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Dwarf", include_self=False)
        )
    ]
)


DAIN_IRONFOOT = make_creature(
    name="Dain Ironfoot",
    power=3, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Noble", "Warrior"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(["haste"]),
            filter=CreaturesWithSubtypeFilter(subtype="Dwarf")
        )
    ]
)


# Balrog has complex attack trigger - keep old style
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
    setup_interceptors=balrog_setup
)


# --- Regular Creatures ---

IRON_HILLS_WARRIOR = make_creature(
    name="Iron Hills Warrior",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"},
    abilities=[
        KeywordAbility(keyword="Haste")
    ]
)


DWARF_BERSERKER = make_creature(
    name="Dwarf Berserker",
    power=3, toughness=1,
    mana_cost="{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Berserker"},
    abilities=[
        KeywordAbility(keyword="Haste")
    ]
)


EREBOR_SMITH = make_creature(
    name="Erebor Smith",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Artificer"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CreateToken(name="Treasure", power=0, toughness=0, subtypes={"Treasure"})
        )
    ]
)


DWARF_MINER = make_creature(
    name="Dwarf Miner",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Citizen"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=CreateToken(name="Treasure", power=0, toughness=0, subtypes={"Treasure"})
        )
    ]
)


MOUNTAIN_GUARD = make_creature(
    name="Mountain Guard",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Soldier"},
    abilities=[
        KeywordAbility(keyword="First strike")
    ]
)


CAVE_TROLL = make_creature(
    name="Cave Troll",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Troll"},
    abilities=[
        KeywordAbility(keyword="Trample")
    ]
)


WARG_RIDER = make_creature(
    name="Warg Rider",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Knight"},
    abilities=[
        KeywordAbility(keyword="Haste")
    ]
)


DRAGON_OF_THE_NORTH = make_creature(
    name="Dragon of the North",
    power=5, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    abilities=[
        KeywordAbility(keyword="Flying")
    ]
)


KHAZAD_DUM_VETERAN = make_creature(
    name="Khazad-dum Veteran",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"}
)


FIRE_DRAKE = make_creature(
    name="Fire Drake",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Drake"},
    abilities=[
        KeywordAbility(keyword="Flying")
    ]
)


MORIA_GOBLIN = make_creature(
    name="Moria Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    abilities=[
        KeywordAbility(keyword="Haste")
    ]
)


# --- Instants ---

FLAME_OF_ANOR = make_instant(
    name="Flame of Anor",
    mana_cost="{1}{R}{R}",
    colors={Color.RED}
)


DWARVEN_RAGE = make_instant(
    name="Dwarven Rage",
    mana_cost="{R}",
    colors={Color.RED}
)


DRAGON_S_BREATH = make_instant(
    name="Dragon's Breath",
    mana_cost="{2}{R}",
    colors={Color.RED}
)


FORGE_FIRE = make_instant(
    name="Forge Fire",
    mana_cost="{R}{R}",
    colors={Color.RED}
)


BATTLE_CRY = make_instant(
    name="Battle Cry of Erebor",
    mana_cost="{1}{R}",
    colors={Color.RED}
)


SMASH_THE_GATE = make_instant(
    name="Smash the Gate",
    mana_cost="{2}{R}",
    colors={Color.RED}
)


# --- Sorceries ---

SIEGE_OF_EREBOR = make_sorcery(
    name="Siege of Erebor",
    mana_cost="{4}{R}{R}",
    colors={Color.RED}
)


DRAGON_FIRE = make_sorcery(
    name="Dragon Fire",
    mana_cost="{3}{R}{R}",
    colors={Color.RED}
)


CALL_OF_THE_MOUNTAIN = make_sorcery(
    name="Call of the Mountain",
    mana_cost="{3}{R}",
    colors={Color.RED}
)


MINES_OF_MORIA = make_sorcery(
    name="Delving the Mines",
    mana_cost="{2}{R}",
    colors={Color.RED}
)


# --- Enchantments ---

FORGE_OF_EREBOR = make_enchantment(
    name="Forge of Erebor",
    mana_cost="{2}{R}",
    colors={Color.RED},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesWithSubtypeFilter(subtype="Dwarf")
        )
    ]
)


FIRES_OF_MOUNT_DOOM = make_enchantment(
    name="Fires of Mount Doom",
    mana_cost="{2}{R}{R}",
    colors={Color.RED}
)


WRATH_OF_THE_DWARVES = make_enchantment(
    name="Wrath of the Dwarves",
    mana_cost="{1}{R}",
    colors={Color.RED}
)


# =============================================================================
# GREEN CARDS - HOBBITS, ENTS, NATURE
# =============================================================================

# --- Legendary Creatures ---

# Frodo has Ring-bearer mechanic - keep old style
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
    setup_interceptors=frodo_setup
)


SAMWISE_THE_BRAVE = make_creature(
    name="Samwise, the Brave",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"},
    supertypes={"Legendary"}
)


MERRY_BRANDYBUCK = make_creature(
    name="Merry, Esquire of Rohan",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hobbit", "Knight"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Hobbit", include_self=False)
        )
    ]
)


PIPPIN_GUARD_OF_THE_CITADEL = make_creature(
    name="Pippin, Guard of the Citadel",
    power=1, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hobbit", "Soldier"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(1)
        )
    ]
)


TREEBEARD_ELDEST_OF_ENTS = make_creature(
    name="Treebeard, Eldest of Ents",
    power=5, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Reach"),
        KeywordAbility(keyword="Vigilance"),
        StaticAbility(
            effect=PTBoost(2, 2),
            filter=CreaturesWithSubtypeFilter(subtype="Treefolk", include_self=False)
        )
    ]
)


TOM_BOMBADIL = make_creature(
    name="Tom Bombadil",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"God"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(4)
        )
    ]
)


# --- Regular Creatures ---

SHIRE_HOBBIT = make_creature(
    name="Shire Hobbit",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CreateToken(name="Food", power=0, toughness=0, subtypes={"Food"})
        )
    ]
)


ENT_SAPLING = make_creature(
    name="Ent Sapling",
    power=0, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    abilities=[
        KeywordAbility(keyword="Defender"),
        KeywordAbility(keyword="Reach")
    ]
)


HOBBITON_GARDENER = make_creature(
    name="Hobbiton Gardener",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"}
)


FANGORN_GUARDIAN = make_creature(
    name="Fangorn Guardian",
    power=4, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    abilities=[
        KeywordAbility(keyword="Reach"),
        KeywordAbility(keyword="Trample")
    ]
)


GREAT_EAGLE = make_creature(
    name="Great Eagle",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    abilities=[
        KeywordAbility(keyword="Flying")
    ]
)


GWAIHIR_WIND_LORD = make_creature(
    name="Gwaihir, Wind Lord",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Flying")
    ]
)


OLD_MAN_WILLOW = make_creature(
    name="Old Man Willow",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    abilities=[
        KeywordAbility(keyword="Reach")
    ]
)


QUICKBEAM = make_creature(
    name="Quickbeam, Bregalad",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Haste")
    ]
)


BUCKLAND_SHIRRIFF = make_creature(
    name="Buckland Shirriff",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Scout"}
)


OLIPHAUNT = make_creature(
    name="Oliphaunt",
    power=6, toughness=6,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    abilities=[
        KeywordAbility(keyword="Trample")
    ]
)


RADAGAST_S_COMPANION = make_creature(
    name="Radagast's Companion",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    abilities=[
        KeywordAbility(keyword="Flying")
    ]
)


HUORN = make_creature(
    name="Huorn",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"}
)


# --- Instants ---

STRENGTH_OF_NATURE = make_instant(
    name="Strength of Nature",
    mana_cost="{1}{G}",
    colors={Color.GREEN}
)


HOBBIT_S_CUNNING = make_instant(
    name="Hobbit's Cunning",
    mana_cost="{G}",
    colors={Color.GREEN}
)


ENTISH_FURY = make_instant(
    name="Entish Fury",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN}
)


GIFT_OF_THE_SHIRE = make_instant(
    name="Gift of the Shire",
    mana_cost="{1}{G}",
    colors={Color.GREEN}
)


EAGLES_ARE_COMING = make_instant(
    name="The Eagles Are Coming",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN}
)


NATURE_S_RECLAMATION = make_instant(
    name="Nature's Reclamation",
    mana_cost="{1}{G}",
    colors={Color.GREEN}
)


# --- Sorceries ---

LAST_MARCH_OF_THE_ENTS = make_sorcery(
    name="Last March of the Ents",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN}
)


SHIRE_HARVEST = make_sorcery(
    name="Shire Harvest",
    mana_cost="{2}{G}",
    colors={Color.GREEN}
)


PARTY_IN_THE_SHIRE = make_sorcery(
    name="Party in the Shire",
    mana_cost="{3}{G}",
    colors={Color.GREEN}
)


ISENGARD_UNLEASHED = make_sorcery(
    name="Isengard Unleashed",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN}
)


# --- Enchantments ---

PARTY_TREE = make_enchantment(
    name="The Party Tree",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Hobbit")
        )
    ]
)


FANGORN_FOREST = make_enchantment(
    name="Heart of Fangorn",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN}
)


SECOND_BREAKFAST = make_enchantment(
    name="Second Breakfast",
    mana_cost="{1}{G}",
    colors={Color.GREEN}
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# --- Legendary Creatures ---

GANDALF_THE_GREY = make_creature(
    name="Gandalf the Grey",
    power=3, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Avatar", "Wizard"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Flash"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(2)
        )
    ]
)


GANDALF_THE_WHITE = make_creature(
    name="Gandalf the White",
    power=4, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Avatar", "Wizard"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Vigilance"),
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesYouControlFilter()
        )
    ]
)


# Shelob has complex damage trigger - keep old style
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
    setup_interceptors=shelob_setup
)


ELROND_AND_ARWEN = make_creature(
    name="Elrond and Arwen, United",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}{G}",
    colors={Color.WHITE, Color.BLUE, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CompositeEffect([
                GainLife(3),
                DrawCards(1)
            ])
        )
    ]
)


ARAGORN_AND_ARWEN = make_creature(
    name="Aragorn and Arwen, Reunited",
    power=5, toughness=5,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Elf", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility(keyword="Vigilance"),
        KeywordAbility(keyword="Lifelink"),
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=CreateToken(name="Human Soldier", power=2, toughness=2, colors={"W"}, subtypes={"Human", "Soldier"})
        )
    ]
)


# =============================================================================
# ARTIFACTS
# =============================================================================

# One Ring has upkeep trigger - keep old style
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
    equip_cost="{2}",
    subtypes={"Ring"},
    supertypes={"Legendary"},
    abilities=[one_ring_setup]  # Pass as list of setup functions
)


STING = make_equipment(
    name="Sting, Blade of Bilbo",
    mana_cost="{2}",
    equip_cost="{1}",
    supertypes={"Legendary"}
)


GLAMDRING = make_equipment(
    name="Glamdring, Foe-hammer",
    mana_cost="{3}",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


ANDURIL = make_equipment(
    name="Anduril, Flame of the West",
    mana_cost="{3}",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


NENYA = make_equipment(
    name="Nenya, Ring of Adamant",
    mana_cost="{2}",
    equip_cost="{1}",
    subtypes={"Ring"},
    supertypes={"Legendary"}
)


VILYA = make_equipment(
    name="Vilya, Ring of Air",
    mana_cost="{2}",
    equip_cost="{1}",
    subtypes={"Ring"},
    supertypes={"Legendary"}
)


NARYA = make_equipment(
    name="Narya, Ring of Fire",
    mana_cost="{2}",
    equip_cost="{1}",
    subtypes={"Ring"},
    supertypes={"Legendary"}
)


PHIAL_OF_GALADRIEL = make_artifact(
    name="Phial of Galadriel",
    mana_cost="{2}",
    supertypes={"Legendary"}
)


PALANTIR_OF_ORTHANC = make_artifact(
    name="Palantir of Orthanc",
    mana_cost="{3}",
    supertypes={"Legendary"}
)


MITHRIL_COAT = make_equipment(
    name="Mithril Coat",
    mana_cost="{3}",
    equip_cost="{3}",
    supertypes={"Legendary"}
)


HORN_OF_GONDOR = make_artifact(
    name="Horn of Gondor",
    mana_cost="{3}",
    supertypes={"Legendary"}
)


RING_OF_BARAHIR = make_equipment(
    name="Ring of Barahir",
    mana_cost="{1}",
    equip_cost="{1}"
)


MORGUL_SWORD = make_equipment(
    name="Morgul Sword",
    mana_cost="{2}",
    equip_cost="{2}"
)


DWARVEN_AXE = make_equipment(
    name="Dwarven Axe",
    mana_cost="{2}",
    equip_cost="{1}"
)


ELVEN_BOW = make_equipment(
    name="Elven Bow",
    mana_cost="{1}",
    equip_cost="{1}"
)


ORC_BLADE = make_equipment(
    name="Orc Blade",
    mana_cost="{1}",
    equip_cost="{1}"
)


# =============================================================================
# LANDS
# =============================================================================

RIVENDELL = make_land(
    name="Rivendell",
    supertypes={"Legendary"}
)


THE_SHIRE = make_land(
    name="The Shire",
    supertypes={"Legendary"}
)


MINAS_TIRITH = make_land(
    name="Minas Tirith",
    supertypes={"Legendary"}
)


MORDOR = make_land(
    name="Mordor, Land of Shadow",
    supertypes={"Legendary"}
)


EREBOR = make_land(
    name="Erebor, the Lonely Mountain",
    supertypes={"Legendary"}
)


HELMS_DEEP = make_land(
    name="Helm's Deep",
    supertypes={"Legendary"}
)


ISENGARD = make_land(
    name="Isengard",
    supertypes={"Legendary"}
)


LOTHLORIEN = make_land(
    name="Lothlorien"
)


FANGORN = make_land(
    name="Fangorn Forest"
)


MOUNT_DOOM = make_land(
    name="Mount Doom",
    supertypes={"Legendary"}
)


WEATHERTOP = make_land(
    name="Weathertop"
)


OSGILIATH = make_land(
    name="Osgiliath, Fallen City"
)


GREY_HAVENS = make_land(
    name="Grey Havens"
)


MORIA = make_land(
    name="Mines of Moria"
)


EDORAS = make_land(
    name="Edoras"
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


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    ARAGORN_KING_OF_GONDOR,
    BOROMIR_CAPTAIN_OF_GONDOR,
    FARAMIR_RANGER_OF_ITHILIEN,
    THEODEN_KING_OF_ROHAN,
    EOWYN_SHIELDMAIDEN,
    EOMER_MARSHAL_OF_ROHAN,
    GONDOR_SOLDIER,
    TOWER_GUARD,
    RIDER_OF_ROHAN,
    KNIGHTS_OF_DOL_AMROTH,
    CITADEL_CASTELLAN,
    ROHIRRIM_LANCER,
    BEACON_WARDEN,
    PELENNOR_DEFENDER,
    OSGILIATH_VETERAN,
    DUNEDAIN_HEALER,
    MINAS_TIRITH_RECRUIT,
    HELM_S_DEEP_GUARD,
    SHIELD_OF_THE_WEST,
    CHARGE_OF_THE_ROHIRRIM,
    GONDORIAN_DISCIPLINE,
    RALLY_THE_WEST,
    ELENDIL_S_COURAGE,
    VALIANT_STAND,
    MUSTERING_OF_GONDOR,
    RIDE_TO_RUIN,
    RESTORATION_OF_THE_KING,
    DAWN_OF_HOPE,
    BANNER_OF_GONDOR,
    OATH_OF_EORL,
    THE_WHITE_TREE,
    GALADRIEL_LADY_OF_LIGHT,
    ELROND_LORD_OF_RIVENDELL,
    ARWEN_EVENSTAR,
    LEGOLAS_PRINCE_OF_MIRKWOOD,
    CELEBORN_LORD_OF_LORIEN,
    LORIEN_SENTINEL,
    RIVENDELL_SCHOLAR,
    MIRKWOOD_ARCHER,
    GREY_HAVENS_NAVIGATOR,
    ELVISH_SEER,
    SILVAN_TRACKER,
    NOLDOR_LOREMASTER,
    IMLADRIS_GUARDIAN,
    MIRROR_OF_GALADRIEL,
    CIRDAN_THE_SHIPWRIGHT,
    FORESIGHT_OF_ELVES,
    ELVEN_WISDOM,
    MISTS_OF_LORIEN,
    VISIONS_OF_THE_PALANTIR,
    COUNTERSPELL_OF_THE_WISE,
    SILVER_FLOW,
    COUNCIL_OF_ELROND,
    WORDS_OF_THE_ELDAR,
    SAILING_TO_VALINOR,
    MEMORY_OF_AGES,
    MIRROR_POOL,
    LIGHT_OF_EARENDIL,
    ELVEN_SANCTUARY,
    SAURON_THE_DARK_LORD,
    WITCH_KING_OF_ANGMAR,
    SARUMAN_THE_WHITE,
    MOUTH_OF_SAURON,
    GRIMA_WORMTONGUE,
    NAZGUL,
    ORC_WARRIOR,
    URUK_HAI_BERSERKER,
    MORDOR_SIEGE_TOWER,
    HARADRIM_ASSASSIN,
    MORIA_ORC,
    CORSAIR_OF_UMBAR,
    EASTERLING_SOLDIER,
    ORC_CHIEFTAIN,
    MORGUL_KNIGHT,
    SHELOB_SPAWN,
    SHADOW_OF_MORDOR,
    CORRUPTION_SPREADS,
    MORGUL_BLADE,
    DARK_WHISPERS,
    TREACHERY_OF_ISENGARD,
    SAURON_S_COMMAND,
    MARCH_OF_THE_ORCS,
    HARVEST_OF_SOULS,
    CORRUPTION_OF_POWER,
    RITUAL_OF_MORGOTH,
    EYE_OF_SAURON,
    SHADOW_OF_THE_EAST,
    THE_RING_TEMPTS,
    GIMLI_SON_OF_GLOIN,
    THORIN_OAKENSHIELD,
    DAIN_IRONFOOT,
    BALROG_OF_MORIA,
    IRON_HILLS_WARRIOR,
    DWARF_BERSERKER,
    EREBOR_SMITH,
    DWARF_MINER,
    MOUNTAIN_GUARD,
    CAVE_TROLL,
    WARG_RIDER,
    DRAGON_OF_THE_NORTH,
    KHAZAD_DUM_VETERAN,
    FIRE_DRAKE,
    MORIA_GOBLIN,
    FLAME_OF_ANOR,
    DWARVEN_RAGE,
    DRAGON_S_BREATH,
    FORGE_FIRE,
    BATTLE_CRY,
    SMASH_THE_GATE,
    SIEGE_OF_EREBOR,
    DRAGON_FIRE,
    CALL_OF_THE_MOUNTAIN,
    MINES_OF_MORIA,
    FORGE_OF_EREBOR,
    FIRES_OF_MOUNT_DOOM,
    WRATH_OF_THE_DWARVES,
    FRODO_RING_BEARER,
    SAMWISE_THE_BRAVE,
    MERRY_BRANDYBUCK,
    PIPPIN_GUARD_OF_THE_CITADEL,
    TREEBEARD_ELDEST_OF_ENTS,
    TOM_BOMBADIL,
    SHIRE_HOBBIT,
    ENT_SAPLING,
    HOBBITON_GARDENER,
    FANGORN_GUARDIAN,
    GREAT_EAGLE,
    GWAIHIR_WIND_LORD,
    OLD_MAN_WILLOW,
    QUICKBEAM,
    BUCKLAND_SHIRRIFF,
    OLIPHAUNT,
    RADAGAST_S_COMPANION,
    HUORN,
    STRENGTH_OF_NATURE,
    HOBBIT_S_CUNNING,
    ENTISH_FURY,
    GIFT_OF_THE_SHIRE,
    EAGLES_ARE_COMING,
    NATURE_S_RECLAMATION,
    LAST_MARCH_OF_THE_ENTS,
    SHIRE_HARVEST,
    PARTY_IN_THE_SHIRE,
    ISENGARD_UNLEASHED,
    PARTY_TREE,
    FANGORN_FOREST,
    SECOND_BREAKFAST,
    GANDALF_THE_GREY,
    GANDALF_THE_WHITE,
    SHELOB_CHILD_OF_UNGOLIANT,
    ELROND_AND_ARWEN,
    ARAGORN_AND_ARWEN,
    THE_ONE_RING,
    STING,
    GLAMDRING,
    ANDURIL,
    NENYA,
    VILYA,
    NARYA,
    PHIAL_OF_GALADRIEL,
    PALANTIR_OF_ORTHANC,
    MITHRIL_COAT,
    HORN_OF_GONDOR,
    RING_OF_BARAHIR,
    MORGUL_SWORD,
    DWARVEN_AXE,
    ELVEN_BOW,
    ORC_BLADE,
    RIVENDELL,
    THE_SHIRE,
    MINAS_TIRITH,
    MORDOR,
    EREBOR,
    HELMS_DEEP,
    ISENGARD,
    LOTHLORIEN,
    FANGORN,
    MOUNT_DOOM,
    WEATHERTOP,
    OSGILIATH,
    GREY_HAVENS,
    MORIA,
    EDORAS
]
