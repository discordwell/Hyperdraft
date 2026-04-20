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
from src.cards import interceptor_helpers as _ih
from typing import Optional, Callable


# =============================================================================
# KEYWORD STORAGE HELPERS
# =============================================================================
# The old abilities DSL represented keyword abilities as ``KeywordAbility("Foo")``
# instances. After the Phase 3 migration we lower those to plain dicts of the
# shape ``{'keyword': 'Foo'}`` which mirrors Hearthstone's convention and is
# what ``has_ability`` / ``Characteristics.keywords`` already understand.
#
# ``_kw_dicts`` returns a fresh list that can be installed on BOTH
# ``Characteristics.abilities`` (so ``has_ability(obj, 'flying', ...)`` works
# at runtime) and on ``CardDefinition.abilities`` (which several tests
# introspect via ``str(a)`` to spot keywords like ``"Hexproof"``).

def _kw_dicts(*keywords: str) -> list[dict]:
    """Return a list of ``{'keyword': name}`` dicts (preserves case)."""
    return [{'keyword': k} for k in keywords]


def _make_creature_with_keywords(
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
    """Build a creature CardDefinition with keyword dicts pre-installed.

    Keyword dicts live on BOTH ``characteristics.abilities`` (for runtime
    queries) and ``CardDefinition.abilities`` (for the string-based keyword
    assertions in ``tests/test_jujutsu_kaisen.py``). No DSL interceptors are
    generated because these are plain dicts, so ``setup_interceptors`` stays
    purely custom.
    """
    kw_list = list(keywords or [])
    char_abilities = _kw_dicts(*kw_list)
    # The CardDefinition abilities list is only for the keyword-substring
    # fallback in tests; use a separate instance so mutations don't leak.
    cd_abilities = _kw_dicts(*kw_list)
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
            abilities=char_abilities,
        ),
        text=text,
        abilities=cd_abilities,
        setup_interceptors=setup_interceptors,
    )


def _make_enchantment_with_keywords(
    *,
    name: str,
    mana_cost: str,
    colors: set,
    subtypes: set = None,
    keywords: list[str] = None,
    text: str = "",
    setup_interceptors=None,
) -> CardDefinition:
    """Same as ``_make_creature_with_keywords`` but for enchantments."""
    kw_list = list(keywords or [])
    char_abilities = _kw_dicts(*kw_list)
    cd_abilities = _kw_dicts(*kw_list)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes=subtypes or set(),
            colors=colors,
            mana_cost=mana_cost,
            abilities=char_abilities,
        ),
        text=text,
        abilities=cd_abilities,
        setup_interceptors=setup_interceptors,
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


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None, abilities=None):
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
        setup_interceptors=setup_interceptors,
        abilities=abilities
    )


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None, abilities=None):
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
        setup_interceptors=setup_interceptors,
        abilities=abilities
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
    # This remains using interceptors as it's a complex set-specific mechanic
    from src.cards.interceptor_helpers import make_static_pt_boost, make_keyword_grant
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
    from src.cards.interceptor_helpers import make_damage_trigger
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': heal_amount if heal_amount else amount},
            source=source_obj.id
        )]
    return make_damage_trigger(source_obj, damage_effect, combat_only=True)



# =============================================================================
# MIGRATED SETUP_INTERCEPTORS FUNCTIONS
# These functions replace the old abilities-DSL-generated interceptors for each
# card. They are ordered so that forward references (e.g. MEGUMI_FUSHIGURO's
# setup referencing yuji_itadori_setup) resolve correctly.
# =============================================================================

def _jujutsu_instructor_setup_migrated(obj, state):
    return _ih.make_static_pt_boost(
        obj, 1, 1, _ih.creatures_with_subtype(obj, "Student")
    )

def _masamichi_yaga_setup_migrated(obj, state):
    return _ih.make_static_pt_boost(
        obj, 1, 1, _ih.creatures_with_subtype(obj, "Cursed Corpse")
    )

def _shikigami_summoner_setup_migrated(obj, state):
    return _ih.make_static_pt_boost(
        obj, 1, 1, _ih.creatures_with_subtype(obj, "Shikigami")
    )

def _zenin_clan_elder_setup_migrated(obj, state):
    return _ih.make_static_pt_boost(
        obj, 1, 1, _ih.other_creatures_with_subtype(obj, "Sorcerer")
    )

def _self_embodiment_of_perfection_setup_migrated(obj, state):
    return _ih.make_static_pt_boost(
        obj, -1, -1, _ih.opponent_creatures_filter(obj)
    )

def _chimera_shadow_garden_setup_migrated(obj, state):
    filt = _ih.creatures_with_subtype(obj, "Shikigami")
    out = list(_ih.make_static_pt_boost(obj, 2, 2, filt))
    out.append(_ih.make_keyword_grant(obj, ["deathtouch"], filt))
    return out

def _window_guardian_setup_migrated(obj, state):
    return _ih.make_static_pt_boost(
        obj, 0, 1, _ih.other_creatures_with_subtype(obj, "Sorcerer")
    )

def _disease_curse_setup_migrated(obj, state):
    return [_ih.make_keyword_grant(
        obj, ["deathtouch"],
        _ih.other_creatures_with_subtype(obj, "Curse"),
    )]

def _special_grade_curse_setup_migrated(obj, state):
    return _ih.make_static_pt_boost(
        obj, 1, 1, _ih.other_creatures_with_subtype(obj, "Curse"),
    )

def _special_grade_sorcerer_setup_migrated(obj, state):
    return [_ih.make_keyword_grant(
        obj, ["hexproof"],
        _ih.other_creatures_with_subtype(obj, "Sorcerer"),
    )]

def _jujutsu_first_year_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 2},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_etb_trigger(obj, effect)]

def _holy_ward_monk_setup_migrated(obj, state):
    def effect(event, st):
        return []
    return [_ih.make_etb_trigger(obj, effect)]

def _technique_analyst_setup_migrated(obj, state):
    def effect(event, st):
        # Scry is non-functional in the old DSL; preserve placeholder.
        return []
    return [_ih.make_etb_trigger(obj, effect)]

def _auxiliary_manager_setup_migrated(obj, state):
    def effect(event, st):
        return []
    return [_ih.make_etb_trigger(obj, effect)]

def _yuta_okkotsu_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_spell_cast_trigger(
        obj, effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]

def _cursed_energy_sensor_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_spell_cast_trigger(obj, effect, controller_only=False)]

def _domain_master_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_spell_cast_trigger(
        obj, effect, spell_type_filter={CardType.ENCHANTMENT},
    )]

def _geto_suguru_setup_migrated(obj, state):
    def trigger_filter(event, st, src):
        if event.type != EventType.ZONE_CHANGE: return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD: return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD: return False
        dying_id = event.payload.get('object_id')
        dying = st.objects.get(dying_id)
        if not dying: return False
        if dying.id == src.id: return False  # exclude self
        if dying.controller == src.controller: return False  # opponent only
        if CardType.CREATURE not in dying.characteristics.types: return False
        return "Curse" in dying.characteristics.subtypes
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Absorbed Curse',
                               'power': 2, 'toughness': 2,
                               'colors': {Color.BLACK}, 'subtypes': {'Curse'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect, filter_fn=trigger_filter)]

def _megumi_fushiguro_setup_migrated(obj, state):
    def etb(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Divine Dog',
                               'power': 2, 'toughness': 2,
                               'colors': {Color.GREEN},
                               'subtypes': {'Shikigami', 'Dog'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    out = [_ih.make_etb_trigger(obj, etb)]
    out.extend(_ih.make_static_pt_boost(
        obj, 1, 0, _ih.creatures_with_subtype(obj, "Shikigami")
    ))
    return out

def _nobara_kugisaki_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_attack_trigger(obj, effect)]

def _aoi_todo_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_attack_trigger(obj, effect)]

def _yuji_itadori_setup_migrated(obj, state):
    def attack_effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 1, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    out = [_ih.make_attack_trigger(obj, attack_effect)]
    # Preserve the Binding Vow interceptor from the original setup.
    out.extend(yuji_itadori_setup(obj, state))
    return out

def _ryomen_sukuna_setup_migrated(obj, state):
    def etb(event, st):
        return []
    out = [_ih.make_etb_trigger(obj, etb)]
    out.extend(ryomen_sukuna_setup(obj, state))
    return out

def _mahito_setup_migrated(obj, state):
    def to_creature_filter(event, st, src):
        if event.type != EventType.DAMAGE: return False
        if event.payload.get('source') != src.id: return False
        target_id = event.payload.get('target')
        target_obj = st.objects.get(target_id)
        if not target_obj or CardType.CREATURE not in target_obj.characteristics.types:
            return False
        return True
    def effect(event, st):
        target_id = event.payload.get('target')
        if not target_id:
            return []
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': target_id, 'counter_type': '-1/-1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_damage_trigger(obj, effect, filter_fn=to_creature_filter)]

def _jogo_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_attack_trigger(obj, effect)]

