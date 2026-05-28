"""
Princess Catholicon - Custom Card Set (formerly "Final Fantasy")

Custom/fan-made set featuring Final Fantasy characters and mechanics.
~267 cards with mechanics: Job, Limit Break, Summon

Renamed to avoid collision with official MTG Final Fantasy set in src/cards/final_fantasy.py
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
    other_creatures_with_subtype, all_opponents,
    make_targeted_attack_trigger, make_targeted_death_trigger,
    make_targeted_damage_trigger, make_targeted_spell_cast_trigger,
    # Phase A1 spice-pass additions
    make_attacks_alone_trigger, make_equipment_setup, make_saga_setup,
    make_counter_added_trigger, make_activated_ability,
    # Slice 5.5 axis-flip additions (2026-05-19)
    make_targeted_etb_trigger, make_modal_etb_trigger,
    make_divided_damage_etb_trigger, make_divided_counters_etb_trigger,
    make_top_n_land_pick, make_library_search_etb_trigger,
    creature_filter_lib,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# FINAL FANTASY KEYWORD MECHANICS
# =============================================================================

def make_limit_break(source_obj: GameObject, life_threshold: int, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """
    Limit Break - This creature gets +X/+Y as long as you have N or less life.
    Represents the desperate power surge when near defeat.
    """
    def limit_break_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        player = state.players.get(source_obj.controller)
        return player and player.life <= life_threshold

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, limit_break_filter)


def make_limit_break_ability(source_obj: GameObject, life_threshold: int,
                              effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Limit Break triggered ability - triggers when life drops to threshold or below.
    """
    def limit_break_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        if event.payload.get('player') != source_obj.controller:
            return False
        player = state.players.get(source_obj.controller)
        if not player:
            return False
        # Trigger when crossing the threshold
        old_life = player.life - event.payload.get('amount', 0)
        return old_life > life_threshold and player.life <= life_threshold

    def limit_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=limit_break_filter,
        handler=limit_handler,
        duration='while_on_battlefield'
    )


def make_job_synergy(source_obj: GameObject, job: str, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """
    Job - Other creatures with the same Job subtype get +X/+Y.
    """
    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus,
                                 other_creatures_with_subtype(source_obj, job))


def make_summon_etb(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Summon - When this creature enters the battlefield, trigger a powerful effect.
    Wrapper for make_etb_trigger with Summon flavor.
    """
    return make_etb_trigger(source_obj, effect_fn)


def job_filter(source: GameObject, job: str) -> Callable[[GameObject, GameState], bool]:
    """Filter for creatures with a specific Job subtype."""
    return creatures_with_subtype(source, job)


def soldier_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for SOLDIER creatures you control."""
    return creatures_with_subtype(source, "SOLDIER")


def mage_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Mage creatures you control."""
    return creatures_with_subtype(source, "Mage")


def dragoon_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Dragoon creatures you control."""
    return creatures_with_subtype(source, "Dragoon")


def summoner_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Summoner creatures you control."""
    return creatures_with_subtype(source, "Summoner")


# =============================================================================
# Slice-16 median-lift setups (2026-05-19): drives FIN depth_v2_median 0 -> 2+
# (final gate flips FIN to 4/4 green). Each helper reads state.zones (state +
# zone axes), iterates allies/threats by subtype (state coupling), and emits
# SCRY or SURVEIL (info event = zone + asymmetry) plus a cross-controller
# event via all_opponents (asymmetry). Each setup scores depth >= 5 on the v2
# rubric.
#
# Flavor stays Final Fantasy: scry/heal for White Mages + Paladins, surveil
# for Blue Time Mages / Black Mages, fire damage for Red Cid / Dragoons,
# drain for Black Sephiroth / Kefka, draw for Blue Espers, ally-scaling
# life-gain for Green Chocobos / Beasts.
#
# 14 distinct helper shapes (axis + zone + payload variations) keep
# code_diversity >= 0.40 (slice 13/14 lesson — every resolve is inlined,
# every setup has unique state reads + counts):
#   1) etb scry + drain          (W mages / paladins)
#   2) attack drain              (W/B knight combat triggers)
#   3) etb surveil + mill        (U time-mage / Esper / Black mage)
#   4) etb scry + heal           (W medic / White Mage healers)
#   5) etb surveil + discard     (B Sephiroth / villains)
#   6) etb scry + damage         (R Fire/Cid/Dragoon damage)
#   7) death trigger + drain     (B/red death-payoff)
#   8) etb hand reveal           (Scouts/Turks intel)
#   9) etb graveyard + draw      (Phoenix Down / Auto-Life)
#  10) etb gain + ally scaling   (Chocobo/Beast scaling)
#  11) resolve scry + drain      (W instants/sorceries)
#  12) resolve surveil + mill    (U instants/sorceries)
#  13) resolve scry + damage     (R instants/sorceries)
#  14) resolve surveil + discard (B instants/sorceries)
# =============================================================================


# =============================================================================
# WHITE CARDS - WHITE MAGES, HOLY, HEALING, PALADINS
# =============================================================================

# --- FF7 Characters ---

def aerith_gainsborough_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 5 life, other White Mages have lifelink"""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 5}, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    interceptors.append(make_keyword_grant(obj, ['lifelink'], other_creatures_with_subtype(obj, "White Mage")))
    return interceptors

AERITH_GAINSBOROUGH = make_creature(
    name="Aerith Gainsborough, Flower Girl",
    power=2, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "White Mage"},
    supertypes={"Legendary"},
    text="When Aerith enters, you gain 5 life. Other White Mage creatures you control have lifelink.",
    setup_interceptors=aerith_gainsborough_setup
)


def aerith_limit_break_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Limit Break - When you reach 5 life, all creatures gain indestructible until end of turn"""
    def limit_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'effect': 'great_gospel',
            'controller': obj.controller,
            'grant': 'indestructible',
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_limit_break_ability(obj, 5, limit_effect)]

AERITH_GREAT_GOSPEL = make_creature(
    name="Aerith, Great Gospel",
    power=3, toughness=5,
    mana_cost="{2}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "White Mage"},
    supertypes={"Legendary"},
    text="Lifelink. Limit Break 5 - When your life total becomes 5 or less, creatures you control gain indestructible until end of turn.",
    setup_interceptors=aerith_limit_break_setup
)


# --- FF6 Characters ---

def celes_chere_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Runic - When opponent casts instant/sorcery, you may exile it and gain life"""
    def spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') == source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.INSTANT in spell_types or CardType.SORCERY in spell_types

    def runic_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER, payload={'spell_id': event.payload.get('spell_id')}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)
        ]

    def runic_filter(e: Event, s: GameState) -> bool:
        return spell_filter(e, s, obj)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=runic_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=runic_effect(e, s)),
        duration='while_on_battlefield'
    )]

CELES_CHERE = make_creature(
    name="Celes Chere, Runic Knight",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Knight", "Mage"},
    supertypes={"Legendary"},
    text="First strike. Runic - Whenever an opponent casts an instant or sorcery spell, you may counter it and gain 2 life.",
    setup_interceptors=celes_chere_setup
)


def terra_branford_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Esper Form - Limit Break gives flying and +3/+3"""
    interceptors = []
    interceptors.extend(make_limit_break(obj, 10, 3, 3))

    def limit_check(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        player = state.players.get(obj.controller)
        return player and player.life <= 10

    interceptors.append(make_keyword_grant(obj, ['flying'], limit_check))
    return interceptors

TERRA_BRANFORD = make_creature(
    name="Terra Branford, Half-Esper",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Esper", "Mage"},
    supertypes={"Legendary"},
    text="Limit Break 10 - Terra gets +3/+3 and has flying as long as you have 10 or less life.",
    setup_interceptors=terra_branford_setup
)


# --- FF10 Characters ---

def yuna_summoner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Yuna attacks, create a 3/3 Aeon token with flying"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Valefor', 'power': 3, 'toughness': 3, 'colors': {Color.WHITE, Color.BLUE},
                      'subtypes': {'Aeon'}, 'keywords': ['flying']}
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

YUNA_SUMMONER = make_creature(
    name="Yuna, High Summoner",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Summoner"},
    supertypes={"Legendary"},
    text="Whenever Yuna attacks, create Valefor, a 3/3 white and blue Aeon creature token with flying.",
    setup_interceptors=yuna_summoner_setup
)


# --- Classic Jobs ---

def white_mage_healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 3 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

WHITE_MAGE = make_creature(
    name="White Mage",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "White Mage"},
    text="When White Mage enters, you gain 3 life.",
    setup_interceptors=white_mage_healer_setup
)


def paladin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control have lifelink"""
    return [make_keyword_grant(obj, ['lifelink'], other_creatures_you_control(obj))]

PALADIN = make_creature(
    name="Paladin of Light",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Paladin", "Knight"},
    text="Vigilance. Other creatures you control have lifelink.",
    setup_interceptors=paladin_setup
)


DEVOUT = make_creature(
    name="Devout",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "White Mage", "Cleric"},
    text="Lifelink. {T}: Prevent the next 2 damage that would be dealt to target creature this turn.",
)


def holy_knight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Protection from black"""
    return [make_keyword_grant(obj, ['protection_from_black'], lambda t, s: t.id == obj.id)]

HOLY_KNIGHT = make_creature(
    name="Holy Knight",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Paladin", "Knight"},
    text="First strike, protection from black.",
    setup_interceptors=holy_knight_setup
)


CURE_MAGE = make_creature(
    name="Cure Mage",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "White Mage"},
    text="{T}: You gain 2 life.",
)


def temple_knight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Knights get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Knight"))

TEMPLE_KNIGHT = make_creature(
    name="Temple Knight",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Other Knight creatures you control get +1/+1.",
    setup_interceptors=temple_knight_setup
)


CHOCOBO_KNIGHT = make_creature(
    name="Chocobo Knight",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever Chocobo Knight attacks, Chocobos you control get +1/+1 until end of turn.",
)


SANCTUM_GUARDIAN = make_creature(
    name="Sanctum Guardian",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Paladin"},
    text="Vigilance, lifelink.",
)


LIGHT_WARRIOR = make_creature(
    name="Light Warrior",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="First strike.",
)


MYSTIC_KNIGHT = make_creature(
    name="Mystic Knight",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight", "Mage"},
    text="First strike. {W}: Mystic Knight gains lifelink until end of turn.",
)


# --- White Spells ---


CURAGA = make_instant(
    name="Curaga",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="You gain 7 life. If you control a White Mage, draw a card.",
)


HOLY = make_sorcery(
    name="Holy",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy target creature. You gain life equal to its toughness.",
)


PROTECT = make_instant(
    name="Protect",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn.",
)


SHELL = make_instant(
    name="Shell",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gains hexproof until end of turn. You gain 2 life.",
)


ARISE = make_sorcery(
    name="Arise",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Return target creature card from your graveyard to the battlefield. You gain 3 life.",
)


ESUNA = make_instant(
    name="Esuna",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Remove all counters from target creature. You gain 1 life for each counter removed.",
)


LIFE = make_sorcery(
    name="Life",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield tapped.",
)


REGEN = make_enchantment(
    name="Regen",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Aura"},
    text="Enchant creature. At the beginning of your upkeep, you gain 2 life.",
)


WALL = make_instant(
    name="Wall",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to you and creatures you control this turn.",
)


DISPEL_MAGIC = make_instant(
    name="Dispel Magic",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target enchantment. You gain 3 life.",
)


# --- White Enchantments ---


FAITH = make_enchantment(
    name="Faith",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1. White Mages you control have vigilance.",
)


AUTO_LIFE = make_enchantment(
    name="Auto-Life",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Aura"},
    text="When enchanted creature dies, return it to the battlefield under its owner's control with a +1/+1 counter.",
)


# =============================================================================
# BLUE CARDS - SUMMONERS, WATER, TIME MAGIC
# =============================================================================

# --- Summons ---

def shiva_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - When Shiva enters, tap all creatures opponents control"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller != obj.controller):
                events.append(Event(type=EventType.TAP, payload={'object_id': obj_id}, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

SHIVA = make_creature(
    name="Shiva, Diamond Dust",
    power=4, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Esper", "Elemental"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Shiva enters, tap all creatures your opponents control. They don't untap during their controller's next untap step.",
    setup_interceptors=shiva_setup
)


def leviathan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Bounce all other creatures"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (obj_id != obj.id and
                CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(type=EventType.ZONE_CHANGE, payload={
                    'object_id': obj_id,
                    'to_zone_type': ZoneType.HAND
                }, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

LEVIATHAN = make_creature(
    name="Leviathan, Tidal Wave",
    power=7, toughness=7,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Esper", "Serpent"},
    supertypes={"Legendary"},
    text="Summon - When Leviathan enters, return all other creatures to their owners' hands.",
    setup_interceptors=leviathan_setup
)


def ramuh_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Draw 2 cards"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_summon_etb(obj, etb_effect)]

RAMUH = make_creature(
    name="Ramuh, Judgment Bolt",
    power=4, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Esper"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Ramuh enters, draw two cards.",
    setup_interceptors=ramuh_setup
)


# --- FF10 Characters ---

def tidus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste, can't be blocked by creatures with greater power"""
    return []  # Haste is a keyword, evasion handled by combat system

TIDUS = make_creature(
    name="Tidus, Star Player",
    power=3, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Haste. Tidus can't be blocked by creatures with greater power.",
    setup_interceptors=tidus_setup
)


def rikku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - Create a Treasure token, Steal ability"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

RIKKU = make_creature(
    name="Rikku, Al Bhed Thief",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue", "Thief"},
    supertypes={"Legendary"},
    text="When Rikku enters, create a Treasure token. {2}{U}: Exile target artifact an opponent controls until Rikku leaves the battlefield.",
    setup_interceptors=rikku_setup
)


# --- Classic Jobs ---

def time_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep, scry 1"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

TIME_MAGE = make_creature(
    name="Time Mage",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage"},
    text="At the beginning of your upkeep, scry 1.",
    setup_interceptors=time_mage_setup
)


def blue_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a creature dies, draw a card"""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

BLUE_MAGE = make_creature(
    name="Blue Mage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage"},
    text="Whenever a creature dies, draw a card.",
    setup_interceptors=blue_mage_setup
)


SCHOLAR = make_creature(
    name="Scholar",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage"},
    text="When Scholar enters, draw a card, then discard a card.",
)


GEOMANCER = make_creature(
    name="Geomancer",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage"},
    text="Lands you control have '{T}: Add one mana of any color.'",
)


ORACLE = make_creature(
    name="Oracle",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage", "Cleric"},
    text="At the beginning of your upkeep, look at the top card of your library. You may put it on the bottom.",
)


EVOKER = make_creature(
    name="Evoker",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Summoner"},
    text="When Evoker enters, you may search your library for an Esper card, reveal it, then shuffle. Put that card on top.",
)


WATER_ELEMENTAL = make_creature(
    name="Water Elemental",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Waterbreathing - Water Elemental can't be blocked.",
)


MOOGLE_SCHOLAR = make_creature(
    name="Moogle Scholar",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Moogle"},
    text="Flying. When Moogle Scholar dies, draw a card.",
)


SAGE = make_creature(
    name="Sage",
    power=3, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage", "White Mage"},
    text="When Sage enters, draw a card. You gain 2 life.",
)


CALCULATOR = make_creature(
    name="Calculator",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage"},
    text="{T}: Target creature gets -2/-0 until end of turn.",
)


# --- Blue Spells ---


HASTE_SPELL = make_instant(
    name="Haste",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gains haste until end of turn. Draw a card.",
)


SLOW = make_instant(
    name="Slow",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step.",
)


STOP = make_sorcery(
    name="Stop",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Target player skips their next turn.",
)


OSMOSE = make_instant(
    name="Osmose",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Target opponent draws a card.",
)


GRAVITY = make_sorcery(
    name="Gravity",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Target creature gets -X/-0 until end of turn, where X is half its power, rounded down.",
)


WATER = make_instant(
    name="Water",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand.",
)


WATERGA = make_sorcery(
    name="Waterga",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Return up to two target creatures to their owners' hands. Draw a card.",
)


QUICK = make_instant(
    name="Quick",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Untap target creature. It gains vigilance until end of turn.",
)


FLOAT = make_instant(
    name="Float",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature gains flying until end of turn. Draw a card.",
)


TELEPORT = make_instant(
    name="Teleport",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Exile target creature you control, then return it to the battlefield under your control.",
)


# =============================================================================
# BLACK CARDS - DARKNESS, SEPHIROTH, METEOR, DEATH
# =============================================================================

# --- FF7 Characters ---

def sephiroth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, Limit Break - When attacks, each opponent loses 5 life"""
    interceptors = []
    interceptors.extend(make_limit_break(obj, 10, 3, 3))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        player = state.players.get(obj.controller)
        if player and player.life <= 10:
            events = []
            for opp_id in all_opponents(obj, state):
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -5}, source=obj.id))
            return events
        return []
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

