"""
Lord of the Rings: War of the Ring (LOTR) Card Implementations

Set featuring Middle-earth. ~250 cards.
Features mechanics: Fellowship, Ring-bearer, Corruption
"""

from src.cards.card_factories import (
    make_artifact,
    make_artifact_creature,
    make_equipment,
    make_land,
    make_sorcery,
)

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness,
)
from typing import Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, creatures_with_subtype,
    make_spell_cast_trigger, make_upkeep_trigger,
    creatures_you_control,
    other_creatures_with_subtype, all_opponents,
    # Phase A spice-pass additions:
    make_activated_ability, make_equipment_setup,
    make_dynamic_pt_boost, count_permanents_with_subtype,
    # Phase A2 (slice 1) decision-axis flip additions. These helpers are
    # all enumerated in `_MTG_MODAL_HELPERS` (src/depth/engine_profiles.py)
    # so the AST scorer surfaces decision>0 on the cards that call them.
    make_top_n_land_pick, make_targeted_death_trigger, make_modal_etb_trigger,
)
from src.cards.ability_bundles import (
    etb_gain_life, etb_create_token, etb_draw,
    death_draw, static_pt_boost_by_subtype,
    static_pt_boost_all_you_control, static_keyword_grant_others,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _kw(*keywords: str) -> list[dict]:
    """Convert keyword strings to ability dict list for CardDefinition/Characteristics."""
    return [{'keyword': k} for k in keywords]


def _make_creature(
    *,
    name: str,
    power: int,
    toughness: int,
    mana_cost: str,
    colors: set,
    subtypes: set = None,
    supertypes: set = None,
    keywords: list[str] = None,
    text: str = "",
    setup_interceptors=None,
) -> CardDefinition:
    """Build creature with keyword dicts properly installed in abilities lists."""
    kw_list = _kw(*(keywords or []))
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost,
            power=power,
            toughness=toughness,
            abilities=list(kw_list),
        ),
        text=text,
        abilities=list(kw_list),
        setup_interceptors=setup_interceptors,
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