def _hanami_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_upkeep_trigger(obj, effect)]

def _finger_bearer_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': opp, 'amount': -2},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_etb_trigger(obj, effect)]

def _cursed_womb_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Curse',
                               'power': 1, 'toughness': 1,
                               'colors': {Color.BLACK}, 'subtypes': {'Curse'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)
                for _ in range(2)]
    return [_ih.make_death_trigger(obj, effect)]

def _vengeful_spirit_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': opp, 'amount': -2},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_death_trigger(obj, effect)]

def _grasshopper_curse_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': opp, 'amount': -1},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_death_trigger(obj, effect)]

def _choso_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_attack_trigger(obj, effect)]

def _toji_fushiguro_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': 'boost'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_attack_trigger(obj, effect)]

def _berserker_sorcerer_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': 'boost'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_attack_trigger(obj, effect)]

def _disaster_flame_caster_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 3, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_etb_trigger(obj, effect)]

def _cursed_energy_bomb_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 4, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_death_trigger(obj, effect)]

def _meteor_curse_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_etb_trigger(obj, effect)]

def _panda_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_damage_trigger(obj, effect, combat_only=True)]

def _divine_dog_totality_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_attack_trigger(obj, effect)]

def _rabbit_escape_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Shikigami Rabbit',
                               'power': 1, 'toughness': 1,
                               'colors': {Color.GREEN},
                               'subtypes': {'Shikigami', 'Rabbit'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)
                for _ in range(3)]
    return [_ih.make_etb_trigger(obj, effect)]

def _divine_dog_white_setup_migrated(obj, state):
    def effect(event, st):
        return []
    return [_ih.make_etb_trigger(obj, effect)]

def _divine_dog_black_setup_migrated(obj, state):
    def effect(event, st):
        return []
    return [_ih.make_death_trigger(obj, effect)]

def _max_elephant_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 3, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_etb_trigger(obj, effect)]

def _cursed_bud_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_upkeep_trigger(obj, effect)]

def _nature_curse_spawn_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Curse',
                               'power': 1, 'toughness': 1,
                               'colors': {Color.GREEN}, 'subtypes': {'Curse'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect)]

def _round_deer_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 4},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_etb_trigger(obj, effect)]

def _tiger_funeral_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect)]

def _reverse_technique_master_setup_migrated(obj, state):
    # Preserve original Reverse Cursed Technique healing
    return reverse_technique_master_setup(obj, state)

def _curse_collector_setup_migrated(obj, state):
    def trigger_filter(event, st, src):
        if event.type != EventType.ZONE_CHANGE: return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD: return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD: return False
        dying = st.objects.get(event.payload.get('object_id'))
        if not dying: return False
        if dying.controller != src.controller: return False  # you control
        if CardType.CREATURE not in dying.characteristics.types: return False
        return "Curse" in dying.characteristics.subtypes
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect, filter_fn=trigger_filter)]

def _vengeful_ancestor_setup_migrated(obj, state):
    def effect(event, st):
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': opp, 'amount': -2},
                        source=obj.id, controller=obj.controller)
                  for opp in _ih.all_opponents(obj, st)]
        events.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': obj.controller, 'amount': 2},
                            source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]

def _domain_observer_setup_migrated(obj, state):
    def trigger_filter(event, st, src):
        if event.type != EventType.ZONE_CHANGE: return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD: return False
        entering = st.objects.get(event.payload.get('object_id'))
        if not entering: return False
        if entering.id == src.id: return False
        return CardType.CREATURE in entering.characteristics.types
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_etb_trigger(obj, effect, filter_fn=trigger_filter)]

def _curse_cycle_spirit_setup_migrated(obj, state):
    def effect(event, st):
        return []
    return [_ih.make_death_trigger(obj, effect)]

def _technique_inheritance_setup_migrated(obj, state):
    def trigger_filter(event, st, src):
        if event.type != EventType.ZONE_CHANGE: return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD: return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD: return False
        dying = st.objects.get(event.payload.get('object_id'))
        if not dying: return False
        if dying.controller != src.controller: return False
        if CardType.CREATURE not in dying.characteristics.types: return False
        return "Shikigami" in dying.characteristics.subtypes
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect, filter_fn=trigger_filter)]

def _finger_guardian_setup_migrated(obj, state):
    def effect(event, st):
        return []
    return [_ih.make_etb_trigger(obj, effect)]

def _malevolent_shrine_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_upkeep_trigger(obj, effect)]

def _horizon_of_captivating_skandha_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Shikigami Fish',
                               'power': 1, 'toughness': 1,
                               'colors': {Color.BLUE},
                               'subtypes': {'Shikigami', 'Fish'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_upkeep_trigger(obj, effect)]

def _shining_sea_of_flowers_setup_migrated(obj, state):
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 2},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_upkeep_trigger(obj, effect)]

def _cursed_womb_death_painting_setup_migrated(obj, state):
    def effect(event, st):
        events = [Event(type=EventType.OBJECT_CREATED,
                        payload={'token': True, 'name': 'Curse',
                                 'power': 1, 'toughness': 1,
                                 'colors': {Color.BLACK}, 'subtypes': {'Curse'},
                                 'keywords': [], 'controller': obj.controller},
                        source=obj.id, controller=obj.controller)]
        events.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': obj.controller, 'amount': -1},
                            source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]

def _curse_purge_setup_migrated(obj, state):
    def trigger_filter(event, st, src):
        if event.type != EventType.ZONE_CHANGE: return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD: return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD: return False
        dying = st.objects.get(event.payload.get('object_id'))
        if not dying: return False
        if CardType.CREATURE not in dying.characteristics.types: return False
        # Old DSL: you_control=False -> opponents' Curses
        if dying.controller == src.controller: return False
        return "Curse" in dying.characteristics.subtypes
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect, filter_fn=trigger_filter)]


# -----------------------------------------------------------------------------
# New / redesigned setup functions (quality pass)
# -----------------------------------------------------------------------------

def _satoru_gojo_setup(obj, state):
    """Limitless - Gojo and other Sorcerers you control have hexproof."""
    def filt(target, st):
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return "Sorcerer" in target.characteristics.subtypes
    return [_ih.make_keyword_grant(obj, ["hexproof"], filt)]


def _toge_inumaki_setup(obj, state):
    """Cursed Speech - attack trigger deals 2 damage to each opponent (word attack)."""
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id,
                               'is_combat': False},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_attack_trigger(obj, effect)]


def _kento_nanami_setup(obj, state):
    """Ratio Technique - attack trigger, deals 3 bonus damage to defending player."""
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 3, 'source': obj.id,
                               'is_combat': False},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_attack_trigger(obj, effect)]


def _dagon_setup(obj, state):
    """Ocean Curse - attack creates a 1/1 blue Shikigami Fish token."""
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Shikigami Fish',
                               'power': 1, 'toughness': 1,
                               'colors': {Color.BLUE},
                               'subtypes': {'Shikigami', 'Fish'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_attack_trigger(obj, effect)]


def _maki_zenin_setup(obj, state):
    """Heavenly Pact - other Warriors you control get +1/+1."""
    return _ih.make_static_pt_boost(
        obj, 1, 1, _ih.other_creatures_with_subtype(obj, "Warrior")
    )


def _naobito_zenin_setup(obj, state):
    """Projection Sorcery - attack trigger untaps Naobito (extra attacks simulated as counter)."""
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_attack_trigger(obj, effect)]


def _forest_spirit_curse_setup(obj, state):
    """Upkeep: create a 1/1 green Curse Plant token."""
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Cursed Sapling',
                               'power': 1, 'toughness': 1,
                               'colors': {Color.GREEN},
                               'subtypes': {'Curse', 'Plant'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_upkeep_trigger(obj, effect)]


def _divine_dog_white_setup(obj, state):
    """White Dog - other Shikigami you control get +0/+1."""
    return _ih.make_static_pt_boost(
        obj, 0, 1, _ih.other_creatures_with_subtype(obj, "Shikigami")
    )


def _divine_dog_black_setup(obj, state):
    """Black Dog - when it dies, deal 2 damage to each opponent."""
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id,
                               'is_combat': False},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_death_trigger(obj, effect)]


def _holy_ward_monk_setup(obj, state):
    """ETB gain 3 life."""
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 3},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_etb_trigger(obj, effect)]


def _curse_cycle_spirit_setup(obj, state):
    """Dies - create a 2/2 black Curse token."""
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Curse',
                               'power': 2, 'toughness': 2,
                               'colors': {Color.BLACK}, 'subtypes': {'Curse'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect)]


def _finger_guardian_setup(obj, state):
    """ETB: each opponent loses 3 life."""
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': opp, 'amount': -3},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_etb_trigger(obj, effect)]