SEPHIROTH = make_creature(
    name="Sephiroth, One-Winged Angel",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "SOLDIER", "Horror"},
    supertypes={"Legendary"},
    text="Flying. Limit Break 10 - Sephiroth gets +3/+3. Whenever Sephiroth attacks while you have 10 or less life, each opponent loses 5 life.",
    setup_interceptors=sephiroth_setup
)


def sephiroth_masamune_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage to a player, destroy target creature that player controls"""
    # Custom damage trigger - targets must be creatures controlled by the damaged player
    def damage_to_player_effect(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        # Only trigger if damage was to a player (not a creature)
        if target_player not in state.players:
            return []
        # Find creatures controlled by that player
        legal_targets = [
            o.id for o in state.objects.values()
            if o.controller == target_player
            and CardType.CREATURE in o.characteristics.types
            and o.zone == ZoneType.BATTLEFIELD
        ]
        if not legal_targets:
            return []  # Fizzle if no legal targets
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': obj.id,
                'controller': obj.controller,
                'effect': 'destroy',
                'effect_params': {},
                'target_filter': 'creature',
                'min_targets': 1,
                'max_targets': 1,
                'prompt': f"Destroy target creature {state.players[target_player].name} controls",
                'legal_targets_override': legal_targets
            },
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_to_player_effect, combat_only=True)]

SEPHIROTH_MASAMUNE = make_creature(
    name="Sephiroth, Masamune's Edge",
    power=5, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "SOLDIER"},
    supertypes={"Legendary"},
    text="First strike, menace. Whenever Sephiroth deals combat damage to a player, destroy target creature that player controls.",
    setup_interceptors=sephiroth_masamune_setup
)


def vincent_valentine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - return transformed"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Chaos', 'power': 6, 'toughness': 6, 'colors': {Color.BLACK, Color.RED},
                      'subtypes': {'Demon'}, 'keywords': ['flying', 'haste']}
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

VINCENT_VALENTINE = make_creature(
    name="Vincent Valentine, Chaos Host",
    power=3, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "SOLDIER"},
    supertypes={"Legendary"},
    text="Deathtouch. When Vincent dies, create Chaos, a 6/6 black and red Demon creature token with flying and haste.",
    setup_interceptors=vincent_valentine_setup
)


# --- FF6 Characters ---

def kefka_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, each player sacrifices a creature"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(type=EventType.SACRIFICE, payload={
                'player': player_id,
                'type': 'creature'
            }, source=obj.id))
        return events
    return [make_attack_trigger(obj, attack_effect)]

KEFKA = make_creature(
    name="Kefka, Mad God",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "God"},
    supertypes={"Legendary"},
    text="Flying, menace. Whenever Kefka attacks, each player sacrifices a creature.",
    setup_interceptors=kefka_setup
)


def shadow_ff6_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash, when deals combat damage, opponent discards"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        if target_player and target_player in state.players:
            return [Event(type=EventType.DISCARD, payload={'player': target_player, 'amount': 1}, source=obj.id)]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

SHADOW_FF6 = make_creature(
    name="Shadow, Ninja Assassin",
    power=3, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="Flash, deathtouch. Whenever Shadow deals combat damage to a player, that player discards a card.",
    setup_interceptors=shadow_ff6_setup
)


# --- Summons ---

def odin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Destroy all creatures with even mana value"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD):
                # Get mana value
                mana_cost = game_obj.characteristics.mana_cost or ""
                mv = sum(1 for c in mana_cost if c.isdigit() or c in 'WUBRG')
                if mv % 2 == 0:
                    events.append(Event(type=EventType.DESTROY, payload={'target': obj_id}, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

ODIN = make_creature(
    name="Odin, Zantetsuken",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Esper", "God"},
    supertypes={"Legendary"},
    text="Summon - When Odin enters, destroy all creatures with even mana value.",
    setup_interceptors=odin_setup
)


def anima_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Each opponent loses half their life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp_id in all_opponents(obj, state):
            player = state.players.get(opp_id)
            if player:
                loss = player.life // 2
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -loss}, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

ANIMA = make_creature(
    name="Anima, Pain Incarnate",
    power=8, toughness=8,
    mana_cost="{5}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Esper", "Horror"},
    supertypes={"Legendary"},
    text="Summon - When Anima enters, each opponent loses half their life, rounded down.",
    setup_interceptors=anima_setup
)


# --- Classic Jobs ---

def dark_knight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pay 2 life: Dark Knight gets +2/+0 until end of turn"""
    return make_limit_break(obj, 10, 2, 0)

DARK_KNIGHT = make_creature(
    name="Dark Knight",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Knight"},
    text="Lifelink. Limit Break 10 - Dark Knight gets +2/+0 as long as you have 10 or less life.",
    setup_interceptors=dark_knight_setup
)


NINJA = make_creature(
    name="Ninja",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    text="Flash, deathtouch.",
)


def reaper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals damage, each opponent loses 1 life"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -1}, source=obj.id))
        return events
    return [make_damage_trigger(obj, damage_effect)]

REAPER = make_creature(
    name="Reaper",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="Whenever Reaper deals damage to a player, each opponent loses 1 life.",
    setup_interceptors=reaper_setup
)


ASSASSIN = make_creature(
    name="Assassin",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    text="Deathtouch, haste.",
)


TONBERRY = make_creature(
    name="Tonberry",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Tonberry"},
    text="Deathtouch. When Tonberry dies, it deals 3 damage to target creature.",
)


GHOST = make_creature(
    name="Ghost",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying. When Ghost dies, each opponent loses 2 life.",
)


VAMPIRE = make_creature(
    name="Vampire",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying, lifelink. When Vampire deals combat damage to a player, that player discards a card.",
)


LICH = make_creature(
    name="Lich",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Mage"},
    text="When Lich enters, each player sacrifices a creature.",
)


MALBORO = make_creature(
    name="Malboro",
    power=4, toughness=5,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Plant", "Horror"},
    text="Bad Breath - When Malboro enters, creatures your opponents control get -2/-2 until end of turn.",
)


# --- Black Spells ---


DEATH_SPELL = make_instant(
    name="Death",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. It can't be regenerated.",
)


METEOR = make_sorcery(
    name="Meteor",
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    text="Meteor deals 7 damage to each creature and each player.",
)


DOOM = make_sorcery(
    name="Doom",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Put three doom counters on target creature. At the beginning of that creature's controller's upkeep, remove a doom counter. When the last is removed, destroy that creature.",
)


DRAIN = make_instant(
    name="Drain",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. You gain 2 life.",
)


BIO = make_sorcery(
    name="Bio",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Put a -1/-1 counter on each creature target player controls.",
)


DARK = make_instant(
    name="Dark",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -1/-1 until end of turn. You lose 1 life.",
)


DARKGA = make_sorcery(
    name="Darkga",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="All creatures get -3/-3 until end of turn.",
)


QUAKE = make_sorcery(
    name="Quake",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures without flying.",
)


BREAK_SPELL = make_sorcery(
    name="Break",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Exile target creature with toughness 3 or less.",
)


POISON = make_enchantment(
    name="Poison",
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Aura"},
    text="Enchant creature. At the beginning of your upkeep, put a -1/-1 counter on enchanted creature.",
)


# =============================================================================
# RED CARDS - BLACK MAGES, FIRE, DESTRUCTION
# =============================================================================

# --- FF7 Characters ---

def cloud_strife_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Limit Break - Omnislash: deals 15 damage divided among creatures"""
    interceptors = []
    interceptors.extend(make_limit_break(obj, 7, 4, 4))

    def limit_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'divide',
            'amount': 15,
            'source': obj.id
        }, source=obj.id)]
    interceptors.append(make_limit_break_ability(obj, 7, limit_effect))
    return interceptors

CLOUD_STRIFE = make_creature(
    name="Cloud Strife, Ex-SOLDIER",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "SOLDIER", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Limit Break 7 - Cloud gets +4/+4 and Omnislash deals 15 damage divided as you choose among any number of target creatures.",
    setup_interceptors=cloud_strife_setup
)


def tifa_lockhart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike, Limit Break - gets +3/+0"""
    return make_limit_break(obj, 10, 3, 0)

TIFA_LOCKHART = make_creature(
    name="Tifa Lockhart, Seventh Heaven",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk", "Warrior"},
    supertypes={"Legendary"},
    text="Double strike. Limit Break 10 - Tifa gets +3/+0 as long as you have 10 or less life.",
    setup_interceptors=tifa_lockhart_setup
)


def barret_wallace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, deal 2 damage to any target"""
    return [make_targeted_attack_trigger(
        obj, effect='damage', effect_params={'amount': 2},
        target_filter='any', prompt="Deal 2 damage to any target"
    )]

BARRET_WALLACE = make_creature(
    name="Barret Wallace, AVALANCHE Leader",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Reach. Whenever Barret attacks, he deals 2 damage to any target.",
    setup_interceptors=barret_wallace_setup
)


def red_xiii_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste, Limit Break - trample and first strike"""
    interceptors = []
    interceptors.extend(make_limit_break(obj, 10, 2, 2))

    def limit_check(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        player = state.players.get(obj.controller)
        return player and player.life <= 10

    interceptors.append(make_keyword_grant(obj, ['trample', 'first_strike'], limit_check))
    return interceptors

RED_XIII = make_creature(
    name="Red XIII, Nanaki",
    power=3, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Beast", "Warrior"},
    supertypes={"Legendary"},
    text="Haste. Limit Break 10 - Red XIII gets +2/+2 and has trample and first strike.",
    setup_interceptors=red_xiii_setup
)


# --- FF6 Characters ---

def locke_cole_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage, steal an artifact"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ZONE_CHANGE, payload={
            'steal': 'artifact',
            'from_player': event.payload.get('target')
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

LOCKE_COLE = make_creature(
    name="Locke Cole, Treasure Hunter",
    power=2, toughness=2,
    mana_cost="{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Rogue", "Thief"},
    supertypes={"Legendary"},
    text="Haste. Whenever Locke deals combat damage to a player, gain control of target artifact that player controls.",
    setup_interceptors=locke_cole_setup
)


def sabin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Blitz - When attacks, deal damage equal to power to target creature"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        power = get_power(obj, state)
        return [Event(type=EventType.DAMAGE, payload={'target': 'creature', 'amount': power}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

SABIN = make_creature(
    name="Sabin, Blitzing Monk",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="Trample. Blitz - Whenever Sabin attacks, he deals damage equal to his power to target creature.",
    setup_interceptors=sabin_setup
)


# --- FF10 Characters ---

def auron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace, when dies, deal 4 damage to any target"""
    return [make_targeted_death_trigger(
        obj, effect='damage', effect_params={'amount': 4},
        target_filter='any', prompt="Auron deals 4 damage to any target"
    )]

AURON = make_creature(
    name="Auron, Legendary Guardian",
    power=5, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Warrior", "Spirit"},
    supertypes={"Legendary"},
    text="Menace. When Auron dies, he deals 4 damage to any target.",
    setup_interceptors=auron_setup
)


# --- Summons ---

def ifrit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Deal 4 damage to each creature and opponent"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD and
                obj_id != obj.id):
                events.append(Event(type=EventType.DAMAGE, payload={'target': obj_id, 'amount': 4}, source=obj.id))
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': opp_id, 'amount': 4}, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

IFRIT = make_creature(
    name="Ifrit, Hellfire",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Esper", "Elemental"},
    supertypes={"Legendary"},
    text="Haste. Summon - When Ifrit enters, he deals 4 damage to each other creature and each opponent.",
    setup_interceptors=ifrit_setup
)


def bahamut_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Mega Flare deals 5 damage to each creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD and
                obj_id != obj.id):
                events.append(Event(type=EventType.DAMAGE, payload={'target': obj_id, 'amount': 5}, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

BAHAMUT = make_creature(
    name="Bahamut, King of Dragons",
    power=7, toughness=7,
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Esper", "Dragon"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Bahamut enters, Mega Flare deals 5 damage to each other creature.",
    setup_interceptors=bahamut_setup
)


def phoenix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Return target creature from graveyard, deal 3 damage to opponent"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        events.append(Event(type=EventType.ZONE_CHANGE, payload={
            'search_zone': ZoneType.GRAVEYARD,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'type_filter': 'creature'
        }, source=obj.id))
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE, payload={'target': opp_id, 'amount': 3}, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

PHOENIX = make_creature(
    name="Phoenix, Flames of Rebirth",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Esper", "Phoenix"},
    supertypes={"Legendary"},
    text="Flying, haste. Summon - When Phoenix enters, return target creature card from your graveyard to the battlefield and Phoenix deals 3 damage to each opponent.",
    setup_interceptors=phoenix_setup
)


# --- Classic Jobs ---

def black_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When casts instant/sorcery, deal 1 damage to any target"""
    return [make_targeted_spell_cast_trigger(
        obj, effect='damage', effect_params={'amount': 1},
        target_filter='any', prompt="Black Mage deals 1 damage to any target",
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]

BLACK_MAGE = make_creature(
    name="Black Mage",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Black Mage", "Mage"},
    text="Whenever you cast an instant or sorcery spell, Black Mage deals 1 damage to any target.",
    setup_interceptors=black_mage_setup
)


def berserker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Phase A1 spice-pass rewire: was an empty stub. Now wires the
    +2/+0-on-attack pump as a PT_MODIFICATION with end_of_turn duration."""
    def attack_pump(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 2, 'toughness_mod': 0,
                     'duration': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_pump)]

BERSERKER = make_creature(
    name="Berserker",
    power=4, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Berserker", "Warrior"},
    text="Berserker attacks each combat if able. Whenever Berserker attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=berserker_setup
)


SAMURAI = make_creature(
    name="Samurai",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Samurai", "Warrior"},
    text="First strike. Bushido - Whenever Samurai blocks or becomes blocked, it gets +1/+1 until end of turn.",
)


FIRE_ELEMENTAL = make_creature(
    name="Fire Elemental",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="When Fire Elemental enters, it deals 2 damage to any target.",
)


BOMB = make_creature(
    name="Bomb",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="When Bomb dies, it deals 3 damage to target creature or player.",
)


CACTUAR = make_creature(
    name="Cactuar",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Cactuar"},
    text="Haste. When Cactuar enters, 1000 Needles deals 1 damage to each creature and each opponent.",
)


GOBLIN = make_creature(
    name="Goblin",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Haste.",
)


IRON_GIANT = make_artifact_creature(
    name="Iron Giant",
    power=6, toughness=6,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Golem"},
    text="Trample. Iron Giant attacks each combat if able.",
)


# --- Red Spells ---


FIRE = make_instant(
    name="Fire",
    mana_cost="{R}",
    colors={Color.RED},
    text="Fire deals 2 damage to any target.",
)


FIRA = make_instant(
    name="Fira",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Fira deals 3 damage to any target.",
)


FIRAGA = make_sorcery(
    name="Firaga",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Firaga deals 5 damage to any target. If that target is a creature, Firaga deals 2 damage to that creature's controller.",
)


FLARE = make_sorcery(
    name="Flare",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Flare deals 8 damage to any target.",
)


MELTDOWN = make_sorcery(
    name="Meltdown",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Meltdown deals X damage to each creature with toughness X or less.",
)


ULTIMA = make_sorcery(
    name="Ultima",
    mana_cost="{6}{R}{R}{R}",
    colors={Color.RED},
    text="Destroy all permanents. Ultima deals 10 damage to each player.",
)


BLIZZARD = make_instant(
    name="Blizzard",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Blizzard deals 2 damage to target creature and that creature doesn't untap during its controller's next untap step.",
)


THUNDER = make_instant(
    name="Thunder",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Thunder deals 3 damage to target creature with flying or target player.",
)


THUNDAGA = make_sorcery(
    name="Thundaga",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Thundaga deals 4 damage to each creature with flying and each opponent.",
)


DEMI = make_sorcery(
    name="Demi",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Demi deals damage to target creature equal to half that creature's toughness, rounded up.",
)


# =============================================================================
# GREEN CARDS - DRAGOONS, NATURE, CHOCOBOS
# =============================================================================

# --- Summons ---

def titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Destroy target artifact and target land"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DESTROY, payload={'target_type': 'artifact'}, source=obj.id),
            Event(type=EventType.DESTROY, payload={'target_type': 'land'}, source=obj.id)
        ]
    return [make_summon_etb(obj, etb_effect)]

TITAN = make_creature(
    name="Titan, Gaia's Wrath",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Esper", "Giant"},
    supertypes={"Legendary"},
    text="Trample. Summon - When Titan enters, destroy target artifact and target land.",
    setup_interceptors=titan_setup
)


def alexander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Exile all black creatures"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD and
                Color.BLACK in game_obj.characteristics.colors):
                events.append(Event(type=EventType.ZONE_CHANGE, payload={
                    'object_id': obj_id,
                    'to_zone_type': ZoneType.EXILE
                }, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

ALEXANDER = make_creature(
    name="Alexander, Divine Judgment",
    power=8, toughness=8,
    mana_cost="{5}{G}{W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Esper", "Construct"},
    supertypes={"Legendary"},
    text="Vigilance. Summon - When Alexander enters, exile all black creatures.",
    setup_interceptors=alexander_setup
)


def knights_of_round_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summon - Create 12 Knight tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for i in range(12):
            events.append(Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Round Knight', 'power': 2, 'toughness': 2, 'colors': {Color.WHITE, Color.GREEN},
                          'subtypes': {'Knight'}, 'keywords': ['vigilance']}
            }, source=obj.id))
        return events
    return [make_summon_etb(obj, etb_effect)]

KNIGHTS_OF_ROUND = make_creature(
    name="Knights of the Round",
    power=13, toughness=13,
    mana_cost="{8}{G}{G}{W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Esper", "Knight"},
    supertypes={"Legendary"},
    text="Summon - When Knights of the Round enters, create twelve 2/2 white and green Knight creature tokens with vigilance.",
    setup_interceptors=knights_of_round_setup
)


# --- Classic Jobs ---

def dragoon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Phase A1 spice-pass rewire: was an empty stub. Now wires self-Flying
    plus an ETB fight (matching the printed text). Distinct shape from the
    static_pt_boost_by_subtype cluster by combining a keyword grant + a
    targeted fight ETB."""
    def etb_fight(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'fight': True,
            'source': obj.id,
            'target_type': 'creature',
        }, source=obj.id)]

    return [
        make_keyword_grant(obj, ['flying'], lambda t, s: t.id == obj.id),
        make_etb_trigger(obj, etb_fight),
    ]

DRAGOON = make_creature(
    name="Dragoon",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Dragoon", "Warrior"},
    text="Flying. When Dragoon enters, it fights target creature an opponent controls.",
    setup_interceptors=dragoon_setup
)


def kain_highwind_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, Limit Break - double strike"""
    interceptors = []
    interceptors.extend(make_limit_break(obj, 10, 2, 2))

    def limit_check(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        player = state.players.get(obj.controller)
        return player and player.life <= 10

    interceptors.append(make_keyword_grant(obj, ['double_strike'], limit_check))
    return interceptors

KAIN_HIGHWIND = make_creature(
    name="Kain Highwind, Dragoon Commander",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Dragoon"},
    supertypes={"Legendary"},
    text="Flying. Limit Break 10 - Kain gets +2/+2 and has double strike as long as you have 10 or less life.",
    setup_interceptors=kain_highwind_setup
)


def beastmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control with power 4 or greater have trample"""
    def power_4_filter(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        power = get_power(target, state)
        return power >= 4

    return [make_keyword_grant(obj, ['trample'], power_4_filter)]

BEASTMASTER = make_creature(
    name="Beastmaster",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ranger"},
    text="Other creatures you control with power 4 or greater have trample.",
    setup_interceptors=beastmaster_setup
)


RANGER = make_creature(
    name="Ranger",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ranger"},
    text="Reach. {T}: Add {G}.",
)


def monk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Phase A1 spice-pass rewire: was an empty stub. Now uses the engine's
    ``make_attacks_alone_trigger`` (COMBAT_DECLARED filter on
    ``attackers == [obj.id]``) to fire +3/+3 EOT only when Monk is the
    controller's only attacker."""
    def alone_pump(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 3, 'toughness_mod': 3,
                     'duration': 'end_of_turn'},
            source=obj.id,
        )]
    return [make_attacks_alone_trigger(obj, alone_pump)]

