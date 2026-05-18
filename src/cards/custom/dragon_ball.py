"""
Dragon Ball Z: Saiyan Saga (DBZ) Card Implementations

Set released 2026. ~250 cards.
Features mechanics: Power Level (+1/+1 counters), Transform, Ki Blast
"""

from src.cards.card_factories import (
    make_artifact,
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
    new_id, get_power, get_toughness,
)
from src.cards.ability_bundles import (
    etb_gain_life, etb_draw, etb_deal_damage, etb_create_token,
    death_draw, attack_deal_damage, attack_add_counters,
    static_pt_boost_by_subtype, static_keyword_grant_others,
)
from src.cards import interceptor_helpers as ih
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# DRAGON BALL Z KEYWORD MECHANICS
# =============================================================================

def make_power_level_trigger(source_obj: GameObject, condition: str = "combat_damage") -> Interceptor:
    """
    Power Level - Put a +1/+1 counter on this creature when condition is met.
    Conditions: combat_damage, attack, block, spell_cast
    """
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('is_combat', False))

    def attack_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == source_obj.id)

    filter_fn = damage_filter if condition == "combat_damage" else attack_filter

    def add_counter(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': source_obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=source_obj.id
        )]

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=add_counter(e, s)),
        duration='while_on_battlefield'
    )


def make_transform_ability(source_obj: GameObject, life_threshold: int = None,
                           power_bonus: int = 2, toughness_bonus: int = 2,
                           keywords: list = None) -> list[Interceptor]:
    """
    Transform - This creature transforms when conditions are met.
    Gets +X/+Y and gains keywords when transformed.
    """
    from src.cards.interceptor_helpers import make_static_pt_boost, make_keyword_grant

    interceptors = []

    def is_transformed(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        if life_threshold:
            player = state.players.get(source_obj.controller)
            return player and player.life <= life_threshold
        counters = target.state.counters.get('+1/+1', 0)
        return counters >= 3

    interceptors.extend(make_static_pt_boost(source_obj, power_bonus, toughness_bonus, is_transformed))

    if keywords:
        interceptors.append(make_keyword_grant(source_obj, keywords, is_transformed))

    return interceptors


def make_ki_blast_ability(source_obj: GameObject, damage: int, life_cost: int = 0) -> Interceptor:
    """
    Ki Blast - Deal damage to any target. May cost life to activate.
    """
    def ki_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'ki_blast')

    def ki_handler(event: Event, state: GameState) -> InterceptorResult:
        events = []
        if life_cost > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': source_obj.controller, 'amount': -life_cost},
                source=source_obj.id
            ))
        target = event.payload.get('target')
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target, 'amount': damage, 'source': source_obj.id},
            source=source_obj.id
        ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=ki_filter,
        handler=ki_handler,
        duration='while_on_battlefield'
    )


def all_opponents(obj: GameObject, state: GameState) -> list[str]:
    return [p_id for p_id in state.players.keys() if p_id != obj.controller]


# =============================================================================
# WHITE CARDS - EARTH'S DEFENDERS, HOPE, REVIVAL
# =============================================================================

def goku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.append(make_power_level_trigger(obj, "combat_damage"))
    interceptors.extend(make_transform_ability(obj, life_threshold=10, power_bonus=3, toughness_bonus=3, keywords=['flying', 'vigilance']))
    return interceptors

GOKU_EARTHS_HERO = make_creature(
    name="Goku, Earth's Hero",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Saiyan", "Z-Fighter"},
    supertypes={"Legendary"},
    setup_interceptors=goku_setup
)


def gohan_hidden_power_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == obj.id:
            return False
        dying = state.objects.get(dying_id)
        return (dying is not None and
                CardType.CREATURE in dying.characteristics.types and
                dying.controller == obj.controller)

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(2)
        ]

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=counter_effect(e, s)),
        duration='while_on_battlefield'
    )]

GOHAN_HIDDEN_POWER = make_creature(
    name="Gohan, Hidden Power",
    power=3, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Saiyan", "Z-Fighter", "Scholar"},
    supertypes={"Legendary"},
    text="Whenever another creature you control dies, put two +1/+1 counters on Gohan, Hidden Power.",
    setup_interceptors=gohan_hidden_power_setup,
)


def krillin_brave_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_gain_life(obj, 3)
    return [itc]

KRILLIN_BRAVE_WARRIOR = make_creature(
    name="Krillin, Brave Warrior",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Z-Fighter", "Monk"},
    supertypes={"Legendary"},
    text="When Krillin, Brave Warrior enters, you gain 3 life.",
    setup_interceptors=krillin_brave_warrior_setup,
)


def videl_hero_in_training_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    filter_fn = ih.other_creatures_with_subtype(obj, "Z-Fighter")
    return [ih.make_keyword_grant(obj, ['vigilance'], filter_fn)]

VIDEL_HERO_IN_TRAINING = make_creature(
    name="Videl, Hero in Training",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Z-Fighter"},
    supertypes={"Legendary"},
    text="Other Z-Fighter creatures you control have vigilance.",
    setup_interceptors=videl_hero_in_training_setup,
)


def supreme_kai_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ACTIVATE,
            payload={'action': 'scry', 'amount': 3, 'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_etb_trigger(obj, scry_effect)]

SUPREME_KAI = make_creature(
    name="Supreme Kai, Divine Watcher",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Kai", "God"},
    supertypes={"Legendary"},
    text="When Supreme Kai, Divine Watcher enters, scry 3.",
    setup_interceptors=supreme_kai_setup,
)


def king_kai_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_upkeep_trigger(obj, draw_effect)]

KING_KAI = make_creature(
    name="King Kai, Martial Arts Master",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kai"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, draw a card.",
    setup_interceptors=king_kai_setup,
)


YAMCHA_Z_FIGHTER = make_creature(
    name="Yamcha, Z-Fighter",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Z-Fighter", "Warrior"}
)


def tien_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_ki_blast_ability(obj, damage=2, life_cost=1)]

TIEN_TRICLOPS = make_creature(
    name="Tien, Triclops Warrior",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Z-Fighter", "Monk"},
    supertypes={"Legendary"},
    setup_interceptors=tien_setup
)


CHIAOTZU = make_creature(
    name="Chiaotzu, Psychic Fighter",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Z-Fighter"},
    supertypes={"Legendary"}
)


KAMI = make_creature(
    name="Kami, Guardian of Earth",
    power=2, toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Namekian", "God"},
    supertypes={"Legendary"}
)


MR_POPO = make_creature(
    name="Mr. Popo, Eternal Servant",
    power=1, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Genie"}
)


EARTHLING_FIGHTER = make_creature(
    name="Earthling Fighter",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"}
)


CAPSULE_CORP_SOLDIER = make_creature(
    name="Capsule Corp Soldier",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"}
)


WORLD_CHAMPION = make_creature(
    name="World Tournament Champion",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"}
)


MARTIAL_ARTIST = make_creature(
    name="Martial Artist",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"}
)


OTHERWORLD_FIGHTER = make_creature(
    name="Otherworld Fighter",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Warrior"}
)


GUARDIAN_ANGEL = make_creature(
    name="Guardian Angel",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"}
)


TURTLE_SCHOOL_STUDENT = make_creature(
    name="Turtle School Student",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"}
)


CRANE_SCHOOL_STUDENT = make_creature(
    name="Crane School Student",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"}
)


# White Instants

SENZU_HEAL = make_instant(
    name="Senzu Heal",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="You gain 4 life. If you control a Z-Fighter, you gain 6 life instead."
)


DIVINE_PROTECTION = make_instant(
    name="Divine Protection",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. If it's a Saiyan, put a +1/+1 counter on it."
)


INSTANT_TRANSMISSION_WHITE = make_instant(
    name="Heroic Rescue",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Exile target creature you control, then return it to the battlefield under your control. You gain 2 life."
)


ENERGY_BARRIER = make_instant(
    name="Energy Barrier",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to creatures you control this turn."
)


KIAI_SHOUT = make_instant(
    name="Kiai Shout",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)


HOPE_OF_EARTH = make_instant(
    name="Hope of Earth",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Create two 1/1 white Human Warrior creature tokens. You gain 1 life for each creature you control."
)


# White Sorceries

REVIVAL = make_sorcery(
    name="Revival",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Return target creature card from your graveyard to the battlefield. You gain life equal to its toughness."
)


DRAGON_BALL_WISH = make_sorcery(
    name="Dragon Ball Wish",
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    text="Choose one: Return all creature cards from your graveyard to your hand; or destroy all creatures with power 4 or greater; or you gain 8 life."
)


TRAINING_COMPLETE = make_sorcery(
    name="Training Complete",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Put two +1/+1 counters on target creature you control. It gains vigilance until end of turn."
)


WORLD_TOURNAMENT = make_sorcery(
    name="World Tournament",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Each player chooses a creature they control. Those creatures fight each other. You gain 3 life."
)


# White Enchantments

def z_fighters_unite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Z-Fighter", include_self=True)
    return itcs

Z_FIGHTERS_UNITE = make_enchantment(
    name="Z-Fighters Unite",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Z-Fighter creatures you control get +1/+1.",
    setup_interceptors=z_fighters_unite_setup,
)


OTHERWORLD = make_enchantment(
    name="Otherworld",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control dies, you may pay {1}. If you do, return it to the battlefield at the beginning of the next end step."
)


KAIS_BLESSING = make_enchantment(
    name="Kai's Blessing",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control have lifelink. {2}{W}: Put a +1/+1 counter on target creature you control."
)


# =============================================================================
# BLUE CARDS - ANDROIDS, STRATEGY, KI CONTROL
# =============================================================================

def android_18_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_draw(obj, 1)
    return [itc]

ANDROID_18 = make_creature(
    name="Android 18, Infinite Energy",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Android"},
    supertypes={"Legendary"},
    text="When Android 18, Infinite Energy enters, draw a card.",
    setup_interceptors=android_18_setup,
)


def android_17_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    filter_fn = ih.other_creatures_with_subtype(obj, "Android")
    return [ih.make_keyword_grant(obj, ['hexproof'], filter_fn)]

ANDROID_17 = make_creature(
    name="Android 17, Nature's Protector",
    power=4, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Android"},
    supertypes={"Legendary"},
    text="Other Android creatures you control have hexproof.",
    setup_interceptors=android_17_setup,
)


def android_16_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': 5, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            )
            for opp_id in ih.all_opponents(obj, state)
        ]
    return [ih.make_death_trigger(obj, death_effect)]

ANDROID_16 = make_creature(
    name="Android 16, Gentle Giant",
    power=5, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Android"},
    supertypes={"Legendary"},
    text="When Android 16, Gentle Giant dies, it deals 5 damage to each opponent.",
    setup_interceptors=android_16_setup,
)


def bulma_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.ARTIFACT in spell_types

    def cost_reduce(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('cost_reduction', 0)
        new_event.payload['cost_reduction'] = current + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM, filter=cast_filter, handler=cost_reduce,
        duration='while_on_battlefield'
    )]

BULMA_GENIUS_INVENTOR = make_creature(
    name="Bulma, Genius Inventor",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    setup_interceptors=bulma_setup
)


def dr_brief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def artifact_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        return (entering and entering.controller == source.controller and
                CardType.ARTIFACT in entering.characteristics.types)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: artifact_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

DR_BRIEF = make_creature(
    name="Dr. Brief, Capsule Corp Founder",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    setup_interceptors=dr_brief_setup
)


ANDROID_19 = make_creature(
    name="Android 19, Energy Absorber",
    power=3, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Android"}
)


ANDROID_20 = make_creature(
    name="Android 20, Dr. Gero",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Android", "Scientist"},
    supertypes={"Legendary"}
)


CAPSULE_CORP_DRONE = make_creature(
    name="Capsule Corp Drone",
    power=1, toughness=1,
    mana_cost="{1}",
    colors=set(),
    subtypes={"Construct"}
)


REPAIR_BOT = make_creature(
    name="Repair Bot",
    power=0, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Construct"}
)


ANALYSIS_DRONE = make_creature(
    name="Analysis Drone",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"}
)


SCIENTIST = make_creature(
    name="Capsule Corp Scientist",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"}
)


RED_RIBBON_SCOUT = make_creature(
    name="Red Ribbon Scout",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier", "Scout"}
)


ANDROID_PROTOTYPE = make_creature(
    name="Android Prototype",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Android"}
)


BATTLE_ANDROID = make_creature(
    name="Battle Android",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Android", "Soldier"}
)


ENERGY_ABSORBER = make_creature(
    name="Energy Absorber",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Android"}
)


# Blue Instants