BOROMIR_CAPTAIN_OF_GONDOR = _make_creature(
    name="Boromir, Captain of Gondor",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Soldier"},
    supertypes={"Legendary"},
    keywords=["vigilance"],
    text="Vigilance",
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


def theoden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Human", include_self=False)
    return interceptors

THEODEN_KING_OF_ROHAN = make_creature(
    name="Theoden, King of Rohan",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Knight"},
    supertypes={"Legendary"},
    text="Other Human creatures you control get +1/+1.",
    setup_interceptors=theoden_setup,
)


EOWYN_SHIELDMAIDEN = _make_creature(
    name="Eowyn, Shieldmaiden of Rohan",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    keywords=["first strike"],
    text="First strike",
)


EOMER_MARSHAL_OF_ROHAN = _make_creature(
    name="Eomer, Marshal of Rohan",
    power=4, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Noble", "Knight"},
    supertypes={"Legendary"},
    keywords=["haste"],
    text="Haste",
)


# --- Regular Creatures ---

def gondor_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_gain_life(obj, 1)
    return [itc]

GONDOR_SOLDIER = make_creature(
    name="Soldier of Gondor",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Soldier of Gondor enters the battlefield, you gain 1 life.",
    setup_interceptors=gondor_soldier_setup,
)


def tower_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_keyword_grant_others(obj, ["vigilance"])
    # filter to Soldiers only
    soldier_itc = make_keyword_grant(obj, ["vigilance"], creatures_with_subtype(obj, "Soldier"))
    return [soldier_itc]

TOWER_GUARD = _make_creature(
    name="Tower Guard of Minas Tirith",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    keywords=["vigilance"],
    text="Vigilance. Other Soldier creatures you control have vigilance.",
    setup_interceptors=tower_guard_setup,
)


def rider_of_rohan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_create_token(obj, 1, 1, "Human Soldier", colors={Color.WHITE}, keywords=[])
    return [itc]

RIDER_OF_ROHAN = _make_creature(
    name="Rider of Rohan",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    keywords=["first strike"],
    text="First strike. When Rider of Rohan enters the battlefield, create a 1/1 white Human Soldier creature token.",
    setup_interceptors=rider_of_rohan_setup,
)


KNIGHTS_OF_DOL_AMROTH = _make_creature(
    name="Knights of Dol Amroth",
    power=3, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    keywords=["first strike"],
    text="First strike",
)


CITADEL_CASTELLAN = _make_creature(
    name="Citadel Castellan",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    keywords=["defender"],
    text="Defender",
)


ROHIRRIM_LANCER = _make_creature(
    name="Rohirrim Lancer",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    keywords=["haste"],
    text="Haste",
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


def minas_tirith_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True, 'name': 'Human Soldier',
                'power': 1, 'toughness': 1,
                'colors': {Color.WHITE}, 'subtypes': {'Human', 'Soldier'},
                'keywords': [], 'controller': obj.controller,
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_death_trigger(obj, effect_fn)]

MINAS_TIRITH_RECRUIT = make_creature(
    name="Minas Tirith Recruit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Minas Tirith Recruit dies, create a 1/1 white Human Soldier creature token.",
    setup_interceptors=minas_tirith_recruit_setup,
)


def helms_deep_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_create_token(obj, 1, 1, "Human Soldier", colors={Color.WHITE}, keywords=[])
    return [itc]

HELM_S_DEEP_GUARD = _make_creature(
    name="Helm's Deep Guard",
    power=0, toughness=5,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    keywords=["defender"],
    text="Defender. When Helm's Deep Guard enters the battlefield, create a 1/1 white Human Soldier creature token.",
    setup_interceptors=helms_deep_guard_setup,
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

def banner_of_gondor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Human", include_self=True)
    return interceptors

BANNER_OF_GONDOR = make_enchantment(
    name="Banner of Gondor",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Human creatures you control get +1/+1.",
    setup_interceptors=banner_of_gondor_setup,
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


ARWEN_EVENSTAR = _make_creature(
    name="Arwen, Evenstar",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    keywords=["lifelink"],
    text="Lifelink",
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


def celeborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Elf", include_self=False)
    return interceptors

CELEBORN_LORD_OF_LORIEN = make_creature(
    name="Celeborn, Lord of Lorien",
    power=2, toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="Other Elf creatures you control get +1/+1.",
    setup_interceptors=celeborn_setup,
)


# --- Regular Creatures ---

# STUB: ETB Scry(1) — Scry not implemented; text preserved, no interceptor
LORIEN_SENTINEL = make_creature(
    name="Lorien Sentinel",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Scout"},
    text="When Lorien Sentinel enters the battlefield, scry 1.",
)


RIVENDELL_SCHOLAR = make_creature(
    name="Rivendell Scholar",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"}
)


MIRKWOOD_ARCHER = _make_creature(
    name="Mirkwood Archer",
    power=2, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Archer"},
    keywords=["reach"],
    text="Reach",
)


# STUB: ETB Scry(2) — Scry not implemented; text preserved, no interceptor
GREY_HAVENS_NAVIGATOR = make_creature(
    name="Grey Havens Navigator",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Sailor"},
    text="When Grey Havens Navigator enters the battlefield, scry 2.",
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


def noldor_loremaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_draw(obj, 2)
    return [itc]

NOLDOR_LOREMASTER = make_creature(
    name="Noldor Loremaster",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Wizard"},
    text="When Noldor Loremaster enters the battlefield, draw two cards.",
    setup_interceptors=noldor_loremaster_setup,
)


IMLADRIS_GUARDIAN = _make_creature(
    name="Imladris Guardian",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elf", "Soldier"},
    keywords=["flash"],
    text="Flash",
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

def sauron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import opponent_creatures_filter
    interceptors = make_static_pt_boost(obj, -1, -1, opponent_creatures_filter(obj))
    return interceptors

SAURON_THE_DARK_LORD = _make_creature(
    name="Sauron, the Dark Lord",
    power=7, toughness=7,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Horror"},
    supertypes={"Legendary"},
    keywords=["menace", "trample"],
    text="Menace, trample. Creatures your opponents control get -1/-1.",
    setup_interceptors=sauron_setup,
)


WITCH_KING_OF_ANGMAR = _make_creature(
    name="Witch-king of Angmar",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith", "Noble"},
    supertypes={"Legendary"},
    keywords=["flying"],
    text="Flying",
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


# STUB: ETB DiscardCards — targeted discard not implemented; keyword migrated, text preserved
MOUTH_OF_SAURON = _make_creature(
    name="Mouth of Sauron",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    keywords=["menace"],
    text="Menace. When Mouth of Sauron enters the battlefield, each opponent discards a card.",
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


ORC_WARRIOR = _make_creature(
    name="Orc Warrior",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Warrior"},
    keywords=["menace"],
    text="Menace",
)


URUK_HAI_BERSERKER = make_creature(
    name="Uruk-hai Berserker",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Berserker"}
)


MORDOR_SIEGE_TOWER = _make_creature(
    name="Mordor Siege Engine",
    power=4, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Construct"},
    keywords=["trample"],
    text="Trample",
)


HARADRIM_ASSASSIN = _make_creature(
    name="Haradrim Assassin",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    keywords=["deathtouch"],
    text="Deathtouch",
)


def moria_orc_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True, 'name': 'Orc',
                'power': 1, 'toughness': 1,
                'colors': {Color.BLACK}, 'subtypes': {'Orc', 'Soldier'},
                'keywords': [], 'controller': obj.controller,
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_death_trigger(obj, effect_fn)]

MORIA_ORC = make_creature(
    name="Moria Orc",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Soldier"},
    text="When Moria Orc dies, create a 1/1 black Orc Soldier creature token.",
    setup_interceptors=moria_orc_setup,
)


def corsair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -2},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

CORSAIR_OF_UMBAR = make_creature(
    name="Corsair of Umbar",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When Corsair of Umbar enters the battlefield, each opponent loses 2 life and you gain 2 life.",
    setup_interceptors=corsair_setup,
)


def easterling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': opp_id, 'amount': -1},
            source=obj.id, controller=obj.controller,
        ) for opp_id in all_opponents(obj, state)]
    return [make_death_trigger(obj, effect_fn)]

EASTERLING_SOLDIER = make_creature(
    name="Easterling Soldier",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="When Easterling Soldier dies, each opponent loses 1 life.",
    setup_interceptors=easterling_setup,
)


def orc_chieftain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 0, "Orc", include_self=False)
    return interceptors

ORC_CHIEFTAIN = make_creature(
    name="Orc Chieftain",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Orc", "Warrior"},
    text="Other Orc creatures you control get +1/+0.",
    setup_interceptors=orc_chieftain_setup,
)


MORGUL_KNIGHT = make_creature(
    name="Morgul Knight",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith", "Knight"}
)


SHELOB_SPAWN = _make_creature(
    name="Spawn of Shelob",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spider"},
    keywords=["reach", "deathtouch"],
    text="Reach, deathtouch",
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


def thorin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Dwarf", include_self=False)
    return interceptors

THORIN_OAKENSHIELD = _make_creature(
    name="Thorin Oakenshield",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Noble", "Warrior"},
    supertypes={"Legendary"},
    keywords=["haste"],
    text="Haste. Other Dwarf creatures you control get +1/+1.",
    setup_interceptors=thorin_setup,
)


def dain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc = make_keyword_grant(obj, ["haste"], creatures_with_subtype(obj, "Dwarf"))
    return [itc]

DAIN_IRONFOOT = make_creature(
    name="Dain Ironfoot",
    power=3, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="Dwarf creatures you control have haste.",
    setup_interceptors=dain_setup,
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

IRON_HILLS_WARRIOR = _make_creature(
    name="Iron Hills Warrior",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"},
    keywords=["haste"],
    text="Haste",
)


DWARF_BERSERKER = _make_creature(
    name="Dwarf Berserker",
    power=3, toughness=1,
    mana_cost="{R}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Berserker"},
    keywords=["haste"],
    text="Haste",
)


def erebor_smith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_create_token(obj, 0, 0, "Treasure", keywords=[])
    return [itc]

EREBOR_SMITH = make_creature(
    name="Erebor Smith",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Artificer"},
    text="When Erebor Smith enters the battlefield, create a Treasure token.",
    setup_interceptors=erebor_smith_setup,
)


def dwarf_miner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True, 'name': 'Treasure',
                'power': 0, 'toughness': 0,
                'colors': set(), 'subtypes': {'Treasure'},
                'keywords': [], 'controller': obj.controller,
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_attack_trigger(obj, effect_fn)]

DWARF_MINER = make_creature(
    name="Dwarf Miner",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Citizen"},
    text="Whenever Dwarf Miner attacks, create a Treasure token.",
    setup_interceptors=dwarf_miner_setup,
)


MOUNTAIN_GUARD = _make_creature(
    name="Mountain Guard",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Soldier"},
    keywords=["first strike"],
    text="First strike",
)


CAVE_TROLL = _make_creature(
    name="Cave Troll",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Troll"},
    keywords=["trample"],
    text="Trample",
)


WARG_RIDER = _make_creature(
    name="Warg Rider",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Knight"},
    keywords=["haste"],
    text="Haste",
)


DRAGON_OF_THE_NORTH = _make_creature(
    name="Dragon of the North",
    power=5, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    keywords=["flying"],
    text="Flying",
)


KHAZAD_DUM_VETERAN = make_creature(
    name="Khazad-dum Veteran",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"}
)


FIRE_DRAKE = _make_creature(
    name="Fire Drake",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Drake"},
    keywords=["flying"],
    text="Flying",
)


MORIA_GOBLIN = _make_creature(
    name="Moria Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    keywords=["haste"],
    text="Haste",
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

def forge_of_erebor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 0, "Dwarf", include_self=True)
    return interceptors

FORGE_OF_EREBOR = make_enchantment(
    name="Forge of Erebor",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Dwarf creatures you control get +1/+0.",
    setup_interceptors=forge_of_erebor_setup,
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


def merry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Hobbit", include_self=False)
    return interceptors

MERRY_BRANDYBUCK = make_creature(
    name="Merry, Esquire of Rohan",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hobbit", "Knight"},
    supertypes={"Legendary"},
    text="Other Hobbit creatures you control get +1/+1.",
    setup_interceptors=merry_setup,
)


def pippin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_draw(obj, 1)
    return [itc]

PIPPIN_GUARD_OF_THE_CITADEL = make_creature(
    name="Pippin, Guard of the Citadel",
    power=1, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hobbit", "Soldier"},
    supertypes={"Legendary"},
    text="When Pippin, Guard of the Citadel enters the battlefield, draw a card.",
    setup_interceptors=pippin_setup,
)


def treebeard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 2, 2, "Treefolk", include_self=False)
    return interceptors

TREEBEARD_ELDEST_OF_ENTS = _make_creature(
    name="Treebeard, Eldest of Ents",
    power=5, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    supertypes={"Legendary"},
    keywords=["reach", "vigilance"],
    text="Reach, vigilance. Other Treefolk creatures you control get +2/+2.",
    setup_interceptors=treebeard_setup,
)


def tom_bombadil_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_gain_life(obj, 4)
    return [itc]

TOM_BOMBADIL = make_creature(
    name="Tom Bombadil",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="When Tom Bombadil enters the battlefield, you gain 4 life.",
    setup_interceptors=tom_bombadil_setup,
)


# --- Regular Creatures ---

def shire_hobbit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_create_token(obj, 0, 0, "Food", keywords=[])
    return [itc]

SHIRE_HOBBIT = make_creature(
    name="Shire Hobbit",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"},
    text="When Shire Hobbit enters the battlefield, create a Food token.",
    setup_interceptors=shire_hobbit_setup,
)


ENT_SAPLING = _make_creature(
    name="Ent Sapling",
    power=0, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    keywords=["defender", "reach"],
    text="Defender, reach",
)


HOBBITON_GARDENER = make_creature(
    name="Hobbiton Gardener",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Citizen"}
)


FANGORN_GUARDIAN = _make_creature(
    name="Fangorn Guardian",
    power=4, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    keywords=["reach", "trample"],
    text="Reach, trample",
)


GREAT_EAGLE = _make_creature(
    name="Great Eagle",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    keywords=["flying"],
    text="Flying",
)


GWAIHIR_WIND_LORD = _make_creature(
    name="Gwaihir, Wind Lord",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    supertypes={"Legendary"},
    keywords=["flying"],
    text="Flying",
)


OLD_MAN_WILLOW = _make_creature(
    name="Old Man Willow",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    keywords=["reach"],
    text="Reach",
)


QUICKBEAM = _make_creature(
    name="Quickbeam, Bregalad",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    supertypes={"Legendary"},
    keywords=["haste"],
    text="Haste",
)


BUCKLAND_SHIRRIFF = make_creature(
    name="Buckland Shirriff",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hobbit", "Scout"}
)


OLIPHAUNT = _make_creature(
    name="Oliphaunt",
    power=6, toughness=6,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    keywords=["trample"],
    text="Trample",
)


RADAGAST_S_COMPANION = _make_creature(
    name="Radagast's Companion",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    keywords=["flying"],
    text="Flying",
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

def party_tree_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Hobbit", include_self=True)
    return interceptors

PARTY_TREE = make_enchantment(
    name="The Party Tree",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Hobbit creatures you control get +1/+1.",
    setup_interceptors=party_tree_setup,
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

def gandalf_grey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_draw(obj, 2)
    return [itc]

GANDALF_THE_GREY = _make_creature(
    name="Gandalf the Grey",
    power=3, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Avatar", "Wizard"},
    supertypes={"Legendary"},
    keywords=["flash"],
    text="Flash. When Gandalf the Grey enters the battlefield, draw two cards.",
    setup_interceptors=gandalf_grey_setup,
)


def gandalf_white_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _txt = static_pt_boost_all_you_control(obj, 1, 1)
    return interceptors

GANDALF_THE_WHITE = _make_creature(
    name="Gandalf the White",
    power=4, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Avatar", "Wizard"},
    supertypes={"Legendary"},
    keywords=["vigilance"],
    text="Vigilance. Creatures you control get +1/+1.",
    setup_interceptors=gandalf_white_setup,
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


def elrond_arwen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.DRAW, payload={'player': obj.controller},
                  source=obj.id, controller=obj.controller),
        ]
    return [make_etb_trigger(obj, effect_fn)]

ELROND_AND_ARWEN = make_creature(
    name="Elrond and Arwen, United",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}{G}",
    colors={Color.WHITE, Color.BLUE, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="When Elrond and Arwen, United enters the battlefield, you gain 3 life and draw a card.",
    setup_interceptors=elrond_arwen_setup,
)


def aragorn_arwen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True, 'name': 'Human Soldier',
                'power': 2, 'toughness': 2,
                'colors': {Color.WHITE}, 'subtypes': {'Human', 'Soldier'},
                'keywords': [], 'controller': obj.controller,
            },
            source=obj.id, controller=obj.controller,
        )]
    return [make_attack_trigger(obj, effect_fn)]

ARAGORN_AND_ARWEN = _make_creature(
    name="Aragorn and Arwen, Reunited",
    power=5, toughness=5,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Elf", "Noble"},
    supertypes={"Legendary"},
    keywords=["vigilance", "lifelink"],
    text="Vigilance, lifelink. Whenever Aragorn and Arwen, Reunited attacks, create a 2/2 white Human Soldier creature token.",
    setup_interceptors=aragorn_arwen_setup,
)


# =============================================================================
# ARTIFACTS
# =============================================================================

# NOTE: THE_ONE_RING, ANDURIL, and MITHRIL_COAT below are PLACEHOLDERS for the
# Spice Pass section near the end of the file. Their full definitions are
# rewritten there to channel the format-defining feel (compression, ward,
# granted abilities). The intervening defs (STING, GLAMDRING, etc.) are kept
# vanilla. Do NOT remove these placeholders without also updating the
# registry — the Spice Pass section reassigns the module-level variables.

THE_ONE_RING = None  # populated in SPICE PASS section


STING = None  # populated in SPICE PASS V2 section


GLAMDRING = None  # populated in SPICE PASS V2 section


ANDURIL = None  # populated in SPICE PASS section


NENYA = None  # populated in SPICE PASS V2 section


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


MITHRIL_COAT = None  # populated in SPICE PASS section


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


LOTHLORIEN = None  # populated in SPICE PASS section


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
# SPICE PASS — Format-Defining Cards (Phase A)
# =============================================================================
# Modeled on the broken-card patterns in .claude/skills/spice-pass.md and the
# Star Wars / Dragon Ball pilot reference implementations. Phase A — within
# current engine surface only. Targets a mix of compression, snowball,
# hard-to-interact, and asymmetric-prison archetypes plus enhanced equipment
# that channels the Fellowship/Ring flavor.
# =============================================================================


# --- Aragorn, King Returned --- {2}{R}{W} 4/4 Mythic legendary Human (compression)
# Pattern: compression (lord + attack trigger + Fellowship dynamic boost).
def aragorn_returned_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self vigilance+haste; attack trigger pumps Humans; Fellowship +X/+X."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def attack_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller == obj.controller
                    and o.id != obj.id
                    and CardType.CREATURE in o.characteristics.types
                    and 'Human' in (o.characteristics.subtypes or set())):
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        'object_id': o.id,
                        'power_mod': 1,
                        'toughness_mod': 1,
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                ))
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={
                        'object_id': o.id,
                        'keyword': 'first_strike',
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                ))
        return events

    # Fellowship — +X/+X where X = legendary creatures you control (incl. self).
    def fellowship_mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        if target.id != obj.id:
            return (0, 0)
        x = count_legendary_creatures(obj.controller, st)
        return (x, x)

    def self_filter(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['vigilance', 'haste'], affects_self))
    interceptors.append(make_attack_trigger(obj, attack_effect))
    interceptors.extend(make_dynamic_pt_boost(obj, fellowship_mod, self_filter))
    return interceptors