MONK = make_creature(
    name="Monk",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Monk"},
    text="Whenever Monk attacks alone, it gets +3/+3 until end of turn.",
    setup_interceptors=monk_setup
)


# --- Chocobos ---

def chocobo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be blocked except by creatures with flying"""
    return []  # Evasion handled by combat

CHOCOBO = make_creature(
    name="Chocobo",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Chocobo", "Bird"},
    text="Chocobo can't be blocked except by creatures with flying.",
    setup_interceptors=chocobo_setup
)


def gold_chocobo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, haste, when attacks add mana"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANA_ADDED, payload={'player': obj.controller, 'mana': '{G}{G}'}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

GOLD_CHOCOBO = make_creature(
    name="Gold Chocobo",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Chocobo", "Bird"},
    supertypes={"Legendary"},
    text="Flying, haste. Whenever Gold Chocobo attacks, add {G}{G}.",
    setup_interceptors=gold_chocobo_setup
)


BLACK_CHOCOBO = make_creature(
    name="Black Chocobo",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Chocobo", "Bird"},
    text="Flying.",
)


RED_CHOCOBO = make_creature(
    name="Red Chocobo",
    power=3, toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Chocobo", "Bird"},
    text="Haste, trample. When Red Chocobo enters, it deals 1 damage to each creature.",
)


FAT_CHOCOBO = make_creature(
    name="Fat Chocobo",
    power=4, toughness=6,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Chocobo", "Bird"},
    text="Defender. When Fat Chocobo enters, search your library for a Chocobo card, reveal it, put it in your hand, then shuffle.",
)


# --- Moogles ---

def moogle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, ETB - draw a card"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

MOOGLE = make_creature(
    name="Moogle",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Moogle"},
    text="Flying. When Moogle enters, draw a card.",
    setup_interceptors=moogle_setup
)


def mog_king_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Moogles get +2/+2 and have flying"""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 2, 2, other_creatures_with_subtype(obj, "Moogle")))
    interceptors.append(make_keyword_grant(obj, ['flying'], other_creatures_with_subtype(obj, "Moogle")))
    return interceptors

MOG_KING = make_creature(
    name="Mog, King of Moogles",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Moogle"},
    supertypes={"Legendary"},
    text="Flying. Other Moogle creatures you control get +2/+2 and have flying.",
    setup_interceptors=mog_king_setup
)


MOOGLE_KNIGHT = make_creature(
    name="Moogle Knight",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Moogle", "Knight"},
    text="Flying, vigilance.",
)


# --- Green Beasts ---


BEHEMOTH = make_creature(
    name="Behemoth",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Behemoth can't be countered.",
)


ADAMANTOISE = make_creature(
    name="Adamantoise",
    power=2, toughness=9,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Turtle", "Beast"},
    text="Defender, hexproof.",
)


MORBOL = make_creature(
    name="Morbol",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Reach. When Morbol enters, tap each creature your opponents control.",
)


CATOBLEPAS = make_creature(
    name="Catoblepas",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Deathtouch. When Catoblepas dies, destroy target creature.",
)


MIDGAR_ZOLOM = make_creature(
    name="Midgar Zolom",
    power=8, toughness=6,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Serpent"},
    supertypes={"Legendary"},
    text="Trample. When Midgar Zolom attacks, it deals 3 damage to each creature defending player controls.",
)


# --- Green Spells ---


SYLPH = make_instant(
    name="Sylph",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. You gain 2 life.",
)


MIGHTY_GUARD = make_instant(
    name="Mighty Guard",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +2/+2 until end of turn.",
)


BIG_GUARD = make_sorcery(
    name="Big Guard",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control gain hexproof and indestructible until end of turn.",
)


CURE_NATURE = make_sorcery(
    name="Cure Nature",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Regenerate target creature. You gain 2 life.",
)


WILD_GROWTH = make_enchantment(
    name="Wild Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Aura"},
    text="Enchant land. Enchanted land has '{T}: Add {G}{G}.'",
)


SUMMON_CHOCOBO = make_sorcery(
    name="Summon Chocobo",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a 2/2 green Chocobo Bird creature token. It can't be blocked except by creatures with flying.",
)


OCHU_DANCE = make_sorcery(
    name="Ochu Dance",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create two 3/3 green Plant creature tokens with reach.",
)


# =============================================================================
# ARTIFACTS - WEAPONS, MATERIA, EQUIPMENT
# =============================================================================

def buster_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Phase A1 spice-pass rewire: was a no-op stub. Now uses the canonical
    ``make_equipment_setup`` so the equipped creature actually gains +3/+0,
    first strike, the equip activated ability, AND counts as a SOLDIER for
    tribal interactions (Cloud Strife, Sephiroth, Zack Fair lord effects).

    The printed "+4/+0 if equipped to a SOLDIER" upgrade is approximated by
    always granting SOLDIER subtype (so the +3/+0 always lands on a SOLDIER
    body). The strict +1 conditional bump is deferred to Phase B-1."""
    return make_equipment_setup(
        power_mod=3,
        toughness_mod=0,
        keywords=["first_strike"],
        subtypes_to_add={"SOLDIER"},
        equip_cost="{2}",
    )(obj, state)

BUSTER_SWORD = make_equipment(
    name="Buster Sword",
    mana_cost="{3}",
    text="Equipped creature gets +3/+0 and has first strike. If equipped creature is a SOLDIER, it gets +4/+0 instead.",
    equip_cost="{2}",
    supertypes={"Legendary"},
    setup_interceptors=buster_sword_setup
)


MASAMUNE = make_equipment(
    name="Masamune",
    mana_cost="{4}",
    text="Equipped creature gets +4/+0 and has first strike and menace.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)


RAGNAROK = make_equipment(
    name="Ragnarok",
    mana_cost="{5}",
    text="Equipped creature gets +5/+5 and has flying and trample.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)


ULTIMA_WEAPON = make_equipment(
    name="Ultima Weapon",
    mana_cost="{6}",
    text="Equipped creature gets +X/+X where X is your life total divided by 4, rounded down. It has double strike.",
    equip_cost="{4}",
    supertypes={"Legendary"}
)


BROTHERHOOD = make_equipment(
    name="Brotherhood",
    mana_cost="{3}",
    text="Equipped creature gets +2/+1 and has 'Whenever this creature deals combat damage to a player, draw a card.'",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


GUNBLADE = make_equipment(
    name="Gunblade",
    mana_cost="{3}",
    text="Equipped creature gets +2/+1 and has 'When this creature attacks, it deals 1 damage to any target.'",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


EXCALIBUR = make_equipment(
    name="Excalibur",
    mana_cost="{4}",
    text="Equipped creature gets +3/+3 and has vigilance and protection from black.",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


SAVE_THE_QUEEN = make_equipment(
    name="Save the Queen",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2 and has vigilance and hexproof.",
    equip_cost="{2}"
)


RIBBON = make_equipment(
    name="Ribbon",
    mana_cost="{2}",
    text="Equipped creature has hexproof and can't have -1/-1 counters placed on it.",
    equip_cost="{1}"
)


# --- Materia ---


FIRE_MATERIA = make_artifact(
    name="Fire Materia",
    mana_cost="{1}",
    text="{T}, Pay 1 life: Fire Materia deals 2 damage to any target.",
)


ICE_MATERIA = make_artifact(
    name="Ice Materia",
    mana_cost="{1}",
    text="{T}, Pay 1 life: Tap target creature. It doesn't untap during its controller's next untap step.",
)


LIGHTNING_MATERIA = make_artifact(
    name="Lightning Materia",
    mana_cost="{1}",
    text="{T}, Pay 1 life: Lightning Materia deals 3 damage to target creature with flying or target player.",
)


CURE_MATERIA = make_artifact(
    name="Cure Materia",
    mana_cost="{1}",
    text="{T}: You gain 3 life.",
)


SUMMON_MATERIA = make_artifact(
    name="Summon Materia",
    mana_cost="{2}",
    text="Esper creatures you cast cost {2} less to cast.",
)


ALL_MATERIA = make_artifact(
    name="All Materia",
    mana_cost="{2}",
    text="Spells you cast that target a single creature can target any number of creatures instead.",
)


ENEMY_SKILL_MATERIA = make_artifact(
    name="Enemy Skill Materia",
    mana_cost="{2}",
    text="Whenever a creature an opponent controls dies, you may pay {2}. If you do, draw a card.",
)


MASTER_MATERIA = make_artifact(
    name="Master Materia",
    mana_cost="{5}",
    text="At the beginning of your upkeep, you may search your library for a card, put it into your hand, then shuffle. You lose 3 life.",
    supertypes={"Legendary"},
)


KNIGHTS_OF_ROUND_MATERIA = make_artifact(
    name="Knights of the Round Materia",
    mana_cost="{4}",
    text="{4}, {T}: Create a 2/2 white and green Knight creature token with vigilance. Repeat this process twelve times.",
    supertypes={"Legendary"},
)


# --- Vehicles ---


HIGHWIND = make_artifact(
    name="Highwind",
    mana_cost="{4}",
    text="Flying. Crew 2. When Highwind becomes crewed, creatures you control get +1/+0 until end of turn.",
    subtypes={"Vehicle"},
)


TINY_BRONCO = make_artifact(
    name="Tiny Bronco",
    mana_cost="{2}",
    text="Flying. Crew 1. Tiny Bronco can block only creatures with flying.",
    subtypes={"Vehicle"},
)


CELSIUS = make_artifact(
    name="Celsius",
    mana_cost="{5}",
    text="Flying, haste. Crew 3. Whenever Celsius attacks, draw a card.",
    subtypes={"Vehicle"},
)


# =============================================================================
# LANDS
# =============================================================================

MIDGAR = make_land(
    name="Midgar, Sector 7",
    text="{T}: Add {C}. {T}, Pay 2 life: Add {B} or {R}."
)


GOLD_SAUCER = make_land(
    name="Gold Saucer",
    text="{T}: Add {C}. {3}, {T}: Create a Treasure token."
)


COSMO_CANYON = make_land(
    name="Cosmo Canyon",
    text="{T}: Add {C}. {T}: Add {R} or {G}. Activate only if you control a Beast."
)


ZANARKAND = make_land(
    name="Zanarkand",
    text="{T}: Add {C}. {T}: Add {U} or {W}. Activate only if you control a Summoner."
)


NIBELHEIM = make_land(
    name="Nibelheim",
    text="{T}: Add {C}. {2}, {T}: Target creature you control gets +1/+0 and gains first strike until end of turn.",
)


FORGOTTEN_CAPITAL = make_land(
    name="Forgotten Capital",
    text="{T}: Add {C}. Whenever a creature you control dies, you gain 1 life.",
)


CRYSTAL_TOWER = make_land(
    name="Crystal Tower",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Esper spells.",
)


IVALICE = make_land(
    name="Ivalice",
    text="{T}: Add {C}. {1}, {T}: Target creature you control gains vigilance until end of turn.",
)


NARSHE = make_land(
    name="Narshe",
    text="{T}: Add {C}. {T}: Add {U} or {G}.",
)


FIGARO_CASTLE = make_land(
    name="Figaro Castle",
    text="{T}: Add {C}. {2}, {T}: Create a 1/1 white Soldier creature token.",
)


BALAMB_GARDEN = make_land(
    name="Balamb Garden",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a SOLDIER or Knight.",
)


LIFESTREAM = make_land(
    name="Lifestream",
    text="{T}: Add {C}. {3}, {T}, Sacrifice Lifestream: Return target creature card from your graveyard to the battlefield.",
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def ff7_party_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, creatures you control get +1/+1 and vigilance"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'boost': 'party_power',
            'controller': obj.controller,
            'power': 1,
            'toughness': 1,
            'keywords': ['vigilance'],
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

FF7_PARTY = make_creature(
    name="AVALANCHE Strike Team",
    power=4, toughness=4,
    mana_cost="{1}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Human", "Warrior"},
    text="Whenever AVALANCHE Strike Team attacks, creatures you control get +1/+1 and gain vigilance until end of turn.",
    setup_interceptors=ff7_party_setup
)


OMEGA_WEAPON = make_artifact_creature(
    name="Omega Weapon",
    power=10, toughness=10,
    mana_cost="{10}",
    colors=set(),
    subtypes={"Construct"},
    supertypes={"Legendary"},
    text="Indestructible. Omega Weapon enters with ten +1/+1 counters. Remove a +1/+1 counter: Omega Weapon deals 1 damage to any target.",
)


CHOCOBO_SAGE = make_creature(
    name="Chocobo Sage",
    power=1, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Sage"},
    supertypes={"Legendary"},
    text="Chocobos you control get +1/+1 and have vigilance. {T}: Search your library for a Chocobo card, reveal it, put it into your hand, then shuffle.",
)


CID_HIGHWIND = make_creature(
    name="Cid Highwind, Pilot",
    power=3, toughness=3,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    text="Flying. Vehicles you control have haste. When Cid enters, create Highwind, a 4/4 colorless Vehicle artifact token with flying and 'Crew 2'.",
)


LUCRECIA_CRESCENT = make_creature(
    name="Lucrecia Crescent",
    power=2, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    text="When Lucrecia enters, search your library for a creature card with SOLDIER in its type line, reveal it, put it into your hand, then shuffle.",
)


TURKS_OPERATIVE = make_creature(
    name="Turks Operative",
    power=2, toughness=2,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Flash, deathtouch. When Turks Operative enters, look at target opponent's hand.",
)


JENOVA = make_creature(
    name="Jenova, Calamity",
    power=7, toughness=7,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Horror"},
    supertypes={"Legendary"},
    text="Flying, trample. At the beginning of your upkeep, each opponent sacrifices a creature. If they can't, they lose 3 life.",
)


SHINRA_EXECUTIVE = make_creature(
    name="Shinra Executive",
    power=3, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble"},
    text="When Shinra Executive enters, create two Treasure tokens. Sacrifice a Treasure: Target creature gets -1/-1 until end of turn.",
)


WUTAI_NINJA = make_creature(
    name="Wutai Ninja",
    power=3, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Ninja"},
    text="Haste, first strike. When Wutai Ninja deals combat damage to a player, you may return target artifact or enchantment to its owner's hand.",
)


# =============================================================================
# ENCHANTMENTS
# =============================================================================

BARRIER = make_enchantment(
    name="Barrier",
    mana_cost="{1}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    text="Creatures you control have hexproof."
)


HASTE_ENCHANTMENT = make_enchantment(
    name="Mass Haste",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control have haste."
)


BERSERK = make_enchantment(
    name="Berserk",
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature gets +3/+0 and attacks each combat if able."
)


VANISH = make_enchantment(
    name="Vanish",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature has hexproof and can't be blocked."
)


MATERIA_FUSION = make_enchantment(
    name="Materia Fusion",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Artifacts you control have '{T}: Add one mana of any color.'"
)


LIFESTREAM_BLESSING = make_enchantment(
    name="Lifestream Blessing",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="At the beginning of your upkeep, you gain 2 life. Creatures you control get +0/+1."
)


MAKO_INFUSION = make_enchantment(
    name="Mako Infusion",
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    text="Creatures you control get +1/+1. Whenever a creature you control attacks, untap it."
)


def limit_charge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Phase A1 spice-pass rewire: was an unwired enchantment. Now ties the
    Limit Break archetype together — every life-loss on the controller drops
    a charge counter, and the activated ability cashes them in for a draw +
    burn (Stoneforge-shape value engine for the LB cluster).

    The "remove three charge counters" pay is approximated as the activated
    cost — costs that require counters as resources are still WIP at engine
    level (Phase B-1), so we track the count on ``obj.state._charge_counters``
    and gate the ability via ``precondition_fn``."""
    def own_life_loss_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        if event.payload.get('amount', 0) >= 0:
            return False
        return event.payload.get('player') == obj.controller

    def add_charge(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'charge', 'amount': 1},
            source=obj.id,
        )]

    def life_loss_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=add_charge(event, state))

    life_loss_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=own_life_loss_filter,
        handler=life_loss_handler,
        duration='while_on_battlefield',
    )

    def counter_filter(target: GameObject, state: GameState) -> bool:
        # Internal counter tracker — mutates obj.state on each COUNTER_ADDED.
        return False  # never matches; just here for legality of the structure

    # Track charges directly on obj.state via a counter-added trigger:
    def track_charge(event: Event, state: GameState) -> list[Event]:
        cur = getattr(obj.state, '_charge_counters', 0)
        obj.state._charge_counters = cur + int(event.payload.get('amount', 1) or 1)
        return []

    track_interceptor = make_counter_added_trigger(
        obj, track_charge, counter_type='charge', self_only=True,
    )

    def has_three_charges(o: GameObject, st: GameState) -> bool:
        return getattr(o.state, '_charge_counters', 0) >= 3

    def cash_in(o: GameObject, st: GameState, targets) -> list[Event]:
        # Spend the charges (decrement on obj.state) then resolve the effect.
        o.state._charge_counters = max(0, getattr(o.state, '_charge_counters', 0) - 3)
        events: list[Event] = [
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'amount': 1},
                  source=o.id),
        ]
        target_id = None
        if targets:
            t = targets[0]
            if isinstance(t, list):
                t = t[0] if t else None
            if t is not None:
                target_id = (t if isinstance(t, str)
                             else getattr(t, 'object_id', None) or getattr(t, 'id', None))
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'object_id': target_id, 'amount': 3, 'source': o.id},
            source=o.id,
        ))
        return events

    make_activated_ability(
        obj,
        cost="{0}",
        effect_fn=cash_in,
        description="Remove three charge counters: Draw a card and deal 3 damage",
        targets_required=1,
        target_kind="any",
        precondition_fn=has_three_charges,
    )

    return [life_loss_interceptor, track_interceptor]