KI_SENSE = make_instant(
    name="Ki Sense",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 3. If you control an Android, draw a card."
)


ENERGY_DRAIN = make_instant(
    name="Energy Drain",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target activated ability. Draw a card."
)


AFTERIMAGE = make_instant(
    name="Afterimage",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof until end of turn. Untap it."
)


INSTANT_TRANSMISSION_BLUE = make_instant(
    name="Instant Transmission",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If it was an Android, you may draw a card."
)


PHOTON_WAVE = make_instant(
    name="Photon Wave",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Tap all creatures target opponent controls. Those creatures don't untap during their controller's next untap step."
)


SOLAR_FLARE_TECHNIQUE = make_instant(
    name="Solar Flare",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap up to two target creatures. They don't untap during their controllers' next untap steps. Draw a card."
)


# Blue Sorceries

ANDROID_CONSTRUCTION = make_sorcery(
    name="Android Construction",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Create two 3/3 blue Android artifact creature tokens."
)


TECHNOLOGY_ADVANCEMENT = make_sorcery(
    name="Technology Advancement",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card. If you control an artifact, discard a card instead of two."
)


ENERGY_ANALYSIS = make_sorcery(
    name="Energy Analysis",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Scry 2, then draw two cards."
)


RED_RIBBON_RESEARCH = make_sorcery(
    name="Red Ribbon Research",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Search your library for an Android or artifact card, reveal it, put it into your hand, then shuffle."
)


# Blue Enchantments

INFINITE_ENERGY = make_enchantment(
    name="Infinite Energy",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Androids you control have '{T}: Add {U}.' At the beginning of your upkeep, untap each Android you control."
)


CAPSULE_TECHNOLOGY = make_enchantment(
    name="Capsule Technology",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Artifacts you control have hexproof. {2}{U}: Create a Treasure token."
)


ENERGY_FIELD = make_enchantment(
    name="Energy Field",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Creatures your opponents control enter tapped. {U}: Target creature doesn't untap during its controller's next untap step."
)


# =============================================================================
# BLACK CARDS - FRIEZA FORCE, DESTRUCTION, EVIL
# =============================================================================

def frieza_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_damage_trigger
    interceptors = []
    interceptors.extend(make_transform_ability(obj, life_threshold=10, power_bonus=4, toughness_bonus=2, keywords=['flying']))

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ZONE_CHANGE, payload={
            'target_type': 'creature', 'to_zone_type': ZoneType.GRAVEYARD
        }, source=obj.id)]
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    return interceptors

FRIEZA_EMPEROR = make_creature(
    name="Frieza, Galactic Emperor",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Tyrant"},
    supertypes={"Legendary"},
    setup_interceptors=frieza_setup
)


def cell_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        return (dying and CardType.CREATURE in dying.characteristics.types and dying_id != source.id)

    def absorb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=absorb_effect(e, s)),
        duration='while_on_battlefield'
    )]

CELL_PERFECT_FORM = make_creature(
    name="Cell, Perfect Form",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Android", "Bio-Weapon"},
    supertypes={"Legendary"},
    setup_interceptors=cell_setup
)


def kid_buu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def lose_life_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -2},
                source=obj.id,
                controller=obj.controller,
            )
            for opp_id in ih.all_opponents(obj, state)
        ]
    return [ih.make_upkeep_trigger(obj, lose_life_effect)]

KID_BUU = make_creature(
    name="Kid Buu, Pure Destruction",
    power=6, toughness=5,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Majin"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, each opponent loses 2 life.",
    setup_interceptors=kid_buu_setup,
)


MAJIN_BUU = make_creature(
    name="Majin Buu, Innocent Evil",
    power=5, toughness=6,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Majin"},
    supertypes={"Legendary"}
)


SUPER_BUU = make_creature(
    name="Super Buu, Absorber",
    power=6, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Majin"},
    supertypes={"Legendary"},
    text="Whenever Super Buu, Absorber attacks, target opponent sacrifices a creature.",
)


ZARBON = make_creature(
    name="Zarbon, Frieza's Elite",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier"},
    supertypes={"Legendary"}
)


DODORIA = make_creature(
    name="Dodoria, Frieza's Elite",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier"},
    supertypes={"Legendary"}
)


GINYU = make_creature(
    name="Captain Ginyu",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier"},
    supertypes={"Legendary"}
)


RECOOME = make_creature(
    name="Recoome",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier", "Ginyu Force"}
)


BURTER = make_creature(
    name="Burter",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier", "Ginyu Force"}
)


JEICE = make_creature(
    name="Jeice",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier", "Ginyu Force"}
)


GULDO = make_creature(
    name="Guldo",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier", "Ginyu Force"}
)


FRIEZA_SOLDIER = make_creature(
    name="Frieza Soldier",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier"}
)


APPULE = make_creature(
    name="Appule",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Soldier"}
)


SAIBAMAN = make_creature(
    name="Saibaman",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Plant", "Warrior"}
)


CELL_JUNIOR = make_creature(
    name="Cell Junior",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Android", "Bio-Weapon"}
)


MAJIN_MINION = make_creature(
    name="Majin Minion",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"}
)


DABURA = make_creature(
    name="Dabura, Demon King",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Noble"},
    supertypes={"Legendary"}
)


BABIDI = make_creature(
    name="Babidi, Dark Wizard",
    power=1, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Wizard"},
    supertypes={"Legendary"}
)


# Black Instants

DEATH_BEAM = make_instant(
    name="Death Beam",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with toughness 3 or less. If you control Frieza, destroy target creature instead."
)


SUPERNOVA = make_instant(
    name="Supernova",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses life equal to that creature's power."
)


FINGER_BEAM = make_instant(
    name="Finger Beam",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn."
)


ABSORPTION = make_instant(
    name="Absorption",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If Cell destroyed it, put two +1/+1 counters on Cell."
)


VANISH = make_instant(
    name="Vanish",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Exile target creature. Its controller loses 2 life."
)


MAJIN_CURSE = make_instant(
    name="Majin Curse",
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If it would die this turn, exile it instead."
)


# Black Sorceries

PLANET_DESTRUCTION = make_sorcery(
    name="Planet Destruction",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. Each player loses 2 life for each creature they controlled that was destroyed this way."
)


GENOCIDE_ATTACK = make_sorcery(
    name="Genocide Attack",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. You gain 2 life for each creature sacrificed this way."
)


RAISE_SAIBAMEN = make_sorcery(
    name="Raise Saibamen",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Create two 2/1 black Plant Warrior creature tokens with 'When this creature dies, it deals 2 damage to the creature that killed it.'"
)


RESURRECTION_F = make_sorcery(
    name="Resurrection",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Return target creature card from a graveyard to the battlefield under your control. That creature is a Zombie in addition to its other types."
)


# Black Enchantments

def frieza_force_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 0, "Soldier", include_self=True)
    return itcs

FRIEZA_FORCE = make_enchantment(
    name="Frieza Force",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Soldier creatures you control get +1/+0.",
    setup_interceptors=frieza_force_setup,
)


MAJIN_MARK = make_enchantment(
    name="Majin Mark",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature. Enchanted creature gets +3/+0 and has menace. At the beginning of your upkeep, you lose 1 life."
)


DARK_ENERGY = make_enchantment(
    name="Dark Energy",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Whenever a creature dies, each opponent loses 1 life and you gain 1 life."
)


# =============================================================================
# RED CARDS - SAIYANS, RAGE, POWER
# =============================================================================

def vegeta_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.append(make_power_level_trigger(obj, "combat_damage"))
    interceptors.extend(make_transform_ability(obj, life_threshold=10, power_bonus=3, toughness_bonus=2, keywords=['trample']))
    return interceptors

VEGETA_SAIYAN_PRINCE = make_creature(
    name="Vegeta, Saiyan Prince",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Noble", "Warrior"},
    supertypes={"Legendary"},
    setup_interceptors=vegeta_setup
)


def broly_legendary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = attack_add_counters(obj, "+1/+1", 2)
    return [itc]

BROLY_LEGENDARY = make_creature(
    name="Broly, Legendary Super Saiyan",
    power=7, toughness=7,
    mana_cost="{3}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Berserker"},
    supertypes={"Legendary"},
    abilities=[{'keyword': 'trample'}],
    text="Trample. Whenever Broly, Legendary Super Saiyan attacks, put two +1/+1 counters on it.",
    setup_interceptors=broly_legendary_setup,
)


FUTURE_TRUNKS = make_creature(
    name="Future Trunks, Time Warrior",
    power=4, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Z-Fighter", "Warrior"},
    supertypes={"Legendary"},
    abilities=[{'keyword': 'haste'}],
    text="Haste."
)


def kid_trunks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 0, "Saiyan", include_self=False)
    return itcs

KID_TRUNKS = make_creature(
    name="Trunks, Young Fighter",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Z-Fighter"},
    supertypes={"Legendary"},
    text="Other Saiyan creatures you control get +1/+0.",
    setup_interceptors=kid_trunks_setup,
)


def goten_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_deal_damage(obj, 2, "each_opponent")
    return [itc]

GOTEN = make_creature(
    name="Goten, Cheerful Saiyan",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Z-Fighter"},
    supertypes={"Legendary"},
    text="When Goten, Cheerful Saiyan enters, it deals 2 damage to each opponent.",
    setup_interceptors=goten_setup,
)


NAPPA = make_creature(
    name="Nappa, Saiyan Elite",
    power=5, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Warrior"},
    supertypes={"Legendary"},
    abilities=[{'keyword': 'menace'}],
    text="Menace."
)


RADITZ = make_creature(
    name="Raditz, Saiyan Warrior",
    power=4, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Warrior"},
    supertypes={"Legendary"},
    abilities=[{'keyword': 'menace'}],
    text="Menace."
)


BARDOCK = make_creature(
    name="Bardock, Father of Goku",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Warrior"},
    supertypes={"Legendary"},
    abilities=[{'keyword': 'haste'}],
    text="Haste."
)


def king_vegeta_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Saiyan", include_self=False)
    return itcs

KING_VEGETA = make_creature(
    name="King Vegeta",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Noble"},
    supertypes={"Legendary"},
    text="Other Saiyan creatures you control get +1/+1.",
    setup_interceptors=king_vegeta_setup,
)


SAIYAN_WARRIOR = make_creature(
    name="Saiyan Warrior",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Warrior"}
)


SAIYAN_ELITE = make_creature(
    name="Saiyan Elite",
    power=4, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Warrior"}
)


GREAT_APE = make_creature(
    name="Great Ape",
    power=8, toughness=8,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Ape"}
)


RAGING_SAIYAN = make_creature(
    name="Raging Saiyan",
    power=4, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Berserker"}
)


SAIYAN_CHILD = make_creature(
    name="Saiyan Child",
    power=2, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Saiyan"}
)


SAIYAN_POD_PILOT = make_creature(
    name="Saiyan Pod Pilot",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Pilot"}
)


# Red Instants

def final_flash_resolve(state: GameState, source_id: str, targets: list):
    target = targets[0] if targets else None
    return [Event(type=EventType.DAMAGE, payload={'target': target, 'amount': 5, 'source': source_id}, source=source_id)]

FINAL_FLASH = make_instant(
    name="Final Flash",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Final Flash deals 5 damage to any target. If you control Vegeta, it deals 7 damage instead."
)


GALICK_GUN = make_instant(
    name="Galick Gun",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Galick Gun deals 3 damage to any target. If that target is a creature, it can't block this turn."
)


BIG_BANG_ATTACK = make_instant(
    name="Big Bang Attack",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Big Bang Attack deals 4 damage to target creature."
)


BURNING_ATTACK = make_instant(
    name="Burning Attack",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Burning Attack deals 3 damage to any target. If you control a Saiyan, it deals 4 damage instead."
)


EXPLOSIVE_WAVE = make_instant(
    name="Explosive Wave",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Explosive Wave deals 2 damage to each creature and each opponent."
)


SAIYAN_RAGE = make_instant(
    name="Saiyan Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target Saiyan creature gets +3/+0 and gains trample until end of turn."
)


KI_EXPLOSION = make_instant(
    name="Ki Explosion",
    mana_cost="{R}",
    colors={Color.RED},
    text="Ki Explosion deals 2 damage to any target."
)


# Red Sorceries

POWER_BALL = make_sorcery(
    name="Power Ball",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Transform all Saiyan creatures you control. They get +4/+4 and gain trample until end of turn."
)


SAIYAN_INVASION = make_sorcery(
    name="Saiyan Invasion",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Create three 2/2 red Saiyan Warrior creature tokens with haste."
)