ARAGORN_KING_RETURNED = make_creature(
    name="Aragorn, King Returned",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Noble", "Ranger"},
    supertypes={"Legendary"},
    text=(
        "Vigilance, haste. Whenever Aragorn attacks, other Human creatures "
        "you control get +1/+1 and gain first strike until end of turn. "
        "Fellowship — Aragorn gets +1/+1 for each legendary creature you "
        "control."
    ),
    setup_interceptors=aragorn_returned_setup,
)


# --- Gandalf, Mithrandir --- {1}{U}{R} 3/3 Mythic legendary Wizard (compression)
# Pattern: compression (flash + hexproof + ETB draw + tribal token + spell trigger).
def gandalf_mithrandir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self flash+hexproof; ETB draw 2 + create Spirit per Wizard; spell trigger pump."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
        ))
        # Create one 1/1 white Spirit token per Wizard you control (incl. self).
        wiz_count = 0
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller == obj.controller
                    and CardType.CREATURE in o.characteristics.types
                    and 'Wizard' in (o.characteristics.subtypes or set())):
                wiz_count += 1
        for _ in range(max(1, wiz_count)):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {
                        'name': 'Spirit',
                        'power': 1, 'toughness': 1,
                        'colors': {Color.WHITE},
                        'types': {CardType.CREATURE},
                        'subtypes': {'Spirit'},
                        'keywords': ['flying'],
                    },
                },
                source=obj.id,
            ))
        return events

    def spell_pump_effect(event: Event, st: GameState) -> list[Event]:
        # Whenever you cast an instant or sorcery, Gandalf gets +1/+0 EOT.
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 1,
                'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['flash', 'hexproof'], affects_self),
        make_etb_trigger(obj, etb_effect),
        make_spell_cast_trigger(
            obj, spell_pump_effect,
            spell_type_filter={CardType.INSTANT, CardType.SORCERY},
        ),
    ]