def _uraume_setup(obj, state):
    """Ice Freeze - ETB taps up to two target creatures (we tap opponent creatures via events)."""
    def effect(event, st):
        events = []
        count = 0
        for other in list(st.objects.values()):
            if count >= 2:
                break
            if other.controller == obj.controller:
                continue
            if other.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in other.characteristics.types:
                continue
            events.append(Event(type=EventType.TAP,
                                payload={'object_id': other.id},
                                source=obj.id, controller=obj.controller))
            count += 1
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _kenjaku_setup(obj, state):
    """Body-swap - whenever an opponent's creature dies, put a +1/+1 counter on Kenjaku.
    Represents consuming their cursed technique."""
    def trigger_filter(event, st, src):
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying = st.objects.get(event.payload.get('object_id'))
        if not dying:
            return False
        if dying.id == src.id:
            return False
        if CardType.CREATURE not in dying.characteristics.types:
            return False
        return dying.controller != src.controller
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, effect, filter_fn=trigger_filter)]


def _rika_orimoto_setup(obj, state):
    """Cursed Queen - attack trigger deals 2 damage to each opponent (curse manifestation)."""
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 2, 'source': obj.id,
                               'is_combat': False},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_attack_trigger(obj, effect)]


def _mei_mei_setup(obj, state):
    """Crow Controller - attack trigger draws a card."""
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_attack_trigger(obj, effect)]


def _kamo_noritoshi_setup(obj, state):
    """Blood Wielder - whenever Kamo attacks, each opponent loses 1 life and you gain 1."""
    def effect(event, st):
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': opp, 'amount': -1},
                        source=obj.id, controller=obj.controller)
                  for opp in _ih.all_opponents(obj, st)]
        events.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': obj.controller, 'amount': 1},
                            source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _black_flash_user_setup(obj, state):
    """Black Flash - whenever Black Flash User deals combat damage, put a +1/+1 counter on it."""
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_damage_trigger(obj, effect, combat_only=True)]


def _infinity_apprentice_setup(obj, state):
    """Limitless student - whenever you cast an instant or sorcery, scry via draw (simplified: put +1/+1 counter)."""
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_spell_cast_trigger(
        obj, effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]


def _six_eyes_prodigy_setup(obj, state):
    """Six Eyes - whenever an opponent casts a spell, scry (we simplify: draw a card on your own spells)."""
    def effect(event, st):
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_spell_cast_trigger(
        obj, effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
        controller_only=True,
    )]


def _technique_prodigy_setup(obj, state):
    """Prowess payoff - whenever you cast a noncreature spell, put +1/+1 counter."""
    def spell_filter(event, st, src):
        if event.type != EventType.CAST:
            return False
        caster = event.payload.get('controller') or event.payload.get('player')
        if caster != src.controller:
            return False
        # Accept instant / sorcery
        obj_id = event.payload.get('object_id') or event.payload.get('source')
        spell = st.objects.get(obj_id) if obj_id else None
        if not spell:
            return False
        types = spell.characteristics.types
        return CardType.INSTANT in types or CardType.SORCERY in types
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_spell_cast_trigger(
        obj, effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]


def _domain_clashing_sorcerers_setup(obj, state):
    """When enters, create a 2/2 white Sorcerer Student token."""
    def effect(event, st):
        return [Event(type=EventType.OBJECT_CREATED,
                      payload={'token': True, 'name': 'Jujutsu Student',
                               'power': 2, 'toughness': 2,
                               'colors': {Color.WHITE},
                               'subtypes': {'Human', 'Sorcerer', 'Student'},
                               'keywords': [], 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_etb_trigger(obj, effect)]


def _binding_oath_enforcer_setup(obj, state):
    """Binding Vow: pay 2 life for +2/+0 until end of turn; also has lifelink-ish: +0/+1 to allies."""
    interceptors = []
    interceptors.extend(make_binding_vow(obj, 2, 2, 0))
    return interceptors


def _cursed_corpse_setup(obj, state):
    """Cursed Corpse - 2/2 colorless Construct, has haste (kept vanilla P/T)."""
    return []


def _hakari_kinji_setup(obj, state):
    """Jackpot - when Hakari attacks, flip a coin. On heads, untap Hakari and put +1/+1 counter.
    We simulate by putting a +1/+1 counter (the coin always lands heads in our simplified model)."""
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller),
                Event(type=EventType.UNTAP,
                      payload={'object_id': obj.id},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_attack_trigger(obj, effect)]


def _kashimo_setup(obj, state):
    """Duelist - whenever Kashimo deals combat damage, put a +1/+1 counter on him."""
    def effect(event, st):
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_damage_trigger(obj, effect, combat_only=True)]


def _angel_hana_kurusu_setup(obj, state):
    """Reverse effects - ETB each opponent loses 3 life; you gain 3 life."""
    def effect(event, st):
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': opp, 'amount': -3},
                        source=obj.id, controller=obj.controller)
                  for opp in _ih.all_opponents(obj, st)]
        events.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': obj.controller, 'amount': 3},
                            source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _tengen_setup(obj, state):
    """Barrier - Sorcerer creatures you control have vigilance and +0/+2."""
    interceptors = []
    filt = _ih.creatures_with_subtype(obj, "Sorcerer")
    interceptors.extend(_ih.make_static_pt_boost(obj, 0, 2, filt))
    interceptors.append(_ih.make_keyword_grant(obj, ["vigilance"], filt))
    return interceptors


def _gojo_unsealed_setup(obj, state):
    """Hollow Purple - ETB deals 5 damage to each opponent and exiles target creature-ish
    (we use damage-to-opp only; exile tokens fire as an OBJECT_DESTROYED on each nonhexproof opp creature)."""
    def effect(event, st):
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': opp, 'amount': -5},
                        source=obj.id, controller=obj.controller)
                  for opp in _ih.all_opponents(obj, st)]
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _shoko_ieri_setup(obj, state):
    """Healer - at the beginning of your upkeep, you gain 2 life. Other Sorcerers you control get +0/+1."""
    interceptors = []
    def effect(event, st):
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 2},
                      source=obj.id, controller=obj.controller)]
    interceptors.append(_ih.make_upkeep_trigger(obj, effect))
    interceptors.extend(_ih.make_static_pt_boost(
        obj, 0, 1, _ih.other_creatures_with_subtype(obj, "Sorcerer")
    ))
    return interceptors


def _yuki_tsukumo_setup(obj, state):
    """Star Rage - ETB deals damage to each opponent equal to number of cards in your hand (simulate: 4 damage flat)."""
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 4, 'source': obj.id,
                               'is_combat': False},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_etb_trigger(obj, effect)]


def _sorcerer_commander_setup(obj, state):
    """Sorcerer tribal anthem - other Sorcerers and Students you control get +1/+1."""
    def filt(target, st):
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        subs = target.characteristics.subtypes
        return "Sorcerer" in subs or "Student" in subs
    return _ih.make_static_pt_boost(obj, 1, 1, filt)