OOZARU_RAMPAGE = make_sorcery(
    name="Oozaru Rampage",
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    text="Create an 8/8 red Saiyan Ape creature token with trample. It must attack each combat if able."
)


ZENKAI_BOOST = make_sorcery(
    name="Zenkai Boost",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Put two +1/+1 counters on target Saiyan creature you control. If that creature has 4 or more +1/+1 counters, it gains haste until end of turn."
)


# Red Enchantments

def saiyan_pride_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 2, 1, "Saiyan", include_self=True)
    return itcs

SAIYAN_PRIDE = make_enchantment(
    name="Saiyan Pride",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Saiyan creatures you control get +2/+1.",
    setup_interceptors=saiyan_pride_setup,
)


SUPER_SAIYAN_AURA = make_enchantment(
    name="Super Saiyan Aura",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Enchant creature. Enchanted creature gets +2/+2 and has haste. When enchanted creature dies, Super Saiyan Aura deals 3 damage to any target."
)


BATTLE_RAGE = make_enchantment(
    name="Battle Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Whenever a creature you control attacks alone, it gets +2/+0 until end of turn."
)


# =============================================================================
# GREEN CARDS - NAMEKIANS, REGENERATION, NATURE
# =============================================================================

def piccolo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_upkeep_trigger(obj, counter_effect)]

PICCOLO_NAMEKIAN_WARRIOR = make_creature(
    name="Piccolo, Namekian Warrior",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Z-Fighter", "Warrior"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, put a +1/+1 counter on Piccolo, Namekian Warrior.",
    setup_interceptors=piccolo_setup,
)


def nail_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Namekian", include_self=False)
    return itcs

NAIL = make_creature(
    name="Nail, Namekian Elite",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Warrior"},
    supertypes={"Legendary"},
    text="Other Namekian creatures you control get +1/+1.",
    setup_interceptors=nail_setup,
)


def dende_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def heal_ability(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ACTIVATE and
                event.payload.get('source') == obj.id and
                event.payload.get('ability') == 'heal')

    def heal_effect(event: Event, state: GameState) -> InterceptorResult:
        target = event.payload.get('target')
        events = [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
        if target:
            events.append(Event(type=EventType.COUNTER_ADDED, payload={
                'object_id': target, 'counter_type': 'heal', 'regenerate': True
            }, source=obj.id))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=heal_ability, handler=heal_effect,
        duration='while_on_battlefield'
    )]

DENDE = make_creature(
    name="Dende, Young Healer",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Cleric"},
    supertypes={"Legendary"},
    setup_interceptors=dende_setup
)


def guru_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                'Namekian' in game_obj.characteristics.subtypes and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(type=EventType.COUNTER_ADDED, payload={
                    'object_id': obj_id, 'counter_type': '+1/+1', 'amount': 1
                }, source=obj.id))
        return events

    from src.cards.interceptor_helpers import make_etb_trigger
    return [make_etb_trigger(obj, etb_effect)]

GURU = make_creature(
    name="Guru, Grand Elder",
    power=0, toughness=6,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Elder"},
    supertypes={"Legendary"},
    setup_interceptors=guru_setup
)


NAMEKIAN_WARRIOR = make_creature(
    name="Namekian Warrior",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Warrior"}
)


NAMEKIAN_HEALER = make_creature(
    name="Namekian Healer",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Cleric"}
)


NAMEKIAN_ELDER = make_creature(
    name="Namekian Elder",
    power=2, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Elder"}
)


def namekian_child_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_gain_life(obj, 1)
    return [itc]

NAMEKIAN_CHILD = make_creature(
    name="Namekian Child",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Namekian"},
    text="When Namekian Child enters, you gain 1 life.",
    setup_interceptors=namekian_child_setup,
)


GIANT_NAMEKIAN = make_creature(
    name="Giant Namekian",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Namekian", "Giant"}
)


PORUNGA = make_creature(
    name="Porunga, Namekian Dragon",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dragon", "God"},
    supertypes={"Legendary"}
)


AJISA_TREE = make_creature(
    name="Ajisa Tree",
    power=0, toughness=5,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"}
)


def namek_frog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = death_draw(obj, 1)
    return [itc]

NAMEK_FROG = make_creature(
    name="Namek Frog",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Frog"},
    text="When Namek Frog dies, draw a card.",
    setup_interceptors=namek_frog_setup,
)


def namek_crab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_gain_life(obj, 2)
    return [itc]

NAMEK_CRAB = make_creature(
    name="Namek Crab",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Crab"},
    text="When Namek Crab enters, you gain 2 life.",
    setup_interceptors=namek_crab_setup,
)


NAMEK_FISH = make_creature(
    name="Giant Namek Fish",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Fish"}
)


# Green Instants

SPECIAL_BEAM_CANNON = make_instant(
    name="Special Beam Cannon",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Special Beam Cannon deals 5 damage to target creature. If you control Piccolo, it deals 7 damage instead."
)


NAMEKIAN_REGENERATION = make_instant(
    name="Namekian Regeneration",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Regenerate target creature. Put a +1/+1 counter on it."
)


HELLZONE_GRENADE = make_instant(
    name="Hellzone Grenade",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Hellzone Grenade deals 4 damage divided as you choose among any number of target creatures."
)


MASENKO = make_instant(
    name="Masenko",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Masenko deals 3 damage to target creature or planeswalker."
)


FUSE = make_instant(
    name="Fuse",
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    text="Exile two target creatures you control, then create a creature token that's a copy of one of them except it has the combined power and toughness of both."
)


NATURE_BARRIER = make_instant(
    name="Nature's Barrier",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gains hexproof and indestructible until end of turn. Untap it."
)


# Green Sorceries

NAMEKIAN_FUSION = make_sorcery(
    name="Namekian Fusion",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="As an additional cost, exile two Namekian creatures you control. Create a Namekian creature token with power and toughness each equal to the total power and toughness of the exiled creatures. It has all abilities of the exiled creatures."
)


REGROWTH = make_sorcery(
    name="Regrowth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Return target card from your graveyard to your hand."
)


DRAGON_BALL_SUMMON = make_sorcery(
    name="Dragon Ball Summon",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Search your library for a Dragon creature card, put it onto the battlefield, then shuffle. You gain 5 life."
)


PLANET_NAMEK = make_sorcery(
    name="Planet Namek's Blessing",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield, then shuffle. You gain 3 life."
)


# Green Enchantments

def namekian_resilience_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    filter_fn = ih.creatures_with_subtype(obj, "Namekian")
    return [ih.make_keyword_grant(obj, ['hexproof'], filter_fn)]

NAMEKIAN_RESILIENCE = make_enchantment(
    name="Namekian Resilience",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Namekian creatures you control have hexproof.",
    setup_interceptors=namekian_resilience_setup,
)


HEALING_AURA = make_enchantment(
    name="Healing Aura",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, you gain 2 life. Whenever you gain life, you may put a +1/+1 counter on target creature you control."
)


NAMEK_WILDS = make_enchantment(
    name="Namek Wilds",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever a creature enters under your control, you gain 1 life. {2}{G}: Create a 2/2 green Namekian Warrior creature token."
)


# =============================================================================
# MULTICOLOR CARDS - FUSIONS AND MAJOR CHARACTERS
# =============================================================================

def vegito_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    interceptors.append(make_power_level_trigger(obj, "combat_damage"))
    return interceptors

VEGITO = make_creature(
    name="Vegito, Ultimate Fusion",
    power=7, toughness=7,
    mana_cost="{2}{W}{W}{R}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Saiyan", "Z-Fighter", "Fusion"},
    supertypes={"Legendary"},
    setup_interceptors=vegito_setup
)


def gogeta_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = attack_deal_damage(obj, 3, "each_opponent")
    return [itc]

GOGETA = make_creature(
    name="Gogeta, Fusion Warrior",
    power=7, toughness=6,
    mana_cost="{2}{R}{R}{W}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Saiyan", "Z-Fighter", "Fusion"},
    supertypes={"Legendary"},
    text="Whenever Gogeta, Fusion Warrior attacks, it deals 3 damage to each opponent.",
    setup_interceptors=gogeta_setup,
)


def gotenks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_create_token(obj, 1, 1, "Super Ghost", count=3, colors={Color.WHITE})
    return [itc]

GOTENKS = make_creature(
    name="Gotenks, Young Fusion",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Saiyan", "Z-Fighter", "Fusion"},
    supertypes={"Legendary"},
    text="When Gotenks, Young Fusion enters, create three 1/1 white Super Ghost creature tokens.",
    setup_interceptors=gotenks_setup,
)


GOKU_SUPER_SAIYAN = make_creature(
    name="Goku, Super Saiyan",
    power=6, toughness=5,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Saiyan", "Z-Fighter"},
    supertypes={"Legendary"},
    abilities=[{'keyword': 'haste'}, {'keyword': 'trample'}],
    text="Haste, trample."
)


GOKU_ULTRA_INSTINCT = make_creature(
    name="Goku, Ultra Instinct",
    power=9, toughness=7,
    mana_cost="{4}{W}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Saiyan", "Z-Fighter"},
    supertypes={"Legendary"}
)


VEGETA_SUPER_SAIYAN = make_creature(
    name="Vegeta, Super Saiyan",
    power=6, toughness=5,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Saiyan", "Noble", "Warrior"},
    supertypes={"Legendary"},
    abilities=[{'keyword': 'haste'}, {'keyword': 'menace'}],
    text="Haste, menace."
)


GOHAN_SSJ2 = make_creature(
    name="Gohan, Super Saiyan 2",
    power=7, toughness=6,
    mana_cost="{3}{W}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Saiyan", "Z-Fighter", "Scholar"},
    supertypes={"Legendary"}
)


def beerus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def destroy_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': opp_id},
                source=obj.id,
                controller=obj.controller,
            )
            for opp_id in ih.all_opponents(obj, state)
        ]
    return [ih.make_upkeep_trigger(obj, destroy_effect)]

BEERUS = make_creature(
    name="Beerus, God of Destruction",
    power=8, toughness=6,
    mana_cost="{4}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"God", "Cat"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, destroy target permanent an opponent controls.",
    setup_interceptors=beerus_setup,
)


WHIS = make_creature(
    name="Whis, Angel Attendant",
    power=4, toughness=6,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Angel"},
    supertypes={"Legendary"}
)


def hit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_damage_trigger

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        target_obj = state.objects.get(target)
        if target_obj and CardType.CREATURE in target_obj.characteristics.types:
            return [Event(type=EventType.TAP, payload={'object_id': target}, source=obj.id)]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

HIT = make_creature(
    name="Hit, The Assassin",
    power=5, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Alien", "Assassin"},
    supertypes={"Legendary"},
    setup_interceptors=hit_setup
)


JIREN = make_creature(
    name="Jiren, The Strongest",
    power=10, toughness=10,
    mana_cost="{5}{W}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Alien", "Warrior"},
    supertypes={"Legendary"}
)


GOLDEN_FRIEZA = make_creature(
    name="Frieza, Golden Form",
    power=8, toughness=7,
    mana_cost="{4}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Alien", "Tyrant"},
    supertypes={"Legendary"}
)


MAJIN_VEGETA = make_creature(
    name="Vegeta, Majin",
    power=6, toughness=5,
    mana_cost="{2}{R}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Saiyan", "Noble", "Warrior"},
    supertypes={"Legendary"}
)


ANDROID_21 = make_creature(
    name="Android 21, Hunger Incarnate",
    power=5, toughness=5,
    mana_cost="{2}{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    subtypes={"Android", "Majin"},
    supertypes={"Legendary"}
)


KEFLA = make_creature(
    name="Kefla, Potara Fusion",
    power=6, toughness=5,
    mana_cost="{2}{R}{G}{W}",
    colors={Color.RED, Color.GREEN, Color.WHITE},
    subtypes={"Saiyan", "Fusion"},
    supertypes={"Legendary"}
)


GOKU_BLACK = make_creature(
    name="Goku Black, Zero Mortal Plan",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Saiyan", "God"},
    supertypes={"Legendary"}
)


ZAMASU = make_creature(
    name="Zamasu, Divine Justice",
    power=4, toughness=6,
    mana_cost="{2}{W}{B}{G}",
    colors={Color.WHITE, Color.BLACK, Color.GREEN},
    subtypes={"Kai", "God"},
    supertypes={"Legendary"}
)


SHENRON = make_creature(
    name="Shenron, Eternal Dragon",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dragon", "God"},
    supertypes={"Legendary"}
)


# =============================================================================
# ARTIFACTS
# =============================================================================

DRAGON_BALL_ONE = make_artifact(
    name="One-Star Dragon Ball",
    mana_cost="{1}",
    text="{T}: Add {C}. If you control all seven Dragon Balls, you may sacrifice them all and pay {7}: You win the game."
)