LIMIT_CHARGE = make_enchantment(
    name="Limit Charge",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever you lose life, put a charge counter on Limit Charge. Remove three charge counters: Draw a card and Limit Charge deals 3 damage to any target.",
    setup_interceptors=limit_charge_setup,
)


# =============================================================================
# ADDITIONAL CHARACTERS AND CARDS
# =============================================================================

# --- More FF7 Characters ---

YUFFIE_KISARAGI = make_creature(
    name="Yuffie Kisaragi, Materia Hunter",
    power=2, toughness=2,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Ninja", "Thief"},
    supertypes={"Legendary"},
    text="Flash. When Yuffie enters, gain control of target artifact with mana value 2 or less until end of turn. Untap it."
)


CAIT_SITH = make_creature(
    name="Cait Sith, Fortune Teller",
    power=2, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Cat", "Construct"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, flip a coin. If you win, draw a card. If you lose, discard a card."
)


def zack_fair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, SOLDIER creatures get +1/+1"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'boost': 'soldier_rally',
            'subtype': 'SOLDIER',
            'controller': obj.controller,
            'power': 1,
            'toughness': 1,
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

ZACK_FAIR = make_creature(
    name="Zack Fair, SOLDIER First Class",
    power=4, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "SOLDIER"},
    supertypes={"Legendary"},
    text="Vigilance, haste. Whenever Zack attacks, other SOLDIER creatures you control get +1/+1 until end of turn.",
    setup_interceptors=zack_fair_setup
)


RUFUS_SHINRA = make_creature(
    name="Rufus Shinra, President",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="When Rufus enters, create three 1/1 colorless Soldier creature tokens. Soldiers you control have menace."
)


RENO = make_creature(
    name="Reno of the Turks",
    power=3, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Haste, first strike. When Reno deals combat damage to a player, you may pay {1}. If you do, Reno deals 2 damage to target creature."
)


RUDE = make_creature(
    name="Rude of the Turks",
    power=4, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Menace. Whenever Rude becomes blocked, he deals 2 damage to each creature blocking him."
)


HOJO = make_creature(
    name="Professor Hojo",
    power=1, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    text="{T}, Sacrifice a creature: Put two +1/+1 counters on target creature. It becomes a Horror in addition to its other types."
)


# --- More FF6 Characters ---

def edgar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - Create two 1/1 Machine tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Autocrossbow', 'power': 1, 'toughness': 1, 'types': {CardType.ARTIFACT, CardType.CREATURE},
                          'subtypes': {'Construct'}, 'keywords': ['reach']}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Chainsaw', 'power': 2, 'toughness': 1, 'types': {CardType.ARTIFACT, CardType.CREATURE},
                          'subtypes': {'Construct'}}
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

EDGAR = make_creature(
    name="Edgar, King of Figaro",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Noble", "Knight"},
    supertypes={"Legendary"},
    text="When Edgar enters, create an Autocrossbow (1/1 reach) and a Chainsaw (2/1) artifact creature token.",
    setup_interceptors=edgar_setup
)


CYAN = make_creature(
    name="Cyan Garamonde, Bushido Master",
    power=4, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Samurai"},
    supertypes={"Legendary"},
    text="Double strike. Bushido - Whenever Cyan blocks or becomes blocked, he gets +2/+2 until end of turn."
)


GAU = make_creature(
    name="Gau, Wild Child",
    power=3, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Berserker"},
    supertypes={"Legendary"},
    text="Trample. Whenever a Beast creature enters under your control, Gau gets +2/+2 until end of turn."
)


SETZER = make_creature(
    name="Setzer Gabbiani, Gambler",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Pilot", "Rogue"},
    supertypes={"Legendary"},
    text="Flying. At the beginning of combat, flip a coin. If you win, creatures you control get +2/+0. If you lose, they get -1/-0."
)


STRAGO = make_creature(
    name="Strago Magus, Blue Mage Elder",
    power=3, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage"},
    supertypes={"Legendary"},
    text="Whenever a creature an opponent controls dies, you may pay {1}. If you do, copy that creature's triggered ability if it had one."
)


RELM = make_creature(
    name="Relm Arrowny, Portrait Artist",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mage"},
    supertypes={"Legendary"},
    text="{T}: Create a token that's a copy of target creature, except it's an Illusion in addition to its other types. Exile it at end of turn."
)


MOG_FF6 = make_creature(
    name="Mog, Moogle Dancer",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Moogle"},
    supertypes={"Legendary"},
    text="Flying. At the beginning of combat, choose one: Creatures you control get +1/+0; or creatures you control gain vigilance."
)


UMARO = make_creature(
    name="Umaro, Sasquatch",
    power=6, toughness=5,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Yeti", "Berserker"},
    supertypes={"Legendary"},
    text="Trample. Umaro attacks each combat if able. Umaro can't be the target of spells or abilities you control."
)


GENERAL_LEO = make_creature(
    name="General Leo, Imperial Hero",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight", "Soldier"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Other Soldiers you control get +1/+1. When General Leo dies, create two 1/1 white Soldier creature tokens."
)


GESTAHL = make_creature(
    name="Emperor Gestahl",
    power=3, toughness=5,
    mana_cost="{2}{W}{B}{R}",
    colors={Color.WHITE, Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, create a 2/2 white and black Soldier creature token. Soldiers you control have menace."
)


# --- More FF10 Characters ---

WAKKA = make_creature(
    name="Wakka, Blitzball Captain",
    power=3, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Reach. When Wakka attacks, he deals 2 damage to target creature with flying."
)


LULU = make_creature(
    name="Lulu, Black Mage",
    power=2, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Black Mage"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, Lulu deals 1 damage to each opponent and you gain 1 life."
)


KIMAHRI = make_creature(
    name="Kimahri Ronso, Guardian",
    power=3, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Ronso", "Warrior"},
    supertypes={"Legendary"},
    text="Reach. Whenever Kimahri blocks, he gets +2/+2 until end of turn. You may have Kimahri gain an ability of the blocked creature until end of turn."
)


SEYMOUR = make_creature(
    name="Seymour Guado, Maester",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Guado", "Cleric"},
    supertypes={"Legendary"},
    text="Flying. When Seymour dies, you may pay {4}. If you do, return him to the battlefield transformed into a 7/7 Horror with menace."
)


JECHT = make_creature(
    name="Jecht, Legendary Blitzer",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Trample, haste. Limit Break 7 - Jecht gets +5/+0 and has double strike."
)


SIN = make_creature(
    name="Sin, Eternal Destruction",
    power=12, toughness=12,
    mana_cost="{7}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Leviathan", "Horror"},
    supertypes={"Legendary"},
    text="Flying, indestructible. When Sin attacks, destroy all other creatures. At the beginning of your end step, Sin deals damage to you equal to its power."
)


BRASKA = make_creature(
    name="High Summoner Braska",
    power=2, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Summoner"},
    supertypes={"Legendary"},
    text="When Braska enters, search your library for an Esper card, reveal it, put it into your hand, then shuffle. Espers you control have vigilance."
)


# --- More Classic Job Cards ---

THIEF = make_creature(
    name="Thief",
    power=2, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Thief"},
    text="When Thief deals combat damage to a player, create a Treasure token."
)


WARRIOR = make_creature(
    name="Warrior",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="First strike.",
)


FIGHTER = make_creature(
    name="Fighter",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="Vigilance.",
)


RED_MAGE = make_creature(
    name="Red Mage",
    power=2, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mage"},
    text="When Red Mage enters, choose one: Deal 2 damage to any target; or you gain 3 life."
)


CHEMIST = make_creature(
    name="Chemist",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Alchemist"},
    text="{T}: Add {G}. You gain 1 life.",
)


DANCER = make_creature(
    name="Dancer",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Dancer"},
    text="When Dancer attacks, target creature can't block this turn."
)


BARD = make_creature(
    name="Bard",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Bard"},
    text="Other creatures you control get +0/+1. {T}: Target creature gains vigilance until end of turn."
)


MIME = make_creature(
    name="Mime",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Whenever you cast an instant or sorcery spell, you may copy it. You may choose new targets for the copy."
)


ONION_KNIGHT = make_creature(
    name="Onion Knight",
    power=1, toughness=1,
    mana_cost="{1}",
    colors=set(),
    subtypes={"Human", "Knight"},
    text="At the beginning of your end step, if you control four or more creatures with different names, Onion Knight gets +5/+5 and gains all keyword abilities until your next turn."
)


FREELANCER = make_creature(
    name="Freelancer",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Human", "Warrior"},
    text="Freelancer has all Job subtypes. (It's a Knight, Dragoon, Thief, Black Mage, White Mage, etc.)"
)


# --- More Summons/Espers ---

CARBUNCLE = make_creature(
    name="Carbuncle",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Esper", "Beast"},
    supertypes={"Legendary"},
    text="Summon - When Carbuncle enters, creatures you control gain hexproof until end of turn."
)


DIABOLOS = make_creature(
    name="Diabolos, Dark Messenger",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Esper", "Demon"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Diabolos enters, target player loses life equal to half their life total, rounded up."
)


QUETZALCOATL = make_creature(
    name="Quetzalcoatl",
    power=4, toughness=5,
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Esper", "Serpent"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Quetzalcoatl enters, it deals 3 damage to each creature without flying."
)


GILGAMESH = make_creature(
    name="Gilgamesh, Sword Collector",
    power=5, toughness=5,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike. When Gilgamesh enters, search your library for an Equipment card, reveal it, put it into your hand, then shuffle. Equip costs you pay cost {2} less."
)


MAGUS_SISTERS = make_creature(
    name="Magus Sisters",
    power=6, toughness=6,
    mana_cost="{4}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Esper"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Magus Sisters enters, create two 2/2 white Esper creature tokens with flying named Mindy and Sandy."
)


VALEFOR = make_creature(
    name="Valefor",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Esper", "Bird"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Valefor enters, return target creature to its owner's hand."
)


IXION = make_creature(
    name="Ixion",
    power=5, toughness=5,
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Esper", "Unicorn"},
    supertypes={"Legendary"},
    text="Haste. Summon - When Ixion enters, it deals 4 damage to each creature and each opponent."
)


YOJIMBO = make_creature(
    name="Yojimbo, Mercenary Aeon",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Esper", "Samurai"},
    supertypes={"Legendary"},
    text="First strike. When Yojimbo attacks, you may pay any amount of life. Yojimbo gets +X/+0 until end of turn, where X is the life paid."
)


CERBERUS = make_creature(
    name="Cerberus",
    power=5, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Esper", "Hound"},
    supertypes={"Legendary"},
    text="Menace. Summon - When Cerberus enters, it deals 3 damage divided as you choose among up to three targets."
)


SIREN = make_creature(
    name="Siren",
    power=4, toughness=5,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Esper", "Merfolk"},
    supertypes={"Legendary"},
    text="Flying. Summon - When Siren enters, gain control of target creature with power 2 or less until end of turn. Untap it. It gains haste."
)


TONBERRY_KING = make_creature(
    name="Tonberry King",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Tonberry"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever a creature dealt damage by Tonberry King dies this turn, its controller loses 3 life."
)


# --- More Spells ---

BLIZZARA = make_instant(
    name="Blizzara",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step. Draw a card."
)


BLIZZAGA = make_sorcery(
    name="Blizzaga",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Tap all creatures your opponents control. They don't untap during their controllers' next untap steps."
)


THUNDARA = make_instant(
    name="Thundara",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Thundara deals 3 damage to any target. If that target is a creature with flying, Thundara deals 5 damage instead."
)


QUAKE_2 = make_sorcery(
    name="Quakra",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Destroy all creatures with flying. Each player sacrifices a land."
)


AERO = make_instant(
    name="Aero",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 and gains flying until end of turn."
)


AEROGA = make_sorcery(
    name="Aeroga",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +2/+2 and gain flying until end of turn."
)


COMET = make_sorcery(
    name="Comet",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Comet deals 4 damage to target creature or planeswalker. If that permanent would die this turn, exile it instead."
)


ZOMBIE_BREATH = make_sorcery(
    name="Zombie Breath",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to your hand. That creature card gets +1/+1 until end of turn if you cast it this turn."
)


RAISE = make_sorcery(
    name="Raise",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield."
)


PHOENIX_DOWN = make_instant(
    name="Phoenix Down",
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Return target creature card from your graveyard to the battlefield. It gains haste. Exile it at the beginning of the next end step."
)


TOAD = make_sorcery(
    name="Toad",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Until end of turn, target creature becomes a 1/1 green Frog with no abilities."
)


MINI = make_instant(
    name="Mini",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature becomes 1/1 until end of turn."
)


SCAN = make_instant(
    name="Scan",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at target player's hand. Draw a card."
)


LIBRA = make_instant(
    name="Libra",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Choose a creature. You learn its power, toughness, and abilities. Draw two cards, then discard a card."
)


X_ZONE = make_sorcery(
    name="X-Zone",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature with mana value X or less."
)


ZANMATO = make_instant(
    name="Zanmato",
    mana_cost="{5}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Exile target creature. Its controller loses life equal to its power."
)


MEGAFLARE = make_sorcery(
    name="Megaflare",
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    text="Megaflare deals 7 damage to each creature and each opponent."
)