def _technique_echo_setup(obj, state):
    """Spells matter payoff - whenever you cast an instant/sorcery, deal 1 damage to each opponent."""
    def effect(event, st):
        return [Event(type=EventType.DAMAGE,
                      payload={'target': opp, 'amount': 1, 'source': obj.id,
                               'is_combat': False},
                      source=obj.id, controller=obj.controller)
                for opp in _ih.all_opponents(obj, st)]
    return [_ih.make_spell_cast_trigger(
        obj, effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]

# =============================================================================
# WHITE CARDS - JUJUTSU SORCERERS, PROTECTION, EXORCISM
# =============================================================================

# --- Legendary Creatures ---

def yuji_itadori_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sukuna's Vessel - Can have Sukuna cards attached. Binding Vow for power boost."""
    interceptors = []
    interceptors.extend(make_binding_vow(obj, 2, 2, 0))
    return interceptors

YUJI_ITADORI = _make_creature_with_keywords(
    name="Yuji Itadori, Sukuna's Vessel",
    power=3, toughness=3,
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    keywords=['Haste'],
    text="Haste Whenever Yuji Itadori, Sukuna's Vessel attacks, Yuji Itadori, Sukuna's Vessel deals 1 damage to each opponent.",
    setup_interceptors=_yuji_itadori_setup_migrated,
)


MEGUMI_FUSHIGURO = _make_creature_with_keywords(
    name="Megumi Fushiguro, Ten Shadows",
    power=2, toughness=3,
    mana_cost="{1}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text='When Megumi Fushiguro, Ten Shadows enters the battlefield, create a 2/2 green Divine Dog creature token. Shikigami creatures you control get +1/+0.',
    setup_interceptors=_megumi_fushiguro_setup_migrated,
)


NOBARA_KUGISAKI = _make_creature_with_keywords(
    name="Nobara Kugisaki, Straw Doll",
    power=3, toughness=2,
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    keywords=['First strike'],
    text='First strike Whenever Nobara Kugisaki, Straw Doll attacks, Nobara Kugisaki, Straw Doll deals 2 damage to each opponent.',
    setup_interceptors=_nobara_kugisaki_setup_migrated,
)


SATORU_GOJO = _make_creature_with_keywords(
    name="Satoru Gojo, The Strongest",
    power=6, toughness=6,
    mana_cost="{3}{W}{U}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['Hexproof', 'Flying'],
    text='Hexproof, Flying. Limitless: Sorcerer creatures you control have hexproof.',
    setup_interceptors=_satoru_gojo_setup,
)


AOI_TODO = _make_creature_with_keywords(
    name="Aoi Todo, Best Friend",
    power=5, toughness=4,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['Trample'],
    text='Trample Whenever Aoi Todo, Best Friend attacks, put a +1/+1 counter on Aoi Todo, Best Friend.',
    setup_interceptors=_aoi_todo_setup_migrated,
)


# --- Regular White Creatures ---

JUJUTSU_FIRST_YEAR = _make_creature_with_keywords(
    name="Jujutsu High First Year",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"},
    text='When Jujutsu High First Year enters the battlefield, you gain 2 life.',
    setup_interceptors=_jujutsu_first_year_setup_migrated,
)


KYOTO_STUDENT = _make_creature_with_keywords(
    name="Kyoto Jujutsu Student",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"},
    keywords=['Vigilance'],
    text='Vigilance',
)


EXORCIST_SORCERER = _make_creature_with_keywords(
    name="Exorcist Sorcerer",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    keywords=['Protection from Curses'],
    text='Protection from Curses',
)


WINDOW_GUARDIAN = _make_creature_with_keywords(
    name="Window Guardian",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    keywords=['Defender'],
    text='Defender Other Sorcerer creatures you control get +0/+1.',
    setup_interceptors=_window_guardian_setup_migrated,
)


BARRIER_TECHNICIAN = make_creature(
    name="Barrier Technician",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"}
)


TEMPLE_PRIEST = _make_creature_with_keywords(
    name="Temple Priest",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    keywords=['Lifelink'],
    text='Lifelink',
)


CURSED_SPEECH_STUDENT = make_creature(
    name="Cursed Speech Student",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"}
)


HOLY_WARD_MONK = _make_creature_with_keywords(
    name="Holy Ward Monk",
    power=2, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    keywords=['Vigilance'],
    text='Vigilance. When Holy Ward Monk enters the battlefield, you gain 3 life.',
    setup_interceptors=_holy_ward_monk_setup,
)


JUJUTSU_INSTRUCTOR = _make_creature_with_keywords(
    name="Jujutsu High Instructor",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text='Student creatures you control get +1/+1.',
    setup_interceptors=_jujutsu_instructor_setup_migrated,
)


GUARDIAN_SHIKIGAMI = _make_creature_with_keywords(
    name="Guardian Shikigami",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Shikigami"},
    keywords=['Defender', 'Vigilance'],
    text='Defender Vigilance',
)


def reverse_technique_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reverse Cursed Technique healing"""
    return [make_reverse_cursed_technique(obj, 0)]

REVERSE_TECHNIQUE_MASTER = _make_creature_with_keywords(
    name="Reverse Technique Master",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    keywords=['Lifelink'],
    text='Lifelink',
    setup_interceptors=_reverse_technique_master_setup_migrated,
)


BINDING_OATH_ENFORCER = _make_creature_with_keywords(
    name="Binding Oath Enforcer",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text='Binding Vow — Pay 2 life: Binding Oath Enforcer gets +2/+0 until end of turn. (Trade power for restraint.)',
    setup_interceptors=_binding_oath_enforcer_setup,
)


HEAVENLY_RESTRICTION_WARRIOR = _make_creature_with_keywords(
    name="Heavenly Restriction Warrior",
    power=4, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"},
    keywords=['First strike'],
    text='First strike',
)


# =============================================================================
# BLUE CARDS - GOJO, INFINITY, TECHNIQUE MASTERY
# =============================================================================

# --- Legendary Creatures ---

YUTA_OKKOTSU = _make_creature_with_keywords(
    name="Yuta Okkotsu, Rika's Beloved",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="Whenever you cast a instant or sorcery, put a +1/+1 counter on Yuta Okkotsu, Rika's Beloved.",
    setup_interceptors=_yuta_okkotsu_setup_migrated,
)


TOGE_INUMAKI = _make_creature_with_keywords(
    name="Toge Inumaki, Cursed Speech",
    power=2, toughness=2,
    mana_cost="{1}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text="Whenever Toge Inumaki, Cursed Speech attacks, Toge deals 2 damage to each opponent. (Cursed speech is law.)",
    setup_interceptors=_toge_inumaki_setup,
)


GETO_SUGURU = _make_creature_with_keywords(
    name="Geto Suguru, Curse Manipulator",
    power=4, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text='Whenever another Curse dies, create a 2/2 black Absorbed Curse creature token.',
    setup_interceptors=_geto_suguru_setup_migrated,
)


MASAMICHI_YAGA = _make_creature_with_keywords(
    name="Masamichi Yaga, Principal",
    power=3, toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text='Cursed Corpse creatures you control get +1/+1.',
    setup_interceptors=_masamichi_yaga_setup_migrated,
)


KENTO_NANAMI = _make_creature_with_keywords(
    name="Kento Nanami, Ratio Technique",
    power=4, toughness=3,
    mana_cost="{2}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['First strike'],
    text='First strike. Whenever Kento Nanami, Ratio Technique attacks, he deals 3 damage to each opponent. (7:3 ratio — overtime.)',
    setup_interceptors=_kento_nanami_setup,
)


# --- Regular Blue Creatures ---

TECHNIQUE_ANALYST = _make_creature_with_keywords(
    name="Technique Analyst",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text='When Technique Analyst enters the battlefield, scry 2.',
    setup_interceptors=_technique_analyst_setup_migrated,
)


INFINITY_APPRENTICE = _make_creature_with_keywords(
    name="Infinity Apprentice",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer", "Student"},
    text='Whenever you cast an instant or sorcery, put a +1/+1 counter on Infinity Apprentice.',
    setup_interceptors=_infinity_apprentice_setup,
)


CURSED_ENERGY_SENSOR = _make_creature_with_keywords(
    name="Cursed Energy Sensor",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text='Whenever an opponent casts a spell, you may draw a card.',
    setup_interceptors=_cursed_energy_sensor_setup_migrated,
)


SIX_EYES_PRODIGY = _make_creature_with_keywords(
    name="Six Eyes Prodigy",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text='Whenever you cast an instant or sorcery, draw a card.',
    setup_interceptors=_six_eyes_prodigy_setup,
)


ILLUSION_CASTER = make_creature(
    name="Illusion Caster",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"}
)


CURSED_TECHNIQUE_THIEF = make_creature(
    name="Cursed Technique Thief",
    power=3, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"}
)


DOMAIN_RESEARCHER = make_creature(
    name="Domain Researcher",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"}
)


LIMITLESS_STUDENT = _make_creature_with_keywords(
    name="Limitless Student",
    power=2, toughness=2,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer", "Student"},
    keywords=['Unblockable'],
    text='Unblockable',
)


SPATIAL_MANIPULATOR = make_creature(
    name="Spatial Manipulator",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"}
)


TECHNIQUE_REVERSAL_MAGE = _make_creature_with_keywords(
    name="Technique Reversal Mage",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    keywords=['Flash'],
    text='Flash',
)


NEW_SHADOW_PRACTITIONER = make_creature(
    name="New Shadow Practitioner",
    power=3, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"}
)


SIMPLE_DOMAIN_MASTER = make_creature(
    name="Simple Domain Master",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"}
)


# =============================================================================
# BLACK CARDS - CURSES, SUKUNA, MALEVOLENCE
# =============================================================================

# --- Legendary Creatures ---

def ryomen_sukuna_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """King of Curses - Binding Vow for power boost"""
    return make_binding_vow(obj, 3, 4, 0)

RYOMEN_SUKUNA = _make_creature_with_keywords(
    name="Ryomen Sukuna, King of Curses",
    power=7, toughness=6,
    mana_cost="{4}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Avatar"},
    supertypes={"Legendary"},
    keywords=['Double strike'],
    text='Double strike When Ryomen Sukuna, King of Curses enters the battlefield, .',
    setup_interceptors=_ryomen_sukuna_setup_migrated,
)


MAHITO = _make_creature_with_keywords(
    name="Mahito, Soul Sculptor",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    supertypes={"Legendary"},
    text='Whenever Mahito, Soul Sculptor deals damage to a creature, put a -1/-1 counter on that creature.',
    setup_interceptors=_mahito_setup_migrated,
)


JOGO = _make_creature_with_keywords(
    name="Jogo, Volcano Curse",
    power=5, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Elemental"},
    supertypes={"Legendary"},
    keywords=['Haste'],
    text='Haste Whenever Jogo, Volcano Curse attacks, Jogo, Volcano Curse deals 2 damage to each opponent.',
    setup_interceptors=_jogo_setup_migrated,
)


HANAMI = _make_creature_with_keywords(
    name="Hanami, Forest Curse",
    power=4, toughness=5,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Curse", "Elemental"},
    supertypes={"Legendary"},
    keywords=['Reach'],
    text='Reach At the beginning of your upkeep, put a +1/+1 counter on Hanami, Forest Curse.',
    setup_interceptors=_hanami_setup_migrated,
)


DAGON = _make_creature_with_keywords(
    name="Dagon, Ocean Curse",
    power=5, toughness=5,
    mana_cost="{3}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Curse", "Elemental"},
    supertypes={"Legendary"},
    keywords=['Unblockable'],
    text='Unblockable. Whenever Dagon, Ocean Curse attacks, create a 1/1 blue Shikigami Fish creature token.',
    setup_interceptors=_dagon_setup,
)


# --- Regular Black Creatures ---

FINGER_BEARER = _make_creature_with_keywords(
    name="Finger Bearer",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text='When Finger Bearer enters the battlefield, each opponent loses 2 life.',
    setup_interceptors=_finger_bearer_setup_migrated,
)


CURSED_WOMB = _make_creature_with_keywords(
    name="Cursed Womb",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    text='When Cursed Womb dies, create two 1/1 black Curse creature token.',
    setup_interceptors=_cursed_womb_setup_migrated,
)


VENGEFUL_SPIRIT = _make_creature_with_keywords(
    name="Vengeful Cursed Spirit",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Curse"},
    keywords=['Menace'],
    text='Menace When Vengeful Cursed Spirit dies, each opponent loses 2 life.',
    setup_interceptors=_vengeful_spirit_setup_migrated,
)


DISEASE_CURSE = _make_creature_with_keywords(
    name="Disease Curse",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    keywords=['Deathtouch'],
    text='Deathtouch Other Curse creatures you control have deathtouch.',
    setup_interceptors=_disease_curse_setup_migrated,
)


GRASSHOPPER_CURSE = _make_creature_with_keywords(
    name="Grasshopper Curse",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Curse", "Insect"},
    keywords=['Flying'],
    text='Flying When Grasshopper Curse dies, each opponent loses 1 life.',
    setup_interceptors=_grasshopper_curse_setup_migrated,
)


FLY_HEAD_CURSE = _make_creature_with_keywords(
    name="Fly Head Curse",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    keywords=['Flying', 'Haste'],
    text='Flying Haste',
)


RESENTFUL_CURSE = make_creature(
    name="Resentful Curse",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"}
)


SPECIAL_GRADE_CURSE = _make_creature_with_keywords(
    name="Special Grade Curse",
    power=6, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    keywords=['Menace'],
    text='Menace Other Curse creatures you control get +1/+1.',
    setup_interceptors=_special_grade_curse_setup_migrated,
)


MALEVOLENT_SHRINE_KEEPER = make_creature(
    name="Malevolent Shrine Keeper",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse", "Cleric"}
)


IDLE_TRANSFIGURATION_VICTIM = make_creature(
    name="Transfigured Human",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Curse", "Horror"}
)


CURSED_CORPSE = make_creature(
    name="Cursed Corpse",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct"}
)


GRADE_ONE_CURSE = make_creature(
    name="Grade One Curse",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"}
)


SMALLPOX_CURSE = make_creature(
    name="Smallpox Curse",
    power=2, toughness=1,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"}
)


CURSE_USER = make_creature(
    name="Curse User",
    power=2, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"}
)


# =============================================================================
# RED CARDS - COMBAT TECHNIQUES, DESTRUCTION
# =============================================================================

# --- Legendary Creatures ---

MAKI_ZENIN = _make_creature_with_keywords(
    name="Maki Zenin, Heavenly Pact",
    power=4, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    keywords=['First strike', 'Vigilance'],
    text='First strike, Vigilance. Other Warrior creatures you control get +1/+1.',
    setup_interceptors=_maki_zenin_setup,
)


CHOSO = _make_creature_with_keywords(
    name="Choso, Death Painting",
    power=4, toughness=4,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Curse", "Human"},
    supertypes={"Legendary"},
    text='Whenever Choso, Death Painting attacks, Choso, Death Painting deals 2 damage to each opponent.',
    setup_interceptors=_choso_setup_migrated,
)


TOJI_FUSHIGURO = _make_creature_with_keywords(
    name="Toji Fushiguro, Sorcerer Killer",
    power=5, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    keywords=['First strike'],
    text='First strike Whenever Toji Fushiguro, Sorcerer Killer attacks, put a boost counter on Toji Fushiguro, Sorcerer Killer.',
    setup_interceptors=_toji_fushiguro_setup_migrated,
)


NAOBITO_ZENIN = _make_creature_with_keywords(
    name="Naobito Zenin, Projection",
    power=4, toughness=3,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['Haste'],
    text='Haste. Whenever Naobito Zenin, Projection attacks, put a +1/+1 counter on him. (24 frames per second.)',
    setup_interceptors=_naobito_zenin_setup,
)


KAMO_NORITOSHI = _make_creature_with_keywords(
    name="Kamo Noritoshi, Blood Wielder",
    power=3, toughness=3,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    text='Whenever Kamo Noritoshi, Blood Wielder attacks, each opponent loses 1 life and you gain 1 life.',
    setup_interceptors=_kamo_noritoshi_setup,
)


# --- Regular Red Creatures ---

BERSERKER_SORCERER = _make_creature_with_keywords(
    name="Berserker Sorcerer",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    text='Whenever Berserker Sorcerer attacks, put a boost counter on Berserker Sorcerer.',
    setup_interceptors=_berserker_sorcerer_setup_migrated,
)


CURSED_TECHNIQUE_STRIKER = _make_creature_with_keywords(
    name="Cursed Technique Striker",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    keywords=['Haste'],
    text='Haste',
)


BLACK_FLASH_USER = _make_creature_with_keywords(
    name="Black Flash User",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    keywords=['Haste'],
    text='Haste. Whenever Black Flash User deals combat damage, put a +1/+1 counter on it.',
    setup_interceptors=_black_flash_user_setup,
)


DISASTER_FLAME_CASTER = _make_creature_with_keywords(
    name="Disaster Flame Caster",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Curse", "Shaman"},
    text='When Disaster Flame Caster enters the battlefield, Disaster Flame Caster deals 3 damage to each opponent.',
    setup_interceptors=_disaster_flame_caster_setup_migrated,
)


BLOOD_ARROW_ARCHER = make_creature(
    name="Blood Arrow Archer",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"}
)


ZENIN_CLAN_WARRIOR = _make_creature_with_keywords(
    name="Zenin Clan Warrior",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    keywords=['First strike'],
    text='First strike',
)


PLAYFUL_CLOUD_WIELDER = _make_creature_with_keywords(
    name="Playful Cloud Wielder",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    keywords=['Trample'],
    text='Trample',
)


CURSED_ENERGY_BOMB = _make_creature_with_keywords(
    name="Cursed Energy Bomb",
    power=4, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Curse", "Elemental"},
    text='When Cursed Energy Bomb dies, Cursed Energy Bomb deals 4 damage to each opponent.',
    setup_interceptors=_cursed_energy_bomb_setup_migrated,
)


MAXIMUM_OUTPUT_FIGHTER = make_creature(
    name="Maximum Output Fighter",
    power=5, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"}
)


CLEAVE_PRACTITIONER = make_creature(
    name="Cleave Practitioner",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"}
)


METEOR_CURSE = _make_creature_with_keywords(
    name="Meteor Curse",
    power=5, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Curse", "Elemental"},
    keywords=['Trample'],
    text='Trample When Meteor Curse enters the battlefield, Meteor Curse deals 2 damage to each opponent.',
    setup_interceptors=_meteor_curse_setup_migrated,
)


DOMAIN_AMPLIFIER = make_creature(
    name="Domain Amplifier",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"}
)


# =============================================================================
# GREEN CARDS - SHIKIGAMI, SUMMONING, NATURE CURSES
# =============================================================================

# --- Legendary Creatures ---

PANDA = _make_creature_with_keywords(
    name="Panda, Cursed Corpse",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Construct", "Panda"},
    supertypes={"Legendary"},
    keywords=['Trample'],
    text='Trample Whenever Panda, Cursed Corpse deals combat damage, put a +1/+1 counter on Panda, Cursed Corpse.',
    setup_interceptors=_panda_setup_migrated,
)


MAHORAGA = _make_creature_with_keywords(
    name="Mahoraga, Eight-Handled Sword",
    power=8, toughness=8,
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Divine"},
    supertypes={"Legendary"},
    keywords=['Trample', 'Indestructible'],
    text='Trample Indestructible',
)


DIVINE_DOG_TOTALITY = _make_creature_with_keywords(
    name="Divine Dog: Totality",
    power=5, toughness=4,
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Shikigami", "Dog"},
    supertypes={"Legendary"},
    keywords=['Menace'],
    text='Menace Whenever Divine Dog: Totality attacks, Divine Dog: Totality deals 2 damage to each opponent.',
    setup_interceptors=_divine_dog_totality_setup_migrated,
)


NUE_SHIKIGAMI = _make_creature_with_keywords(
    name="Nue, Thunder Shikigami",
    power=3, toughness=2,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Shikigami", "Bird"},
    supertypes={"Legendary"},
    keywords=['Flying'],
    text='Flying',
)


RABBIT_ESCAPE = _make_creature_with_keywords(
    name="Rabbit Escape Swarm",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Rabbit"},
    supertypes={"Legendary"},
    text='When Rabbit Escape Swarm enters the battlefield, create three 1/1 green Shikigami Rabbit creature token.',
    setup_interceptors=_rabbit_escape_setup_migrated,
)


# --- Regular Green Creatures ---

DIVINE_DOG_WHITE = _make_creature_with_keywords(
    name="Divine Dog: White",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Dog"},
    text='Other Shikigami you control get +0/+1.',
    setup_interceptors=_divine_dog_white_setup,
)


DIVINE_DOG_BLACK = _make_creature_with_keywords(
    name="Divine Dog: Black",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Dog"},
    text='When Divine Dog: Black dies, it deals 2 damage to each opponent.',
    setup_interceptors=_divine_dog_black_setup,
)


TOAD_SHIKIGAMI = _make_creature_with_keywords(
    name="Toad Shikigami",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Frog"},
    keywords=['Reach'],
    text='Reach',
)


MAX_ELEPHANT = _make_creature_with_keywords(
    name="Max Elephant",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Elephant"},
    keywords=['Trample'],
    text='Trample When Max Elephant enters the battlefield, you may Max Elephant deals 3 damage to each opponent.',
    setup_interceptors=_max_elephant_setup_migrated,
)


GREAT_SERPENT = _make_creature_with_keywords(
    name="Great Serpent Shikigami",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Snake"},
    keywords=['Deathtouch', 'Reach'],
    text='Deathtouch Reach',
)


SHIKIGAMI_SUMMONER = _make_creature_with_keywords(
    name="Shikigami Summoner",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    text='Shikigami creatures you control get +1/+1.',
    setup_interceptors=_shikigami_summoner_setup_migrated,
)


FOREST_SPIRIT_CURSE = _make_creature_with_keywords(
    name="Forest Spirit Curse",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Spirit"},
    keywords=['Hexproof'],
    text='Hexproof. At the beginning of your upkeep, create a 1/1 green Curse Plant creature token.',
    setup_interceptors=_forest_spirit_curse_setup,
)


CURSED_BUD = _make_creature_with_keywords(
    name="Cursed Bud",
    power=0, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Plant"},
    keywords=['Defender'],
    text='Defender At the beginning of your upkeep, put a +1/+1 counter on Cursed Bud.',
    setup_interceptors=_cursed_bud_setup_migrated,
)


NATURE_CURSE_SPAWN = _make_creature_with_keywords(
    name="Nature Curse Spawn",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Elemental"},
    text='When Nature Curse Spawn dies, create a 1/1 green Curse creature token.',
    setup_interceptors=_nature_curse_spawn_setup_migrated,
)


CHIMERA_DEATH_PAINTING = _make_creature_with_keywords(
    name="Chimera Death Painting",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Curse", "Chimera"},
    keywords=['Trample'],
    text='Trample',
)


WHEEL_SHIKIGAMI = make_creature(
    name="Wheel Shikigami",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Construct"}
)


ROUND_DEER = _make_creature_with_keywords(
    name="Round Deer Shikigami",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Elk"},
    text='When Round Deer Shikigami enters the battlefield, you gain 4 life.',
    setup_interceptors=_round_deer_setup_migrated,
)


TIGER_FUNERAL = _make_creature_with_keywords(
    name="Tiger Funeral Shikigami",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shikigami", "Cat"},
    keywords=['Haste'],
    text='Haste When Tiger Funeral Shikigami dies, draw a card.',
    setup_interceptors=_tiger_funeral_setup_migrated,
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

SUKUNA_FINGER = _make_creature_with_keywords(
    name="Sukuna's Finger",
    power=0, toughness=1,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Horror"},
    keywords=['Indestructible'],
    text='Indestructible',
)


RIKA_ORIMOTO = _make_creature_with_keywords(
    name="Rika Orimoto, Cursed Queen",
    power=6, toughness=6,
    mana_cost="{4}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Spirit", "Curse"},
    supertypes={"Legendary"},
    keywords=['Flying'],
    text='Flying. Whenever Rika Orimoto, Cursed Queen attacks, she deals 2 damage to each opponent.',
    setup_interceptors=_rika_orimoto_setup,
)


DOMAIN_CLASHING_SORCERERS = _make_creature_with_keywords(
    name="Domain-Clashing Sorcerers",
    power=4, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Sorcerer"},
    text='When Domain-Clashing Sorcerers enter the battlefield, create a 2/2 white Jujutsu Student creature token.',
    setup_interceptors=_domain_clashing_sorcerers_setup,
)


MEI_MEI = _make_creature_with_keywords(
    name="Mei Mei, Crow Controller",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['Flying'],
    text='Flying. Whenever Mei Mei, Crow Controller attacks, draw a card.',
    setup_interceptors=_mei_mei_setup,
)


SUGURU_GETO_CORRUPTED = _make_creature_with_keywords(
    name="Kenjaku, Brain Stealer",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text="Whenever a creature an opponent controls dies, put a +1/+1 counter on Kenjaku, Brain Stealer. (Consume the technique.)",
    setup_interceptors=_kenjaku_setup,
)


URAUME = _make_creature_with_keywords(
    name="Uraume, Ice Servant",
    power=3, toughness=4,
    mana_cost="{2}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    text='When Uraume, Ice Servant enters the battlefield, tap up to two creatures your opponents control.',
    setup_interceptors=_uraume_setup,
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

MALEVOLENT_SHRINE = _make_enchantment_with_keywords(
    name="Malevolent Shrine",
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Domain"},
    text='At the beginning of your upkeep, Malevolent Shrine deals 2 damage to each opponent.',
    setup_interceptors=_malevolent_shrine_setup_migrated,
)


UNLIMITED_VOID = make_enchantment(
    name="Unlimited Void",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Domain"}
)


CHIMERA_SHADOW_GARDEN = _make_enchantment_with_keywords(
    name="Chimera Shadow Garden",
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Domain"},
    text='Shikigami creatures you control get +2/+2. Shikigami creatures you control have deathtouch.',
    setup_interceptors=_chimera_shadow_garden_setup_migrated,
)


SELF_EMBODIMENT_OF_PERFECTION = _make_enchantment_with_keywords(
    name="Self-Embodiment of Perfection",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Domain"},
    text='Creatures your opponents control get -1/-1.',
    setup_interceptors=_self_embodiment_of_perfection_setup_migrated,
)


def coffin_of_the_iron_mountain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jogo's Domain - deals damage when creatures enter"""
    from src.cards.interceptor_helpers import make_etb_trigger

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
    setup_interceptors=coffin_of_the_iron_mountain_setup
)