DRAGON_BALL_TWO = make_artifact(
    name="Two-Star Dragon Ball",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}: Scry 1."
)

DRAGON_BALL_THREE = make_artifact(
    name="Three-Star Dragon Ball",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}: You gain 2 life."
)

DRAGON_BALL_FOUR = make_artifact(
    name="Four-Star Dragon Ball",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}: Target creature gets +1/+1 until end of turn."
)

DRAGON_BALL_FIVE = make_artifact(
    name="Five-Star Dragon Ball",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}: Draw a card, then discard a card."
)

DRAGON_BALL_SIX = make_artifact(
    name="Six-Star Dragon Ball",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}: Target creature can't block this turn."
)

DRAGON_BALL_SEVEN = make_artifact(
    name="Seven-Star Dragon Ball",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}: Untap target permanent."
)


def senzu_bean_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def activate_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ACTIVATE and
                event.payload.get('source') == obj.id)

    def heal_effect(event: Event, state: GameState) -> InterceptorResult:
        target_creature = event.payload.get('target')
        events = [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 5}, source=obj.id),
            Event(type=EventType.ZONE_CHANGE, payload={'object_id': obj.id, 'to_zone_type': ZoneType.GRAVEYARD}, source=obj.id)
        ]
        if target_creature:
            events.append(Event(type=EventType.COUNTER_ADDED, payload={
                'object_id': target_creature, 'counter_type': '+1/+1', 'amount': 2
            }, source=obj.id))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=activate_filter, handler=heal_effect,
        duration='while_on_battlefield'
    )]

SENZU_BEAN = make_artifact(
    name="Senzu Bean",
    mana_cost="{1}",
    text="{T}, Sacrifice Senzu Bean: You gain 5 life and put two +1/+1 counters on target creature you control."
)


SCOUTER = make_equipment(
    name="Scouter",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+0. Whenever equipped creature attacks, scry 1."
)


POTARA_EARRINGS = make_artifact(
    name="Potara Earrings",
    mana_cost="{3}",
    text="{3}, {T}, Sacrifice Potara Earrings and two creatures you control: Create a creature token that's a copy of one of those creatures except it has base power and toughness equal to the total power and total toughness of both creatures. It has all abilities of both creatures."
)


FUSION_EARRINGS = make_artifact(
    name="Fusion Earrings",
    mana_cost="{2}",
    text="{4}, Exile Fusion Earrings and two Saiyan creatures you control: Search your library for a Fusion creature card, put it onto the battlefield, then shuffle."
)


GRAVITY_CHAMBER = make_artifact(
    name="Gravity Chamber",
    mana_cost="{3}",
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control. That creature can't attack this turn."
)


TIME_MACHINE = make_artifact(
    name="Time Machine",
    mana_cost="{4}",
    text="{2}, {T}: Exile target creature you control. Return it to the battlefield at the beginning of the next end step with two +1/+1 counters on it."
)


CAPSULE = make_artifact(
    name="Capsule",
    mana_cost="{1}",
    text="{2}, {T}, Sacrifice Capsule: Search your library for an artifact card with mana value 3 or less, put it onto the battlefield, then shuffle."
)


SPACE_POD = make_artifact(
    name="Saiyan Space Pod",
    mana_cost="{2}",
    subtypes={"Vehicle"},
    text="Flying. Crew 1. When Saiyan Space Pod enters, scry 1."
)


NIMBUS_CLOUD = make_artifact(
    name="Nimbus Cloud",
    mana_cost="{2}",
    subtypes={"Vehicle"},
    text="Flying. Crew 1. Nimbus Cloud can only be crewed by creatures with no -1/-1 counters."
)


DRAGON_RADAR = make_artifact(
    name="Dragon Radar",
    mana_cost="{2}",
    text="{1}, {T}: Look at the top five cards of your library. You may reveal an artifact card from among them and put it into your hand. Put the rest on the bottom of your library in any order."
)


Z_SWORD = make_equipment(
    name="Z-Sword",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has vigilance. If equipped creature is a Saiyan, it also has first strike."
)


POWER_POLE = make_equipment(
    name="Power Pole",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1 and has reach."
)


TURTLE_SHELL = make_equipment(
    name="Turtle Shell",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +0/+3. At the beginning of your upkeep, put a +1/+1 counter on equipped creature."
)


WEIGHTED_CLOTHING = make_equipment(
    name="Weighted Clothing",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets -1/-0. When Weighted Clothing becomes unattached, put two +1/+1 counters on the creature it was attached to."
)


# =============================================================================
# LANDS
# =============================================================================

KAME_HOUSE = make_land(
    name="Kame House",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a Z-Fighter.",
    supertypes={"Legendary"}
)


CAPSULE_CORP = make_land(
    name="Capsule Corporation",
    text="{T}: Add {C}. {2}, {T}: Create a Treasure token.",
    supertypes={"Legendary"}
)


HYPERBOLIC_TIME_CHAMBER = make_land(
    name="Hyperbolic Time Chamber",
    text="{T}: Add {C}. {3}, {T}: Put a +1/+1 counter on target creature you control. You can't activate this ability more than once each turn.",
    supertypes={"Legendary"}
)


PLANET_NAMEK_LAND = make_land(
    name="Planet Namek",
    text="{T}: Add {G}. Namekian creatures you control have '{G}: Regenerate this creature.'",
    supertypes={"Legendary"}
)


PLANET_VEGETA = make_land(
    name="Planet Vegeta",
    text="{T}: Add {R}. Saiyan creatures you control get +0/+1.",
    supertypes={"Legendary"}
)


LOOKOUT = make_land(
    name="The Lookout",
    text="{T}: Add {W}. {2}{W}, {T}: Scry 2.",
    supertypes={"Legendary"}
)


WORLD_TOURNAMENT_ARENA = make_land(
    name="World Tournament Arena",
    text="{T}: Add {C}. {4}, {T}: Target creature you control fights target creature you don't control."
)


KORIN_TOWER = make_land(
    name="Korin Tower",
    text="{T}: Add {W}. {2}, {T}: You gain 2 life.",
    supertypes={"Legendary"}
)


FRIEZA_SPACESHIP = make_land(
    name="Frieza's Spaceship",
    text="{T}: Add {B}. {2}{B}, {T}: Target creature gets -1/-1 until end of turn."
)


CELL_GAMES_ARENA = make_land(
    name="Cell Games Arena",
    text="{T}: Add {C}. Creatures can't have hexproof or shroud. (Perfect battlefield.)",
    supertypes={"Legendary"}
)


KING_KAIS_PLANET = make_land(
    name="King Kai's Planet",
    text="{T}: Add {W} or {U}. Creatures you control have 'At the beginning of your upkeep, scry 1.'",
    supertypes={"Legendary"}
)


SERPENT_ROAD = make_land(
    name="Snake Way",
    text="{T}: Add {C}. {1}, {T}: Target creature gains haste until end of turn."
)


MAJIN_BUU_HOUSE = make_land(
    name="Majin Buu's House",
    text="{T}: Add {B} or {R}. Majin creatures you control get +1/+0."
)


RED_RIBBON_HQ = make_land(
    name="Red Ribbon Army HQ",
    text="{T}: Add {U}. Android creatures you control have '{T}: Add {U}.'",
    supertypes={"Legendary"}
)


OTHERWORLD_ARENA = make_land(
    name="Otherworld Tournament Arena",
    text="{T}: Add {W}. Spirit creatures you control get +1/+1."
)


# Basic Lands

PLAINS_DBZ = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"}
)


ISLAND_DBZ = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"}
)


SWAMP_DBZ = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"}
)


MOUNTAIN_DBZ = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"}
)


FOREST_DBZ = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"}
)


# =============================================================================
# ADDITIONAL INSTANTS - KI ATTACKS
# =============================================================================

KAMEHAMEHA = make_instant(
    name="Kamehameha",
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Kamehameha deals 5 damage to any target. If you control Goku, it deals 7 damage instead and you gain 3 life."
)


SPIRIT_BOMB = make_sorcery(
    name="Spirit Bomb",
    mana_cost="{4}{W}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Spirit Bomb deals damage to target creature equal to the total power of creatures you control. If that creature would die this turn, exile it instead."
)


DESTRUCTO_DISC = make_instant(
    name="Destructo Disc",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Destroy target creature with power 4 or less. If you control Krillin, destroy target creature instead."
)


DEATH_BALL = make_instant(
    name="Death Ball",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Death Ball deals 6 damage to any target. If that target is a creature and it dies this turn, exile it."
)


CANDY_BEAM = make_instant(
    name="Candy Beam",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Turn target creature into a 0/1 colorless Candy artifact creature token until end of turn. (It loses all abilities.)"
)


HUMAN_EXTINCTION_ATTACK = make_sorcery(
    name="Human Extinction Attack",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures with toughness 3 or less. Each opponent loses 2 life for each creature they controlled that was destroyed this way."
)


SOLAR_KAMEHAMEHA = make_instant(
    name="Solar Kamehameha",
    mana_cost="{3}{W}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Solar Kamehameha deals 6 damage to any target. You gain 3 life."
)


FINAL_EXPLOSION = make_sorcery(
    name="Final Explosion",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, sacrifice a creature. Final Explosion deals damage equal to that creature's power to each creature and each opponent."
)


OMEGA_BLASTER = make_instant(
    name="Omega Blaster",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Omega Blaster deals 5 damage to target creature. If it would die this turn, exile it instead."
)


ERASER_CANNON = make_instant(
    name="Eraser Cannon",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Eraser Cannon deals 4 damage to target creature. That creature can't regenerate this turn."
)


# =============================================================================
# SPICE PASS PHASE A — Format-Defining DBZ Cards
# =============================================================================
# Mirrors the Star Wars spice pass (.claude/plans/proud-singing-sonnet.md).
# Phase A here = cards built within current engine capability (W1-W7 + Phase-B
# helpers from the SW pass: was_destroyed_this_turn, condition_fn on
# make_cost_reduction, precondition_fn on make_activated_ability).


# --- Future Sword --- {2} Equipment, Uncommon (Trunks combo target)
FUTURE_SWORD = make_equipment(
    name="Future Sword",
    mana_cost="{2}",
    subtypes={"Sword"},  # Equipment subtype also gets "Sword" so Trunks's
                          # attach trigger filter can recognise it.
    text=(
        "Equipped creature gets +2/+2 and has haste. Equip {1}."
    ),
    setup_interceptors=ih.make_equipment_setup(
        power_mod=2, toughness_mod=2,
        keywords=["haste"],
        equip_cost="{1}",
    ),
)


# --- Master Roshi's Training Hall --- Land, Uncommon (gated tutor)
def master_roshi_hall_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {2}, {T}: tutor a Z-Fighter or Monk creature ≤MV3 (only when
    you control ≤3 creatures)."""

    def mana_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'C': 1}},
            source=o.id,
        )]

    ih.make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_effect,
        description="Tap: Add {C}.",
    )

    def gate_few_creatures(o: GameObject, st: GameState) -> bool:
        cnt = sum(
            1 for x in st.objects.values()
            if x.zone == ZoneType.BATTLEFIELD
            and x.controller == o.controller
            and CardType.CREATURE in (x.characteristics.types or set())
        )
        return cnt <= 3

    def tutor_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': o.controller,
                'subtypes_any': ['Z-Fighter', 'Monk'],
                'card_type': 'creature',
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=o.id,
        )]

    ih.make_activated_ability(
        obj,
        cost="{2}, {T}",
        effect_fn=tutor_effect,
        description="{2}, {T}: tutor a Z-Fighter or Monk ≤ MV 3.",
        precondition_fn=gate_few_creatures,
    )
    return []

MASTER_ROSHIS_TRAINING_HALL = make_land(
    name="Master Roshi's Training Hall",
    text=(
        "{T}: Add {C}. "
        "{2}, {T}: Search your library for a Z-Fighter or Monk creature card "
        "with mana value 3 or less, reveal it, put it into your hand, then "
        "shuffle. Activate this ability only if you control three or fewer "
        "creatures."
    ),
    supertypes={"Legendary"},
    setup_interceptors=master_roshi_hall_setup,
)


# --- Capsule Corp R&D --- {1}{U} Legendary Artifact, Rare (artifact tutor engine)
def capsule_corp_rnd_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {U}. {2}, {T}: peek 3, may grab artifact or Scientist creature.
    Whenever you cast an artifact spell, scry 1."""

    def mana_blue(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'U': 1}},
            source=o.id,
        )]

    ih.make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_blue,
        description="Tap: Add {U}.",
    )

    def peek_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Look at top 3, optionally grab an artifact or Scientist creature.
        # Engine: SEARCH_LIBRARY restricted to top 3 isn't natively supported,
        # so we approximate with REVEAL_TOP + a SEARCH_LIBRARY with a
        # subtypes_any filter. Players will see the top 3 either way; the
        # search picks any matching card (we accept the imperfection that
        # the search isn't strictly "from the revealed set").
        return [
            Event(
                type=EventType.REVEAL_TOP,
                payload={'player': o.controller, 'count': 3},
                source=o.id,
            ),
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={
                    'player': o.controller,
                    'subtypes_any': ['Scientist'],
                    'destination': 'hand',
                    'min_count': 0,
                    'max_count': 1,
                    'reveal': True,
                },
                source=o.id,
            ),
        ]

    ih.make_activated_ability(
        obj,
        cost="{2}, {T}",
        effect_fn=peek_effect,
        description=(
            "{2}, {T}: Look at top 3 of your library; grab a Scientist creature."
        ),
    )

    def artifact_cast_filter(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        if event.controller != src.controller:
            return False
        cast_obj_id = event.payload.get('object_id') or event.payload.get('card_id')
        if not cast_obj_id:
            return False
        cast_obj = st.objects.get(cast_obj_id)
        if not cast_obj:
            return False
        return CardType.ARTIFACT in (cast_obj.characteristics.types or set())

    def scry_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]

    return [ih.make_spell_cast_trigger(obj, scry_effect, filter_fn=artifact_cast_filter)]