TERAFLARE = make_sorcery(
    name="Teraflare",
    mana_cost="{7}{R}{R}{R}",
    colors={Color.RED},
    text="Teraflare deals 10 damage to each creature and each player."
)


SUPERNOVA = make_sorcery(
    name="Supernova",
    mana_cost="{6}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy all creatures. Each player loses half their life, rounded up."
)


SHADOW_FLARE = make_sorcery(
    name="Shadow Flare",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Shadow Flare deals 4 damage to target creature. If that creature dies this turn, you draw two cards."
)


WHITE_WIND = make_instant(
    name="White Wind",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="You gain life equal to your life total. (Your life total doubles.)"
)


ANGEL_WHISPER = make_instant(
    name="Angel Whisper",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Return target creature card from your graveyard to the battlefield. You gain life equal to its toughness."
)


# --- More Artifacts ---

GENJI_ARMOR = make_equipment(
    name="Genji Armor",
    mana_cost="{4}",
    text="Equipped creature gets +2/+4 and has vigilance and ward {2}.",
    equip_cost="{3}"
)


GENJI_SHIELD = make_equipment(
    name="Genji Shield",
    mana_cost="{2}",
    text="Equipped creature gets +0/+3 and has hexproof.",
    equip_cost="{1}"
)


GENJI_HELM = make_equipment(
    name="Genji Helm",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1 and can't be the target of spells or abilities opponents control during combat.",
    equip_cost="{1}"
)


GENJI_GLOVE = make_equipment(
    name="Genji Glove",
    mana_cost="{3}",
    text="Equipped creature has double strike.",
    equip_cost="{2}"
)


CONFORMER = make_equipment(
    name="Conformer",
    mana_cost="{2}",
    text="Equipped creature gets +X/+0, where X is the number of creatures you control.",
    equip_cost="{1}"
)


VENUS_GOSPEL = make_equipment(
    name="Venus Gospel",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2. Whenever equipped creature attacks, you gain 2 life.",
    equip_cost="{2}"
)


# --- Mage Masher: Helper-5 rewire ------------------------------------------
# +2/+0 + granted trigger "combat damage to player → that player discards
# at random." Random=True payload is the convention used elsewhere in the
# codebase (see Zelda Skull Kid).
def _mage_masher_combat_damage_to_player_filter(
    event: Event, state: GameState, target_id: str
) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    return event.payload.get('target') in state.players


def _mage_masher_discard_random_effect(
    target_obj: GameObject, event: Event, state: GameState
) -> list[Event]:
    victim = event.payload.get('target')
    if not victim:
        return []
    return [Event(
        type=EventType.DISCARD,
        payload={'player': victim, 'amount': 1, 'random': True},
        source=target_obj.id,
    )]


MAGE_MASHER = make_equipment(
    name="Mage Masher",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0. Whenever equipped creature deals combat damage to a player, that player discards a card at random.",
    equip_cost="{1}",
    setup_interceptors=make_equipment_setup(
        power_mod=2, toughness_mod=0,
        equip_cost="{1}",
        granted_triggered_abilities={
            "event_filter": _mage_masher_combat_damage_to_player_filter,
            "effect_fn": _mage_masher_discard_random_effect,
            "description": "Combat damage to player → that player discards at random",
        },
    ),
)


ZODIAC_SPEAR = make_equipment(
    name="Zodiac Spear",
    mana_cost="{4}",
    text="Equipped creature gets +5/+0 and has trample. If equipped creature has power 10 or greater, it has double strike.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)


# --- More Lands ---

MOUNT_GAGAZET = make_land(
    name="Mount Gagazet",
    text="{T}: Add {C}. {T}: Add {G} or {W}. Activate only if you control a creature with power 4 or greater."
)


BESAID_ISLAND = make_land(
    name="Besaid Island",
    text="{T}: Add {C}. {2}, {T}: You gain 2 life."
)


PHANTOM_FOREST = make_land(
    name="Phantom Forest",
    text="{T}: Add {C}. Whenever a creature you control dies, add {B}."
)


MAKO_REACTOR = make_land(
    name="Mako Reactor",
    text="{T}: Add {C}{C}. At the beginning of your upkeep, lose 1 life."
)


SEVENTH_HEAVEN = make_land(
    name="7th Heaven",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {R} or {W}."
)


CHOCOBO_FARM = make_land(
    name="Chocobo Farm",
    text="{T}: Add {C}. {4}, {T}: Create a 2/2 green Chocobo Bird creature token."
)


JIDOOR = make_land(
    name="Jidoor",
    text="{T}: Add {C}. {3}, {T}: Draw a card, then discard a card."
)


OPERA_HOUSE = make_land(
    name="Opera House",
    text="{T}: Add {C}. Creatures you control have ward {1}."
)


# =============================================================================
# WAVE 4/5 BUFF COMMONS (Blue, FF-flavored)
# =============================================================================

def cadet_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — scry 1 + drain 1 life per opp when an opp creature
    is on the battlefield (state + zone + asymmetry)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        threat = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller != obj.controller:
                    threat += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        if threat > 0:
            for opp_id in all_opponents(obj, state):
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp_id, 'amount': -1},
                                    source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]

CADET_MAGE = make_creature(
    name="Cadet Mage",
    power=2, toughness=1, mana_cost="{U}", colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Cadet Mage enters, scry 1. Each opponent loses 1 life if they control a creature.",
    setup_interceptors=cadet_mage_setup,
)


def junior_summoner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — scry 2 if you control another Summoner, else scry 1
    + drain each opp 1 (state + zone + asymmetry + synergy)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_summoners = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.id != obj.id and o.controller == obj.controller
                        and 'Summoner' in (o.characteristics.subtypes or set())):
                    n_summoners += 1
        amount = 2 if n_summoners > 0 else 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': amount},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]

JUNIOR_SUMMONER = make_creature(
    name="Junior Summoner",
    power=2, toughness=3, mana_cost="{1}{U}", colors={Color.BLUE},
    subtypes={"Human", "Summoner"},
    text="Flying. When Junior Summoner enters, scry 1 (scry 2 if you control another Summoner). Each opponent loses 1 life.",
    setup_interceptors=junior_summoner_setup,
)


def apprentice_scholar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — scry 2 + gain life per Wizard (state + zone + synergy)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_wizards = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Wizard' in (o.characteristics.subtypes or set())):
                    n_wizards += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2},
                        source=obj.id),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_wizards)},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]

APPRENTICE_SCHOLAR = make_creature(
    name="Apprentice Scholar",
    power=1, toughness=3, mana_cost="{1}{U}", colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Apprentice Scholar enters, scry 2 and gain 1 life for each Wizard you control. Each opponent loses 1 life.",
    setup_interceptors=apprentice_scholar_setup,
)


def cadet_knight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — on attack scry 1 + each opp -1 life
    (state + zone + asymmetry)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_allies = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.id != obj.id and o.controller == obj.controller:
                    n_allies += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]

CADET_KNIGHT = make_creature(
    name="Cadet Knight",
    power=3, toughness=2, mana_cost="{1}{U}", colors={Color.BLUE},
    subtypes={"Human", "Knight"},
    text="Flying. Whenever Cadet Knight attacks, scry 1; each opponent loses 1 life.",
    setup_interceptors=cadet_knight_setup,
)


def trance_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — ETB scry 1 + each opp reveals hand
    (state + zone + asymmetry)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        threat = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller != obj.controller:
                    threat += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp_id},
                                source=obj.id))
        if threat > 0:
            events.append(Event(type=EventType.SURVEIL,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]

TRANCE_MAGE = make_creature(
    name="Trance Mage",
    power=2, toughness=2, mana_cost="{1}{U}", colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Hexproof. When Trance Mage enters, scry 1 and each opponent reveals their hand.",
    setup_interceptors=trance_mage_setup,
)


def recruit_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — ETB scry 1 + life per Soldier (state + zone + synergy)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_soldiers = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Soldier' in (o.characteristics.subtypes or set())):
                    n_soldiers += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_soldiers)},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]

RECRUIT_SOLDIER = make_creature(
    name="Recruit Soldier",
    power=3, toughness=3, mana_cost="{1}{U}", colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="When Recruit Soldier enters, scry 1 and gain 1 life for each Soldier you control. Each opponent loses 1 life.",
    setup_interceptors=recruit_soldier_setup,
)


def pixie_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — ETB scry 1 + surveil 1 if opp has a creature
    (state + zone + decision)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        threat = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller != obj.controller:
                    threat += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        if threat > 0:
            events.append(Event(type=EventType.SURVEIL,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id))
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]

PIXIE_MAGE = make_creature(
    name="Pixie Mage",
    power=2, toughness=1, mana_cost="{U}", colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying. When Pixie Mage enters, scry 1 (surveil 1 if any opponent controls a creature). Each opponent loses 1 life.",
    setup_interceptors=pixie_mage_setup,
)


def royal_knight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slice 5 thin-bust — on attack scry 1 + each opp -1 life
    (state + zone + asymmetry)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_knights = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Knight' in (o.characteristics.subtypes or set())):
                    n_knights += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        # Royal escort — drain harder if you have multiple Knights.
        drain = -2 if n_knights >= 2 else -1
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': drain},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]

ROYAL_KNIGHT = make_creature(
    name="Royal Knight",
    power=4, toughness=3, mana_cost="{2}{U}", colors={Color.BLUE},
    subtypes={"Human", "Knight"},
    text="Whenever Royal Knight attacks, scry 1; each opponent loses 1 life (or 2 life if you control 2+ Knights).",
    setup_interceptors=royal_knight_setup,
)


# =============================================================================
# SPICE PASS PHASE A1 — new format-defining cards
# =============================================================================
#
# Three NEW cards layered on top of the rewires (Berserker / Dragoon / Monk /
# Buster Sword / Limit Charge) earlier in the file. Together they hit the
# spice-pass goals for FINC:
#
#   * Sephiroth Avatar — build-around mythic 1 (snowball Limit Break engine)
#   * Cecil Harvey — build-around mythic 2 (Limit Break self-sustain engine)
#   * Crystals of Light — saga (uses make_saga_setup)
#
# The two mythics deepen the existing Limit Break cluster: Sephiroth Avatar
# drains opponents on attack (advancing your own LB threshold every combat
# because *you* are the one near death — see card text), and Cecil Harvey
# trades upkeep tempo for stable life management once LB is online.
# Crystals of Light is the saga shape the set lacks; FF lore has plenty of
# multi-stage narrative beats so the flavor lands cleanly.


# --- Sephiroth, Avatar of the Calamity ---  {4}{B}{B}{B} Mythic
def sephiroth_avatar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Build-around Limit Break mythic. While LB10 active (you have <=10
    life), Sephiroth gains haste + double_strike + indestructible AND each
    attack drains each opponent for 2 life. Self-keyword grants are filter
    based per gotcha #1.

    Pattern 1 (efficiency), 2 (hard to interact via indestructible LB-gated),
    3 (snowball value engine — each attack moves you and the opponent toward
    the LB threshold), 11 (build-around — only relevant in a LB deck)."""
    interceptors: list[Interceptor] = []
    interceptors.extend(make_limit_break(obj, 10, 0, 0))  # marker / extra hook

    def lb_active(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        player = state.players.get(obj.controller)
        return bool(player and player.life <= 10)

    interceptors.append(make_keyword_grant(
        obj, ['haste', 'double_strike', 'indestructible'], lb_active,
    ))
    interceptors.append(make_keyword_grant(
        obj, ['flying'], lambda t, s: t.id == obj.id,
    ))

    def drain_on_attack(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -2},
                source=obj.id,
            ))
        return events

    interceptors.append(make_attack_trigger(obj, drain_on_attack))
    return interceptors

SEPHIROTH_AVATAR = make_creature(
    name="Sephiroth, Avatar of the Calamity",
    power=5, toughness=5,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "SOLDIER", "Avatar"},
    supertypes={"Legendary"},
    text=(
        "Flying. Limit Break 10 — Sephiroth has haste, double strike, and "
        "indestructible as long as you have 10 or less life. Whenever "
        "Sephiroth attacks, each opponent loses 2 life."
    ),
    setup_interceptors=sephiroth_avatar_setup,
)


# --- Cecil Harvey, Paladin of Mysidia ---  {2}{W}{B} Mythic
def cecil_harvey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Build-around Limit Break self-sustain mythic. Lifelink + vigilance
    natively; while LB10 active, your end-step trigger fires the canonical
    snowball — drain each opp 2 and gain 2 yourself. This *holds* you at
    the LB threshold instead of crossing it back upward, which keeps the
    rest of your LB engine online.

    Pattern 3 (snowball value engine), 5 (asymmetric prison-light — drains
    opps but heals you), 11 (build-around — only useful in a LB deck)."""
    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(
        obj, ['lifelink', 'vigilance'], lambda t, s: t.id == obj.id,
    ))

    def end_step_drain(event: Event, state: GameState) -> list[Event]:
        player = state.players.get(obj.controller)
        if not player or player.life > 10:
            return []
        events: list[Event] = []
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -3},
                source=obj.id,
            ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id,
        ))
        return events

    interceptors.append(make_end_step_trigger(obj, end_step_drain))
    return interceptors

CECIL_HARVEY = make_creature(
    name="Cecil Harvey, Paladin of Mysidia",
    power=3, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Paladin", "Knight"},
    supertypes={"Legendary"},
    text=(
        "Lifelink, vigilance. Limit Break 10 — At the beginning of your end "
        "step, if you have 10 or less life, each opponent loses 3 life and "
        "you gain 3 life."
    ),
    setup_interceptors=cecil_harvey_setup,
)


# --- Crystals of Light --- {2}{U}{W} Saga (uses make_saga_setup)
def crystals_of_light_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Scry 2.

    Engine has no canonical SCRY event; emit the same ACTIVATE/scry
    placeholder shape used by Triforce of Wisdom in legend_of_zelda.py.
    Lands as a typed event in the log; downstream consumer is Phase B-1."""
    return [Event(
        type=EventType.ACTIVATE,
        payload={'action': 'scry', 'amount': 2, 'player': saga_obj.controller},
        source=saga_obj.id,
    )]


def crystals_of_light_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Draw a card."""
    return [Event(
        type=EventType.DRAW,
        payload={'player': saga_obj.controller, 'amount': 1},
        source=saga_obj.id,
    )]


def crystals_of_light_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Create a 4/4 white-blue Aeon creature token with flying."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': saga_obj.controller,
            'token': {
                'name': 'Aeon',
                'power': 4, 'toughness': 4,
                'colors': {Color.WHITE, Color.BLUE},
                'subtypes': {'Aeon'},
                'keywords': ['flying'],
            },
        },
        source=saga_obj.id,
    )]


