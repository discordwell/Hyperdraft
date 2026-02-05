"""
Demon Slayer (DMS) Card Implementations

Set released May 2026. ~250 cards.
Features mechanics: Breathing, Demon, Nichirin Blade, Blood Demon Art
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, creatures_with_subtype,
    make_upkeep_trigger, make_end_step_trigger, make_spell_cast_trigger,
    make_block_trigger, make_life_gain_trigger, make_life_loss_trigger
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    from src.engine import CardDefinition, Characteristics
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


def make_artifact_equipment(name: str, mana_cost: str, text: str, supertypes: set = None, setup_interceptors=None):
    """Helper to create equipment card definitions."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes={"Equipment"},
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, subtypes: set = None, supertypes: set = None, text: str = ""):
    """Helper to create land card definitions."""
    from src.engine import CardDefinition, Characteristics
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
# DEMON SLAYER KEYWORD HELPERS
# =============================================================================

def make_breathing_ability(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    life_cost: int = 1
) -> Interceptor:
    """
    Breathing - {T}, Pay N life: Effect.
    Activated ability representing breathing techniques.
    """
    def breathing_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return event.payload.get('source') == source_obj.id

    def breathing_handler(event: Event, state: GameState) -> InterceptorResult:
        # Pay life cost
        life_event = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -life_cost},
            source=source_obj.id
        )
        # Tap self
        tap_event = Event(
            type=EventType.TAP,
            payload={'object_id': source_obj.id},
            source=source_obj.id
        )
        # Effect
        effect_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_event, tap_event] + effect_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=breathing_filter,
        handler=breathing_handler,
        duration='while_on_battlefield'
    )


def make_breathing_attack_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    life_cost: int = 1
) -> Interceptor:
    """
    Breathing - Whenever this creature attacks, you may pay N life. If you do, effect.
    """
    def attack_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == obj.id)

    def attack_handler(event: Event, state: GameState) -> InterceptorResult:
        life_event = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -life_cost, 'may': True},
            source=source_obj.id
        )
        effect_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_event] + effect_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: attack_filter(e, s, source_obj),
        handler=attack_handler,
        duration='while_on_battlefield'
    )


def make_demon_night_bonus(
    source_obj: GameObject,
    power_bonus: int,
    toughness_bonus: int
) -> list[Interceptor]:
    """
    Demon - This creature gets +X/+Y during opponents' turns (night).
    """
    def is_night(state: GameState) -> bool:
        return state.active_player != source_obj.controller

    def is_self_at_night(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id and is_night(state)

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, is_self_at_night)


def make_blood_demon_art(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    life_cost: int = 2
) -> Interceptor:
    """
    Blood Demon Art - Pay N life: Powerful demon ability.
    """
    def bda_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return event.payload.get('source') == source_obj.id

    def bda_handler(event: Event, state: GameState) -> InterceptorResult:
        life_event = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -life_cost},
            source=source_obj.id
        )
        effect_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_event] + effect_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=bda_filter,
        handler=bda_handler,
        duration='while_on_battlefield'
    )


def make_nichirin_bonus_vs_demons(
    source_obj: GameObject,
    power_bonus: int = 2
) -> Interceptor:
    """
    Nichirin Blade - Equipped creature gets +N/+0 when attacking Demons.
    Also deals extra damage to Demons.
    """
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source_obj.state.attached_to:
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target:
            return False
        return 'Demon' in target.characteristics.subtypes

    def damage_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) + power_bonus
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=damage_filter,
        handler=damage_handler,
        duration='while_on_battlefield'
    )


def make_regeneration(source_obj: GameObject, amount: int = 1) -> Interceptor:
    """
    Demon regeneration - At end of turn, remove N damage from this creature.
    """
    def regen_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': source_obj.id, 'amount': -amount, 'heal': True},
            source=source_obj.id
        )]

    return make_end_step_trigger(source_obj, regen_effect, controller_only=True)


def make_slayer_mark(source_obj: GameObject) -> Interceptor:
    """
    Demon Slayer Mark - When life is low, get stronger.
    This creature gets +2/+2 as long as you have 10 or less life.
    """
    def mark_active(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        player = state.players.get(source_obj.controller)
        return player and player.life <= 10

    return make_static_pt_boost(source_obj, 2, 2, mark_active)


# =============================================================================
# WHITE CARDS - DEMON SLAYER CORPS, HEALING, PROTECTION
# =============================================================================

def kagaya_ubuyashiki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Leader of the Demon Slayer Corps - buffs all Slayers"""
    def slayer_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Slayer' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors = make_static_pt_boost(obj, 1, 1, slayer_filter)
    interceptors.append(make_keyword_grant(obj, ['vigilance'], slayer_filter))
    return interceptors

KAGAYA_UBUYASHIKI = make_creature(
    name="Kagaya Ubuyashiki",
    power=1,
    toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Other Slayers you control get +1/+1 and have vigilance. At the beginning of your upkeep, you gain 1 life for each Slayer you control.",
    setup_interceptors=kagaya_ubuyashiki_setup
)


def corps_healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Gain 3 life"""
    def heal_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, heal_effect)]

CORPS_HEALER = make_creature(
    name="Corps Healer",
    power=1,
    toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="When Corps Healer enters, you gain 3 life.",
    setup_interceptors=corps_healer_setup
)


def butterfly_estate_nurse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap: Prevent 2 damage to target creature"""
    def prevent_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system handles this
    return [make_breathing_ability(obj, prevent_effect, life_cost=0)]

BUTTERFLY_ESTATE_NURSE = make_creature(
    name="Butterfly Estate Nurse",
    power=1,
    toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="{T}: Prevent the next 2 damage that would be dealt to target creature this turn.",
    setup_interceptors=butterfly_estate_nurse_setup
)


def demon_slayer_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike. When attacks, gets +1/+0 if you control a Hashira."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        for o in state.objects.values():
            if (o.controller == obj.controller and
                'Hashira' in o.characteristics.subtypes and
                o.zone == ZoneType.BATTLEFIELD):
                return [Event(
                    type=EventType.GRANT_PT_MODIFIER,
                    payload={'object_id': obj.id, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'},
                    source=obj.id
                )]
        return []
    return [make_attack_trigger(obj, attack_effect)]

DEMON_SLAYER_RECRUIT = make_creature(
    name="Demon Slayer Recruit",
    power=2,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="First strike. Whenever Demon Slayer Recruit attacks, it gets +1/+0 until end of turn if you control a Hashira.",
    setup_interceptors=demon_slayer_recruit_setup
)


def final_selection_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature survives combat damage, put a +1/+1 counter on it."""
    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return (event.payload.get('target') == source.id and
                event.payload.get('is_combat', False))

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)]

    return [make_damage_trigger(obj, counter_effect, combat_only=True, filter_fn=damage_filter)]

FINAL_SELECTION_SURVIVOR = make_creature(
    name="Final Selection Survivor",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Whenever Final Selection Survivor survives combat damage, put a +1/+1 counter on it.",
    setup_interceptors=final_selection_survivor_setup
)


def wisteria_ward_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Demons can't attack you or block your creatures."""
    def cant_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        if 'Demon' not in attacker.characteristics.subtypes:
            return False
        return event.payload.get('defending_player') == obj.controller

    def prevent_attack(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_attack_filter,
        handler=prevent_attack,
        duration='while_on_battlefield'
    )]

WISTERIA_WARD = make_enchantment(
    name="Wisteria Ward",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Demons can't attack you or planeswalkers you control.",
    setup_interceptors=wisteria_ward_setup
)


SUNLIGHT_PROTECTION = make_instant(
    name="Sunlight Protection",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control gains indestructible until end of turn. If it's a Slayer, it also gains lifelink until end of turn."
)


TOTAL_CONCENTRATION_CONSTANT = make_enchantment(
    name="Total Concentration Constant",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Slayers you control have vigilance and get +0/+1. Breathing abilities you activate cost 1 less life to activate."
)


CORPS_TRAINING = make_sorcery(
    name="Corps Training",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on each Slayer you control. You gain 1 life for each Slayer you control."
)


RECOVERY_AT_THE_ESTATE = make_sorcery(
    name="Recovery at the Estate",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. Remove all damage from creatures you control."
)


def swordsmith_village_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Search for an Equipment card"""
    def search_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Search system handles this
    return [make_etb_trigger(obj, search_effect)]

SWORDSMITH_VILLAGE_ELDER = make_creature(
    name="Swordsmith Village Elder",
    power=1,
    toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Artificer"},
    text="When Swordsmith Village Elder enters, you may search your library for an Equipment card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=swordsmith_village_elder_setup
)


def kakushi_messenger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, scry 2"""
    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, scry_effect)]

KAKUSHI_MESSENGER = make_creature(
    name="Kakushi Messenger",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When Kakushi Messenger enters, scry 2.",
    setup_interceptors=kakushi_messenger_setup
)


def aoi_kanzaki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Slayers you control have lifelink"""
    def other_slayers(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Slayer' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['lifelink'], other_slayers)]

AOI_KANZAKI = make_creature(
    name="Aoi Kanzaki",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    supertypes={"Legendary"},
    text="Other Slayers you control have lifelink.",
    setup_interceptors=aoi_kanzaki_setup
)


DEMON_SLAYER_CORPS_BANNER = make_artifact(
    name="Demon Slayer Corps Banner",
    mana_cost="{2}",
    text="Slayers you control get +1/+0. {W}, {T}: Target Slayer you control gains vigilance until end of turn."
)


WISTERIA_INCENSE = make_artifact(
    name="Wisteria Incense",
    mana_cost="{1}",
    text="Demons can't block Slayers you control."
)


def devoted_trainee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a Hashira enters under your control, put two +1/+1 counters on this."""
    def hashira_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                'Hashira' in entering.characteristics.subtypes)

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2}, source=obj.id)]

    return [make_etb_trigger(obj, counter_effect, filter_fn=hashira_etb_filter)]

DEVOTED_TRAINEE = make_creature(
    name="Devoted Trainee",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Whenever a Hashira enters under your control, put two +1/+1 counters on Devoted Trainee.",
    setup_interceptors=devoted_trainee_setup
)


BREATH_OF_RECOVERY = make_instant(
    name="Breath of Recovery",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="You gain 3 life. If you control a Slayer, you gain 5 life instead."
)


SWORN_PROTECTOR = make_creature(
    name="Sworn Protector",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Defender. Whenever Sworn Protector blocks a Demon, it gets +2/+2 until end of turn."
)


UBUYASHIKI_BLESSING = make_enchantment(
    name="Ubuyashiki Blessing",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchanted creature gets +1/+2 and has 'Breathing abilities you activate cost no life to activate.'"
)


CORPS_SOLIDARITY = make_instant(
    name="Corps Solidarity",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1 until end of turn. Slayers you control also gain indestructible until end of turn."
)


# =============================================================================
# BLUE CARDS - WATER/MIST BREATHING, EVASION
# =============================================================================

