"""
Attack on Titan (AOT) Card Implementations

Set featuring ~250 cards.
Mechanics: ODM Gear, Titan Shift, Wall
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from src.cards import interceptor_helpers as ih
from typing import Optional, Callable


# =============================================================================
# POST-DSL MIGRATION HELPERS
# =============================================================================
# Replacements for the old src.engine.abilities DSL primitives. These are
# inlined closure-builders rather than class-based Abilities: each card wires
# its behaviour directly via setup_interceptors, with hand-written rules text.

def _scry_events(obj: GameObject, amount: int) -> list[Event]:
    """Emit a scry ACTIVATE placeholder event (matches old Scry(N).generate_events)."""
    return [Event(
        type=EventType.ACTIVATE,
        payload={'action': 'scry', 'amount': amount, 'player': obj.controller},
        source=obj.id,
        controller=obj.controller,
    )]


def _draw_events(obj: GameObject, amount: int = 1) -> list[Event]:
    return [Event(
        type=EventType.DRAW,
        payload={'player': obj.controller},
        source=obj.id,
        controller=obj.controller,
    ) for _ in range(amount)]


def _gain_life_events(obj: GameObject, amount: int) -> list[Event]:
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': obj.controller, 'amount': amount},
        source=obj.id,
        controller=obj.controller,
    )]


def _opponents_lose_life_events(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': opp, 'amount': -amount},
        source=obj.id,
        controller=obj.controller,
    ) for opp in ih.all_opponents(obj, state)]


def _subtype_etb_trigger(obj: GameObject, subtype: str, effect_fn, you_control: bool = False) -> Interceptor:
    """ETB trigger that fires when ANY creature with a given subtype enters the battlefield.

    Mirrors the old ETBTrigger(target=CreatureWithSubtype(...)) wiring. Default
    you_control=False matches DSL default (no controller restriction).
    """
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        if subtype not in (entering.characteristics.subtypes or set()):
            return False
        if you_control and entering.controller != source.controller:
            return False
        return True

    return ih.make_etb_trigger(obj, effect_fn, filter_fn=filter_fn)


def _another_creature_etb_trigger(obj: GameObject, effect_fn) -> Interceptor:
    """ETB trigger that fires when ANOTHER creature (not self) enters the battlefield."""
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return CardType.CREATURE in entering.characteristics.types

    return ih.make_etb_trigger(obj, effect_fn, filter_fn=filter_fn)


# =============================================================================
# SELF-KEYWORD & COMMON EFFECT BUILDERS
# =============================================================================

def _self_keywords(obj: GameObject, keywords: list[str]) -> Interceptor:
    """Grant a permanent keywords only to itself (flying on self, etc.)."""
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return ih.make_keyword_grant(obj, keywords, is_self)


def _damage_all_other_creatures(obj: GameObject, state: GameState, amount: int, include_own: bool = True) -> list[Event]:
    """Emit DAMAGE events targeting every creature except the source itself."""
    events = []
    for target in state.objects.values():
        if target.id == obj.id:
            continue
        if CardType.CREATURE not in target.characteristics.types:
            continue
        if target.zone != ZoneType.BATTLEFIELD:
            continue
        if not include_own and target.controller == obj.controller:
            continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': amount, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ))
    return events


def _damage_each_opponent(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    """Emit DAMAGE events hitting each opponent's life total (Beast Titan 'throws')."""
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': opp, 'amount': amount, 'source': obj.id},
        source=obj.id,
        controller=obj.controller,
    ) for opp in ih.all_opponents(obj, state)]


def _subtype_death_trigger(obj: GameObject, subtype: str, effect_fn, you_control: bool = False) -> Interceptor:
    """Death trigger that fires when ANY creature with a given subtype dies."""
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
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
        if CardType.CREATURE not in dying.characteristics.types:
            return False
        if subtype not in (dying.characteristics.subtypes or set()):
            return False
        if you_control and dying.controller != source.controller:
            return False
        return True

    return ih.make_death_trigger(obj, effect_fn, filter_fn=filter_fn)


def _another_creature_death_trigger(obj: GameObject, effect_fn) -> Interceptor:
    """Death trigger that fires when ANOTHER creature (not self) dies."""
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == source.id:
            return False
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return CardType.CREATURE in dying.characteristics.types

    return ih.make_death_trigger(obj, effect_fn, filter_fn=filter_fn)


def _subtype_attack_trigger(obj: GameObject, subtype: str, effect_fn, you_control: bool = True) -> Interceptor:
    """Attack trigger: fires when any creature with the given subtype attacks."""
    def filter_fn(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        if CardType.CREATURE not in attacker.characteristics.types:
            return False
        if subtype not in (attacker.characteristics.subtypes or set()):
            return False
        if you_control and attacker.controller != source.controller:
            return False
        return True

    return ih.make_attack_trigger(obj, effect_fn, filter_fn=filter_fn)


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


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, abilities=None):
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
        abilities=abilities
    )


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, abilities=None):
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
        abilities=abilities
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
# AOT KEYWORD MECHANICS
# =============================================================================

def make_odm_gear_bonus(source_obj: GameObject, equipped_creature_id: str) -> list[Interceptor]:
    """ODM Gear - Equipped creature gains flying and first strike."""
    from src.cards.interceptor_helpers import make_keyword_grant
    def is_equipped(target: GameObject, state: GameState) -> bool:
        return target.id == equipped_creature_id

    return [make_keyword_grant(source_obj, ['flying', 'first_strike'], is_equipped)]


def make_titan_shift(source_obj: GameObject, titan_power: int, titan_toughness: int, shift_cost_life: int = 3) -> Interceptor:
    """Titan Shift - Pay life to transform into Titan form with boosted stats."""
    def shift_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'titan_shift')

    def shift_handler(event: Event, state: GameState) -> InterceptorResult:
        life_payment = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -shift_cost_life},
            source=source_obj.id
        )
        transform_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': source_obj.id,
                'counter_type': 'titan_form',
                'power': titan_power,
                'toughness': titan_toughness,
                'duration': 'end_of_turn'
            },
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_payment, transform_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=shift_filter,
        handler=shift_handler,
        duration='while_on_battlefield'
    )


def make_wall_defense(source_obj: GameObject, toughness_bonus: int) -> list[Interceptor]:
    """Wall - Grants defender and bonus toughness to itself."""
    from src.cards.interceptor_helpers import make_keyword_grant, make_static_pt_boost
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id

    interceptors = []
    interceptors.append(make_keyword_grant(source_obj, ['defender'], is_self))
    interceptors.extend(make_static_pt_boost(source_obj, 0, toughness_bonus, is_self))
    return interceptors


# =============================================================================
# WHITE CARDS - SURVEY CORPS, HUMANITY'S HOPE
# =============================================================================

# --- Legendary Creatures ---

def _eren_yeager_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "I'll destroy them all!" Haste on self + attack trigger pumps other Scouts.
    scout_filter = ih.other_creatures_with_subtype(obj, "Scout")
    def attack_effect(event, s):
        # When he attacks, each other Scout gets +1/+0 and haste until end of turn.
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id,
        ) for target in s.objects.values() if scout_filter(target, s)]
    return [
        _self_keywords(obj, ['haste', 'trample']),
        ih.make_attack_trigger(obj, attack_effect),
    ]

EREN_YEAGER_SCOUT = make_creature(
    name="Eren Yeager, Survey Corps",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Haste, trample. Whenever Eren Yeager, Survey Corps attacks, other Scouts you control get +1/+0 until end of turn.",
    setup_interceptors=_eren_yeager_scout_setup,
)


def _mikasa_ackerman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Humanity's Strongest: self first strike + vigilance, other Scouts get +1/+1.
    other_scouts = ih.other_creatures_with_subtype(obj, "Scout")
    return [
        _self_keywords(obj, ['first_strike', 'vigilance']),
        *ih.make_static_pt_boost(obj, 1, 1, other_scouts),
    ]

MIKASA_ACKERMAN = make_creature(
    name="Mikasa Ackerman, Humanity's Strongest",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier", "Ackerman"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Other Scout creatures you control get +1/+1.",
    setup_interceptors=_mikasa_ackerman_setup,
)


def _armin_arlert_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event, s):
        return _scry_events(obj, 2) + _draw_events(obj, 1)
    return [ih.make_etb_trigger(obj, effect)]

ARMIN_ARLERT = make_creature(
    name="Armin Arlert, Tactician",
    power=1, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Scout", "Advisor"},
    supertypes={"Legendary"},
    text="When Armin Arlert, Tactician enters the battlefield, scry 2 and draw a card.",
    setup_interceptors=_armin_arlert_setup,
)


def _levi_ackerman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Humanity's Strongest: self has double strike, other Scouts get +1/+1.
    return [
        _self_keywords(obj, ['double_strike']),
        *ih.make_static_pt_boost(obj, 1, 1, ih.other_creatures_with_subtype(obj, "Scout")),
    ]

LEVI_ACKERMAN = make_creature(
    name="Levi Ackerman, Captain",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier", "Ackerman"},
    supertypes={"Legendary"},
    text="Double strike. Other Scout creatures you control get +1/+1.",
    setup_interceptors=_levi_ackerman_setup,
)


def _erwin_smith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Commander's Charge: on attack, draw a card (leadership = card advantage).
    return [
        _self_keywords(obj, ['vigilance']),
        ih.make_attack_trigger(obj, lambda e, s: _draw_events(obj, 1)),
    ]

ERWIN_SMITH = make_creature(
    name="Erwin Smith, Commander",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance. Whenever Erwin Smith, Commander attacks, draw a card.",
    setup_interceptors=_erwin_smith_setup,
)


def _hange_zoe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Titan-Study: ETB scry 1, and every Titan death teaches us something (draw).
    def titan_dies(event, s):
        return _scry_events(obj, 1) + _draw_events(obj, 1)
    return [
        ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 1)),
        _subtype_death_trigger(obj, "Titan", titan_dies),
    ]

HANGE_ZOE = make_creature(
    name="Hange Zoe, Researcher",
    power=2, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Scout", "Artificer"},
    supertypes={"Legendary"},
    text="When Hange Zoe enters the battlefield, scry 1. Whenever a Titan dies, scry 1 and draw a card.",
    setup_interceptors=_hange_zoe_setup,
)


# --- Regular Creatures ---

def _survey_corps_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _gain_life_events(obj, 2))]

SURVEY_CORPS_RECRUIT = make_creature(
    name="Survey Corps Recruit",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="When Survey Corps Recruit enters the battlefield, you gain 2 life.",
    setup_interceptors=_survey_corps_recruit_setup,
)


def _survey_corps_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['first_strike'])]

SURVEY_CORPS_VETERAN = make_creature(
    name="Survey Corps Veteran",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="First strike.",
    setup_interceptors=_survey_corps_veteran_setup,
)


def _garrison_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_block_trigger(obj, lambda e, s: _gain_life_events(obj, 2))]

GARRISON_SOLDIER = make_creature(
    name="Garrison Soldier",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever Garrison Soldier blocks, you gain 2 life.",
    setup_interceptors=_garrison_soldier_setup,
)


def _military_police_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['lifelink'])]

MILITARY_POLICE_OFFICER = make_creature(
    name="Military Police Officer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    text="Lifelink.",
    setup_interceptors=_military_police_officer_setup,
)


def wall_defender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """High toughness defender"""
    return make_wall_defense(obj, 2)

WALL_DEFENDER = make_creature(
    name="Wall Defender",
    power=0, toughness=6,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wall"},
    setup_interceptors=wall_defender_setup
)


def _training_corps_cadet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # A fallen cadet spurs the others: draw a card when this dies.
    return [ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 1))]

TRAINING_CORPS_CADET = make_creature(
    name="Training Corps Cadet",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Training Corps Cadet dies, draw a card.",
    setup_interceptors=_training_corps_cadet_setup,
)


def _historia_reiss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 1, 1, ih.other_creatures_with_subtype(obj, "Human"))

HISTORIA_REISS = make_creature(
    name="Historia Reiss, True Queen",
    power=2, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Other Human creatures you control get +1/+1.",
    setup_interceptors=_historia_reiss_setup,
)


def _sasha_blouse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Potato Girl: self reach, ETB gain 2 life (hunted a meal).
    return [
        _self_keywords(obj, ['reach']),
        ih.make_etb_trigger(obj, lambda e, s: _gain_life_events(obj, 2)),
    ]

SASHA_BLOUSE = make_creature(
    name="Sasha Blouse, Hunter",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Reach. When Sasha Blouse, Hunter enters the battlefield, you gain 2 life.",
    setup_interceptors=_sasha_blouse_setup,
)


def _connie_springer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Loyal friend: haste + draw on death (he goes out swinging).
    return [
        _self_keywords(obj, ['haste']),
        ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 1)),
    ]