HORIZON_OF_CAPTIVATING_SKANDHA = _make_enchantment_with_keywords(
    name="Horizon of the Captivating Skandha",
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Domain"},
    text='At the beginning of your upkeep, create a 1/1 blue Shikigami Fish creature token.',
    setup_interceptors=_horizon_of_captivating_skandha_setup_migrated,
)


SHINING_SEA_OF_FLOWERS = _make_enchantment_with_keywords(
    name="Shining Sea of Flowers",
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Domain"},
    text='At the beginning of your upkeep, you gain 2 life.',
    setup_interceptors=_shining_sea_of_flowers_setup_migrated,
)


AUTHENTIC_MUTUAL_LOVE = make_enchantment(
    name="Authentic Mutual Love",
    mana_cost="{4}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Domain"}
)


TIME_CELL_MOON_PALACE = make_enchantment(
    name="Time Cell Moon Palace",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Domain"}
)


DEADLY_SENTENCING = make_enchantment(
    name="Deadly Sentencing",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Domain"}
)


# --- Other Enchantments ---

CURSED_ENERGY_FLOW = make_enchantment(
    name="Cursed Energy Flow",
    mana_cost="{1}{B}",
    colors={Color.BLACK}
)


BINDING_CONTRACT = make_enchantment(
    name="Binding Contract",
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK}
)