def tanjiro_water_breathing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Water Breathing forms + Sun Breathing awakening at low life"""
    interceptors = []

    # Breathing attack trigger
    def water_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP,
            payload={'object_id': None},  # Target chosen by system
            source=obj.id
        )]
    interceptors.append(make_breathing_attack_trigger(obj, water_effect, life_cost=1))

    # Sun breathing at low life
    interceptors.extend(make_slayer_mark(obj))

    return interceptors

TANJIRO_WATER_BREATHING = make_creature(
    name="Tanjiro Kamado, Water Breather",
    power=3,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Slayer"},
    supertypes={"Legendary"},
    text="Breathing — Whenever Tanjiro attacks, you may pay 1 life. If you do, tap target creature. Demon Slayer Mark — Tanjiro gets +2/+2 as long as you have 10 or less life.",
    setup_interceptors=tanjiro_water_breathing_setup
)


def sakonji_urokodaki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Master trainer - other Slayers you control with Water subtype get +1/+1"""
    def water_slayers(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Slayer' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return make_static_pt_boost(obj, 1, 1, water_slayers)

SAKONJI_UROKODAKI = make_creature(
    name="Sakonji Urokodaki",
    power=2,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Slayer"},
    supertypes={"Legendary"},
    text="Other Slayers you control get +1/+1. {U}, {T}: Target Slayer you control can't be blocked this turn.",
    setup_interceptors=sakonji_urokodaki_setup
)


WATER_SURFACE_SLASH = make_instant(
    name="Water Surface Slash",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -2/-0 until end of turn. Draw a card."
)


WATER_WHEEL = make_instant(
    name="Water Wheel",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If you control a Slayer, scry 2."
)


FLOWING_DANCE = make_instant(
    name="Flowing Dance",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof and can't be blocked this turn."
)


def muichiro_tokito_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mist Hashira - hexproof, mist breathing makes creatures unblockable"""
    def mist_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Grant unblockable
    return [make_breathing_ability(obj, mist_effect, life_cost=1)]

MUICHIRO_TOKITO = make_creature(
    name="Muichiro Tokito, Mist Hashira",
    power=4,
    toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="Hexproof. Breathing — {T}, Pay 1 life: Target creature you control can't be blocked this turn.",
    setup_interceptors=muichiro_tokito_setup
)


OBSCURING_CLOUDS = make_instant(
    name="Obscuring Clouds",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Creatures you control can't be blocked this turn. Draw a card."
)


MIST_BREATHING_FORM = make_enchantment(
    name="Mist Breathing Form",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchanted creature has hexproof and 'Breathing — {T}, Pay 1 life: This creature can't be blocked this turn.'"
)


def sabito_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, target Slayer gets +2/+2 and gains hexproof until end of turn"""
    def buff_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system handles
    return [make_etb_trigger(obj, buff_effect)]

SABITO_SPIRIT = make_creature(
    name="Sabito, Guiding Spirit",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Slayer"},
    supertypes={"Legendary"},
    text="When Sabito enters, target Slayer you control gets +2/+2 and gains hexproof until end of turn.",
    setup_interceptors=sabito_spirit_setup
)


def makomo_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, draw a card for each Slayer you control"""
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        slayer_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and CardType.CREATURE in o.characteristics.types
                         and 'Slayer' in o.characteristics.subtypes
                         and o.zone == ZoneType.BATTLEFIELD)
        if slayer_count > 0:
            return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': slayer_count}, source=obj.id)]
        return []
    return [make_etb_trigger(obj, draw_effect)]

MAKOMO_SPIRIT = make_creature(
    name="Makomo, Teaching Spirit",
    power=1,
    toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Slayer"},
    supertypes={"Legendary"},
    text="When Makomo enters, draw a card for each Slayer you control.",
    setup_interceptors=makomo_spirit_setup
)


WHIRLPOOL_TECHNIQUE = make_instant(
    name="Whirlpool Technique",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures target opponent controls to their owner's hand. You lose 2 life."
)


WATERFALL_BASIN = make_instant(
    name="Waterfall Basin",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If you control a Slayer, counter it unless they pay {4} instead."
)


def water_breathing_student_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be blocked as long as you control Sakonji"""
    def unblockable_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        for o in state.objects.values():
            if (o.controller == obj.controller and
                o.name == "Sakonji Urokodaki" and
                o.zone == ZoneType.BATTLEFIELD):
                return True
        return False
    return [make_keyword_grant(obj, ['unblockable'], unblockable_filter)]

WATER_BREATHING_STUDENT = make_creature(
    name="Water Breathing Student",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Slayer"},
    text="Water Breathing Student can't be blocked as long as you control Sakonji Urokodaki.",
    setup_interceptors=water_breathing_student_setup
)


DEAD_CALM = make_instant(
    name="Dead Calm",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Counter target activated or triggered ability. Draw a card."
)


CONSTANT_FLUX = make_enchantment(
    name="Constant Flux",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1. Whenever you activate a Breathing ability, draw a card."
)


DROP_RIPPLE_THRUST = make_instant(
    name="Drop Ripple Thrust",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -3/-0 until end of turn. If it's a Demon, tap it."
)


SPLASHING_WATER_FLOW = make_sorcery(
    name="Splashing Water Flow",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Return up to two target creatures to their owners' hands. Draw a card."
)


def fog_concealment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Your creatures have hexproof during opponents' turns"""
    def your_creatures_opponents_turn(target: GameObject, state: GameState) -> bool:
        if state.active_player == obj.controller:
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['hexproof'], your_creatures_opponents_turn)]

FOG_CONCEALMENT = make_enchantment(
    name="Fog Concealment",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Creatures you control have hexproof during opponents' turns.",
    setup_interceptors=fog_concealment_setup
)


# =============================================================================
# BLACK CARDS - DEMONS, MUZAN, CORRUPTION
# =============================================================================

def muzan_kibutsuji_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """The Demon King - creates demons, destroys slayers"""
    interceptors = []

    # Night bonus
    interceptors.extend(make_demon_night_bonus(obj, 3, 3))

    # Regeneration
    interceptors.append(make_regeneration(obj, 2))

    # ETB: Each opponent sacrifices a creature
    def sacrifice_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.SACRIFICE,
                    payload={'player': player_id, 'type': 'creature'},
                    source=obj.id
                ))
        return events
    interceptors.append(make_etb_trigger(obj, sacrifice_effect))

    return interceptors

MUZAN_KIBUTSUJI = make_creature(
    name="Muzan Kibutsuji",
    power=6,
    toughness=6,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Noble"},
    supertypes={"Legendary"},
    text="Indestructible. Demon — Muzan gets +3/+3 during opponents' turns. At end of turn, remove 2 damage from Muzan. When Muzan enters, each opponent sacrifices a creature.",
    setup_interceptors=muzan_kibutsuji_setup
)


def akaza_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upper Moon Three - attacks each turn, gets stronger from combat"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 2, 2))

    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)]
    interceptors.append(make_damage_trigger(obj, combat_damage_effect, combat_only=True))

    return interceptors

AKAZA = make_creature(
    name="Akaza, Upper Moon Three",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Haste. Demon — Akaza gets +2/+2 during opponents' turns. Whenever Akaza deals combat damage, put a +1/+1 counter on him. Akaza attacks each combat if able.",
    setup_interceptors=akaza_setup
)


def doma_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upper Moon Two - ice powers, drains life"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 2, 2))

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))

    return interceptors

DOMA = make_creature(
    name="Doma, Upper Moon Two",
    power=4,
    toughness=5,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying. Demon — Doma gets +2/+2 during opponents' turns. Whenever Doma deals combat damage to a player, you gain 2 life and that player loses 2 life.",
    setup_interceptors=doma_setup
)


def kokushibo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upper Moon One - former slayer, uses Moon Breathing"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 3, 3))

    # Double strike at night
    def double_strike_at_night(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return state.active_player != obj.controller

    interceptors.append(make_keyword_grant(obj, ['double_strike'], double_strike_at_night))

    return interceptors

KOKUSHIBO = make_creature(
    name="Kokushibo, Upper Moon One",
    power=6,
    toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Slayer"},
    supertypes={"Legendary"},
    text="Demon — Kokushibo gets +3/+3 and has double strike during opponents' turns. Moon Breathing — {2}{B}, Pay 2 life: Kokushibo deals 3 damage to target creature.",
    setup_interceptors=kokushibo_setup
)


def nezuko_demon_form_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Nezuko in demon form - stronger but berserk"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 2, 2))
    interceptors.append(make_regeneration(obj, 1))
    return interceptors

NEZUKO_DEMON_FORM = make_creature(
    name="Nezuko, Awakened Demon",
    power=4,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Haste. Demon — Nezuko gets +2/+2 during opponents' turns. At end of turn, remove 1 damage from Nezuko. Nezuko can't attack humans. (Creatures without the Demon subtype that your opponents control.)",
    setup_interceptors=nezuko_demon_form_setup
)


def lower_moon_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Generic Lower Moon demon"""
    return make_demon_night_bonus(obj, 1, 1)

LOWER_MOON_DEMON = make_creature(
    name="Lower Moon Demon",
    power=3,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Demon — Lower Moon Demon gets +1/+1 during opponents' turns.",
    setup_interceptors=lower_moon_demon_setup
)


def temple_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Basic demon with menace"""
    return make_demon_night_bonus(obj, 1, 0)

TEMPLE_DEMON = make_creature(
    name="Temple Demon",
    power=2,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Menace. Demon — Temple Demon gets +1/+0 during opponents' turns.",
    setup_interceptors=temple_demon_setup
)


def hand_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """The demon from Final Selection - gets counters from kills"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 2, 2))

    def kill_trigger_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying.controller != source.controller and
                CardType.CREATURE in dying.characteristics.types)

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)]

    interceptors.append(make_death_trigger(obj, counter_effect, filter_fn=kill_trigger_filter))
    return interceptors

HAND_DEMON = make_creature(
    name="Hand Demon",
    power=4,
    toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Demon — Hand Demon gets +2/+2 during opponents' turns. Whenever another creature dies, put a +1/+1 counter on Hand Demon.",
    setup_interceptors=hand_demon_setup
)


DEMONIC_TRANSFORMATION = make_instant(
    name="Demonic Transformation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature becomes a Demon in addition to its other types and gets +2/+2 until end of turn. It gains 'Demon — This creature gets +1/+1 during opponents' turns.'"
)


BLOOD_DEMON_ART_SPELL = make_instant(
    name="Blood Demon Art: Destruction",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="As an additional cost, pay 3 life. Destroy target creature. If it was a Slayer, draw two cards."
)


MUZAN_BLOOD = make_sorcery(
    name="Muzan's Blood",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature becomes a Demon in addition to its other types. Put two +1/+1 counters on it. It gains 'At the beginning of your upkeep, you lose 1 life.'"
)


DEMON_CONSUMPTION = make_instant(
    name="Demon Consumption",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it was a Demon, you gain life equal to its toughness."
)


NIGHTMARE_BLOOD_ART = make_enchantment(
    name="Nightmare Blood Art",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="At the beginning of each opponent's upkeep, that player loses 1 life. Demons you control get +1/+0."
)


def swamp_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Demon with swampwalk"""
    return make_demon_night_bonus(obj, 1, 1)

SWAMP_DEMON = make_creature(
    name="Swamp Demon",
    power=2,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Swampwalk. Demon — Swamp Demon gets +1/+1 during opponents' turns.",
    setup_interceptors=swamp_demon_setup
)


def spider_demon_mother_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creates spider tokens"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 1, 1))

    def spawn_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Spider', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Spider', 'Demon'}},
            },
            source=obj.id
        )]
    interceptors.append(make_upkeep_trigger(obj, spawn_effect))
    return interceptors

SPIDER_DEMON_MOTHER = make_creature(
    name="Spider Demon Mother",
    power=3,
    toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Spider"},
    text="Demon — Spider Demon Mother gets +1/+1 during opponents' turns. At the beginning of your upkeep, create a 1/1 black Spider Demon creature token.",
    setup_interceptors=spider_demon_mother_setup
)


TEMPTATION_OF_ETERNITY = make_sorcery(
    name="Temptation of Eternity",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. It becomes a Demon in addition to its other types."
)


def drum_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kyogai - attacks trigger confusion"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 1, 1))

    def drum_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Disorientation effect
    interceptors.append(make_attack_trigger(obj, drum_effect))
    return interceptors

DRUM_DEMON = make_creature(
    name="Kyogai, Drum Demon",
    power=3,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Demon — Kyogai gets +1/+1 during opponents' turns. Whenever Kyogai attacks, defending player discards a card.",
    setup_interceptors=drum_demon_setup
)


ENDLESS_NIGHT = make_enchantment(
    name="Endless Night",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Demons you control get +2/+2. (This represents permanent night for Demons.)"
)


# =============================================================================
# RED CARDS - FLAME/THUNDER BREATHING, AGGRESSION
# =============================================================================