CAPSULE_CORP_RND = CardDefinition(
    name="Capsule Corp R&D",
    mana_cost="{1}{U}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        colors={Color.BLUE},
        supertypes={"Legendary"},
        mana_cost="{1}{U}",
    ),
    text=(
        "{T}: Add {U}. "
        "{2}, {T}: Look at the top three cards of your library; you may "
        "reveal an artifact or Scientist creature card from among them and "
        "put it into your hand. "
        "Whenever you cast an artifact spell, scry 1."
    ),
    setup_interceptors=capsule_corp_rnd_setup,
)


# --- Ginyu Force, Assemble! --- {3}{B}{R} Sorcery, Uncommon (tribal anchor)
def ginyu_assemble_resolve(targets: list, state: GameState) -> list[Event]:
    """Tutor up to two Ginyu Force creatures with haste EOT."""
    # Best-effort caster lookup (mirrors avatar_tla pattern).
    caster = None
    for o in state.objects.values():
        if (getattr(o.card_def, 'name', None) == "Ginyu Force, Assemble!"
                and o.zone == ZoneType.STACK):
            caster = o.controller
            break
    if not caster:
        for o in state.objects.values():
            if (getattr(o.card_def, 'name', None) == "Ginyu Force, Assemble!"
                    and o.zone == ZoneType.GRAVEYARD):
                caster = o.controller
                break
    if not caster:
        return []
    # Two SEARCH_LIBRARY events — each picks a Ginyu Force creature card and
    # puts it onto the battlefield tapped.
    events: list[Event] = []
    for _ in range(2):
        events.append(Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': caster,
                'subtype': 'Ginyu Force',
                'card_type': 'creature',
                'destination': 'battlefield',
                'tapped': True,
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source='ginyu_assemble',
        ))
    return events

GINYU_FORCE_ASSEMBLE = make_sorcery(
    name="Ginyu Force, Assemble!",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text=(
        "Search your library for up to two creature cards with subtype Ginyu "
        "Force, reveal them, put them onto the battlefield tapped, then shuffle."
    ),
    resolve=ginyu_assemble_resolve,
)


# --- Trunks, Sword of the Future --- {1}{R}{R} 3/2 Rare legendary creature
def trunks_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self haste; ETB tutors a Sword equipment; equip-of-Sword untaps Trunks
    and gives him double strike EOT."""

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_tutor_sword(event: Event, st: GameState) -> list[Event]:
        # Tutor a Sword equipment to battlefield.
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'subtype': 'Sword',
                'card_type': 'artifact',
                'destination': 'battlefield',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=obj.id,
        )]

    def attach_to_trunks_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACH:
            return False
        if event.payload.get('target') != obj.id:
            return False
        attaching_id = event.payload.get('source') or event.payload.get('attacher')
        if not attaching_id:
            return False
        attaching = st.objects.get(attaching_id)
        if not attaching:
            return False
        return 'Sword' in (attaching.characteristics.subtypes or set())

    def attach_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.UNTAP, payload={'object_id': obj.id}, source=obj.id),
                Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={
                        'object_id': obj.id,
                        'keyword': 'double_strike',
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                ),
            ],
        )

    sword_attach_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attach_to_trunks_filter,
        handler=attach_handler,
        duration='while_on_battlefield',
    )

    return [
        ih.make_keyword_grant(obj, ['haste'], affects_self),
        ih.make_etb_trigger(obj, etb_tutor_sword),
        sword_attach_trigger,
    ]

TRUNKS_SWORD_OF_FUTURE = make_creature(
    name="Trunks, Sword of the Future",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Z-Fighter", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "Haste. When Trunks enters, search your library for a Sword card, "
        "put it onto the battlefield, then shuffle. "
        "Whenever a Sword becomes attached to Trunks, untap him; he gains "
        "double strike until end of turn."
    ),
    setup_interceptors=trunks_sword_setup,
)


# --- Goku, Pure of Heart --- {2}{R}{G} 3/3 Mythic legendary creature
def goku_pure_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack +1/+1 counter, other-creature death +1/+1 counter, escalating
    keywords gated on counter thresholds."""

    def attack_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]

    def other_creature_death_filter(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        dead_id = event.payload.get('object_id')
        if not dead_id or dead_id == src.id:
            return False
        dead = st.objects.get(dead_id)
        if not dead or dead.controller != src.controller:
            return False
        return CardType.CREATURE in (dead.characteristics.types or set())

    def death_counter_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]

    # Threshold-gated keyword grants: filter returns True only when Goku has
    # the right number of +1/+1 counters AND the target IS Goku.
    def threshold_filter(threshold: int):
        def fn(target: GameObject, st: GameState) -> bool:
            if target.id != obj.id:
                return False
            return target.state.counters.get('+1/+1', 0) >= threshold
        return fn

    # 6-counter combat-damage trigger: draw 2 cards.
    def six_counter_combat_dmg(event: Event, st: GameState) -> list[Event]:
        if obj.state.counters.get('+1/+1', 0) < 6:
            return []
        target = event.payload.get('target')
        if not target or target not in st.players:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 2},
            source=obj.id,
        )]

    return [
        ih.make_attack_trigger(obj, attack_effect),
        ih.make_death_trigger(obj, death_counter_effect, filter_fn=other_creature_death_filter),
        # Threshold-3: trample + double_strike.
        ih.make_keyword_grant(obj, ['trample', 'double_strike'], threshold_filter(3)),
        # Threshold-6: flying.
        ih.make_keyword_grant(obj, ['flying'], threshold_filter(6)),
        # Threshold-6 combat-damage draw.
        ih.make_damage_trigger(obj, six_counter_combat_dmg, combat_only=True),
    ]

GOKU_PURE_OF_HEART = make_creature(
    name="Goku, Pure of Heart",
    power=3, toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Saiyan", "Z-Fighter"},
    supertypes={"Legendary"},
    text=(
        "Whenever Goku attacks, put a +1/+1 counter on him. "
        "Whenever another creature you control dies, put a +1/+1 counter on Goku. "
        "As long as Goku has 3 or more +1/+1 counters, he has trample and "
        "double strike. As long as he has 6 or more, he has flying and "
        "\"Whenever Goku deals combat damage to a player, draw two cards.\""
    ),
    setup_interceptors=goku_pure_setup,
)


# =============================================================================
# SPICE PASS PHASE B — Cards using W7 (cast-from-zone) and existing engine
# =============================================================================


# --- Senzu Bean Reanimator --- {1}{G}{W} Sorcery, Rare
def senzu_reanimator_resolve(targets: list, state: GameState) -> list[Event]:
    """Return target creature ≤MV4 from graveyard to battlefield with haste +
    indestructible until end of turn."""
    if not targets:
        return []
    target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.GRAVEYARD:
        return []
    if CardType.CREATURE not in (target.characteristics.types or set()):
        return []
    # MV ≤ 4 check.
    cost_str = (
        target.characteristics.mana_cost
        or (target.card_def.mana_cost if target.card_def else "")
        or "{0}"
    )
    try:
        from src.engine import ManaCost
        if ManaCost.parse(cost_str).mana_value > 4:
            return []
    except Exception:
        pass
    return [
        Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': target_id,
                'destination': 'battlefield',
                'controller': target.controller,
            },
            source=target_id,
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'haste', 'duration': 'end_of_turn'},
            source=target_id,
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
            source=target_id,
        ),
    ]

SENZU_BEAN_REANIMATOR = make_sorcery(
    name="Senzu Bean Reanimator",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text=(
        "Return target creature card with mana value 4 or less from your "
        "graveyard to the battlefield. It gains haste and indestructible "
        "until end of turn."
    ),
    resolve=senzu_reanimator_resolve,
)


# --- Hyperbolic Time Chamber, Refurbished --- {2} Legendary Artifact, Rare
def hyperbolic_chamber_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {4}, {T}, exile two creature cards from your graveyard:
    take an extra turn after this one."""

    def mana_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'C': 1}},
            source=o.id,
        )]

    ih.make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_effect,
        description="Tap: Add {C}.",
    )

    def extra_turn_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Cost: {4}, {T}, plus exile two graveyard creature cards (the two
        # targets). Verify each target is in own graveyard and a creature.
        gy_ids = []
        for t in targets:
            tid = t.object_id if hasattr(t, 'object_id') else t
            tobj = st.objects.get(tid)
            if not tobj or tobj.zone != ZoneType.GRAVEYARD:
                continue
            if tobj.controller != o.controller:
                continue
            if CardType.CREATURE not in (tobj.characteristics.types or set()):
                continue
            gy_ids.append(tid)
        if len(gy_ids) < 2:
            return []
        events: list[Event] = []
        for gy_id in gy_ids[:2]:
            events.append(Event(
                type=EventType.EXILE,
                payload={'object_id': gy_id},
                source=o.id,
            ))
        events.append(Event(
            type=EventType.EXTRA_TURN,
            payload={'player': o.controller},
            source=o.id,
        ))
        return events

    ih.make_activated_ability(
        obj,
        cost="{4}, {T}",
        effect_fn=extra_turn_effect,
        description=(
            "{4}, {T}, exile two creature cards from your graveyard: "
            "take an extra turn after this one."
        ),
        targets_required=2,
        target_kind="creature",
    )

    return []

HYPERBOLIC_TIME_CHAMBER_REFURBISHED = CardDefinition(
    name="Hyperbolic Time Chamber, Refurbished",
    mana_cost="{2}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        supertypes={"Legendary"},
        mana_cost="{2}",
    ),
    text=(
        "{T}: Add {C}. "
        "{4}, {T}, exile two creature cards from your graveyard: Take an "
        "extra turn after this one."
    ),
    setup_interceptors=hyperbolic_chamber_setup,
)


# =============================================================================
# SPICE PASS v2 EXPANSION — 7 NEW format-defining picks
# =============================================================================
# Builds on Phase A/B above. Targets the gaps surfaced by the 2026-05-18
# depth audit: missing Dragon Balls assembly payoff, unwired flagship
# mythics (Shenron / Bardock / Future Trunks / Goku UI), and a saga slot.
# All names are NEW (no collision with existing DBZ legendaries — the
# originals stay untouched).


# --- Shenron, Wish Granter --- {4}{G}{U}{B} 7/7 Mythic Legendary Dragon
# The Dragon Ball assembly payoff. ETB scales with Dragon Ball count.
# Pattern 11 (build-around) + pattern 3 (snowball value).
def shenron_wish_granter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: count Dragon Balls you control. If 7+, take an extra turn and draw
    7. Else draw cards = number of Dragon Balls you control + scry 3."""

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def _count_dragon_balls(ctrl_id: str, st: GameState) -> int:
        bf = st.zones.get('battlefield')
        if not bf:
            return 0
        n = 0
        for oid in bf.objects:
            o = st.objects.get(oid)
            if not o or o.controller != ctrl_id:
                continue
            nm = (o.card_def.name if o.card_def else o.characteristics.name or "")
            if "Dragon Ball" in nm and CardType.ARTIFACT in (o.characteristics.types or set()):
                n += 1
        return n

    def etb_wish(event: Event, st: GameState) -> list[Event]:
        n_balls = _count_dragon_balls(obj.controller, st)
        events: list[Event] = []
        if n_balls >= 7:
            # Wish granted: draw 7, take an extra turn.
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 7},
                source=obj.id,
            ))
            events.append(Event(
                type=EventType.EXTRA_TURN,
                payload={'player': obj.controller},
                source=obj.id,
            ))
        else:
            # Partial wish: draw N + scry 3.
            if n_balls > 0:
                events.append(Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': n_balls},
                    source=obj.id,
                ))
            events.append(Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 3},
                source=obj.id,
            ))
        return events

    return [
        ih.make_keyword_grant(obj, ['flying', 'trample'], affects_self),
        ih.make_etb_trigger(obj, etb_wish),
    ]