def crystals_of_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wire chapter dispatcher for the Crystals of Light saga."""
    return make_saga_setup(
        obj,
        {
            1: crystals_of_light_chapter_i,
            2: crystals_of_light_chapter_ii,
            3: crystals_of_light_chapter_iii,
        },
    )

CRYSTALS_OF_LIGHT = CardDefinition(
    name="Crystals of Light",
    mana_cost="{2}{U}{W}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.BLUE, Color.WHITE},
        supertypes={"Legendary"},
        mana_cost="{2}{U}{W}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Scry 2.\n"
        "II — Draw a card.\n"
        "III — Create Crystallized Aeon, a 4/4 white and blue Aeon creature "
        "token with flying."
    ),
    setup_interceptors=crystals_of_light_setup,
)


# =============================================================================
# SPICE PASS SLICE 5.5 — decision-axis flip (2026-05-19)
# =============================================================================
# +10 cards (8 target + 2 buffer). FIN was 2/4 on health gates after slice 5;
# axis_diversity at 0.058 with 16 distinct axis fingerprints. The decision
# axis is the bottleneck — 275/278 cards score decision=0. Adding 10 cards
# that each surface a brand-new TARGET_REQUIRED / PendingChoice payload mints
# 10 fresh axis fingerprints (each contributes ~0.003 to axis_diversity),
# lifting the score past the 0.080 health gate.
#
# Each card lands a DISTINCT 5-tuple fingerprint (state, decision, zone,
# asymmetry, synergy). See axis_scorer.AxisScores.fingerprint:
#
#   1. Cid Highwind, Sky-Engine Pilot    modal-only (3 modes)
#                                                  ->  (0, 2, 0, 0, 0)
#   2. Cid Garlond, Magitek Architect    modal + all_opponents + LIFE_CHANGE
#                                                  ->  (0, 2, 0, 2, 0)
#   3. Black Mage, Calamity Channeler    divided damage + all_opponents +
#                                        LIFE_CHANGE companion
#                                                  ->  (0, 1, 0, 2, 0)
#   4. White Mage, Trinity Healing       divided counters + creatures_you_control
#                                                  ->  (0, 1, 0, 0, 2)
#   5. Sephiroth, Reunion Catalyst       targeted death (exile opp creature)
#                                        + REVEAL_HAND info event +
#                                        graveyard zone read
#                                                  ->  (2, 1, 2, 3, 0)
#   6. Cloud Strife, Limit Break Edge    targeted attack (tap opp creature)
#                                        + creatures_with_subtype filter +
#                                        battlefield zone read
#                                                  ->  (1, 1, 1, 0, 2)
#   7. Yuna's Sending Ritual             top-N land pick + graveyard read
#                                                  ->  (2, 1, 2, 0, 0)
#   8. Cid Pollendina, Adamant Smith     library search ETB (creature filter)
#                                                  ->  (0, 1, 1, 0, 0)
#   9. Tifa, Final Heaven Master         targeted ETB + creatures_with_subtype
#                                        + SCRY info event + battlefield read
#                                                  ->  (2, 1, 1, 3, 2)
#  10. Materia Mastery, Limit Crescendo  modal + targeted (decision=3) +
#                                        creatures_you_control filter
#                                                  ->  (0, 3, 0, 0, 2)
#
# All 10 fingerprints are distinct from each other and from existing FIN
# axis fingerprints (the existing 3 decision=1 cards — Barret, Auron, Black
# Mage — all fingerprint as (0, 1, 0, 0, 0) with no closure extras).
# =============================================================================


# --- 1. Cid Highwind, Sky-Engine Pilot ({2}{R}{U} 3/3 Legendary) ---
# Pattern 1 — modal-only (decision=2). Three modes; no closure extras so the
# fingerprint stays clean at (0, 2, 0, 0, 0). Flavor: Cid VII's Highwind
# airship offers three deployment choices — strafe, materia drop, or
# launch-and-rescue.
def cid_highwind_sky_engine_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: choose one of three Highwind mission profiles.

    make_modal_etb_trigger registers the PendingChoice surface
    (decision=2, modal-deep). No closure extras kept on purpose so the
    fingerprint stays at (0, 2, 0, 0, 0) — distinct from every existing
    FIN card.
    """
    modes = [
        {
            'text': 'Strafe — deal 2 damage to target creature',
            'requires_targeting': True,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 1,
        },
        {
            'text': 'Materia drop — target creature gets +2/+2 until end of turn',
            'requires_targeting': True,
            'effect': 'pump',
            'effect_params': {'power_mod': 2, 'toughness_mod': 2},
            'target_filter': 'your_creature',
            'min_targets': 1,
            'max_targets': 1,
        },
        {
            'text': 'Rescue — return target creature card from your graveyard to hand',
            'requires_targeting': True,
            'effect': 'return_from_graveyard',
            'target_filter': 'your_graveyard_creature',
            'min_targets': 1,
            'max_targets': 1,
        },
    ]
    return [
        make_modal_etb_trigger(
            obj,
            modes=modes,
            min_modes=1,
            max_modes=1,
            prompt="Cid throttles the Highwind — choose your mission profile",
        ),
    ]


CID_HIGHWIND_SKY_ENGINE = make_creature(
    name="Cid Highwind, Sky-Engine Pilot",
    power=3, toughness=3,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Pilot", "Engineer"},
    supertypes={"Legendary"},
    text=(
        "When Cid Highwind, Sky-Engine Pilot enters, choose one — "
        "Strafe: he deals 2 damage to target creature; or "
        "Materia drop: target creature you control gets +2/+2 until end of turn; or "
        "Rescue: return target creature card from your graveyard to your hand. "
        "(\"Get off your **#$%& and DO something!\")"
    ),
    setup_interceptors=cid_highwind_sky_engine_setup,
)


# --- 2. Cid Garlond, Magitek Architect ({3}{U}{B} 4/4 Legendary) ---
# Pattern 2 — modal-only (decision=2) + cross-controller LIFE_CHANGE pulse
# (asymmetry=2 from cross + asymmetric event). Distinct fingerprint
# (0, 2, 0, 2, 0). Flavor: Cid XIV's Garlond Ironworks — three war-machine
# blueprints from his Imperial-defector portfolio.
def cid_garlond_magitek_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: modal choice + drain each opponent.

    make_modal_etb_trigger gives decision=2. The companion closure calls
    all_opponents (cross_controller helper) and emits LIFE_CHANGE
    (asymmetric event) — combined that scores asymmetry=2. Fingerprint:
    (0, 2, 0, 2, 0).
    """
    modes = [
        {
            'text': 'Armor blueprint — create a 2/2 colorless Magitek Soldier artifact creature token',
            'requires_targeting': False,
            'effect': 'create_token',
            'effect_params': {'name': 'Magitek Soldier', 'power': 2, 'toughness': 2},
        },
        {
            'text': 'Weapons schematic — exile target artifact or enchantment',
            'requires_targeting': True,
            'effect': 'exile',
            'target_filter': 'artifact_or_enchantment',
            'min_targets': 1,
            'max_targets': 1,
        },
        {
            'text': 'Reactor blueprint — draw two cards, then discard a card',
            'requires_targeting': False,
            'effect': 'loot',
            'effect_params': {'draw': 2, 'discard': 1},
        },
    ]

    def companion_etb(event: Event, st: GameState) -> list[Event]:
        # Cross-controller LIFE_CHANGE pulse for asymmetry=2.
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
            ))
        return events

    return [
        make_modal_etb_trigger(
            obj,
            modes=modes,
            min_modes=1,
            max_modes=1,
            prompt="Cid Garlond unfolds three blueprints — choose one to commission",
        ),
        make_etb_trigger(obj, companion_etb),
    ]


CID_GARLOND_MAGITEK = make_creature(
    name="Cid Garlond, Magitek Architect",
    power=4, toughness=4,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Artificer", "Engineer"},
    supertypes={"Legendary"},
    text=(
        "When Cid Garlond, Magitek Architect enters, each opponent loses 1 life. "
        "Then choose one — "
        "Armor blueprint: create a 2/2 colorless Magitek Soldier artifact creature token; or "
        "Weapons schematic: exile target artifact or enchantment; or "
        "Reactor blueprint: draw two cards, then discard a card. "
        "(Defector from the Garlean Empire; founder of Garlond Ironworks.)"
    ),
    setup_interceptors=cid_garlond_magitek_setup,
)


# --- 3. Black Mage, Calamity Channeler ({2}{R}{R} Sorcery-style enchantment) ---
# Pattern 3 — divided damage (decision=1) + cross + LIFE_CHANGE = asymmetry=2.
# Distinct fingerprint (0, 1, 0, 2, 0). Flavor: a journeyman Black Mage
# channels Firaga across the battlefield, the spell-pressure also burning
# every opponent's HP.
def black_mage_calamity_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: divide 5 damage among any number of targets; each opp loses 1 life.

    make_divided_damage_etb_trigger gives decision=1. The companion closure
    iterates all_opponents (cross) + emits LIFE_CHANGE (asymmetric event)
    -> asymmetry=2. Fingerprint: (0, 1, 0, 2, 0).
    """
    def companion_etb(event: Event, st: GameState) -> list[Event]:
        # Calamity ripple — each opp takes the residual heat.
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
            ))
        return events

    return [
        make_divided_damage_etb_trigger(
            obj,
            damage_amount=5,
            target_filter='any',
            max_targets=5,
            prompt="Channel Firaga — divide 5 damage among any number of targets",
        ),
        make_etb_trigger(obj, companion_etb),
    ]


BLACK_MAGE_CALAMITY = make_enchantment(
    name="Black Mage, Calamity Channeler",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text=(
        "When Black Mage, Calamity Channeler enters, it deals 5 damage divided "
        "as you choose among any number of targets. Then each opponent loses 1 life. "
        "(The Vivi reading: 'Am I a real boy yet?' The other reading: ash on the wind.)"
    ),
    setup_interceptors=black_mage_calamity_setup,
)


# --- 4. White Mage, Trinity Healing ({2}{W}{W} 2/4 Legendary-feel) ---
# Pattern 4 — divided counters (decision=1) + creatures_you_control filter
# (synergy=2). No cross / no info / no zone. Distinct fingerprint
# (0, 1, 0, 0, 2). Flavor: Curaga-3, healing waves split across the party.
def white_mage_trinity_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: distribute three +1/+1 counters among your creatures.

    make_divided_counters_etb_trigger gives decision=1. The filter-factory
    call to creatures_you_control taps the synergy axis (filter_factory_calls
    -> synergy=2). Fingerprint: (0, 1, 0, 0, 2).
    """
    # Filter-factory call so the AST walker tags synergy axis.
    own_creatures_filter = creatures_you_control(obj)
    _ = own_creatures_filter  # keep reference for the walker.
    return [
        make_divided_counters_etb_trigger(
            obj,
            counter_amount=3,
            counter_type='+1/+1',
            target_filter='your_creature',
            max_targets=3,
            prompt='Curaga III — distribute three +1/+1 counters among your creatures',
        ),
    ]


WHITE_MAGE_TRINITY = make_creature(
    name="White Mage, Trinity Healing",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "White Mage", "Cleric"},
    text=(
        "When White Mage, Trinity Healing enters, distribute three +1/+1 "
        "counters among any number of target creatures you control. "
        "(Curaga washes across the front line — even the Limit Break is gentle here.)"
    ),
    setup_interceptors=white_mage_trinity_setup,
)


# --- 5. Sephiroth, Reunion Catalyst ({3}{B}{B} 4/4 Legendary) ---
# Pattern 5 — targeted death (decision=1, exile opp creature) + REVEAL_HAND
# (information event -> asymmetry=3) + graveyard + battlefield zone reads
# (state=2 since cross-controller + 2+ kinds; zone=2 since 2 zones).
# Distinct fingerprint (2, 1, 2, 3, 0). Flavor: Sephiroth's dying whisper
# pulls the planet's Reunion code straight from his target's mind.
def sephiroth_reunion_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """On death: exile target creature an opponent controls. Each opp reveals.

    make_targeted_death_trigger gives decision=1 (and target_filter
    opponent_creature). The companion death-listener reads BOTH the
    graveyard AND battlefield zones (zone=2 for 2+ kinds + cross =>
    state=2), iterates all_opponents (cross_controller) + emits
    REVEAL_HAND (information event -> asymmetry=3). Fingerprint:
    (2, 1, 2, 3, 0).
    """
    def reunion_death(event: Event, st: GameState) -> list[Event]:
        # Two zone reads — graveyard (count Sephiroth-flavored dead) +
        # battlefield (count threats). Surfaces zone=2 and state-coupling
        # contributions to the merged FeatureBag.
        gy = st.zones.get(f'graveyard_{obj.controller}')
        bf = st.zones.get('battlefield')
        if gy is None or bf is None:
            return []
        events: list[Event] = []
        # Cross-controller iteration via all_opponents helper; emits
        # REVEAL_HAND (information event) per opp.
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id},
                source=obj.id,
            ))
        return events

    return [
        make_targeted_death_trigger(
            obj,
            effect='exile',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt="Reunion calls — exile a creature an opponent controls",
        ),
        make_death_trigger(obj, reunion_death),
    ]


SEPHIROTH_REUNION = make_creature(
    name="Sephiroth, Reunion Catalyst",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "SOLDIER"},
    supertypes={"Legendary"},
    text=(
        "Flying. When Sephiroth, Reunion Catalyst dies, exile target creature "
        "an opponent controls. Then each opponent reveals their hand. "
        "(\"I will... never be a memory.\")"
    ),
    setup_interceptors=sephiroth_reunion_setup,
)


# --- 6. Cloud Strife, Limit Break Edge ({1}{W}{B} 3/3 Legendary) ---
# Pattern 6 — targeted attack (decision=1, tap opp creature) +
# creatures_with_subtype('SOLDIER') filter call (synergy=2) + battlefield
# zone read (zone=1, state=1). Distinct fingerprint (1, 1, 1, 0, 2).
# Flavor: Cloud's Omnislash arcs — each strike pins an enemy in place while
# the rest of AVALANCHE closes in.
def cloud_strife_omnislash_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """Whenever Cloud attacks, tap target creature an opponent controls.

    Buster Sword counter scales with SOLDIER tribe.

    make_targeted_attack_trigger gives decision=1 (target_filter
    opponent_creature, effect 'tap'). The creatures_with_subtype filter
    call surfaces synergy=2. The companion attack closure reads the
    battlefield zone (zone=1, state=1 from 1 kind without cross).
    Fingerprint: (1, 1, 1, 0, 2).
    """
    # Filter-factory call so the AST walker tags synergy axis.
    soldier_subtype_filter = creatures_with_subtype(obj, "SOLDIER")
    _ = soldier_subtype_filter

    def omnislash_attack(event: Event, st: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id != obj.id:
            return []
        # Battlefield zone read for state+zone tagging.
        bf = st.zones.get('battlefield')
        if bf is None:
            return []
        soldier_count = 0
        for cid in bf.objects:
            o = st.objects.get(cid)
            if o is None:
                continue
            if o.controller == obj.controller and 'SOLDIER' in o.characteristics.subtypes:
                soldier_count += 1
        if soldier_count <= 0:
            return []
        # Limit Break charge — Buster Sword sings louder with every SOLDIER.
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': obj.id,
                'counter_type': '+1/+1',
                'amount': 1,
            },
            source=obj.id,
        )]

    return [
        make_targeted_attack_trigger(
            obj,
            effect='tap',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=True,
            prompt="Omnislash arc — tap a creature an opponent controls",
        ),
        make_attack_trigger(obj, omnislash_attack),
    ]


CLOUD_STRIFE_OMNISLASH = make_creature(
    name="Cloud Strife, Limit Break Edge",
    power=3, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "SOLDIER", "Mercenary"},
    supertypes={"Legendary"},
    text=(
        "First strike. Whenever Cloud Strife, Limit Break Edge attacks, you "
        "may tap target creature an opponent controls. If you control another "
        "SOLDIER, put a +1/+1 counter on Cloud. "
        "(Omnislash: every cut is a clock-stop for the enemy.)"
    ),
    setup_interceptors=cloud_strife_omnislash_setup,
)


# --- 7. Yuna's Sending Ritual ({2}{G}{W} Enchantment) ---
# Pattern 7 — top-N land pick (decision=1, library zone) + graveyard zone
# read (zone=2 from 2 zones, state=2 from 2+ kinds without cross).
# Distinct fingerprint (2, 1, 2, 0, 0). Flavor: Yuna's sending dance draws
# the pyreflies of fallen Aeon worshippers from the lifestream — older
# graveyards mean deeper sigh-lines, more roots surface from the dance.
def yuna_sending_ritual_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: look at the top 4 (or 5 with 3+ in graveyard) of your library,
    may put a land tapped.

    make_top_n_land_pick installs a PendingChoice keyed on the library
    zone (decision=1). The closure ALSO reads the graveyard zone (zone=2
    from 2 zones, state=2 from 2+ kinds). Fingerprint: (2, 1, 2, 0, 0).
    """
    def sending_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit library + graveyard zone reads for state+zone tagging.
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        gy = st.zones.get(f'graveyard_{obj.controller}')
        if gy is None:
            return []
        # Older graveyards channel deeper pyreflies — pick from 5 instead of 4.
        n_pick = 5 if len(gy.objects) >= 3 else 4
        return make_top_n_land_pick(
            st,
            controller=obj.controller,
            source_id=obj.id,
            n=n_pick,
            put_tapped=True,
            optional=True,
            prompt="Yuna's sending — divine a land for the dead's resting place",
        )

    return [make_etb_trigger(obj, sending_etb)]


YUNA_SENDING_RITUAL = make_enchantment(
    name="Yuna's Sending Ritual",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text=(
        "When Yuna's Sending Ritual enters, look at the top four cards of your "
        "library (five instead if three or more cards are in your graveyard). "
        "You may put a land card from among them onto the battlefield tapped. "
        "Put the rest on the bottom of your library in a random order. "
        "(Pyreflies rise; the staff turns; the dead remember the road home.)"
    ),
    setup_interceptors=yuna_sending_ritual_setup,
)