HEAVENLY_RESTRICTION = make_enchantment(
    name="Heavenly Restriction",
    mana_cost="{1}{W}",
    colors={Color.WHITE}
)


CURSED_SPEECH_SEAL = make_enchantment(
    name="Cursed Speech Seal",
    mana_cost="{1}{U}",
    colors={Color.BLUE}
)


BARRIER_TECHNIQUE = make_enchantment(
    name="Barrier Technique",
    mana_cost="{2}{W}",
    colors={Color.WHITE}
)


CURSED_WOMB_DEATH_PAINTING = _make_enchantment_with_keywords(
    name="Cursed Womb: Death Painting",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text='At the beginning of your upkeep, create a 1/1 black Curse creature token and you lose 1 life.',
    setup_interceptors=_cursed_womb_death_painting_setup_migrated,
)


JUJUTSU_REGULATIONS = make_enchantment(
    name="Jujutsu Regulations",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE}
)


VEIL_TECHNIQUE = make_enchantment(
    name="Veil Technique",
    mana_cost="{1}{U}",
    colors={Color.BLUE}
)


CURSE_PURGE = _make_enchantment_with_keywords(
    name="Curse Purge",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text='Whenever Curse dies, you gain 1 life.',
    setup_interceptors=_curse_purge_setup_migrated,
)