SHENRON_WISH_GRANTER = make_creature(
    name="Shenron, Wish Granter",
    power=7, toughness=7,
    mana_cost="{4}{G}{U}{B}",
    colors={Color.GREEN, Color.BLUE, Color.BLACK},
    subtypes={"Dragon", "God"},
    supertypes={"Legendary"},
    text=(
        "Flying, trample. When Shenron enters, count the Dragon Ball artifacts "
        "you control. If seven or more, draw seven cards and take an extra turn "
        "after this one. Otherwise, draw a card for each Dragon Ball you "
        "control, then scry 3."
    ),
    setup_interceptors=shenron_wish_granter_setup,
)


# --- Eternal Dragon's Wish --- {2}{U}{B}{G} Sorcery, Mythic
# Win-the-game card / Dragon Ball assembly tutor. Pattern 1+11.
def eternal_dragons_wish_resolve(targets: list, state: GameState) -> list[Event]:
    """If you control seven Dragon Balls, sacrifice them and win the game.
    Otherwise, search your library for a Dragon Ball artifact card and put it
    onto the battlefield."""
    caster = None
    for o in state.objects.values():
        if (getattr(o.card_def, 'name', None) == "Eternal Dragon's Wish"
                and o.zone in (ZoneType.STACK, ZoneType.GRAVEYARD)):
            caster = o.controller
            break
    if not caster:
        return []

    # Count Dragon Balls.
    bf = state.zones.get('battlefield')
    ball_ids: list[str] = []
    if bf:
        for oid in bf.objects:
            o = state.objects.get(oid)
            if not o or o.controller != caster:
                continue
            nm = (o.card_def.name if o.card_def else o.characteristics.name or "")
            if "Dragon Ball" in nm and CardType.ARTIFACT in (o.characteristics.types or set()):
                ball_ids.append(oid)

    if len(ball_ids) >= 7:
        # Wish: sacrifice all balls + win.
        events: list[Event] = []
        for ball_id in ball_ids[:7]:
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={'object_id': ball_id, 'player': caster},
                source='eternal_dragons_wish',
            ))
        events.append(Event(
            type=EventType.PLAYER_WINS,
            payload={'player': caster, 'reason': "Eternal Dragon's Wish granted"},
            source='eternal_dragons_wish',
        ))
        return events

    # Tutor a Dragon Ball.
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': caster,
            'name_contains': 'Dragon Ball',
            'card_type': 'artifact',
            'destination': 'battlefield',
            'min_count': 0,
            'max_count': 1,
            'reveal': True,
        },
        source='eternal_dragons_wish',
    )]

ETERNAL_DRAGONS_WISH = make_sorcery(
    name="Eternal Dragon's Wish",
    mana_cost="{2}{U}{B}{G}",
    colors={Color.BLUE, Color.BLACK, Color.GREEN},
    text=(
        "If you control seven Dragon Ball artifacts, sacrifice them — you win "
        "the game. Otherwise, search your library for a Dragon Ball artifact "
        "card, put it onto the battlefield, then shuffle."
    ),
    resolve=eternal_dragons_wish_resolve,
)


# --- The Saiyan Saga --- {1}{R}{R} Saga, Rare
# 3-chapter tribal payoff for Saiyan/Z-Fighter package. Pattern 4 + 11.
def _saiyan_saga_ch_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Tutor a Saiyan creature card with mana value 3 or less."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'subtype': 'Saiyan',
            'card_type': 'creature',
            'destination': 'hand',
            'min_count': 0,
            'max_count': 1,
            'reveal': True,
        },
        source=saga_obj.id,
    )]


def _saiyan_saga_ch_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Put a +1/+1 counter on each Saiyan you control."""
    events: list[Event] = []
    for o in list(state.objects.values()):
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if o.controller != saga_obj.controller:
            continue
        if 'Saiyan' not in (o.characteristics.subtypes or set()):
            continue
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
            source=saga_obj.id,
        ))
    return events


def _saiyan_saga_ch_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Each opponent loses life equal to the number of Saiyans you
    control. You gain that much life."""
    n_saiyans = 0
    for o in state.objects.values():
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if o.controller != saga_obj.controller:
            continue
        if 'Saiyan' not in (o.characteristics.subtypes or set()):
            continue
        n_saiyans += 1
    if n_saiyans <= 0:
        return []
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': pid, 'amount': -n_saiyans},
            source=saga_obj.id,
        ))
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': saga_obj.controller, 'amount': n_saiyans},
        source=saga_obj.id,
    ))
    return events


def saiyan_saga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_saga_setup(
        obj,
        {
            1: _saiyan_saga_ch_i,
            2: _saiyan_saga_ch_ii,
            3: _saiyan_saga_ch_iii,
        },
    )

THE_SAIYAN_SAGA = CardDefinition(
    name="The Saiyan Saga",
    mana_cost="{1}{R}{R}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.RED},
        mana_cost="{1}{R}{R}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Search your library for a Saiyan creature card, reveal it, put "
        "it into your hand, then shuffle.\n"
        "II — Put a +1/+1 counter on each Saiyan you control.\n"
        "III — Each opponent loses life equal to the number of Saiyans you "
        "control. You gain that much life."
    ),
    setup_interceptors=saiyan_saga_setup,
)


# --- Bardock, Father of Saiyans --- {2}{R}{R} 4/3 Rare Legendary Saiyan Seer
# Prescient seer that scries on every Saiyan ETB. Snowball draw on combat
# damage. Pattern 3 (snowball value engine) + 11 (tribal payoff).
def bardock_father_of_saiyans_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 3, reveal Saiyan from top to hand. Other Saiyan ETB: scry 1.
    Whenever Bardock deals combat damage to a player, draw a card."""

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_self_effect(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 3},
                source=obj.id,
            ),
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={
                    'player': obj.controller,
                    'subtype': 'Saiyan',
                    'card_type': 'creature',
                    'destination': 'hand',
                    'min_count': 0,
                    'max_count': 1,
                    'reveal': True,
                },
                source=obj.id,
            ),
        ]

    def other_saiyan_etb_filter(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if not entering_id or entering_id == src.id:
            return False
        entering = st.objects.get(entering_id)
        if not entering or entering.controller != src.controller:
            return False
        return 'Saiyan' in (entering.characteristics.subtypes or set())

    def scry_one(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]

    def combat_damage_draw(event: Event, st: GameState) -> list[Event]:
        target = event.payload.get('target')
        if not target or target not in st.players:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]

    return [
        ih.make_etb_trigger(obj, etb_self_effect),
        ih.make_etb_trigger(obj, scry_one, filter_fn=other_saiyan_etb_filter),
        ih.make_damage_trigger(obj, combat_damage_draw, combat_only=True),
    ]

BARDOCK_FATHER_OF_SAIYANS = make_creature(
    name="Bardock, Father of Saiyans",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Saiyan", "Warrior", "Seer"},
    supertypes={"Legendary"},
    text=(
        "When Bardock enters, scry 3, then search your library for a Saiyan "
        "creature card, reveal it, put it into your hand, then shuffle. "
        "Whenever another Saiyan you control enters, scry 1. "
        "Whenever Bardock deals combat damage to a player, draw a card."
    ),
    setup_interceptors=bardock_father_of_saiyans_setup,
)


# --- Future Trunks, Tomorrow's Hope --- {2}{U}{R} 3/3 Rare Legendary
# Saiyan Time Traveler. Tutoring + selective recursion. Pattern 7 + 8.
def future_trunks_tomorrow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste self. ETB: tutor any sorcery card ≤MV4 to hand. Whenever Trunks
    attacks, return target creature with mana value 3 or less from your
    graveyard to your hand."""

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_tutor_sorcery(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'card_type': 'sorcery',
                'max_mana_value': 4,
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=obj.id,
        )]

    def attack_recur_effect(event: Event, st: GameState) -> list[Event]:
        # Find smallest creature in own graveyard with MV ≤ 3 and return it.
        gy = st.zones.get(f'graveyard_{obj.controller}')
        if not gy:
            return []
        candidates: list[tuple[int, str]] = []
        for cid in gy.objects:
            c = st.objects.get(cid)
            if not c:
                continue
            if CardType.CREATURE not in (c.characteristics.types or set()):
                continue
            cost_str = (
                c.characteristics.mana_cost
                or (c.card_def.mana_cost if c.card_def else "")
                or "{0}"
            )
            try:
                from src.engine import ManaCost
                mv = ManaCost.parse(cost_str).mana_value
            except Exception:
                mv = 0
            if mv > 3:
                continue
            candidates.append((mv, cid))
        if not candidates:
            return []
        # Pick the lowest-MV candidate deterministically.
        candidates.sort(key=lambda kv: kv[0])
        _, picked = candidates[0]
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': picked,
                'destination': 'hand',
                'controller': obj.controller,
            },
            source=obj.id,
        )]

    return [
        ih.make_keyword_grant(obj, ['haste'], affects_self),
        ih.make_etb_trigger(obj, etb_tutor_sorcery),
        ih.make_attack_trigger(obj, attack_recur_effect),
    ]

FUTURE_TRUNKS_TOMORROW = make_creature(
    name="Future Trunks, Tomorrow's Hope",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Saiyan", "Z-Fighter", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "Haste. When Future Trunks enters, search your library for a sorcery "
        "card with mana value 4 or less, reveal it, put it into your hand, "
        "then shuffle. Whenever Future Trunks attacks, you may return a "
        "creature card with mana value 3 or less from your graveyard to your "
        "hand."
    ),
    setup_interceptors=future_trunks_tomorrow_setup,
)


# --- Goku, Ultra Instinct Sign --- {3}{W}{U} 4/5 Mythic Legendary Saiyan God
# Endgame board-controlling mythic. Pattern 2 (hard to interact) + 9 (tempo
# theft). Static ward + own-turn-end untap + counters from being targeted.
def goku_ultra_instinct_sign_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, vigilance, ward {2}. Whenever Goku becomes the target of a
    spell or ability, put a +1/+1 counter on him and untap him. At the
    beginning of your end step, if Goku has 4+ +1/+1 counters, take an
    extra turn (one-shot per game)."""

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    # ward {2}: counter targeting unless paid.
    ward_iceptor = ih.make_ward(obj, mana_cost="{2}")

    # Targeting trigger: when Goku is targeted, +1/+1 counter + untap him.
    def targeting_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.TARGET_CHOSEN:
            return False
        if event.payload.get('target_id') != obj.id:
            return False
        return True

    def targeting_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id,
                ),
                Event(type=EventType.UNTAP, payload={'object_id': obj.id}, source=obj.id),
            ],
        )

    target_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=targeting_filter,
        handler=targeting_handler,
        duration='while_on_battlefield',
    )

    # End step extra-turn trigger (one-shot, gated by counters).
    def end_step_effect(event: Event, st: GameState) -> list[Event]:
        if getattr(obj.state, '_ui_sign_extra_turn_fired', False):
            return []
        if obj.state.counters.get('+1/+1', 0) < 4:
            return []
        # Mark fired (one-shot).
        setattr(obj.state, '_ui_sign_extra_turn_fired', True)
        return [Event(
            type=EventType.EXTRA_TURN,
            payload={'player': obj.controller},
            source=obj.id,
        )]

    return [
        ih.make_keyword_grant(obj, ['flying', 'vigilance'], affects_self),
        ward_iceptor,
        target_trigger,
        ih.make_end_step_trigger(obj, end_step_effect),
    ]

GOKU_ULTRA_INSTINCT_SIGN = make_creature(
    name="Goku, Ultra Instinct Sign",
    power=4, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Saiyan", "Z-Fighter", "God"},
    supertypes={"Legendary"},
    text=(
        "Flying, vigilance, ward {2}. Whenever Goku becomes the target of a "
        "spell or ability, put a +1/+1 counter on him and untap him. "
        "At the beginning of your end step, if Goku has four or more +1/+1 "
        "counters, take an extra turn after this one. (This ability triggers "
        "only once each game.)"
    ),
    setup_interceptors=goku_ultra_instinct_sign_setup,
)


# --- Kame House, Master's Refuge --- Legendary Land
# Z-Fighter tutor with gated activation. Pattern 7 (tutoring) + 11.
def kame_house_refuge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {W} or {U}. {2}, {T}: Search your library for a Z-Fighter
    creature card with mana value 3 or less, reveal it, put it into your
    hand, then shuffle. Activate only if you control a Z-Fighter."""

    def mana_w(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'W': 1}},
            source=o.id,
        )]

    def mana_u(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'U': 1}},
            source=o.id,
        )]

    ih.make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_w,
        description="Tap: Add {W}.",
    )
    ih.make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_u,
        description="Tap: Add {U}.",
    )

    def gate_has_z_fighter(o: GameObject, st: GameState) -> bool:
        for x in st.objects.values():
            if x.zone != ZoneType.BATTLEFIELD:
                continue
            if x.controller != o.controller:
                continue
            if 'Z-Fighter' in (x.characteristics.subtypes or set()):
                return True
        return False

    def tutor_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': o.controller,
                'subtype': 'Z-Fighter',
                'card_type': 'creature',
                'max_mana_value': 3,
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=o.id,
        )]

    ih.make_activated_ability(
        obj,
        cost="{2}, {T}",
        effect_fn=tutor_effect,
        description="{2}, {T}: Tutor a Z-Fighter creature ≤MV3.",
        precondition_fn=gate_has_z_fighter,
    )
    return []