CONNIE_SPRINGER = make_creature(
    name="Connie Springer, Loyal Friend",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Haste. When Connie Springer dies, draw a card.",
    setup_interceptors=_connie_springer_setup,
)


def _jean_kirstein_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_keyword_grant(obj, ["vigilance"], ih.other_creatures_with_subtype(obj, "Scout"))]

JEAN_KIRSTEIN = make_creature(
    name="Jean Kirstein, Natural Leader",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Other Scout creatures you control have vigilance.",
    setup_interceptors=_jean_kirstein_setup,
)


def _miche_zacharias_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Squad Leader scents Titans: self vigilance + other Scouts get vigilance.
    return [
        _self_keywords(obj, ['vigilance']),
        ih.make_keyword_grant(obj, ['vigilance'], ih.other_creatures_with_subtype(obj, "Scout")),
    ]

MICHE_ZACHARIAS = make_creature(
    name="Miche Zacharias, Squad Leader",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance. Other Scout creatures you control have vigilance.",
    setup_interceptors=_miche_zacharias_setup,
)


def _petra_ral_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ODM-mobile. Dies helping the squad; her loss buffs.
    return [
        _self_keywords(obj, ['flying']),
        ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 1)),
    ]

PETRA_RAL = make_creature(
    name="Petra Ral, Levi Squad",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Flying. When Petra Ral dies, draw a card.",
    setup_interceptors=_petra_ral_setup,
)


def _oluo_bozado_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Levi Squad ODM specialist: first strike.
    return [_self_keywords(obj, ['first_strike'])]

OLUO_BOZADO = make_creature(
    name="Oluo Bozado, Levi Squad",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="First strike.",
    setup_interceptors=_oluo_bozado_setup,
)


def _squad_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB create a 1/1 Scout Soldier token.
    def etb_effect(event, s):
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Scout',
                    'power': 1, 'toughness': 1,
                    'colors': {Color.WHITE},
                    'subtypes': {'Human', 'Scout', 'Soldier'},
                },
            },
            source=obj.id,
        )]
    return [ih.make_etb_trigger(obj, etb_effect)]

SQUAD_CAPTAIN = make_creature(
    name="Squad Captain",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="When Squad Captain enters the battlefield, create a 1/1 white Human Scout Soldier creature token.",
    setup_interceptors=_squad_captain_setup,
)


def _wall_garrison_elite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Wall mechanic + vigilance.
    return make_wall_defense(obj, 1) + [_self_keywords(obj, ['vigilance'])]

WALL_GARRISON_ELITE = make_creature(
    name="Wall Garrison Elite",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender, vigilance. (Gets +0/+1 from its Wall training.)",
    setup_interceptors=_wall_garrison_elite_setup,
)


def _interior_police_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Flash + deathtouch — the Interior Police strike from shadows.
    return [_self_keywords(obj, ['flash', 'deathtouch'])]

INTERIOR_POLICE = make_creature(
    name="Interior Police",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Rogue"},
    text="Flash, deathtouch.",
    setup_interceptors=_interior_police_setup,
)


def _shiganshina_citizen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_death_trigger(obj, lambda e, s: _gain_life_events(obj, 2))]

SHIGANSHINA_CITIZEN = make_creature(
    name="Shiganshina Citizen",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Shiganshina Citizen dies, you gain 2 life.",
    setup_interceptors=_shiganshina_citizen_setup,
)


def _eldian_refugee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _gain_life_events(obj, 1))]

ELDIAN_REFUGEE = make_creature(
    name="Eldian Refugee",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Eldian Refugee enters the battlefield, you gain 1 life.",
    setup_interceptors=_eldian_refugee_setup,
)


def _wall_cultist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_wall_defense(obj, 1)

WALL_CULTIST = make_creature(
    name="Wall Cultist",
    power=0, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric", "Wall"},
    text="Defender. (Gets +0/+1.)",
    setup_interceptors=_wall_cultist_setup,
)


def _horse_mounted_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste'])]

HORSE_MOUNTED_SCOUT = make_creature(
    name="Horse Mounted Scout",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="Haste.",
    setup_interceptors=_horse_mounted_scout_setup,
)


# --- Instants ---

DEVOTED_HEART = make_instant(
    name="Devoted Heart",
    mana_cost="{W}",
    colors={Color.WHITE},
    # Complex conditional effect
)


SURVEY_CORPS_CHARGE = make_instant(
    name="Survey Corps Charge",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    # Complex pump effect
)


WALL_DEFENSE = make_instant(
    name="Wall Defense",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    # Complex pump effect
)


HUMANITYS_HOPE = make_instant(
    name="Humanity's Hope",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    # Exile + life gain
)


SALUTE_OF_HEARTS = make_instant(
    name="Salute of Hearts",
    mana_cost="{W}",
    colors={Color.WHITE},
    # Complex conditional effect
)


STRATEGIC_RETREAT = make_instant(
    name="Strategic Retreat",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    # Bounce + life gain
)


FORMATION_BREAK = make_instant(
    name="Formation Break",
    mana_cost="{W}",
    colors={Color.WHITE},
    # Grant flying + draw
)


GARRISON_REINFORCEMENTS = make_instant(
    name="Garrison Reinforcements",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    # Create tokens
)


# --- Sorceries ---

SURVEY_MISSION = make_sorcery(
    name="Survey Mission",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 white Human Scout Soldier creature tokens with vigilance."
)


EVACUATION_ORDER = make_sorcery(
    name="Evacuation Order",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return all creatures to their owners' hands."
)


WALL_RECONSTRUCTION = make_sorcery(
    name="Wall Reconstruction",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures with power 4 or greater. You gain 2 life for each creature destroyed this way."
)


TRAINING_EXERCISE = make_sorcery(
    name="Training Exercise",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature becomes a Scout in addition to its other types and gets +1/+1 until end of turn. Draw a card."
)


# --- Enchantments ---

def _survey_corps_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 1, 1, ih.creatures_with_subtype(obj, "Scout"))

SURVEY_CORPS_BANNER = make_enchantment(
    name="Survey Corps Banner",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Scout creatures you control get +1/+1.",
    setup_interceptors=_survey_corps_banner_setup,
)


def _wings_of_freedom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_keyword_grant(obj, ["flying"], ih.creatures_with_subtype(obj, "Scout"))]

WINGS_OF_FREEDOM = make_enchantment(
    name="Wings of Freedom",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Scout creatures you control have flying.",
    setup_interceptors=_wings_of_freedom_setup,
)


def _wall_faith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Wall Faith anthem: Wall creatures you control get +0/+2.
    return ih.make_static_pt_boost(obj, 0, 2, ih.creatures_with_subtype(obj, "Wall"))

WALL_FAITH = make_enchantment(
    name="Wall Faith",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Wall creatures you control get +0/+2.",
    setup_interceptors=_wall_faith_setup,
)


# =============================================================================
# BLUE CARDS - STRATEGY, PLANNING, INTELLIGENCE
# =============================================================================

# --- Legendary Creatures ---

def _armin_colossal_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Steam explosion ETB: deal 5 damage to every other creature.
    def etb_effect(event, s):
        return _damage_all_other_creatures(obj, s, 5)
    return [
        _self_keywords(obj, ['trample']),
        ih.make_etb_trigger(obj, etb_effect),
    ]

ARMIN_COLOSSAL_TITAN = make_creature(
    name="Armin, Colossal Titan",
    power=10, toughness=10,
    mana_cost="{5}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Trample. When Armin, Colossal Titan enters the battlefield, it deals 5 damage to each other creature.",
    setup_interceptors=_armin_colossal_titan_setup,
)


def _erwin_gambit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Text says "When ~ enters, scry 1" (simplified from spell-cast trigger).
    return [ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 1))]

ERWIN_GAMBIT = make_creature(
    name="Erwin Smith, The Gambit",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout", "Noble"},
    supertypes={"Legendary"},
    text="When Erwin Smith, The Gambit enters the battlefield, scry 1.",
    setup_interceptors=_erwin_gambit_setup,
)


def _pieck_finger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Cart Titan logistics carrier: vigilance (stays back) + flash-like utility via vigilance+trample.
    return [_self_keywords(obj, ['vigilance', 'trample'])]

PIECK_FINGER = make_creature(
    name="Pieck Finger, Cart Titan",
    power=3, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Vigilance, trample.",
    setup_interceptors=_pieck_finger_setup,
)


# --- Regular Creatures ---

def _intelligence_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 2))]

INTELLIGENCE_OFFICER = make_creature(
    name="Intelligence Officer",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout", "Advisor"},
    text="When Intelligence Officer enters the battlefield, scry 2.",
    setup_interceptors=_intelligence_officer_setup,
)


def _marleyan_spy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['flying'])]

MARLEYAN_SPY = make_creature(
    name="Marleyan Spy",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Flying.",
    setup_interceptors=_marleyan_spy_setup,
)


def _survey_cartographer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 1))]

SURVEY_CARTOGRAPHER = make_creature(
    name="Survey Cartographer",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="When Survey Cartographer enters the battlefield, scry 1.",
    setup_interceptors=_survey_cartographer_setup,
)


def _titan_researcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_subtype_etb_trigger(obj, "Titan", lambda e, s: _draw_events(obj, 1))]

TITAN_RESEARCHER = make_creature(
    name="Titan Researcher",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="Whenever Titan enters the battlefield, draw a card.",
    setup_interceptors=_titan_researcher_setup,
)


def _strategic_advisor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Grants flying to a Scout on ETB (ODM coordination).
    def etb_effect(event, s):
        scouts = ih.other_creatures_with_subtype(obj, "Scout")
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': t.id, 'keyword': 'flying', 'duration': 'end_of_turn'},
            source=obj.id,
        ) for t in s.objects.values() if scouts(t, s)]
    return [ih.make_etb_trigger(obj, etb_effect)]

STRATEGIC_ADVISOR = make_creature(
    name="Strategic Advisor",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text="When Strategic Advisor enters the battlefield, each other Scout you control gains flying until end of turn.",
    setup_interceptors=_strategic_advisor_setup,
)


def _wall_architect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB create a 0/4 Wall token with defender.
    def etb_effect(event, s):
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Wall',
                    'power': 0, 'toughness': 4,
                    'colors': {Color.WHITE},
                    'subtypes': {'Wall'},
                    'keywords': ['defender'],
                },
            },
            source=obj.id,
        )]
    return [ih.make_etb_trigger(obj, etb_effect)]

WALL_ARCHITECT = make_creature(
    name="Wall Architect",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="When Wall Architect enters the battlefield, create a 0/4 white Wall creature token with defender.",
    setup_interceptors=_wall_architect_setup,
)


def _military_tactician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['flash'])]

MILITARY_TACTICIAN = make_creature(
    name="Military Tactician",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier", "Advisor"},
    text="Flash.",
    setup_interceptors=_military_tactician_setup,
)


def _signal_corps_operator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB scry 1 (sent a flare signal).
    return [ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 1))]

SIGNAL_CORPS_OPERATOR = make_creature(
    name="Signal Corps Operator",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="When Signal Corps Operator enters the battlefield, scry 1.",
    setup_interceptors=_signal_corps_operator_setup,
)


def _supply_corps_quartermaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _draw_events(obj, 1))]

SUPPLY_CORPS_QUARTERMASTER = make_creature(
    name="Supply Corps Quartermaster",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="When Supply Corps Quartermaster enters the battlefield, draw a card.",
    setup_interceptors=_supply_corps_quartermaster_setup,
)


def _coastal_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['flying'])]

COASTAL_SCOUT = make_creature(
    name="Coastal Scout",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="Flying.",
    setup_interceptors=_coastal_scout_setup,
)


def _formation_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['defender']), ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 1))]

FORMATION_ANALYST = make_creature(
    name="Formation Analyst",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text="Defender. When Formation Analyst enters the battlefield, scry 1.",
    setup_interceptors=_formation_analyst_setup,
)


# --- Instants ---

STRATEGIC_ANALYSIS = make_instant(
    name="Strategic Analysis",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    # Draw two
)


TACTICAL_RETREAT = make_instant(
    name="Tactical Retreat",
    mana_cost="{U}",
    colors={Color.BLUE},
    # Bounce + scry
)


FORMATION_SHIFT = make_instant(
    name="Formation Shift",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    # Bounce + draw
)


COUNTER_STRATEGY = make_instant(
    name="Counter Strategy",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    # Counter spell
)


FLARE_SIGNAL = make_instant(
    name="Flare Signal",
    mana_cost="{U}",
    colors={Color.BLUE},
    # Tap/untap + draw
)


INTELLIGENCE_REPORT = make_instant(
    name="Intelligence Report",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    # Conditional draw
)