# =============================================================================
# EQUIPMENT - CURSED TOOLS
# =============================================================================

INVERTED_SPEAR_OF_HEAVEN = make_equipment(
    name="Inverted Spear of Heaven",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has 'Damage dealt by this creature can't be prevented.' Equipped creature has protection from instants.",
    equip_cost="{2}",
    subtypes={"Cursed"}
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
    subtypes={"Human", "Sorcerer"}
)


ZENIN_CLAN_ELDER = _make_creature_with_keywords(
    name="Zenin Clan Elder",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer"},
    text='Other Sorcerer creatures you control get +1/+1.',
    setup_interceptors=_zenin_clan_elder_setup_migrated,
)


AUXILIARY_MANAGER = _make_creature_with_keywords(
    name="Auxiliary Manager",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text='When Auxiliary Manager enters the battlefield, scry 2.',
    setup_interceptors=_auxiliary_manager_setup_migrated,
)


CURSE_COLLECTOR = _make_creature_with_keywords(
    name="Curse Collector",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text='Whenever Curse you control dies, draw a card.',
    setup_interceptors=_curse_collector_setup_migrated,
)


DEATH_PAINTING_WOMB = _make_creature_with_keywords(
    name="Death Painting Womb",
    power=0, toughness=4,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    keywords=['Defender'],
    text='Defender',
)


BLOOD_MANIPULATION_EXPERT = make_creature(
    name="Blood Manipulation Expert",
    power=3, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Sorcerer"}
)


TECHNIQUE_PRODIGY = _make_creature_with_keywords(
    name="Technique Prodigy",
    power=2, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Sorcerer", "Student"},
    keywords=['Prowess'],
    text='Prowess. Whenever you cast an instant or sorcery, put a +1/+1 counter on Technique Prodigy.',
    setup_interceptors=_technique_prodigy_setup,
)


SHIKIGAMI_CRAFTER = make_creature(
    name="Shikigami Crafter",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Sorcerer"}
)


VENGEFUL_ANCESTOR = _make_creature_with_keywords(
    name="Vengeful Ancestor Spirit",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Curse"},
    text='When Vengeful Ancestor Spirit enters the battlefield, each opponent loses 2 life and you gain 2 life.',
    setup_interceptors=_vengeful_ancestor_setup_migrated,
)


DOMAIN_OBSERVER = _make_creature_with_keywords(
    name="Domain Observer",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text='Whenever another creature enters the battlefield, draw a card.',
    setup_interceptors=_domain_observer_setup_migrated,
)


CURSED_ENERGY_WELL = _make_creature_with_keywords(
    name="Cursed Energy Well",
    power=0, toughness=5,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Curse"},
    keywords=['Defender'],
    text='Defender',
)


SORCERER_HUNTER = _make_creature_with_keywords(
    name="Sorcerer Hunter",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    keywords=['Haste'],
    text='Haste',
)


SHIKIGAMI_TRAINER = make_creature(
    name="Shikigami Trainer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Sorcerer"}
)


DOMAIN_AMPLIFICATION_MAGE = make_creature(
    name="Domain Amplification Mage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"}
)


CURSE_CYCLE_SPIRIT = _make_creature_with_keywords(
    name="Curse Cycle Spirit",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spirit", "Curse"},
    text='When Curse Cycle Spirit dies, create a 2/2 black Curse creature token.',
    setup_interceptors=_curse_cycle_spirit_setup,
)


BINDING_VOW_WITNESS = make_creature(
    name="Binding Vow Witness",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Cleric"}
)


TECHNIQUE_INHERITANCE = _make_creature_with_keywords(
    name="Technique Inheritance Master",
    power=3, toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Sorcerer"},
    text='Whenever Shikigami you control dies, you may draw a card.',
    setup_interceptors=_technique_inheritance_setup_migrated,
)


SPECIAL_GRADE_SORCERER = _make_creature_with_keywords(
    name="Special Grade Sorcerer",
    power=5, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    keywords=['Hexproof'],
    text='Hexproof Other Sorcerer creatures you control have hexproof.',
    setup_interceptors=_special_grade_sorcerer_setup_migrated,
)


FINGER_GUARDIAN = _make_creature_with_keywords(
    name="Sukuna's Finger Guardian",
    power=4, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Curse", "Warrior"},
    keywords=['Menace'],
    text="Menace. When Sukuna's Finger Guardian enters the battlefield, each opponent loses 3 life.",
    setup_interceptors=_finger_guardian_setup,
)


DOMAIN_MASTER = _make_creature_with_keywords(
    name="Domain Master",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text='Whenever you cast a enchantment, draw a card.',
    setup_interceptors=_domain_master_setup_migrated,
)


# =============================================================================
# NEW ICONIC CHARACTERS (quality pass)
# =============================================================================

HAKARI_KINJI = _make_creature_with_keywords(
    name="Hakari Kinji, Private Pure Love Train",
    power=4, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Sorcerer", "Student"},
    supertypes={"Legendary"},
    keywords=['Haste'],
    text="Haste. Whenever Hakari attacks, put a +1/+1 counter on him and untap him. (Jackpot: spin to win.)",
    setup_interceptors=_hakari_kinji_setup,
)


KASHIMO_HAJIME = _make_creature_with_keywords(
    name="Kashimo Hajime, Electric Duelist",
    power=5, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['First strike', 'Haste'],
    text='First strike, Haste. Whenever Kashimo Hajime deals combat damage, put a +1/+1 counter on him.',
    setup_interceptors=_kashimo_setup,
)


ANGEL_HANA_KURUSU = _make_creature_with_keywords(
    name="Angel, Hana's Host",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer", "Angel"},
    supertypes={"Legendary"},
    keywords=['Flying'],
    text="Flying. When Angel, Hana's Host enters the battlefield, each opponent loses 3 life and you gain 3 life. (Reverse Cursed Technique: Jacob's Ladder.)",
    setup_interceptors=_angel_hana_kurusu_setup,
)


TENGEN = _make_creature_with_keywords(
    name="Tengen, Barrier Master",
    power=3, toughness=5,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['Hexproof'],
    text='Hexproof. Sorcerer creatures you control have vigilance and get +0/+2.',
    setup_interceptors=_tengen_setup,
)


GOJO_UNSEALED = _make_creature_with_keywords(
    name="Gojo Unsealed, Hollow Purple",
    power=7, toughness=5,
    mana_cost="{4}{W}{U}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['Hexproof', 'Flying', 'Haste'],
    text='Hexproof, Flying, Haste. When Gojo Unsealed, Hollow Purple enters the battlefield, each opponent loses 5 life. (Cursed Technique Amalgamation.)',
    setup_interceptors=_gojo_unsealed_setup,
)


SHOKO_IERI = _make_creature_with_keywords(
    name="Shoko Ieiri, Healer",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Sorcerer", "Cleric"},
    supertypes={"Legendary"},
    text='At the beginning of your upkeep, you gain 2 life. Other Sorcerer creatures you control get +0/+1.',
    setup_interceptors=_shoko_ieri_setup,
)


YUKI_TSUKUMO = _make_creature_with_keywords(
    name="Yuki Tsukumo, Star Rage",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Sorcerer"},
    supertypes={"Legendary"},
    keywords=['Trample'],
    text='Trample. When Yuki Tsukumo enters the battlefield, she deals 4 damage to each opponent. (Bom ba.)',
    setup_interceptors=_yuki_tsukumo_setup,
)


SORCERER_COMMANDER = _make_creature_with_keywords(
    name="Sorcerer Commander",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Sorcerer"},
    text='Other Sorcerer and Student creatures you control get +1/+1.',
    setup_interceptors=_sorcerer_commander_setup,
)


TECHNIQUE_ECHO = _make_creature_with_keywords(
    name="Technique Echo",
    power=2, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Spirit"},
    text='Whenever you cast an instant or sorcery, Technique Echo deals 1 damage to each opponent.',
    setup_interceptors=_technique_echo_setup,
)


BLACK_FLASH_MOMENT = make_instant(
    name="Black Flash Moment",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +4/+0 and gains first strike until end of turn. If it's a Sorcerer, it also gains trample.",
)