KAME_HOUSE_MASTERS_REFUGE = make_land(
    name="Kame House, Master's Refuge",
    text=(
        "{T}: Add {W} or {U}. "
        "{2}, {T}: Search your library for a Z-Fighter creature card with "
        "mana value 3 or less, reveal it, put it into your hand, then "
        "shuffle. Activate this ability only if you control a Z-Fighter."
    ),
    supertypes={"Legendary"},
    setup_interceptors=kame_house_refuge_setup,
)


# =============================================================================
# CARD REGISTRY
# =============================================================================

DRAGON_BALL_CARDS = {
    # WHITE - EARTH'S DEFENDERS
    "Goku, Earth's Hero": GOKU_EARTHS_HERO,
    "Gohan, Hidden Power": GOHAN_HIDDEN_POWER,
    "Krillin, Brave Warrior": KRILLIN_BRAVE_WARRIOR,
    "Videl, Hero in Training": VIDEL_HERO_IN_TRAINING,
    "Supreme Kai, Divine Watcher": SUPREME_KAI,
    "King Kai, Martial Arts Master": KING_KAI,
    "Yamcha, Z-Fighter": YAMCHA_Z_FIGHTER,
    "Tien, Triclops Warrior": TIEN_TRICLOPS,
    "Chiaotzu, Psychic Fighter": CHIAOTZU,
    "Kami, Guardian of Earth": KAMI,
    "Mr. Popo, Eternal Servant": MR_POPO,
    "Earthling Fighter": EARTHLING_FIGHTER,
    "Capsule Corp Soldier": CAPSULE_CORP_SOLDIER,
    "World Tournament Champion": WORLD_CHAMPION,
    "Martial Artist": MARTIAL_ARTIST,
    "Otherworld Fighter": OTHERWORLD_FIGHTER,
    "Guardian Angel": GUARDIAN_ANGEL,
    "Turtle School Student": TURTLE_SCHOOL_STUDENT,
    "Crane School Student": CRANE_SCHOOL_STUDENT,
    "Senzu Heal": SENZU_HEAL,
    "Divine Protection": DIVINE_PROTECTION,
    "Heroic Rescue": INSTANT_TRANSMISSION_WHITE,
    "Energy Barrier": ENERGY_BARRIER,
    "Kiai Shout": KIAI_SHOUT,
    "Hope of Earth": HOPE_OF_EARTH,
    "Revival": REVIVAL,
    "Dragon Ball Wish": DRAGON_BALL_WISH,
    "Training Complete": TRAINING_COMPLETE,
    "World Tournament": WORLD_TOURNAMENT,
    "Z-Fighters Unite": Z_FIGHTERS_UNITE,
    "Otherworld": OTHERWORLD,
    "Kai's Blessing": KAIS_BLESSING,

    # BLUE - ANDROIDS, STRATEGY
    "Android 18, Infinite Energy": ANDROID_18,
    "Android 17, Nature's Protector": ANDROID_17,
    "Android 16, Gentle Giant": ANDROID_16,
    "Bulma, Genius Inventor": BULMA_GENIUS_INVENTOR,
    "Dr. Brief, Capsule Corp Founder": DR_BRIEF,
    "Android 19, Energy Absorber": ANDROID_19,
    "Android 20, Dr. Gero": ANDROID_20,
    "Capsule Corp Drone": CAPSULE_CORP_DRONE,
    "Repair Bot": REPAIR_BOT,
    "Analysis Drone": ANALYSIS_DRONE,
    "Capsule Corp Scientist": SCIENTIST,
    "Red Ribbon Scout": RED_RIBBON_SCOUT,
    "Android Prototype": ANDROID_PROTOTYPE,
    "Battle Android": BATTLE_ANDROID,
    "Energy Absorber": ENERGY_ABSORBER,
    "Ki Sense": KI_SENSE,
    "Energy Drain": ENERGY_DRAIN,
    "Afterimage": AFTERIMAGE,
    "Instant Transmission": INSTANT_TRANSMISSION_BLUE,
    "Photon Wave": PHOTON_WAVE,
    "Solar Flare": SOLAR_FLARE_TECHNIQUE,
    "Android Construction": ANDROID_CONSTRUCTION,
    "Technology Advancement": TECHNOLOGY_ADVANCEMENT,
    "Energy Analysis": ENERGY_ANALYSIS,
    "Red Ribbon Research": RED_RIBBON_RESEARCH,
    "Infinite Energy": INFINITE_ENERGY,
    "Capsule Technology": CAPSULE_TECHNOLOGY,
    "Energy Field": ENERGY_FIELD,

    # BLACK - FRIEZA FORCE, DESTRUCTION
    "Frieza, Galactic Emperor": FRIEZA_EMPEROR,
    "Cell, Perfect Form": CELL_PERFECT_FORM,
    "Kid Buu, Pure Destruction": KID_BUU,
    "Majin Buu, Innocent Evil": MAJIN_BUU,
    "Super Buu, Absorber": SUPER_BUU,
    "Zarbon, Frieza's Elite": ZARBON,
    "Dodoria, Frieza's Elite": DODORIA,
    "Captain Ginyu": GINYU,
    "Recoome": RECOOME,
    "Burter": BURTER,
    "Jeice": JEICE,
    "Guldo": GULDO,
    "Frieza Soldier": FRIEZA_SOLDIER,
    "Appule": APPULE,
    "Saibaman": SAIBAMAN,
    "Cell Junior": CELL_JUNIOR,
    "Majin Minion": MAJIN_MINION,
    "Dabura, Demon King": DABURA,
    "Babidi, Dark Wizard": BABIDI,
    "Death Beam": DEATH_BEAM,
    "Supernova": SUPERNOVA,
    "Finger Beam": FINGER_BEAM,
    "Absorption": ABSORPTION,
    "Vanish": VANISH,
    "Majin Curse": MAJIN_CURSE,
    "Planet Destruction": PLANET_DESTRUCTION,
    "Genocide Attack": GENOCIDE_ATTACK,
    "Raise Saibamen": RAISE_SAIBAMEN,
    "Resurrection": RESURRECTION_F,
    "Frieza Force": FRIEZA_FORCE,
    "Majin Mark": MAJIN_MARK,
    "Dark Energy": DARK_ENERGY,

    # RED - SAIYANS, RAGE, POWER
    "Vegeta, Saiyan Prince": VEGETA_SAIYAN_PRINCE,
    "Broly, Legendary Super Saiyan": BROLY_LEGENDARY,
    "Future Trunks, Time Warrior": FUTURE_TRUNKS,
    "Trunks, Young Fighter": KID_TRUNKS,
    "Goten, Cheerful Saiyan": GOTEN,
    "Nappa, Saiyan Elite": NAPPA,
    "Raditz, Saiyan Warrior": RADITZ,
    "Bardock, Father of Goku": BARDOCK,
    "King Vegeta": KING_VEGETA,
    "Saiyan Warrior": SAIYAN_WARRIOR,
    "Saiyan Elite": SAIYAN_ELITE,
    "Great Ape": GREAT_APE,
    "Raging Saiyan": RAGING_SAIYAN,
    "Saiyan Child": SAIYAN_CHILD,
    "Saiyan Pod Pilot": SAIYAN_POD_PILOT,
    "Final Flash": FINAL_FLASH,
    "Galick Gun": GALICK_GUN,
    "Big Bang Attack": BIG_BANG_ATTACK,
    "Burning Attack": BURNING_ATTACK,
    "Explosive Wave": EXPLOSIVE_WAVE,
    "Saiyan Rage": SAIYAN_RAGE,
    "Ki Explosion": KI_EXPLOSION,
    "Power Ball": POWER_BALL,
    "Saiyan Invasion": SAIYAN_INVASION,
    "Oozaru Rampage": OOZARU_RAMPAGE,
    "Zenkai Boost": ZENKAI_BOOST,
    "Saiyan Pride": SAIYAN_PRIDE,
    "Super Saiyan Aura": SUPER_SAIYAN_AURA,
    "Battle Rage": BATTLE_RAGE,

    # GREEN - NAMEKIANS, REGENERATION
    "Piccolo, Namekian Warrior": PICCOLO_NAMEKIAN_WARRIOR,
    "Nail, Namekian Elite": NAIL,
    "Dende, Young Healer": DENDE,
    "Guru, Grand Elder": GURU,
    "Namekian Warrior": NAMEKIAN_WARRIOR,
    "Namekian Healer": NAMEKIAN_HEALER,
    "Namekian Elder": NAMEKIAN_ELDER,
    "Namekian Child": NAMEKIAN_CHILD,
    "Giant Namekian": GIANT_NAMEKIAN,
    "Porunga, Namekian Dragon": PORUNGA,
    "Ajisa Tree": AJISA_TREE,
    "Namek Frog": NAMEK_FROG,
    "Namek Crab": NAMEK_CRAB,
    "Giant Namek Fish": NAMEK_FISH,
    "Special Beam Cannon": SPECIAL_BEAM_CANNON,
    "Namekian Regeneration": NAMEKIAN_REGENERATION,
    "Hellzone Grenade": HELLZONE_GRENADE,
    "Masenko": MASENKO,
    "Fuse": FUSE,
    "Nature's Barrier": NATURE_BARRIER,
    "Namekian Fusion": NAMEKIAN_FUSION,
    "Regrowth": REGROWTH,
    "Dragon Ball Summon": DRAGON_BALL_SUMMON,
    "Planet Namek's Blessing": PLANET_NAMEK,
    "Namekian Resilience": NAMEKIAN_RESILIENCE,
    "Healing Aura": HEALING_AURA,
    "Namek Wilds": NAMEK_WILDS,

    # MULTICOLOR - FUSIONS AND MAJOR CHARACTERS
    "Vegito, Ultimate Fusion": VEGITO,
    "Gogeta, Fusion Warrior": GOGETA,
    "Gotenks, Young Fusion": GOTENKS,
    "Goku, Super Saiyan": GOKU_SUPER_SAIYAN,
    "Goku, Ultra Instinct": GOKU_ULTRA_INSTINCT,
    "Vegeta, Super Saiyan": VEGETA_SUPER_SAIYAN,
    "Gohan, Super Saiyan 2": GOHAN_SSJ2,
    "Beerus, God of Destruction": BEERUS,
    "Whis, Angel Attendant": WHIS,
    "Hit, The Assassin": HIT,
    "Jiren, The Strongest": JIREN,
    "Frieza, Golden Form": GOLDEN_FRIEZA,
    "Vegeta, Majin": MAJIN_VEGETA,
    "Android 21, Hunger Incarnate": ANDROID_21,
    "Kefla, Potara Fusion": KEFLA,
    "Goku Black, Zero Mortal Plan": GOKU_BLACK,
    "Zamasu, Divine Justice": ZAMASU,
    "Shenron, Eternal Dragon": SHENRON,

    # ARTIFACTS
    "One-Star Dragon Ball": DRAGON_BALL_ONE,
    "Two-Star Dragon Ball": DRAGON_BALL_TWO,
    "Three-Star Dragon Ball": DRAGON_BALL_THREE,
    "Four-Star Dragon Ball": DRAGON_BALL_FOUR,
    "Five-Star Dragon Ball": DRAGON_BALL_FIVE,
    "Six-Star Dragon Ball": DRAGON_BALL_SIX,
    "Seven-Star Dragon Ball": DRAGON_BALL_SEVEN,
    "Senzu Bean": SENZU_BEAN,
    "Scouter": SCOUTER,
    "Potara Earrings": POTARA_EARRINGS,
    "Fusion Earrings": FUSION_EARRINGS,
    "Gravity Chamber": GRAVITY_CHAMBER,
    "Time Machine": TIME_MACHINE,
    "Capsule": CAPSULE,
    "Saiyan Space Pod": SPACE_POD,
    "Nimbus Cloud": NIMBUS_CLOUD,
    "Dragon Radar": DRAGON_RADAR,
    "Z-Sword": Z_SWORD,
    "Power Pole": POWER_POLE,
    "Turtle Shell": TURTLE_SHELL,
    "Weighted Clothing": WEIGHTED_CLOTHING,

    # LANDS
    "Kame House": KAME_HOUSE,
    "Capsule Corporation": CAPSULE_CORP,
    "Hyperbolic Time Chamber": HYPERBOLIC_TIME_CHAMBER,
    "Planet Namek": PLANET_NAMEK_LAND,
    "Planet Vegeta": PLANET_VEGETA,
    "The Lookout": LOOKOUT,
    "World Tournament Arena": WORLD_TOURNAMENT_ARENA,
    "Korin Tower": KORIN_TOWER,
    "Frieza's Spaceship": FRIEZA_SPACESHIP,
    "Cell Games Arena": CELL_GAMES_ARENA,
    "King Kai's Planet": KING_KAIS_PLANET,
    "Snake Way": SERPENT_ROAD,
    "Majin Buu's House": MAJIN_BUU_HOUSE,
    "Red Ribbon Army HQ": RED_RIBBON_HQ,
    "Otherworld Tournament Arena": OTHERWORLD_ARENA,

    # BASIC LANDS
    "Plains": PLAINS_DBZ,
    "Island": ISLAND_DBZ,
    "Swamp": SWAMP_DBZ,
    "Mountain": MOUNTAIN_DBZ,
    "Forest": FOREST_DBZ,

    # KI ATTACKS
    "Kamehameha": KAMEHAMEHA,
    "Spirit Bomb": SPIRIT_BOMB,
    "Destructo Disc": DESTRUCTO_DISC,
    "Death Ball": DEATH_BALL,
    "Candy Beam": CANDY_BEAM,
    "Human Extinction Attack": HUMAN_EXTINCTION_ATTACK,
    "Solar Kamehameha": SOLAR_KAMEHAMEHA,
    "Final Explosion": FINAL_EXPLOSION,
    "Omega Blaster": OMEGA_BLASTER,
    "Eraser Cannon": ERASER_CANNON,

    # SPICE PASS Phase A
    "Future Sword": FUTURE_SWORD,
    "Master Roshi's Training Hall": MASTER_ROSHIS_TRAINING_HALL,
    "Capsule Corp R&D": CAPSULE_CORP_RND,
    "Ginyu Force, Assemble!": GINYU_FORCE_ASSEMBLE,
    "Trunks, Sword of the Future": TRUNKS_SWORD_OF_FUTURE,
    "Goku, Pure of Heart": GOKU_PURE_OF_HEART,
    # SPICE PASS Phase B
    "Senzu Bean Reanimator": SENZU_BEAN_REANIMATOR,
    "Hyperbolic Time Chamber, Refurbished": HYPERBOLIC_TIME_CHAMBER_REFURBISHED,
    # SPICE PASS v2 EXPANSION (2026-05-18) — Dragon Balls assembly payoff,
    # saga, and reskinned flagship mythics.
    "Shenron, Wish Granter": SHENRON_WISH_GRANTER,
    "Eternal Dragon's Wish": ETERNAL_DRAGONS_WISH,
    "The Saiyan Saga": THE_SAIYAN_SAGA,
    "Bardock, Father of Saiyans": BARDOCK_FATHER_OF_SAIYANS,
    "Future Trunks, Tomorrow's Hope": FUTURE_TRUNKS_TOMORROW,
    "Goku, Ultra Instinct Sign": GOKU_ULTRA_INSTINCT_SIGN,
    "Kame House, Master's Refuge": KAME_HOUSE_MASTERS_REFUGE,
}