RECONNAISSANCE = make_instant(
    name="Reconnaissance",
    mana_cost="{U}",
    colors={Color.BLUE},
    # Impulse effect
)


ESCAPE_ROUTE = make_instant(
    name="Escape Route",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    # Double bounce
)


# --- Sorceries ---

SURVEY_THE_LAND = make_sorcery(
    name="Survey the Land",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card."
)


MAPPING_EXPEDITION = make_sorcery(
    name="Mapping Expedition",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Draw four cards."
)


MEMORY_WIPE = make_sorcery(
    name="Memory Wipe",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Target player shuffles their hand into their library, then draws that many cards."
)


# --- Enchantments ---

def _strategic_planning_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Upkeep scry 1.
    return [ih.make_upkeep_trigger(obj, lambda e, s: _scry_events(obj, 1))]

STRATEGIC_PLANNING = make_enchantment(
    name="Strategic Planning",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1.",
    setup_interceptors=_strategic_planning_setup,
)


def _information_network_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_another_creature_etb_trigger(obj, lambda e, s: _scry_events(obj, 1))]

INFORMATION_NETWORK = make_enchantment(
    name="Information Network",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever another creature enters the battlefield, scry 1.",
    setup_interceptors=_information_network_setup,
)


# =============================================================================
# BLACK CARDS - MARLEY, WARRIORS, BETRAYAL
# =============================================================================

# --- Legendary Creatures ---

def reiner_braun_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Titan Shift - becomes 6/6"""
    return [make_titan_shift(obj, 6, 6, 3)]

REINER_BRAUN = make_creature(
    name="Reiner Braun, Armored Titan",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    setup_interceptors=reiner_braun_setup
)


def _bertholdt_hoover_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Colossal kick ETB: deal 4 damage to each other creature; trample.
    def etb_effect(event, s):
        return _damage_all_other_creatures(obj, s, 4)
    return [
        _self_keywords(obj, ['trample']),
        ih.make_etb_trigger(obj, etb_effect),
    ]

BERTHOLDT_HOOVER = make_creature(
    name="Bertholdt Hoover, Colossal Titan",
    power=10, toughness=10,
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Trample. When Bertholdt Hoover enters the battlefield, it deals 4 damage to each other creature.",
    setup_interceptors=_bertholdt_hoover_setup,
)


def _annie_leonhart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Hardening: static indestructible + deathtouch — crystallization made flesh.
    return [_self_keywords(obj, ['indestructible', 'deathtouch'])]

ANNIE_LEONHART = make_creature(
    name="Annie Leonhart, Female Titan",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Indestructible, deathtouch. (Hardening — her crystal armor cannot be shattered.)",
    setup_interceptors=_annie_leonhart_setup,
)


def _zeke_yeager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Beast Titan: "throws" rocks. Attack trigger deals 2 to each opponent.
    # Plus +2/+2 anthem for other Titans. Self reach (he throws from the back).
    def throw(event, s):
        return _damage_each_opponent(obj, s, 2)
    return [
        _self_keywords(obj, ['reach']),
        *ih.make_static_pt_boost(obj, 2, 2, ih.other_creatures_with_subtype(obj, "Titan")),
        ih.make_attack_trigger(obj, throw),
    ]

ZEKE_YEAGER = make_creature(
    name="Zeke Yeager, Beast Titan",
    power=6, toughness=6,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Reach. Other Titan creatures you control get +2/+2. Whenever Zeke Yeager attacks, he deals 2 damage to each opponent.",
    setup_interceptors=_zeke_yeager_setup,
)


def _war_hammer_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # First strike (the hammer swings before they can reach her).
    return [_self_keywords(obj, ['first_strike', 'trample'])]

WAR_HAMMER_TITAN = make_creature(
    name="War Hammer Titan",
    power=5, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="First strike, trample.",
    setup_interceptors=_war_hammer_titan_setup,
)


# --- Regular Creatures ---

def _marleyan_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['menace'])]

MARLEYAN_WARRIOR = make_creature(
    name="Marleyan Warrior",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Soldier"},
    text="Menace.",
    setup_interceptors=_marleyan_warrior_setup,
)


def _warrior_candidate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_death_trigger(obj, lambda e, s: _opponents_lose_life_events(obj, s, 2))]

WARRIOR_CANDIDATE = make_creature(
    name="Warrior Candidate",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="When Warrior Candidate dies, each opponent loses 2 life.",
    setup_interceptors=_warrior_candidate_setup,
)


def _marleyan_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['deathtouch'])]

MARLEYAN_OFFICER = make_creature(
    name="Marleyan Officer",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Deathtouch.",
    setup_interceptors=_marleyan_officer_setup,
)


def _infiltrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['menace'])]

INFILTRATOR = make_creature(
    name="Infiltrator",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Menace.",
    setup_interceptors=_infiltrator_setup,
)


def _eldian_internment_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_another_creature_death_trigger(obj, lambda e, s: _gain_life_events(obj, 1))]

ELDIAN_INTERNMENT_GUARD = make_creature(
    name="Eldian Internment Guard",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Whenever another creature dies, you gain 1 life.",
    setup_interceptors=_eldian_internment_guard_setup,
)


def _titan_inheritor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Inheritor draws power from death: ETB draw 1.
    return [ih.make_etb_trigger(obj, lambda e, s: _draw_events(obj, 1))]

TITAN_INHERITOR = make_creature(
    name="Titan Inheritor",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="When Titan Inheritor enters the battlefield, draw a card.",
    setup_interceptors=_titan_inheritor_setup,
)


def _military_executioner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['deathtouch', 'menace'])]

MILITARY_EXECUTIONER = make_creature(
    name="Military Executioner",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Deathtouch, menace.",
    setup_interceptors=_military_executioner_setup,
)


def _restorationist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB each opponent loses 1 life (blood-spilling fanatic).
    return [ih.make_etb_trigger(obj, lambda e, s: _opponents_lose_life_events(obj, s, 1))]

RESTORATIONIST = make_creature(
    name="Restorationist",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Cleric"},
    text="When Restorationist enters the battlefield, each opponent loses 1 life.",
    setup_interceptors=_restorationist_setup,
)


def _pure_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Mindless hungry — trample. The basic Titan.
    return [_self_keywords(obj, ['trample'])]

PURE_TITAN = make_creature(
    name="Pure Titan",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Trample.",
    setup_interceptors=_pure_titan_setup,
)


def _abnormal_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Unpredictable — haste + trample.
    return [_self_keywords(obj, ['haste', 'trample'])]

ABNORMAL_TITAN = make_creature(
    name="Abnormal Titan",
    power=5, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Haste, trample.",
    setup_interceptors=_abnormal_titan_setup,
)


def _small_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste'])]

SMALL_TITAN = make_creature(
    name="Small Titan",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Haste.",
    setup_interceptors=_small_titan_setup,
)


def _titan_horde_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB create two 2/2 Titan tokens (the horde).
    def etb_effect(event, s):
        token = {
            'controller': obj.controller,
            'token': {
                'name': 'Pure Titan',
                'power': 2, 'toughness': 2,
                'colors': {Color.BLACK},
                'subtypes': {'Titan'},
            },
        }
        return [
            Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload=dict(token), source=obj.id),
        ]
    return [
        _self_keywords(obj, ['trample']),
        ih.make_etb_trigger(obj, etb_effect),
    ]

TITAN_HORDE = make_creature(
    name="Titan Horde",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Trample. When Titan Horde enters the battlefield, create two 2/2 black Titan creature tokens.",
    setup_interceptors=_titan_horde_setup,
)


def _mindless_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['trample'])]

MINDLESS_TITAN = make_creature(
    name="Mindless Titan",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Trample.",
    setup_interceptors=_mindless_titan_setup,
)


def _crawling_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_death_trigger(obj, lambda e, s: _opponents_lose_life_events(obj, s, 2))]

CRAWLING_TITAN = make_creature(
    name="Crawling Titan",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="When Crawling Titan dies, each opponent loses 2 life.",
    setup_interceptors=_crawling_titan_setup,
)


# --- Instants ---

BETRAYAL = make_instant(
    name="Betrayal",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Destroy + life loss
)


TITANS_HUNGER = make_instant(
    name="Titan's Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    # -3/-3 + life gain
)


COORDINATE_POWER = make_instant(
    name="Coordinate Power",
    mana_cost="{B}",
    colors={Color.BLACK},
    # Pump + conditional menace
)


MEMORY_MANIPULATION = make_instant(
    name="Memory Manipulation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Discard + conditional draw
)


CRYSTALLIZATION = make_instant(
    name="Crystallization",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Hexproof/indestructible + tap
)


SACRIFICE_PLAY = make_instant(
    name="Sacrifice Play",
    mana_cost="{B}",
    colors={Color.BLACK},
    # Additional cost sacrifice + draw two
)


WARRIOR_RESOLVE = make_instant(
    name="Warrior's Resolve",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Indestructible + life loss
)


# --- Sorceries ---

TITANIZATION = make_sorcery(
    name="Titanization",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all non-Titan creatures. Create a 4/4 black Titan creature token."
)


MARLEY_INVASION = make_sorcery(
    name="Marley Invasion",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices two creatures. You create a 3/3 black Warrior creature token for each creature sacrificed this way."
)


INHERIT_POWER = make_sorcery(
    name="Inherit Power",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it was a Titan, create a token copy of it."
)


ELDIAN_PURGE = make_sorcery(
    name="Eldian Purge",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses 3 life."
)


# --- Enchantments ---

def _paths_of_titans_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event, s):
        return _draw_events(obj, 1) + _opponents_lose_life_events(obj, s, 1)
    return [_subtype_death_trigger(obj, "Titan", effect)]

PATHS_OF_TITANS = make_enchantment(
    name="Paths of Titans",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Whenever Titan dies, draw a card and each opponent loses 1 life.",
    setup_interceptors=_paths_of_titans_setup,
)


def _warrior_program_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 1, 1, ih.creatures_with_subtype(obj, "Warrior"))

WARRIOR_PROGRAM = make_enchantment(
    name="Warrior Program",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Warrior creatures you control get +1/+1.",
    setup_interceptors=_warrior_program_setup,
)


def _marleyan_dominion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Warrior-lord anthem: Warrior creatures you control get +1/+0.
    return ih.make_static_pt_boost(obj, 1, 0, ih.creatures_with_subtype(obj, "Warrior"))

MARLEYAN_DOMINION = make_enchantment(
    name="Marleyan Dominion",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Warrior creatures you control get +1/+0.",
    setup_interceptors=_marleyan_dominion_setup,
)


# =============================================================================
# RED CARDS - ATTACK TITAN, RAGE, DESTRUCTION
# =============================================================================

# --- Legendary Creatures ---

def _eren_attack_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Never stop fighting: haste + trample, attack trigger deals 2 to any creature (simplified: each opponent).
    def on_attack(event, s):
        return _damage_each_opponent(obj, s, 2)
    return [
        _self_keywords(obj, ['haste', 'trample']),
        ih.make_attack_trigger(obj, on_attack),
    ]

EREN_ATTACK_TITAN = make_creature(
    name="Eren Yeager, Attack Titan",
    power=6, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Haste, trample. Whenever Eren Yeager, Attack Titan attacks, he deals 2 damage to each opponent.",
    setup_interceptors=_eren_attack_titan_setup,
)


def _eren_founding_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    filt = ih.other_creatures_with_subtype(obj, "Titan")
    return (
        ih.make_static_pt_boost(obj, 3, 3, filt)
        + [ih.make_keyword_grant(obj, ["haste"], filt)]
    )

EREN_FOUNDING_TITAN = make_creature(
    name="Eren Yeager, Founding Titan",
    power=10, toughness=10,
    mana_cost="{5}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Other Titan creatures you control get +3/+3. Other Titan creatures you control have haste.",
    setup_interceptors=_eren_founding_titan_setup,
)


def _grisha_yeager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Rogue Titan who stole the Founding. Haste + death trigger draw (his sacrifice gives knowledge).
    return [
        _self_keywords(obj, ['haste']),
        ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 1)),
    ]

GRISHA_YEAGER = make_creature(
    name="Grisha Yeager, Rogue Titan",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Haste. When Grisha Yeager dies, draw a card.",
    setup_interceptors=_grisha_yeager_setup,
)


def _jaw_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste', 'first_strike'])]

JAW_TITAN = make_creature(
    name="Jaw Titan",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Haste, first strike.",
    setup_interceptors=_jaw_titan_setup,
)


# --- Regular Creatures ---

def _berserker_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['double_strike'])]

BERSERKER_TITAN = make_creature(
    name="Berserker Titan",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Double strike.",
    setup_interceptors=_berserker_titan_setup,
)


def _raging_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste', 'trample'])]

RAGING_TITAN = make_creature(
    name="Raging Titan",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Haste, trample.",
    setup_interceptors=_raging_titan_setup,
)


def _charging_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB: deals 1 to each opponent (it bursts through the wall).
    def etb_effect(event, s):
        return _damage_each_opponent(obj, s, 1)
    return [
        _self_keywords(obj, ['haste']),
        ih.make_etb_trigger(obj, etb_effect),
    ]

CHARGING_TITAN = make_creature(
    name="Charging Titan",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Haste. When Charging Titan enters the battlefield, it deals 1 damage to each opponent.",
    setup_interceptors=_charging_titan_setup,
)


def _wall_breaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['trample'])]

WALL_BREAKER = make_creature(
    name="Wall Breaker",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Trample.",
    setup_interceptors=_wall_breaker_setup,
)


def _eldian_rebel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Goes out in a blaze: death trigger deals 1 to each opponent.
    def on_death(event, s):
        return _damage_each_opponent(obj, s, 1)
    return [
        _self_keywords(obj, ['haste']),
        ih.make_death_trigger(obj, on_death),
    ]

ELDIAN_REBEL = make_creature(
    name="Eldian Rebel",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste. When Eldian Rebel dies, it deals 1 damage to each opponent.",
    setup_interceptors=_eldian_rebel_setup,
)


def _attack_titan_acolyte_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['first_strike'])]

ATTACK_TITAN_ACOLYTE = make_creature(
    name="Attack Titan Acolyte",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="First strike.",
    setup_interceptors=_attack_titan_acolyte_setup,
)


def _yeagerist_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste'])]

YEAGERIST_SOLDIER = make_creature(
    name="Yeagerist Soldier",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Haste.",
    setup_interceptors=_yeagerist_soldier_setup,
)


def _yeagerist_fanatic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Suicide bomber: haste + on death deal 2.
    def on_death(event, s):
        return _damage_each_opponent(obj, s, 2)
    return [
        _self_keywords(obj, ['haste']),
        ih.make_death_trigger(obj, on_death),
    ]

YEAGERIST_FANATIC = make_creature(
    name="Yeagerist Fanatic",
    power=3, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Haste. When Yeagerist Fanatic dies, it deals 2 damage to each opponent.",
    setup_interceptors=_yeagerist_fanatic_setup,
)


def _explosive_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Death-rattle: deals 2 to each opponent when it dies (explosion).
    def on_death(event, s):
        return _damage_each_opponent(obj, s, 2)
    return [ih.make_death_trigger(obj, on_death)]

EXPLOSIVE_SPECIALIST = make_creature(
    name="Explosive Specialist",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier", "Artificer"},
    text="When Explosive Specialist dies, it deals 2 damage to each opponent.",
    setup_interceptors=_explosive_specialist_setup,
)


def _thunder_spear_trooper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB: deal 3 damage to each Titan opponent controls.
    def etb_effect(event, s):
        events = []
        for t in s.objects.values():
            if t.controller == obj.controller:
                continue
            if t.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in t.characteristics.types:
                continue
            if 'Titan' not in (t.characteristics.subtypes or set()):
                continue
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': t.id, 'amount': 3, 'source': obj.id},
                source=obj.id,
            ))
        return events
    return [ih.make_etb_trigger(obj, etb_effect)]

THUNDER_SPEAR_TROOPER = make_creature(
    name="Thunder Spear Trooper",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout", "Soldier"},
    text="When Thunder Spear Trooper enters the battlefield, it deals 3 damage to each Titan an opponent controls.",
    setup_interceptors=_thunder_spear_trooper_setup,
)


def _cannon_operator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB damage 1 to each opponent (artillery).
    def etb_effect(event, s):
        return _damage_each_opponent(obj, s, 1)
    return [ih.make_etb_trigger(obj, etb_effect)]

CANNON_OPERATOR = make_creature(
    name="Cannon Operator",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="When Cannon Operator enters the battlefield, it deals 1 damage to each opponent.",
    setup_interceptors=_cannon_operator_setup,
)


def _floch_forster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 1, 0, ih.other_creatures_with_subtype(obj, "Soldier"))

FLOCH_FORSTER = make_creature(
    name="Floch Forster, Yeagerist Leader",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Other Soldier creatures you control get +1/+0.",
    setup_interceptors=_floch_forster_setup,
)


# --- Instants ---

TITANS_RAGE = make_instant(
    name="Titan's Rage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    # Pump + conditional indestructible
)


THUNDER_SPEAR_STRIKE = make_instant(
    name="Thunder Spear Strike",
    mana_cost="{2}{R}",
    colors={Color.RED},
    # Conditional damage
)


WALL_BOMBARDMENT = make_instant(
    name="Wall Bombardment",
    mana_cost="{3}{R}",
    colors={Color.RED},
    # Damage to creature and player
)


COORDINATE_ATTACK = make_instant(
    name="Coordinate Attack",
    mana_cost="{R}",
    colors={Color.RED},
    # Pump + draw
)


DESPERATE_CHARGE = make_instant(
    name="Desperate Charge",
    mana_cost="{1}{R}",
    colors={Color.RED},
    # Team pump + haste
)


BURNING_WILL = make_instant(
    name="Burning Will",
    mana_cost="{R}",
    colors={Color.RED},
    # Pump
)


CANNON_BARRAGE = make_instant(
    name="Cannon Barrage",
    mana_cost="{2}{R}",
    colors={Color.RED},
    # Divided damage
)


# --- Sorceries ---

THE_RUMBLING = make_sorcery(
    name="The Rumbling",
    mana_cost="{5}{R}{R}{R}",
    colors={Color.RED},
    text="Destroy all lands. Create ten 6/6 red Titan creature tokens with trample."
)


TITANS_FURY = make_sorcery(
    name="Titan's Fury",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Titan's Fury deals X damage to each creature and each player."
)


BREACH_THE_WALL = make_sorcery(
    name="Breach the Wall",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Destroy target artifact or land. Deal 3 damage to its controller."
)


RALLY_THE_YEAGERISTS = make_sorcery(
    name="Rally the Yeagerists",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Create three 2/1 red Human Soldier creature tokens with haste."
)


# --- Enchantments ---

def _attack_on_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    filt = ih.creatures_with_subtype(obj, "Titan")
    return (
        ih.make_static_pt_boost(obj, 2, 0, filt)
        + [ih.make_keyword_grant(obj, ["haste"], filt)]
    )

ATTACK_ON_TITAN = make_enchantment(
    name="Attack on Titan",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Titan creatures you control get +2/+0. Titan creatures you control have haste.",
    setup_interceptors=_attack_on_titan_setup,
)


def _rage_of_the_titans_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_subtype_attack_trigger(obj, "Titan", lambda e, s: [])]

RAGE_OF_THE_TITANS = make_enchantment(
    name="Rage of the Titans",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever Titan you control attacks, .",
    setup_interceptors=_rage_of_the_titans_setup,
)


def _founding_titan_power_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Titans you control get double strike (a Founding-tier anthem).
    return [ih.make_keyword_grant(obj, ["double_strike"], ih.creatures_with_subtype(obj, "Titan"))]

FOUNDING_TITAN_POWER = make_enchantment(
    name="Founding Titan's Power",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Titan creatures you control have double strike.",
    setup_interceptors=_founding_titan_power_setup,
)


# =============================================================================
# GREEN CARDS - COLOSSAL FORCES, BEAST TITAN, NATURE
# =============================================================================

# --- Legendary Creatures ---

def _beast_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Beast "throws" — on attack, 2 damage to each opponent. Reach + trample.
    def on_attack(event, s):
        return _damage_each_opponent(obj, s, 2)
    return [
        _self_keywords(obj, ['reach', 'trample']),
        ih.make_attack_trigger(obj, on_attack),
    ]

BEAST_TITAN = make_creature(
    name="Beast Titan",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Reach, trample. Whenever Beast Titan attacks, it deals 2 damage to each opponent.",
    setup_interceptors=_beast_titan_setup,
)


def _colossal_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Steam explosion ETB: deals 3 damage to each other creature; trample.
    def etb_effect(event, s):
        return _damage_all_other_creatures(obj, s, 3)
    return [
        _self_keywords(obj, ['trample']),
        ih.make_etb_trigger(obj, etb_effect),
    ]

COLOSSAL_TITAN = make_creature(
    name="Colossal Titan",
    power=10, toughness=10,
    mana_cost="{7}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Trample. When Colossal Titan enters the battlefield, it deals 3 damage to each other creature.",
    setup_interceptors=_colossal_titan_setup,
)


def _tom_ksaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['reach'])]

TOM_KSAVER = make_creature(
    name="Tom Ksaver, Beast Inheritor",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Reach.",
    setup_interceptors=_tom_ksaver_setup,
)


# --- Regular Creatures ---

def wall_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Massive wall Titan"""
    return make_wall_defense(obj, 4)