def kyojuro_rengoku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flame Hashira - aggressive, flame breathing"""
    interceptors = []

    # Flame Breathing - deals damage when attacking
    def flame_effect(event: Event, state: GameState) -> list[Event]:
        # Target first opponent (simplified - would need target selection)
        opponents = [p_id for p_id in state.players if p_id != obj.controller]
        if opponents:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': opponents[0], 'amount': 2, 'source': obj.id, 'is_combat': False},
                source=obj.id
            )]
        return []
    interceptors.append(make_breathing_attack_trigger(obj, flame_effect, life_cost=1))

    return interceptors

KYOJURO_RENGOKU = make_creature(
    name="Kyojuro Rengoku, Flame Hashira",
    power=5,
    toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="Haste, first strike. Breathing — Whenever Kyojuro attacks, you may pay 1 life. If you do, Kyojuro deals 2 damage to any target.",
    setup_interceptors=kyojuro_rengoku_setup
)


def zenitsu_agatsuma_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Thunder Breathing - when asleep (tapped), becomes powerful"""
    def thunder_boost(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id and target.state.tapped

    return make_static_pt_boost(obj, 4, 0, thunder_boost)

ZENITSU_AGATSUMA = make_creature(
    name="Zenitsu Agatsuma",
    power=1,
    toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Slayer"},
    supertypes={"Legendary"},
    text="First strike. Thunder Breathing — Zenitsu gets +4/+0 as long as he's tapped. (He's asleep and fighting on instinct.)",
    setup_interceptors=zenitsu_agatsuma_setup
)


THUNDERCLAP_AND_FLASH = make_instant(
    name="Thunderclap and Flash",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +3/+0 and gains first strike until end of turn. If it's a Slayer, it also gains haste."
)


FLAME_BREATHING_FIRST_FORM = make_instant(
    name="Flame Breathing: Unknowing Fire",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker."
)


FLAME_BREATHING_NINTH_FORM = make_sorcery(
    name="Flame Breathing: Rengoku",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Flame Breathing: Rengoku deals 5 damage to each creature and each opponent. You lose 3 life."
)


def shinjuro_rengoku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Former Flame Hashira - buffs Flame breathing"""
    def flame_slayers(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Slayer' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return make_static_pt_boost(obj, 1, 0, flame_slayers)

SHINJURO_RENGOKU = make_creature(
    name="Shinjuro Rengoku",
    power=3,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human"},
    supertypes={"Legendary"},
    text="Other Slayers you control get +1/+0. {R}, {T}: Target Slayer you control gains first strike until end of turn.",
    setup_interceptors=shinjuro_rengoku_setup
)


BURNING_DETERMINATION = make_enchantment(
    name="Burning Determination",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control have haste. Breathing abilities you activate deal 1 damage to any target."
)


def flame_breathing_student_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deals damage on attack to defending player"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Find defending player (opponent)
        opponents = [p_id for p_id in state.players if p_id != obj.controller]
        if opponents:
            return [Event(type=EventType.DAMAGE, payload={'target': opponents[0], 'amount': 1, 'source': obj.id, 'is_combat': False}, source=obj.id)]
        return []
    return [make_attack_trigger(obj, attack_effect)]

FLAME_BREATHING_STUDENT = make_creature(
    name="Flame Breathing Student",
    power=2,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Slayer"},
    text="Haste. Whenever Flame Breathing Student attacks, it deals 1 damage to defending player.",
    setup_interceptors=flame_breathing_student_setup
)


SIXFOLD = make_instant(
    name="Sixfold",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Target Slayer you control deals damage equal to its power to target creature. If that creature is a Demon, it deals double that damage instead."
)


THUNDER_BREATHING_FORM = make_enchantment(
    name="Thunder Breathing Form",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Enchanted creature gets +2/+0 and has first strike. Breathing — {T}, Pay 1 life: Enchanted creature gains double strike until end of turn."
)


def kaigaku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Former Thunder Breather turned Demon"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 2, 1))

    # Thunder breathing still works
    def thunder_effect(event: Event, state: GameState) -> list[Event]:
        # Target first opponent
        opponents = [p_id for p_id in state.players if p_id != obj.controller]
        if opponents:
            return [Event(type=EventType.DAMAGE, payload={'target': opponents[0], 'amount': 3, 'source': obj.id, 'is_combat': False}, source=obj.id)]
        return []
    interceptors.append(make_breathing_ability(obj, thunder_effect, life_cost=2))

    return interceptors

KAIGAKU = make_creature(
    name="Kaigaku, Fallen Thunder",
    power=4,
    toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "Slayer"},
    supertypes={"Legendary"},
    text="First strike. Demon — Kaigaku gets +2/+1 during opponents' turns. Breathing — {T}, Pay 2 life: Kaigaku deals 3 damage to any target.",
    setup_interceptors=kaigaku_setup
)


HEAT_OF_BATTLE = make_instant(
    name="Heat of Battle",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 until end of turn. If you've lost life this turn, it gets +4/+0 instead."
)


EXPLOSIVE_BLOOD = make_instant(
    name="Explosive Blood",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Explosive Blood deals 3 damage to target creature. If that creature is a Demon, Explosive Blood deals 5 damage instead."
)


SET_YOUR_HEART_ABLAZE = make_sorcery(
    name="Set Your Heart Ablaze",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn. If you control a Hashira, they also gain first strike."
)


THUNDER_BREATHING_STUDENT = make_creature(
    name="Thunder Breathing Student",
    power=2,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Slayer"},
    text="Haste. Breathing — {T}, Pay 1 life: Thunder Breathing Student gets +2/+0 until end of turn."
)


BLAZING_RAGE = make_enchantment(
    name="Blazing Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchanted creature gets +2/+1 and has 'Whenever this creature attacks, it deals 1 damage to defending player.'"
)


FLAMING_BLADE = make_instant(
    name="Flaming Blade",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control gets +3/+0 and gains 'Whenever this creature deals combat damage to a Demon, destroy that Demon' until end of turn."
)


# =============================================================================
# GREEN CARDS - BEAST/SERPENT BREATHING, NATURE
# =============================================================================

def inosuke_hashibira_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beast Breathing - aggressive, can't be blocked by small creatures"""
    def cant_be_blocked_by_small(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        if event.payload.get('attacker_id') != obj.id:
            return False
        blocker_id = event.payload.get('blocker_id')
        blocker = state.objects.get(blocker_id)
        if not blocker:
            return False
        return blocker.characteristics.power is not None and blocker.characteristics.power < 3

    def prevent_block(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_be_blocked_by_small,
        handler=prevent_block,
        duration='while_on_battlefield'
    )]

INOSUKE_HASHIBIRA = make_creature(
    name="Inosuke Hashibira",
    power=4,
    toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Slayer"},
    supertypes={"Legendary"},
    text="Trample. Beast Breathing — Inosuke can't be blocked by creatures with power 2 or less. Breathing — {T}, Pay 1 life: Inosuke gets +2/+2 until end of turn.",
    setup_interceptors=inosuke_hashibira_setup
)


def obanai_iguro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Serpent Hashira - deathtouch, serpent synergy"""
    def serpent_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Grant deathtouch to Slayers
    return [make_breathing_ability(obj, serpent_effect, life_cost=1)]

OBANAI_IGURO = make_creature(
    name="Obanai Iguro, Serpent Hashira",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="Deathtouch. Breathing — {T}, Pay 1 life: Target Slayer you control gains deathtouch until end of turn. Kaburamaru — Whenever Obanai attacks, create a 1/1 green Snake creature token.",
    setup_interceptors=obanai_iguro_setup
)


BEAST_BREATHING_FANG = make_instant(
    name="Beast Breathing: Fang",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +2/+2 and gains trample until end of turn."
)


SERPENT_BREATHING_FORM = make_enchantment(
    name="Serpent Breathing Form",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchanted creature gets +1/+2 and has deathtouch. Breathing — {T}, Pay 1 life: Enchanted creature fights target creature."
)


def forest_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Protects the wisteria forest"""
    def wisteria_buff(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return make_static_pt_boost(obj, 0, 1, wisteria_buff)

FOREST_GUARDIAN = make_creature(
    name="Wisteria Forest Guardian",
    power=2,
    toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="Reach. Other creatures you control get +0/+1.",
    setup_interceptors=forest_guardian_setup
)


BEAST_BREATHING_SLICE = make_instant(
    name="Beast Breathing: Crazy Cutting",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature. If it kills that creature, put a +1/+1 counter on your creature."
)


WILD_INSTINCT = make_enchantment(
    name="Wild Instinct",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchanted creature gets +1/+1 and has trample. It attacks each combat if able."
)


def kaburamaru_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Obanai's snake companion"""
    def partner_buff(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        for o in state.objects.values():
            if 'Obanai' in o.name and o.zone == ZoneType.BATTLEFIELD:
                return True
        return False
    return make_static_pt_boost(obj, 1, 1, partner_buff)

KABURAMARU = make_creature(
    name="Kaburamaru",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Snake"},
    supertypes={"Legendary"},
    text="Deathtouch. Kaburamaru gets +1/+1 as long as you control Obanai Iguro. Partner with Obanai Iguro.",
    setup_interceptors=kaburamaru_setup
)


DEVOUR_WHOLE = make_instant(
    name="Devour Whole",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature. If that creature would die this turn, exile it instead."
)


PRIMAL_FURY = make_sorcery(
    name="Primal Fury",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on each creature you control. Those creatures gain trample until end of turn."
)


def boar_mount_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mount for Inosuke style"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_PT_MODIFIER,
            payload={'object_id': obj.id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

BOAR_MOUNT = make_creature(
    name="Mountain Boar",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Boar"},
    text="Trample. Whenever Mountain Boar attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=boar_mount_setup
)


SNAKE_COIL = make_instant(
    name="Serpentine Coil",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature can't attack or block until end of turn. If you control a Snake, draw a card."
)


WISTERIA_BLOOM = make_sorcery(
    name="Wisteria Bloom",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Create a 1/1 white Spirit creature token."
)


NATURE_SENSE = make_instant(
    name="Spatial Awareness",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Reveal the top three cards of your library. You may put a creature card from among them into your hand. Put the rest on the bottom of your library."
)


def forest_demon_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets bigger when fighting Demons"""
    def fighting_demons(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        for o in state.objects.values():
            if ('Demon' in o.characteristics.subtypes and
                o.controller != obj.controller and
                o.zone == ZoneType.BATTLEFIELD):
                return True
        return False
    return make_static_pt_boost(obj, 2, 2, fighting_demons)

FOREST_DEMON_HUNTER = make_creature(
    name="Forest Demon Hunter",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Slayer"},
    text="Forest Demon Hunter gets +2/+2 as long as an opponent controls a Demon.",
    setup_interceptors=forest_demon_hunter_setup
)


OVERGROWTH_TECHNIQUE = make_enchantment(
    name="Overgrowth Technique",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control. Breathing abilities you activate cost no life to activate."
)


# =============================================================================
# MULTICOLOR CARDS - HASHIRA
# =============================================================================

def giyu_tomioka_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Water Hashira - defensive, water breathing master"""
    interceptors = []

    # Dead Calm - hexproof for Slayers
    def slayer_hexproof(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Slayer' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    interceptors.append(make_keyword_grant(obj, ['hexproof'], slayer_hexproof))

    return interceptors

GIYU_TOMIOKA = make_creature(
    name="Giyu Tomioka, Water Hashira",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="Dead Calm — Slayers you control have hexproof. Breathing — {T}, Pay 1 life: Target creature can't attack or block until your next turn.",
    setup_interceptors=giyu_tomioka_setup
)


def shinobu_kocho_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Insect Hashira - poison, small but deadly"""
    interceptors = []

    # Poison damage (deathtouch + wither-like effect)
    def poison_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if target and CardType.CREATURE in target.characteristics.types:
            return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': target_id, 'counter_type': '-1/-1', 'amount': 2}, source=obj.id)]
        return []
    interceptors.append(make_damage_trigger(obj, poison_effect))

    return interceptors

SHINOBU_KOCHO = make_creature(
    name="Shinobu Kocho, Insect Hashira",
    power=2,
    toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="Flying, deathtouch. Insect Breathing — Whenever Shinobu deals damage to a creature, put two -1/-1 counters on that creature.",
    setup_interceptors=shinobu_kocho_setup
)


def mitsuri_kanroji_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Love Hashira - buffs other creatures significantly"""
    def other_creatures_buff(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return make_static_pt_boost(obj, 1, 1, other_creatures_buff)

MITSURI_KANROJI = make_creature(
    name="Mitsuri Kanroji, Love Hashira",
    power=4,
    toughness=5,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="First strike. Love Breathing — Other creatures you control get +1/+1. Breathing — {T}, Pay 1 life: Target creature you control gains indestructible until end of turn.",
    setup_interceptors=mitsuri_kanroji_setup
)


def sanemi_shinazugawa_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wind Hashira - aggressive, marechi blood"""
    interceptors = []

    # When damaged, opponent's Demons get -1/-1
    def blood_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o in state.objects.values():
            if (o.controller != obj.controller and
                'Demon' in o.characteristics.subtypes and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(type=EventType.GRANT_PT_MODIFIER,
                    payload={'object_id': o.id, 'power': -1, 'toughness': -1, 'duration': 'end_of_turn'},
                    source=obj.id))
        return events

    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == source.id

    interceptors.append(make_damage_trigger(obj, blood_effect, filter_fn=damage_filter))

    return interceptors

SANEMI_SHINAZUGAWA = make_creature(
    name="Sanemi Shinazugawa, Wind Hashira",
    power=5,
    toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="First strike, haste. Marechi Blood — Whenever Sanemi is dealt damage, Demons your opponents control get -1/-1 until end of turn.",
    setup_interceptors=sanemi_shinazugawa_setup
)


def gyomei_himejima_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Stone Hashira - largest, most powerful"""
    interceptors = []

    # Stone Breathing - indestructible when blocking
    def block_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
            source=obj.id
        )]
    interceptors.append(make_block_trigger(obj, block_effect))

    return interceptors

GYOMEI_HIMEJIMA = make_creature(
    name="Gyomei Himejima, Stone Hashira",
    power=6,
    toughness=7,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="Vigilance, reach. Stone Breathing — Whenever Gyomei blocks, he gains indestructible until end of turn. Gyomei can block an additional creature each combat.",
    setup_interceptors=gyomei_himejima_setup
)


def tengen_uzui_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sound Hashira - flashy, dual wielding"""
    interceptors = []

    # Sound Breathing - double strike
    def sound_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'double_strike', 'duration': 'end_of_turn'},
            source=obj.id
        )]
    interceptors.append(make_breathing_attack_trigger(obj, sound_effect, life_cost=2))

    return interceptors

TENGEN_UZUI = make_creature(
    name="Tengen Uzui, Sound Hashira",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Slayer", "Hashira"},
    supertypes={"Legendary"},
    text="First strike. Breathing — Whenever Tengen attacks, you may pay 2 life. If you do, he gains double strike until end of turn. Flamboyant — Whenever Tengen deals combat damage to a player, draw a card.",
    setup_interceptors=tengen_uzui_setup
)


def nezuko_kamado_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Nezuko - demon that protects"""
    interceptors = []

    # Demon bonus
    interceptors.extend(make_demon_night_bonus(obj, 1, 1))

    # Protects Tanjiro
    def tanjiro_protection(target: GameObject, state: GameState) -> bool:
        return ('Tanjiro' in target.name and
                target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD)
    interceptors.append(make_keyword_grant(obj, ['hexproof'], tanjiro_protection))

    # Regeneration
    interceptors.append(make_regeneration(obj, 1))

    return interceptors

NEZUKO_KAMADO = make_creature(
    name="Nezuko Kamado",
    power=2,
    toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Demon — Nezuko gets +1/+1 during opponents' turns. Tanjiro creatures you control have hexproof. Blood Demon Art — {R}, Pay 1 life: Nezuko deals 2 damage to target creature.",
    setup_interceptors=nezuko_kamado_setup
)


def tanjiro_sun_breathing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tanjiro with Sun Breathing - ultimate form"""
    interceptors = []

    # Sun breathing destroys demons
    def sun_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Destroy target Demon
    interceptors.append(make_breathing_attack_trigger(obj, sun_effect, life_cost=2))

    # Demon Slayer Mark
    interceptors.extend(make_slayer_mark(obj))

    return interceptors

TANJIRO_SUN_BREATHING = make_creature(
    name="Tanjiro Kamado, Sun Breather",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Slayer"},
    supertypes={"Legendary"},
    text="Vigilance, haste. Sun Breathing — Whenever Tanjiro attacks, you may pay 2 life. If you do, destroy target Demon. Demon Slayer Mark — Tanjiro gets +2/+2 as long as you have 10 or less life.",
    setup_interceptors=tanjiro_sun_breathing_setup
)


HASHIRA_MEETING = make_sorcery(
    name="Hashira Meeting",
    mana_cost="{2}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    text="Search your library for up to three Hashira cards, reveal them, and put them into your hand. Then shuffle."
)


FINAL_FORM = make_instant(
    name="Final Form",
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Target Slayer you control gets +3/+3 and gains first strike, vigilance, and indestructible until end of turn. You lose 3 life."
)


DEMON_SLAYER_MARK_AWAKENING = make_enchantment(
    name="Demon Slayer Mark Awakening",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="At the beginning of your upkeep, you lose 1 life. Slayers you control get +2/+0 and have first strike."
)


COMBINED_BREATHING = make_instant(
    name="Combined Breathing Technique",
    mana_cost="{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    text="Target creature you control gets +3/+3 and gains flying, first strike, and trample until end of turn."
)


BONDS_OF_FRIENDSHIP = make_enchantment(
    name="Bonds of Friendship",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Whenever a Slayer you control dies, you may return target Slayer card from your graveyard to your hand. Slayers you control get +0/+1."
)


SUNRISE_COUNTDOWN = make_enchantment(
    name="Sunrise Countdown",
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="At the beginning of each end step, put a dawn counter on Sunrise Countdown. When Sunrise Countdown has five or more dawn counters, sacrifice it and destroy all Demons."
)


# =============================================================================
# ARTIFACTS - NICHIRIN BLADES AND EQUIPMENT
# =============================================================================

def nichirin_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Standard Nichirin blade"""
    return [make_nichirin_bonus_vs_demons(obj, 2)]

NICHIRIN_SWORD = make_artifact_equipment(
    name="Nichirin Sword",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1. Nichirin Blade — Equipped creature deals 2 extra damage to Demons. Equip {2}",
    setup_interceptors=nichirin_sword_setup
)


def red_nichirin_blade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Red blade prevents regeneration"""
    return [make_nichirin_bonus_vs_demons(obj, 3)]

RED_NICHIRIN_BLADE = make_artifact_equipment(
    name="Red Nichirin Blade",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has first strike. Nichirin Blade — Equipped creature deals 3 extra damage to Demons. Demons dealt damage by equipped creature can't regenerate this turn. Equip {3}",
    setup_interceptors=red_nichirin_blade_setup
)


GYOMEIS_FLAIL = make_artifact_equipment(
    name="Gyomei's Flail and Axe",
    mana_cost="{4}",
    text="Equipped creature gets +3/+3 and has reach. Whenever equipped creature blocks, it deals 2 damage to each creature it's blocking. Equip {3}",
    supertypes={"Legendary"}
)


TENGENS_CLEAVERS = make_artifact_equipment(
    name="Tengen's Cleavers",
    mana_cost="{3}",
    text="Equipped creature gets +2/+1 and has first strike. Whenever equipped creature deals combat damage to a player, you may pay 1 life. If you do, it gains double strike until end of turn. Equip {2}",
    supertypes={"Legendary"}
)


MITSURIS_WHIP_SWORD = make_artifact_equipment(
    name="Mitsuri's Whip Sword",
    mana_cost="{3}",
    text="Equipped creature gets +1/+2 and can block an additional creature each combat. Equipped creature has reach. Equip {2}",
    supertypes={"Legendary"}
)


SHINOBUS_STINGER = make_artifact_equipment(
    name="Shinobu's Stinger",
    mana_cost="{2}",
    text="Equipped creature gets +1/+0 and has deathtouch. Whenever equipped creature deals damage to a creature, put two -1/-1 counters on that creature. Equip {1}",
    supertypes={"Legendary"}
)


INOSUKES_JAGGED_BLADES = make_artifact_equipment(
    name="Inosuke's Jagged Blades",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0 and has trample. Equipped creature can't be blocked by creatures with power 2 or less. Equip {2}",
    supertypes={"Legendary"}
)


ZENITSU_BLADE = make_artifact_equipment(
    name="Zenitsu's Blade",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1. Whenever equipped creature becomes tapped, it gets +3/+0 until end of turn. Equip {1}",
    supertypes={"Legendary"}
)


WISTERIA_POISON = make_artifact(
    name="Wisteria Poison",
    mana_cost="{1}",
    text="{T}, Sacrifice Wisteria Poison: Destroy target Demon."
)


DEMON_SLAYER_UNIFORM = make_artifact_equipment(
    name="Demon Slayer Uniform",
    mana_cost="{1}",
    text="Equipped creature gets +0/+1 and has 'Damage dealt to this creature by Demons is reduced by 1.' Equip {1}"
)


KASUGAI_CROW = make_artifact(
    name="Kasugai Crow",
    mana_cost="{2}",
    text="Flying. {T}: Scry 1. {2}, {T}, Sacrifice Kasugai Crow: Draw a card."
)


SWORDSMITH_TOOLS = make_artifact(
    name="Swordsmith's Tools",
    mana_cost="{2}",
    text="{2}, {T}: Search your library for an Equipment card with mana value 3 or less, reveal it, put it into your hand, then shuffle."
)


MUZAN_BLOOD_VIAL = make_artifact(
    name="Muzan's Blood Vial",
    mana_cost="{2}",
    text="{3}, {T}, Sacrifice Muzan's Blood Vial: Target creature becomes a Demon in addition to its other types. Put three +1/+1 counters on it. It gains 'At the beginning of your upkeep, you lose 2 life.'"
)


DEMON_ART_FOCUS = make_artifact(
    name="Demon Art Focus",
    mana_cost="{3}",
    text="Blood Demon Art abilities you activate cost {1} less to activate. {T}: Add {B}."
)


# =============================================================================
# LANDS
# =============================================================================

BUTTERFLY_ESTATE = make_land(
    name="Butterfly Estate",
    text="{T}: Add {W}. {W}, {T}: You gain 1 life. Activate only if you control a Slayer."
)


MT_SAGIRI = make_land(
    name="Mt. Sagiri",
    text="{T}: Add {U}. {U}, {T}: Target Slayer you control can't be blocked this turn. Activate only as a sorcery."
)


INFINITY_CASTLE = make_land(
    name="Infinity Castle",
    text="{T}: Add {B}. {B}, {T}: Target Demon you control gets +1/+0 until end of turn.",
    supertypes={"Legendary"}
)


FLAME_TRAINING_GROUNDS = make_land(
    name="Flame Training Grounds",
    text="{T}: Add {R}. {R}, {T}: Target Slayer you control gets +1/+0 until end of turn."
)


WISTERIA_FOREST = make_land(
    name="Wisteria Forest",
    text="{T}: Add {G}. Demons can't attack you as long as you control three or more lands."
)


SWORDSMITH_VILLAGE = make_land(
    name="Swordsmith Village",
    text="{T}: Add {C}. {2}, {T}: Attach target Equipment you control to target creature you control.",
    supertypes={"Legendary"}
)


DEMON_SLAYER_HEADQUARTERS = make_land(
    name="Demon Slayer Headquarters",
    text="{T}: Add one mana of any color. This mana can only be spent to cast Slayer spells or activate abilities of Slayers.",
    supertypes={"Legendary"}
)


FINAL_SELECTION_MOUNTAIN = make_land(
    name="Final Selection Mountain",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast creature spells."
)


ENTERTAINMENT_DISTRICT = make_land(
    name="Entertainment District",
    text="{T}: Add {C}. {1}, {T}: Target creature can't block this turn."
)


MUGEN_TRAIN = make_land(
    name="Mugen Train",
    text="{T}: Add {C}. {3}, {T}: Put target creature on top of its owner's library.",
    supertypes={"Legendary"}
)


# Basic Lands with flavor
PLAINS_DMS = make_land(name="Plains", subtypes={"Plains"}, text="{T}: Add {W}.")
ISLAND_DMS = make_land(name="Island", subtypes={"Island"}, text="{T}: Add {U}.")
SWAMP_DMS = make_land(name="Swamp", subtypes={"Swamp"}, text="{T}: Add {B}.")
MOUNTAIN_DMS = make_land(name="Mountain", subtypes={"Mountain"}, text="{T}: Add {R}.")
FOREST_DMS = make_land(name="Forest", subtypes={"Forest"}, text="{T}: Add {G}.")


# =============================================================================
# ADDITIONAL WHITE CARDS
# =============================================================================

PILLAR_OF_STRENGTH = make_instant(
    name="Pillar of Strength",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+4 until end of turn. If it's a Slayer, it also gains vigilance."
)


def kanata_ubuyashiki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Daughter of Kagaya"""
    def slayer_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    def slayer_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                'Slayer' in entering.characteristics.subtypes)

    return [make_etb_trigger(obj, slayer_etb_effect, filter_fn=slayer_etb_filter)]

KANATA_UBUYASHIKI = make_creature(
    name="Kanata Ubuyashiki",
    power=1,
    toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Whenever a Slayer enters under your control, scry 1.",
    setup_interceptors=kanata_ubuyashiki_setup
)


DEMON_SLAYER_MARK_BEARER = make_creature(
    name="Demon Slayer Mark Bearer",
    power=3,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Demon Slayer Mark — As long as you have 10 or less life, Demon Slayer Mark Bearer gets +2/+2 and has first strike."
)


CORPS_MEDIC = make_creature(
    name="Corps Medic",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="{T}: Prevent the next 1 damage that would be dealt to target creature this turn. If it's a Slayer, prevent 2 damage instead."
)


# =============================================================================
# ADDITIONAL BLUE CARDS
# =============================================================================

ELEVENTH_FORM_DEAD_CALM = make_instant(
    name="Eleventh Form: Dead Calm",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. If you control a Slayer, draw a card."
)


WATER_BREATHING_MASTER = make_creature(
    name="Water Breathing Master",
    power=3,
    toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Slayer"},
    text="Whenever you activate a Breathing ability, draw a card. Breathing — {T}, Pay 1 life: Target creature can't attack this turn."
)


MIST_CLONE = make_instant(
    name="Mist Clone",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control, except it's an illusion in addition to its other types. Sacrifice it at the beginning of the next end step."
)


# =============================================================================
# ADDITIONAL BLACK CARDS
# =============================================================================

def enmu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lower Moon One - sleep demon"""
    interceptors = []
    interceptors.extend(make_demon_night_bonus(obj, 1, 1))

    def sleep_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Tap and don't untap
    interceptors.append(make_attack_trigger(obj, sleep_effect))
    return interceptors

ENMU = make_creature(
    name="Enmu, Lower Moon One",
    power=3,
    toughness=4,
    mana_cost="{2}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Demon — Enmu gets +1/+1 during opponents' turns. Blood Demon Art — Whenever Enmu attacks, tap target creature. It doesn't untap during its controller's next untap step.",
    setup_interceptors=enmu_setup
)


BLOOD_DEMON_ART_NIGHTMARE = make_sorcery(
    name="Blood Demon Art: Nightmare",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost, pay 2 life. Tap all creatures target opponent controls. Those creatures don't untap during their controller's next untap step."
)


DEVOUR_HUMANS = make_sorcery(
    name="Devour Humans",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target non-Demon creature. You gain life equal to its toughness."
)


# =============================================================================
# ADDITIONAL RED CARDS
# =============================================================================

GODSPEED = make_instant(
    name="Godspeed",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Target creature you control gets +3/+0 and gains first strike and haste until end of turn. If it's Zenitsu, it gains double strike instead of first strike."
)


FLAME_BREATHING_MASTER = make_creature(
    name="Flame Breathing Master",
    power=4,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Slayer"},
    text="Haste. Breathing — {T}, Pay 1 life: Flame Breathing Master deals 2 damage to any target."
)


RAGING_INFERNO = make_sorcery(
    name="Raging Inferno",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Raging Inferno deals 4 damage to each creature and each player. Demons dealt damage this way are exiled instead of put into a graveyard."
)


# =============================================================================
# ADDITIONAL GREEN CARDS
# =============================================================================

BEAST_SENSE = make_instant(
    name="Beast Sense",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+1 and gains hexproof until end of turn. If it's Inosuke, it also gains trample."
)


SERPENT_COILS = make_enchantment(
    name="Serpent Coils",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchanted creature has deathtouch and 'Whenever this creature deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step.'"
)


WISTERIA_GUARDIAN = make_creature(
    name="Wisteria Guardian",
    power=3,
    toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Reach. Demons can't attack you unless their controller pays {2} for each Demon they control that's attacking you."
)


# =============================================================================
# ADDITIONAL MULTICOLOR CARDS
# =============================================================================

def upper_moon_assembly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, search for a Demon"""
    def search_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Search handled by system
    return [make_etb_trigger(obj, search_effect)]

UPPER_MOON_ASSEMBLY = make_sorcery(
    name="Upper Moon Assembly",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Search your library for a Demon creature card, reveal it, put it into your hand, then shuffle. You lose 2 life."
)


TOTAL_CONCENTRATION_BREATHING = make_instant(
    name="Total Concentration Breathing",
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Target Slayer you control gets +2/+2 until end of turn. Until end of turn, Breathing abilities that creature activates cost no life to activate."
)


TEAMWORK = make_instant(
    name="Teamwork",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Up to two target Slayers you control each get +1/+1 and gain first strike until end of turn."
)


DEMON_SLAYER_LEGACY = make_enchantment(
    name="Demon Slayer Legacy",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Slayers you control get +1/+1. Whenever a Slayer you control dies, draw a card."
)


# =============================================================================
# FINAL ADDITIONAL CARDS TO REACH ~250
# =============================================================================

ROOKIE_SLAYER = make_creature(
    name="Rookie Slayer",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="When Rookie Slayer enters, you gain 1 life."
)


TRAINED_SLAYER = make_creature(
    name="Trained Slayer",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="First strike."
)


VETERAN_SLAYER = make_creature(
    name="Veteran Slayer",
    power=3,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Vigilance. Veteran Slayer gets +1/+1 as long as you control a Hashira."
)


FLEDGLING_DEMON = make_creature(
    name="Fledgling Demon",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Demon — Fledgling Demon gets +1/+1 during opponents' turns."
)


BLOODTHIRSTY_DEMON = make_creature(
    name="Bloodthirsty Demon",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Menace. Demon — Bloodthirsty Demon gets +2/+0 during opponents' turns."
)


ANCIENT_DEMON = make_creature(
    name="Ancient Demon",
    power=5,
    toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Demon — Ancient Demon gets +2/+2 during opponents' turns. At the beginning of your end step, you lose 1 life."
)


WATER_FORM_STRIKE = make_instant(
    name="Water Form Strike",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature gets -2/-0 until end of turn. If you control a Slayer, draw a card."
)


MIST_SHROUD = make_instant(
    name="Mist Shroud",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof until end of turn. Scry 1."
)


FIERY_ASSAULT = make_instant(
    name="Fiery Assault",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control deals damage equal to its power to target creature you don't control."
)


WILD_CHARGE = make_sorcery(
    name="Wild Charge",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +3/+3 and gains trample until end of turn. It must attack this turn if able."
)


DEMON_HUNTERS_VOW = make_enchantment(
    name="Demon Hunter's Vow",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Whenever you cast a Slayer spell, you gain 1 life."
)


BLOOD_MOON_RITUAL = make_sorcery(
    name="Blood Moon Ritual",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="As an additional cost, sacrifice a creature. Search your library for a Demon card, put it onto the battlefield, then shuffle."
)


HASHIRA_TRAINING = make_sorcery(
    name="Hashira Training",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on each Slayer you control. You gain 1 life for each Slayer you control."
)


DEMON_REGENERATION = make_instant(
    name="Demon Regeneration",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Regenerate target Demon. (The next time it would be destroyed this turn, instead tap it, remove all damage from it, and remove it from combat.)"
)


FIRST_BREATH = make_instant(
    name="First Breath",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature you control gets +1/+1 until end of turn. If it's a Slayer, untap it."
)


DEMON_BLOOD_FRENZY = make_enchantment(
    name="Demon Blood Frenzy",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchanted creature gets +2/+1 and attacks each combat if able. At the beginning of your upkeep, you lose 1 life."
)


SLAYER_COORDINATION = make_instant(
    name="Slayer Coordination",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Slayers you control get +1/+1 until end of turn. If you control three or more Slayers, they also gain vigilance until end of turn."
)


MIDNIGHT_HUNT = make_sorcery(
    name="Midnight Hunt",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature that was dealt damage this turn. If it was a Slayer, draw a card."
)


DAWN_BREAKS = make_sorcery(
    name="Dawn Breaks",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all Demons. You gain 2 life for each Demon destroyed this way."
)


DEMON_SLAYER_BLADE = make_instant(
    name="Demon Slayer's Strike",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control deals damage equal to its power to target Demon. If that Demon would die this turn, exile it instead."
)


SERPENT_STRIKE = make_instant(
    name="Serpent Strike",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gains deathtouch until end of turn. It fights target creature you don't control."
)


BLOOD_ART_EXPLOSION = make_instant(
    name="Blood Art: Explosion",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="As an additional cost, pay 2 life. Blood Art: Explosion deals 4 damage to target creature."
)


WATER_SURFACE = make_enchantment(
    name="Water Surface",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Creatures you control can't be blocked as long as they have no counters on them."
)


DEMON_PURSUIT = make_sorcery(
    name="Demon Pursuit",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature an opponent controls. If the creature you control survives, put a +1/+1 counter on it."
)


HASHIRA_WISDOM = make_sorcery(
    name="Hashira's Wisdom",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. If you control a Hashira, draw three cards instead, then discard a card."
)


FLAME_TIGERS = make_creature(
    name="Flame Tigers",
    power=3,
    toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Cat"},
    text="Haste. When Flame Tigers enters, it deals 2 damage to any target."
)


CORPS_SUPPLY_DEPOT = make_artifact(
    name="Corps Supply Depot",
    mana_cost="{3}",
    text="{T}: Add {C}. {2}, {T}: Draw a card. Activate only if you control a Slayer."
)


DEMON_LAIR = make_land(
    name="Demon Lair",
    text="{T}: Add {B}. Demons you control have 'At the beginning of your end step, remove 1 damage from this creature.'"
)


HASHIRA_ESTATE = make_land(
    name="Hashira Estate",
    text="{T}: Add one mana of any color. Spend this mana only to cast Hashira spells or activate abilities of Hashira.",
    supertypes={"Legendary"}
)


# =============================================================================
# ADDITIONAL CARDS - EXPANDING THE SET
# =============================================================================

# More White Cards
CORPS_MESSENGER = make_creature(
    name="Corps Messenger",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When Corps Messenger enters, look at the top card of your library. You may put it on the bottom."
)

PROTECTIVE_FORMATION = make_instant(
    name="Protective Formation",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control gain indestructible until end of turn. You gain 1 life for each Slayer you control."
)

DAWN_PATROL = make_creature(
    name="Dawn Patrol",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Vigilance. When Dawn Patrol enters, you gain 2 life."
)

CORPS_INSTRUCTOR = make_creature(
    name="Corps Instructor",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Other Slayers you control enter with an additional +1/+1 counter on them."
)

BLESSED_BLADE = make_instant(
    name="Blessed Blade",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature you control gets +1/+1 until end of turn. If it's equipped, it gets +2/+2 instead."
)

HEALING_MEDITATION = make_sorcery(
    name="Healing Meditation",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. Scry 2."
)

WISTERIA_BARRIER = make_enchantment(
    name="Wisteria Barrier",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Demons enter tapped. Demons don't untap during their controllers' untap steps unless that player pays {2} for each Demon they control."
)

CORPS_VETERAN = make_creature(
    name="Corps Veteran",
    power=3,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="First strike. When Corps Veteran dies, you may return another target Slayer card from your graveyard to your hand."
)

PURIFYING_LIGHT = make_instant(
    name="Purifying Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target Demon. You gain life equal to its power."
)

CORPS_UNITY = make_enchantment(
    name="Corps Unity",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Slayers you control get +0/+1. Whenever a Slayer you control attacks, you gain 1 life."
)

# More Blue Cards
WATER_CLONE = make_instant(
    name="Water Clone",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control. It's an Illusion in addition to its other types. Exile it at the beginning of the next end step."
)

MIST_WALKER = make_creature(
    name="Mist Walker",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Slayer"},
    text="Mist Walker can't be blocked. Whenever Mist Walker deals combat damage to a player, scry 1."
)

DEPTH_PERCEPTION = make_instant(
    name="Depth Perception",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library. Put one into your hand and the rest on the bottom of your library in any order."
)

FLUID_MOTION = make_enchantment(
    name="Fluid Motion",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Creatures you control can't be blocked by creatures with greater power."
)

WATER_WALL = make_instant(
    name="Water Wall",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature gets -4/-0 until end of turn. If it's a Demon, tap it."
)

SILENT_REFLECTION = make_sorcery(
    name="Silent Reflection",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards, then discard a card. If you discarded a Slayer card, draw another card."
)

OCEAN_DEEP = make_creature(
    name="Ocean Deep",
    power=3,
    toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Hexproof. Ocean Deep can block an additional creature each combat."
)

WAVE_DANCER = make_creature(
    name="Wave Dancer",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Slayer"},
    text="When Wave Dancer enters, target creature can't attack or block until your next turn."
)

TIDAL_SURGE = make_sorcery(
    name="Tidal Surge",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands."
)

REFLECTIVE_POOL = make_enchantment(
    name="Reflective Pool",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1. {2}{U}: Draw a card. Activate only once each turn."
)

# More Black Cards
BLOOD_PUPPET = make_creature(
    name="Blood Puppet",
    power=2,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Construct"},
    text="Demon — Blood Puppet gets +1/+1 during opponents' turns. When Blood Puppet dies, each opponent loses 1 life."
)

SOUL_HARVEST = make_sorcery(
    name="Soul Harvest",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each player sacrifices a creature. You draw a card for each creature sacrificed this way."
)

NIGHT_STALKER = make_creature(
    name="Night Stalker",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Demon — Night Stalker gets +2/+1 during opponents' turns. Menace."
)

CORRUPTING_INFLUENCE = make_enchantment(
    name="Corrupting Influence",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Whenever a non-Demon creature dies, you may pay 1 life. If you do, create a 1/1 black Demon creature token."
)

BLOOD_OFFERING = make_instant(
    name="Blood Offering",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost, pay 2 life. Target creature gets -2/-2 until end of turn."
)

DARK_CONSUMPTION = make_sorcery(
    name="Dark Consumption",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it was a Slayer, draw two cards and lose 2 life."
)

SHADOW_DEMON = make_creature(
    name="Shadow Demon",
    power=4,
    toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Demon — Shadow Demon gets +2/+2 during opponents' turns. Shadow Demon can't be blocked except by Demons or Slayers."
)

DEMONIC_PACT = make_enchantment(
    name="Demonic Pact",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, choose one that hasn't been chosen: Draw two cards; or target opponent discards two cards; or destroy target non-Demon creature; or you lose 8 life."
)

GRAVE_EMERGENCE = make_sorcery(
    name="Grave Emergence",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to your hand. If it's a Demon, put it onto the battlefield instead."
)

CURSED_BLOOD = make_instant(
    name="Cursed Blood",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -1/-1 until end of turn. If it's a Slayer, it gets -3/-3 instead."
)

# More Red Cards
BLAZING_SPEED = make_instant(
    name="Blazing Speed",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains haste until end of turn. It must attack this turn if able."
)

FLAME_DANCER = make_creature(
    name="Flame Dancer",
    power=2,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Slayer"},
    text="Haste. When Flame Dancer enters, it deals 1 damage to any target."
)

THUNDER_STRIKE = make_instant(
    name="Thunder Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Thunder Strike deals 3 damage to target creature. If it's a Demon, Thunder Strike deals 5 damage instead."
)

BATTLE_CRY = make_sorcery(
    name="Battle Cry",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 until end of turn."
)

RAGE_OF_THE_SUN = make_sorcery(
    name="Rage of the Sun",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Rage of the Sun deals 3 damage to each creature and each opponent. If it's day (your turn), it deals 5 damage instead."
)

LIGHTNING_REFLEXES = make_enchantment(
    name="Lightning Reflexes",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchanted creature gets +1/+0 and has first strike. {R}: Enchanted creature gets +1/+0 until end of turn."
)

BURNING_VENGEANCE = make_enchantment(
    name="Burning Vengeance",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever a Slayer you control deals damage to a Demon, Burning Vengeance deals 2 damage to that Demon's controller."
)

FLASH_STEP = make_instant(
    name="Flash Step",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gains first strike until end of turn. If it's a Slayer, it also gains +1/+0 until end of turn."
)

FIRE_BREATHING_STUDENT = make_creature(
    name="Fire Breathing Student",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Slayer"},
    text="Haste. {R}: Fire Breathing Student gets +1/+0 until end of turn."
)

EXPLOSIVE_STRIKE = make_instant(
    name="Explosive Strike",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature you control deals damage equal to its power to target creature or player."
)

# More Green Cards
FOREST_TRACKER = make_creature(
    name="Forest Tracker",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Slayer"},
    text="When Forest Tracker enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)

BEAST_COMPANION = make_creature(
    name="Beast Companion",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Beast Companion gets +1/+1 for each other Beast you control."
)

NATURE_BOND = make_enchantment(
    name="Nature's Bond",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Whenever a creature enters under your control, you gain 1 life."
)

SERPENT_AMBUSH = make_instant(
    name="Serpent Ambush",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gains deathtouch and fights target creature you don't control."
)

TOWERING_GUARDIAN = make_creature(
    name="Towering Guardian",
    power=4,
    toughness=6,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Reach, vigilance. Towering Guardian can block an additional creature each combat."
)

WILD_GROWTH = make_sorcery(
    name="Wild Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature. It gains trample until end of turn."
)

PACK_TACTICS = make_enchantment(
    name="Pack Tactics",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever you attack with two or more creatures, those creatures get +1/+1 until end of turn."
)

FERAL_INSTINCT = make_instant(
    name="Feral Instinct",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If it's a Beast or Slayer, it also gains trample."
)

ANCIENT_WISTERIA = make_creature(
    name="Ancient Wisteria",
    power=5,
    toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Elemental"},
    text="Reach, vigilance. Demons can't attack you. When Ancient Wisteria enters, destroy all Demons."
)

FOREST_AMBUSH = make_instant(
    name="Forest Ambush",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create two 1/1 green Beast creature tokens. They gain haste until end of turn."
)

# More Multicolor Cards
BLADE_MASTER = make_creature(
    name="Blade Master",
    power=3,
    toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="First strike, vigilance. Blade Master gets +1/+1 for each Equipment attached to it."
)

DEMON_HUNTER_ELITE = make_creature(
    name="Demon Hunter Elite",
    power=4,
    toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Vigilance. Demon Hunter Elite deals double damage to Demons."
)

NIGHT_TERROR = make_creature(
    name="Night Terror",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    text="Demon — Night Terror gets +3/+3 during opponents' turns. Haste. When Night Terror enters, it deals 2 damage to each opponent."
)

COORDINATED_STRIKE = make_instant(
    name="Coordinated Strike",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Up to two target creatures you control each get +2/+0 and gain first strike until end of turn."
)

DEMON_LORD = make_creature(
    name="Demon Lord",
    power=6,
    toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying. Demon — Demon Lord gets +2/+2 during opponents' turns. Other Demons you control get +1/+1."
)

SUNRISE_WARRIOR = make_creature(
    name="Sunrise Warrior",
    power=3,
    toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Slayer"},
    text="Haste. Whenever Sunrise Warrior attacks, it gets +2/+0 until end of turn if it's your turn."
)

SHADOW_AND_FLAME = make_instant(
    name="Shadow and Flame",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Shadow and Flame deals 3 damage to target creature. You lose 2 life."
)

UNITED_FRONT = make_sorcery(
    name="United Front",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Put a +1/+1 counter on each creature you control. You gain 1 life for each creature you control."
)

TWILIGHT_HUNTER = make_creature(
    name="Twilight Hunter",
    power=3,
    toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Slayer"},
    text="Flash. When Twilight Hunter enters, target creature gets -2/-2 until end of turn."
)

DEMON_BANE = make_instant(
    name="Demon Bane",
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Destroy target Demon. You gain 3 life."
)

# More Artifacts
TRAINING_DUMMY = make_artifact(
    name="Training Dummy",
    mana_cost="{2}",
    text="{T}: Put a +1/+1 counter on target Slayer you control."
)

HEALING_POTION = make_artifact(
    name="Healing Potion",
    mana_cost="{1}",
    text="{T}, Sacrifice Healing Potion: You gain 4 life."
)

DEMON_COMPASS = make_artifact(
    name="Demon Compass",
    mana_cost="{2}",
    text="{T}: Look at the top card of your library. If it's a Demon card, you may reveal it and put it into your hand."
)

REINFORCED_UNIFORM = make_artifact_equipment(
    name="Reinforced Uniform",
    mana_cost="{2}",
    text="Equipped creature gets +1/+2. Equip {2}"
)

SIGNAL_FLARE = make_artifact(
    name="Signal Flare",
    mana_cost="{1}",
    text="{T}, Sacrifice Signal Flare: Search your library for a Slayer card, reveal it, put it into your hand, then shuffle."
)

# More Lands
HIDDEN_VILLAGE = make_land(
    name="Hidden Village",
    text="{T}: Add {C}. {2}, {T}: Target creature you control gains hexproof until end of turn."
)

MOUNTAIN_PATH = make_land(
    name="Mountain Path",
    text="Mountain Path enters tapped. {T}: Add {R} or {W}."
)

DEMON_SHRINE = make_land(
    name="Demon Shrine",
    text="{T}: Add {C}. {B}, {T}: Target Demon you control gains indestructible until end of turn."
)

TRAINING_GROUNDS = make_land(
    name="Training Grounds",
    text="{T}: Add {C}. {1}, {T}: Put a +1/+1 counter on target creature you control that entered the battlefield this turn."
)

TWILIGHT_FOREST = make_land(
    name="Twilight Forest",
    text="Twilight Forest enters tapped. {T}: Add {G} or {B}."
)


# =============================================================================
# REGISTRY
# =============================================================================

DEMON_SLAYER_CARDS = {
    # WHITE - DEMON SLAYER CORPS
    "Kagaya Ubuyashiki": KAGAYA_UBUYASHIKI,
    "Corps Healer": CORPS_HEALER,
    "Butterfly Estate Nurse": BUTTERFLY_ESTATE_NURSE,
    "Demon Slayer Recruit": DEMON_SLAYER_RECRUIT,
    "Final Selection Survivor": FINAL_SELECTION_SURVIVOR,
    "Wisteria Ward": WISTERIA_WARD,
    "Sunlight Protection": SUNLIGHT_PROTECTION,
    "Total Concentration Constant": TOTAL_CONCENTRATION_CONSTANT,
    "Corps Training": CORPS_TRAINING,
    "Recovery at the Estate": RECOVERY_AT_THE_ESTATE,
    "Swordsmith Village Elder": SWORDSMITH_VILLAGE_ELDER,
    "Kakushi Messenger": KAKUSHI_MESSENGER,
    "Aoi Kanzaki": AOI_KANZAKI,
    "Demon Slayer Corps Banner": DEMON_SLAYER_CORPS_BANNER,
    "Wisteria Incense": WISTERIA_INCENSE,
    "Devoted Trainee": DEVOTED_TRAINEE,
    "Breath of Recovery": BREATH_OF_RECOVERY,
    "Sworn Protector": SWORN_PROTECTOR,
    "Ubuyashiki Blessing": UBUYASHIKI_BLESSING,
    "Corps Solidarity": CORPS_SOLIDARITY,
    "Pillar of Strength": PILLAR_OF_STRENGTH,
    "Kanata Ubuyashiki": KANATA_UBUYASHIKI,
    "Demon Slayer Mark Bearer": DEMON_SLAYER_MARK_BEARER,
    "Corps Medic": CORPS_MEDIC,
    "Rookie Slayer": ROOKIE_SLAYER,
    "Trained Slayer": TRAINED_SLAYER,
    "Veteran Slayer": VETERAN_SLAYER,
    "Demon Hunter's Vow": DEMON_HUNTERS_VOW,
    "Hashira Training": HASHIRA_TRAINING,
    "First Breath": FIRST_BREATH,
    "Slayer Coordination": SLAYER_COORDINATION,
    "Dawn Breaks": DAWN_BREAKS,
    "Demon Slayer's Strike": DEMON_SLAYER_BLADE,

    # BLUE - WATER/MIST BREATHING
    "Tanjiro Kamado, Water Breather": TANJIRO_WATER_BREATHING,
    "Sakonji Urokodaki": SAKONJI_UROKODAKI,
    "Water Surface Slash": WATER_SURFACE_SLASH,
    "Water Wheel": WATER_WHEEL,
    "Flowing Dance": FLOWING_DANCE,
    "Muichiro Tokito, Mist Hashira": MUICHIRO_TOKITO,
    "Obscuring Clouds": OBSCURING_CLOUDS,
    "Mist Breathing Form": MIST_BREATHING_FORM,
    "Sabito, Guiding Spirit": SABITO_SPIRIT,
    "Makomo, Teaching Spirit": MAKOMO_SPIRIT,
    "Whirlpool Technique": WHIRLPOOL_TECHNIQUE,
    "Waterfall Basin": WATERFALL_BASIN,
    "Water Breathing Student": WATER_BREATHING_STUDENT,
    "Dead Calm": DEAD_CALM,
    "Constant Flux": CONSTANT_FLUX,
    "Drop Ripple Thrust": DROP_RIPPLE_THRUST,
    "Splashing Water Flow": SPLASHING_WATER_FLOW,
    "Fog Concealment": FOG_CONCEALMENT,
    "Eleventh Form: Dead Calm": ELEVENTH_FORM_DEAD_CALM,
    "Water Breathing Master": WATER_BREATHING_MASTER,
    "Mist Clone": MIST_CLONE,
    "Water Form Strike": WATER_FORM_STRIKE,
    "Mist Shroud": MIST_SHROUD,
    "Water Surface": WATER_SURFACE,
    "Hashira's Wisdom": HASHIRA_WISDOM,

    # BLACK - DEMONS
    "Muzan Kibutsuji": MUZAN_KIBUTSUJI,
    "Akaza, Upper Moon Three": AKAZA,
    "Doma, Upper Moon Two": DOMA,
    "Kokushibo, Upper Moon One": KOKUSHIBO,
    "Nezuko, Awakened Demon": NEZUKO_DEMON_FORM,
    "Lower Moon Demon": LOWER_MOON_DEMON,
    "Temple Demon": TEMPLE_DEMON,
    "Hand Demon": HAND_DEMON,
    "Demonic Transformation": DEMONIC_TRANSFORMATION,
    "Blood Demon Art: Destruction": BLOOD_DEMON_ART_SPELL,
    "Muzan's Blood": MUZAN_BLOOD,
    "Demon Consumption": DEMON_CONSUMPTION,
    "Nightmare Blood Art": NIGHTMARE_BLOOD_ART,
    "Swamp Demon": SWAMP_DEMON,
    "Spider Demon Mother": SPIDER_DEMON_MOTHER,
    "Temptation of Eternity": TEMPTATION_OF_ETERNITY,
    "Kyogai, Drum Demon": DRUM_DEMON,
    "Endless Night": ENDLESS_NIGHT,
    "Enmu, Lower Moon One": ENMU,
    "Blood Demon Art: Nightmare": BLOOD_DEMON_ART_NIGHTMARE,
    "Devour Humans": DEVOUR_HUMANS,
    "Fledgling Demon": FLEDGLING_DEMON,
    "Bloodthirsty Demon": BLOODTHIRSTY_DEMON,
    "Ancient Demon": ANCIENT_DEMON,
    "Blood Moon Ritual": BLOOD_MOON_RITUAL,
    "Demon Regeneration": DEMON_REGENERATION,
    "Demon Blood Frenzy": DEMON_BLOOD_FRENZY,
    "Midnight Hunt": MIDNIGHT_HUNT,

    # RED - FLAME/THUNDER BREATHING
    "Kyojuro Rengoku, Flame Hashira": KYOJURO_RENGOKU,
    "Zenitsu Agatsuma": ZENITSU_AGATSUMA,
    "Thunderclap and Flash": THUNDERCLAP_AND_FLASH,
    "Flame Breathing: Unknowing Fire": FLAME_BREATHING_FIRST_FORM,
    "Flame Breathing: Rengoku": FLAME_BREATHING_NINTH_FORM,
    "Shinjuro Rengoku": SHINJURO_RENGOKU,
    "Burning Determination": BURNING_DETERMINATION,
    "Flame Breathing Student": FLAME_BREATHING_STUDENT,
    "Sixfold": SIXFOLD,
    "Thunder Breathing Form": THUNDER_BREATHING_FORM,
    "Kaigaku, Fallen Thunder": KAIGAKU,
    "Heat of Battle": HEAT_OF_BATTLE,
    "Explosive Blood": EXPLOSIVE_BLOOD,
    "Set Your Heart Ablaze": SET_YOUR_HEART_ABLAZE,
    "Thunder Breathing Student": THUNDER_BREATHING_STUDENT,
    "Blazing Rage": BLAZING_RAGE,
    "Flaming Blade": FLAMING_BLADE,
    "Godspeed": GODSPEED,
    "Flame Breathing Master": FLAME_BREATHING_MASTER,
    "Raging Inferno": RAGING_INFERNO,
    "Fiery Assault": FIERY_ASSAULT,
    "Blood Art: Explosion": BLOOD_ART_EXPLOSION,
    "Flame Tigers": FLAME_TIGERS,

    # GREEN - BEAST/SERPENT BREATHING
    "Inosuke Hashibira": INOSUKE_HASHIBIRA,
    "Obanai Iguro, Serpent Hashira": OBANAI_IGURO,
    "Beast Breathing: Fang": BEAST_BREATHING_FANG,
    "Serpent Breathing Form": SERPENT_BREATHING_FORM,
    "Wisteria Forest Guardian": FOREST_GUARDIAN,
    "Beast Breathing: Crazy Cutting": BEAST_BREATHING_SLICE,
    "Wild Instinct": WILD_INSTINCT,
    "Kaburamaru": KABURAMARU,
    "Devour Whole": DEVOUR_WHOLE,
    "Primal Fury": PRIMAL_FURY,
    "Mountain Boar": BOAR_MOUNT,
    "Serpentine Coil": SNAKE_COIL,
    "Wisteria Bloom": WISTERIA_BLOOM,
    "Spatial Awareness": NATURE_SENSE,
    "Forest Demon Hunter": FOREST_DEMON_HUNTER,
    "Overgrowth Technique": OVERGROWTH_TECHNIQUE,
    "Beast Sense": BEAST_SENSE,
    "Serpent Coils": SERPENT_COILS,
    "Wisteria Guardian": WISTERIA_GUARDIAN,
    "Wild Charge": WILD_CHARGE,
    "Demon Pursuit": DEMON_PURSUIT,
    "Serpent Strike": SERPENT_STRIKE,

    # MULTICOLOR - HASHIRA AND SPECIAL
    "Giyu Tomioka, Water Hashira": GIYU_TOMIOKA,
    "Shinobu Kocho, Insect Hashira": SHINOBU_KOCHO,
    "Mitsuri Kanroji, Love Hashira": MITSURI_KANROJI,
    "Sanemi Shinazugawa, Wind Hashira": SANEMI_SHINAZUGAWA,
    "Gyomei Himejima, Stone Hashira": GYOMEI_HIMEJIMA,
    "Tengen Uzui, Sound Hashira": TENGEN_UZUI,
    "Nezuko Kamado": NEZUKO_KAMADO,
    "Tanjiro Kamado, Sun Breather": TANJIRO_SUN_BREATHING,
    "Hashira Meeting": HASHIRA_MEETING,
    "Final Form": FINAL_FORM,
    "Demon Slayer Mark Awakening": DEMON_SLAYER_MARK_AWAKENING,
    "Combined Breathing Technique": COMBINED_BREATHING,
    "Bonds of Friendship": BONDS_OF_FRIENDSHIP,
    "Sunrise Countdown": SUNRISE_COUNTDOWN,
    "Upper Moon Assembly": UPPER_MOON_ASSEMBLY,
    "Total Concentration Breathing": TOTAL_CONCENTRATION_BREATHING,
    "Teamwork": TEAMWORK,
    "Demon Slayer Legacy": DEMON_SLAYER_LEGACY,

    # ARTIFACTS
    "Nichirin Sword": NICHIRIN_SWORD,
    "Red Nichirin Blade": RED_NICHIRIN_BLADE,
    "Gyomei's Flail and Axe": GYOMEIS_FLAIL,
    "Tengen's Cleavers": TENGENS_CLEAVERS,
    "Mitsuri's Whip Sword": MITSURIS_WHIP_SWORD,
    "Shinobu's Stinger": SHINOBUS_STINGER,
    "Inosuke's Jagged Blades": INOSUKES_JAGGED_BLADES,
    "Zenitsu's Blade": ZENITSU_BLADE,
    "Wisteria Poison": WISTERIA_POISON,
    "Demon Slayer Uniform": DEMON_SLAYER_UNIFORM,
    "Kasugai Crow": KASUGAI_CROW,
    "Swordsmith's Tools": SWORDSMITH_TOOLS,
    "Muzan's Blood Vial": MUZAN_BLOOD_VIAL,
    "Demon Art Focus": DEMON_ART_FOCUS,
    "Corps Supply Depot": CORPS_SUPPLY_DEPOT,

    # LANDS
    "Butterfly Estate": BUTTERFLY_ESTATE,
    "Mt. Sagiri": MT_SAGIRI,
    "Infinity Castle": INFINITY_CASTLE,
    "Flame Training Grounds": FLAME_TRAINING_GROUNDS,
    "Wisteria Forest": WISTERIA_FOREST,
    "Swordsmith Village": SWORDSMITH_VILLAGE,
    "Demon Slayer Headquarters": DEMON_SLAYER_HEADQUARTERS,
    "Final Selection Mountain": FINAL_SELECTION_MOUNTAIN,
    "Entertainment District": ENTERTAINMENT_DISTRICT,
    "Mugen Train": MUGEN_TRAIN,
    "Demon Lair": DEMON_LAIR,
    "Hashira Estate": HASHIRA_ESTATE,
    "Plains": PLAINS_DMS,
    "Island": ISLAND_DMS,
    "Swamp": SWAMP_DMS,
    "Mountain": MOUNTAIN_DMS,
    "Forest": FOREST_DMS,

    # ADDITIONAL WHITE CARDS
    "Corps Messenger": CORPS_MESSENGER,
    "Protective Formation": PROTECTIVE_FORMATION,
    "Dawn Patrol": DAWN_PATROL,
    "Corps Instructor": CORPS_INSTRUCTOR,
    "Blessed Blade": BLESSED_BLADE,
    "Healing Meditation": HEALING_MEDITATION,
    "Wisteria Barrier": WISTERIA_BARRIER,
    "Corps Veteran": CORPS_VETERAN,
    "Purifying Light": PURIFYING_LIGHT,
    "Corps Unity": CORPS_UNITY,

    # ADDITIONAL BLUE CARDS
    "Water Clone": WATER_CLONE,
    "Mist Walker": MIST_WALKER,
    "Depth Perception": DEPTH_PERCEPTION,
    "Fluid Motion": FLUID_MOTION,
    "Water Wall": WATER_WALL,
    "Silent Reflection": SILENT_REFLECTION,
    "Ocean Deep": OCEAN_DEEP,
    "Wave Dancer": WAVE_DANCER,
    "Tidal Surge": TIDAL_SURGE,
    "Reflective Pool": REFLECTIVE_POOL,

    # ADDITIONAL BLACK CARDS
    "Blood Puppet": BLOOD_PUPPET,
    "Soul Harvest": SOUL_HARVEST,
    "Night Stalker": NIGHT_STALKER,
    "Corrupting Influence": CORRUPTING_INFLUENCE,
    "Blood Offering": BLOOD_OFFERING,
    "Dark Consumption": DARK_CONSUMPTION,
    "Shadow Demon": SHADOW_DEMON,
    "Demonic Pact": DEMONIC_PACT,
    "Grave Emergence": GRAVE_EMERGENCE,
    "Cursed Blood": CURSED_BLOOD,

    # ADDITIONAL RED CARDS
    "Blazing Speed": BLAZING_SPEED,
    "Flame Dancer": FLAME_DANCER,
    "Thunder Strike": THUNDER_STRIKE,
    "Battle Cry": BATTLE_CRY,
    "Rage of the Sun": RAGE_OF_THE_SUN,
    "Lightning Reflexes": LIGHTNING_REFLEXES,
    "Burning Vengeance": BURNING_VENGEANCE,
    "Flash Step": FLASH_STEP,
    "Fire Breathing Student": FIRE_BREATHING_STUDENT,
    "Explosive Strike": EXPLOSIVE_STRIKE,

    # ADDITIONAL GREEN CARDS
    "Forest Tracker": FOREST_TRACKER,
    "Beast Companion": BEAST_COMPANION,
    "Nature's Bond": NATURE_BOND,
    "Serpent Ambush": SERPENT_AMBUSH,
    "Towering Guardian": TOWERING_GUARDIAN,
    "Wild Growth": WILD_GROWTH,
    "Pack Tactics": PACK_TACTICS,
    "Feral Instinct": FERAL_INSTINCT,
    "Ancient Wisteria": ANCIENT_WISTERIA,
    "Forest Ambush": FOREST_AMBUSH,

    # ADDITIONAL MULTICOLOR CARDS
    "Blade Master": BLADE_MASTER,
    "Demon Hunter Elite": DEMON_HUNTER_ELITE,
    "Night Terror": NIGHT_TERROR,
    "Coordinated Strike": COORDINATED_STRIKE,
    "Demon Lord": DEMON_LORD,
    "Sunrise Warrior": SUNRISE_WARRIOR,
    "Shadow and Flame": SHADOW_AND_FLAME,
    "United Front": UNITED_FRONT,
    "Twilight Hunter": TWILIGHT_HUNTER,
    "Demon Bane": DEMON_BANE,

    # ADDITIONAL ARTIFACTS
    "Training Dummy": TRAINING_DUMMY,
    "Healing Potion": HEALING_POTION,
    "Demon Compass": DEMON_COMPASS,
    "Reinforced Uniform": REINFORCED_UNIFORM,
    "Signal Flare": SIGNAL_FLARE,

    # ADDITIONAL LANDS
    "Hidden Village": HIDDEN_VILLAGE,
    "Mountain Path": MOUNTAIN_PATH,
    "Demon Shrine": DEMON_SHRINE,
    "Training Grounds": TRAINING_GROUNDS,
    "Twilight Forest": TWILIGHT_FOREST,
}

print(f"Loaded {len(DEMON_SLAYER_CARDS)} Demon Slayer cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    KAGAYA_UBUYASHIKI,
    CORPS_HEALER,
    BUTTERFLY_ESTATE_NURSE,
    DEMON_SLAYER_RECRUIT,
    FINAL_SELECTION_SURVIVOR,
    WISTERIA_WARD,
    SUNLIGHT_PROTECTION,
    TOTAL_CONCENTRATION_CONSTANT,
    CORPS_TRAINING,
    RECOVERY_AT_THE_ESTATE,
    SWORDSMITH_VILLAGE_ELDER,
    KAKUSHI_MESSENGER,
    AOI_KANZAKI,
    DEMON_SLAYER_CORPS_BANNER,
    WISTERIA_INCENSE,
    DEVOTED_TRAINEE,
    BREATH_OF_RECOVERY,
    SWORN_PROTECTOR,
    UBUYASHIKI_BLESSING,
    CORPS_SOLIDARITY,
    TANJIRO_WATER_BREATHING,
    SAKONJI_UROKODAKI,
    WATER_SURFACE_SLASH,
    WATER_WHEEL,
    FLOWING_DANCE,
    MUICHIRO_TOKITO,
    OBSCURING_CLOUDS,
    MIST_BREATHING_FORM,
    SABITO_SPIRIT,
    MAKOMO_SPIRIT,
    WHIRLPOOL_TECHNIQUE,
    WATERFALL_BASIN,
    WATER_BREATHING_STUDENT,
    DEAD_CALM,
    CONSTANT_FLUX,
    DROP_RIPPLE_THRUST,
    SPLASHING_WATER_FLOW,
    FOG_CONCEALMENT,
    MUZAN_KIBUTSUJI,
    AKAZA,
    DOMA,
    KOKUSHIBO,
    NEZUKO_DEMON_FORM,
    LOWER_MOON_DEMON,
    TEMPLE_DEMON,
    HAND_DEMON,
    DEMONIC_TRANSFORMATION,
    BLOOD_DEMON_ART_SPELL,
    MUZAN_BLOOD,
    DEMON_CONSUMPTION,
    NIGHTMARE_BLOOD_ART,
    SWAMP_DEMON,
    SPIDER_DEMON_MOTHER,
    TEMPTATION_OF_ETERNITY,
    DRUM_DEMON,
    ENDLESS_NIGHT,
    KYOJURO_RENGOKU,
    ZENITSU_AGATSUMA,
    THUNDERCLAP_AND_FLASH,
    FLAME_BREATHING_FIRST_FORM,
    FLAME_BREATHING_NINTH_FORM,
    SHINJURO_RENGOKU,
    BURNING_DETERMINATION,
    FLAME_BREATHING_STUDENT,
    SIXFOLD,
    THUNDER_BREATHING_FORM,
    KAIGAKU,
    HEAT_OF_BATTLE,
    EXPLOSIVE_BLOOD,
    SET_YOUR_HEART_ABLAZE,
    THUNDER_BREATHING_STUDENT,
    BLAZING_RAGE,
    FLAMING_BLADE,
    INOSUKE_HASHIBIRA,
    OBANAI_IGURO,
    BEAST_BREATHING_FANG,
    SERPENT_BREATHING_FORM,
    FOREST_GUARDIAN,
    BEAST_BREATHING_SLICE,
    WILD_INSTINCT,
    KABURAMARU,
    DEVOUR_WHOLE,
    PRIMAL_FURY,
    BOAR_MOUNT,
    SNAKE_COIL,
    WISTERIA_BLOOM,
    NATURE_SENSE,
    FOREST_DEMON_HUNTER,
    OVERGROWTH_TECHNIQUE,
    GIYU_TOMIOKA,
    SHINOBU_KOCHO,
    MITSURI_KANROJI,
    SANEMI_SHINAZUGAWA,
    GYOMEI_HIMEJIMA,
    TENGEN_UZUI,
    NEZUKO_KAMADO,
    TANJIRO_SUN_BREATHING,
    HASHIRA_MEETING,
    FINAL_FORM,
    DEMON_SLAYER_MARK_AWAKENING,
    COMBINED_BREATHING,
    BONDS_OF_FRIENDSHIP,
    SUNRISE_COUNTDOWN,
    NICHIRIN_SWORD,
    RED_NICHIRIN_BLADE,
    GYOMEIS_FLAIL,
    TENGENS_CLEAVERS,
    MITSURIS_WHIP_SWORD,
    SHINOBUS_STINGER,
    INOSUKES_JAGGED_BLADES,
    ZENITSU_BLADE,
    WISTERIA_POISON,
    DEMON_SLAYER_UNIFORM,
    KASUGAI_CROW,
    SWORDSMITH_TOOLS,
    MUZAN_BLOOD_VIAL,
    DEMON_ART_FOCUS,
    BUTTERFLY_ESTATE,
    MT_SAGIRI,
    INFINITY_CASTLE,
    FLAME_TRAINING_GROUNDS,
    WISTERIA_FOREST,
    SWORDSMITH_VILLAGE,
    DEMON_SLAYER_HEADQUARTERS,
    FINAL_SELECTION_MOUNTAIN,
    ENTERTAINMENT_DISTRICT,
    MUGEN_TRAIN,
    PLAINS_DMS,
    ISLAND_DMS,
    SWAMP_DMS,
    MOUNTAIN_DMS,
    FOREST_DMS,
    PILLAR_OF_STRENGTH,
    KANATA_UBUYASHIKI,
    DEMON_SLAYER_MARK_BEARER,
    CORPS_MEDIC,
    ELEVENTH_FORM_DEAD_CALM,
    WATER_BREATHING_MASTER,
    MIST_CLONE,
    ENMU,
    BLOOD_DEMON_ART_NIGHTMARE,
    DEVOUR_HUMANS,
    GODSPEED,
    FLAME_BREATHING_MASTER,
    RAGING_INFERNO,
    BEAST_SENSE,
    SERPENT_COILS,
    WISTERIA_GUARDIAN,
    UPPER_MOON_ASSEMBLY,
    TOTAL_CONCENTRATION_BREATHING,
    TEAMWORK,
    DEMON_SLAYER_LEGACY,
    ROOKIE_SLAYER,
    TRAINED_SLAYER,
    VETERAN_SLAYER,
    FLEDGLING_DEMON,
    BLOODTHIRSTY_DEMON,
    ANCIENT_DEMON,
    WATER_FORM_STRIKE,
    MIST_SHROUD,
    FIERY_ASSAULT,
    WILD_CHARGE,
    DEMON_HUNTERS_VOW,
    BLOOD_MOON_RITUAL,
    HASHIRA_TRAINING,
    DEMON_REGENERATION,
    FIRST_BREATH,
    DEMON_BLOOD_FRENZY,
    SLAYER_COORDINATION,
    MIDNIGHT_HUNT,
    DAWN_BREAKS,
    DEMON_SLAYER_BLADE,
    SERPENT_STRIKE,
    BLOOD_ART_EXPLOSION,
    WATER_SURFACE,
    DEMON_PURSUIT,
    HASHIRA_WISDOM,
    FLAME_TIGERS,
    CORPS_SUPPLY_DEPOT,
    DEMON_LAIR,
    HASHIRA_ESTATE,
    CORPS_MESSENGER,
    PROTECTIVE_FORMATION,
    DAWN_PATROL,
    CORPS_INSTRUCTOR,
    BLESSED_BLADE,
    HEALING_MEDITATION,
    WISTERIA_BARRIER,
    CORPS_VETERAN,
    PURIFYING_LIGHT,
    CORPS_UNITY,
    WATER_CLONE,
    MIST_WALKER,
    DEPTH_PERCEPTION,
    FLUID_MOTION,
    WATER_WALL,
    SILENT_REFLECTION,
    OCEAN_DEEP,
    WAVE_DANCER,
    TIDAL_SURGE,
    REFLECTIVE_POOL,
    BLOOD_PUPPET,
    SOUL_HARVEST,
    NIGHT_STALKER,
    CORRUPTING_INFLUENCE,
    BLOOD_OFFERING,
    DARK_CONSUMPTION,
    SHADOW_DEMON,
    DEMONIC_PACT,
    GRAVE_EMERGENCE,
    CURSED_BLOOD,
    BLAZING_SPEED,
    FLAME_DANCER,
    THUNDER_STRIKE,
    BATTLE_CRY,
    RAGE_OF_THE_SUN,
    LIGHTNING_REFLEXES,
    BURNING_VENGEANCE,
    FLASH_STEP,
    FIRE_BREATHING_STUDENT,
    EXPLOSIVE_STRIKE,
    FOREST_TRACKER,
    BEAST_COMPANION,
    NATURE_BOND,
    SERPENT_AMBUSH,
    TOWERING_GUARDIAN,
    WILD_GROWTH,
    PACK_TACTICS,
    FERAL_INSTINCT,
    ANCIENT_WISTERIA,
    FOREST_AMBUSH,
    BLADE_MASTER,
    DEMON_HUNTER_ELITE,
    NIGHT_TERROR,
    COORDINATED_STRIKE,
    DEMON_LORD,
    SUNRISE_WARRIOR,
    SHADOW_AND_FLAME,
    UNITED_FRONT,
    TWILIGHT_HUNTER,
    DEMON_BANE,
    TRAINING_DUMMY,
    HEALING_POTION,
    DEMON_COMPASS,
    REINFORCED_UNIFORM,
    SIGNAL_FLARE,
    HIDDEN_VILLAGE,
    MOUNTAIN_PATH,
    DEMON_SHRINE,
    TRAINING_GROUNDS,
    TWILIGHT_FOREST
]