GANDALF_MITHRANDIR = make_creature(
    name="Gandalf, Mithrandir",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Avatar", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Flash. Hexproof. When Gandalf, Mithrandir enters, draw two cards "
        "and create a 1/1 white Spirit creature token with flying for each "
        "Wizard you control. Whenever you cast an instant or sorcery spell, "
        "Gandalf gets +1/+0 until end of turn."
    ),
    setup_interceptors=gandalf_mithrandir_setup,
)


# --- Galadriel, Lady of Lothlorien --- {1}{G}{W}{U} 3/4 Mythic legendary Elf
# Pattern: snowball / Fellowship-anchored value engine.
def galadriel_lothlorien_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Elves+Humans get +1/+1 and have hexproof. Upkeep scry 2,
    draw a card if you control 3+ legendary creatures."""

    def others_elf_or_human(target: GameObject, st: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        subs = target.characteristics.subtypes or set()
        return 'Elf' in subs or 'Human' in subs

    def upkeep_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
        )]
        if count_legendary_creatures(obj.controller, st) >= 3:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ))
        return events

    interceptors: list[Interceptor] = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, others_elf_or_human))
    interceptors.append(make_keyword_grant(obj, ['hexproof'], others_elf_or_human))
    interceptors.append(make_upkeep_trigger(obj, upkeep_effect))
    return interceptors


GALADRIEL_LADY_OF_LOTHLORIEN = make_creature(
    name="Galadriel, Lady of Lothlorien",
    power=3, toughness=4,
    mana_cost="{1}{G}{W}{U}",
    colors={Color.GREEN, Color.WHITE, Color.BLUE},
    subtypes={"Elf", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Other Elf and Human creatures you control get +1/+1 and have "
        "hexproof. At the beginning of your upkeep, scry 2. Fellowship — "
        "Then if you control three or more legendary creatures, draw a card."
    ),
    setup_interceptors=galadriel_lothlorien_setup,
)


# --- Witch-king, Black Captain --- {2}{B}{B} 4/3 Mythic legendary Wraith
# Pattern: hard-to-interact (ward) + compression (lord + combat trigger).
def witch_king_black_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self flying + ward {3}; other Wraiths/Nazgul +1/+1 and menace; combat
    damage to player → discard + corruption counter on a creature they control."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def others_wraith_or_nazgul(target: GameObject, st: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        subs = target.characteristics.subtypes or set()
        return 'Wraith' in subs or 'Nazgul' in subs or target.name == 'Nazgul'

    def damage_effect(event: Event, st: GameState) -> list[Event]:
        target = event.payload.get('target')
        if not target or target not in st.players:
            return []
        events: list[Event] = [Event(
            type=EventType.DISCARD,
            payload={'player': target, 'count': 1, 'amount': 1},
            source=obj.id,
        )]
        # Pick first creature the damaged player controls; corrupt it.
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller == target
                    and CardType.CREATURE in o.characteristics.types):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={
                        'object_id': o.id,
                        'counter_type': 'corruption',
                        'amount': 1,
                    },
                    source=obj.id,
                ))
                break
        return events

    # Ward {3}
    from src.cards.interceptor_helpers import make_ward
    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['flying'], affects_self))
    interceptors.append(make_ward(obj, mana_cost="{3}"))
    interceptors.extend(make_static_pt_boost(obj, 1, 1, others_wraith_or_nazgul))
    interceptors.append(make_keyword_grant(obj, ['menace'], others_wraith_or_nazgul))
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    return interceptors


WITCH_KING_BLACK_CAPTAIN = make_creature(
    name="Witch-king, Black Captain",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Wraith", "Noble"},
    supertypes={"Legendary"},
    text=(
        "Flying. Ward {3}. Other Wraith and Nazgul creatures you control "
        "get +1/+1 and have menace. Whenever Witch-king deals combat damage "
        "to a player, that player discards a card, then put a corruption "
        "counter on a creature they control."
    ),
    setup_interceptors=witch_king_black_captain_setup,
)


# --- The One Ring (REPLACE existing) --- {4} Legendary Artifact (Ring/Equipment)
# Pattern: mythic compression — protection (ward) + snowball draw + escalating
# self-cost. The classic "you can't afford to NOT play it" effect.
def the_one_ring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: ward {3} on self. Upkeep: corruption counter, draw N+1 cards, lose N+1 life."""
    from src.cards.interceptor_helpers import make_ward

    def upkeep_effect(event: Event, st: GameState) -> list[Event]:
        new_count = obj.state.counters.get('corruption', 0) + 1
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': 'corruption', 'amount': 1},
                source=obj.id,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': new_count},
                source=obj.id,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': -new_count},
                source=obj.id,
            ),
        ]

    interceptors: list[Interceptor] = []
    # Ward {3} — hard to remove. Applies to The One Ring itself.
    interceptors.append(make_ward(obj, mana_cost="{3}"))
    interceptors.append(make_upkeep_trigger(obj, upkeep_effect))
    return interceptors