WALL_TITAN = make_creature(
    name="Wall Titan",
    power=0, toughness=12,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan", "Wall"},
    setup_interceptors=wall_titan_setup
)


def _forest_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['reach', 'trample'])]

FOREST_TITAN = make_creature(
    name="Forest Titan",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Reach, trample.",
    setup_interceptors=_forest_titan_setup,
)


def _towering_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['trample', 'reach'])]

TOWERING_TITAN = make_creature(
    name="Towering Titan",
    power=8, toughness=8,
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Trample, reach.",
    setup_interceptors=_towering_titan_setup,
)


def _ancient_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['trample']), ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 2))]

ANCIENT_TITAN = make_creature(
    name="Ancient Titan",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Trample. When Ancient Titan enters the battlefield, scry 2.",
    setup_interceptors=_ancient_titan_setup,
)


def _primordial_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['trample'])]

PRIMORDIAL_TITAN = make_creature(
    name="Primordial Titan",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Trample.",
    setup_interceptors=_primordial_titan_setup,
)


FOREST_DWELLER = make_creature(
    name="Forest Dweller",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human"},
    # Vanilla 2/3 at 2 mana — balanced.
)


def _paradis_farmer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _gain_life_events(obj, 1))]

PARADIS_FARMER = make_creature(
    name="Paradis Farmer",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Citizen"},
    text="When Paradis Farmer enters the battlefield, you gain 1 life.",
    setup_interceptors=_paradis_farmer_setup,
)


def _titan_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['reach'])]

TITAN_HUNTER = make_creature(
    name="Titan Hunter",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="Reach.",
    setup_interceptors=_titan_hunter_setup,
)


def _forest_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 1))]

FOREST_SCOUT = make_creature(
    name="Forest Scout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When Forest Scout enters the battlefield, scry 1.",
    setup_interceptors=_forest_scout_setup,
)


ELDIAN_WOODCUTTER = make_creature(
    name="Eldian Woodcutter",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Citizen"},
    # Vanilla beater; balanced at 2/2 for 2.
)


def _wild_horse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste'])]

WILD_HORSE = make_creature(
    name="Wild Horse",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    text="Haste.",
    setup_interceptors=_wild_horse_setup,
)


def _survey_corps_mount_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB: grant haste to each other Scout until end of turn.
    def etb_effect(event, s):
        scouts = ih.other_creatures_with_subtype(obj, "Scout")
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': t.id, 'keyword': 'haste', 'duration': 'end_of_turn'},
            source=obj.id,
        ) for t in s.objects.values() if scouts(t, s)]
    return [ih.make_etb_trigger(obj, etb_effect)]

SURVEY_CORPS_MOUNT = make_creature(
    name="Survey Corps Mount",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    text="When Survey Corps Mount enters the battlefield, each other Scout you control gains haste until end of turn.",
    setup_interceptors=_survey_corps_mount_setup,
)


# --- Instants ---

TITANS_GROWTH = make_instant(
    name="Titan's Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    # Pump +4/+4
)


HARDENING_ABILITY = make_instant(
    name="Hardening Ability",
    mana_cost="{G}",
    colors={Color.GREEN},
    # +0/+5 + indestructible
)


REGENERATION = make_instant(
    name="Regeneration",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    # Regenerate + conditional counters
)


FOREST_AMBUSH = make_instant(
    name="Forest Ambush",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    # Fight with pump
)


COLOSSAL_STRENGTH = make_instant(
    name="Colossal Strength",
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    # +4/+4 + trample
)


NATURAL_REGENERATION = make_instant(
    name="Natural Regeneration",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    # Put counters on all creatures
)


WILD_CHARGE = make_instant(
    name="Wild Charge",
    mana_cost="{G}",
    colors={Color.GREEN},
    # +2/+2 + trample
)


# --- Sorceries ---

SUMMON_THE_TITANS = make_sorcery(
    name="Summon the Titans",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Create two 6/6 green Titan creature tokens with trample."
)


TITAN_RAMPAGE = make_sorcery(
    name="Titan Rampage",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +X/+X until end of turn, where X is its power. It fights up to one target creature you don't control."
)