JACKPOT_DOMAIN = make_enchantment(
    name="Idle Death Gamble",
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Domain"},
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

    # New iconic characters & archetype payoffs
    "Hakari Kinji, Private Pure Love Train": HAKARI_KINJI,
    "Kashimo Hajime, Electric Duelist": KASHIMO_HAJIME,
    "Angel, Hana's Host": ANGEL_HANA_KURUSU,
    "Tengen, Barrier Master": TENGEN,
    "Gojo Unsealed, Hollow Purple": GOJO_UNSEALED,
    "Shoko Ieiri, Healer": SHOKO_IERI,
    "Yuki Tsukumo, Star Rage": YUKI_TSUKUMO,
    "Sorcerer Commander": SORCERER_COMMANDER,
    "Technique Echo": TECHNIQUE_ECHO,
    "Black Flash Moment": BLACK_FLASH_MOMENT,
    "Idle Death Gamble": JACKPOT_DOMAIN,
}


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    YUJI_ITADORI,
    MEGUMI_FUSHIGURO,
    NOBARA_KUGISAKI,
    SATORU_GOJO,
    AOI_TODO,
    JUJUTSU_FIRST_YEAR,
    KYOTO_STUDENT,
    EXORCIST_SORCERER,
    WINDOW_GUARDIAN,
    BARRIER_TECHNICIAN,
    TEMPLE_PRIEST,
    CURSED_SPEECH_STUDENT,
    HOLY_WARD_MONK,
    JUJUTSU_INSTRUCTOR,
    GUARDIAN_SHIKIGAMI,
    REVERSE_TECHNIQUE_MASTER,
    BINDING_OATH_ENFORCER,
    HEAVENLY_RESTRICTION_WARRIOR,
    YUTA_OKKOTSU,
    TOGE_INUMAKI,
    GETO_SUGURU,
    MASAMICHI_YAGA,
    KENTO_NANAMI,
    TECHNIQUE_ANALYST,
    INFINITY_APPRENTICE,
    CURSED_ENERGY_SENSOR,
    SIX_EYES_PRODIGY,
    ILLUSION_CASTER,
    CURSED_TECHNIQUE_THIEF,
    DOMAIN_RESEARCHER,
    LIMITLESS_STUDENT,
    SPATIAL_MANIPULATOR,
    TECHNIQUE_REVERSAL_MAGE,
    NEW_SHADOW_PRACTITIONER,
    SIMPLE_DOMAIN_MASTER,
    RYOMEN_SUKUNA,
    MAHITO,
    JOGO,
    HANAMI,
    DAGON,
    FINGER_BEARER,
    CURSED_WOMB,
    VENGEFUL_SPIRIT,
    DISEASE_CURSE,
    GRASSHOPPER_CURSE,
    FLY_HEAD_CURSE,
    RESENTFUL_CURSE,
    SPECIAL_GRADE_CURSE,
    MALEVOLENT_SHRINE_KEEPER,
    IDLE_TRANSFIGURATION_VICTIM,
    CURSED_CORPSE,
    GRADE_ONE_CURSE,
    SMALLPOX_CURSE,
    CURSE_USER,
    MAKI_ZENIN,
    CHOSO,
    TOJI_FUSHIGURO,
    NAOBITO_ZENIN,
    KAMO_NORITOSHI,
    BERSERKER_SORCERER,
    CURSED_TECHNIQUE_STRIKER,
    BLACK_FLASH_USER,
    DISASTER_FLAME_CASTER,
    BLOOD_ARROW_ARCHER,
    ZENIN_CLAN_WARRIOR,
    PLAYFUL_CLOUD_WIELDER,
    CURSED_ENERGY_BOMB,
    MAXIMUM_OUTPUT_FIGHTER,
    CLEAVE_PRACTITIONER,
    METEOR_CURSE,
    DOMAIN_AMPLIFIER,
    PANDA,
    MAHORAGA,
    DIVINE_DOG_TOTALITY,
    NUE_SHIKIGAMI,
    RABBIT_ESCAPE,
    DIVINE_DOG_WHITE,
    DIVINE_DOG_BLACK,
    TOAD_SHIKIGAMI,
    MAX_ELEPHANT,
    GREAT_SERPENT,
    SHIKIGAMI_SUMMONER,
    FOREST_SPIRIT_CURSE,
    CURSED_BUD,
    NATURE_CURSE_SPAWN,
    CHIMERA_DEATH_PAINTING,
    WHEEL_SHIKIGAMI,
    ROUND_DEER,
    TIGER_FUNERAL,
    SUKUNA_FINGER,
    RIKA_ORIMOTO,
    DOMAIN_CLASHING_SORCERERS,
    MEI_MEI,
    SUGURU_GETO_CORRUPTED,
    URAUME,
    DIVERGENT_FIST,
    BLACK_FLASH,
    HOLLOW_PURPLE,
    REVERSAL_RED,
    LAPSE_BLUE,
    DOMAIN_AMPLIFICATION,
    CURSED_ENERGY_DRAIN,
    IDLE_TRANSFIGURATION,
    CLEAVE,
    DISMANTLE,
    EXORCISM_RITE,
    SIMPLE_DOMAIN,
    FALLING_BLOSSOM_EMOTION,
    MAXIMUM_UZUMAKI,
    RESONANCE,
    HAIRPIN,
    STRAW_DOLL_TECHNIQUE,
    BLOOD_MANIPULATION,
    SUPERNOVA,
    TEN_SHADOWS_SUMMON,
    INHERITED_TECHNIQUE,
    CURSED_BUD_GROWTH,
    REVERSE_CURSED_TECHNIQUE,
    BINDING_VOW_INSTANT,
    CURSED_TECHNIQUE_LAPSE,
    DOMAIN_NEGATION,
    CURSE_ABSORPTION,
    PROJECTION_SORCERY,
    SHIBUYA_INCIDENT,
    CULLING_GAME,
    NIGHT_PARADE,
    JUJUTSU_HIGH_TRAINING,
    KYOTO_GOODWILL_EVENT,
    CURSE_PURIFICATION,
    DOMAIN_COLLAPSE,
    UNLIMITED_VOID_BURST,
    SHIKIGAMI_ARMY,
    CURSE_GENESIS,
    MASSACRE,
    TECHNIQUE_MASTERY,
    SOUL_MULTIPLICITY,
    MALEVOLENT_SHRINE,
    UNLIMITED_VOID,
    CHIMERA_SHADOW_GARDEN,
    SELF_EMBODIMENT_OF_PERFECTION,
    COFFIN_OF_THE_IRON_MOUNTAIN,
    HORIZON_OF_CAPTIVATING_SKANDHA,
    SHINING_SEA_OF_FLOWERS,
    AUTHENTIC_MUTUAL_LOVE,
    TIME_CELL_MOON_PALACE,
    DEADLY_SENTENCING,
    CURSED_ENERGY_FLOW,
    BINDING_CONTRACT,
    HEAVENLY_RESTRICTION,
    CURSED_SPEECH_SEAL,
    BARRIER_TECHNIQUE,
    CURSED_WOMB_DEATH_PAINTING,
    JUJUTSU_REGULATIONS,
    VEIL_TECHNIQUE,
    CURSE_PURGE,
    INVERTED_SPEAR_OF_HEAVEN,
    PLAYFUL_CLOUD,
    SLAUGHTER_DEMON,
    SPLIT_SOUL_KATANA,
    DRAGON_BONE,
    FESTERING_LIFE_SWORD,
    BLACK_ROPE,
    GLASSES_OF_PERCEPTION,
    MEGUMI_KNIFE,
    MAKI_GLASSES,
    CURSED_TOOL_COLLECTION,
    PRISON_REALM,
    FINGER_COLLECTION,
    CURSED_ENERGY_DETECTOR,
    JUJUTSU_HIGH_EMBLEM,
    VEIL_GENERATOR,
    CURSED_SPEECH_RICE_BALL,
    JUJUTSU_HIGH,
    SHIBUYA_STATION,
    KYOTO_SCHOOL,
    CURSED_GROUNDS,
    FINGER_SHRINE,
    HIDDEN_INVENTORY,
    TOKYO_TOWER,
    DOMAIN_BATTLEFIELD,
    CURSE_BREAKER,
    ZENIN_CLAN_ELDER,
    AUXILIARY_MANAGER,
    CURSE_COLLECTOR,
    DEATH_PAINTING_WOMB,
    BLOOD_MANIPULATION_EXPERT,
    TECHNIQUE_PRODIGY,
    SHIKIGAMI_CRAFTER,
    VENGEFUL_ANCESTOR,
    DOMAIN_OBSERVER,
    CURSED_ENERGY_WELL,
    SORCERER_HUNTER,
    SHIKIGAMI_TRAINER,
    DOMAIN_AMPLIFICATION_MAGE,
    CURSE_CYCLE_SPIRIT,
    BINDING_VOW_WITNESS,
    TECHNIQUE_INHERITANCE,
    SPECIAL_GRADE_SORCERER,
    FINGER_GUARDIAN,
    DOMAIN_MASTER,
    HAKARI_KINJI,
    KASHIMO_HAJIME,
    ANGEL_HANA_KURUSU,
    TENGEN,
    GOJO_UNSEALED,
    SHOKO_IERI,
    YUKI_TSUKUMO,
    SORCERER_COMMANDER,
    TECHNIQUE_ECHO,
    BLACK_FLASH_MOMENT,
    JACKPOT_DOMAIN
]