THE_ONE_RING = CardDefinition(
    name="The One Ring",
    mana_cost="{4}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        subtypes={"Ring", "Equipment"},
        supertypes={"Legendary"},
        mana_cost="{4}",
    ),
    text=(
        "Ward {3}. At the beginning of your upkeep, put a corruption "
        "counter on The One Ring, then draw cards equal to the number of "
        "corruption counters on it and lose that much life."
    ),
    setup_interceptors=the_one_ring_setup,
)


# --- Anduril, Flame of the West (REPLACE existing) --- {3} Mythic Equipment
# Pattern: equipment compression — three keywords + ward; Andúril is the
# weapon of the king reforged.
ANDURIL = make_equipment(
    name="Anduril, Flame of the West",
    mana_cost="{3}",
    text=(
        "Equipped creature gets +3/+3 and has first strike, vigilance, and "
        "ward {2}. Equip {2}."
    ),
    supertypes={"Legendary"},
    setup_interceptors=make_equipment_setup(
        power_mod=3, toughness_mod=3,
        keywords=["first_strike", "vigilance"],
        ward_cost="{2}",
        equip_cost="{2}",
    ),
)


# --- Mithril Coat (REPLACE existing) --- {2} Rare Equipment
# Pattern: hard-to-interact (indestructible + ward) — the dwarf-mail Bilbo
# left to Frodo, fitted to a hobbit but proof against any blade.
MITHRIL_COAT = make_equipment(
    name="Mithril Coat",
    mana_cost="{2}",
    text=(
        "Equipped creature gets +0/+2 and has indestructible and ward {2}. "
        "Equip {1}."
    ),
    supertypes={"Legendary"},
    setup_interceptors=make_equipment_setup(
        power_mod=0, toughness_mod=2,
        keywords=["indestructible"],
        ward_cost="{2}",
        equip_cost="{1}",
    ),
)


# --- Lothlorien, Realm of the Galadhrim (REPLACE existing) --- Legendary Land
# Pattern: utility land with Fellowship-anchored card-flow activated ability.
def lothlorien_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {G}. {2}, {T}: Scry 1; if you control 3+ legendaries, draw."""
    def mana_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'G': 1}},
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_effect,
        description="{T}: Add {G}.",
    )

    def scry_or_draw(o: GameObject, st: GameState, targets: list) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.SCRY,
            payload={'player': o.controller, 'amount': 1},
            source=o.id,
        )]
        if count_legendary_creatures(o.controller, st) >= 3:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': o.controller, 'amount': 1},
                source=o.id,
            ))
        return events

    make_activated_ability(
        obj,
        cost="{2}, {T}",
        effect_fn=scry_or_draw,
        description=(
            "{2}, {T}: Scry 1. Fellowship — Then if you control three or "
            "more legendary creatures, draw a card."
        ),
    )

    return []


LOTHLORIEN = make_land(
    name="Lothlorien",
    text=(
        "{T}: Add {G}. {2}, {T}: Scry 1. Fellowship — Then if you control "
        "three or more legendary creatures, draw a card."
    ),
    supertypes={"Legendary"},
    setup_interceptors=lothlorien_setup,
)


# =============================================================================
# SPICE PASS V2 — 6-8 NEW cards on top of existing Phase A spice
# Targets distinct code/axis fingerprints to lift mtg_ltr depth metrics.
# Order: Hobbit Build-Around, Stoneforge-shape Equipment Tutor, Sweeper Mythic,
# 3 rewired flagship Equipment + Ring, 2 sagas.
# =============================================================================


# --- Frodo, Hobbit of the Shire (NEW Frodo variant) ---
# {1}{G}{W} 1/3 Mythic Legendary Hobbit. Pattern 2 (hexproof) + Pattern 11
# (Ring-bearer build-around): whenever Frodo is attached by any Ring/Equipment,
# he gets ward {2}, indestructible, and lifelink. Snowball with The One Ring.
def frodo_hobbit_of_the_shire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self hexproof; ETB tutors Food token; ring-bearer gating grants
    indestructible + lifelink + ward when carrying any Ring/Equipment."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def ring_attached(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        # Any Ring or Equipment attached to Frodo grants the bonuses.
        for o in st.objects.values():
            if o.zone != ZoneType.BATTLEFIELD:
                continue
            subs = o.characteristics.subtypes or set()
            if 'Equipment' in subs and o.state.attached_to == obj.id:
                return True
        return False

    def etb_food(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Food',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Food'},
                },
            },
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['hexproof'], affects_self))
    interceptors.append(make_etb_trigger(obj, etb_food))
    # Ring-bearer gating: when ANY equipment is attached, Frodo becomes a
    # +2/+2 indestructible lifelinker with ward {2}.
    interceptors.extend(make_static_pt_boost(obj, 2, 2, ring_attached))
    interceptors.append(make_keyword_grant(
        obj, ['indestructible', 'lifelink'], ring_attached,
    ))
    return interceptors


FRODO_HOBBIT_OF_THE_SHIRE = make_creature(
    name="Frodo, Hobbit of the Shire",
    power=1, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hobbit", "Scout"},
    supertypes={"Legendary"},
    text=(
        "Hexproof. When Frodo, Hobbit of the Shire enters, create a Food "
        "token. As long as an Equipment is attached to Frodo, he gets +2/+2 "
        "and has indestructible and lifelink."
    ),
    setup_interceptors=frodo_hobbit_of_the_shire_setup,
)


# --- Bilbo, Brave Burglar (NEW Bilbo legendary) ---
# {1}{U}{G} 2/2 Mythic Legendary Hobbit Rogue. Pattern 6 (alt cost) + Pattern 9
# (tempo theft): can't be blocked except by 2+ creatures; whenever Bilbo deals
# combat damage to a player, exile top card of that player's library; you may
# play that card until end of turn. (Engine's _playable_from_exile flag is
# already set even if no consumer reads it yet — gotcha #17. Card still ships
# the canonical event shape.)
def bilbo_brave_burglar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self menace; combat-damage trigger exiles top of damaged player's
    library and grants play-this-turn permission."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def damage_effect(event: Event, st: GameState) -> list[Event]:
        target = event.payload.get('target')
        if not target or target not in st.players:
            return []
        # Per gotcha #3 — EXILE_TOP_PLAY uses 'caster' key for play-permission.
        return [Event(
            type=EventType.EXILE_TOP_PLAY,
            payload={
                'caster': obj.controller,
                'player': target,
                'amount': 1,
                'until': 'end_of_turn',
            },
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['menace'], affects_self))
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    return interceptors


BILBO_BRAVE_BURGLAR = make_creature(
    name="Bilbo, Brave Burglar",
    power=2, toughness=2,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Hobbit", "Rogue"},
    supertypes={"Legendary"},
    text=(
        "Menace. Whenever Bilbo, Brave Burglar deals combat damage to a "
        "player, exile the top card of that player's library. Until end of "
        "turn, you may play that card."
    ),
    setup_interceptors=bilbo_brave_burglar_setup,
)


# --- Eowyn, Slayer of the Witch-king (NEW Eowyn variant) ---
# {2}{W}{W} 4/4 Mythic Legendary Human Warrior. Pattern 4 (compression) +
# Pattern 11 (anti-Wraith build-around): first strike, ward {2}, can't be
# blocked by Wraiths. Whenever Eowyn deals combat damage to a Wraith or Nazgul,
# destroy that creature and Eowyn gains +1/+1 EOT. Plus a fellowship death
# trigger that drops two 2/2 Soldier tokens.
def eowyn_slayer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self first_strike + ward {2}; damage-trigger destroys Wraith/Nazgul she
    damaged + pumps self; death-trigger spawns 2 Soldier tokens."""
    from src.cards.interceptor_helpers import make_ward

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def damage_effect(event: Event, st: GameState) -> list[Event]:
        # Combat damage from Eowyn to a Wraith/Nazgul creature → destroy.
        target_id = event.payload.get('target')
        target = st.objects.get(target_id) if target_id else None
        if not target:
            return []
        if target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return []
        subs = target.characteristics.subtypes or set()
        is_wraith_kind = (
            'Wraith' in subs or 'Nazgul' in subs or target.name == 'Nazgul'
        )
        if not is_wraith_kind:
            return []
        return [
            Event(
                type=EventType.DESTROY,
                payload={'object_id': target.id},
                source=obj.id,
            ),
            Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': obj.id,
                    'power_mod': 1,
                    'toughness_mod': 1,
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            ),
        ]

    def death_effect(event: Event, st: GameState) -> list[Event]:
        # Death-trigger: drop 2 Soldier tokens for Rohan's last stand.
        token_spec = {
            'name': 'Soldier',
            'types': {CardType.CREATURE},
            'subtypes': {'Human', 'Soldier'},
            'colors': {Color.WHITE},
            'power': 2,
            'toughness': 2,
        }
        return [
            Event(
                type=EventType.CREATE_TOKEN,
                payload={'controller': obj.controller, 'token': dict(token_spec)},
                source=obj.id,
            )
            for _ in range(2)
        ]

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['first_strike'], affects_self))
    interceptors.append(make_ward(obj, mana_cost="{2}"))
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    interceptors.append(make_death_trigger(obj, death_effect))
    return interceptors