PRIMAL_GROWTH = make_sorcery(
    name="Primal Growth",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and put them onto the battlefield tapped."
)


AWAKENING_OF_THE_TITANS = make_sorcery(
    name="Awakening of the Titans",
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    text="Put all Titan creature cards from your hand and graveyard onto the battlefield."
)


# --- Enchantments ---

def _titans_dominion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    filt = ih.creatures_with_subtype(obj, "Titan")
    return (
        ih.make_static_pt_boost(obj, 2, 2, filt)
        + [ih.make_keyword_grant(obj, ["trample"], filt)]
    )

TITANS_DOMINION = make_enchantment(
    name="Titan's Dominion",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Titan creatures you control get +2/+2. Titan creatures you control have trample.",
    setup_interceptors=_titans_dominion_setup,
)


def _force_of_nature_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Green anthem: all your creatures get +1/+1.
    return ih.make_static_pt_boost(obj, 1, 1, ih.creatures_you_control(obj))

FORCE_OF_NATURE = make_enchantment(
    name="Force of Nature",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +1/+1.",
    setup_interceptors=_force_of_nature_setup,
)


def _hardened_skin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Titans you control have hexproof (hardening crystal).
    return [ih.make_keyword_grant(obj, ["hexproof"], ih.creatures_with_subtype(obj, "Titan"))]

HARDENED_SKIN = make_enchantment(
    name="Hardened Skin",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Titan creatures you control have hexproof.",
    setup_interceptors=_hardened_skin_setup,
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# Nine Titans (Legendary)

def _founding_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # The Founding Titan: indestructible, trample, hexproof (ultimate Titan).
    return [_self_keywords(obj, ['indestructible', 'trample', 'hexproof'])]

FOUNDING_TITAN = make_creature(
    name="The Founding Titan",
    power=12, toughness=12,
    mana_cost="{4}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Indestructible, trample, hexproof.",
    setup_interceptors=_founding_titan_setup,
)


def _attack_titan_card_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Haste + trample. Attack trigger pumps other Titans +1/+0 until EOT.
    def on_attack(event, s):
        filt = ih.other_creatures_with_subtype(obj, "Titan")
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': t.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id,
        ) for t in s.objects.values() if filt(t, s)]
    return [
        _self_keywords(obj, ['haste', 'trample']),
        ih.make_attack_trigger(obj, on_attack),
    ]

ATTACK_TITAN_CARD = make_creature(
    name="The Attack Titan",
    power=8, toughness=6,
    mana_cost="{3}{R}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Haste, trample. Whenever The Attack Titan attacks, other Titans you control get +1/+0 until end of turn.",
    setup_interceptors=_attack_titan_card_setup,
)


def _armored_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['indestructible', 'trample'])]

ARMORED_TITAN = make_creature(
    name="The Armored Titan",
    power=6, toughness=8,
    mana_cost="{3}{B}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Indestructible, trample.",
    setup_interceptors=_armored_titan_setup,
)


def _female_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # First strike + deathtouch = lethal in any fight.
    return [_self_keywords(obj, ['first_strike', 'deathtouch'])]

FEMALE_TITAN = make_creature(
    name="The Female Titan",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="First strike, deathtouch.",
    setup_interceptors=_female_titan_setup,
)


def _colossal_titan_legendary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # The Rumbling in card form: ETB deals 6 damage to every other creature.
    def etb_effect(event, s):
        return _damage_all_other_creatures(obj, s, 6)
    return [
        _self_keywords(obj, ['trample']),
        ih.make_etb_trigger(obj, etb_effect),
    ]

COLOSSAL_TITAN_LEGENDARY = make_creature(
    name="The Colossal Titan",
    power=15, toughness=15,
    mana_cost="{7}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Trample. When The Colossal Titan enters the battlefield, it deals 6 damage to each other creature.",
    setup_interceptors=_colossal_titan_legendary_setup,
)


def _beast_titan_legendary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 2, 2, ih.other_creatures_with_subtype(obj, "Titan"))

BEAST_TITAN_LEGENDARY = make_creature(
    name="The Beast Titan",
    power=8, toughness=8,
    mana_cost="{4}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Other Titan creatures you control get +2/+2.",
    setup_interceptors=_beast_titan_legendary_setup,
)


def _cart_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Cart: vigilance + trample (supply wagon).
    return [_self_keywords(obj, ['vigilance', 'trample'])]

CART_TITAN = make_creature(
    name="The Cart Titan",
    power=3, toughness=6,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Vigilance, trample.",
    setup_interceptors=_cart_titan_setup,
)


def _jaw_titan_legendary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste', 'first_strike'])]

JAW_TITAN_LEGENDARY = make_creature(
    name="The Jaw Titan",
    power=5, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Haste, first strike.",
    setup_interceptors=_jaw_titan_legendary_setup,
)


def _war_hammer_titan_legendary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['first_strike', 'indestructible'])]

WAR_HAMMER_TITAN_LEGENDARY = make_creature(
    name="The War Hammer Titan",
    power=6, toughness=6,
    mana_cost="{3}{B}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="First strike, indestructible.",
    setup_interceptors=_war_hammer_titan_legendary_setup,
)


# Other Multicolor

def _kenny_ackerman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['deathtouch', 'first_strike'])]

KENNY_ACKERMAN = make_creature(
    name="Kenny Ackerman, The Ripper",
    power=4, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Rogue", "Ackerman"},
    supertypes={"Legendary"},
    text="Deathtouch, first strike.",
    setup_interceptors=_kenny_ackerman_setup,
)


def _porco_galliard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste', 'first_strike'])]

PORCO_GALLIARD = make_creature(
    name="Porco Galliard, Jaw Titan",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Haste, first strike.",
    setup_interceptors=_porco_galliard_setup,
)


def _marcel_galliard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # "Fallen Warrior" — his death grants Titans indestructible (one time) — simplified: death draws.
    return [ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 1))]

MARCEL_GALLIARD = make_creature(
    name="Marcel Galliard, Fallen Warrior",
    power=2, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Marcel Galliard dies, draw a card.",
    setup_interceptors=_marcel_galliard_setup,
)


def _ymir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Original Titan: death trigger draws (her legacy endures).
    return [ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 2))]

YMIR = make_creature(
    name="Ymir, Original Titan",
    power=4, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="When Ymir, Original Titan dies, draw two cards.",
    setup_interceptors=_ymir_setup,
)


def _gabi_braun_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['first_strike', 'haste'])]

GABI_BRAUN = make_creature(
    name="Gabi Braun, Warrior Candidate",
    power=2, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Warrior", "Soldier"},
    supertypes={"Legendary"},
    text="First strike, haste.",
    setup_interceptors=_gabi_braun_setup,
)


def _falco_grice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Jaw Inheritor; Falco later flies — flying + vigilance.
    return [_self_keywords(obj, ['flying', 'vigilance'])]

FALCO_GRICE = make_creature(
    name="Falco Grice, Jaw Inheritor",
    power=3, toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Flying, vigilance.",
    setup_interceptors=_falco_grice_setup,
)


def _colt_grice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['reach']), ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 1))]

COLT_GRICE = make_creature(
    name="Colt Grice, Beast Candidate",
    power=2, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Reach. When Colt Grice enters the battlefield, scry 1.",
    setup_interceptors=_colt_grice_setup,
)


def _uri_reiss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Pacifist king — lifelink.
    return [_self_keywords(obj, ['lifelink'])]

URI_REISS = make_creature(
    name="Uri Reiss, Founding Inheritor",
    power=3, toughness=5,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble", "Titan"},
    supertypes={"Legendary"},
    text="Lifelink.",
    setup_interceptors=_uri_reiss_setup,
)


def _rod_reiss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Aberrant crawling Titan: defender (can't attack, immense body).
    return [_self_keywords(obj, ['defender'])]

ROD_REISS = make_creature(
    name="Rod Reiss, Aberrant Titan",
    power=1, toughness=15,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Defender. (A massive, shuddering Titan that cannot stand — or attack.)",
    setup_interceptors=_rod_reiss_setup,
)


# =============================================================================
# EQUIPMENT
# =============================================================================

ODM_GEAR = make_equipment(
    name="ODM Gear",
    mana_cost="{2}",
    text="Equipped creature gets +1/+0 and has flying and first strike.",
    equip_cost="{2}",
    # Equipment boost - complex effect
)


ADVANCED_ODM_GEAR = make_equipment(
    name="Advanced ODM Gear",
    mana_cost="{3}",
    text="Equipped creature gets +2/+1 and has flying, first strike, and vigilance.",
    equip_cost="{2}"
)


THUNDER_SPEAR = make_equipment(
    name="Thunder Spear",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0. Whenever equipped creature deals combat damage to a Titan, destroy that Titan.",
    equip_cost="{1}"
)


ANTI_PERSONNEL_ODM_GEAR = make_equipment(
    name="Anti-Personnel ODM Gear",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0, has flying, and has '{T}: This creature deals 2 damage to target creature.'",
    equip_cost="{2}"
)


SURVEY_CORPS_CLOAK = make_equipment(
    name="Survey Corps Cloak",
    mana_cost="{1}",
    text="Equipped creature gets +0/+1 and has hexproof as long as it's not attacking.",
    equip_cost="{1}"
)


BLADE_SET = make_equipment(
    name="Blade Set",
    mana_cost="{1}",
    text="Equipped creature gets +2/+0.",
    equip_cost="{1}"
)


GAS_CANISTER = make_equipment(
    name="Gas Canister",
    mana_cost="{1}",
    text="Equipped creature has '{T}, Sacrifice Gas Canister: This creature gains flying until end of turn. Draw a card.'",
    equip_cost="{1}"
)


GARRISON_CANNON = make_equipment(
    name="Garrison Cannon",
    mana_cost="{4}",
    text="Equipped creature has '{T}: This creature deals 4 damage to target attacking or blocking creature.'",
    equip_cost="{3}"
)


FLARE_GUN = make_equipment(
    name="Flare Gun",
    mana_cost="{1}",
    text="Equipped creature has '{T}, Sacrifice Flare Gun: Draw a card. You may reveal a Scout card from your hand. If you do, draw another card.'",
    equip_cost="{1}"
)


# =============================================================================
# ARTIFACTS
# =============================================================================

FOUNDING_TITAN_SERUM = make_artifact(
    name="Founding Titan Serum",
    mana_cost="{3}",
    text="{T}, Sacrifice Founding Titan Serum: Target creature becomes a Titan in addition to its other types and gets +4/+4 until end of turn."
)


TITAN_SERUM = make_artifact(
    name="Titan Serum",
    mana_cost="{2}",
    text="{T}, Sacrifice Titan Serum: Target creature becomes a Titan in addition to its other types and gets +2/+2 until end of turn."
)


ARMORED_TITAN_SERUM = make_artifact(
    name="Armored Titan Serum",
    mana_cost="{3}",
    text="{T}, Sacrifice Armored Titan Serum: Target creature becomes a Titan in addition to its other types and gains indestructible until end of turn."
)


SUPPLY_CACHE = make_artifact(
    name="Supply Cache",
    mana_cost="{2}",
    text="{T}, Sacrifice Supply Cache: Add {C}{C}{C}. Draw a card."
)


SIGNAL_FLARE = make_artifact(
    name="Signal Flare",
    mana_cost="{1}",
    text="{T}, Sacrifice Signal Flare: Scry 2, then draw a card."
)


WAR_HAMMER = make_artifact(
    name="War Hammer Construct",
    mana_cost="{4}",
    text="{2}, {T}: Create a 2/2 colorless Construct artifact creature token."
)


COORDINATE = make_artifact(
    name="The Coordinate",
    mana_cost="{5}",
    text="{T}: Gain control of target Titan until end of turn. Untap it. It gains haste until end of turn.",
    supertypes={"Legendary"}
)


ATTACK_TITAN_MEMORIES = make_artifact(
    name="Attack Titan's Memories",
    mana_cost="{3}",
    text="{2}, {T}: Look at the top three cards of your library. Put one into your hand and the rest on the bottom in any order.",
    supertypes={"Legendary"}
)


BASEMENT_KEY = make_artifact(
    name="Basement Key",
    mana_cost="{1}",
    text="{T}, Sacrifice Basement Key: Draw two cards. You may put a land card from your hand onto the battlefield.",
    supertypes={"Legendary"}
)


GRISHA_JOURNAL = make_artifact(
    name="Grisha's Journal",
    mana_cost="{2}",
    text="{1}, {T}: Draw a card. If you control Eren Yeager, draw two cards instead.",
    supertypes={"Legendary"}
)


# =============================================================================
# LANDS
# =============================================================================

WALL_MARIA = make_land(
    name="Wall Maria",
    text="{T}: Add {C}. {T}: Add {W}. Activate only if you control a Scout.",
    supertypes={"Legendary"}
)


WALL_ROSE = make_land(
    name="Wall Rose",
    text="{T}: Add {C}. {T}: Add {W} or {R}. Activate only if you control a Soldier.",
    supertypes={"Legendary"}
)


WALL_SHEENA = make_land(
    name="Wall Sheena",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a Noble.",
    supertypes={"Legendary"}
)


SHIGANSHINA_DISTRICT = make_land(
    name="Shiganshina District",
    text="Shiganshina District enters tapped. {T}: Add {R} or {W}."
)


TROST_DISTRICT = make_land(
    name="Trost District",
    text="Trost District enters tapped. {T}: Add {W} or {U}."
)


STOHESS_DISTRICT = make_land(
    name="Stohess District",
    text="Stohess District enters tapped. {T}: Add {W} or {B}."
)


SURVEY_CORPS_HQ = make_land(
    name="Survey Corps Headquarters",
    text="{T}: Add {C}. {2}, {T}: Scout creatures you control get +1/+0 until end of turn."
)


GARRISON_HEADQUARTERS = make_land(
    name="Garrison Headquarters",
    text="{T}: Add {C}. {2}, {T}: Create a 1/1 white Human Soldier creature token with defender."
)


MILITARY_POLICE_HQ = make_land(
    name="Military Police Headquarters",
    text="{T}: Add {C}. {3}, {T}: Tap target creature."
)


PARADIS_ISLAND = make_land(
    name="Paradis Island",
    text="Paradis Island enters tapped. When it enters, you gain 1 life. {T}: Add {G} or {W}."
)


MARLEY = make_land(
    name="Marley",
    text="Marley enters tapped. {T}: Add {B} or {R}."
)


LIBERIO_INTERNMENT_ZONE = make_land(
    name="Liberio Internment Zone",
    text="{T}: Add {C}. {T}: Add {B}. Activate only if you control a Warrior."
)


FOREST_OF_GIANT_TREES = make_land(
    name="Forest of Giant Trees",
    text="{T}: Add {G}. Creatures with flying you control get +0/+1."
)


UTGARD_CASTLE = make_land(
    name="Utgard Castle",
    text="Utgard Castle enters tapped. {T}: Add {W} or {B}. {3}, {T}: Create a 0/4 white Wall creature token with defender."
)


REISS_CHAPEL = make_land(
    name="Reiss Chapel",
    text="{T}: Add {C}. {4}, {T}, Sacrifice Reiss Chapel: Search your library for a Titan card, reveal it, and put it into your hand.",
    supertypes={"Legendary"}
)


PATHS = make_land(
    name="The Paths",
    text="{T}: Add one mana of any color. Spend this mana only to cast Titan spells.",
    supertypes={"Legendary"}
)


OCEAN = make_land(
    name="The Ocean",
    text="The Ocean enters tapped. When it enters, scry 1. {T}: Add {U} or {G}.",
    supertypes={"Legendary"}
)


# Additional Locations
ORVUD_DISTRICT = make_land(
    name="Orvud District",
    text="Orvud District enters tapped. {T}: Add {W} or {R}. When Orvud District enters, you may tap target creature."
)


KARANES_DISTRICT = make_land(
    name="Karanes District",
    text="Karanes District enters tapped. {T}: Add {U} or {W}."
)


RAGAKO_VILLAGE = make_land(
    name="Ragako Village",
    text="{T}: Add {C}. {2}, {T}: Create a 2/2 black Titan creature token that attacks each combat if able."
)


UNDERGROUND_CITY = make_land(
    name="Underground City",
    text="{T}: Add {B}. {3}{B}, {T}: Return target creature card with mana value 2 or less from your graveyard to the battlefield."
)


# Additional White Cards
def _nile_dok_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 0, 1, ih.other_creatures_with_subtype(obj, "Soldier"))