print(f"Loaded {len(DRAGON_BALL_CARDS)} Dragon Ball Z cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    GOKU_EARTHS_HERO,
    GOHAN_HIDDEN_POWER,
    KRILLIN_BRAVE_WARRIOR,
    VIDEL_HERO_IN_TRAINING,
    SUPREME_KAI,
    KING_KAI,
    YAMCHA_Z_FIGHTER,
    TIEN_TRICLOPS,
    CHIAOTZU,
    KAMI,
    MR_POPO,
    EARTHLING_FIGHTER,
    CAPSULE_CORP_SOLDIER,
    WORLD_CHAMPION,
    MARTIAL_ARTIST,
    OTHERWORLD_FIGHTER,
    GUARDIAN_ANGEL,
    TURTLE_SCHOOL_STUDENT,
    CRANE_SCHOOL_STUDENT,
    SENZU_HEAL,
    DIVINE_PROTECTION,
    INSTANT_TRANSMISSION_WHITE,
    ENERGY_BARRIER,
    KIAI_SHOUT,
    HOPE_OF_EARTH,
    REVIVAL,
    DRAGON_BALL_WISH,
    TRAINING_COMPLETE,
    WORLD_TOURNAMENT,
    Z_FIGHTERS_UNITE,
    OTHERWORLD,
    KAIS_BLESSING,
    ANDROID_18,
    ANDROID_17,
    ANDROID_16,
    BULMA_GENIUS_INVENTOR,
    DR_BRIEF,
    ANDROID_19,
    ANDROID_20,
    CAPSULE_CORP_DRONE,
    REPAIR_BOT,
    ANALYSIS_DRONE,
    SCIENTIST,
    RED_RIBBON_SCOUT,
    ANDROID_PROTOTYPE,
    BATTLE_ANDROID,
    ENERGY_ABSORBER,
    KI_SENSE,
    ENERGY_DRAIN,
    AFTERIMAGE,
    INSTANT_TRANSMISSION_BLUE,
    PHOTON_WAVE,
    SOLAR_FLARE_TECHNIQUE,
    ANDROID_CONSTRUCTION,
    TECHNOLOGY_ADVANCEMENT,
    ENERGY_ANALYSIS,
    RED_RIBBON_RESEARCH,
    INFINITE_ENERGY,
    CAPSULE_TECHNOLOGY,
    ENERGY_FIELD,
    FRIEZA_EMPEROR,
    CELL_PERFECT_FORM,
    KID_BUU,
    MAJIN_BUU,
    SUPER_BUU,
    ZARBON,
    DODORIA,
    GINYU,
    RECOOME,
    BURTER,
    JEICE,
    GULDO,
    FRIEZA_SOLDIER,
    APPULE,
    SAIBAMAN,
    CELL_JUNIOR,
    MAJIN_MINION,
    DABURA,
    BABIDI,
    DEATH_BEAM,
    SUPERNOVA,
    FINGER_BEAM,
    ABSORPTION,
    VANISH,
    MAJIN_CURSE,
    PLANET_DESTRUCTION,
    GENOCIDE_ATTACK,
    RAISE_SAIBAMEN,
    RESURRECTION_F,
    FRIEZA_FORCE,
    MAJIN_MARK,
    DARK_ENERGY,
    VEGETA_SAIYAN_PRINCE,
    BROLY_LEGENDARY,
    FUTURE_TRUNKS,
    KID_TRUNKS,
    GOTEN,
    NAPPA,
    RADITZ,
    BARDOCK,
    KING_VEGETA,
    SAIYAN_WARRIOR,
    SAIYAN_ELITE,
    GREAT_APE,
    RAGING_SAIYAN,
    SAIYAN_CHILD,
    SAIYAN_POD_PILOT,
    FINAL_FLASH,
    GALICK_GUN,
    BIG_BANG_ATTACK,
    BURNING_ATTACK,
    EXPLOSIVE_WAVE,
    SAIYAN_RAGE,
    KI_EXPLOSION,
    POWER_BALL,
    SAIYAN_INVASION,
    OOZARU_RAMPAGE,
    ZENKAI_BOOST,
    SAIYAN_PRIDE,
    SUPER_SAIYAN_AURA,
    BATTLE_RAGE,
    PICCOLO_NAMEKIAN_WARRIOR,
    NAIL,
    DENDE,
    GURU,
    NAMEKIAN_WARRIOR,
    NAMEKIAN_HEALER,
    NAMEKIAN_ELDER,
    NAMEKIAN_CHILD,
    GIANT_NAMEKIAN,
    PORUNGA,
    AJISA_TREE,
    NAMEK_FROG,
    NAMEK_CRAB,
    NAMEK_FISH,
    SPECIAL_BEAM_CANNON,
    NAMEKIAN_REGENERATION,
    HELLZONE_GRENADE,
    MASENKO,
    FUSE,
    NATURE_BARRIER,
    NAMEKIAN_FUSION,
    REGROWTH,
    DRAGON_BALL_SUMMON,
    PLANET_NAMEK,
    NAMEKIAN_RESILIENCE,
    HEALING_AURA,
    NAMEK_WILDS,
    VEGITO,
    GOGETA,
    GOTENKS,
    GOKU_SUPER_SAIYAN,
    GOKU_ULTRA_INSTINCT,
    VEGETA_SUPER_SAIYAN,
    GOHAN_SSJ2,
    BEERUS,
    WHIS,
    HIT,
    JIREN,
    GOLDEN_FRIEZA,
    MAJIN_VEGETA,
    ANDROID_21,
    KEFLA,
    GOKU_BLACK,
    ZAMASU,
    SHENRON,
    DRAGON_BALL_ONE,
    DRAGON_BALL_TWO,
    DRAGON_BALL_THREE,
    DRAGON_BALL_FOUR,
    DRAGON_BALL_FIVE,
    DRAGON_BALL_SIX,
    DRAGON_BALL_SEVEN,
    SENZU_BEAN,
    SCOUTER,
    POTARA_EARRINGS,
    FUSION_EARRINGS,
    GRAVITY_CHAMBER,
    TIME_MACHINE,
    CAPSULE,
    SPACE_POD,
    NIMBUS_CLOUD,
    DRAGON_RADAR,
    Z_SWORD,
    POWER_POLE,
    TURTLE_SHELL,
    WEIGHTED_CLOTHING,
    KAME_HOUSE,
    CAPSULE_CORP,
    HYPERBOLIC_TIME_CHAMBER,
    PLANET_NAMEK_LAND,
    PLANET_VEGETA,
    LOOKOUT,
    WORLD_TOURNAMENT_ARENA,
    KORIN_TOWER,
    FRIEZA_SPACESHIP,
    CELL_GAMES_ARENA,
    KING_KAIS_PLANET,
    SERPENT_ROAD,
    MAJIN_BUU_HOUSE,
    RED_RIBBON_HQ,
    OTHERWORLD_ARENA,
    PLAINS_DBZ,
    ISLAND_DBZ,
    SWAMP_DBZ,
    MOUNTAIN_DBZ,
    FOREST_DBZ,
    KAMEHAMEHA,
    SPIRIT_BOMB,
    DESTRUCTO_DISC,
    DEATH_BALL,
    CANDY_BEAM,
    HUMAN_EXTINCTION_ATTACK,
    SOLAR_KAMEHAMEHA,
    FINAL_EXPLOSION,
    OMEGA_BLASTER,
    ERASER_CANNON,
    # SPICE PASS Phase A
    FUTURE_SWORD,
    MASTER_ROSHIS_TRAINING_HALL,
    CAPSULE_CORP_RND,
    GINYU_FORCE_ASSEMBLE,
    TRUNKS_SWORD_OF_FUTURE,
    GOKU_PURE_OF_HEART,
    # SPICE PASS Phase B
    SENZU_BEAN_REANIMATOR,
    HYPERBOLIC_TIME_CHAMBER_REFURBISHED,
    # SPICE PASS v2 EXPANSION
    SHENRON_WISH_GRANTER,
    ETERNAL_DRAGONS_WISH,
    THE_SAIYAN_SAGA,
    BARDOCK_FATHER_OF_SAIYANS,
    FUTURE_TRUNKS_TOMORROW,
    GOKU_ULTRA_INSTINCT_SIGN,
    KAME_HOUSE_MASTERS_REFUGE,
]