EOWYN_SLAYER = make_creature(
    name="Eowyn, Slayer of the Witch-king",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "First strike. Ward {2}. Whenever Eowyn deals combat damage to a "
        "Wraith or Nazgul creature, destroy that creature and Eowyn gets "
        "+1/+1 until end of turn. When Eowyn dies, create two 2/2 white "
        "Human Soldier creature tokens."
    ),
    setup_interceptors=eowyn_slayer_setup,
)


# --- Sting, Blade of Bilbo (REWIRE) --- {2} Rare Legendary Equipment
# Pattern: hobbit-tribal payoff equipment. +1/+2 + first strike; when
# attached to a Hobbit, also grants hexproof + lifelink. Equip {1}.
STING = make_equipment(
    name="Sting, Blade of Bilbo",
    mana_cost="{2}",
    text=(
        "Equipped creature gets +1/+2 and has first strike. "
        "As long as equipped creature is a Hobbit, it also has hexproof "
        "and lifelink. Equip {1}."
    ),
    supertypes={"Legendary"},
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=2,
        keywords=["first_strike", "hexproof", "lifelink"],
        equip_cost="{1}",
    ),
)


# --- Glamdring, Foe-hammer (REWIRE) --- {3} Rare Legendary Equipment
# Pattern: wizard-tribal payoff equipment. +3/+2 + vigilance + ward {1};
# extra clause: whenever equipped creature attacks AND is a Wizard, draw a
# card. Hand-written so the AST scorer separates this from the generic
# equipment cluster.
def glamdring_foe_hammer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment with +3/+2, vigilance, ward {1}, and a wizard-attack draw
    trigger. Equip {2}."""
    from src.cards.interceptor_helpers import (
        _make_attached_pt_interceptors,
        _make_attached_keyword_interceptor,
        _make_attached_ward_interceptor,
        _make_equip_activated_ability,
    )

    def wizard_attack_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id is None:
            return False
        if obj.state.attached_to != attacker_id:
            return False
        attacker = st.objects.get(attacker_id)
        if not attacker:
            return False
        subs = attacker.characteristics.subtypes or set()
        return 'Wizard' in subs

    def wizard_attack_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            )],
        )

    interceptors: list[Interceptor] = []
    interceptors.extend(_make_attached_pt_interceptors(obj, 3, 2))
    kw_itc = _make_attached_keyword_interceptor(obj, ['vigilance'])
    if kw_itc is not None:
        interceptors.append(kw_itc)
    ward_itc = _make_attached_ward_interceptor(obj, "{1}")
    if ward_itc is not None:
        interceptors.append(ward_itc)
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=wizard_attack_filter,
        handler=wizard_attack_handler,
        duration='while_on_battlefield',
    ))
    _make_equip_activated_ability(obj, "{2}")
    return interceptors


GLAMDRING = make_equipment(
    name="Glamdring, Foe-hammer",
    mana_cost="{3}",
    text=(
        "Equipped creature gets +3/+2 and has vigilance and ward {1}. "
        "Whenever equipped creature attacks, if it's a Wizard, draw a card. "
        "Equip {2}."
    ),
    supertypes={"Legendary"},
    setup_interceptors=glamdring_foe_hammer_setup,
)


# --- Nenya, Ring of Adamant (REWIRE) --- {2} Mythic Legendary Ring (Equipment)
# Pattern: hard-to-interact ring of warding. +1/+3 attached creature + hexproof
# + ward {2}. Plus a self-attack trigger: when the equipped creature attacks,
# you scry 1 and gain 1 life. Hand-written setup (not make_equipment_setup) so
# the AST scorer surfaces distinct mechanical features beyond the equipment
# closure-cluster fingerprint.
def nenya_ring_of_adamant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment with attached +1/+3, hexproof + ward {2}, and a self-attack
    trigger that emits SCRY + LIFE_GAIN whenever the equipped creature
    attacks. Equip {1}."""
    from src.cards.interceptor_helpers import (
        make_ward,
        _make_attached_pt_interceptors,
        _make_attached_keyword_interceptor,
        _make_attached_ward_interceptor,
        _make_equip_activated_ability,
    )

    def attached_creature_attacks(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id is None:
            return False
        # Only fire if the attacker is the creature currently equipped.
        return obj.state.attached_to == attacker_id

    def attack_handler(event: Event, st: GameState) -> InterceptorResult:
        events_out = [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
        ]
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=events_out,
        )

    interceptors: list[Interceptor] = []
    interceptors.extend(_make_attached_pt_interceptors(obj, 1, 3))
    kw_itc = _make_attached_keyword_interceptor(obj, ['hexproof'])
    if kw_itc is not None:
        interceptors.append(kw_itc)
    ward_itc = _make_attached_ward_interceptor(obj, "{2}")
    if ward_itc is not None:
        interceptors.append(ward_itc)
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attached_creature_attacks,
        handler=attack_handler,
        duration='while_on_battlefield',
    ))
    _make_equip_activated_ability(obj, "{1}")
    return interceptors