NILE_DOK = make_creature(
    name="Nile Dok, Military Police Commander",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    text="Other Soldier creatures you control get +0/+1.",
    setup_interceptors=_nile_dok_setup,
)


def _darius_zackly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['vigilance'])]

DARIUS_ZACKLY = make_creature(
    name="Darius Zackly, Premier",
    power=1, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance.",
    setup_interceptors=_darius_zackly_setup,
)


def _dot_pixis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 1, 0, ih.creatures_with_subtype(obj, "Soldier"))

DOT_PIXIS = make_creature(
    name="Dot Pixis, Garrison Commander",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    text="Soldier creatures you control get +1/+0.",
    setup_interceptors=_dot_pixis_setup,
)


def _hannes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Garrison Captain: vigilance + block trigger gain 2 life.
    return [
        _self_keywords(obj, ['vigilance']),
        ih.make_block_trigger(obj, lambda e, s: _gain_life_events(obj, 2)),
    ]

HANNES = make_creature(
    name="Hannes, Garrison Captain",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance. Whenever Hannes blocks, you gain 2 life.",
    setup_interceptors=_hannes_setup,
)


def _carla_yeager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Eren's mother: her death makes others stronger. Other Humans get +1/+0 EOT on death.
    def on_death(event, s):
        humans = ih.other_creatures_with_subtype(obj, "Human")
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': t.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id,
        ) for t in s.objects.values() if humans(t, s)]
    return [ih.make_death_trigger(obj, on_death)]

CARLA_YEAGER = make_creature(
    name="Carla Yeager, Eren's Mother",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    supertypes={"Legendary"},
    text="When Carla Yeager dies, other Humans you control get +1/+1 until end of turn.",
    setup_interceptors=_carla_yeager_setup,
)


def _wall_rose_garrison_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_block_trigger(obj, lambda e, s: _gain_life_events(obj, 3))]

WALL_ROSE_GARRISON = make_creature(
    name="Wall Rose Garrison",
    power=1, toughness=5,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wall"},
    text="Whenever Wall Rose Garrison blocks, you gain 3 life.",
    setup_interceptors=_wall_rose_garrison_setup,
)


MILITARY_TRIBUNAL = make_sorcery(
    name="Military Tribunal",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Exile target creature. Its controller creates a 1/1 white Human Soldier creature token."
)


# Additional Blue Cards
def _moblit_berner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 2))]

MOBLIT_BERNER = make_creature(
    name="Moblit Berner, Hange's Assistant",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="When Moblit Berner, Hange's Assistant enters the battlefield, scry 2.",
    setup_interceptors=_moblit_berner_setup,
)


def _onyankopon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['flying'])]

ONYANKOPON = make_creature(
    name="Onyankopon, Anti-Marleyan",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    text="Flying.",
    setup_interceptors=_onyankopon_setup,
)


def _yelena_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Zealot: menace + ETB scry 2.
    return [
        _self_keywords(obj, ['menace']),
        ih.make_etb_trigger(obj, lambda e, s: _scry_events(obj, 2)),
    ]

YELENA = make_creature(
    name="Yelena, True Believer",
    power=2, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Menace. When Yelena enters the battlefield, scry 2.",
    setup_interceptors=_yelena_setup,
)


def _ilse_langnar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Titan Chronicler: death trigger draw (her final diary entry).
    return [ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 1))]

ILSE_LANGNAR = make_creature(
    name="Ilse Langnar, Titan Chronicler",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="When Ilse Langnar dies, draw a card.",
    setup_interceptors=_ilse_langnar_setup,
)


INFORMATION_GATHERING = make_sorcery(
    name="Information Gathering",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at target opponent's hand. Draw a card."
)


def _titan_biology_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event, s):
        return _scry_events(obj, 1) + _draw_events(obj, 1)
    return [
        _subtype_etb_trigger(obj, "Titan", effect),
        _subtype_death_trigger(obj, "Titan", effect),
    ]

TITAN_BIOLOGY = make_enchantment(
    name="Titan Biology",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever Titan enters the battlefield, scry 1 and draw a card. Whenever Titan dies, scry 1 and draw a card.",
    setup_interceptors=_titan_biology_setup,
)


# Additional Black Cards
def _dina_fritz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Smiling Titan: ETB deals 2 to each opponent (she ate Carla).
    def etb_effect(event, s):
        return _damage_each_opponent(obj, s, 2)
    return [ih.make_etb_trigger(obj, etb_effect)]

DINA_FRITZ = make_creature(
    name="Dina Fritz, Smiling Titan",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="When Dina Fritz enters the battlefield, it deals 2 damage to each opponent.",
    setup_interceptors=_dina_fritz_setup,
)


def _kruger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['haste']), ih.make_death_trigger(obj, lambda e, s: _draw_events(obj, 1))]

KRUGER = make_creature(
    name="Eren Kruger, The Owl",
    power=4, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Haste. When Eren Kruger dies, draw a card.",
    setup_interceptors=_kruger_setup,
)


def _gross_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_another_creature_death_trigger(obj, lambda e, s: _opponents_lose_life_events(obj, s, 1))]

GROSS = make_creature(
    name="Sergeant Major Gross",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever another creature dies, each opponent loses 1 life.",
    setup_interceptors=_gross_setup,
)


def _magath_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 1, 1, ih.other_creatures_with_subtype(obj, "Warrior"))

MAGATH = make_creature(
    name="Theo Magath, Marleyan General",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    text="Other Warrior creatures you control get +1/+1.",
    setup_interceptors=_magath_setup,
)


def _willy_tybur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Declaration of War: his death creates a 6/6 War Hammer Titan token (the turning point).
    def on_death(event, s):
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'War Hammer Titan',
                    'power': 6, 'toughness': 6,
                    'colors': {Color.BLACK, Color.WHITE},
                    'subtypes': {'Titan'},
                    'keywords': ['first_strike'],
                },
            },
            source=obj.id,
        )]
    return [ih.make_death_trigger(obj, on_death)]

WILLY_TYBUR = make_creature(
    name="Willy Tybur, Declaration of War",
    power=2, toughness=2,
    mana_cost="{2}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="When Willy Tybur dies, create a 6/6 black and white Titan creature token with first strike.",
    setup_interceptors=_willy_tybur_setup,
)


ELDIAN_ARMBAND = make_artifact(
    name="Eldian Armband",
    mana_cost="{1}",
    text="Equipped creature gets +0/+1 and is an Eldian in addition to its other types. Equip {1}"
)


# Additional Red Cards
def _kaya_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_etb_trigger(obj, lambda e, s: _gain_life_events(obj, 2))]

KAYA = make_creature(
    name="Kaya, Sasha's Friend",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Citizen"},
    supertypes={"Legendary"},
    text="When Kaya enters the battlefield, you gain 2 life.",
    setup_interceptors=_kaya_setup,
)


def _keith_shadis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Instructor: lord for Soldiers (trained them all).
    return ih.make_static_pt_boost(obj, 1, 0, ih.other_creatures_with_subtype(obj, "Soldier"))

KEITH_SHADIS = make_creature(
    name="Keith Shadis, Instructor",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Other Soldier creatures you control get +1/+0.",
    setup_interceptors=_keith_shadis_setup,
)


def _louise_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_self_keywords(obj, ['first_strike', 'haste'])]

LOUISE = make_creature(
    name="Louise, Yeagerist Devotee",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="First strike, haste.",
    setup_interceptors=_louise_setup,
)


TITAN_TRANSFORMATION = make_instant(
    name="Titan Transformation",
    mana_cost="{2}{R}",
    colors={Color.RED},
    # Grant Titan type + pump + trample
)


DECLARATION_OF_WAR = make_sorcery(
    name="Declaration of War",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Gain control of all Titans until end of turn. Untap them. They gain haste until end of turn."
)


# Additional Green Cards
def _ymir_fritz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [ih.make_keyword_grant(obj, ["hexproof"], ih.creatures_with_subtype(obj, "Titan"))]

YMIR_FRITZ = make_creature(
    name="Ymir Fritz, Source of All Titans",
    power=8, toughness=8,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Titan creatures you control have hexproof.",
    setup_interceptors=_ymir_fritz_setup,
)


def _king_fritz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return ih.make_static_pt_boost(obj, 1, 1, ih.creatures_with_subtype(obj, "Titan"))

KING_FRITZ = make_creature(
    name="King Fritz, First Eldian King",
    power=3, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Titan creatures you control get +1/+1.",
    setup_interceptors=_king_fritz_setup,
)


TITANS_BLESSING = make_instant(
    name="Titan's Blessing",
    mana_cost="{G}",
    colors={Color.GREEN},
    # Pump + conditional trample/hexproof
)


WALL_TITAN_ARMY = make_sorcery(
    name="Wall Titan Army",
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    text="Create four 6/6 green Titan creature tokens with trample."
)


# Basic lands
PLAINS_AOT = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"}
)


ISLAND_AOT = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"}
)


SWAMP_AOT = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"}
)