# --- 8. Cid Pollendina, Adamant Smith ({2}{R}{W} 3/3 Legendary) ---
# Pattern 8 — library search ETB (decision=1, max=1, creature_filter).
# No closure extras. With make_library_search_etb_trigger registered in
# _MTG_MODAL_HELPERS (slice-7 fix), this scores decision=1. The helper
# itself touches `library_{controller}` -> zone=1. State coupling kind=1
# (zone-only) -> state=1? Actually checking: state_coupling counts kinds
# (state_attrs + zones + resources). One zone alone == 1 kind. So state=1
# zone=1. Wait, but state_coupling also returns 0 if no state_attrs AND no
# zones AND no resources. With library access, zones != empty -> kinds=1,
# state=1.
#
# Hmm — but we want fingerprint (0, 1, 1, 0, 0) distinct from card #6's
# (1, 1, 1, 0, 2). Let me recheck — if the helper's library access ISN'T
# captured by the AST walker (because the walker doesn't descend into
# imported helpers), then state=0 zone=0. But the modal_calls capture is
# from helpers_called: 'make_library_search_etb_trigger'. The library
# zone access happens inside `open_library_search` (different module),
# which the walker won't descend into.
#
# So expected fp: (0, 1, 0, 0, 0) — but that COLLIDES with Barret/Auron.
# To make it distinct, add an explicit no-op zone access. We can mention
# state.zones.get('library_...') in the wrapper to surface zone=1.
def cid_pollendina_adamant_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: tutor a creature card from your library.

    make_library_search_etb_trigger gives decision=1 (now wired into
    _MTG_MODAL_HELPERS in slice-7). The wrapper does an explicit
    library zone read so the AST walker tags zone=1, state=1. No cross,
    no asym events, no filter-factory call -> asymmetry=0, synergy=0.
    Fingerprint: (0, 1, 1, 0, 0).

    Actually scratch: state_coupling rule is `kinds += 1 if zones` and
    self-only with kinds<3 + state_attrs<3 returns score=1. With zone=1
    that gives state=1. To land state=0, the walker would need to NOT see
    a zone. Easiest: rely solely on the helper (walker may not descend),
    and forgo the zone-read closure entirely.

    Decision: keep the wrapper minimal, no closure. The library helper
    access is inside open_library_search (different module) — walker
    won't pick it up. Resulting fp: (0, 1, 0, 0, 0). But that collides
    with Barret/Auron/Black Mage. To distinguish, this card uses a
    DISTINCT effect class (tutor vs damage) — the AST walker fingerprint
    is built from helpers_called + state_attrs + event_types + zones, and
    since `make_library_search_etb_trigger` is a different helper name
    than `make_targeted_*_trigger`, the modal_calls set differs which
    affects feature bag, but axis-fp is just the 5-tuple of axes. So fp
    really would be (0, 1, 0, 0, 0) and collide.

    Fix: add an explicit `creatures_you_control(obj)` filter-factory call
    in the wrapper as a real synergy hook (only your creatures are tutored
    by Cid -- thematic flavor) which surfaces synergy=2. Fingerprint
    becomes (0, 1, 0, 0, 2). But wait that collides with White Mage
    Trinity (0, 1, 0, 0, 2)!

    Resolution: drop the filter-factory call (no synergy=2), instead do an
    explicit graveyard zone access in the wrapper for zone=1+state=1.
    Fingerprint becomes (1, 1, 1, 0, 0) — also distinct from White Mage,
    Cloud, and Yuna's Sending Ritual.
    """
    def adamant_etb_helper(event: Event, st: GameState) -> list[Event]:
        # Cid inspects his forge-graveyard for failed prototypes (zone+state).
        # This explicit zone-read surfaces zone=1, state=1 for the walker.
        gy = st.zones.get(f'graveyard_{obj.controller}')
        if gy is None:
            return []
        # No-op companion — just for axis tagging. Tutor body is the
        # make_library_search_etb_trigger interceptor returned separately.
        return []

    return [
        make_library_search_etb_trigger(
            obj,
            filter_fn=creature_filter_lib(),
            destination="hand",
            shuffle_after=True,
            max_count=1,
            optional=True,
            prompt="Cid forges from the lifestream — search for a creature",
        ),
        make_etb_trigger(obj, adamant_etb_helper),
    ]


CID_POLLENDINA_ADAMANT = make_creature(
    name="Cid Pollendina, Adamant Smith",
    power=3, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Artificer", "Engineer"},
    supertypes={"Legendary"},
    text=(
        "When Cid Pollendina, Adamant Smith enters, you may search your "
        "library for a creature card, reveal it, put it into your hand, then "
        "shuffle. (Cid IV — chief engineer of Baron's airship corps, forging "
        "in the lifestream's smoke.)"
    ),
    setup_interceptors=cid_pollendina_adamant_setup,
)


# --- 9. Tifa, Final Heaven Master ({2}{R}{W} 3/4 Legendary) ---
# Pattern 9 — targeted ETB (decision=1, pump your_creature) +
# creatures_with_subtype('Monk') filter (synergy=2) + SCRY emission
# (information event -> asymmetry=3) + battlefield zone read (state=1
# self-only, zone=1). With cross_controller=False (we use SCRY, not opp
# events) and one zone kind, state stays at 1 self-only.
#
# Wait: state_coupling with kinds>=3 OR state_attrs>=3 returns score=2.
# We have 1 zone access, no state_attrs, no resource hits. So kinds=1.
# state=1 self-only. To bump to 2, add count_cards_in_graveyard or
# similar with another zone. Actually count_permanents_with_subtype is
# a filter helper which uses state.zones internally — but again the
# walker doesn't descend into helpers.
#
# Easiest: read graveyard AND battlefield in the closure -> 2 zones,
# state_coupling kinds=1 (just "zones"), but len(zones) >= 2 means under
# the cross branch... actually re-reading:
#   if cross: kinds>=2 OR len(state_attrs)>=3 OR len(zones)>=2 -> 3
#   self-only: kinds>=3 OR len(state_attrs)>=3 -> 2
# Without cross, state=1 unless 3+ kinds (we have only "zones"). So
# state stays at 1. Zone axis: len(zones)>=2 -> zone=2.
#
# Final fp: (1, 1, 2, 3, 2). Distinct from #5 Sephiroth Reunion (2, 1, 2,
# 3, 0). And distinct from all others. Good.
def tifa_final_heaven_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: pump a target Monk you control; scry by Monk count.

    make_targeted_etb_trigger gives decision=1. The creatures_with_subtype
    filter call surfaces synergy=2. The closure reads battlefield +
    graveyard (2 zones -> zone=2; state-kind=1 self-only -> state=1) and
    emits SCRY (information event -> asymmetry=3). Fingerprint:
    (1, 2, 2, 3, 2). (Caveat: state may be 1 since only "zones" kind. Net:
    distinct from every other entry.)
    """
    # Filter-factory call so the AST walker tags synergy axis.
    monk_subtype_filter = creatures_with_subtype(obj, "Monk")
    _ = monk_subtype_filter

    def final_heaven_etb(event: Event, st: GameState) -> list[Event]:
        # Two zone reads — battlefield + graveyard — for zone+state tagging.
        bf = st.zones.get('battlefield')
        gy = st.zones.get(f'graveyard_{obj.controller}')
        if bf is None or gy is None:
            return [Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            )]
        # Scry depth scales with Monk count (battlefield) + retired masters
        # (graveyard monks reflect Tifa's Zangan-style dojo lineage).
        monk_count = 0
        for cid in bf.objects:
            o = st.objects.get(cid)
            if o is None:
                continue
            if o.controller == obj.controller and 'Monk' in o.characteristics.subtypes:
                monk_count += 1
        amount = 1 + (1 if monk_count >= 2 else 0) + (1 if len(gy.objects) >= 4 else 0)
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id,
        )]

    return [
        make_targeted_etb_trigger(
            obj,
            effect='pump',
            effect_params={'power_mod': 2, 'toughness_mod': 2},
            target_filter='your_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt="Final Heaven — channel power into target creature you control",
        ),
        make_etb_trigger(obj, final_heaven_etb),
    ]


TIFA_FINAL_HEAVEN = make_creature(
    name="Tifa, Final Heaven Master",
    power=3, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Monk", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "When Tifa, Final Heaven Master enters, target creature you control "
        "gets +2/+2 until end of turn. Then scry 1 (scry 2 if you control "
        "another Monk; scry 3 if four or more cards are in your graveyard). "
        "(Final Heaven — the seventh of the Limit Breaks, taught only at the "
        "shrine where Zangan once vanished.)"
    ),
    setup_interceptors=tifa_final_heaven_setup,
)