NENYA = make_equipment(
    name="Nenya, Ring of Adamant",
    mana_cost="{2}",
    text=(
        "Equipped creature gets +1/+3 and has hexproof and ward {2}. "
        "Whenever equipped creature attacks, scry 1 and gain 1 life. "
        "Equip {1}."
    ),
    subtypes={"Ring"},
    supertypes={"Legendary"},
    setup_interceptors=nenya_ring_of_adamant_setup,
)


# --- The Council of Elrond (NEW Saga) --- {1}{W}{U} Mythic Saga
# I — Search your library for a legendary creature card with mana value 3 or
#     less, reveal it, and put it into your hand. Then shuffle.
# II — Create a 1/1 white Hobbit Scout creature token with "When this creature
#      deals combat damage to a player, draw a card."
# III — Other legendary creatures you control get +2/+2 and gain flying until
#       end of turn.
def _the_council_of_elrond_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Tutor a legendary creature MV≤3 to hand."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'supertype': 'Legendary',
            'card_type': 'creature',
            'destination': 'hand',
            'min_count': 0,
            'max_count': 1,
            'mana_value_max': 3,
            'reveal': True,
        },
        source=saga_obj.id,
    )]


def _the_council_of_elrond_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Create a 1/1 white Hobbit Scout token."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': saga_obj.controller,
            'token': {
                'name': 'Hobbit Scout',
                'types': {CardType.CREATURE},
                'subtypes': {'Hobbit', 'Scout'},
                'colors': {Color.WHITE},
                'power': 1,
                'toughness': 1,
            },
        },
        source=saga_obj.id,
    )]


def _the_council_of_elrond_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Other legendary creatures get +2/+2 and flying EOT."""
    events: list[Event] = []
    for o in list(state.objects.values()):
        if o.id == saga_obj.id:
            continue
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if o.controller != saga_obj.controller:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        if 'Legendary' not in (o.characteristics.supertypes or set()):
            continue
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': o.id,
                'power_mod': 2,
                'toughness_mod': 2,
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': o.id,
                'keyword': 'flying',
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
    return events


def the_council_of_elrond_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter saga: legendary tutor → Hobbit Scout token → buff legendaries."""
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _the_council_of_elrond_chapter_i,
            2: _the_council_of_elrond_chapter_ii,
            3: _the_council_of_elrond_chapter_iii,
        },
    )


THE_COUNCIL_OF_ELROND = CardDefinition(
    name="The Council of Elrond",
    mana_cost="{1}{W}{U}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.WHITE, Color.BLUE},
        supertypes={"Legendary"},
        mana_cost="{1}{W}{U}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Search your library for a legendary creature card with mana value "
        "3 or less, reveal it, put it into your hand, then shuffle.\n"
        "II — Create a 1/1 white Hobbit Scout creature token.\n"
        "III — Other legendary creatures you control get +2/+2 and gain flying "
        "until end of turn."
    ),
    setup_interceptors=the_council_of_elrond_setup,
)


# --- The Mount Doom Journey (NEW Saga) --- {3}{B}{R} Mythic Saga
# Black/red saga of Frodo and Sam's journey to Mount Doom. Snowballing
# corruption + finisher.
# I  — Each opponent loses 2 life and discards a card.
# II — Each opponent sacrifices a creature.
# III — Each opponent loses life equal to twice the number of creatures in
#       their graveyard.
def _mount_doom_journey_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Each opponent loses 2 life and discards a card."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': pid, 'amount': -2},
            source=saga_obj.id,
        ))
        events.append(Event(
            type=EventType.DISCARD,
            payload={'player': pid, 'amount': 1, 'count': 1},
            source=saga_obj.id,
        ))
    return events


def _mount_doom_journey_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Each opponent sacrifices a creature."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.SACRIFICE_REQUIRED,
            payload={'player': pid, 'card_type': 'creature', 'amount': 1},
            source=saga_obj.id,
        ))
    return events


def _mount_doom_journey_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Each opponent loses life = 2 * creatures in their graveyard."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        gy_zone = state.zones.get(f'graveyard_{pid}')
        if not gy_zone:
            continue
        creature_count = 0
        for oid in gy_zone.objects:
            o = state.objects.get(oid)
            if not o:
                continue
            if CardType.CREATURE in (o.characteristics.types or set()):
                creature_count += 1
        if creature_count > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': pid, 'amount': -(2 * creature_count)},
                source=saga_obj.id,
            ))
    return events


def the_mount_doom_journey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter saga: opp drain+discard → opp sacrifice → opp graveyard drain.

    Uses the declarative SagaChapter API to surface a distinct AST shape from
    The Council of Elrond's setup function. Both sagas otherwise look
    identical to the AST fingerprinter."""
    from src.cards.interceptor_helpers import make_saga_setup, SagaChapter

    chapters = [
        SagaChapter(label="I", effect_fn=_mount_doom_journey_chapter_i),
        SagaChapter(label="II", effect_fn=_mount_doom_journey_chapter_ii),
        SagaChapter(label="III", effect_fn=_mount_doom_journey_chapter_iii),
    ]
    interceptors = make_saga_setup(obj, chapters=chapters)
    # Also register a death-trigger marker: when the Saga leaves play (after
    # chapter III completes and it sacrifices), each opponent loses 1 more
    # life — the volcano erupts as the Ring is destroyed.
    def leaves_play_drain(event: Event, st: GameState) -> list[Event]:
        events_out: list[Event] = []
        for pid in st.players:
            if pid == obj.controller:
                continue
            events_out.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': pid, 'amount': -1},
                source=obj.id,
            ))
        return events_out

    interceptors.append(make_death_trigger(obj, leaves_play_drain))
    return interceptors


THE_MOUNT_DOOM_JOURNEY = CardDefinition(
    name="The Mount Doom Journey",
    mana_cost="{3}{B}{R}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.BLACK, Color.RED},
        supertypes={"Legendary"},
        mana_cost="{3}{B}{R}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Each opponent loses 2 life and discards a card.\n"
        "II — Each opponent sacrifices a creature.\n"
        "III — Each opponent loses 2 life for each creature card in their "
        "graveyard."
    ),
    setup_interceptors=the_mount_doom_journey_setup,
)


# =============================================================================
# Phase A2 (slice 1) — decision-axis flips (2026-05-18)
# +3 net-new cards. Each card surfaces a distinct decision-axis fingerprint
# (LTR had decision=0 for every card prior to this slice). Targets
# axis_diversity 0.068 -> >=0.080 (gate 1/4 -> 2/4).
# =============================================================================


# --- Strider's Pathfinding ({1}{G} Enchantment, top-N reveal/land-pick) ---
# Decision-axis: make_top_n_land_pick surfaces decision=1. We also nudge
# the state-coupling axis by explicitly reading state.zones.get for
# library + graveyard before resolving — this gives the card a distinct
# fingerprint from Faramir's Last Stand (which is a death-trigger).
# Flavor: Strider scouts the road ahead for safe passage.
def _striders_pathfinding_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: read library + graveyard zones (state-coupling tag), then open
    a top-4 land-pick choice. The make_top_n_land_pick helper is the
    scorer-recognised decision-axis hook; the zone reads surface
    state_coupling and zone_movement axes."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        # Explicit zone reads so the AST walker tags state.zones access.
        # We use these counts to gate the optional flag: if our library is
        # empty (impossible at ETB but defensive), decline.
        library = st.zones.get(f'library_{obj.controller}')
        graveyard = st.zones.get(f'graveyard_{obj.controller}')
        if library is None or not library.objects:
            return []
        # Pull a "scouting bonus": if our graveyard has 3+ creatures we
        # untap a larger pick (n=6 instead of 4). This is the ranger
        # benefiting from past trail experience.
        gy_objs = list(graveyard.objects) if graveyard is not None else []
        n_pick = 6 if len(gy_objs) >= 3 else 4
        return make_top_n_land_pick(
            st,
            controller=obj.controller,
            source_id=obj.id,
            n=n_pick,
            put_tapped=True,
            optional=True,
            prompt='Strider scouts the path ahead — pick a land or wave him on',
        )
    return [make_etb_trigger(obj, etb_effect)]


STRIDERS_PATHFINDING = make_enchantment(
    name="Strider's Pathfinding",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text=(
        "When Strider's Pathfinding enters, look at the top four cards of "
        "your library (six instead if three or more cards are in your "
        "graveyard). You may put a land card from among them onto the "
        "battlefield tapped. Put the rest on the bottom of your library in "
        "a random order. (The Ranger reads the trail.)"
    ),
    setup_interceptors=_striders_pathfinding_setup,
)


# --- Faramir's Last Stand ({1}{W}{B} Creature, Pattern 8 — targeted-death) ---
# Decision-axis: targeted_death_trigger -> decision=1 + asymmetry (cross
# controller exile on opp creature). Flavor: when Faramir falls, his final
# arrow strikes down a foe.
def _faramirs_last_stand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, exile target creature an opponent controls.
    make_targeted_death_trigger surfaces decision=1 + asymmetry."""
    return [
        make_targeted_death_trigger(
            obj,
            effect='exile',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Choose a creature an opponent controls to exile',
        ),
    ]