MOUNTAIN_AOT = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"}
)


FOREST_AOT = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"}
)


# =============================================================================
# CARD DICTIONARY
# =============================================================================

ATTACK_ON_TITAN_CARDS = {
    # WHITE - SURVEY CORPS, HUMANITY'S HOPE
    "Eren Yeager, Survey Corps": EREN_YEAGER_SCOUT,
    "Mikasa Ackerman, Humanity's Strongest": MIKASA_ACKERMAN,
    "Armin Arlert, Tactician": ARMIN_ARLERT,
    "Levi Ackerman, Captain": LEVI_ACKERMAN,
    "Erwin Smith, Commander": ERWIN_SMITH,
    "Hange Zoe, Researcher": HANGE_ZOE,
    "Historia Reiss, True Queen": HISTORIA_REISS,
    "Sasha Blouse, Hunter": SASHA_BLOUSE,
    "Connie Springer, Loyal Friend": CONNIE_SPRINGER,
    "Jean Kirstein, Natural Leader": JEAN_KIRSTEIN,
    "Miche Zacharias, Squad Leader": MICHE_ZACHARIAS,
    "Petra Ral, Levi Squad": PETRA_RAL,
    "Oluo Bozado, Levi Squad": OLUO_BOZADO,
    "Survey Corps Recruit": SURVEY_CORPS_RECRUIT,
    "Survey Corps Veteran": SURVEY_CORPS_VETERAN,
    "Garrison Soldier": GARRISON_SOLDIER,
    "Military Police Officer": MILITARY_POLICE_OFFICER,
    "Wall Defender": WALL_DEFENDER,
    "Training Corps Cadet": TRAINING_CORPS_CADET,
    "Squad Captain": SQUAD_CAPTAIN,
    "Wall Garrison Elite": WALL_GARRISON_ELITE,
    "Interior Police": INTERIOR_POLICE,
    "Shiganshina Citizen": SHIGANSHINA_CITIZEN,
    "Eldian Refugee": ELDIAN_REFUGEE,
    "Wall Cultist": WALL_CULTIST,
    "Horse Mounted Scout": HORSE_MOUNTED_SCOUT,
    "Devoted Heart": DEVOTED_HEART,
    "Survey Corps Charge": SURVEY_CORPS_CHARGE,
    "Wall Defense": WALL_DEFENSE,
    "Humanity's Hope": HUMANITYS_HOPE,
    "Salute of Hearts": SALUTE_OF_HEARTS,
    "Strategic Retreat": STRATEGIC_RETREAT,
    "Formation Break": FORMATION_BREAK,
    "Garrison Reinforcements": GARRISON_REINFORCEMENTS,
    "Survey Mission": SURVEY_MISSION,
    "Evacuation Order": EVACUATION_ORDER,
    "Wall Reconstruction": WALL_RECONSTRUCTION,
    "Training Exercise": TRAINING_EXERCISE,
    "Survey Corps Banner": SURVEY_CORPS_BANNER,
    "Wings of Freedom": WINGS_OF_FREEDOM,
    "Wall Faith": WALL_FAITH,

    # BLUE - STRATEGY, PLANNING
    "Armin, Colossal Titan": ARMIN_COLOSSAL_TITAN,
    "Erwin Smith, The Gambit": ERWIN_GAMBIT,
    "Pieck Finger, Cart Titan": PIECK_FINGER,
    "Intelligence Officer": INTELLIGENCE_OFFICER,
    "Marleyan Spy": MARLEYAN_SPY,
    "Survey Cartographer": SURVEY_CARTOGRAPHER,
    "Titan Researcher": TITAN_RESEARCHER,
    "Strategic Advisor": STRATEGIC_ADVISOR,
    "Wall Architect": WALL_ARCHITECT,
    "Military Tactician": MILITARY_TACTICIAN,
    "Signal Corps Operator": SIGNAL_CORPS_OPERATOR,
    "Supply Corps Quartermaster": SUPPLY_CORPS_QUARTERMASTER,
    "Coastal Scout": COASTAL_SCOUT,
    "Formation Analyst": FORMATION_ANALYST,
    "Strategic Analysis": STRATEGIC_ANALYSIS,
    "Tactical Retreat": TACTICAL_RETREAT,
    "Formation Shift": FORMATION_SHIFT,
    "Counter Strategy": COUNTER_STRATEGY,
    "Flare Signal": FLARE_SIGNAL,
    "Intelligence Report": INTELLIGENCE_REPORT,
    "Reconnaissance": RECONNAISSANCE,
    "Escape Route": ESCAPE_ROUTE,
    "Survey the Land": SURVEY_THE_LAND,
    "Mapping Expedition": MAPPING_EXPEDITION,
    "Memory Wipe": MEMORY_WIPE,
    "Strategic Planning": STRATEGIC_PLANNING,
    "Information Network": INFORMATION_NETWORK,

    # BLACK - MARLEY, WARRIORS, BETRAYAL
    "Reiner Braun, Armored Titan": REINER_BRAUN,
    "Bertholdt Hoover, Colossal Titan": BERTHOLDT_HOOVER,
    "Annie Leonhart, Female Titan": ANNIE_LEONHART,
    "Zeke Yeager, Beast Titan": ZEKE_YEAGER,
    "War Hammer Titan": WAR_HAMMER_TITAN,
    "Marleyan Warrior": MARLEYAN_WARRIOR,
    "Warrior Candidate": WARRIOR_CANDIDATE,
    "Marleyan Officer": MARLEYAN_OFFICER,
    "Infiltrator": INFILTRATOR,
    "Eldian Internment Guard": ELDIAN_INTERNMENT_GUARD,
    "Titan Inheritor": TITAN_INHERITOR,
    "Military Executioner": MILITARY_EXECUTIONER,
    "Restorationist": RESTORATIONIST,
    "Pure Titan": PURE_TITAN,
    "Abnormal Titan": ABNORMAL_TITAN,
    "Small Titan": SMALL_TITAN,
    "Titan Horde": TITAN_HORDE,
    "Mindless Titan": MINDLESS_TITAN,
    "Crawling Titan": CRAWLING_TITAN,
    "Betrayal": BETRAYAL,
    "Titan's Hunger": TITANS_HUNGER,
    "Coordinate Power": COORDINATE_POWER,
    "Memory Manipulation": MEMORY_MANIPULATION,
    "Crystallization": CRYSTALLIZATION,
    "Sacrifice Play": SACRIFICE_PLAY,
    "Warrior's Resolve": WARRIOR_RESOLVE,
    "Titanization": TITANIZATION,
    "Marley Invasion": MARLEY_INVASION,
    "Inherit Power": INHERIT_POWER,
    "Eldian Purge": ELDIAN_PURGE,
    "Paths of Titans": PATHS_OF_TITANS,
    "Warrior Program": WARRIOR_PROGRAM,
    "Marleyan Dominion": MARLEYAN_DOMINION,

    # RED - ATTACK TITAN, RAGE
    "Eren Yeager, Attack Titan": EREN_ATTACK_TITAN,
    "Eren Yeager, Founding Titan": EREN_FOUNDING_TITAN,
    "Grisha Yeager, Rogue Titan": GRISHA_YEAGER,
    "Jaw Titan": JAW_TITAN,
    "Floch Forster, Yeagerist Leader": FLOCH_FORSTER,
    "Berserker Titan": BERSERKER_TITAN,
    "Raging Titan": RAGING_TITAN,
    "Charging Titan": CHARGING_TITAN,
    "Wall Breaker": WALL_BREAKER,
    "Eldian Rebel": ELDIAN_REBEL,
    "Attack Titan Acolyte": ATTACK_TITAN_ACOLYTE,
    "Yeagerist Soldier": YEAGERIST_SOLDIER,
    "Yeagerist Fanatic": YEAGERIST_FANATIC,
    "Explosive Specialist": EXPLOSIVE_SPECIALIST,
    "Thunder Spear Trooper": THUNDER_SPEAR_TROOPER,
    "Cannon Operator": CANNON_OPERATOR,
    "Titan's Rage": TITANS_RAGE,
    "Thunder Spear Strike": THUNDER_SPEAR_STRIKE,
    "Wall Bombardment": WALL_BOMBARDMENT,
    "Coordinate Attack": COORDINATE_ATTACK,
    "Desperate Charge": DESPERATE_CHARGE,
    "Burning Will": BURNING_WILL,
    "Cannon Barrage": CANNON_BARRAGE,
    "The Rumbling": THE_RUMBLING,
    "Titan's Fury": TITANS_FURY,
    "Breach the Wall": BREACH_THE_WALL,
    "Rally the Yeagerists": RALLY_THE_YEAGERISTS,
    "Attack on Titan": ATTACK_ON_TITAN,
    "Rage of the Titans": RAGE_OF_THE_TITANS,
    "Founding Titan's Power": FOUNDING_TITAN_POWER,

    # GREEN - COLOSSAL FORCES, NATURE
    "Beast Titan": BEAST_TITAN,
    "Colossal Titan": COLOSSAL_TITAN,
    "Tom Ksaver, Beast Inheritor": TOM_KSAVER,
    "Wall Titan": WALL_TITAN,
    "Forest Titan": FOREST_TITAN,
    "Towering Titan": TOWERING_TITAN,
    "Ancient Titan": ANCIENT_TITAN,
    "Primordial Titan": PRIMORDIAL_TITAN,
    "Forest Dweller": FOREST_DWELLER,
    "Paradis Farmer": PARADIS_FARMER,
    "Titan Hunter": TITAN_HUNTER,
    "Forest Scout": FOREST_SCOUT,
    "Eldian Woodcutter": ELDIAN_WOODCUTTER,
    "Wild Horse": WILD_HORSE,
    "Survey Corps Mount": SURVEY_CORPS_MOUNT,
    "Titan's Growth": TITANS_GROWTH,
    "Hardening Ability": HARDENING_ABILITY,
    "Regeneration": REGENERATION,
    "Forest Ambush": FOREST_AMBUSH,
    "Colossal Strength": COLOSSAL_STRENGTH,
    "Natural Regeneration": NATURAL_REGENERATION,
    "Wild Charge": WILD_CHARGE,
    "Summon the Titans": SUMMON_THE_TITANS,
    "Titan Rampage": TITAN_RAMPAGE,
    "Primal Growth": PRIMAL_GROWTH,
    "Awakening of the Titans": AWAKENING_OF_THE_TITANS,
    "Titan's Dominion": TITANS_DOMINION,
    "Force of Nature": FORCE_OF_NATURE,
    "Hardened Skin": HARDENED_SKIN,

    # MULTICOLOR - NINE TITANS & OTHERS
    "The Founding Titan": FOUNDING_TITAN,
    "The Attack Titan": ATTACK_TITAN_CARD,
    "The Armored Titan": ARMORED_TITAN,
    "The Female Titan": FEMALE_TITAN,
    "The Colossal Titan": COLOSSAL_TITAN_LEGENDARY,
    "The Beast Titan": BEAST_TITAN_LEGENDARY,
    "The Cart Titan": CART_TITAN,
    "The Jaw Titan": JAW_TITAN_LEGENDARY,
    "The War Hammer Titan": WAR_HAMMER_TITAN_LEGENDARY,
    "Kenny Ackerman, The Ripper": KENNY_ACKERMAN,
    "Porco Galliard, Jaw Titan": PORCO_GALLIARD,
    "Marcel Galliard, Fallen Warrior": MARCEL_GALLIARD,
    "Ymir, Original Titan": YMIR,
    "Gabi Braun, Warrior Candidate": GABI_BRAUN,
    "Falco Grice, Jaw Inheritor": FALCO_GRICE,
    "Colt Grice, Beast Candidate": COLT_GRICE,
    "Uri Reiss, Founding Inheritor": URI_REISS,
    "Rod Reiss, Aberrant Titan": ROD_REISS,

    # EQUIPMENT
    "ODM Gear": ODM_GEAR,
    "Advanced ODM Gear": ADVANCED_ODM_GEAR,
    "Thunder Spear": THUNDER_SPEAR,
    "Anti-Personnel ODM Gear": ANTI_PERSONNEL_ODM_GEAR,
    "Survey Corps Cloak": SURVEY_CORPS_CLOAK,
    "Blade Set": BLADE_SET,
    "Gas Canister": GAS_CANISTER,
    "Garrison Cannon": GARRISON_CANNON,
    "Flare Gun": FLARE_GUN,

    # ARTIFACTS
    "Founding Titan Serum": FOUNDING_TITAN_SERUM,
    "Titan Serum": TITAN_SERUM,
    "Armored Titan Serum": ARMORED_TITAN_SERUM,
    "Supply Cache": SUPPLY_CACHE,
    "Signal Flare": SIGNAL_FLARE,
    "War Hammer Construct": WAR_HAMMER,
    "The Coordinate": COORDINATE,
    "Attack Titan's Memories": ATTACK_TITAN_MEMORIES,
    "Basement Key": BASEMENT_KEY,
    "Grisha's Journal": GRISHA_JOURNAL,

    # LANDS
    "Wall Maria": WALL_MARIA,
    "Wall Rose": WALL_ROSE,
    "Wall Sheena": WALL_SHEENA,
    "Shiganshina District": SHIGANSHINA_DISTRICT,
    "Trost District": TROST_DISTRICT,
    "Stohess District": STOHESS_DISTRICT,
    "Survey Corps Headquarters": SURVEY_CORPS_HQ,
    "Garrison Headquarters": GARRISON_HEADQUARTERS,
    "Military Police Headquarters": MILITARY_POLICE_HQ,
    "Paradis Island": PARADIS_ISLAND,
    "Marley": MARLEY,
    "Liberio Internment Zone": LIBERIO_INTERNMENT_ZONE,
    "Forest of Giant Trees": FOREST_OF_GIANT_TREES,
    "Utgard Castle": UTGARD_CASTLE,
    "Reiss Chapel": REISS_CHAPEL,
    "The Paths": PATHS,
    "The Ocean": OCEAN,

    # ADDITIONAL LANDS
    "Orvud District": ORVUD_DISTRICT,
    "Karanes District": KARANES_DISTRICT,
    "Ragako Village": RAGAKO_VILLAGE,
    "Underground City": UNDERGROUND_CITY,

    # ADDITIONAL WHITE
    "Nile Dok, Military Police Commander": NILE_DOK,
    "Darius Zackly, Premier": DARIUS_ZACKLY,
    "Dot Pixis, Garrison Commander": DOT_PIXIS,
    "Hannes, Garrison Captain": HANNES,
    "Carla Yeager, Eren's Mother": CARLA_YEAGER,
    "Wall Rose Garrison": WALL_ROSE_GARRISON,
    "Military Tribunal": MILITARY_TRIBUNAL,

    # ADDITIONAL BLUE
    "Moblit Berner, Hange's Assistant": MOBLIT_BERNER,
    "Onyankopon, Anti-Marleyan": ONYANKOPON,
    "Yelena, True Believer": YELENA,
    "Ilse Langnar, Titan Chronicler": ILSE_LANGNAR,
    "Information Gathering": INFORMATION_GATHERING,
    "Titan Biology": TITAN_BIOLOGY,

    # ADDITIONAL BLACK
    "Dina Fritz, Smiling Titan": DINA_FRITZ,
    "Eren Kruger, The Owl": KRUGER,
    "Sergeant Major Gross": GROSS,
    "Theo Magath, Marleyan General": MAGATH,
    "Willy Tybur, Declaration of War": WILLY_TYBUR,
    "Eldian Armband": ELDIAN_ARMBAND,

    # ADDITIONAL RED
    "Kaya, Sasha's Friend": KAYA,
    "Keith Shadis, Instructor": KEITH_SHADIS,
    "Louise, Yeagerist Devotee": LOUISE,
    "Titan Transformation": TITAN_TRANSFORMATION,
    "Declaration of War": DECLARATION_OF_WAR,

    # ADDITIONAL GREEN
    "Ymir Fritz, Source of All Titans": YMIR_FRITZ,
    "King Fritz, First Eldian King": KING_FRITZ,
    "Titan's Blessing": TITANS_BLESSING,
    "Wall Titan Army": WALL_TITAN_ARMY,

    # BASIC LANDS
    "Plains": PLAINS_AOT,
    "Island": ISLAND_AOT,
    "Swamp": SWAMP_AOT,
    "Mountain": MOUNTAIN_AOT,
    "Forest": FOREST_AOT,
}