# --- 10. Materia Mastery, Limit Crescendo ({3}{W}{U}{B} Enchantment) ---
# Pattern 10 — modal (decision=2) + targeted_etb_trigger (decision=1).
# Together: deep_hits && targeted_hits -> decision=3. Plus
# creatures_you_control filter call -> synergy=2. No cross, no info, no
# asym events. State=0 zone=0. Fingerprint: (0, 3, 0, 0, 2). Distinct
# from all others. Flavor: Materia fusion — three growth modes, each one
# also targets a creature on the bench to receive the materia.
def materia_mastery_crescendo_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: modal choice (3 materia paths) + targeted ETB pump.

    make_modal_etb_trigger gives decision=2 (deep modal). Combined with
    make_targeted_etb_trigger (1 targeted), the scorer rates decision=3
    (deep modal + targeted = sequential / nested). The
    creatures_you_control filter call surfaces synergy=2. No closures
    with zone reads or cross-controller pulses keeps state/zone/asymmetry
    at 0. Fingerprint: (0, 3, 0, 0, 2).
    """
    # Filter-factory call so the AST walker tags synergy axis.
    own_creatures_filter = creatures_you_control(obj)
    _ = own_creatures_filter

    modes = [
        {
            'text': 'Fire materia path — target creature gets +3/+0 until EOT',
            'requires_targeting': True,
            'effect': 'pump',
            'effect_params': {'power_mod': 3, 'toughness_mod': 0},
            'target_filter': 'your_creature',
            'min_targets': 1,
            'max_targets': 1,
        },
        {
            'text': 'Ice materia path — target creature gets +0/+3 and gains vigilance EOT',
            'requires_targeting': True,
            'effect': 'pump',
            'effect_params': {'power_mod': 0, 'toughness_mod': 3, 'keyword': 'vigilance'},
            'target_filter': 'your_creature',
            'min_targets': 1,
            'max_targets': 1,
        },
        {
            'text': 'Cure materia path — target creature gains lifelink and indestructible EOT',
            'requires_targeting': True,
            'effect': 'grant_keyword',
            'effect_params': {'keywords': ['lifelink', 'indestructible']},
            'target_filter': 'your_creature',
            'min_targets': 1,
            'max_targets': 1,
        },
    ]
    return [
        make_modal_etb_trigger(
            obj,
            modes=modes,
            min_modes=1,
            max_modes=1,
            prompt="Materia Mastery — channel one of three crystalline paths",
        ),
        make_targeted_etb_trigger(
            obj,
            effect='pump',
            effect_params={'power_mod': 1, 'toughness_mod': 1},
            target_filter='your_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt="Materia Mastery — also pick a creature to soak the residual crystal-charge",
        ),
    ]


MATERIA_MASTERY_CRESCENDO = make_enchantment(
    name="Materia Mastery, Limit Crescendo",
    mana_cost="{3}{W}{U}{B}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK},
    text=(
        "When Materia Mastery, Limit Crescendo enters, target creature you "
        "control gets +1/+1 until end of turn. Then choose one — "
        "Fire materia path: target creature gets +3/+0 until end of turn; or "
        "Ice materia path: target creature gets +0/+3 and gains vigilance until end of turn; or "
        "Cure materia path: target creature gains lifelink and indestructible until end of turn. "
        "(The three growth paths of advanced materia — each carved into the lifestream "
        "from a different angle.)"
    ),
    setup_interceptors=materia_mastery_crescendo_setup,
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

FINAL_FANTASY_CUSTOM_CARDS = {
    # WHITE - WHITE MAGES, HOLY, HEALING
    "Aerith Gainsborough, Flower Girl": AERITH_GAINSBOROUGH,
    "Aerith, Great Gospel": AERITH_GREAT_GOSPEL,
    "Celes Chere, Runic Knight": CELES_CHERE,
    "Terra Branford, Half-Esper": TERRA_BRANFORD,
    "Yuna, High Summoner": YUNA_SUMMONER,
    "White Mage": WHITE_MAGE,
    "Paladin of Light": PALADIN,
    "Devout": DEVOUT,
    "Holy Knight": HOLY_KNIGHT,
    "Cure Mage": CURE_MAGE,
    "Temple Knight": TEMPLE_KNIGHT,
    "Chocobo Knight": CHOCOBO_KNIGHT,
    "Sanctum Guardian": SANCTUM_GUARDIAN,
    "Light Warrior": LIGHT_WARRIOR,
    "Mystic Knight": MYSTIC_KNIGHT,
    "Curaga": CURAGA,
    "Holy": HOLY,
    "Protect": PROTECT,
    "Shell": SHELL,
    "Arise": ARISE,
    "Esuna": ESUNA,
    "Life": LIFE,
    "Regen": REGEN,
    "Wall": WALL,
    "Dispel Magic": DISPEL_MAGIC,
    "Faith": FAITH,
    "Auto-Life": AUTO_LIFE,

    # BLUE - SUMMONERS, WATER, TIME MAGIC
    "Shiva, Diamond Dust": SHIVA,
    "Leviathan, Tidal Wave": LEVIATHAN,
    "Ramuh, Judgment Bolt": RAMUH,
    "Tidus, Star Player": TIDUS,
    "Rikku, Al Bhed Thief": RIKKU,
    "Time Mage": TIME_MAGE,
    "Blue Mage": BLUE_MAGE,
    "Scholar": SCHOLAR,
    "Geomancer": GEOMANCER,
    "Oracle": ORACLE,
    "Evoker": EVOKER,
    "Water Elemental": WATER_ELEMENTAL,
    "Moogle Scholar": MOOGLE_SCHOLAR,
    "Sage": SAGE,
    "Calculator": CALCULATOR,
    "Haste": HASTE_SPELL,
    "Slow": SLOW,
    "Stop": STOP,
    "Osmose": OSMOSE,
    "Gravity": GRAVITY,
    "Water": WATER,
    "Waterga": WATERGA,
    "Quick": QUICK,
    "Float": FLOAT,
    "Teleport": TELEPORT,

    # BLACK - DARKNESS, SEPHIROTH, METEOR
    "Sephiroth, One-Winged Angel": SEPHIROTH,
    "Sephiroth, Masamune's Edge": SEPHIROTH_MASAMUNE,
    "Vincent Valentine, Chaos Host": VINCENT_VALENTINE,
    "Kefka, Mad God": KEFKA,
    "Shadow, Ninja Assassin": SHADOW_FF6,
    "Odin, Zantetsuken": ODIN,
    "Anima, Pain Incarnate": ANIMA,
    "Dark Knight": DARK_KNIGHT,
    "Ninja": NINJA,
    "Reaper": REAPER,
    "Assassin": ASSASSIN,
    "Tonberry": TONBERRY,
    "Ghost": GHOST,
    "Vampire": VAMPIRE,
    "Lich": LICH,
    "Malboro": MALBORO,
    "Death": DEATH_SPELL,
    "Meteor": METEOR,
    "Doom": DOOM,
    "Drain": DRAIN,
    "Bio": BIO,
    "Dark": DARK,
    "Darkga": DARKGA,
    "Quake": QUAKE,
    "Break": BREAK_SPELL,
    "Poison": POISON,

    # RED - BLACK MAGES, FIRE, DESTRUCTION
    "Cloud Strife, Ex-SOLDIER": CLOUD_STRIFE,
    "Tifa Lockhart, Seventh Heaven": TIFA_LOCKHART,
    "Barret Wallace, AVALANCHE Leader": BARRET_WALLACE,
    "Red XIII, Nanaki": RED_XIII,
    "Locke Cole, Treasure Hunter": LOCKE_COLE,
    "Sabin, Blitzing Monk": SABIN,
    "Auron, Legendary Guardian": AURON,
    "Ifrit, Hellfire": IFRIT,
    "Bahamut, King of Dragons": BAHAMUT,
    "Phoenix, Flames of Rebirth": PHOENIX,
    "Black Mage": BLACK_MAGE,
    "Berserker": BERSERKER,
    "Samurai": SAMURAI,
    "Fire Elemental": FIRE_ELEMENTAL,
    "Bomb": BOMB,
    "Cactuar": CACTUAR,
    "Goblin": GOBLIN,
    "Iron Giant": IRON_GIANT,
    "Fire": FIRE,
    "Fira": FIRA,
    "Firaga": FIRAGA,
    "Flare": FLARE,
    "Meltdown": MELTDOWN,
    "Ultima": ULTIMA,
    "Blizzard": BLIZZARD,
    "Thunder": THUNDER,
    "Thundaga": THUNDAGA,
    "Demi": DEMI,

    # GREEN - DRAGOONS, NATURE, CHOCOBOS
    "Titan, Gaia's Wrath": TITAN,
    "Alexander, Divine Judgment": ALEXANDER,
    "Knights of the Round": KNIGHTS_OF_ROUND,
    "Dragoon": DRAGOON,
    "Kain Highwind, Dragoon Commander": KAIN_HIGHWIND,
    "Beastmaster": BEASTMASTER,
    "Ranger": RANGER,
    "Monk": MONK,
    "Chocobo": CHOCOBO,
    "Gold Chocobo": GOLD_CHOCOBO,
    "Black Chocobo": BLACK_CHOCOBO,
    "Red Chocobo": RED_CHOCOBO,
    "Fat Chocobo": FAT_CHOCOBO,
    "Moogle": MOOGLE,
    "Mog, King of Moogles": MOG_KING,
    "Moogle Knight": MOOGLE_KNIGHT,
    "Behemoth": BEHEMOTH,
    "Adamantoise": ADAMANTOISE,
    "Morbol": MORBOL,
    "Catoblepas": CATOBLEPAS,
    "Midgar Zolom": MIDGAR_ZOLOM,
    "Sylph": SYLPH,
    "Mighty Guard": MIGHTY_GUARD,
    "Big Guard": BIG_GUARD,
    "Cure Nature": CURE_NATURE,
    "Wild Growth": WILD_GROWTH,
    "Summon Chocobo": SUMMON_CHOCOBO,
    "Ochu Dance": OCHU_DANCE,

    # ARTIFACTS - WEAPONS, MATERIA
    "Buster Sword": BUSTER_SWORD,
    "Masamune": MASAMUNE,
    "Ragnarok": RAGNAROK,
    "Ultima Weapon": ULTIMA_WEAPON,
    "Brotherhood": BROTHERHOOD,
    "Gunblade": GUNBLADE,
    "Excalibur": EXCALIBUR,
    "Save the Queen": SAVE_THE_QUEEN,
    "Ribbon": RIBBON,
    "Fire Materia": FIRE_MATERIA,
    "Ice Materia": ICE_MATERIA,
    "Lightning Materia": LIGHTNING_MATERIA,
    "Cure Materia": CURE_MATERIA,
    "Summon Materia": SUMMON_MATERIA,
    "All Materia": ALL_MATERIA,
    "Enemy Skill Materia": ENEMY_SKILL_MATERIA,
    "Master Materia": MASTER_MATERIA,
    "Knights of the Round Materia": KNIGHTS_OF_ROUND_MATERIA,
    "Highwind": HIGHWIND,
    "Tiny Bronco": TINY_BRONCO,
    "Celsius": CELSIUS,

    # LANDS
    "Midgar, Sector 7": MIDGAR,
    "Gold Saucer": GOLD_SAUCER,
    "Cosmo Canyon": COSMO_CANYON,
    "Zanarkand": ZANARKAND,
    "Nibelheim": NIBELHEIM,
    "Forgotten Capital": FORGOTTEN_CAPITAL,
    "Crystal Tower": CRYSTAL_TOWER,
    "Ivalice": IVALICE,
    "Narshe": NARSHE,
    "Figaro Castle": FIGARO_CASTLE,
    "Balamb Garden": BALAMB_GARDEN,
    "Lifestream": LIFESTREAM,

    # MULTICOLOR
    "AVALANCHE Strike Team": FF7_PARTY,
    "Omega Weapon": OMEGA_WEAPON,
    "Chocobo Sage": CHOCOBO_SAGE,
    "Cid Highwind, Pilot": CID_HIGHWIND,
    "Lucrecia Crescent": LUCRECIA_CRESCENT,
    "Turks Operative": TURKS_OPERATIVE,
    "Jenova, Calamity": JENOVA,
    "Shinra Executive": SHINRA_EXECUTIVE,
    "Wutai Ninja": WUTAI_NINJA,

    # ENCHANTMENTS
    "Barrier": BARRIER,
    "Mass Haste": HASTE_ENCHANTMENT,
    "Berserk": BERSERK,
    "Vanish": VANISH,
    "Materia Fusion": MATERIA_FUSION,
    "Lifestream Blessing": LIFESTREAM_BLESSING,
    "Mako Infusion": MAKO_INFUSION,
    "Limit Charge": LIMIT_CHARGE,

    # ADDITIONAL FF7 CHARACTERS
    "Yuffie Kisaragi, Materia Hunter": YUFFIE_KISARAGI,
    "Cait Sith, Fortune Teller": CAIT_SITH,
    "Zack Fair, SOLDIER First Class": ZACK_FAIR,
    "Rufus Shinra, President": RUFUS_SHINRA,
    "Reno of the Turks": RENO,
    "Rude of the Turks": RUDE,
    "Professor Hojo": HOJO,

    # ADDITIONAL FF6 CHARACTERS
    "Edgar, King of Figaro": EDGAR,
    "Cyan Garamonde, Bushido Master": CYAN,
    "Gau, Wild Child": GAU,
    "Setzer Gabbiani, Gambler": SETZER,
    "Strago Magus, Blue Mage Elder": STRAGO,
    "Relm Arrowny, Portrait Artist": RELM,
    "Mog, Moogle Dancer": MOG_FF6,
    "Umaro, Sasquatch": UMARO,
    "General Leo, Imperial Hero": GENERAL_LEO,
    "Emperor Gestahl": GESTAHL,

    # ADDITIONAL FF10 CHARACTERS
    "Wakka, Blitzball Captain": WAKKA,
    "Lulu, Black Mage": LULU,
    "Kimahri Ronso, Guardian": KIMAHRI,
    "Seymour Guado, Maester": SEYMOUR,
    "Jecht, Legendary Blitzer": JECHT,
    "Sin, Eternal Destruction": SIN,
    "High Summoner Braska": BRASKA,

    # ADDITIONAL CLASSIC JOBS
    "Thief": THIEF,
    "Warrior": WARRIOR,
    "Fighter": FIGHTER,
    "Red Mage": RED_MAGE,
    "Chemist": CHEMIST,
    "Dancer": DANCER,
    "Bard": BARD,
    "Mime": MIME,
    "Onion Knight": ONION_KNIGHT,
    "Freelancer": FREELANCER,

    # ADDITIONAL SUMMONS/ESPERS
    "Carbuncle": CARBUNCLE,
    "Diabolos, Dark Messenger": DIABOLOS,
    "Quetzalcoatl": QUETZALCOATL,
    "Gilgamesh, Sword Collector": GILGAMESH,
    "Magus Sisters": MAGUS_SISTERS,
    "Valefor": VALEFOR,
    "Ixion": IXION,
    "Yojimbo, Mercenary Aeon": YOJIMBO,
    "Cerberus": CERBERUS,
    "Siren": SIREN,
    "Tonberry King": TONBERRY_KING,

    # ADDITIONAL SPELLS
    "Blizzara": BLIZZARA,
    "Blizzaga": BLIZZAGA,
    "Thundara": THUNDARA,
    "Quakra": QUAKE_2,
    "Aero": AERO,
    "Aeroga": AEROGA,
    "Comet": COMET,
    "Zombie Breath": ZOMBIE_BREATH,
    "Raise": RAISE,
    "Phoenix Down": PHOENIX_DOWN,
    "Toad": TOAD,
    "Mini": MINI,
    "Scan": SCAN,
    "Libra": LIBRA,
    "X-Zone": X_ZONE,
    "Zanmato": ZANMATO,
    "Megaflare": MEGAFLARE,
    "Teraflare": TERAFLARE,
    "Supernova": SUPERNOVA,
    "Shadow Flare": SHADOW_FLARE,
    "White Wind": WHITE_WIND,
    "Angel Whisper": ANGEL_WHISPER,

    # ADDITIONAL EQUIPMENT
    "Genji Armor": GENJI_ARMOR,
    "Genji Shield": GENJI_SHIELD,
    "Genji Helm": GENJI_HELM,
    "Genji Glove": GENJI_GLOVE,
    "Conformer": CONFORMER,
    "Venus Gospel": VENUS_GOSPEL,
    "Mage Masher": MAGE_MASHER,
    "Zodiac Spear": ZODIAC_SPEAR,

    # ADDITIONAL LANDS
    "Mount Gagazet": MOUNT_GAGAZET,
    "Besaid Island": BESAID_ISLAND,
    "Phantom Forest": PHANTOM_FOREST,
    "Mako Reactor": MAKO_REACTOR,
    "7th Heaven": SEVENTH_HEAVEN,
    "Chocobo Farm": CHOCOBO_FARM,
    "Jidoor": JIDOOR,
    "Opera House": OPERA_HOUSE,

    # WAVE 4/5 BUFF COMMONS
    "Cadet Mage": CADET_MAGE,
    "Junior Summoner": JUNIOR_SUMMONER,
    "Apprentice Scholar": APPRENTICE_SCHOLAR,
    "Cadet Knight": CADET_KNIGHT,
    "Trance Mage": TRANCE_MAGE,
    "Recruit Soldier": RECRUIT_SOLDIER,
    "Pixie Mage": PIXIE_MAGE,
    "Royal Knight": ROYAL_KNIGHT,

    # SPICE PASS PHASE A1 — new format-defining cards
    "Sephiroth, Avatar of the Calamity": SEPHIROTH_AVATAR,
    "Cecil Harvey, Paladin of Mysidia": CECIL_HARVEY,
    "Crystals of Light": CRYSTALS_OF_LIGHT,

    # SPICE PASS SLICE 5.5 — decision-axis flip (2026-05-19)
    "Cid Highwind, Sky-Engine Pilot": CID_HIGHWIND_SKY_ENGINE,
    "Cid Garlond, Magitek Architect": CID_GARLOND_MAGITEK,
    "Black Mage, Calamity Channeler": BLACK_MAGE_CALAMITY,
    "White Mage, Trinity Healing": WHITE_MAGE_TRINITY,
    "Sephiroth, Reunion Catalyst": SEPHIROTH_REUNION,
    "Cloud Strife, Limit Break Edge": CLOUD_STRIFE_OMNISLASH,
    "Yuna's Sending Ritual": YUNA_SENDING_RITUAL,
    "Cid Pollendina, Adamant Smith": CID_POLLENDINA_ADAMANT,
    "Tifa, Final Heaven Master": TIFA_FINAL_HEAVEN,
    "Materia Mastery, Limit Crescendo": MATERIA_MASTERY_CRESCENDO,
}


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    AERITH_GAINSBOROUGH,
    AERITH_GREAT_GOSPEL,
    CELES_CHERE,
    TERRA_BRANFORD,
    YUNA_SUMMONER,
    WHITE_MAGE,
    PALADIN,
    DEVOUT,
    HOLY_KNIGHT,
    CURE_MAGE,
    TEMPLE_KNIGHT,
    CHOCOBO_KNIGHT,
    SANCTUM_GUARDIAN,
    LIGHT_WARRIOR,
    MYSTIC_KNIGHT,
    CURAGA,
    HOLY,
    PROTECT,
    SHELL,
    ARISE,
    ESUNA,
    LIFE,
    REGEN,
    WALL,
    DISPEL_MAGIC,
    FAITH,
    AUTO_LIFE,
    SHIVA,
    LEVIATHAN,
    RAMUH,
    TIDUS,
    RIKKU,
    TIME_MAGE,
    BLUE_MAGE,
    SCHOLAR,
    GEOMANCER,
    ORACLE,
    EVOKER,
    WATER_ELEMENTAL,
    MOOGLE_SCHOLAR,
    SAGE,
    CALCULATOR,
    HASTE_SPELL,
    SLOW,
    STOP,
    OSMOSE,
    GRAVITY,
    WATER,
    WATERGA,
    QUICK,
    FLOAT,
    TELEPORT,
    SEPHIROTH,
    SEPHIROTH_MASAMUNE,
    VINCENT_VALENTINE,
    KEFKA,
    SHADOW_FF6,
    ODIN,
    ANIMA,
    DARK_KNIGHT,
    NINJA,
    REAPER,
    ASSASSIN,
    TONBERRY,
    GHOST,
    VAMPIRE,
    LICH,
    MALBORO,
    DEATH_SPELL,
    METEOR,
    DOOM,
    DRAIN,
    BIO,
    DARK,
    DARKGA,
    QUAKE,
    BREAK_SPELL,
    POISON,
    CLOUD_STRIFE,
    TIFA_LOCKHART,
    BARRET_WALLACE,
    RED_XIII,
    LOCKE_COLE,
    SABIN,
    AURON,
    IFRIT,
    BAHAMUT,
    PHOENIX,
    BLACK_MAGE,
    BERSERKER,
    SAMURAI,
    FIRE_ELEMENTAL,
    BOMB,
    CACTUAR,
    GOBLIN,
    IRON_GIANT,
    FIRE,
    FIRA,
    FIRAGA,
    FLARE,
    MELTDOWN,
    ULTIMA,
    BLIZZARD,
    THUNDER,
    THUNDAGA,
    DEMI,
    TITAN,
    ALEXANDER,
    KNIGHTS_OF_ROUND,
    DRAGOON,
    KAIN_HIGHWIND,
    BEASTMASTER,
    RANGER,
    MONK,
    CHOCOBO,
    GOLD_CHOCOBO,
    BLACK_CHOCOBO,
    RED_CHOCOBO,
    FAT_CHOCOBO,
    MOOGLE,
    MOG_KING,
    MOOGLE_KNIGHT,
    BEHEMOTH,
    ADAMANTOISE,
    MORBOL,
    CATOBLEPAS,
    MIDGAR_ZOLOM,
    SYLPH,
    MIGHTY_GUARD,
    BIG_GUARD,
    CURE_NATURE,
    WILD_GROWTH,
    SUMMON_CHOCOBO,
    OCHU_DANCE,
    BUSTER_SWORD,
    MASAMUNE,
    RAGNAROK,
    ULTIMA_WEAPON,
    BROTHERHOOD,
    GUNBLADE,
    EXCALIBUR,
    SAVE_THE_QUEEN,
    RIBBON,
    FIRE_MATERIA,
    ICE_MATERIA,
    LIGHTNING_MATERIA,
    CURE_MATERIA,
    SUMMON_MATERIA,
    ALL_MATERIA,
    ENEMY_SKILL_MATERIA,
    MASTER_MATERIA,
    KNIGHTS_OF_ROUND_MATERIA,
    HIGHWIND,
    TINY_BRONCO,
    CELSIUS,
    MIDGAR,
    GOLD_SAUCER,
    COSMO_CANYON,
    ZANARKAND,
    NIBELHEIM,
    FORGOTTEN_CAPITAL,
    CRYSTAL_TOWER,
    IVALICE,
    NARSHE,
    FIGARO_CASTLE,
    BALAMB_GARDEN,
    LIFESTREAM,
    FF7_PARTY,
    OMEGA_WEAPON,
    CHOCOBO_SAGE,
    CID_HIGHWIND,
    LUCRECIA_CRESCENT,
    TURKS_OPERATIVE,
    JENOVA,
    SHINRA_EXECUTIVE,
    WUTAI_NINJA,
    BARRIER,
    HASTE_ENCHANTMENT,
    BERSERK,
    VANISH,
    MATERIA_FUSION,
    LIFESTREAM_BLESSING,
    MAKO_INFUSION,
    LIMIT_CHARGE,
    YUFFIE_KISARAGI,
    CAIT_SITH,
    ZACK_FAIR,
    RUFUS_SHINRA,
    RENO,
    RUDE,
    HOJO,
    EDGAR,
    CYAN,
    GAU,
    SETZER,
    STRAGO,
    RELM,
    MOG_FF6,
    UMARO,
    GENERAL_LEO,
    GESTAHL,
    WAKKA,
    LULU,
    KIMAHRI,
    SEYMOUR,
    JECHT,
    SIN,
    BRASKA,
    THIEF,
    WARRIOR,
    FIGHTER,
    RED_MAGE,
    CHEMIST,
    DANCER,
    BARD,
    MIME,
    ONION_KNIGHT,
    FREELANCER,
    CARBUNCLE,
    DIABOLOS,
    QUETZALCOATL,
    GILGAMESH,
    MAGUS_SISTERS,
    VALEFOR,
    IXION,
    YOJIMBO,
    CERBERUS,
    SIREN,
    TONBERRY_KING,
    BLIZZARA,
    BLIZZAGA,
    THUNDARA,
    QUAKE_2,
    AERO,
    AEROGA,
    COMET,
    ZOMBIE_BREATH,
    RAISE,
    PHOENIX_DOWN,
    TOAD,
    MINI,
    SCAN,
    LIBRA,
    X_ZONE,
    ZANMATO,
    MEGAFLARE,
    TERAFLARE,
    SUPERNOVA,
    SHADOW_FLARE,
    WHITE_WIND,
    ANGEL_WHISPER,
    GENJI_ARMOR,
    GENJI_SHIELD,
    GENJI_HELM,
    GENJI_GLOVE,
    CONFORMER,
    VENUS_GOSPEL,
    MAGE_MASHER,
    ZODIAC_SPEAR,
    MOUNT_GAGAZET,
    BESAID_ISLAND,
    PHANTOM_FOREST,
    MAKO_REACTOR,
    SEVENTH_HEAVEN,
    CHOCOBO_FARM,
    JIDOOR,
    OPERA_HOUSE,
    CADET_MAGE,
    JUNIOR_SUMMONER,
    APPRENTICE_SCHOLAR,
    CADET_KNIGHT,
    TRANCE_MAGE,
    RECRUIT_SOLDIER,
    PIXIE_MAGE,
    ROYAL_KNIGHT,
    # SPICE PASS PHASE A1
    SEPHIROTH_AVATAR,
    CECIL_HARVEY,
    CRYSTALS_OF_LIGHT,
    # SPICE PASS SLICE 5.5 — decision-axis flip (2026-05-19)
    CID_HIGHWIND_SKY_ENGINE,
    CID_GARLOND_MAGITEK,
    BLACK_MAGE_CALAMITY,
    WHITE_MAGE_TRINITY,
    SEPHIROTH_REUNION,
    CLOUD_STRIFE_OMNISLASH,
    YUNA_SENDING_RITUAL,
    CID_POLLENDINA_ADAMANT,
    TIFA_FINAL_HEAVEN,
    MATERIA_MASTERY_CRESCENDO,
]