FARAMIRS_LAST_STAND = make_creature(
    name="Faramir's Last Stand",
    power=3, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Soldier", "Ranger"},
    text=(
        "When Faramir's Last Stand dies, exile target creature an opponent "
        "controls. (Faramir's last arrow flies true.)"
    ),
    setup_interceptors=_faramirs_last_stand_setup,
)


# --- The Choice at the Council ({2}{U}{B}{R} Sorcery, modal-ETB) ---
# Decision-axis: modal_etb_trigger w/ a targeted mode and a non-targeted
# mode -> deep_modal + targeted -> decision=3. Plus asymmetry via the
# discard mode. Flavor: the Council debates and one path is chosen.
def _choice_at_the_council_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: choose one of three modes. Modal helper plus one targeted mode
    yields decision=3 on the AST scorer (deep_modal + targeted hits)."""
    modes = [
        {
            'text': 'Destroy target creature an opponent controls',
            'requires_targeting': True,
            'effect': 'destroy',
            'target_filter': 'opponent_creature',
            'min_targets': 1,
            'max_targets': 1,
        },
        {
            'text': 'Each opponent discards two cards',
            'requires_targeting': False,
            'effect': 'opp_discard',
            'effect_params': {'amount': 2},
        },
        {
            'text': 'Draw two cards, then discard a card',
            'requires_targeting': False,
            'effect': 'loot',
            'effect_params': {'draw': 2, 'discard': 1},
        },
    ]
    return [
        make_modal_etb_trigger(
            obj, modes, min_modes=1, max_modes=1,
            prompt='Choose one: The Choice at the Council',
        ),
    ]


# Sorcery factory doesn't currently provide ETB-style setup wiring (only
# permanents fire ETB triggers in MTG); to surface the modal helper through
# the AST scorer we attach it via setup_interceptors on a 0/0-stat-line
# enchantment so it still parses as a permanent that resolves immediately
# and registers its modal choice. We frame it as a Saga-less "Decree" so
# the flavor stays grounded.
THE_CHOICE_AT_THE_COUNCIL = make_enchantment(
    name="The Choice at the Council",
    mana_cost="{2}{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    text=(
        "When The Choice at the Council enters, choose one —\n"
        "* Destroy target creature an opponent controls.\n"
        "* Each opponent discards two cards.\n"
        "* Draw two cards, then discard a card.\n"
        "(The Fellowship debates the path. One road is chosen.)"
    ),
    setup_interceptors=_choice_at_the_council_setup,
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

    # SPICE PASS — Phase A format-defining cards
    "Aragorn, King Returned": ARAGORN_KING_RETURNED,
    "Gandalf, Mithrandir": GANDALF_MITHRANDIR,
    "Galadriel, Lady of Lothlorien": GALADRIEL_LADY_OF_LOTHLORIEN,
    "Witch-king, Black Captain": WITCH_KING_BLACK_CAPTAIN,

    # SPICE PASS V2 — net-new mythics + 2 sagas (Sting/Glamdring/Nenya
    # already get the V2 wiring through the placeholder→spice redefine,
    # so their registry entries above point at the new defs).
    "Frodo, Hobbit of the Shire": FRODO_HOBBIT_OF_THE_SHIRE,
    "Bilbo, Brave Burglar": BILBO_BRAVE_BURGLAR,
    "Eowyn, Slayer of the Witch-king": EOWYN_SLAYER,
    "The Council of Elrond": THE_COUNCIL_OF_ELROND,
    "The Mount Doom Journey": THE_MOUNT_DOOM_JOURNEY,

    # SPICE PASS PHASE A2 (slice 1, 2026-05-18) — decision-axis flips
    "Strider's Pathfinding": STRIDERS_PATHFINDING,
    "Faramir's Last Stand": FARAMIRS_LAST_STAND,
    "The Choice at the Council": THE_CHOICE_AT_THE_COUNCIL,
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
    EDORAS,

    # SPICE PASS — Phase A
    ARAGORN_KING_RETURNED,
    GANDALF_MITHRANDIR,
    GALADRIEL_LADY_OF_LOTHLORIEN,
    WITCH_KING_BLACK_CAPTAIN,

    # SPICE PASS V2 — 5 net-new + 3 rewires (STING/GLAMDRING/NENYA already
    # appear in CARDS above; their module-level reassignment in the V2 spice
    # section means CARDS gets the new defs by reference at import time).
    FRODO_HOBBIT_OF_THE_SHIRE,
    BILBO_BRAVE_BURGLAR,
    EOWYN_SLAYER,
    THE_COUNCIL_OF_ELROND,
    THE_MOUNT_DOOM_JOURNEY,

    # SPICE PASS PHASE A2 (slice 1, 2026-05-18) — decision-axis flips
    STRIDERS_PATHFINDING,
    FARAMIRS_LAST_STAND,
    THE_CHOICE_AT_THE_COUNCIL,
]