print(f"Loaded {len(ATTACK_ON_TITAN_CARDS)} Attack on Titan cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    EREN_YEAGER_SCOUT,
    MIKASA_ACKERMAN,
    ARMIN_ARLERT,
    LEVI_ACKERMAN,
    ERWIN_SMITH,
    HANGE_ZOE,
    SURVEY_CORPS_RECRUIT,
    SURVEY_CORPS_VETERAN,
    GARRISON_SOLDIER,
    MILITARY_POLICE_OFFICER,
    WALL_DEFENDER,
    TRAINING_CORPS_CADET,
    HISTORIA_REISS,
    SASHA_BLOUSE,
    CONNIE_SPRINGER,
    JEAN_KIRSTEIN,
    MICHE_ZACHARIAS,
    PETRA_RAL,
    OLUO_BOZADO,
    SQUAD_CAPTAIN,
    WALL_GARRISON_ELITE,
    INTERIOR_POLICE,
    SHIGANSHINA_CITIZEN,
    ELDIAN_REFUGEE,
    WALL_CULTIST,
    HORSE_MOUNTED_SCOUT,
    DEVOTED_HEART,
    SURVEY_CORPS_CHARGE,
    WALL_DEFENSE,
    HUMANITYS_HOPE,
    SALUTE_OF_HEARTS,
    STRATEGIC_RETREAT,
    FORMATION_BREAK,
    GARRISON_REINFORCEMENTS,
    SURVEY_MISSION,
    EVACUATION_ORDER,
    WALL_RECONSTRUCTION,
    TRAINING_EXERCISE,
    SURVEY_CORPS_BANNER,
    WINGS_OF_FREEDOM,
    WALL_FAITH,
    ARMIN_COLOSSAL_TITAN,
    ERWIN_GAMBIT,
    PIECK_FINGER,
    INTELLIGENCE_OFFICER,
    MARLEYAN_SPY,
    SURVEY_CARTOGRAPHER,
    TITAN_RESEARCHER,
    STRATEGIC_ADVISOR,
    WALL_ARCHITECT,
    MILITARY_TACTICIAN,
    SIGNAL_CORPS_OPERATOR,
    SUPPLY_CORPS_QUARTERMASTER,
    COASTAL_SCOUT,
    FORMATION_ANALYST,
    STRATEGIC_ANALYSIS,
    TACTICAL_RETREAT,
    FORMATION_SHIFT,
    COUNTER_STRATEGY,
    FLARE_SIGNAL,
    INTELLIGENCE_REPORT,
    RECONNAISSANCE,
    ESCAPE_ROUTE,
    SURVEY_THE_LAND,
    MAPPING_EXPEDITION,
    MEMORY_WIPE,
    STRATEGIC_PLANNING,
    INFORMATION_NETWORK,
    REINER_BRAUN,
    BERTHOLDT_HOOVER,
    ANNIE_LEONHART,
    ZEKE_YEAGER,
    WAR_HAMMER_TITAN,
    MARLEYAN_WARRIOR,
    WARRIOR_CANDIDATE,
    MARLEYAN_OFFICER,
    INFILTRATOR,
    ELDIAN_INTERNMENT_GUARD,
    TITAN_INHERITOR,
    MILITARY_EXECUTIONER,
    RESTORATIONIST,
    PURE_TITAN,
    ABNORMAL_TITAN,
    SMALL_TITAN,
    TITAN_HORDE,
    MINDLESS_TITAN,
    CRAWLING_TITAN,
    BETRAYAL,
    TITANS_HUNGER,
    COORDINATE_POWER,
    MEMORY_MANIPULATION,
    CRYSTALLIZATION,
    SACRIFICE_PLAY,
    WARRIOR_RESOLVE,
    TITANIZATION,
    MARLEY_INVASION,
    INHERIT_POWER,
    ELDIAN_PURGE,
    PATHS_OF_TITANS,
    WARRIOR_PROGRAM,
    MARLEYAN_DOMINION,
    EREN_ATTACK_TITAN,
    EREN_FOUNDING_TITAN,
    GRISHA_YEAGER,
    JAW_TITAN,
    BERSERKER_TITAN,
    RAGING_TITAN,
    CHARGING_TITAN,
    WALL_BREAKER,
    ELDIAN_REBEL,
    ATTACK_TITAN_ACOLYTE,
    YEAGERIST_SOLDIER,
    YEAGERIST_FANATIC,
    EXPLOSIVE_SPECIALIST,
    THUNDER_SPEAR_TROOPER,
    CANNON_OPERATOR,
    FLOCH_FORSTER,
    TITANS_RAGE,
    THUNDER_SPEAR_STRIKE,
    WALL_BOMBARDMENT,
    COORDINATE_ATTACK,
    DESPERATE_CHARGE,
    BURNING_WILL,
    CANNON_BARRAGE,
    THE_RUMBLING,
    TITANS_FURY,
    BREACH_THE_WALL,
    RALLY_THE_YEAGERISTS,
    ATTACK_ON_TITAN,
    RAGE_OF_THE_TITANS,
    FOUNDING_TITAN_POWER,
    BEAST_TITAN,
    COLOSSAL_TITAN,
    TOM_KSAVER,
    WALL_TITAN,
    FOREST_TITAN,
    TOWERING_TITAN,
    ANCIENT_TITAN,
    PRIMORDIAL_TITAN,
    FOREST_DWELLER,
    PARADIS_FARMER,
    TITAN_HUNTER,
    FOREST_SCOUT,
    ELDIAN_WOODCUTTER,
    WILD_HORSE,
    SURVEY_CORPS_MOUNT,
    TITANS_GROWTH,
    HARDENING_ABILITY,
    REGENERATION,
    FOREST_AMBUSH,
    COLOSSAL_STRENGTH,
    NATURAL_REGENERATION,
    WILD_CHARGE,
    SUMMON_THE_TITANS,
    TITAN_RAMPAGE,
    PRIMAL_GROWTH,
    AWAKENING_OF_THE_TITANS,
    TITANS_DOMINION,
    FORCE_OF_NATURE,
    HARDENED_SKIN,
    FOUNDING_TITAN,
    ATTACK_TITAN_CARD,
    ARMORED_TITAN,
    FEMALE_TITAN,
    COLOSSAL_TITAN_LEGENDARY,
    BEAST_TITAN_LEGENDARY,
    CART_TITAN,
    JAW_TITAN_LEGENDARY,
    WAR_HAMMER_TITAN_LEGENDARY,
    KENNY_ACKERMAN,
    PORCO_GALLIARD,
    MARCEL_GALLIARD,
    YMIR,
    GABI_BRAUN,
    FALCO_GRICE,
    COLT_GRICE,
    URI_REISS,
    ROD_REISS,
    ODM_GEAR,
    ADVANCED_ODM_GEAR,
    THUNDER_SPEAR,
    ANTI_PERSONNEL_ODM_GEAR,
    SURVEY_CORPS_CLOAK,
    BLADE_SET,
    GAS_CANISTER,
    GARRISON_CANNON,
    FLARE_GUN,
    FOUNDING_TITAN_SERUM,
    TITAN_SERUM,
    ARMORED_TITAN_SERUM,
    SUPPLY_CACHE,
    SIGNAL_FLARE,
    WAR_HAMMER,
    COORDINATE,
    ATTACK_TITAN_MEMORIES,
    BASEMENT_KEY,
    GRISHA_JOURNAL,
    WALL_MARIA,
    WALL_ROSE,
    WALL_SHEENA,
    SHIGANSHINA_DISTRICT,
    TROST_DISTRICT,
    STOHESS_DISTRICT,
    SURVEY_CORPS_HQ,
    GARRISON_HEADQUARTERS,
    MILITARY_POLICE_HQ,
    PARADIS_ISLAND,
    MARLEY,
    LIBERIO_INTERNMENT_ZONE,
    FOREST_OF_GIANT_TREES,
    UTGARD_CASTLE,
    REISS_CHAPEL,
    PATHS,
    OCEAN,
    ORVUD_DISTRICT,
    KARANES_DISTRICT,
    RAGAKO_VILLAGE,
    UNDERGROUND_CITY,
    NILE_DOK,
    DARIUS_ZACKLY,
    DOT_PIXIS,
    HANNES,
    CARLA_YEAGER,
    WALL_ROSE_GARRISON,
    MILITARY_TRIBUNAL,
    MOBLIT_BERNER,
    ONYANKOPON,
    YELENA,
    ILSE_LANGNAR,
    INFORMATION_GATHERING,
    TITAN_BIOLOGY,
    DINA_FRITZ,
    KRUGER,
    GROSS,
    MAGATH,
    WILLY_TYBUR,
    ELDIAN_ARMBAND,
    KAYA,
    KEITH_SHADIS,
    LOUISE,
    TITAN_TRANSFORMATION,
    DECLARATION_OF_WAR,
    YMIR_FRITZ,
    KING_FRITZ,
    TITANS_BLESSING,
    WALL_TITAN_ARMY,
    PLAINS_AOT,
    ISLAND_AOT,
    SWAMP_AOT,
    MOUNTAIN_AOT,
    FOREST_AOT
]
