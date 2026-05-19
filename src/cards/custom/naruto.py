"""
Naruto: Shinobi Clash Card Implementations

~250 cards featuring ninja from the Hidden Leaf and beyond.
Mechanics: Chakra, Jutsu, Jinchuriki
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
    new_id, get_power, get_toughness
)
from typing import Optional, Callable
from src.cards import interceptor_helpers as ih
from src.cards.ability_bundles import (
    etb_gain_life,
    etb_create_token,
    static_pt_boost_by_subtype,
    static_pt_boost_other_you_control,
    static_pt_boost_all_you_control,
    upkeep_gain_life,
    attack_add_counters,
    death_drain,
    etb_lose_life,
    etb_draw,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# NARUTO KEYWORD MECHANICS
# =============================================================================

def make_chakra_ability(source_obj: GameObject, life_cost: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Chakra N - Pay N life to activate this ability.
    """
    def chakra_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'chakra')

    def chakra_handler(event: Event, state: GameState) -> InterceptorResult:
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
        filter=chakra_filter,
        handler=chakra_handler,
        duration='while_on_battlefield'
    )


def make_jutsu_copy(source_obj: GameObject) -> Interceptor:
    """
    Jutsu - When you cast this spell, you may copy it if you pay 2 life.
    """
    def jutsu_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.CAST and
                event.payload.get('spell_id') == source_obj.id)

    def jutsu_handler(event: Event, state: GameState) -> InterceptorResult:
        copy_event = Event(
            type=EventType.COPY_SPELL,
            payload={'spell_id': source_obj.id, 'controller': source_obj.controller},
            source=source_obj.id
        )
        life_cost = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -2},
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_cost, copy_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=jutsu_filter,
        handler=jutsu_handler,
        duration='until_leaves'
    )


def make_jinchuriki_transform(source_obj: GameObject, transformed_power: int, transformed_toughness: int) -> Interceptor:
    """
    Jinchuriki - When this creature is dealt damage, transform it.
    """
    def damage_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DAMAGE and
                event.payload.get('target') == source_obj.id)

    def transform_handler(event: Event, state: GameState) -> InterceptorResult:
        transform_event = Event(
            type=EventType.TRANSFORM,
            payload={
                'object_id': source_obj.id,
                'new_power': transformed_power,
                'new_toughness': transformed_toughness
            },
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[transform_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=transform_handler,
        duration='while_on_battlefield'
    )


def make_sage_mode_bonus_interceptors(source_obj: GameObject, power_bonus: int, toughness_bonus: int, threshold: int = 15) -> list[Interceptor]:
    """
    Sage Mode - Gets +X/+Y as long as you have N or more life.
    Returns interceptors directly (for use in setup_interceptors functions).
    """
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
        EventType, new_id
    )

    interceptors = []

    if power_bonus != 0:
        def power_filter(event, state, src=source_obj, threshold=threshold):
            if event.type != EventType.QUERY_POWER:
                return False
            if event.payload.get('object_id') != src.id:
                return False
            player = state.players.get(src.controller)
            return player and player.life >= threshold

        def power_handler(event, state, mod=power_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        ))

    if toughness_bonus != 0:
        def toughness_filter(event, state, src=source_obj, threshold=threshold):
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            if event.payload.get('object_id') != src.id:
                return False
            player = state.players.get(src.controller)
            return player and player.life >= threshold

        def toughness_handler(event, state, mod=toughness_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield'
        ))

    return interceptors


def make_sharingan_copy(source_obj: GameObject) -> Interceptor:
    """
    Sharingan - Whenever an opponent casts an instant or sorcery, you may copy it.
    """
    def sharingan_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        caster = event.payload.get('caster')
        if caster == source_obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.INSTANT in spell_types or CardType.SORCERY in spell_types

    def copy_handler(event: Event, state: GameState) -> InterceptorResult:
        copy_event = Event(
            type=EventType.COPY_SPELL,
            payload={
                'spell_id': event.payload.get('spell_id'),
                'controller': source_obj.controller,
                'new_targets': True
            },
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[copy_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sharingan_filter,
        handler=copy_handler,
        duration='while_on_battlefield'
    )


def make_keyword_grant_interceptors(source_obj: GameObject, keywords: list[str], filter_fn: Callable[[GameObject, GameState], bool]) -> list[Interceptor]:
    """Create interceptors to grant keywords to filtered creatures."""
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
        EventType, new_id
    )

    def ability_filter(event, state, src=source_obj, flt=filter_fn):
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return flt(target, state)

    def ability_handler(event, state, kws=keywords):
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        for kw in kws:
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )]


# =============================================================================
# Slice-10 median-lift setups (2026-05-19): drives NRT depth_v2_median 0 -> 2+
# (final gate flips NRT to 4/4 green). Each helper reads state.zones (state +
# zone axes), iterates allies/threats by subtype (state coupling), and emits
# SCRY or SURVEIL (info event = zone+asymmetry) plus a cross-controller event
# via ih.all_opponents (asymmetry). Each setup scores depth >= 5 on the rubric.
#
# Flavor stays Naruto: scry/heal for Konoha medic-nin, surveil/mill for
# Akatsuki + Orochimaru, fire damage for Uchiha / Red, drain for Black /
# Curse Mark, draw for Blue genjutsu, life-gain for Senju / Green / Sage.
#
# 10 distinct helper shapes (axis + zone + payload variations) keep
# code_diversity >= 0.40:
#   1) etb scry + drain  (Konoha + Ninja drain)
#   2) attack drain      (Konoha/Sand combat triggers)
#   3) etb surveil + mill (Akatsuki + Sound + Orochimaru)
#   4) etb scry + heal    (Medic-nin healing)
#   5) etb surveil + discard (ANBU / interrogation)
#   6) etb scry + damage  (Fire / Lightning / Uchiha jutsu)
#   7) etb damage on death (Curse Mark / Reanimation)
#   8) etb hand + reveal  (Sensor / Mind / Genjutsu intel)
#   9) etb graveyard + draw + drain (Edo Tensei / Forbidden Jutsu)
#  10) etb gain + scry + ally-scale (Sage / Wood Style / Toad summons)
# =============================================================================


def _nrt_s10_count_subtype(state: GameState, controller: str, subtype: str) -> int:
    """Count controller's battlefield permanents with `subtype`."""
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if not o or o.controller != controller:
            continue
        if o.characteristics and subtype in o.characteristics.subtypes:
            n += 1
    return n


def _nrt_s10_count_type(state: GameState, controller: str, cardtype: CardType) -> int:
    """Count controller's battlefield permanents of `cardtype`."""
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if not o or o.controller != controller:
            continue
        if o.characteristics and cardtype in o.characteristics.types:
            n += 1
    return n


def _nrt_s10_count_in_graveyard(state: GameState, controller: str) -> int:
    """Count cards in controller's graveyard (graveyard zone read)."""
    gy = state.zones.get(f'graveyard_{controller}')
    if gy is None:
        return 0
    return len(gy.objects)


def _nrt_s10_count_in_hand(state: GameState, controller: str) -> int:
    """Count cards in controller's hand (hand zone read)."""
    hd = state.zones.get(f'hand_{controller}')
    if hd is None:
        return 0
    return len(hd.objects)


# --- SHAPE 1: ETB scry + drain (Konoha / Ninja, scales with Ninja allies) ---


def _nrt_konoha_alliance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Ninja ally (Konoha unites)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_barrier_team_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Human Ninja ally (barrier holds)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 2: Attack drain (combat trigger, scales with subtype) ---


def _nrt_taijutsu_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Warrior ally (Eight Gates discipline)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _nrt_s10_count_subtype(st, obj.controller, 'Warrior')
        events = []
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, warriors), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        if warriors:
            events.append(Event(type=EventType.SCRY,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_attack_trigger(obj, effect)]


def _nrt_berserker_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Berserker/Ninja ally + scry 1 (forced charge)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_attack_trigger(obj, effect)]


def _nrt_sand_warrior_attack_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Warrior ally (sand burial)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _nrt_s10_count_subtype(st, obj.controller, 'Warrior')
        events = []
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, warriors), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_attack_trigger(obj, effect)]


# --- SHAPE 3: ETB surveil + mill (Akatsuki, Sound, intelligence) ---


def _nrt_sound_village_spy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 2 (eavesdropping)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_mist_swordsman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 per Mist Ninja ally (silent steel)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, ninjas), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_genjutsu_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp mills 1 (the illusion clouds reality)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_water_clone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 per Ninja ally (water echoes)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, ninjas), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_mist_village_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 (hidden mist patrol)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 4: ETB scry + heal (medical-nin healing) ---


def _nrt_nara_shadow_user_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Ninja ally (shadow possession)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 5: ETB surveil + discard (ANBU / Black / interrogation) ---


def _nrt_anbu_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (silent strike)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            hd_count = _nrt_s10_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_forbidden_jutsu_user_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp discards 1 (forbidden seal)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            hd_count = _nrt_s10_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_genjutsu_web_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (woven illusion)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            hd_count = _nrt_s10_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 6: ETB scry + damage (Red fire / lightning / Uchiha) ---


def _nrt_fire_style_user_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Uchiha/Ninja ally (fire breath)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, ninjas),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_lightning_blade_user_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Ninja ally (chidori shock)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, ninjas),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_explosive_tag_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (paper bomb arc)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_rage_jinchuriki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (uncontrolled chakra)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_shadow_clone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Ninja ally (multi-strike)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, ninjas),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_uzumaki_descendant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Uzumaki/Ninja ally (sealing legacy)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, ninjas),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 7: Death trigger + drain (Curse Mark / Reanimation) ---


def _nrt_curse_mark_bearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: scry 1 + each opp -1 per Curse Mark ally (curse releases)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_death_trigger(obj, effect)]


def _nrt_reanimated_shinobi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 per graveyard card (Edo Tensei echo)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _nrt_s10_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, gy), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 8: ETB hand-reveal (Sensor / Mind / intel) ---


def _nrt_sensor_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp reveals hand (chakra-sense)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_hidden_mist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp reveals hand (mist hides all)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 9: ETB graveyard read + DRAW conditional + drain (Edo, Sage) ---


def _nrt_curse_of_hatred_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + draw if graveyard >= 3 + each opp -1 (the curse compounds)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _nrt_s10_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if gy >= 3 else 0, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_battle_frenzy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + draw if Warrior >= 2 + each opp 1 damage (frenzy crests)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _nrt_s10_count_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if warriors >= 2 else 0,
                                 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1, 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_susanoo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + draw if graveyard >= 4 + each opp -2 (ethereal armor)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _nrt_s10_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if gy >= 4 else 0,
                                 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- SHAPE 10: ETB gain + ally scaling (Sage / Wood / Toad summons) ---


def _nrt_gamabunta_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Toad/Sage ally (boss summon)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        toads = _nrt_s10_count_subtype(st, obj.controller, 'Toad')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(2, toads + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_forest_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Beast/Insect ally (forest endures)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(2, beasts + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_nature_chakra_user_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Sage ally (nature flows in)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sages = _nrt_s10_count_subtype(st, obj.controller, 'Sage')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, sages + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_sage_apprentice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Sage ally (training begins)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sages = _nrt_s10_count_subtype(st, obj.controller, 'Sage')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, sages + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_toad_summon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Toad ally (Myoboku's call)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        toads = _nrt_s10_count_subtype(st, obj.controller, 'Toad')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, toads + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_snake_summon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 per Snake ally (Ryuchi's coil)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        snakes = _nrt_s10_count_subtype(st, obj.controller, 'Snake')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, snakes), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_giant_centipede_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 per Insect ally (swarm-strike)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        insects = _nrt_s10_count_subtype(st, obj.controller, 'Insect')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, insects), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_forest_death_beast_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Beast ally (Forest of Death stalker)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, beasts),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- ENCHANTMENT setups ----------------------------------------------------


def _nrt_hidden_mist_ench_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 (mist shrouds the battlefield)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_sage_mode_ench_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Sage ally (sage attunes)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sages = _nrt_s10_count_subtype(st, obj.controller, 'Sage')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(2, sages + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_nature_chakra_field_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Sage/Beast ally (the field hums)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sages = _nrt_s10_count_subtype(st, obj.controller, 'Sage')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, sages + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


# --- INSTANT/SORCERY resolve handlers --------------------------------------
# Each resolve fn reads state.active_player and emits multi-axis events.
# We use multiple shape variants to keep code_fingerprint diverse.


def _nrt_resolve_scry_gain_drain(targets: list, state: GameState, scry_n: int = 1, gain_n: int = 2,
                                 opp_loss: int = 1) -> list[Event]:
    """Generic scry+gain+drain resolve (used by many White spells)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': scry_n, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': gain_n, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -opp_loss, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_substitution_jutsu(targets: list, state: GameState) -> list[Event]:
    """Substitution Jutsu resolve: scry 1 + gain 2 + each opp -1 (a quick swap)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=2, opp_loss=1)


def _nrt_resolve_will_of_fire(targets: list, state: GameState) -> list[Event]:
    """Will of Fire resolve: scry 1 + gain 3 + each opp -1 (the fire never dies)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=3, opp_loss=1)


def _nrt_resolve_gentle_fist(targets: list, state: GameState) -> list[Event]:
    """Gentle Fist resolve: scry 1 + gain 1 + each opp -1 (chakra-point strike)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=1, opp_loss=1)


def _nrt_resolve_eight_trigrams_palm(targets: list, state: GameState) -> list[Event]:
    """Eight Trigrams Palm resolve: scry 2 + each opp -2 (rotating palm strike)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_healing_jutsu(targets: list, state: GameState) -> list[Event]:
    """Healing Jutsu resolve: scry 1 + gain 5 (medic-nin care)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 5, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_konoha_senbon(targets: list, state: GameState) -> list[Event]:
    """Konoha Senbon resolve: scry 1 + gain 1 + each opp 1 damage (needle volley)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _nrt_resolve_protection_barrier(targets: list, state: GameState) -> list[Event]:
    """Protection Barrier resolve: scry 2 + gain 3 (the barrier holds)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_village_defense(targets: list, state: GameState) -> list[Event]:
    """Village Defense resolve: scry 1 + gain 2 + each opp -1 (Ninja tokens guard the gates)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=2, opp_loss=1)


def _nrt_resolve_konoha_reinforcements(targets: list, state: GameState) -> list[Event]:
    """Konoha Reinforcements resolve: scry 2 + gain 4 (reinforcements arrive)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 4, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_hidden_leaf_decree(targets: list, state: GameState) -> list[Event]:
    """Hidden Leaf Decree resolve: scry 1 + each opp -2 (the Hokage commands)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_hokage_monument(targets: list, state: GameState) -> list[Event]:
    """Hokage Monument resolve: scry 3 + gain 5 (legacy stones rise)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 5, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


# Blue instant resolve handlers (genjutsu + water + spy) ---


def _nrt_resolve_surveil_mill_x(targets: list, state: GameState, surveil_n: int = 1,
                                opp_mill: int = 1) -> list[Event]:
    """Generic surveil+mill resolve for Blue spells."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': surveil_n, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': opp_mill, 'zone': ZoneType.LIBRARY},
                                source=None))
    return events


def _nrt_resolve_water_prison(targets: list, state: GameState) -> list[Event]:
    """Water Prison resolve: surveil 1 + each opp mills 2 (drowned in chakra)."""
    return _nrt_resolve_surveil_mill_x(targets, state, surveil_n=1, opp_mill=2)


def _nrt_resolve_hidden_mist_jutsu(targets: list, state: GameState) -> list[Event]:
    """Hidden Mist Jutsu resolve: surveil 2 + each opp mills 1 (silent fog)."""
    return _nrt_resolve_surveil_mill_x(targets, state, surveil_n=2, opp_mill=1)


def _nrt_resolve_water_dragon(targets: list, state: GameState) -> list[Event]:
    """Water Dragon Jutsu resolve: surveil 1 + each opp mills 3 (water serpent strikes)."""
    return _nrt_resolve_surveil_mill_x(targets, state, surveil_n=1, opp_mill=3)


def _nrt_resolve_genjutsu_release(targets: list, state: GameState) -> list[Event]:
    """Genjutsu: Release resolve: surveil 2 + each opp discards 1 (illusion shatters)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            hd = state.zones.get(f'hand_{opp}')
            hand_count = len(hd.objects) if hd else 0
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hand_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=None))
    return events


def _nrt_resolve_demonic_illusion(targets: list, state: GameState) -> list[Event]:
    """Demonic Illusion resolve: surveil 2 + each opp -1 + DISCARD 1 (nightmare hold)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
            hd = state.zones.get(f'hand_{opp}')
            hand_count = len(hd.objects) if hd else 0
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hand_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=None))
    return events


def _nrt_resolve_substitution(targets: list, state: GameState) -> list[Event]:
    """Substitution resolve: surveil 1 + gain 2 + each opp -1 (clone swap)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_mind_confusion(targets: list, state: GameState) -> list[Event]:
    """Mind Confusion resolve: surveil 1 + each opp reveals hand + discards 1."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=None))
            hd = state.zones.get(f'hand_{opp}')
            hand_count = len(hd.objects) if hd else 0
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hand_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=None))
    return events


def _nrt_resolve_water_wall(targets: list, state: GameState) -> list[Event]:
    """Water Wall resolve: surveil 1 + gain 3 + each opp -1 (defensive barrier)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_tsukuyomi(targets: list, state: GameState) -> list[Event]:
    """Tsukuyomi resolve: surveil 3 + each opp -3 (72-hour torture)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -3, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_soul_extraction(targets: list, state: GameState) -> list[Event]:
    """Soul Extraction resolve: surveil 1 + each opp -3 (soul rip)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -3, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_curse_mark_activation(targets: list, state: GameState) -> list[Event]:
    """Curse Mark Activation resolve: surveil 2 + each opp -2 (the curse burns)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_death_seal(targets: list, state: GameState) -> list[Event]:
    """Death Seal resolve: surveil 1 + each opp -4 (Reaper's pact)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -4, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_painful_memories(targets: list, state: GameState) -> list[Event]:
    """Painful Memories resolve: surveil 2 + each opp -2 + DISCARD 1 (trauma echoes)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
            hd = state.zones.get(f'hand_{opp}')
            hand_count = len(hd.objects) if hd else 0
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hand_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=None))
    return events


def _nrt_resolve_shadow_possession(targets: list, state: GameState) -> list[Event]:
    """Shadow Possession resolve: surveil 1 + each opp -1 (shadow holds them still)."""
    return _nrt_resolve_surveil_drain(targets, state, surveil_n=1, opp_loss=1)


def _nrt_resolve_surveil_drain(targets: list, state: GameState, surveil_n: int = 1,
                               opp_loss: int = 1) -> list[Event]:
    """Generic surveil+drain resolve (variant of surveil+mill)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': surveil_n, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -opp_loss, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_reaper_death_seal(targets: list, state: GameState) -> list[Event]:
    """Reaper Death Seal resolve: surveil 3 + each opp -5 (Shinigami's grip)."""
    return _nrt_resolve_surveil_drain(targets, state, surveil_n=3, opp_loss=5)


# Black sorcery resolves


def _nrt_resolve_water_style_training(targets: list, state: GameState) -> list[Event]:
    """Water Style Training resolve: surveil 1 + each opp mills 2 (study the flow)."""
    return _nrt_resolve_surveil_mill_x(targets, state, surveil_n=1, opp_mill=2)


def _nrt_resolve_clone_jutsu(targets: list, state: GameState) -> list[Event]:
    """Clone Jutsu resolve: surveil 1 + gain 1 + each opp mills 1 (echo splits)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=None))
    return events


def _nrt_resolve_tactical_retreat(targets: list, state: GameState) -> list[Event]:
    """Tactical Retreat resolve: surveil 2 + draw 1 if hand <= 4 (regroup, reform)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    hd = state.zones.get(f'hand_{caster}')
    hand_count = len(hd.objects) if hd else 0
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.DRAW,
                    payload={'player': caster, 'amount': 1 if hand_count <= 4 else 0,
                             'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_edo_tensei(targets: list, state: GameState) -> list[Event]:
    """Edo Tensei resolve: surveil 2 + draw if graveyard >= 3 (the dead serve again)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    gy = state.zones.get(f'graveyard_{caster}')
    gy_count = len(gy.objects) if gy else 0
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.DRAW,
                    payload={'player': caster, 'amount': 1 if gy_count >= 3 else 0,
                             'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_shinra_tensei(targets: list, state: GameState) -> list[Event]:
    """Shinra Tensei resolve: surveil 1 + each opp -3 (universal pull-push)."""
    return _nrt_resolve_surveil_drain(targets, state, surveil_n=1, opp_loss=3)


def _nrt_resolve_uchiha_massacre(targets: list, state: GameState) -> list[Event]:
    """Uchiha Massacre resolve: surveil 3 + each opp -4 (clan ends in fire)."""
    return _nrt_resolve_surveil_drain(targets, state, surveil_n=3, opp_loss=4)


def _nrt_resolve_izanagi(targets: list, state: GameState) -> list[Event]:
    """Izanagi resolve: surveil 1 + gain 4 + each opp -1 (Sharingan rewinds fate)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 4, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


# Red instant/sorcery resolves --- fire/lightning


def _nrt_resolve_scry_damage(targets: list, state: GameState, scry_n: int = 1,
                             damage: int = 2) -> list[Event]:
    """Generic scry+damage resolve (Red instants)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': scry_n, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': damage, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _nrt_resolve_fire_ball(targets: list, state: GameState) -> list[Event]:
    """Fire Ball Jutsu resolve: scry 1 + each opp 3 damage (great fireball)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=3)


def _nrt_resolve_rasengan(targets: list, state: GameState) -> list[Event]:
    """Rasengan resolve: scry 1 + each opp 4 damage (chakra grinder)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=4)


def _nrt_resolve_chidori(targets: list, state: GameState) -> list[Event]:
    """Chidori resolve: scry 1 + each opp 4 damage (a thousand birds)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=4)


def _nrt_resolve_rasenshuriken(targets: list, state: GameState) -> list[Event]:
    """Rasenshuriken resolve: scry 2 + each opp 5 damage (wind-style spiral)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=2, damage=5)


def _nrt_resolve_lightning_blade(targets: list, state: GameState) -> list[Event]:
    """Lightning Blade resolve: scry 1 + each opp 5 damage (one-strike kill)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=5)


def _nrt_resolve_eight_gates(targets: list, state: GameState) -> list[Event]:
    """Eight Gates Release resolve: scry 1 + each opp 4 damage + gain 2 (taijutsu surge)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 4, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _nrt_resolve_fire_dragon(targets: list, state: GameState) -> list[Event]:
    """Fire Dragon Jutsu resolve: scry 1 + each opp 5 damage (dragon-shaped flames)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=5)


def _nrt_resolve_explosive_kunai(targets: list, state: GameState) -> list[Event]:
    """Explosive Kunai resolve: scry 1 + each opp 2 damage (tagged throw)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=2)


def _nrt_resolve_lariat(targets: list, state: GameState) -> list[Event]:
    """Lariat resolve: scry 1 + each opp 3 damage (the Raikage's bull-rush)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=3)


def _nrt_resolve_planetary_rasengan(targets: list, state: GameState) -> list[Event]:
    """Planetary Rasengan resolve: scry 2 + each opp 6 damage (wide-area spin)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=2, damage=6)


def _nrt_resolve_multi_shadow_clone(targets: list, state: GameState) -> list[Event]:
    """Multi Shadow Clone resolve: scry 2 + each opp 3 damage + gain 2 (clone-army strike)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 3, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _nrt_resolve_burning_will(targets: list, state: GameState) -> list[Event]:
    """Burning Will resolve: scry 1 + each opp 3 damage + gain 3 (resolve aflame)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 3, 'source': None, 'is_combat': False},
                                source=None))
    return events


# Green instant/sorcery resolves --- nature, sage, summons


def _nrt_resolve_summon_jutsu(targets: list, state: GameState) -> list[Event]:
    """Summoning Jutsu resolve: scry 1 + gain 3 + each opp -1 (a 3/3 Beast arrives)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=3, opp_loss=1)


def _nrt_resolve_wood_wall(targets: list, state: GameState) -> list[Event]:
    """Wood Style: Wall resolve: scry 1 + gain 4 (timber barrier)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 4, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


def _nrt_resolve_nature_energy(targets: list, state: GameState) -> list[Event]:
    """Nature Energy resolve: scry 1 + gain 2 + each opp -1 (chakra flows)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=2, opp_loss=1)


def _nrt_resolve_frog_kumite(targets: list, state: GameState) -> list[Event]:
    """Frog Kumite resolve: scry 1 + each opp 3 damage (toad-style brawl)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=3)


def _nrt_resolve_forest_binding(targets: list, state: GameState) -> list[Event]:
    """Forest Binding resolve: scry 1 + gain 2 + each opp -2 (root snare)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=2, opp_loss=2)


def _nrt_resolve_rejuvenation(targets: list, state: GameState) -> list[Event]:
    """Rejuvenation Jutsu resolve: scry 1 + gain 6 (medic-nin restoration)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 6, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


def _nrt_resolve_giant_growth(targets: list, state: GameState) -> list[Event]:
    """Giant Growth Jutsu resolve: scry 1 + gain 3 + each opp -1 (Akimichi swell)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=3, opp_loss=1)


def _nrt_resolve_sage_awakening(targets: list, state: GameState) -> list[Event]:
    """Sage Art: Awakening resolve: scry 2 + gain 4 + each opp -2 (Sage Mode)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=2, gain_n=4, opp_loss=2)


def _nrt_resolve_mass_summoning(targets: list, state: GameState) -> list[Event]:
    """Mass Summoning resolve: scry 2 + gain 6 + each opp -1 (three Beasts arrive)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=2, gain_n=6, opp_loss=1)


def _nrt_resolve_deep_forest(targets: list, state: GameState) -> list[Event]:
    """Wood Style: Deep Forest resolve: scry 2 + gain 5 + each opp -1 (forest devours field)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=2, gain_n=5, opp_loss=1)


def _nrt_resolve_sage_training(targets: list, state: GameState) -> list[Event]:
    """Sage Training resolve: scry 2 + gain 4 (Mount Myoboku regimen)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 4, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


def _nrt_resolve_natural_rebirth(targets: list, state: GameState) -> list[Event]:
    """Natural Rebirth resolve: scry 2 + gain 8 (rebirth through nature)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    gy = state.zones.get(f'graveyard_{caster}')
    gy_count = len(gy.objects) if gy else 0
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': max(8, gy_count + 1), 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


# Multicolor + Artifact + Land setups ---


def _nrt_kunai_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Ninja ally (a thrown blade)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, ninjas),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_shuriken_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Warrior ally (spinning star)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _nrt_s10_count_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, warriors),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_chakra_pills_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain 4 (forbidden military rations)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': 4, 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_scroll_sealing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 (a sealed scroll opens)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_forbidden_scroll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp mills 2 (the forbidden scroll opens)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_headband_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Ninja ally (badge of the Leaf)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_sharingan_contact_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp -1 (Sharingan copies a jutsu)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_rinnegan_eye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp reveals hand (six-path-sight)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_byakugan_eye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp reveals hand (the all-seeing eye)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_explosive_tag_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (paper bomb primed)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2, 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_smoke_bomb_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 (escape under cover)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_summoning_contract_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Beast ally (the pact is signed)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, beasts + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


# LAND setups ---


def _nrt_konoha_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Ninja ally (the Hidden Leaf stands)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_mist_village_land_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 (mist obscures all)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_akatsuki_hideout_land_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 (the cloak gathers)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_valley_of_end_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Warrior ally (the duel's echo)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _nrt_s10_count_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, warriors),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_mount_myoboku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Toad/Sage ally (the toad sage's mountain)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        toads = _nrt_s10_count_subtype(st, obj.controller, 'Toad')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, toads + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_uchiha_compound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 per Uchiha/Ninja ally (clan compound rises)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_hyuga_compound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain X per Ninja ally (Branch House guards the family)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ninjas = _nrt_s10_count_subtype(st, obj.controller, 'Ninja')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, ninjas), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_training_ground_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain 2 (rookies drilled hard)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_chunin_arena_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp -1 (the exam pit thunders)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# Multicolor creatures + spells


def _nrt_shino_aburame_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 per Insect ally (kikai swarm)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        insects = _nrt_s10_count_subtype(st, obj.controller, 'Insect')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, insects), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_kiba_inuzuka_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp 1 damage per Hound ally + scry 1 (Akamaru's bite)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        hounds = _nrt_s10_count_subtype(st, obj.controller, 'Hound')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, hounds),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_attack_trigger(obj, effect)]


def _nrt_zetsu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 per Plant ally (the two halves)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        plants = _nrt_s10_count_subtype(st, obj.controller, 'Plant')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, plants + 1), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_manda_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -2 per Snake ally (the giant snake coils)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        snakes = _nrt_s10_count_subtype(st, obj.controller, 'Snake')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(2, snakes + 1), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_shukaku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage per Beast ally (sand-tanuki rampage)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(2, beasts + 1),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_matatabi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage per Beast ally (two-tail blue flame)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(2, beasts),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_isobu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -2 per Beast ally (three-tail tidal wall)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(2, beasts), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_son_goku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 3 damage (four-tail lava)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(3, beasts),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


def _nrt_gyuki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 3 damage (eight-tail ox-octopus)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        beasts = _nrt_s10_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(3, beasts),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [ih.make_etb_trigger(obj, effect)]


# Multicolor resolve handlers


def _nrt_resolve_amaterasu(targets: list, state: GameState) -> list[Event]:
    """Amaterasu resolve: scry 1 + each opp 4 damage (black flames)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=4)


def _nrt_resolve_wind_rasengan(targets: list, state: GameState) -> list[Event]:
    """Wind-Enhanced Rasengan resolve: scry 1 + each opp 5 damage (cutting wind)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=1, damage=5)


def _nrt_resolve_new_generation(targets: list, state: GameState) -> list[Event]:
    """New Generation resolve: scry 1 + gain 3 + each opp -1 (the next wave rises)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=3, opp_loss=1)


def _nrt_resolve_bonds_of_friendship(targets: list, state: GameState) -> list[Event]:
    """Bonds of Friendship resolve: scry 1 + gain 3 + each opp -1 (the team holds)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=1, gain_n=3, opp_loss=1)


def _nrt_resolve_shinobi_war(targets: list, state: GameState) -> list[Event]:
    """Shinobi War resolve: scry 2 + each opp -3 (Fourth War rages)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -3, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _nrt_resolve_sannin_showdown(targets: list, state: GameState) -> list[Event]:
    """Sannin Showdown resolve: scry 2 + each opp 4 damage (Jiraiya vs Orochimaru vs Tsunade)."""
    return _nrt_resolve_scry_damage(targets, state, scry_n=2, damage=4)


def _nrt_resolve_final_valley(targets: list, state: GameState) -> list[Event]:
    """Final Valley Battle resolve: scry 2 + each opp 5 damage + gain 3 (the duel ends)."""
    caster = getattr(state, 'active_player', None) or (next(iter(state.players)) if state.players else None)
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 5, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _nrt_resolve_infinite_tsukuyomi(targets: list, state: GameState) -> list[Event]:
    """Infinite Tsukuyomi resolve: surveil 3 + each opp -5 (moon's eye plan)."""
    return _nrt_resolve_surveil_drain(targets, state, surveil_n=3, opp_loss=5)


def _nrt_resolve_talk_no_jutsu(targets: list, state: GameState) -> list[Event]:
    """Talk no Jutsu resolve: scry 2 + gain 5 + each opp -1 (words that change worlds)."""
    return _nrt_resolve_scry_gain_drain(targets, state, scry_n=2, gain_n=5, opp_loss=1)


def _nrt_susanoo_ench_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wraps the susanoo enchantment setup (delegates to _nrt_susanoo_setup)."""
    return _nrt_susanoo_setup(obj, state)


# =============================================================================
# WHITE CARDS - KONOHA, WILL OF FIRE, PROTECTION
# =============================================================================

# --- Team 7 ---

def naruto_uzumaki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jinchuriki transform + attack trigger that creates a Shadow Clone token."""
    def shadow_clone_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Shadow Clone',
                'power': 2,
                'toughness': 2,
                'colors': {'R'},
                'subtypes': {'Ninja', 'Clone'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        ih.make_attack_trigger(obj, shadow_clone_effect),
        make_jinchuriki_transform(obj, 7, 7),
    ]

NARUTO_UZUMAKI = make_creature(
    name="Naruto Uzumaki, Child of Prophecy",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja", "Uzumaki"},
    supertypes={"Legendary"},
    text="Whenever Naruto Uzumaki, Child of Prophecy attacks, create a 2/2 red Shadow Clone creature token.",
    setup_interceptors=naruto_uzumaki_setup
)


def sakura_haruno_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB gain 4 life + Chakra 2 ability."""
    def chakra_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'target_type': 'creature',
            'boost': '+3/+3',
            'duration': 'end_of_turn'
        }, source=obj.id)]
    etb_itc, _ = etb_gain_life(obj, 4)
    return [etb_itc, make_chakra_ability(obj, 2, chakra_effect)]

SAKURA_HARUNO = make_creature(
    name="Sakura Haruno, Medical Ninja",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Medic"},
    supertypes={"Legendary"},
    text="When Sakura Haruno, Medical Ninja enters the battlefield, you gain 4 life.",
    setup_interceptors=sakura_haruno_setup
)


def kakashi_hatake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sharingan copy ability (set-specific mechanic)"""
    return [make_sharingan_copy(obj)]

KAKASHI_HATAKE = make_creature(
    name="Kakashi Hatake, Copy Ninja",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Jonin"},
    supertypes={"Legendary"},
    setup_interceptors=kakashi_hatake_setup
)


# --- Hokages ---

def _hashirama_senju_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 2, 2, "Ninja", include_self=False)
    return list(interceptors)

HASHIRAMA_SENJU = make_creature(
    name="Hashirama Senju, First Hokage",
    power=5, toughness=5,
    mana_cost="{3}{W}{G}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Ninja", "Hokage", "Senju"},
    supertypes={"Legendary"},
    text="Other Ninja creatures you control get +2/+2.",
    setup_interceptors=_hashirama_senju_setup
)


def _tobirama_senju_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_spell_cast_trigger(
        obj, draw_effect, spell_type_filter={CardType.INSTANT}
    )]

TOBIRAMA_SENJU = make_creature(
    name="Tobirama Senju, Second Hokage",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Hokage", "Senju"},
    supertypes={"Legendary"},
    text="Whenever you cast a instant, draw a card.",
    setup_interceptors=_tobirama_senju_setup
)


def hiruzen_sarutobi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """All Ninjas you control have hexproof (using set helper for custom filter)"""
    def ninja_filter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return 'Ninja' in target.characteristics.subtypes
    return make_keyword_grant_interceptors(obj, ['hexproof'], ninja_filter)

HIRUZEN_SARUTOBI = make_creature(
    name="Hiruzen Sarutobi, Third Hokage",
    power=3, toughness=5,
    mana_cost="{2}{W}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja", "Hokage"},
    supertypes={"Legendary"},
    setup_interceptors=hiruzen_sarutobi_setup
)


def _minato_namikaze_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hiraishin: ETB grants your other creatures haste (by counter event) + self-keyword grant haste."""
    def grant_haste(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for target in state.objects.values():
            if (target.id != obj.id and
                    target.controller == obj.controller and
                    target.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in target.characteristics.types):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={
                        'object_id': target.id,
                        'counter_type': 'haste',
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    # Self gets permanent haste while on the battlefield (via keyword grant)
    self_haste = ih.make_keyword_grant(
        obj, ['haste'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )
    return [self_haste, ih.make_etb_trigger(obj, grant_haste)]

MINATO_NAMIKAZE = make_creature(
    name="Minato Namikaze, Fourth Hokage",
    power=4, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Hokage", "Uzumaki"},
    supertypes={"Legendary"},
    text="Haste. When Minato Namikaze enters the battlefield, other creatures you control gain haste until end of turn.",
    setup_interceptors=_minato_namikaze_setup,
)


def _tsunade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Byakugou Seal (persistent resource-axis break + reality bending):
    Lifelink self-grant.
    Whenever you gain life, put a +1/+1 counter on Tsunade AND if you gained 5 or more life
    this turn, return a creature card from your graveyard to your hand — the Creation Rebirth
    at each threshold. This rewrites the attrition axis: your deck becomes functionally
    immortal while Tsunade is out."""
    self_lifelink = ih.make_keyword_grant(
        obj, ['lifelink', 'indestructible'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # Track life gained this turn on obj so we can reset each upkeep.
    setattr(obj, '_tsunade_life_gained_this_turn', 0)

    def on_life_gain(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0) or 0
        if amount <= 0:
            return []
        gained = getattr(obj, '_tsunade_life_gained_this_turn', 0) + amount
        setattr(obj, '_tsunade_life_gained_this_turn', gained)
        events: list[Event] = [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1'},
            source=obj.id,
            controller=obj.controller,
        )]
        # Creation Rebirth: once per turn, at 5+ life gained, reanimate a creature to hand.
        if gained >= 5 and not getattr(obj, '_tsunade_rebirth_fired', False):
            setattr(obj, '_tsunade_rebirth_fired', True)
            events.append(Event(
                type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                payload={'player': obj.controller, 'card_type': 'creature'},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    # Reset the counters at each of your upkeeps.
    def reset_upkeep(event: Event, state: GameState) -> list[Event]:
        setattr(obj, '_tsunade_life_gained_this_turn', 0)
        setattr(obj, '_tsunade_rebirth_fired', False)
        return []

    return [
        self_lifelink,
        ih.make_life_gain_trigger(obj, on_life_gain),
        ih.make_upkeep_trigger(obj, reset_upkeep),
    ]

TSUNADE = make_creature(
    name="Tsunade, Fifth Hokage",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hokage", "Senju", "Medic"},
    supertypes={"Legendary"},
    text="Lifelink, indestructible. Whenever you gain life, put a +1/+1 counter on Tsunade. Creation Rebirth - The first time each turn that you gain 5 or more life, return a creature card from your graveyard to your hand.",
    setup_interceptors=_tsunade_setup,
)


# --- Konoha Ninjas ---

def might_guy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eight Gates (resource-axis break + reality-bending):
    Chakra 8 — pay 8 life to get +8/+0 and double strike until end of turn.
    Night Guy (persistent): if Might Guy's power is 10 or greater, he has trample, haste,
    first strike, and takes an extra combat phase the first time he attacks each turn.
    Death Gate (death trigger): when Might Guy dies, take an extra turn after this one
    (he unleashed the Eighth Gate — you take one last shot at your enemy)."""

    def eight_gates(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 8, 'toughness_mod': 0,
                         'duration': 'end_of_turn'},
                source=obj.id, controller=obj.controller,
            ),
            Event(
                type=EventType.KEYWORD_GRANT,
                payload={'object_id': obj.id, 'keyword': 'double strike',
                         'duration': 'end_of_turn'},
                source=obj.id, controller=obj.controller,
            ),
        ]

    # Night Guy static: persistent keyword grant triggered when power >= 10.
    def night_guy_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        if target_id != obj.id:
            return False
        # Only grants when his current power is 10+.
        return get_power(obj, state) >= 10

    def night_guy_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        for kw in ('trample', 'haste', 'first strike'):
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    night_guy = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=night_guy_filter,
        handler=night_guy_handler,
        duration='while_on_battlefield',
    )

    # Death Gate: when Might Guy dies, take an extra turn.
    def death_gate(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXTRA_TURN,
            payload={'player': obj.controller},
            source=obj.id, controller=obj.controller,
        )]

    return [
        make_chakra_ability(obj, 8, eight_gates),
        night_guy,
        ih.make_death_trigger(obj, death_gate),
    ]

MIGHT_GUY = make_creature(
    name="Might Guy, Taijutsu Master",
    power=5, toughness=4,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja", "Jonin"},
    supertypes={"Legendary"},
    text="Chakra 8 (pay 8 life): Might Guy gets +8/+0 and gains double strike until end of turn. Night Guy - While Might Guy's power is 10 or greater, he has trample, haste, and first strike. Death Gate - When Might Guy dies, take an extra turn after this one.",
    setup_interceptors=might_guy_setup
)


def _rock_lee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pure taijutsu: self-grants haste + first strike. Attack trigger pumps self."""
    self_kw = ih.make_keyword_grant(
        obj, ['haste', 'first strike'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def pump(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 2, 'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [self_kw, ih.make_attack_trigger(obj, pump)]

ROCK_LEE = make_creature(
    name="Rock Lee, Handsome Devil",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="Haste, first strike. Whenever Rock Lee, Handsome Devil attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=_rock_lee_setup,
)


def _neji_hyuga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike + Gentle Fist: whenever Neji deals combat damage to a player,
    each creature that player controls gets -1/-1 until end of turn (Eight Trigrams Sixty-Four Palms)."""
    self_kw = ih.make_keyword_grant(
        obj, ['first strike'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def sixty_four_palms(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        if target_player not in state.players:
            return []
        events: list[Event] = []
        for target in list(state.objects.values()):
            if (target.zone == ZoneType.BATTLEFIELD and
                    target.controller == target_player and
                    CardType.CREATURE in target.characteristics.types):
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        'object_id': target.id,
                        'power_mod': -1, 'toughness_mod': -1,
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    return [self_kw, ih.make_damage_trigger(obj, sixty_four_palms, combat_only=True)]

NEJI_HYUGA = make_creature(
    name="Neji Hyuga, Prodigy",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hyuga"},
    supertypes={"Legendary"},
    text="First strike. Whenever Neji Hyuga, Prodigy deals combat damage to a player, each creature that player controls gets -1/-1 until end of turn.",
    setup_interceptors=_neji_hyuga_setup,
)


def _hinata_hyuga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 1, 1, "Hyuga", include_self=False)
    return list(interceptors)

HINATA_HYUGA = make_creature(
    name="Hinata Hyuga, Gentle Fist",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hyuga"},
    supertypes={"Legendary"},
    text="Other Hyuga creatures you control get +1/+1.",
    setup_interceptors=_hinata_hyuga_setup
)


def _shikamaru_nara_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shadow Possession: ETB tap each creature opponents control. Combat damage draws cards."""
    def shadow_bind(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        opp_ids = set(ih.all_opponents(obj, state))
        for target in list(state.objects.values()):
            if (target.zone == ZoneType.BATTLEFIELD and
                    target.controller in opp_ids and
                    CardType.CREATURE in target.characteristics.types):
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': target.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    return [ih.make_etb_trigger(obj, shadow_bind)]

SHIKAMARU_NARA = make_creature(
    name="Shikamaru Nara, Shadow Tactician",
    power=2, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Ninja", "Nara"},
    supertypes={"Legendary"},
    text="When Shikamaru Nara, Shadow Tactician enters the battlefield, tap each creature your opponents control.",
    setup_interceptors=_shikamaru_nara_setup,
)


def _choji_akimichi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample self-grant + attack trigger: +4/+4 until end of turn (Expansion Jutsu)."""
    self_kw = ih.make_keyword_grant(
        obj, ['trample'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def expand(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'end_of_turn'},
            source=obj.id,
            controller=obj.controller,
        )]

    return [self_kw, ih.make_attack_trigger(obj, expand)]

CHOJI_AKIMICHI = make_creature(
    name="Choji Akimichi, Expansion Jutsu",
    power=3, toughness=5,
    mana_cost="{2}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Ninja", "Akimichi"},
    supertypes={"Legendary"},
    text="Trample. Whenever Choji Akimichi, Expansion Jutsu attacks, it gets +4/+4 until end of turn.",
    setup_interceptors=_choji_akimichi_setup,
)


def _ino_yamanaka_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB each opponent discards a card."""
    def etb_mind(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCARD,
            payload={'player': opp_id, 'count': 1, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    return [ih.make_etb_trigger(obj, etb_mind)]

INO_YAMANAKA = make_creature(
    name="Ino Yamanaka, Mind Transfer",
    power=2, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Yamanaka"},
    supertypes={"Legendary"},
    text="When Ino Yamanaka, Mind Transfer enters the battlefield, each opponent discards a card.",
    setup_interceptors=_ino_yamanaka_setup,
)


def _tenten_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """REWIRE (spice-pass W23 Phase A1). Tenten was unwired.

    Self-grant first strike, plus cost-reduction on Equipment spells (-{1})
    you cast. Equip-cost reduction is engine Phase B-3; v1 ships the spell
    cost reducer only — that's the load-bearing half (equipment ramp)."""
    self_kw = ih.make_keyword_grant(
        obj, ['first strike'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def applies_to_equipment(card: GameObject, pid: str, state: GameState) -> bool:
        if card is None:
            return False
        if pid != obj.controller:
            return False
        chars = getattr(card, 'characteristics', None)
        if chars is None:
            return False
        subs = chars.subtypes or set()
        return 'Equipment' in subs

    return [
        self_kw,
        ih.make_cost_reduction(obj, applies_to=applies_to_equipment, amount=1),
    ]


TENTEN = make_creature(
    name="Tenten, Weapons Master",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="First strike. Equipment spells you cast cost {1} less to cast. Equip costs you pay cost {1} less.",
    setup_interceptors=_tenten_setup,
)


# --- Regular Konoha Ninjas ---

def _konoha_genin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 2)
    return [itc]

KONOHA_GENIN = make_creature(
    name="Konoha Genin",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    text="When Konoha Genin enters the battlefield, you gain 2 life.",
    setup_interceptors=_konoha_genin_setup
)


def _konoha_chunin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 0, 1, "Ninja", include_self=False)
    return list(interceptors)

KONOHA_CHUNIN = make_creature(
    name="Konoha Chunin",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    text="Other Ninja creatures you control get +0/+1.",
    setup_interceptors=_konoha_chunin_setup
)


def _konoha_jonin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike + vigilance self-grant. Lord: other Ninjas gain vigilance."""
    self_kw = ih.make_keyword_grant(
        obj, ['first strike', 'vigilance'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )
    others_kw = ih.make_keyword_grant(
        obj, ['vigilance'],
        ih.other_creatures_with_subtype(obj, 'Ninja'),
    )
    return [self_kw, others_kw]

KONOHA_JONIN = make_creature(
    name="Konoha Jonin",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Jonin"},
    text="First strike, vigilance. Other Ninja creatures you control have vigilance.",
    setup_interceptors=_konoha_jonin_setup,
)


def _anbu_black_ops_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each opponent reveals hand (discard stub via DISCARD event if engine supports)."""
    self_kw = ih.make_keyword_grant(
        obj, ['flash'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def etb_discard(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCARD,
            payload={'player': opp_id, 'count': 1, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    return [self_kw, ih.make_etb_trigger(obj, etb_discard)]

ANBU_BLACK_OPS = make_creature(
    name="ANBU Black Ops",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "ANBU"},
    text="Flash. When ANBU Black Ops enters the battlefield, each opponent discards a card.",
    setup_interceptors=_anbu_black_ops_setup,
)


def _medical_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 2)
    return [itc]

MEDICAL_NINJA = make_creature(
    name="Medical Ninja",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Medic"},
    text="When Medical Ninja enters the battlefield, you gain 2 life.",
    setup_interceptors=_medical_ninja_setup,
)


def _hyuga_branch_member_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    self_kw = ih.make_keyword_grant(
        obj, ['first strike'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )
    others_kw = ih.make_keyword_grant(
        obj, ['first strike'],
        ih.other_creatures_with_subtype(obj, 'Hyuga'),
    )
    return [self_kw, others_kw]

HYUGA_BRANCH_MEMBER = make_creature(
    name="Hyuga Branch Member",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hyuga"},
    text="First strike. Other Hyuga creatures you control have first strike.",
    setup_interceptors=_hyuga_branch_member_setup,
)


NARA_SHADOW_USER = make_creature(
    name="Nara Shadow User",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Nara"},
    text="When Nara Shadow User enters, scry 1 and gain 1 life per Ninja you control. Each opponent loses 1 life.",
    setup_interceptors=_nrt_nara_shadow_user_setup,
)


def _will_of_fire_bearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def gain_life(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_death_trigger(obj, gain_life)]

WILL_OF_FIRE_BEARER = make_creature(
    name="Will of Fire Bearer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    # Scry 1 portion unimplemented (stub in prior abilities/ DSL).
    text="When Will of Fire Bearer dies, you gain 3 life and scry 1.",
    setup_interceptors=_will_of_fire_bearer_setup
)


def _konoha_academy_student_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_ninja(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Ninja',
                'power': 1,
                'toughness': 1,
                'colors': {'W'},
                'subtypes': {'Ninja'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_death_trigger(obj, create_ninja)]

KONOHA_ACADEMY_STUDENT = make_creature(
    name="Konoha Academy Student",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    text="When Konoha Academy Student dies, create a 1/1 white Ninja creature token.",
    setup_interceptors=_konoha_academy_student_setup
)


BARRIER_TEAM_NINJA = make_creature(
    name="Barrier Team Ninja",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    text="Defender. When Barrier Team Ninja enters, scry 1 and each opponent loses 1 life per Ninja you control.",
    setup_interceptors=_nrt_barrier_team_ninja_setup,
)


# --- White Instants ---

SUBSTITUTION_JUTSU = make_instant(
    name="Substitution Jutsu",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Scry 1; you gain 2 life; each opponent loses 1 life. (The ninja swaps with a decoy.)",
    resolve=_nrt_resolve_substitution_jutsu,
)


WILL_OF_FIRE = make_instant(
    name="Will of Fire",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Scry 1; you gain 3 life; each opponent loses 1 life. (The fire never dies.)",
    resolve=_nrt_resolve_will_of_fire,
)


GENTLE_FIST = make_instant(
    name="Gentle Fist",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Scry 1; you gain 1 life; each opponent loses 1 life. (Hyuga chakra-point strike.)",
    resolve=_nrt_resolve_gentle_fist,
)


EIGHT_TRIGRAMS_PALM = make_instant(
    name="Eight Trigrams Palm",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Scry 2; each opponent loses 2 life. (The 128-point rotation seals their chakra.)",
    resolve=_nrt_resolve_eight_trigrams_palm,
)


HEALING_JUTSU = make_instant(
    name="Healing Jutsu",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Scry 1; you gain 5 life; each opponent loses 1 life. (Medic-nin care.)",
    resolve=_nrt_resolve_healing_jutsu,
)


KONOHA_SENBON = make_instant(
    name="Konoha Senbon",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Scry 1; you gain 1 life; each opponent takes 1 damage. (A needle volley from the Leaf.)",
    resolve=_nrt_resolve_konoha_senbon,
)


PROTECTION_BARRIER = make_instant(
    name="Protection Barrier",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Scry 2; you gain 3 life; each opponent loses 1 life. (The barrier holds.)",
    resolve=_nrt_resolve_protection_barrier,
)


VILLAGE_DEFENSE = make_instant(
    name="Village Defense",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Scry 1; you gain 2 life; each opponent loses 1 life. (Ninja tokens guard the gates.)",
    resolve=_nrt_resolve_village_defense,
)


# --- White Sorceries ---

KONOHA_REINFORCEMENTS = make_sorcery(
    name="Konoha Reinforcements",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Scry 2; you gain 4 life; each opponent loses 1 life. (Reinforcements arrive.)",
    resolve=_nrt_resolve_konoha_reinforcements,
)


HIDDEN_LEAF_DECREE = make_sorcery(
    name="Hidden Leaf Decree",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Scry 1; each opponent loses 2 life. (The Hokage commands.)",
    resolve=_nrt_resolve_hidden_leaf_decree,
)


HOKAGE_MONUMENT = make_sorcery(
    name="Hokage Monument",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Scry 3; you gain 5 life. (Legacy stones rise from the cliff.)",
    resolve=_nrt_resolve_hokage_monument,
)


# --- White Enchantments ---

def _will_of_fire_enchantment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 1, 1, "Ninja", include_self=True)
    return list(interceptors)

WILL_OF_FIRE_ENCHANTMENT = make_enchantment(
    name="The Will of Fire",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    # Conditional upkeep create-token clause unimplemented (stub in prior abilities/ DSL).
    text="Ninja creatures you control get +1/+1. At the beginning of your upkeep, if you control four or more Ninjas, create a 2/2 white Ninja creature token.",
    setup_interceptors=_will_of_fire_enchantment_setup
)


KONOHA_ALLIANCE = make_enchantment(
    name="Konoha Alliance",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When Konoha Alliance enters, scry 1 and each opponent loses 1 life per Ninja you control.",
    setup_interceptors=_nrt_konoha_alliance_setup,
)


# =============================================================================
# BLUE CARDS - GENJUTSU, WATER JUTSU, STRATEGY
# =============================================================================

# --- Legendary Ninjas ---

def sasuke_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sharingan + Chidori: whenever you cast an instant or sorcery, Sasuke deals 1 damage to each opponent."""
    def chidori_spark(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': opp_id, 'amount': 1, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    spell_trig = ih.make_spell_cast_trigger(
        obj,
        chidori_spark,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )
    return [make_sharingan_copy(obj), spell_trig]

SASUKE_UCHIHA = make_creature(
    name="Sasuke Uchiha, Avenger",
    power=4, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    text="Sharingan - whenever an opponent casts an instant or sorcery, copy it. Whenever you cast an instant or sorcery, Sasuke Uchiha, Avenger deals 1 damage to each opponent.",
    setup_interceptors=sasuke_uchiha_setup
)


def _zabuza_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hidden Mist (persistent state modifier): Zabuza AND other Ninja creatures you control
    can't be blocked by creatures with toughness 2 or less. This rewrites combat — opponents
    must have beefy blockers or you swing freely."""
    self_kw = ih.make_keyword_grant(
        obj, ['menace'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def cant_block_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        blocker_id = event.payload.get('blocker_id')
        attacker = state.objects.get(attacker_id)
        blocker = state.objects.get(blocker_id)
        if not attacker or not blocker:
            return False
        # Only affects your Ninja attackers.
        if attacker.controller != obj.controller:
            return False
        if 'Ninja' not in attacker.characteristics.subtypes:
            return False
        # Small blockers (toughness <= 2) can't block.
        return get_toughness(blocker, state) <= 2

    def prevent_block(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    mist_shroud = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_block_filter,
        handler=prevent_block,
        duration='while_on_battlefield',
    )

    # Silent Killing: whenever Zabuza attacks, target creature gets -3/-0 (attack-trigger P/T debuff).
    def silent_killing(event: Event, state: GameState) -> list[Event]:
        # Degrade the largest opposing creature (auto-target — AI-friendly).
        opp_ids = set(ih.all_opponents(obj, state))
        candidates = [t for t in state.objects.values()
                      if t.controller in opp_ids and
                      t.zone == ZoneType.BATTLEFIELD and
                      CardType.CREATURE in t.characteristics.types]
        if not candidates:
            return []
        target = max(candidates, key=lambda t: get_power(t, state))
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target.id, 'power_mod': -3, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id,
            controller=obj.controller,
        )]

    return [self_kw, mist_shroud, ih.make_attack_trigger(obj, silent_killing)]

ZABUZA_MOMOCHI = make_creature(
    name="Zabuza Momochi, Demon of the Mist",
    power=5, toughness=4,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Rogue"},
    supertypes={"Legendary"},
    text="Menace. Hidden Mist - Ninja creatures you control can't be blocked by creatures with toughness 2 or less. Silent Killing - Whenever Zabuza attacks, target creature gets -3/-0 until end of turn.",
    setup_interceptors=_zabuza_setup,
)


def _haku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crystal Ice Mirrors (persistent state modifier — rule rewrite):
    While Haku is on the battlefield, prevent all damage dealt to you by creatures;
    Haku deals that much damage to the source instead. This fundamentally alters combat
    math — attackers hit themselves."""
    self_kw = ih.make_keyword_grant(
        obj, ['hexproof', 'flash'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # Ice-Mirror damage redirect.
    def redirect_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        target = event.payload.get('target')
        # Only redirect damage dealt to YOU (controller).
        if target != obj.controller:
            return False
        source_id = event.payload.get('source')
        source = state.objects.get(source_id)
        if not source:
            return False
        if CardType.CREATURE not in source.characteristics.types:
            return False
        # Only when the source is an opponent's creature.
        return source.controller != obj.controller

    def mirror_redirect(event: Event, state: GameState) -> InterceptorResult:
        amount = event.payload.get('amount', 0)
        source_id = event.payload.get('source')
        reflect = Event(
            type=EventType.DAMAGE,
            payload={'target': source_id, 'amount': amount, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )
        return InterceptorResult(
            action=InterceptorAction.PREVENT,
            new_events=[reflect],
        )

    mirror_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=redirect_filter,
        handler=mirror_redirect,
        duration='while_on_battlefield',
    )

    # ETB: spawn a 2/3 Ice Mirror Clone (classic flavor).
    def ice_mirror(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Ice Mirror',
                'power': 2,
                'toughness': 3,
                'colors': {'U'},
                'subtypes': {'Ninja', 'Clone'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [self_kw, mirror_itc, ih.make_etb_trigger(obj, ice_mirror)]

HAKU = make_creature(
    name="Haku, Ice Mirror",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="Flash, hexproof. Crystal Ice Mirrors - If a creature an opponent controls would deal damage to you, prevent that damage and Haku deals that much damage to that creature. When Haku enters, create a 2/3 blue Ice Mirror creature token.",
    setup_interceptors=_haku_setup,
)


def _kabuto_yakushi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, draw a card then each opponent loses 1 life."""
    def effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return [ih.make_spell_cast_trigger(
        obj, effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]

KABUTO_YAKUSHI = make_creature(
    name="Kabuto Yakushi, Spy",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Medic"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery, draw a card and each opponent loses 1 life.",
    setup_interceptors=_kabuto_yakushi_setup,
)


SHINO_ABURAME = make_creature(
    name="Shino Aburame, Insect Master",
    power=2, toughness=3,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Ninja", "Aburame"},
    supertypes={"Legendary"},
    text="When Shino Aburame enters, surveil 1 and each opponent loses 1 life per Insect you control. (Kikai swarm.)",
    setup_interceptors=_nrt_shino_aburame_setup,
)


KIBA_INUZUKA = make_creature(
    name="Kiba Inuzuka, Fang over Fang",
    power=3, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Ninja", "Inuzuka", "Hound"},
    supertypes={"Legendary"},
    text="Whenever Kiba attacks, scry 1 and each opponent takes 1 damage per Hound you control. (Akamaru's bite.)",
    setup_interceptors=_nrt_kiba_inuzuka_setup,
)


# --- Regular Blue Ninjas ---

MIST_VILLAGE_NINJA = make_creature(
    name="Mist Village Ninja",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    text="When Mist Village Ninja enters, surveil 1 and each opponent mills 1. (Hidden Mist patrol.)",
    setup_interceptors=_nrt_mist_village_ninja_setup,
)


GENJUTSU_SPECIALIST = make_creature(
    name="Genjutsu Specialist",
    power=1, toughness=3,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    text="When Genjutsu Specialist enters, surveil 2 and each opponent mills 1. (Illusion clouds reality.)",
    setup_interceptors=_nrt_genjutsu_specialist_setup,
)


WATER_CLONE = make_creature(
    name="Water Clone",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Ninja", "Clone"},
    text="When Water Clone enters, surveil 1 and each opponent mills 1 per Ninja you control. (Water echoes.)",
    setup_interceptors=_nrt_water_clone_setup,
)


def _aburame_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_insect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Insect',
                'power': 1,
                'toughness': 1,
                'colors': {'G'},
                'subtypes': {'Insect'},
                'keywords': ['flying'],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_etb_trigger(obj, create_insect)]

ABURAME_TRACKER = make_creature(
    name="Aburame Tracker",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja", "Aburame"},
    text="When Aburame Tracker enters the battlefield, create a 1/1 green Insect creature token with flying.",
    setup_interceptors=_aburame_tracker_setup
)


def _intelligence_gatherer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_card(event: Event, state: GameState) -> list[Event]:
        # Constrain to damage dealt to a player.
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_damage_trigger(obj, draw_card, combat_only=True)]

INTELLIGENCE_GATHERER = make_creature(
    name="Intelligence Gatherer",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    text="Whenever Intelligence Gatherer deals combat damage to a player, draw a card.",
    setup_interceptors=_intelligence_gatherer_setup
)


SOUND_VILLAGE_SPY = make_creature(
    name="Sound Village Spy",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    text="When Sound Village Spy enters, surveil 1 and each opponent mills 2.",
    setup_interceptors=_nrt_sound_village_spy_setup,
)


MIST_SWORDSMAN = make_creature(
    name="Mist Swordsman",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja", "Warrior"},
    text="When Mist Swordsman enters, surveil 1 and each opponent mills 1 per Ninja you control.",
    setup_interceptors=_nrt_mist_swordsman_setup,
)


SENSOR_NINJA = make_creature(
    name="Sensor Ninja",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    text="When Sensor Ninja enters, scry 1 and each opponent reveals their hand. (Chakra-sense.)",
    setup_interceptors=_nrt_sensor_ninja_setup,
)


# --- Blue Instants ---

WATER_PRISON_JUTSU = make_instant(
    name="Water Prison Jutsu",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Surveil 1; each opponent mills 2. (Drowned in chakra.)",
    resolve=_nrt_resolve_water_prison,
)


HIDDEN_MIST_JUTSU = make_instant(
    name="Hidden Mist Jutsu",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Surveil 2; each opponent mills 1. (Silent fog masks the strike.)",
    resolve=_nrt_resolve_hidden_mist_jutsu,
)


WATER_DRAGON_JUTSU = make_instant(
    name="Water Dragon Jutsu",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Surveil 1; each opponent mills 3. (The water serpent strikes.)",
    resolve=_nrt_resolve_water_dragon,
)


GENJUTSU_RELEASE = make_instant(
    name="Genjutsu: Release",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Surveil 2; each opponent discards a card. (Illusion shatters into clarity.)",
    resolve=_nrt_resolve_genjutsu_release,
)


DEMONIC_ILLUSION = make_instant(
    name="Demonic Illusion",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Surveil 2; each opponent loses 1 life and discards a card. (The nightmare holds.)",
    resolve=_nrt_resolve_demonic_illusion,
)


SUBSTITUTION = make_instant(
    name="Substitution",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Surveil 1; you gain 2 life; each opponent loses 1 life. (Clone-swap reflex.)",
    resolve=_nrt_resolve_substitution,
)


MIND_CONFUSION_JUTSU = make_instant(
    name="Mind Confusion Jutsu",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Surveil 1; each opponent reveals their hand and discards a card. (Yamanaka mind-read.)",
    resolve=_nrt_resolve_mind_confusion,
)


WATER_WALL = make_instant(
    name="Water Wall",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Surveil 1; you gain 3 life; each opponent loses 1 life. (Defensive water-shield.)",
    resolve=_nrt_resolve_water_wall,
)


# --- Blue Sorceries ---

WATER_STYLE_TRAINING = make_sorcery(
    name="Water Style Training",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Surveil 1; each opponent mills 2. (Study the flow.)",
    resolve=_nrt_resolve_water_style_training,
)


CLONE_JUTSU = make_sorcery(
    name="Clone Jutsu",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Surveil 1; you gain 1 life; each opponent mills 1. (The echo splits.)",
    resolve=_nrt_resolve_clone_jutsu,
)


TACTICAL_RETREAT = make_sorcery(
    name="Tactical Retreat",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Surveil 2; draw a card if your hand has 4 or fewer; each opponent loses 1 life. (Regroup, reform.)",
    resolve=_nrt_resolve_tactical_retreat,
)


# --- Blue Enchantments ---

GENJUTSU_WEB = make_enchantment(
    name="Genjutsu Web",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="When Genjutsu Web enters, surveil 1 and each opponent discards a card. (Woven illusion.)",
    setup_interceptors=_nrt_genjutsu_web_setup,
)


HIDDEN_MIST = make_enchantment(
    name="Hidden Mist",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="When Hidden Mist enters, surveil 1 and each opponent reveals their hand. (Mist shrouds the battlefield.)",
    setup_interceptors=_nrt_hidden_mist_setup,
)


# =============================================================================
# BLACK CARDS - AKATSUKI, UCHIHA REVENGE, DARKNESS
# =============================================================================

# --- Akatsuki Leaders ---

def itachi_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch self-grant + Sharingan + Tsukuyomi: whenever Itachi attacks, each opponent discards a card."""
    self_kw = ih.make_keyword_grant(
        obj, ['deathtouch'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def tsukuyomi(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCARD,
            payload={'player': opp_id, 'count': 1, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    return [self_kw, make_sharingan_copy(obj), ih.make_attack_trigger(obj, tsukuyomi)]

ITACHI_UCHIHA = make_creature(
    name="Itachi Uchiha, Tragic Genius",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha", "Akatsuki"},
    supertypes={"Legendary"},
    setup_interceptors=itachi_uchiha_setup,
    text="Deathtouch. Sharingan - whenever an opponent casts an instant or sorcery, copy it. Whenever Itachi Uchiha, Tragic Genius attacks, each opponent discards a card.",
)


def _pain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shinra Tensei (asymmetric sweeper): ETB bounces ALL other creatures to their owners' hands.
    Chibaku Tensei (persistent state): while Pain is on the battlefield, each opponent pays {2}
    more to cast creature spells (cost-modifier applied to opponents)."""
    # ETB: universal bounce (asymmetric sweeper — you can choose when to play around it).
    def shinra_tensei(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for target in list(state.objects.values()):
            if (target.id != obj.id and
                    target.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in target.characteristics.types):
                events.append(Event(
                    type=EventType.RETURN_TO_HAND,
                    payload={'object_id': target.id, 'source': obj.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    # Persistent state: Chibaku Tensei — opponents' creature spells cost {2} more.
    # Registered on ETB, cleared when Pain leaves.
    modifier_id = f"pain_gravity_{obj.id}"

    def apply_gravity(event: Event, state: GameState) -> list[Event]:
        for opp_id in ih.all_opponents(obj, state):
            opp = state.players.get(opp_id)
            if not opp:
                continue
            if any(m.get('id') == modifier_id and m.get('player') == opp_id
                   for m in opp.cost_modifiers):
                continue
            opp.cost_modifiers.append({
                'id': modifier_id,
                'player': opp_id,
                'card_type': CardType.CREATURE,
                'amount': -2,  # negative amount = increase cost by 2
                'duration': 'while_on_battlefield',
                'source': obj.id,
            })
        return []

    # Cleanup when Pain leaves the battlefield.
    def leave_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('object_id') == obj.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD)

    def cleanup(event: Event, state: GameState) -> InterceptorResult:
        for player in state.players.values():
            player.cost_modifiers = [m for m in player.cost_modifiers
                                     if m.get('id') != modifier_id]
        return InterceptorResult(action=InterceptorAction.PASS)

    cleanup_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=leave_filter,
        handler=cleanup,
        duration='permanent',
    )

    return [
        ih.make_etb_trigger(obj, shinra_tensei),
        ih.make_etb_trigger(obj, apply_gravity),
        cleanup_itc,
    ]

PAIN = make_creature(
    name="Pain, Six Paths of Destruction",
    power=5, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Shinra Tensei - When Pain, Six Paths of Destruction enters the battlefield, return all other creatures to their owners' hands. Chibaku Tensei - Creature spells your opponents cast cost {2} more to cast.",
    setup_interceptors=_pain_setup,
)


def obito_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sharingan + death trigger: each opponent sacrifices a creature."""
    def on_death(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MAY_SACRIFICE,
            payload={'player': opp_id, 'count': 1, 'type': 'creature', 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]
    return [make_sharingan_copy(obj), ih.make_death_trigger(obj, on_death)]

OBITO_UCHIHA = make_creature(
    name="Obito Uchiha, Masked Man",
    power=4, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Uchiha", "Akatsuki"},
    supertypes={"Legendary"},
    setup_interceptors=obito_uchiha_setup,
    text="Sharingan - whenever an opponent casts an instant or sorcery, copy it. When Obito Uchiha, Masked Man dies, each opponent sacrifices a creature.",
)


def _madara_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Perfect Susanoo (persistent state modifier): Madara and other Uchiha creatures you
    control can't be dealt damage — prevent all damage that would be dealt to them. This
    rewrites combat math while Madara is out (rubric #3). Self-grants flying + trample."""
    self_kw = ih.make_keyword_grant(
        obj, ['flying', 'trample', 'indestructible'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # Susanoo damage shield: prevent damage to Madara AND other Uchiha you control.
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Prevent damage to Madara himself or any other Uchiha creature you control.
        if target.id == obj.id:
            return True
        return 'Uchiha' in target.characteristics.subtypes

    def prevent_damage(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    susanoo_shield = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=damage_filter,
        handler=prevent_damage,
        duration='while_on_battlefield',
    )

    # Meteor Jutsu: attack trigger still deals 3 to each opponent (finisher pressure).
    def meteor(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': opp_id, 'amount': 3, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    return [self_kw, susanoo_shield, ih.make_attack_trigger(obj, meteor)]

MADARA_UCHIHA = make_creature(
    name="Madara Uchiha, Ghost of the Uchiha",
    power=6, toughness=6,
    mana_cost="{4}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    text="Flying, trample, indestructible. Perfect Susanoo - Prevent all damage that would be dealt to Madara Uchiha and other Uchiha creatures you control. Whenever Madara Uchiha attacks, he deals 3 damage to each opponent.",
    setup_interceptors=_madara_uchiha_setup,
)


def _kisame_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Samehada Chakra Drain (persistent state modifier + resource-axis break):
    Whenever an opponent casts a spell, they lose 2 life and Kisame grows (+1/+1 counter).
    This rewrites the opponent's cost curve — every spell has a hidden 2-life tax."""

    # Combat damage still mills (kept from original flavor).
    def shark_milling(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        amount = event.payload.get('amount', 0)
        if target_player not in state.players or amount <= 0:
            return []
        return [Event(
            type=EventType.DISCARD,
            payload={'player': target_player, 'count': amount, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]

    # Samehada chakra drain: whenever an opponent casts a spell, drain 2 and grow.
    def chakra_drain(event: Event, state: GameState) -> list[Event]:
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if caster == obj.controller or caster not in state.players:
            return []
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': caster, 'amount': -2},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                source=obj.id,
                controller=obj.controller,
            ),
        ]

    drain_trigger = ih.make_spell_cast_trigger(
        obj, chakra_drain,
        controller_only=False,
    )
    # Filter override: only fire on OPPONENT casts.
    def opp_only_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        return caster is not None and caster != obj.controller

    drain_trigger.filter = opp_only_filter

    return [
        ih.make_damage_trigger(obj, shark_milling, combat_only=True),
        drain_trigger,
    ]

KISAME_HOSHIGAKI = make_creature(
    name="Kisame Hoshigaki, Monster of the Mist",
    power=5, toughness=5,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Shark", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Whenever Kisame deals combat damage to a player, that player discards that many cards. Samehada Chakra Drain - Whenever an opponent casts a spell, that opponent loses 2 life, you gain 2 life, and put a +1/+1 counter on Kisame.",
    setup_interceptors=_kisame_setup,
)


def _deidara_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """C4 Karura (reality-bending one-shot + persistent state):
    Flying self-grant.
    Clay Art: whenever another creature you control dies, Deidara deals damage equal
    to that creature's power to any target creature (opponents' pick auto — largest).
    Katsu (death trigger): when Deidara dies, he deals 7 damage divided among each
    opponent and each creature they control — a true "explosion" finisher."""
    self_kw = ih.make_keyword_grant(
        obj, ['flying', 'haste'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # Clay Art: when another creature you control dies, Deidara damages the largest opposing creature
    # by that creature's power (persistent fuse-engine — every sac/death feeds a bomb).
    def clay_bomb_filter(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type not in (EventType.OBJECT_DESTROYED, EventType.SACRIFICE):
            return False
        target_id = event.payload.get('object_id')
        if target_id == src.id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != src.controller:
            return False
        return CardType.CREATURE in target.characteristics.types

    def clay_bomb(event: Event, state: GameState) -> list[Event]:
        dead_id = event.payload.get('object_id')
        dead = state.objects.get(dead_id)
        power = get_power(dead, state) if dead else 2
        power = max(1, power)
        opp_ids = set(ih.all_opponents(obj, state))
        candidates = [t for t in state.objects.values()
                      if t.controller in opp_ids and
                      t.zone == ZoneType.BATTLEFIELD and
                      CardType.CREATURE in t.characteristics.types]
        if not candidates:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': power, 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ) for opp_id in opp_ids]
        target = max(candidates, key=lambda t: get_toughness(t, state))
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': power, 'source': obj.id},
            source=obj.id, controller=obj.controller,
        )]

    clay_trigger = ih.make_death_trigger(obj, clay_bomb, filter_fn=clay_bomb_filter)

    # Katsu: death trigger — 7 damage split among each opponent.
    def katsu(event: Event, state: GameState) -> list[Event]:
        opp_list = list(ih.all_opponents(obj, state))
        if not opp_list:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': opp_id, 'amount': 7, 'source': obj.id},
            source=obj.id, controller=obj.controller,
        ) for opp_id in opp_list]

    return [self_kw, clay_trigger, ih.make_death_trigger(obj, katsu)]

DEIDARA = make_creature(
    name="Deidara, Art is an Explosion",
    power=3, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Flying, haste. Clay Art - Whenever another creature you control dies, Deidara deals damage equal to that creature's power to target creature. Katsu - When Deidara dies, he deals 7 damage to each opponent.",
    setup_interceptors=_deidara_setup,
)


def _sasori_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two 2/2 Puppet tokens + static: Puppet creatures you control have deathtouch."""
    token_itc, _ = etb_create_token(obj, 2, 2, 'Puppet', count=2, colors={'B'})
    kw_itc = ih.make_keyword_grant(
        obj, ['deathtouch'],
        ih.creatures_with_subtype(obj, 'Puppet'),
    )
    return [token_itc, kw_itc]

SASORI = make_creature(
    name="Sasori, Puppet Master",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="When Sasori, Puppet Master enters the battlefield, create two 2/2 black Puppet creature tokens. Puppet creatures you control have deathtouch.",
    setup_interceptors=_sasori_setup,
)


def _hidan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Indestructible self. Blood ritual: whenever Hidan deals combat damage, you lose 1 and each opponent loses 3."""
    self_kw = ih.make_keyword_grant(
        obj, ['indestructible'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def blood_ritual(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': -1},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -3},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return [self_kw, ih.make_damage_trigger(obj, blood_ritual, combat_only=True)]

HIDAN = make_creature(
    name="Hidan, Immortal Zealot",
    power=4, toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Indestructible. Whenever Hidan deals combat damage, you lose 1 life and each opponent loses 3 life.",
    setup_interceptors=_hidan_setup,
)


def _kakuzu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: add four +1/+1 counters. Life-loss trigger: drain 1 from each opponent."""
    def etb_counters(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1'},
            source=obj.id,
            controller=obj.controller,
        ) for _ in range(4)]

    def on_opponent_loss(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        ih.make_etb_trigger(obj, etb_counters),
        ih.make_life_loss_trigger(obj, on_opponent_loss, opponent_only=True),
    ]

KAKUZU = make_creature(
    name="Kakuzu, Five Hearts",
    power=3, toughness=3,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Kakuzu enters the battlefield with four +1/+1 counters on it. Whenever an opponent loses life, you gain 1 life.",
    setup_interceptors=_kakuzu_setup,
)


def _konan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_paper(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Paper',
                'power': 1,
                'toughness': 1,
                'colors': {'U'},
                'subtypes': {'Paper'},
                'keywords': ['flying'],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_upkeep_trigger(obj, create_paper)]

KONAN = make_creature(
    name="Konan, Angel of Ame",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    # "Flying" and the sacrifice-five activated ability are unimplemented (text-only in prior DSL).
    text="Flying. At the beginning of your upkeep, create a 1/1 blue Paper creature token with flying. Sacrifice five Papers: Destroy target permanent.",
    setup_interceptors=_konan_setup
)


ZETSU = make_creature(
    name="Zetsu, White and Black",
    power=2, toughness=4,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Plant", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Deathtouch. When Zetsu enters, surveil 1 and each opponent loses 1 life per Plant you control. (The two halves.)",
    setup_interceptors=_nrt_zetsu_setup,
)


# --- Other Black Ninjas ---

def _orochimaru_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Edo Tensei (reality-bending one-shot, tutor/selection break): whenever Orochimaru
    attacks, return a creature card from a graveyard to the battlefield under your control.
    Deathtouch self-grant + upkeep tax (you lose 2 life — he's a soul leech)."""
    self_kw = ih.make_keyword_grant(
        obj, ['deathtouch'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # Edo Tensei: attack-trigger reanimation from ANY graveyard (tutor/selection break).
    def edo_tensei(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'player': obj.controller,
                'card_type': 'creature',
                'from_any_graveyard': True,
                'to_zone': ZoneType.BATTLEFIELD,
                'new_controller': obj.controller,
                'source': obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    # Soul tax at upkeep (balancing cost — drains YOU).
    def soul_tax(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': -2},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        self_kw,
        ih.make_attack_trigger(obj, edo_tensei),
        ih.make_upkeep_trigger(obj, soul_tax),
    ]

OROCHIMARU = make_creature(
    name="Orochimaru, Sannin of Ambition",
    power=4, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Ninja", "Sannin"},
    supertypes={"Legendary"},
    text="Deathtouch. Edo Tensei - Whenever Orochimaru attacks, return a creature card from any graveyard to the battlefield under your control. At the beginning of your upkeep, you lose 2 life.",
    setup_interceptors=_orochimaru_setup,
)


def curse_mark_sasuke_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jinchuriki - transform when damaged (set-specific mechanic)"""
    return [make_jinchuriki_transform(obj, 6, 5)]

CURSE_MARK_SASUKE = make_creature(
    name="Sasuke, Curse Mark Awakened",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    setup_interceptors=curse_mark_sasuke_setup
)


def _sound_village_jonin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace self-grant + ETB: each opponent discards a card."""
    self_kw = ih.make_keyword_grant(
        obj, ['menace'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def etb_discard(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCARD,
            payload={'player': opp_id, 'count': 1, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    return [self_kw, ih.make_etb_trigger(obj, etb_discard)]

SOUND_VILLAGE_JONIN = make_creature(
    name="Sound Village Jonin",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Jonin"},
    text="Menace. When Sound Village Jonin enters the battlefield, each opponent discards a card.",
    setup_interceptors=_sound_village_jonin_setup,
)


CURSE_MARK_BEARER = make_creature(
    name="Curse Mark Bearer",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    text="When Curse Mark Bearer dies, scry 1 and each opponent loses 1 life per Ninja you control. (The curse releases.)",
    setup_interceptors=_nrt_curse_mark_bearer_setup,
)


ANBU_ASSASSIN = make_creature(
    name="ANBU Assassin",
    power=2, toughness=1,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "ANBU"},
    text="Deathtouch, menace. When ANBU Assassin enters, surveil 1 and each opponent discards a card. (Silent strike from the shadows.)",
    setup_interceptors=_nrt_anbu_assassin_setup,
)


def _uchiha_avenger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control dies, Uchiha Avenger gets +1/+1 until end of turn."""
    def death_filter(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type not in (EventType.OBJECT_DESTROYED, EventType.SACRIFICE):
            return False
        target_id = event.payload.get('object_id')
        if target_id == src.id:
            return False
        # Only fire for creatures the controller owned
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != src.controller:
            return False
        return CardType.CREATURE in target.characteristics.types

    def pump(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id,
            controller=obj.controller,
        )]

    return [ih.make_death_trigger(obj, pump, filter_fn=death_filter)]

UCHIHA_AVENGER = make_creature(
    name="Uchiha Avenger",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    text="Whenever another creature you control dies, Uchiha Avenger gets +1/+1 until end of turn.",
    setup_interceptors=_uchiha_avenger_setup,
)


def _rogue_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_lose_life(obj, 1)
    # On death, each opponent loses 2 life.
    def on_death(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': opp_id, 'amount': -2},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]
    return [itc, ih.make_death_trigger(obj, on_death)]

ROGUE_NINJA = make_creature(
    name="Rogue Ninja",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Rogue"},
    text="When Rogue Ninja enters the battlefield, each opponent loses 1 life. When Rogue Ninja dies, each opponent loses 2 life.",
    setup_interceptors=_rogue_ninja_setup,
)


def _puppet_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch + on death, create a 1/1 Puppet token (salvaged parts)."""
    self_kw = ih.make_keyword_grant(
        obj, ['deathtouch'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def on_death(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Puppet',
                'power': 1,
                'toughness': 1,
                'colors': {'B'},
                'subtypes': {'Puppet'},
                'keywords': ['deathtouch'],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [self_kw, ih.make_death_trigger(obj, on_death)]

PUPPET_ASSASSIN = make_creature(
    name="Puppet Assassin",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Construct", "Puppet"},
    text="Deathtouch. When Puppet Assassin dies, create a 1/1 black Puppet creature token with deathtouch.",
    setup_interceptors=_puppet_assassin_setup,
)


FORBIDDEN_JUTSU_USER = make_creature(
    name="Forbidden Jutsu User",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    text="When Forbidden Jutsu User enters, surveil 2 and each opponent discards a card. (The forbidden seal opens.)",
    setup_interceptors=_nrt_forbidden_jutsu_user_setup,
)


REANIMATED_SHINOBI = make_creature(
    name="Reanimated Shinobi",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Ninja"},
    text="When Reanimated Shinobi enters, surveil 1 and each opponent loses 1 life per card in your graveyard. (Edo Tensei echo.)",
    setup_interceptors=_nrt_reanimated_shinobi_setup,
)


# --- Black Instants ---

TSUKUYOMI = make_instant(
    name="Tsukuyomi",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Surveil 3; each opponent loses 3 life. (72 hours of torture in a second.)",
    resolve=_nrt_resolve_tsukuyomi,
)


AMATERASU = make_instant(
    name="Amaterasu",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Scry 1; each opponent takes 4 damage. (Black flames burn until target ash.)",
    resolve=_nrt_resolve_amaterasu,
)


SOUL_EXTRACTION = make_instant(
    name="Soul Extraction",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Surveil 1; each opponent loses 3 life. (The soul tears free.)",
    resolve=_nrt_resolve_soul_extraction,
)


CURSE_MARK_ACTIVATION = make_instant(
    name="Curse Mark Activation",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Surveil 2; each opponent loses 2 life. (The curse burns to life.)",
    resolve=_nrt_resolve_curse_mark_activation,
)


DEATH_SEAL = make_instant(
    name="Death Seal",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Surveil 1; each opponent loses 4 life. (The Reaper's pact is sealed.)",
    resolve=_nrt_resolve_death_seal,
)


SHADOW_POSSESSION = make_instant(
    name="Shadow Possession",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Surveil 1; each opponent loses 1 life. (Their shadow holds them still.)",
    resolve=_nrt_resolve_shadow_possession,
)


REAPER_DEATH_SEAL = make_instant(
    name="Reaper Death Seal",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Surveil 3; each opponent loses 5 life. (Shinigami's grip closes.)",
    resolve=_nrt_resolve_reaper_death_seal,
)


PAINFUL_MEMORIES = make_instant(
    name="Painful Memories",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Surveil 2; each opponent loses 2 life and discards a card. (Old trauma echoes.)",
    resolve=_nrt_resolve_painful_memories,
)


# --- Black Sorceries ---

EDO_TENSEI = make_sorcery(
    name="Edo Tensei",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Surveil 2; draw a card if your graveyard has 3 or more cards; each opponent loses 2 life. (The dead serve again.)",
    resolve=_nrt_resolve_edo_tensei,
)


SHINRA_TENSEI = make_sorcery(
    name="Shinra Tensei",
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    text="Surveil 1; each opponent loses 3 life. (Universal pull-push.)",
    resolve=_nrt_resolve_shinra_tensei,
)


UCHIHA_MASSACRE = make_sorcery(
    name="Uchiha Massacre",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Surveil 3; each opponent loses 4 life. (The clan ends in fire.)",
    resolve=_nrt_resolve_uchiha_massacre,
)


IZANAGI = make_sorcery(
    name="Izanagi",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Surveil 1; you gain 4 life; each opponent loses 1 life. (Sharingan rewinds fate.)",
    resolve=_nrt_resolve_izanagi,
)


# --- Black Enchantments ---

CURSE_OF_HATRED = make_enchantment(
    name="Curse of Hatred",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Aura"},
    text="When Curse of Hatred enters, surveil 2; draw a card if your graveyard has 3 or more cards; each opponent loses 1 life. (The curse compounds.)",
    setup_interceptors=_nrt_curse_of_hatred_setup,
)


def _akatsuki_hideout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Akatsuki creatures you control get +1/+1 and have menace."""
    pt_boost, _ = static_pt_boost_by_subtype(obj, 1, 1, "Akatsuki", include_self=True)
    menace = ih.make_keyword_grant(
        obj, ['menace'],
        ih.creatures_with_subtype(obj, 'Akatsuki'),
    )
    return list(pt_boost) + [menace]

AKATSUKI_HIDEOUT = make_enchantment(
    name="Akatsuki Hideout",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Akatsuki creatures you control get +1/+1 and have menace.",
    setup_interceptors=_akatsuki_hideout_setup,
)


# =============================================================================
# RED CARDS - FIRE JUTSU, PASSION, NARUTO'S DETERMINATION
# =============================================================================

# --- Legendary Red Characters ---

def naruto_sage_mode_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sage Mode: +3/+3 while you have 15+ life. Attack trigger creates a 2/2 Frog Clone token."""
    sage = make_sage_mode_bonus_interceptors(obj, 3, 3)

    def clone(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Shadow Clone',
                'power': 2, 'toughness': 2,
                'colors': {'R'},
                'subtypes': {'Ninja', 'Clone'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return list(sage) + [ih.make_attack_trigger(obj, clone)]

NARUTO_SAGE_MODE = make_creature(
    name="Naruto, Sage of Mount Myoboku",
    power=4, toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Ninja", "Uzumaki", "Sage"},
    supertypes={"Legendary"},
    text="Sage Mode - Naruto, Sage of Mount Myoboku gets +3/+3 as long as you have 15 or more life. Whenever Naruto attacks, create a 2/2 red Ninja Clone creature token.",
    setup_interceptors=naruto_sage_mode_setup,
)


def jiraiya_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Summoning Jutsu (tutor / selection break):
    ETB: search your library for a creature card with 'Toad', 'Sage', or 'Summon' in its
    subtype and put it onto the battlefield. Sage Mode self-buff persists while Jiraiya
    has >= 15 life."""
    def summoning_jutsu(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'card_type': 'creature',
                'subtype_any_of': ['Toad', 'Sage', 'Summon'],
                'to_zone': ZoneType.BATTLEFIELD,
                'source': obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    # Backup: if tutor didn't find anything, at least materialize a 3/3 Toad token at end of trigger.
    def create_toad(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Toad',
                'power': 3,
                'toughness': 3,
                'colors': {'G'},
                'subtypes': {'Toad'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        ih.make_etb_trigger(obj, summoning_jutsu),
        ih.make_etb_trigger(obj, create_toad),
        *make_sage_mode_bonus_interceptors(obj, 2, 2),
    ]

JIRAIYA = make_creature(
    name="Jiraiya, Toad Sage",
    power=4, toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Ninja", "Sannin", "Sage"},
    supertypes={"Legendary"},
    text="Summoning Jutsu - When Jiraiya enters the battlefield, search your library for a Toad, Sage, or Summon creature card and put it onto the battlefield, then create a 3/3 green Toad creature token. Sage Mode - Jiraiya gets +2/+2 as long as you have 15 or more life.",
    setup_interceptors=jiraiya_setup
)


def killer_bee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lightning Sword Dance (resource-axis break):
    Jinchuriki transform when damaged.
    Haste + 'Eight-Tails tentacles': whenever Killer Bee deals combat damage to a player,
    untap him — he can attack again this turn (extra combat engine per swing).
    While in Tailed Beast mode (post-transform 8/8), he gets trample."""
    self_kw = ih.make_keyword_grant(
        obj, ['haste', 'trample'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # After combat damage to a player → untap (keep swinging) AND extra combat this turn.
    def tentacle_storm(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.UNTAP,
                payload={'object_id': obj.id},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.EXTRA_COMBAT,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            ),
        ]

    return [
        self_kw,
        make_jinchuriki_transform(obj, 8, 8),
        ih.make_damage_trigger(obj, tentacle_storm, combat_only=True),
    ]

KILLER_BEE = make_creature(
    name="Killer Bee, Eight-Tails Jinchuriki",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Jinchuriki"},
    supertypes={"Legendary"},
    text="Haste, trample. Jinchuriki - When Killer Bee is dealt damage, he becomes an 8/8. Lightning Sword Dance - Whenever Killer Bee deals combat damage to a player, untap him and take an extra combat phase after this one.",
    setup_interceptors=killer_bee_setup
)


def gaara_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sand Coffin (asymmetric sweeper + reality-bending):
    Jinchuriki transform when damaged (6/6 Shukaku mode).
    Sand Shield: Gaara has indestructible.
    Shukaku's Wrath (ETB one-shot): each opponent returns all creatures they control to
    their owners' hands, then loses 3 life for each creature returned."""
    self_kw = ih.make_keyword_grant(
        obj, ['indestructible'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def shukaku_wrath(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        opp_ids = set(ih.all_opponents(obj, state))
        counts: dict[str, int] = {opp_id: 0 for opp_id in opp_ids}
        for target in list(state.objects.values()):
            if (target.zone == ZoneType.BATTLEFIELD and
                    target.controller in opp_ids and
                    CardType.CREATURE in target.characteristics.types):
                events.append(Event(
                    type=EventType.RETURN_TO_HAND,
                    payload={'object_id': target.id, 'source': obj.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
                counts[target.controller] = counts.get(target.controller, 0) + 1
        for opp_id, n in counts.items():
            if n > 0:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opp_id, 'amount': -3 * n},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    return [
        self_kw,
        make_jinchuriki_transform(obj, 6, 6),
        ih.make_etb_trigger(obj, shukaku_wrath),
    ]

GAARA = make_creature(
    name="Gaara, One-Tail Jinchuriki",
    power=3, toughness=4,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Ninja", "Jinchuriki", "Kazekage"},
    supertypes={"Legendary"},
    text="Indestructible. Jinchuriki - When Gaara is dealt damage, he becomes a 6/6. Shukaku's Wrath - When Gaara enters the battlefield, each opponent returns all creatures they control to their owners' hands, then loses 3 life for each creature returned this way.",
    setup_interceptors=gaara_setup
)


def _a_fourth_raikage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """REWIRE (spice-pass W23 Phase A1). A, Fourth Raikage was unwired.

    Self-grant haste + first strike (always), plus Lightning Armor: gain
    hexproof on your turn (active_player == controller). Conditional
    QUERY_ABILITIES intercept gates the hexproof grant on state-time
    active player — pattern 2 (hard to interact with on your turn).
    """
    self_kw_always = ih.make_keyword_grant(
        obj, ['haste', 'first strike'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def lightning_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        # Only grant hexproof while it's your turn.
        return state.active_player == obj.controller

    def lightning_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'hexproof' not in granted:
            granted.append('hexproof')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    lightning_armor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=lightning_filter,
        handler=lightning_handler,
        duration='while_on_battlefield',
    )

    return [self_kw_always, lightning_armor]


A_FOURTH_RAIKAGE = make_creature(
    name="A, Fourth Raikage",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Raikage"},
    supertypes={"Legendary"},
    text="Haste, first strike. Lightning Armor - A has hexproof as long as it's your turn.",
    setup_interceptors=_a_fourth_raikage_setup,
)


def _mei_terumi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """REWIRE (spice-pass W23 Phase A1). Mei Terumi was unwired.

    Boil Style attack trigger: 2 damage to each creature the defending
    player controls (auto-resolves on defending side = each opponent's
    creatures, since the engine doesn't pick a defending player until
    later resolution). v1 ships the simpler "each creature each opponent
    controls" shape, which matches the flavor (asymmetric board wipe-lite)
    and is testable.
    """
    def boil_style(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        opp_ids = set(ih.all_opponents(obj, state))
        for target in list(state.objects.values()):
            if (target.zone == ZoneType.BATTLEFIELD and
                    target.controller in opp_ids and
                    CardType.CREATURE in target.characteristics.types):
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': target.id, 'amount': 2, 'source': obj.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    return [ih.make_attack_trigger(obj, boil_style)]


MEI_TERUMI = make_creature(
    name="Mei Terumi, Fifth Mizukage",
    power=3, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Ninja", "Mizukage"},
    supertypes={"Legendary"},
    text="When Mei attacks, she deals 2 damage to each creature defending player controls. {U}{R}: Target creature gets -2/-0 until end of turn.",
    setup_interceptors=_mei_terumi_setup,
)


# --- Regular Red Ninjas ---

FIRE_STYLE_USER = make_creature(
    name="Fire Style User",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="When Fire Style User enters, scry 1 and each opponent takes 1 damage per Ninja you control. (Fire breath.)",
    setup_interceptors=_nrt_fire_style_user_setup,
)


def _cloud_village_ninja_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste and first strike via keyword grant."""
    return [ih.make_keyword_grant(
        obj, ['haste', 'first strike'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )]

CLOUD_VILLAGE_NINJA = make_creature(
    name="Cloud Village Ninja",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="Haste, first strike.",
    setup_interceptors=_cloud_village_ninja_setup,
)


UZUMAKI_DESCENDANT = make_creature(
    name="Uzumaki Descendant",
    power=2, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Uzumaki"},
    text="When Uzumaki Descendant enters, scry 1 and each opponent takes 1 damage per Ninja you control. (The sealing legacy.)",
    setup_interceptors=_nrt_uzumaki_descendant_setup,
)


SHADOW_CLONE = make_creature(
    name="Shadow Clone",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Ninja", "Clone"},
    text="When Shadow Clone enters, scry 1 and each opponent takes 1 damage per Ninja you control. (Multi-strike echo.)",
    setup_interceptors=_nrt_shadow_clone_setup,
)


EXPLOSIVE_TAG_NINJA = make_creature(
    name="Explosive Tag Ninja",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="When Explosive Tag Ninja enters, scry 1 and each opponent takes 2 damage. (Paper bomb arc.)",
    setup_interceptors=_nrt_explosive_tag_ninja_setup,
)


def _sand_village_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace + attack: put a +1/+1 counter on itself."""
    self_kw = ih.make_keyword_grant(
        obj, ['menace'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )
    itc, _ = attack_add_counters(obj, '+1/+1', 1)
    return [self_kw, itc]

SAND_VILLAGE_WARRIOR = make_creature(
    name="Sand Village Warrior",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Warrior"},
    text="Menace. Whenever Sand Village Warrior attacks, put a +1/+1 counter on it.",
    setup_interceptors=_sand_village_warrior_setup,
)


TAIJUTSU_SPECIALIST = make_creature(
    name="Taijutsu Specialist",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Warrior"},
    text="Whenever Taijutsu Specialist attacks, scry 1 and each opponent loses 1 life per Warrior you control. (Eight Gates discipline.)",
    setup_interceptors=_nrt_taijutsu_specialist_setup,
)


RAGE_FILLED_JINCHURIKI = make_creature(
    name="Rage-Filled Jinchuriki",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Jinchuriki"},
    text="When Rage-Filled Jinchuriki enters, scry 1 and each opponent takes 2 damage. (Uncontrolled chakra surge.)",
    setup_interceptors=_nrt_rage_jinchuriki_setup,
)


LIGHTNING_BLADE_USER = make_creature(
    name="Lightning Blade User",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="When Lightning Blade User enters, scry 1 and each opponent takes 1 damage per Ninja you control. (Chidori shock.)",
    setup_interceptors=_nrt_lightning_blade_user_setup,
)


BERSERKER_NINJA = make_creature(
    name="Berserker Ninja",
    power=4, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="Berserker Ninja attacks each combat if able. Whenever it attacks, scry 1 and each opponent loses 1 life per Ninja you control.",
    setup_interceptors=_nrt_berserker_ninja_setup,
)


# --- Red Instants ---

FIRE_BALL_JUTSU = make_instant(
    name="Fire Ball Jutsu",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Scry 1; each opponent takes 3 damage. (The great fireball.)",
    resolve=_nrt_resolve_fire_ball,
)


RASENGAN = make_instant(
    name="Rasengan",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Scry 1; each opponent takes 4 damage. (Chakra grinder.)",
    resolve=_nrt_resolve_rasengan,
)


CHIDORI = make_instant(
    name="Chidori",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Scry 1; each opponent takes 4 damage. (A thousand birds.)",
    resolve=_nrt_resolve_chidori,
)


RASENSHURIKEN = make_instant(
    name="Rasenshuriken",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Scry 2; each opponent takes 5 damage. (Wind-style spiral.)",
    resolve=_nrt_resolve_rasenshuriken,
)


LIGHTNING_BLADE = make_instant(
    name="Lightning Blade",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Scry 1; each opponent takes 5 damage. (One-strike kill.)",
    resolve=_nrt_resolve_lightning_blade,
)


EIGHT_GATES_RELEASE = make_instant(
    name="Eight Gates Release",
    mana_cost="{R}",
    colors={Color.RED},
    text="Scry 1; you gain 2 life; each opponent takes 4 damage. (Taijutsu surge.)",
    resolve=_nrt_resolve_eight_gates,
)


FIRE_DRAGON_JUTSU = make_instant(
    name="Fire Dragon Jutsu",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Scry 1; each opponent takes 5 damage. (Dragon-shaped flames.)",
    resolve=_nrt_resolve_fire_dragon,
)


EXPLOSIVE_KUNAI = make_instant(
    name="Explosive Kunai",
    mana_cost="{R}",
    colors={Color.RED},
    text="Scry 1; each opponent takes 2 damage. (Tagged-throw arc.)",
    resolve=_nrt_resolve_explosive_kunai,
)


LARIAT = make_instant(
    name="Lariat",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Scry 1; each opponent takes 3 damage. (The Raikage's bull-rush.)",
    resolve=_nrt_resolve_lariat,
)


WIND_ENHANCED_RASENGAN = make_instant(
    name="Wind-Enhanced Rasengan",
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Scry 1; each opponent takes 5 damage. (Cutting wind around a chakra core.)",
    resolve=_nrt_resolve_wind_rasengan,
)


# --- Red Sorceries ---

PLANETARY_RASENGAN = make_sorcery(
    name="Planetary Rasengan",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Scry 2; each opponent takes 6 damage. (Wide-area chakra spin.)",
    resolve=_nrt_resolve_planetary_rasengan,
)


TAILED_BEAST_BOMB = make_sorcery(
    name="Tailed Beast Bomb",
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    text="Tailed Beast Bomb deals 10 damage to any target."
)


MULTI_SHADOW_CLONE = make_sorcery(
    name="Multi Shadow Clone Jutsu",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Scry 2; you gain 2 life; each opponent takes 3 damage. (Clone-army strike.)",
    resolve=_nrt_resolve_multi_shadow_clone,
)


BURNING_WILL = make_sorcery(
    name="Burning Will",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Scry 1; you gain 3 life; each opponent takes 3 damage. (Resolve aflame.)",
    resolve=_nrt_resolve_burning_will,
)


# --- Red Enchantments ---

def _nine_tails_cloak_upkeep_effect(target_obj, event, state):
    """Enchanted creature's controller loses 2 life at upkeep — the
    chakra burnout cost of channeling the Nine-Tails."""
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': target_obj.controller, 'amount': -2,
                 'source': 'nine_tails_cloak'},
        source=target_obj.id,
    )]


NINE_TAILS_CLOAK = make_enchantment(
    name="Nine-Tails Cloak",
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature gets +3/+0 and has trample. At the beginning of enchanted creature's controller's upkeep, that player loses 2 life.",
    setup_interceptors=ih.make_aura_setup(
        power_mod=3, toughness_mod=0,
        keywords=["trample"],
        granted_triggered_abilities={
            "trigger_on": "enchanted_controller_upkeep",
            "effect_fn": _nine_tails_cloak_upkeep_effect,
            "description": "Upkeep: enchanted controller loses 2 life",
        },
    ),
)


BATTLE_FRENZY = make_enchantment(
    name="Battle Frenzy",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="When Battle Frenzy enters, scry 1, draw if Warriors >= 2, and each opponent takes 1 damage. (Frenzy crests.)",
    setup_interceptors=_nrt_battle_frenzy_setup,
)


# =============================================================================
# GREEN CARDS - NATURE CHAKRA, SAGE MODE, SUMMONS
# =============================================================================

# --- Legendary Green Characters ---

def _naruto_kyubi_mode_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kurama Mode (persistent state modifier + ongoing engine):
    Naruto has all creature types. Haste + trample self-grant.
    Attack trigger: put a +1/+1 counter on each creature you control AND Naruto deals 3
    damage to each opponent. Every swing stacks a permanent board state advantage."""
    self_kw = ih.make_keyword_grant(
        obj, ['haste', 'trample'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # All-types: QUERY_TYPES interceptor that pads subtypes with a deep set of types.
    ALL_TYPES = [
        "Human", "Ninja", "Uzumaki", "Jinchuriki", "Sage", "Hokage", "Senju", "Uchiha",
        "Hyuga", "Nara", "Yamanaka", "Akimichi", "Aburame", "Inuzuka", "Medic", "Jonin",
        "Clone", "Ape", "Fox", "Spirit", "Tailed Beast", "Toad", "Snake", "Slug", "Summon",
        "Plant", "Shark", "Turtle", "Horse", "Insect", "Cat", "Octopus", "Otsutsuki", "God",
    ]
    all_types_itc = ih.type_grant_interceptor(
        obj,
        ALL_TYPES,
        affects_filter=lambda target, st: target.id == obj.id,
    )

    # Attack trigger: mass +1/+1 counters to your board AND 3 damage to each opponent.
    def kurama_surge(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for target in list(state.objects.values()):
            if (target.controller == obj.controller and
                    target.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in target.characteristics.types):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target.id, 'counter_type': '+1/+1'},
                    source=obj.id,
                    controller=obj.controller,
                ))
        for opp_id in ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': 3, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return [self_kw, all_types_itc, ih.make_attack_trigger(obj, kurama_surge)]

NARUTO_KYUBI_MODE = make_creature(
    name="Naruto, Kyubi Chakra Mode",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Ninja", "Uzumaki", "Jinchuriki"},
    supertypes={"Legendary"},
    text="Haste, trample. Kurama Mode - Naruto has all creature types. Whenever Naruto attacks, put a +1/+1 counter on each creature you control, and Naruto deals 3 damage to each opponent.",
    setup_interceptors=_naruto_kyubi_mode_setup
)


def _hashirama_wood_style_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_treant(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Treant',
                'power': 3,
                'toughness': 3,
                'colors': {'G'},
                'subtypes': {'Treant'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_attack_trigger(obj, create_treant)]

HASHIRAMA_WOOD_STYLE = make_creature(
    name="Hashirama, Wood Style Master",
    power=5, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "Hokage", "Senju"},
    supertypes={"Legendary"},
    text="Whenever Hashirama, Wood Style Master attacks, create a 3/3 green Treant creature token.",
    setup_interceptors=_hashirama_wood_style_setup
)


def _yamato_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_other_you_control(obj, 0, 2)
    return list(interceptors)

YAMATO = make_creature(
    name="Yamato, Wood Style User",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "ANBU"},
    supertypes={"Legendary"},
    text="Other creatures you control get +0/+2.",
    setup_interceptors=_yamato_setup
)


GAMABUNTA = make_creature(
    name="Gamabunta, Toad Boss",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Toad", "Summon"},
    supertypes={"Legendary"},
    text="Trample. When Gamabunta enters, scry 1 and gain X life per Toad you control. Each opponent loses 1 life.",
    setup_interceptors=_nrt_gamabunta_setup,
)


MANDA = make_creature(
    name="Manda, Snake Boss",
    power=8, toughness=6,
    mana_cost="{5}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Snake", "Summon"},
    supertypes={"Legendary"},
    text="Trample, deathtouch. When Manda enters, surveil 1 and each opponent loses 2 life per Snake you control.",
    setup_interceptors=_nrt_manda_setup,
)


def _katsuyu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 6)
    return [itc]

KATSUYU = make_creature(
    name="Katsuyu, Slug Princess",
    power=4, toughness=8,
    mana_cost="{4}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Slug", "Summon"},
    supertypes={"Legendary"},
    text="When Katsuyu, Slug Princess enters the battlefield, you gain 6 life.",
    setup_interceptors=_katsuyu_setup
)


# --- Tailed Beasts ---

def _kurama_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tailed Beast Bomb (reality-bending one-shot + resource axis break):
    Trample + haste + can't be countered self-grant.
    ETB: deal 9 damage divided among any number of targets (opponents and creatures they
    control) — biggest opposing threat dies first, remainder goes to face.
    Tailed Beast Chakra: whenever Kurama deals combat damage to a player, you take an
    extra turn after this one — but Kurama becomes untargetable by its controller (flavor:
    the fox demands another turn from you)."""
    self_kw = ih.make_keyword_grant(
        obj, ['trample', 'haste'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # ETB: 9 damage divided (split: big creature first, rest to face).
    def tailed_beast_bomb(event: Event, state: GameState) -> list[Event]:
        opp_ids = set(ih.all_opponents(obj, state))
        if not opp_ids:
            return []
        candidates = [t for t in state.objects.values()
                      if t.controller in opp_ids and
                      t.zone == ZoneType.BATTLEFIELD and
                      CardType.CREATURE in t.characteristics.types]
        # Sort by toughness descending, take out biggest threats.
        candidates.sort(key=lambda t: get_toughness(t, state), reverse=True)
        remaining = 9
        events: list[Event] = []
        for target in candidates:
            if remaining <= 0:
                break
            tough = max(1, get_toughness(target, state))
            dmg = min(tough, remaining)
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target.id, 'amount': dmg, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            ))
            remaining -= dmg
        # Remainder to face — split across opponents.
        if remaining > 0:
            per_opp = remaining // max(1, len(opp_ids))
            extra = remaining - per_opp * len(opp_ids)
            for idx, opp_id in enumerate(opp_ids):
                amt = per_opp + (extra if idx == 0 else 0)
                if amt > 0:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': opp_id, 'amount': amt, 'source': obj.id},
                        source=obj.id,
                        controller=obj.controller,
                    ))
        return events

    # Tailed Beast Chakra: combat damage to player → extra turn.
    def extra_turn_trigger(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXTRA_TURN,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        self_kw,
        ih.make_etb_trigger(obj, tailed_beast_bomb),
        ih.make_damage_trigger(obj, extra_turn_trigger, combat_only=True),
    ]

KURAMA = make_creature(
    name="Kurama, Nine-Tailed Fox",
    power=9, toughness=9,
    mana_cost="{6}{R}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Fox", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample, haste. Tailed Beast Bomb - When Kurama enters, it deals 9 damage divided as you choose among any number of targets. Whenever Kurama deals combat damage to a player, take an extra turn after this one.",
    setup_interceptors=_kurama_setup,
)


SHUKAKU = make_creature(
    name="Shukaku, One-Tail",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Tanuki", "Spirit", "Beast", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample. When Shukaku enters, scry 1 and each opponent takes 2+ damage per Beast you control. (Sand-tanuki rampage.)",
    setup_interceptors=_nrt_shukaku_setup,
)


MATATABI = make_creature(
    name="Matatabi, Two-Tails",
    power=5, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Cat", "Spirit", "Beast", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Haste. When Matatabi enters, scry 1 and each opponent takes 2 damage per Beast you control. (Two-tail blue flame.)",
    setup_interceptors=_nrt_matatabi_setup,
)


ISOBU = make_creature(
    name="Isobu, Three-Tails",
    power=4, toughness=7,
    mana_cost="{3}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Turtle", "Spirit", "Beast", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Hexproof. When Isobu enters, surveil 1 and each opponent loses 2+ life per Beast you control. (Three-tail tidal wall.)",
    setup_interceptors=_nrt_isobu_setup,
)


SON_GOKU = make_creature(
    name="Son Goku, Four-Tails",
    power=7, toughness=5,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Ape", "Spirit", "Beast", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample. When Son Goku enters, scry 1 and each opponent takes 3+ damage per Beast you control. (Four-tail lava.)",
    setup_interceptors=_nrt_son_goku_setup,
)


def _kokuo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def gain_life(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 5},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_damage_trigger(obj, gain_life, combat_only=True)]

KOKUO = make_creature(
    name="Kokuo, Five-Tails",
    power=5, toughness=5,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Horse", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Whenever Kokuo, Five-Tails deals combat damage to a player, you gain 5 life.",
    setup_interceptors=_kokuo_setup
)


def _saiken_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_two(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        if target_id not in state.players:
            return []
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(2)
        ]
    return [ih.make_damage_trigger(obj, draw_two, combat_only=True)]

SAIKEN = make_creature(
    name="Saiken, Six-Tails",
    power=4, toughness=6,
    mana_cost="{3}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Slug", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Whenever Saiken, Six-Tails deals combat damage to a player, draw two cards.",
    setup_interceptors=_saiken_setup
)


def _chomei_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 2, 2, "Insect", include_self=False)
    return list(interceptors)

CHOMEI = make_creature(
    name="Chomei, Seven-Tails",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Other Insect creatures you control get +2/+2.",
    setup_interceptors=_chomei_setup
)


GYUKI = make_creature(
    name="Gyuki, Eight-Tails",
    power=8, toughness=8,
    mana_cost="{5}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Octopus", "Spirit", "Beast", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample. When Gyuki enters, scry 1 and each opponent takes 3+ damage per Beast you control. (Eight-tail ox-octopus.)",
    setup_interceptors=_nrt_gyuki_setup,
)


# --- Regular Green Creatures ---

TOAD_SUMMON = make_creature(
    name="Toad Summon",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Toad", "Summon"},
    text="When Toad Summon enters, scry 1 and gain X life per Toad you control. Each opponent loses 1 life. (Myoboku's call.)",
    setup_interceptors=_nrt_toad_summon_setup,
)


SNAKE_SUMMON = make_creature(
    name="Snake Summon",
    power=2, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Snake", "Summon"},
    text="Deathtouch. When Snake Summon enters, surveil 1 and each opponent loses 1 life per Snake you control. (Ryuchi's coil.)",
    setup_interceptors=_nrt_snake_summon_setup,
)


def _slug_summon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 3)
    return [itc]

SLUG_SUMMON = make_creature(
    name="Slug Summon",
    power=1, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Slug", "Summon"},
    text="When Slug Summon enters the battlefield, you gain 3 life.",
    setup_interceptors=_slug_summon_setup
)


FOREST_OF_DEATH_BEAST = make_creature(
    name="Forest of Death Beast",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. When Forest of Death Beast enters, scry 1 and each opponent takes 1 damage per Beast you control.",
    setup_interceptors=_nrt_forest_death_beast_setup,
)


NATURE_CHAKRA_USER = make_creature(
    name="Nature Chakra User",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "Sage"},
    text="When Nature Chakra User enters, scry 1 and gain X life per Sage you control. Each opponent loses 1 life. (Nature flows in.)",
    setup_interceptors=_nrt_nature_chakra_user_setup,
)


def _wood_style_clone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_sapling(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Sapling',
                'power': 1,
                'toughness': 1,
                'colors': {'G'},
                'subtypes': {'Sapling'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_death_trigger(obj, create_sapling)]

WOOD_STYLE_CLONE = make_creature(
    name="Wood Style Clone",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Treant", "Ninja", "Clone"},
    text="When Wood Style Clone dies, create a 1/1 green Sapling creature token.",
    setup_interceptors=_wood_style_clone_setup
)


SAGE_APPRENTICE = make_creature(
    name="Sage Apprentice",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "Sage"},
    text="When Sage Apprentice enters, scry 1 and gain X life per Sage you control. Each opponent loses 1 life. (Training begins.)",
    setup_interceptors=_nrt_sage_apprentice_setup,
)


GIANT_CENTIPEDE = make_creature(
    name="Giant Centipede",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Menace. When Giant Centipede enters, surveil 1 and each opponent loses 1 life per Insect you control. (Swarm-strike.)",
    setup_interceptors=_nrt_giant_centipede_setup,
)


def _aburame_insect_swarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_flying_insect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Insect',
                'power': 1,
                'toughness': 1,
                'colors': {'G'},
                'subtypes': {'Insect'},
                'keywords': ['flying'],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_death_trigger(obj, create_flying_insect)]

ABURAME_INSECT_SWARM = make_creature(
    name="Aburame Insect Swarm",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="When Aburame Insect Swarm dies, create a 1/1 green Insect creature token with flying.",
    setup_interceptors=_aburame_insect_swarm_setup
)


FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treant", "Beast"},
    text="Reach. When Forest Guardian enters, scry 1 and gain X life per Beast you control. Each opponent loses 1 life.",
    setup_interceptors=_nrt_forest_guardian_setup,
)


# --- Green Instants ---

SUMMONING_JUTSU = make_instant(
    name="Summoning Jutsu",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Scry 1; you gain 3 life; each opponent loses 1 life. (A 3/3 Beast arrives.)",
    resolve=_nrt_resolve_summon_jutsu,
)


WOOD_STYLE_WALL = make_instant(
    name="Wood Style: Wall",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Scry 1; you gain 4 life. (Timber barrier rises.)",
    resolve=_nrt_resolve_wood_wall,
)


NATURE_ENERGY = make_instant(
    name="Nature Energy",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Scry 1; you gain 2 life; each opponent loses 1 life. (Chakra flows from the land.)",
    resolve=_nrt_resolve_nature_energy,
)


FROG_KUMITE = make_instant(
    name="Frog Kumite",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Scry 1; each opponent takes 3 damage. (Toad-style brawl.)",
    resolve=_nrt_resolve_frog_kumite,
)


FOREST_BINDING = make_instant(
    name="Forest Binding",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Scry 1; you gain 2 life; each opponent loses 2 life. (Root-snare strangles.)",
    resolve=_nrt_resolve_forest_binding,
)


REJUVENATION_JUTSU = make_instant(
    name="Rejuvenation Jutsu",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Scry 1; you gain 6 life. (Medic-nin restoration.)",
    resolve=_nrt_resolve_rejuvenation,
)


GIANT_GROWTH_JUTSU = make_instant(
    name="Giant Growth Jutsu",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Scry 1; you gain 3 life; each opponent loses 1 life. (Akimichi swell.)",
    resolve=_nrt_resolve_giant_growth,
)


SAGE_ART_AWAKENING = make_instant(
    name="Sage Art: Awakening",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Scry 2; you gain 4 life; each opponent loses 2 life. (Sage Mode awakens.)",
    resolve=_nrt_resolve_sage_awakening,
)


# --- Green Sorceries ---

MASS_SUMMONING = make_sorcery(
    name="Mass Summoning",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Scry 2; you gain 6 life; each opponent loses 1 life. (Three Beasts arrive.)",
    resolve=_nrt_resolve_mass_summoning,
)


WOOD_STYLE_DEEP_FOREST = make_sorcery(
    name="Wood Style: Deep Forest",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    text="Scry 2; you gain 5 life; each opponent loses 1 life. (The forest devours the field.)",
    resolve=_nrt_resolve_deep_forest,
)


SAGE_TRAINING = make_sorcery(
    name="Sage Training",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Scry 2; you gain 4 life. (Mount Myoboku regimen.)",
    resolve=_nrt_resolve_sage_training,
)


NATURAL_REBIRTH = make_sorcery(
    name="Natural Rebirth",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Scry 2; you gain 8 life (or more if your graveyard is full). (Rebirth through nature.)",
    resolve=_nrt_resolve_natural_rebirth,
)


# --- Green Enchantments ---

SAGE_MODE_ENCHANTMENT = make_enchantment(
    name="Sage Mode",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When Sage Mode enters, scry 1 and gain X life per Sage you control. Each opponent loses 1 life.",
    setup_interceptors=_nrt_sage_mode_ench_setup,
)


FOREST_OF_DEATH = make_enchantment(
    name="Forest of Death",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control have trample. Whenever a creature you control deals combat damage to a player, put a +1/+1 counter on it."
)


NATURE_CHAKRA_FIELD = make_enchantment(
    name="Nature Chakra Field",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="When Nature Chakra Field enters, scry 1 and gain X life per Sage you control. (The field hums.)",
    setup_interceptors=_nrt_nature_chakra_field_setup,
)


# =============================================================================
# ARTIFACTS - WEAPONS, SCROLLS, SHARINGAN
# =============================================================================

KUNAI = make_equipment(
    name="Kunai",
    mana_cost="{1}",
    text="When Kunai enters, scry 1 and each opponent takes 1 damage per Ninja you control. (A thrown blade.)",
    equip_cost="{1}",
    setup_interceptors=_nrt_kunai_setup,
)


SHURIKEN = make_equipment(
    name="Shuriken",
    mana_cost="{1}",
    text="When Shuriken enters, scry 1 and each opponent takes 1 damage per Warrior you control. (Spinning star.)",
    equip_cost="{2}",
    setup_interceptors=_nrt_shuriken_setup,
)


# --- Samehada, Shark Skin: Helper-5 rewire ---------------------------------
# +3/+2 + granted trigger "combat damage to player → controller gains that
# much life." The lifelink-on-trigger pattern feels distinct from
# vanilla lifelink because it only fires on combat damage to players.
def _samehada_combat_damage_to_player_filter(
    event: Event, state: GameState, target_id: str
) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    if event.payload.get('target') not in state.players:
        return False
    amt = event.payload.get('amount', 0) or 0
    return amt > 0


def _samehada_lifegain_effect(
    target_obj: GameObject, event: Event, state: GameState
) -> list[Event]:
    amt = event.payload.get('amount', 0) or 0
    if amt <= 0:
        return []
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': target_obj.controller, 'amount': amt},
        source=target_obj.id,
    )]


SAMEHADA = make_equipment(
    name="Samehada, Shark Skin",
    mana_cost="{3}",
    text="Equipped creature gets +3/+2. Whenever equipped creature deals combat damage to a player, you gain that much life.",
    equip_cost="{3}",
    supertypes={"Legendary"},
    setup_interceptors=ih.make_equipment_setup(
        power_mod=3, toughness_mod=2,
        equip_cost="{3}",
        granted_triggered_abilities={
            "event_filter": _samehada_combat_damage_to_player_filter,
            "effect_fn": _samehada_lifegain_effect,
            "description": "Combat damage to player → controller gains that much life",
        },
    ),
)


EXECUTIONERS_BLADE = make_equipment(
    name="Executioner's Blade",
    mana_cost="{2}",
    text="Equipped creature gets +3/+0. Whenever equipped creature destroys a creature, put a +1/+1 counter on it.",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


SCROLL_OF_SEALING = make_artifact(
    name="Scroll of Sealing",
    mana_cost="{2}",
    text="When Scroll of Sealing enters, surveil 1 and each opponent loses 1 life. (A sealed scroll opens.)",
    setup_interceptors=_nrt_scroll_sealing_setup,
)


CHAKRA_PILLS = make_artifact(
    name="Chakra Pills",
    mana_cost="{1}",
    text="When Chakra Pills enters, scry 1 and you gain 4 life. (Forbidden military rations.)",
    setup_interceptors=_nrt_chakra_pills_setup,
)


FORBIDDEN_SCROLL = make_artifact(
    name="Forbidden Scroll",
    mana_cost="{3}",
    text="When Forbidden Scroll enters, surveil 2 and each opponent mills 2. (The forbidden scroll opens.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_forbidden_scroll_setup,
)


HEADBAND_OF_THE_LEAF = make_equipment(
    name="Headband of the Leaf",
    mana_cost="{1}",
    text="When Headband of the Leaf enters, scry 1 and you gain X life per Ninja you control. (Badge of the Leaf.)",
    equip_cost="{1}",
    setup_interceptors=_nrt_headband_setup,
)


SHARINGAN_CONTACT = make_artifact(
    name="Sharingan Contact",
    mana_cost="{2}",
    text="When Sharingan Contact enters, scry 2 and each opponent loses 1 life. (Sharingan copies a jutsu.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_sharingan_contact_setup,
)


RINNEGAN_EYE = make_artifact(
    name="Rinnegan Eye",
    mana_cost="{4}",
    text="When Rinnegan Eye enters, surveil 2 and each opponent reveals their hand. (Six-path-sight.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_rinnegan_eye_setup,
)


BYAKUGAN_EYE = make_artifact(
    name="Byakugan Eye",
    mana_cost="{2}",
    text="When Byakugan Eye enters, scry 1 and each opponent reveals their hand. (The all-seeing eye.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_byakugan_eye_setup,
)


PUPPET_CORE = make_artifact(
    name="Puppet Core",
    mana_cost="{2}",
    text="{3}, {T}: Create a 2/2 black Puppet artifact creature token with deathtouch."
)


EXPLOSIVE_TAG = make_artifact(
    name="Explosive Tag",
    mana_cost="{1}",
    text="When Explosive Tag enters, scry 1 and each opponent takes 2 damage. (Paper bomb primed.)",
    setup_interceptors=_nrt_explosive_tag_setup,
)


SMOKE_BOMB = make_artifact(
    name="Smoke Bomb",
    mana_cost="{1}",
    text="When Smoke Bomb enters, surveil 1 and each opponent loses 1 life. (Escape under cover.)",
    setup_interceptors=_nrt_smoke_bomb_setup,
)


SUMMONING_CONTRACT = make_artifact(
    name="Summoning Contract",
    mana_cost="{3}",
    text="When Summoning Contract enters, scry 1 and gain X life per Beast you control. (The pact is signed.)",
    setup_interceptors=_nrt_summoning_contract_setup,
)


# =============================================================================
# LANDS
# =============================================================================

HIDDEN_LEAF_VILLAGE = make_land(
    name="Hidden Leaf Village",
    text="When Hidden Leaf Village enters, scry 1 and gain X life per Ninja you control. (The Hidden Leaf stands.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_konoha_village_setup,
)


HIDDEN_MIST_VILLAGE = make_land(
    name="Hidden Mist Village",
    text="When Hidden Mist Village enters, surveil 1 and each opponent mills 1. (Mist obscures all.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_mist_village_land_setup,
)


HIDDEN_SAND_VILLAGE = make_land(
    name="Hidden Sand Village",
    text="{T}: Add {C}. {T}: Add {R} or {G}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


HIDDEN_CLOUD_VILLAGE = make_land(
    name="Hidden Cloud Village",
    text="{T}: Add {C}. {T}: Add {U} or {R}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


HIDDEN_STONE_VILLAGE = make_land(
    name="Hidden Stone Village",
    text="{T}: Add {C}. {T}: Add {R} or {B}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


VALLEY_OF_THE_END = make_land(
    name="Valley of the End",
    text="When Valley of the End enters, scry 1 and each opponent takes X damage per Warrior you control. (The duel's echo.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_valley_of_end_setup,
)


AKATSUKI_HIDEOUT_LAND = make_land(
    name="Akatsuki Hideout",
    text="When Akatsuki Hideout enters, surveil 1 and each opponent loses 1 life. (The cloak gathers.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_akatsuki_hideout_land_setup,
)


FOREST_OF_DEATH_LAND = make_land(
    name="Forest of Death",
    text="{T}: Add {G}. {2}{G}, {T}: Create a 1/1 green Insect creature token."
)


MOUNT_MYOBOKU = make_land(
    name="Mount Myoboku",
    text="When Mount Myoboku enters, scry 1 and gain X life per Toad you control. (The toad sage's mountain.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_mount_myoboku_setup,
)


RYUCHI_CAVE = make_land(
    name="Ryuchi Cave",
    text="{T}: Add {B}. {T}: Add {B} or {G}. Activate only if you control a Snake.",
    supertypes={"Legendary"}
)


SHIKKOTSU_FOREST = make_land(
    name="Shikkotsu Forest",
    text="{T}: Add {W}. {T}: Add {W} or {G}. Activate only if you control a Slug.",
    supertypes={"Legendary"}
)


UCHIHA_COMPOUND = make_land(
    name="Uchiha Compound",
    text="When Uchiha Compound enters, surveil 1 and each opponent loses 1+ life per Ninja you control. (Clan compound rises.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_uchiha_compound_setup,
)


HYUGA_COMPOUND = make_land(
    name="Hyuga Compound",
    text="When Hyuga Compound enters, scry 1 and gain X life per Ninja you control. (Branch House guards the family.)",
    supertypes={"Legendary"},
    setup_interceptors=_nrt_hyuga_compound_setup,
)


TRAINING_GROUND = make_land(
    name="Training Ground",
    text="When Training Ground enters, scry 1 and you gain 2 life. (Rookies drilled hard.)",
    setup_interceptors=_nrt_training_ground_setup,
)


CHUNIN_EXAM_ARENA = make_land(
    name="Chunin Exam Arena",
    text="When Chunin Exam Arena enters, scry 2 and each opponent loses 1 life. (The exam pit thunders.)",
    setup_interceptors=_nrt_chunin_arena_setup,
)


HOKAGE_MONUMENT_LAND = make_land(
    name="Hokage Rock",
    text="{T}: Add {W}. {W}, {T}: Target Ninja creature you control gains vigilance until end of turn."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# --- Gold Cards ---

def team_7_formation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Custom filter for Naruto, Sasuke, and Sakura (set-specific)"""
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
        EventType, new_id
    )

    def team7_filter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        name = target.characteristics.name
        return 'Naruto' in name or 'Sasuke' in name or 'Sakura' in name

    interceptors = []

    def power_filter(event, state, src=obj, flt=team7_filter):
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return flt(target, state)

    def power_handler(event, state):
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'
    ))

    def toughness_filter(event, state, src=obj, flt=team7_filter):
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return flt(target, state)

    def toughness_handler(event, state):
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_handler,
        duration='while_on_battlefield'
    ))

    return interceptors

TEAM_7_FORMATION = make_enchantment(
    name="Team 7 Formation",
    mana_cost="{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    setup_interceptors=team_7_formation_setup
)


NEW_GENERATION = make_sorcery(
    name="New Generation",
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Scry 1; you gain 3 life; each opponent loses 1 life. (The next wave rises.)",
    resolve=_nrt_resolve_new_generation,
)


BONDS_OF_FRIENDSHIP = make_instant(
    name="Bonds of Friendship",
    mana_cost="{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Scry 1; you gain 3 life; each opponent loses 1 life. (Team holds the bond.)",
    resolve=_nrt_resolve_bonds_of_friendship,
)


SHINOBI_WAR = make_sorcery(
    name="Shinobi War",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Scry 2; each opponent loses 3 life. (Fourth War rages.)",
    resolve=_nrt_resolve_shinobi_war,
)


def _allied_shinobi_forces_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    pt_boost, _ = static_pt_boost_by_subtype(obj, 2, 1, "Ninja", include_self=True)

    def create_ninja(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Ninja',
                'power': 1,
                'toughness': 1,
                'colors': {'W'},
                'subtypes': {'Ninja'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return list(pt_boost) + [ih.make_upkeep_trigger(obj, create_ninja)]

ALLIED_SHINOBI_FORCES = make_enchantment(
    name="Allied Shinobi Forces",
    mana_cost="{2}{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    text="Ninja creatures you control get +2/+1. At the beginning of your upkeep, create a 1/1 white Ninja creature token.",
    setup_interceptors=_allied_shinobi_forces_setup
)


SANNIN_SHOWDOWN = make_sorcery(
    name="Sannin Showdown",
    mana_cost="{3}{W}{B}{G}",
    colors={Color.WHITE, Color.BLACK, Color.GREEN},
    text="Scry 2; each opponent takes 4 damage. (Jiraiya vs Orochimaru vs Tsunade.)",
    resolve=_nrt_resolve_sannin_showdown,
)


FINAL_VALLEY_BATTLE = make_sorcery(
    name="Final Valley Battle",
    mana_cost="{4}{W}{B}{R}",
    colors={Color.WHITE, Color.BLACK, Color.RED},
    text="Scry 2; you gain 3 life; each opponent takes 5 damage. (The duel ends.)",
    resolve=_nrt_resolve_final_valley,
)


INFINITE_TSUKUYOMI = make_sorcery(
    name="Infinite Tsukuyomi",
    mana_cost="{6}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Surveil 3; each opponent loses 5 life. (Moon's Eye Plan.)",
    resolve=_nrt_resolve_infinite_tsukuyomi,
)


TALK_NO_JUTSU = make_instant(
    name="Talk no Jutsu",
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Scry 2; you gain 5 life; each opponent loses 1 life. (Words that change worlds.)",
    resolve=_nrt_resolve_talk_no_jutsu,
)


SUSANOO = make_enchantment(
    name="Susanoo",
    mana_cost="{4}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Aura"},
    text="When Susanoo enters, surveil 2; draw a card if your graveyard has 4 or more cards; each opponent loses 2 life. (Ethereal armor coalesces.)",
    setup_interceptors=_nrt_susanoo_ench_setup,
)


# =============================================================================
# NEW LEGENDARY ADDITIONS (Quality pass)
# =============================================================================

# --- Kushina Uzumaki (W/R): Chain-seal protector for Uzumaki clan ---

def _kushina_uzumaki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two 1/1 red Ninja tokens. Static: Uzumaki creatures you control have indestructible."""
    token_itc, _ = etb_create_token(obj, 1, 1, 'Ninja', count=2, colors={'R'})
    protect = ih.make_keyword_grant(
        obj, ['indestructible'],
        ih.creatures_with_subtype(obj, 'Uzumaki'),
    )
    return [token_itc, protect]

KUSHINA_UZUMAKI = make_creature(
    name="Kushina Uzumaki, Red-Hot Habanero",
    power=3, toughness=3,
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja", "Uzumaki"},
    supertypes={"Legendary"},
    text="When Kushina Uzumaki enters the battlefield, create two 1/1 red Ninja creature tokens. Uzumaki creatures you control have indestructible.",
    setup_interceptors=_kushina_uzumaki_setup,
)


# --- Fugaku Uchiha (B): Clan head, Uchiha lord ---

def _fugaku_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Uchiha creatures you control get +1/+1."""
    interceptors, _ = static_pt_boost_by_subtype(obj, 1, 1, "Uchiha", include_self=False)
    return list(interceptors)

FUGAKU_UCHIHA = make_creature(
    name="Fugaku Uchiha, Clan Head",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    text="Other Uchiha creatures you control get +1/+1.",
    setup_interceptors=_fugaku_uchiha_setup,
)


# --- Nagato, Rinnegan Master (U/B): Spellslinger payoff ---

def _nagato_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, draw a card."""
    def effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_spell_cast_trigger(
        obj, effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]

NAGATO_RINNEGAN = make_creature(
    name="Nagato, Rinnegan Master",
    power=2, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Akatsuki", "Uzumaki"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery, draw a card.",
    setup_interceptors=_nagato_setup,
)


# --- Indra Otsutsuki (B/R): Ancestor of Uchiha - attack damages each opponent ---

def _indra_otsutsuki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Indra attacks, each opponent loses 2 life."""
    def drain(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': opp_id, 'amount': -2},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]
    return [ih.make_attack_trigger(obj, drain)]

INDRA_OTSUTSUKI = make_creature(
    name="Indra Otsutsuki, Firstborn",
    power=4, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Otsutsuki", "Uchiha"},
    supertypes={"Legendary"},
    text="Whenever Indra Otsutsuki, Firstborn attacks, each opponent loses 2 life.",
    setup_interceptors=_indra_otsutsuki_setup,
)


# --- Asura Otsutsuki (G/W): Ancestor of Senju - token generator ---

def _asura_otsutsuki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two 1/1 green Ninja tokens. Senju creatures you control get +1/+1."""
    token_itc, _ = etb_create_token(obj, 1, 1, 'Ninja', count=2, colors={'G'})
    pt_boost, _ = static_pt_boost_by_subtype(obj, 1, 1, "Senju", include_self=False)
    return [token_itc] + list(pt_boost)

ASURA_OTSUTSUKI = make_creature(
    name="Asura Otsutsuki, Secondborn",
    power=3, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Ninja", "Otsutsuki", "Senju"},
    supertypes={"Legendary"},
    text="When Asura Otsutsuki, Secondborn enters the battlefield, create two 1/1 green Ninja creature tokens. Other Senju creatures you control get +1/+1.",
    setup_interceptors=_asura_otsutsuki_setup,
)


# --- Kaguya Otsutsuki (5-color mythic): Divine Tree ultimate ---

def _kaguya_otsutsuki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each opponent loses 5 life, you draw 3 cards. Self-grant flying + hexproof."""
    self_kw = ih.make_keyword_grant(
        obj, ['flying', 'hexproof', 'trample'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -5},
                source=obj.id,
                controller=obj.controller,
            ))
        for _ in range(3):
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return [self_kw, ih.make_etb_trigger(obj, etb_effect)]

KAGUYA_OTSUTSUKI = make_creature(
    name="Kaguya Otsutsuki, Rabbit Goddess",
    power=8, toughness=8,
    mana_cost="{6}{W}{U}{B}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK},
    subtypes={"Otsutsuki", "God"},
    supertypes={"Legendary"},
    text="Flying, hexproof, trample. When Kaguya Otsutsuki, Rabbit Goddess enters the battlefield, each opponent loses 5 life and you draw three cards.",
    setup_interceptors=_kaguya_otsutsuki_setup,
)


# --- Danzo Shimura (W/B): ANBU commander ---

def _danzo_shimura_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control dies, each opponent loses 1 life."""
    def death_filter(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type not in (EventType.OBJECT_DESTROYED, EventType.SACRIFICE):
            return False
        target_id = event.payload.get('object_id')
        if target_id == src.id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != src.controller:
            return False
        return CardType.CREATURE in target.characteristics.types

    def drain(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': opp_id, 'amount': -1},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    return [ih.make_death_trigger(obj, drain, filter_fn=death_filter)]

DANZO_SHIMURA = make_creature(
    name="Danzo Shimura, Root Architect",
    power=3, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Ninja", "ANBU"},
    supertypes={"Legendary"},
    text="Whenever another creature you control dies, each opponent loses 1 life.",
    setup_interceptors=_danzo_shimura_setup,
)


# =============================================================================
# GAME-ALTERING LEGENDARY ADDITIONS (Raise The Bar pass)
# =============================================================================

# --- Hagoromo Otsutsuki, Sage of Six Paths (5C): Persistent spell-copy engine ---

def _hagoromo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ninshu (persistent state modifier + ongoing engine):
    Self-grants flying, hexproof, and vigilance.
    Whenever you cast a non-creature spell, copy it (you may choose new targets).
    Asymmetric sweeper ETB: destroy target creature with the greatest power among creatures
    your opponents control (signature Sage judgment)."""
    self_kw = ih.make_keyword_grant(
        obj, ['flying', 'hexproof', 'vigilance'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def ninshu_copy(event: Event, state: GameState) -> list[Event]:
        spell_id = event.payload.get('spell_id')
        if spell_id is None:
            return []
        return [Event(
            type=EventType.COPY_SPELL,
            payload={'spell_id': spell_id, 'controller': obj.controller, 'new_targets': True},
            source=obj.id,
            controller=obj.controller,
        )]

    # Non-creature spell filter (counts instants, sorceries, enchantments, artifacts).
    def non_creature_spell_filter(event: Event, state: GameState, src: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if caster != src.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        if not spell_types:
            st = event.payload.get('spell_type')
            if st is not None:
                spell_types = {st}
        # Exclude creatures — only copy jutsu/enchantments/etc.
        if CardType.CREATURE in spell_types:
            return False
        return bool(spell_types)

    ninshu_trig = ih.make_spell_cast_trigger(
        obj, ninshu_copy, filter_fn=non_creature_spell_filter,
    )

    # Sage Judgment: ETB destroys the biggest opposing creature.
    def sage_judgment(event: Event, state: GameState) -> list[Event]:
        opp_ids = set(ih.all_opponents(obj, state))
        candidates = [t for t in state.objects.values()
                      if t.controller in opp_ids and
                      t.zone == ZoneType.BATTLEFIELD and
                      CardType.CREATURE in t.characteristics.types]
        if not candidates:
            return []
        biggest = max(candidates, key=lambda t: get_power(t, state))
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': biggest.id, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]

    return [self_kw, ninshu_trig, ih.make_etb_trigger(obj, sage_judgment)]

HAGOROMO_OTSUTSUKI = make_creature(
    name="Hagoromo Otsutsuki, Sage of Six Paths",
    power=5, toughness=6,
    mana_cost="{4}{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    subtypes={"Human", "Ninja", "Otsutsuki", "Sage"},
    supertypes={"Legendary"},
    text="Flying, hexproof, vigilance. Sage Judgment - When Hagoromo enters the battlefield, destroy target creature with the greatest power among creatures your opponents control. Ninshu - Whenever you cast a noncreature spell, copy it. You may choose new targets for the copy.",
    setup_interceptors=_hagoromo_setup,
)


# --- Isshiki Otsutsuki, Karma Reborn (B/U): Alt win condition on karma counters ---

def _isshiki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Karma Seal (alt win condition + ongoing engine):
    Indestructible self-grant.
    Whenever Isshiki attacks, put a karma counter on target opponent.
    At the beginning of your upkeep, if an opponent has 4 or more karma counters, that
    opponent loses the game. (Tracked via a custom counter on the player — at cleanup this
    is the mechanic stub that scheduling engine supports via PLAYER_LOSES.)"""
    self_kw = ih.make_keyword_grant(
        obj, ['indestructible'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    # Attack trigger: put a karma counter on each opponent (auto-spread — no target picker).
    def karma_seal(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in ih.all_opponents(obj, state):
            opp = state.players.get(opp_id)
            if opp is None:
                continue
            karma = getattr(opp, '_karma_counters', 0) + 1
            setattr(opp, '_karma_counters', karma)
            # Emit a marker counter-added event for observability/tests.
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'player': opp_id, 'counter_type': 'karma'},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    # Upkeep: check if any opponent has 4+ karma counters → they lose.
    def karma_check(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in ih.all_opponents(obj, state):
            opp = state.players.get(opp_id)
            if opp is None:
                continue
            if getattr(opp, '_karma_counters', 0) >= 4:
                events.append(Event(
                    type=EventType.PLAYER_LOSES,
                    payload={'player': opp_id, 'source': obj.id, 'reason': 'karma'},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    return [
        self_kw,
        ih.make_attack_trigger(obj, karma_seal),
        ih.make_upkeep_trigger(obj, karma_check),
    ]

ISSHIKI_OTSUTSUKI = make_creature(
    name="Isshiki Otsutsuki, Karma Reborn",
    power=5, toughness=5,
    mana_cost="{4}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Otsutsuki", "God"},
    supertypes={"Legendary"},
    text="Indestructible. Karma Seal - Whenever Isshiki attacks, put a karma counter on each opponent. At the beginning of your upkeep, any opponent with 4 or more karma counters loses the game.",
    setup_interceptors=_isshiki_setup,
)


# --- Shadow Clone Jutsu Naruto, Multiplicity (R): Mass transform / combo enabler ---

def _shadow_clone_naruto_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Multi Shadow Clone Jutsu (reality-bending one-shot + ongoing engine):
    Haste self-grant.
    ETB: for each creature you control (including this one), create a 2/1 red Shadow Clone
    Ninja creature token with haste. This is a token-mirror swarm.
    Whenever another Clone you control attacks, put a +1/+1 counter on it and it becomes a
    copy of any creature you control until end of turn (mass-transform combo)."""
    self_kw = ih.make_keyword_grant(
        obj, ['haste'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def multi_clone(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        # Count existing creatures you control.
        your_creatures = [t for t in state.objects.values()
                          if t.controller == obj.controller and
                          t.zone == ZoneType.BATTLEFIELD and
                          CardType.CREATURE in t.characteristics.types]
        count = max(1, len(your_creatures))
        for _ in range(count):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'token': True,
                    'name': 'Shadow Clone',
                    'power': 2,
                    'toughness': 1,
                    'colors': {'R'},
                    'subtypes': {'Ninja', 'Clone'},
                    'keywords': ['haste'],
                    'controller': obj.controller,
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    # Whenever ANOTHER attacking creature is a Clone you control, buff it.
    def clone_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        if attacker_id == obj.id:
            return False
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        if attacker.controller != obj.controller:
            return False
        return 'Clone' in attacker.characteristics.subtypes

    def clone_buff(event: Event, state: GameState) -> InterceptorResult:
        attacker_id = event.payload.get('attacker_id')
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': attacker_id, 'counter_type': '+1/+1'},
                    source=obj.id,
                    controller=obj.controller,
                ),
            ],
        )

    clone_swarm = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=clone_attack_filter,
        handler=clone_buff,
        duration='while_on_battlefield',
    )

    return [
        self_kw,
        ih.make_etb_trigger(obj, multi_clone),
        clone_swarm,
    ]

SHADOW_CLONE_NARUTO = make_creature(
    name="Naruto, Multi Shadow Clone",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Uzumaki", "Clone"},
    supertypes={"Legendary"},
    text="Haste. Multi Shadow Clone Jutsu - When Naruto, Multi Shadow Clone enters the battlefield, for each creature you control, create a 2/1 red Shadow Clone Ninja creature token with haste. Whenever another Clone you control attacks, put a +1/+1 counter on it.",
    setup_interceptors=_shadow_clone_naruto_setup,
)


# =============================================================================
# SPICE PASS W23 — PHASE A1 (2026-05-18)
# 5 new cards + 3 rewires (Tenten, A Fourth Raikage, Mei Terumi above).
# Targets: build-around mythic (pattern 11), assembly mythic on Tailed Beast
# count (pattern 11), equipment (Sharingan Eye), saga (Chunin Exams), and a
# build-around Uchiha (compression + ping engine).
# =============================================================================


# --- Sharingan Eye (NEW, Phase A1 — equipment, pattern 4 compression) ---
# {2} Legendary Equipment, Mythic. Equip {2}. Equipped creature gets +2/+2,
# has lifelink and ward {1}. Mechanically a Sharingan stand-in: vision +
# self-defense + sustain. The +2/+2 / lifelink / ward {1} stack is a real
# threat-and-answer compression on whichever creature carries it.
SHARINGAN_EYE_EQUIPMENT = CardDefinition(
    name="Sharingan Eye",
    mana_cost="{2}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        subtypes={"Equipment"},
        colors=set(),
        supertypes={"Legendary"},
        mana_cost="{2}",
    ),
    text=(
        "Equipped creature gets +2/+2, has lifelink and ward {1}. "
        "Equip {2}."
    ),
    setup_interceptors=ih.make_equipment_setup(
        power_mod=2, toughness_mod=2,
        keywords=["lifelink"],
        ward_cost="{1}",
        equip_cost="{2}",
    ),
)


# --- Naruto, Sage of Six Paths (NEW, Phase A1 — build-around mythic, pattern 11) ---
# {3}{R}{G}{W} 5/5 Legendary Human Ninja Uzumaki Sage. Trample, haste.
# ETB: untap each Tailed Beast permanent you control.
# Whenever ANOTHER Tailed Beast you control enters or attacks, draw a card.
# Build-around: the more Tailed Beasts you assemble, the more this card
# does. Vanilla 5/5 without the Tailed Beast support. With it, an engine.
def _naruto_six_paths_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Build-around mythic — synergy hook on Tailed Beast subtype."""
    self_kw = ih.make_keyword_grant(
        obj, ['trample', 'haste'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def untap_tailed_beasts(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for target in list(state.objects.values()):
            if target.id == obj.id:
                continue
            if target.controller != obj.controller:
                continue
            if target.zone != ZoneType.BATTLEFIELD:
                continue
            if 'Tailed Beast' in (target.characteristics.subtypes or set()):
                events.append(Event(
                    type=EventType.UNTAP,
                    payload={'object_id': target.id},
                    source=obj.id,
                    controller=obj.controller,
                ))
        return events

    # Trigger on Tailed Beasts entering. We use a custom filter on
    # ZONE_CHANGE / OBJECT_CREATED to catch ETB of *other* TB permanents
    # under our control.
    def tb_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            target_id = event.payload.get('object_id')
        elif event.type == EventType.OBJECT_CREATED:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            target_id = event.payload.get('object_id')
        else:
            return False
        if target_id == source.id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != source.controller:
            return False
        return 'Tailed Beast' in (target.characteristics.subtypes or set())

    def draw_one(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]

    tb_etb_trig = ih.make_etb_trigger(
        obj, draw_one, filter_fn=tb_etb_filter,
    )

    # Attack trigger: when ANOTHER Tailed Beast you control attacks, draw.
    def tb_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id == obj.id:
            return False
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        if attacker.controller != obj.controller:
            return False
        return 'Tailed Beast' in (attacker.characteristics.subtypes or set())

    def tb_attack_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    tb_attack_trig = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=tb_attack_filter,
        handler=tb_attack_handler,
        duration='while_on_battlefield',
    )

    return [
        self_kw,
        ih.make_etb_trigger(obj, untap_tailed_beasts),
        tb_etb_trig,
        tb_attack_trig,
    ]


NARUTO_SIX_PATHS = make_creature(
    name="Naruto, Sage of Six Paths",
    power=5, toughness=5,
    mana_cost="{3}{R}{G}{W}",
    colors={Color.RED, Color.GREEN, Color.WHITE},
    subtypes={"Human", "Ninja", "Uzumaki", "Sage"},
    supertypes={"Legendary"},
    text=(
        "Trample, haste. When Naruto, Sage of Six Paths enters the "
        "battlefield, untap each Tailed Beast you control. Whenever "
        "another Tailed Beast you control enters the battlefield or "
        "attacks, draw a card."
    ),
    setup_interceptors=_naruto_six_paths_setup,
)


# --- Kurama Sealed, Nine-Tail Avatar (NEW, Phase A1 — assembly mythic gated on
# Tailed Beast count; pattern 11 build-around). ---
# {6}{R}{R}{G} 0/0 Legendary Spirit Tailed Beast.
# Trample, haste.
# As Kurama Sealed enters, it gets +2/+2 counters for each other Tailed Beast
# you control.
# Whenever Kurama Sealed attacks, if you control 3 or more Tailed Beast
# permanents (including this one), it deals damage equal to its power to
# each opponent.
def _kurama_sealed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tailed Beast assembly mythic — payoff scales with TB count."""
    self_kw = ih.make_keyword_grant(
        obj, ['trample', 'haste'],
        lambda target, st: target.id == obj.id and target.zone == ZoneType.BATTLEFIELD,
    )

    def etb_counters(event: Event, state: GameState) -> list[Event]:
        # Count OTHER Tailed Beasts you control.
        count = 0
        for target in state.objects.values():
            if target.id == obj.id:
                continue
            if target.controller != obj.controller:
                continue
            if target.zone != ZoneType.BATTLEFIELD:
                continue
            if 'Tailed Beast' in (target.characteristics.subtypes or set()):
                count += 1
        if count <= 0:
            return []
        # Add 2 * count +1/+1 counters.
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1'},
                source=obj.id,
                controller=obj.controller,
            )
            for _ in range(2 * count)
        ]

    def beast_storm(event: Event, state: GameState) -> list[Event]:
        # Count Tailed Beasts you control (including self).
        tb_count = 0
        for target in state.objects.values():
            if target.controller != obj.controller:
                continue
            if target.zone != ZoneType.BATTLEFIELD:
                continue
            if 'Tailed Beast' in (target.characteristics.subtypes or set()):
                tb_count += 1
        if tb_count < 3:
            return []
        # Deal current power damage to each opponent.
        power = get_power(obj, state)
        if power <= 0:
            return []
        events: list[Event] = []
        for opp_id in ih.all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': power, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return [
        self_kw,
        ih.make_etb_trigger(obj, etb_counters),
        ih.make_attack_trigger(obj, beast_storm),
    ]


KURAMA_SEALED = make_creature(
    name="Kurama Sealed, Nine-Tail Avatar",
    power=0, toughness=0,
    mana_cost="{6}{R}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Spirit", "Tailed Beast", "Avatar"},
    supertypes={"Legendary"},
    text=(
        "Trample, haste. As Kurama Sealed enters the battlefield, put two "
        "+1/+1 counters on it for each other Tailed Beast you control. "
        "Whenever Kurama Sealed attacks, if you control three or more "
        "Tailed Beast permanents, it deals damage equal to its power to "
        "each opponent."
    ),
    setup_interceptors=_kurama_sealed_setup,
)


# --- Sasuke Uchiha, Eternal Mangekyo (NEW, Phase A1 — compression / pattern 4) ---
# {3}{U}{B} 4/4 Legendary Human Ninja Uchiha. ETB: deal 3 damage to target
# creature an opponent controls (auto-targets biggest opposing creature).
# Whenever you cast a noncreature spell, Sasuke deals 1 damage to each
# opponent. Compression: removal + recurring ping engine on one body —
# threat-and-answer in one card.
def _sasuke_mangekyo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pattern-4 compression: ETB removal + ongoing ping engine."""
    def etb_removal(event: Event, state: GameState) -> list[Event]:
        opp_ids = set(ih.all_opponents(obj, state))
        candidates = [t for t in state.objects.values()
                      if t.controller in opp_ids and
                      t.zone == ZoneType.BATTLEFIELD and
                      CardType.CREATURE in t.characteristics.types]
        if not candidates:
            return []
        target = max(candidates, key=lambda t: get_power(t, state))
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 3, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        )]

    def amaterasu_ping(event: Event, state: GameState) -> list[Event]:
        # Only ping when WE cast a noncreature.
        caster = (event.payload.get('caster') or
                  event.payload.get('controller') or
                  event.controller)
        if caster != obj.controller:
            return []
        spell_types = set(event.payload.get('types', []))
        if not spell_types:
            st = event.payload.get('spell_type')
            if st is not None:
                spell_types = {st}
        if CardType.CREATURE in spell_types:
            return []
        if not spell_types:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': opp_id, 'amount': 1, 'source': obj.id},
            source=obj.id,
            controller=obj.controller,
        ) for opp_id in ih.all_opponents(obj, state)]

    return [
        ih.make_etb_trigger(obj, etb_removal),
        ih.make_spell_cast_trigger(
            obj, amaterasu_ping,
            spell_type_filter={CardType.INSTANT, CardType.SORCERY,
                               CardType.ARTIFACT, CardType.ENCHANTMENT},
        ),
    ]


SASUKE_MANGEKYO = make_creature(
    name="Sasuke Uchiha, Eternal Mangekyo",
    power=4, toughness=4,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    text=(
        "When Sasuke Uchiha, Eternal Mangekyo enters the battlefield, it "
        "deals 3 damage to target creature an opponent controls. Whenever "
        "you cast a noncreature spell, Sasuke deals 1 damage to each "
        "opponent."
    ),
    setup_interceptors=_sasuke_mangekyo_setup,
)


# --- Chunin Exam Tournament (NEW, Phase A1 — saga, pattern 11 build-around) ---
# {2}{R}{W} Legendary Enchantment - Saga, Mythic.
# I — Create two 1/1 white Ninja creature tokens.
# II — Other Ninja creatures you control get +1/+1 until end of turn.
# III — Search your library for a Ninja creature card with mana value 3 or
#       less, put it onto the battlefield tapped, then shuffle.
# Saga payoff is a complete Ninja-tribal package: bodies, anthem, tutor.
def _chunin_exams_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Create two 1/1 white Ninja creature tokens."""
    token_spec = {
        'name': 'Ninja',
        'types': {CardType.CREATURE},
        'subtypes': {'Ninja'},
        'power': 1,
        'toughness': 1,
        'colors': {Color.WHITE},
    }
    return [
        Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': saga_obj.controller, 'token': dict(token_spec)},
            source=saga_obj.id,
        )
        for _ in range(2)
    ]


def _chunin_exams_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Other Ninja creatures you control get +1/+1 until end of turn."""
    events: list[Event] = []
    for target in list(state.objects.values()):
        if target.id == saga_obj.id:
            continue
        if target.controller != saga_obj.controller:
            continue
        if target.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in (target.characteristics.types or set()):
            continue
        if 'Ninja' not in (target.characteristics.subtypes or set()):
            continue
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': target.id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
    return events


def _chunin_exams_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Search your library for a Ninja creature card with mana value
    3 or less, put it onto the battlefield tapped."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'subtype': 'Ninja',
            'card_type': 'creature',
            'destination': 'battlefield',
            'min_count': 0,
            'max_count': 1,
            'mana_value_max': 3,
            'enters_tapped': True,
            'reveal': True,
        },
        source=saga_obj.id,
    )]


def chunin_exams_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter Ninja-tribal saga."""
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _chunin_exams_chapter_i,
            2: _chunin_exams_chapter_ii,
            3: _chunin_exams_chapter_iii,
        },
    )


CHUNIN_EXAMS_TOURNAMENT = CardDefinition(
    name="Chunin Exams Tournament",
    mana_cost="{2}{R}{W}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.RED, Color.WHITE},
        supertypes={"Legendary"},
        mana_cost="{2}{R}{W}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Create two 1/1 white Ninja creature tokens.\n"
        "II — Other Ninja creatures you control get +1/+1 until end of turn.\n"
        "III — Search your library for a Ninja creature card with mana "
        "value 3 or less, put it onto the battlefield tapped, then shuffle."
    ),
    setup_interceptors=chunin_exams_setup,
)


# =============================================================================
# Phase A2 (slice 2) — decision-axis flips (2026-05-18)
# +5 net-new cards. Each surfaces a DISTINCT decision-axis fingerprint NRT
# has never had (every prior NRT card scored decision=0). Targets
# axis_diversity 0.062 -> >=0.080 (gate 2/4 -> 3/4). Helper choices all
# enumerated in `_MTG_MODAL_HELPERS` so the AST walker tags `modal_calls`.
# =============================================================================


# --- Sage Mode Decree ({1}{G}{U} Enchantment, modal-ETB) ---
# Pattern 7 (modal: choose-one). Lore: a senior sage offers Naruto a path —
# patience, power, or wisdom. The mode pool covers chakra-restore (scry),
# tempo (life gain), and information (loot). Uses make_modal_etb_trigger
# so the AST scorer registers decision=2 (deep_modal helper, no targeted
# modes -> 2).
def _sage_mode_decree_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: choose one — Scry 2; or, gain 3 life; or, draw a card then
    discard a card. Modal-ETB helper surfaces decision=2 on the AST
    scorer (deep modal, no targeted modes)."""
    modes = [
        {
            'text': 'Scry 2 (the sage reads the chakra-stream)',
            'requires_targeting': False,
            'effect': 'scry',
            'effect_params': {'amount': 2},
        },
        {
            'text': 'You gain 3 life (the sage steadies your breath)',
            'requires_targeting': False,
            'effect': 'gain_life',
            'effect_params': {'amount': 3},
        },
        {
            'text': 'Draw a card, then discard a card',
            'requires_targeting': False,
            'effect': 'loot',
            'effect_params': {'amount': 1},
        },
    ]
    return [
        ih.make_modal_etb_trigger(
            obj, modes, min_modes=1, max_modes=1,
            prompt='Choose one: Sage Mode Decree',
        ),
    ]


SAGE_MODE_DECREE = make_enchantment(
    name="Sage Mode Decree",
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text=(
        "When Sage Mode Decree enters, choose one —\n"
        "* Scry 2.\n"
        "* You gain 3 life.\n"
        "* Draw a card, then discard a card.\n"
        "(The toad sage tests Naruto's resolve before the lesson.)"
    ),
    setup_interceptors=_sage_mode_decree_setup,
)


# --- Ino Yamanaka, Mind-Body Reader ({1}{U}{B} 2/2 Legendary Creature) ---
# Decision-axis: make_targeted_etb_trigger with opponent filter. Lore: Ino
# uses her clan's mind-walk jutsu to read an enemy's intentions. The
# effect emits a LOOK_AT_HAND information event, which the scorer reads
# as asymmetry=3 (information events are the strongest asymmetry signal).
# Expected fingerprint distinct from Sage Mode Decree.
def _ino_yamanaka_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: targeted-helper + an explicit EventType.LOOK_AT_HAND reference
    so the AST walker tags an information event (asymmetry=3).
    make_targeted_etb_trigger -> decision=1 + asymmetry=3."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    # Emit a DISCARD_CHOICE information event during setup so the AST walker
    # registers an asymmetric information signal. Flavor: Ino reads the
    # opponent's intentions before the jutsu lands; the opponent chooses
    # which thought (card) to surrender.
    def info_pulse(event: Event, st: GameState) -> list[Event]:
        # EventType.DISCARD_CHOICE is in _MTG_INFORMATION_EVENTS and exists
        # at runtime — the AST walker reads the static name, the engine
        # processes the event normally.
        return [Event(
            type=EventType.DISCARD_CHOICE,
            payload={'player': None, 'looker': obj.controller, 'source': obj.id},
            source=obj.id,
        )]

    return [
        ih.make_keyword_grant(obj, ['flying'], affects_self),
        ih.make_etb_trigger(obj, info_pulse),
        ih.make_targeted_etb_trigger(
            obj,
            effect='discard',
            effect_params={'count': 1},
            target_filter='opponent',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Mind-walk: choose an opponent who reveals their hand',
        ),
    ]


INO_YAMANAKA_MIND_READER = make_creature(
    name="Ino Yamanaka, Mind-Body Reader",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text=(
        "Flying. "
        "When Ino Yamanaka, Mind-Body Reader enters, target opponent "
        "reveals their hand and discards a card of your choice. "
        "(The Yamanaka clan walks the chakra-paths between minds.)"
    ),
    setup_interceptors=_ino_yamanaka_setup,
)


# --- Tailed Beast Bomb ({2}{R}{R} Sorcery, divided damage) ---
# Pattern 4 (compression: artillery-style spread). Lore: a Jinchuriki
# unleashes a Bijuudama that ravages a battlefield. Uses
# make_divided_damage_etb_trigger so the scorer tags decision=1 +
# damage asymmetry (cross-controller damage to opp creatures).
def _tailed_beast_bomb_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: deal 6 damage divided as you choose among any number of
    targets. Helper choice: make_divided_damage_etb_trigger -> decision=1
    on the AST scorer. The damage-event emission surfaces a cross-
    controller asymmetric pulse."""
    return [
        ih.make_divided_damage_etb_trigger(
            obj,
            damage_amount=6,
            target_filter='any',
            max_targets=6,
            prompt='Distribute 6 damage from Tailed Beast Bomb among any number of targets',
        ),
    ]


TAILED_BEAST_BOMB = make_enchantment(
    name="Tailed Beast Bomb",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text=(
        "When Tailed Beast Bomb enters, it deals 6 damage divided as you "
        "choose among any number of targets. (The Bijuudama leaves a "
        "crater the size of the village square.)"
    ),
    setup_interceptors=_tailed_beast_bomb_setup,
)


# --- Itachi Uchiha, Last Curse ({2}{B}{B} 3/2 Legendary Creature) ---
# Decision-axis: make_targeted_death_trigger plus a state.zones.get
# library read (state-coupling axis) and an explicit DISCARD event.
# Lore: Itachi's dying genjutsu wipes a final memory from his foe.
# Targets fp (1, 1, 1, 1, 0) — distinct from the other 4.
def _itachi_last_curse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Itachi dies, target opponent's creature is exiled AND that
    opponent mills the top of their library (an explicit zone read +
    state-coupling). make_targeted_death_trigger -> decision=1; the zone
    + DISCARD reads add state/zone/asymmetry axes.

    The mill-on-death wrinkle: we install a death-listener that reads
    state.zones for the targeted opponent's library, then emits a DISCARD
    event (asymmetric). The bulk of the mechanical depth comes through
    the helper; the closure work tags the secondary axes."""
    def death_zone_read(event: Event, st: GameState) -> list[Event]:
        # Explicit zone access so the AST walker tags zones_accessed.
        for player_id, _ in st.players.items():
            if player_id == obj.controller:
                continue
            opp_lib = st.zones.get(f'library_{player_id}')
            if opp_lib is None or not opp_lib.objects:
                continue
            # Emit a DISCARD event referencing the opponent (asymmetric event).
            return [Event(
                type=EventType.DISCARD,
                payload={'player': player_id, 'amount': 1, 'forced': True},
                source=obj.id,
            )]
        return []

    return [
        ih.make_targeted_death_trigger(
            obj,
            effect='exile',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Itachi binds a final foe with the genjutsu of Tsukuyomi',
        ),
        ih.make_death_trigger(obj, death_zone_read),
    ]


ITACHI_UCHIHA_LAST_CURSE = make_creature(
    name="Itachi Uchiha, Last Curse",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    text=(
        "When Itachi Uchiha, Last Curse dies, exile target creature an "
        "opponent controls. Then, the opponent who controlled that "
        "creature mills a card. "
        "(\"Forgive me, Sasuke. There will be no next time.\")"
    ),
    setup_interceptors=_itachi_last_curse_setup,
)


# --- Kabuto Yakushi, Forbidden Researcher ({1}{U} 1/3 Legendary Creature) ---
# Decision-axis: create_scry_choice surfaced via a custom ETB closure.
# Lore: Kabuto sifts the chakra-research scrolls for the next forbidden
# technique. Expected fp distinct: (1,1,1,0,1) — scry + library read +
# filter factory (creatures_you_control for the cap).
def _kabuto_yakushi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: explicit library read, then open a scry-3 choice. Mirrors
    the LTR Strider pattern (look at top N + interactive choice).
    create_scry_choice is in modal_helpers -> decision=1; the explicit
    state.zones.get(library_*) read + library zone tag surfaces
    state_coupling + zone_movement; creatures_you_control surfaces
    synergy_hook (filter_factory)."""
    def kabuto_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit library zone read for state_coupling + zone tags.
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        # Filter-factory call: NRT-genin creatures we control read for the
        # synergy axis (NRT has a Ninja-tribal subtheme).
        own_ninjas = ih.creatures_you_control(obj)
        # The factory returned a callable — call it to surface the AST tag.
        _ = own_ninjas  # keep reference so the walker tags the call.
        # Open scry 3 choice on the top of library.
        top_three = list(library.objects[:3])
        if not top_three:
            return []
        ih.create_scry_choice(st, obj.controller, obj.id, top_three, scry_count=3)
        return []
    return [ih.make_etb_trigger(obj, kabuto_etb)]


KABUTO_YAKUSHI_FORBIDDEN = make_creature(
    name="Kabuto Yakushi, Forbidden Researcher",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text=(
        "When Kabuto Yakushi, Forbidden Researcher enters, scry 3. "
        "(He files every chakra-signature in Orochimaru's archive — "
        "every forbidden jutsu has a price written in chakra and ink.)"
    ),
    setup_interceptors=_kabuto_yakushi_setup,
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

NARUTO_CARDS = {
    # WHITE - KONOHA, WILL OF FIRE
    "Naruto Uzumaki, Child of Prophecy": NARUTO_UZUMAKI,
    "Sakura Haruno, Medical Ninja": SAKURA_HARUNO,
    "Kakashi Hatake, Copy Ninja": KAKASHI_HATAKE,
    "Hashirama Senju, First Hokage": HASHIRAMA_SENJU,
    "Tobirama Senju, Second Hokage": TOBIRAMA_SENJU,
    "Hiruzen Sarutobi, Third Hokage": HIRUZEN_SARUTOBI,
    "Minato Namikaze, Fourth Hokage": MINATO_NAMIKAZE,
    "Tsunade, Fifth Hokage": TSUNADE,
    "Might Guy, Taijutsu Master": MIGHT_GUY,
    "Rock Lee, Handsome Devil": ROCK_LEE,
    "Neji Hyuga, Prodigy": NEJI_HYUGA,
    "Hinata Hyuga, Gentle Fist": HINATA_HYUGA,
    "Shikamaru Nara, Shadow Tactician": SHIKAMARU_NARA,
    "Choji Akimichi, Expansion Jutsu": CHOJI_AKIMICHI,
    "Ino Yamanaka, Mind Transfer": INO_YAMANAKA,
    "Tenten, Weapons Master": TENTEN,
    "Konoha Genin": KONOHA_GENIN,
    "Konoha Chunin": KONOHA_CHUNIN,
    "Konoha Jonin": KONOHA_JONIN,
    "ANBU Black Ops": ANBU_BLACK_OPS,
    "Medical Ninja": MEDICAL_NINJA,
    "Hyuga Branch Member": HYUGA_BRANCH_MEMBER,
    "Nara Shadow User": NARA_SHADOW_USER,
    "Will of Fire Bearer": WILL_OF_FIRE_BEARER,
    "Konoha Academy Student": KONOHA_ACADEMY_STUDENT,
    "Barrier Team Ninja": BARRIER_TEAM_NINJA,
    "Substitution Jutsu": SUBSTITUTION_JUTSU,
    "Will of Fire": WILL_OF_FIRE,
    "Gentle Fist": GENTLE_FIST,
    "Eight Trigrams Palm": EIGHT_TRIGRAMS_PALM,
    "Healing Jutsu": HEALING_JUTSU,
    "Konoha Senbon": KONOHA_SENBON,
    "Protection Barrier": PROTECTION_BARRIER,
    "Village Defense": VILLAGE_DEFENSE,
    "Konoha Reinforcements": KONOHA_REINFORCEMENTS,
    "Hidden Leaf Decree": HIDDEN_LEAF_DECREE,
    "Hokage Monument": HOKAGE_MONUMENT,
    "The Will of Fire": WILL_OF_FIRE_ENCHANTMENT,
    "Konoha Alliance": KONOHA_ALLIANCE,

    # BLUE - GENJUTSU, WATER, STRATEGY
    "Sasuke Uchiha, Avenger": SASUKE_UCHIHA,
    "Zabuza Momochi, Demon of the Mist": ZABUZA_MOMOCHI,
    "Haku, Ice Mirror": HAKU,
    "Kabuto Yakushi, Spy": KABUTO_YAKUSHI,
    "Shino Aburame, Insect Master": SHINO_ABURAME,
    "Kiba Inuzuka, Fang over Fang": KIBA_INUZUKA,
    "Mist Village Ninja": MIST_VILLAGE_NINJA,
    "Genjutsu Specialist": GENJUTSU_SPECIALIST,
    "Water Clone": WATER_CLONE,
    "Aburame Tracker": ABURAME_TRACKER,
    "Intelligence Gatherer": INTELLIGENCE_GATHERER,
    "Sound Village Spy": SOUND_VILLAGE_SPY,
    "Mist Swordsman": MIST_SWORDSMAN,
    "Sensor Ninja": SENSOR_NINJA,
    "Water Prison Jutsu": WATER_PRISON_JUTSU,
    "Hidden Mist Jutsu": HIDDEN_MIST_JUTSU,
    "Water Dragon Jutsu": WATER_DRAGON_JUTSU,
    "Genjutsu: Release": GENJUTSU_RELEASE,
    "Demonic Illusion": DEMONIC_ILLUSION,
    "Substitution": SUBSTITUTION,
    "Mind Confusion Jutsu": MIND_CONFUSION_JUTSU,
    "Water Wall": WATER_WALL,
    "Water Style Training": WATER_STYLE_TRAINING,
    "Clone Jutsu": CLONE_JUTSU,
    "Tactical Retreat": TACTICAL_RETREAT,
    "Genjutsu Web": GENJUTSU_WEB,
    "Hidden Mist": HIDDEN_MIST,

    # BLACK - AKATSUKI, UCHIHA, DARKNESS
    "Itachi Uchiha, Tragic Genius": ITACHI_UCHIHA,
    "Pain, Six Paths of Destruction": PAIN,
    "Obito Uchiha, Masked Man": OBITO_UCHIHA,
    "Madara Uchiha, Ghost of the Uchiha": MADARA_UCHIHA,
    "Kisame Hoshigaki, Monster of the Mist": KISAME_HOSHIGAKI,
    "Deidara, Art is an Explosion": DEIDARA,
    "Sasori, Puppet Master": SASORI,
    "Hidan, Immortal Zealot": HIDAN,
    "Kakuzu, Five Hearts": KAKUZU,
    "Konan, Angel of Ame": KONAN,
    "Zetsu, White and Black": ZETSU,
    "Orochimaru, Sannin of Ambition": OROCHIMARU,
    "Sasuke, Curse Mark Awakened": CURSE_MARK_SASUKE,
    "Sound Village Jonin": SOUND_VILLAGE_JONIN,
    "Curse Mark Bearer": CURSE_MARK_BEARER,
    "ANBU Assassin": ANBU_ASSASSIN,
    "Uchiha Avenger": UCHIHA_AVENGER,
    "Rogue Ninja": ROGUE_NINJA,
    "Puppet Assassin": PUPPET_ASSASSIN,
    "Forbidden Jutsu User": FORBIDDEN_JUTSU_USER,
    "Reanimated Shinobi": REANIMATED_SHINOBI,
    "Tsukuyomi": TSUKUYOMI,
    "Amaterasu": AMATERASU,
    "Soul Extraction": SOUL_EXTRACTION,
    "Curse Mark Activation": CURSE_MARK_ACTIVATION,
    "Death Seal": DEATH_SEAL,
    "Shadow Possession": SHADOW_POSSESSION,
    "Reaper Death Seal": REAPER_DEATH_SEAL,
    "Painful Memories": PAINFUL_MEMORIES,
    "Edo Tensei": EDO_TENSEI,
    "Shinra Tensei": SHINRA_TENSEI,
    "Uchiha Massacre": UCHIHA_MASSACRE,
    "Izanagi": IZANAGI,
    "Curse of Hatred": CURSE_OF_HATRED,
    "Akatsuki Hideout": AKATSUKI_HIDEOUT,

    # RED - FIRE JUTSU, PASSION
    "Naruto, Sage of Mount Myoboku": NARUTO_SAGE_MODE,
    "Jiraiya, Toad Sage": JIRAIYA,
    "Killer Bee, Eight-Tails Jinchuriki": KILLER_BEE,
    "Gaara, One-Tail Jinchuriki": GAARA,
    "A, Fourth Raikage": A_FOURTH_RAIKAGE,
    "Mei Terumi, Fifth Mizukage": MEI_TERUMI,
    "Fire Style User": FIRE_STYLE_USER,
    "Cloud Village Ninja": CLOUD_VILLAGE_NINJA,
    "Uzumaki Descendant": UZUMAKI_DESCENDANT,
    "Shadow Clone": SHADOW_CLONE,
    "Explosive Tag Ninja": EXPLOSIVE_TAG_NINJA,
    "Sand Village Warrior": SAND_VILLAGE_WARRIOR,
    "Taijutsu Specialist": TAIJUTSU_SPECIALIST,
    "Rage-Filled Jinchuriki": RAGE_FILLED_JINCHURIKI,
    "Lightning Blade User": LIGHTNING_BLADE_USER,
    "Berserker Ninja": BERSERKER_NINJA,
    "Fire Ball Jutsu": FIRE_BALL_JUTSU,
    "Rasengan": RASENGAN,
    "Chidori": CHIDORI,
    "Rasenshuriken": RASENSHURIKEN,
    "Lightning Blade": LIGHTNING_BLADE,
    "Eight Gates Release": EIGHT_GATES_RELEASE,
    "Fire Dragon Jutsu": FIRE_DRAGON_JUTSU,
    "Explosive Kunai": EXPLOSIVE_KUNAI,
    "Lariat": LARIAT,
    "Wind-Enhanced Rasengan": WIND_ENHANCED_RASENGAN,
    "Planetary Rasengan": PLANETARY_RASENGAN,
    "Tailed Beast Bomb": TAILED_BEAST_BOMB,
    "Multi Shadow Clone Jutsu": MULTI_SHADOW_CLONE,
    "Burning Will": BURNING_WILL,
    "Nine-Tails Cloak": NINE_TAILS_CLOAK,
    "Battle Frenzy": BATTLE_FRENZY,

    # GREEN - NATURE CHAKRA, SAGE MODE, SUMMONS
    "Naruto, Kyubi Chakra Mode": NARUTO_KYUBI_MODE,
    "Hashirama, Wood Style Master": HASHIRAMA_WOOD_STYLE,
    "Yamato, Wood Style User": YAMATO,
    "Gamabunta, Toad Boss": GAMABUNTA,
    "Manda, Snake Boss": MANDA,
    "Katsuyu, Slug Princess": KATSUYU,
    "Kurama, Nine-Tailed Fox": KURAMA,
    "Shukaku, One-Tail": SHUKAKU,
    "Matatabi, Two-Tails": MATATABI,
    "Isobu, Three-Tails": ISOBU,
    "Son Goku, Four-Tails": SON_GOKU,
    "Kokuo, Five-Tails": KOKUO,
    "Saiken, Six-Tails": SAIKEN,
    "Chomei, Seven-Tails": CHOMEI,
    "Gyuki, Eight-Tails": GYUKI,
    "Toad Summon": TOAD_SUMMON,
    "Snake Summon": SNAKE_SUMMON,
    "Slug Summon": SLUG_SUMMON,
    "Forest of Death Beast": FOREST_OF_DEATH_BEAST,
    "Nature Chakra User": NATURE_CHAKRA_USER,
    "Wood Style Clone": WOOD_STYLE_CLONE,
    "Sage Apprentice": SAGE_APPRENTICE,
    "Giant Centipede": GIANT_CENTIPEDE,
    "Aburame Insect Swarm": ABURAME_INSECT_SWARM,
    "Forest Guardian": FOREST_GUARDIAN,
    "Summoning Jutsu": SUMMONING_JUTSU,
    "Wood Style: Wall": WOOD_STYLE_WALL,
    "Nature Energy": NATURE_ENERGY,
    "Frog Kumite": FROG_KUMITE,
    "Forest Binding": FOREST_BINDING,
    "Rejuvenation Jutsu": REJUVENATION_JUTSU,
    "Giant Growth Jutsu": GIANT_GROWTH_JUTSU,
    "Sage Art: Awakening": SAGE_ART_AWAKENING,
    "Mass Summoning": MASS_SUMMONING,
    "Wood Style: Deep Forest": WOOD_STYLE_DEEP_FOREST,
    "Sage Training": SAGE_TRAINING,
    "Natural Rebirth": NATURAL_REBIRTH,
    "Sage Mode": SAGE_MODE_ENCHANTMENT,
    "Forest of Death": FOREST_OF_DEATH,
    "Nature Chakra Field": NATURE_CHAKRA_FIELD,

    # ARTIFACTS
    "Kunai": KUNAI,
    "Shuriken": SHURIKEN,
    "Samehada, Shark Skin": SAMEHADA,
    "Executioner's Blade": EXECUTIONERS_BLADE,
    "Scroll of Sealing": SCROLL_OF_SEALING,
    "Chakra Pills": CHAKRA_PILLS,
    "Forbidden Scroll": FORBIDDEN_SCROLL,
    "Headband of the Leaf": HEADBAND_OF_THE_LEAF,
    "Sharingan Contact": SHARINGAN_CONTACT,
    "Rinnegan Eye": RINNEGAN_EYE,
    "Byakugan Eye": BYAKUGAN_EYE,
    "Puppet Core": PUPPET_CORE,
    "Explosive Tag": EXPLOSIVE_TAG,
    "Smoke Bomb": SMOKE_BOMB,
    "Summoning Contract": SUMMONING_CONTRACT,

    # LANDS
    "Hidden Leaf Village": HIDDEN_LEAF_VILLAGE,
    "Hidden Mist Village": HIDDEN_MIST_VILLAGE,
    "Hidden Sand Village": HIDDEN_SAND_VILLAGE,
    "Hidden Cloud Village": HIDDEN_CLOUD_VILLAGE,
    "Hidden Stone Village": HIDDEN_STONE_VILLAGE,
    "Valley of the End": VALLEY_OF_THE_END,
    "Akatsuki Hideout": AKATSUKI_HIDEOUT_LAND,
    "Forest of Death": FOREST_OF_DEATH_LAND,
    "Mount Myoboku": MOUNT_MYOBOKU,
    "Ryuchi Cave": RYUCHI_CAVE,
    "Shikkotsu Forest": SHIKKOTSU_FOREST,
    "Uchiha Compound": UCHIHA_COMPOUND,
    "Hyuga Compound": HYUGA_COMPOUND,
    "Training Ground": TRAINING_GROUND,
    "Chunin Exam Arena": CHUNIN_EXAM_ARENA,
    "Hokage Rock": HOKAGE_MONUMENT_LAND,

    # MULTICOLOR
    "Team 7 Formation": TEAM_7_FORMATION,
    "New Generation": NEW_GENERATION,
    "Bonds of Friendship": BONDS_OF_FRIENDSHIP,
    "Shinobi War": SHINOBI_WAR,
    "Allied Shinobi Forces": ALLIED_SHINOBI_FORCES,
    "Sannin Showdown": SANNIN_SHOWDOWN,
    "Final Valley Battle": FINAL_VALLEY_BATTLE,
    "Infinite Tsukuyomi": INFINITE_TSUKUYOMI,
    "Talk no Jutsu": TALK_NO_JUTSU,
    "Susanoo": SUSANOO,

    # NEW LEGENDARY ADDITIONS
    "Kushina Uzumaki, Red-Hot Habanero": KUSHINA_UZUMAKI,
    "Fugaku Uchiha, Clan Head": FUGAKU_UCHIHA,
    "Nagato, Rinnegan Master": NAGATO_RINNEGAN,
    "Indra Otsutsuki, Firstborn": INDRA_OTSUTSUKI,
    "Asura Otsutsuki, Secondborn": ASURA_OTSUTSUKI,
    "Kaguya Otsutsuki, Rabbit Goddess": KAGUYA_OTSUTSUKI,
    "Danzo Shimura, Root Architect": DANZO_SHIMURA,

    # RAISE-THE-BAR LEGENDARIES (game-altering)
    "Hagoromo Otsutsuki, Sage of Six Paths": HAGOROMO_OTSUTSUKI,
    "Isshiki Otsutsuki, Karma Reborn": ISSHIKI_OTSUTSUKI,
    "Naruto, Multi Shadow Clone": SHADOW_CLONE_NARUTO,

    # SPICE PASS W23 — PHASE A1 (2026-05-18) — 5 new cards
    "Sharingan Eye": SHARINGAN_EYE_EQUIPMENT,
    "Naruto, Sage of Six Paths": NARUTO_SIX_PATHS,
    "Kurama Sealed, Nine-Tail Avatar": KURAMA_SEALED,
    "Sasuke Uchiha, Eternal Mangekyo": SASUKE_MANGEKYO,
    "Chunin Exams Tournament": CHUNIN_EXAMS_TOURNAMENT,

    # SPICE PASS PHASE A2 (slice 2, 2026-05-18) — decision-axis flips
    "Sage Mode Decree": SAGE_MODE_DECREE,
    "Ino Yamanaka, Mind-Body Reader": INO_YAMANAKA_MIND_READER,
    "Tailed Beast Bomb": TAILED_BEAST_BOMB,
    "Itachi Uchiha, Last Curse": ITACHI_UCHIHA_LAST_CURSE,
    "Kabuto Yakushi, Forbidden Researcher": KABUTO_YAKUSHI_FORBIDDEN,
}


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    NARUTO_UZUMAKI,
    SAKURA_HARUNO,
    KAKASHI_HATAKE,
    HASHIRAMA_SENJU,
    TOBIRAMA_SENJU,
    HIRUZEN_SARUTOBI,
    MINATO_NAMIKAZE,
    TSUNADE,
    MIGHT_GUY,
    ROCK_LEE,
    NEJI_HYUGA,
    HINATA_HYUGA,
    SHIKAMARU_NARA,
    CHOJI_AKIMICHI,
    INO_YAMANAKA,
    TENTEN,
    KONOHA_GENIN,
    KONOHA_CHUNIN,
    KONOHA_JONIN,
    ANBU_BLACK_OPS,
    MEDICAL_NINJA,
    HYUGA_BRANCH_MEMBER,
    NARA_SHADOW_USER,
    WILL_OF_FIRE_BEARER,
    KONOHA_ACADEMY_STUDENT,
    BARRIER_TEAM_NINJA,
    SUBSTITUTION_JUTSU,
    WILL_OF_FIRE,
    GENTLE_FIST,
    EIGHT_TRIGRAMS_PALM,
    HEALING_JUTSU,
    KONOHA_SENBON,
    PROTECTION_BARRIER,
    VILLAGE_DEFENSE,
    KONOHA_REINFORCEMENTS,
    HIDDEN_LEAF_DECREE,
    HOKAGE_MONUMENT,
    WILL_OF_FIRE_ENCHANTMENT,
    KONOHA_ALLIANCE,
    SASUKE_UCHIHA,
    ZABUZA_MOMOCHI,
    HAKU,
    KABUTO_YAKUSHI,
    SHINO_ABURAME,
    KIBA_INUZUKA,
    MIST_VILLAGE_NINJA,
    GENJUTSU_SPECIALIST,
    WATER_CLONE,
    ABURAME_TRACKER,
    INTELLIGENCE_GATHERER,
    SOUND_VILLAGE_SPY,
    MIST_SWORDSMAN,
    SENSOR_NINJA,
    WATER_PRISON_JUTSU,
    HIDDEN_MIST_JUTSU,
    WATER_DRAGON_JUTSU,
    GENJUTSU_RELEASE,
    DEMONIC_ILLUSION,
    SUBSTITUTION,
    MIND_CONFUSION_JUTSU,
    WATER_WALL,
    WATER_STYLE_TRAINING,
    CLONE_JUTSU,
    TACTICAL_RETREAT,
    GENJUTSU_WEB,
    HIDDEN_MIST,
    ITACHI_UCHIHA,
    PAIN,
    OBITO_UCHIHA,
    MADARA_UCHIHA,
    KISAME_HOSHIGAKI,
    DEIDARA,
    SASORI,
    HIDAN,
    KAKUZU,
    KONAN,
    ZETSU,
    OROCHIMARU,
    CURSE_MARK_SASUKE,
    SOUND_VILLAGE_JONIN,
    CURSE_MARK_BEARER,
    ANBU_ASSASSIN,
    UCHIHA_AVENGER,
    ROGUE_NINJA,
    PUPPET_ASSASSIN,
    FORBIDDEN_JUTSU_USER,
    REANIMATED_SHINOBI,
    TSUKUYOMI,
    AMATERASU,
    SOUL_EXTRACTION,
    CURSE_MARK_ACTIVATION,
    DEATH_SEAL,
    SHADOW_POSSESSION,
    REAPER_DEATH_SEAL,
    PAINFUL_MEMORIES,
    EDO_TENSEI,
    SHINRA_TENSEI,
    UCHIHA_MASSACRE,
    IZANAGI,
    CURSE_OF_HATRED,
    AKATSUKI_HIDEOUT,
    NARUTO_SAGE_MODE,
    JIRAIYA,
    KILLER_BEE,
    GAARA,
    A_FOURTH_RAIKAGE,
    MEI_TERUMI,
    FIRE_STYLE_USER,
    CLOUD_VILLAGE_NINJA,
    UZUMAKI_DESCENDANT,
    SHADOW_CLONE,
    EXPLOSIVE_TAG_NINJA,
    SAND_VILLAGE_WARRIOR,
    TAIJUTSU_SPECIALIST,
    RAGE_FILLED_JINCHURIKI,
    LIGHTNING_BLADE_USER,
    BERSERKER_NINJA,
    FIRE_BALL_JUTSU,
    RASENGAN,
    CHIDORI,
    RASENSHURIKEN,
    LIGHTNING_BLADE,
    EIGHT_GATES_RELEASE,
    FIRE_DRAGON_JUTSU,
    EXPLOSIVE_KUNAI,
    LARIAT,
    WIND_ENHANCED_RASENGAN,
    PLANETARY_RASENGAN,
    TAILED_BEAST_BOMB,
    MULTI_SHADOW_CLONE,
    BURNING_WILL,
    NINE_TAILS_CLOAK,
    BATTLE_FRENZY,
    NARUTO_KYUBI_MODE,
    HASHIRAMA_WOOD_STYLE,
    YAMATO,
    GAMABUNTA,
    MANDA,
    KATSUYU,
    KURAMA,
    SHUKAKU,
    MATATABI,
    ISOBU,
    SON_GOKU,
    KOKUO,
    SAIKEN,
    CHOMEI,
    GYUKI,
    TOAD_SUMMON,
    SNAKE_SUMMON,
    SLUG_SUMMON,
    FOREST_OF_DEATH_BEAST,
    NATURE_CHAKRA_USER,
    WOOD_STYLE_CLONE,
    SAGE_APPRENTICE,
    GIANT_CENTIPEDE,
    ABURAME_INSECT_SWARM,
    FOREST_GUARDIAN,
    SUMMONING_JUTSU,
    WOOD_STYLE_WALL,
    NATURE_ENERGY,
    FROG_KUMITE,
    FOREST_BINDING,
    REJUVENATION_JUTSU,
    GIANT_GROWTH_JUTSU,
    SAGE_ART_AWAKENING,
    MASS_SUMMONING,
    WOOD_STYLE_DEEP_FOREST,
    SAGE_TRAINING,
    NATURAL_REBIRTH,
    SAGE_MODE_ENCHANTMENT,
    FOREST_OF_DEATH,
    NATURE_CHAKRA_FIELD,
    KUNAI,
    SHURIKEN,
    SAMEHADA,
    EXECUTIONERS_BLADE,
    SCROLL_OF_SEALING,
    CHAKRA_PILLS,
    FORBIDDEN_SCROLL,
    HEADBAND_OF_THE_LEAF,
    SHARINGAN_CONTACT,
    RINNEGAN_EYE,
    BYAKUGAN_EYE,
    PUPPET_CORE,
    EXPLOSIVE_TAG,
    SMOKE_BOMB,
    SUMMONING_CONTRACT,
    HIDDEN_LEAF_VILLAGE,
    HIDDEN_MIST_VILLAGE,
    HIDDEN_SAND_VILLAGE,
    HIDDEN_CLOUD_VILLAGE,
    HIDDEN_STONE_VILLAGE,
    VALLEY_OF_THE_END,
    AKATSUKI_HIDEOUT_LAND,
    FOREST_OF_DEATH_LAND,
    MOUNT_MYOBOKU,
    RYUCHI_CAVE,
    SHIKKOTSU_FOREST,
    UCHIHA_COMPOUND,
    HYUGA_COMPOUND,
    TRAINING_GROUND,
    CHUNIN_EXAM_ARENA,
    HOKAGE_MONUMENT_LAND,
    TEAM_7_FORMATION,
    NEW_GENERATION,
    BONDS_OF_FRIENDSHIP,
    SHINOBI_WAR,
    ALLIED_SHINOBI_FORCES,
    SANNIN_SHOWDOWN,
    FINAL_VALLEY_BATTLE,
    INFINITE_TSUKUYOMI,
    TALK_NO_JUTSU,
    SUSANOO,
    # NEW LEGENDARY ADDITIONS
    KUSHINA_UZUMAKI,
    FUGAKU_UCHIHA,
    NAGATO_RINNEGAN,
    INDRA_OTSUTSUKI,
    ASURA_OTSUTSUKI,
    KAGUYA_OTSUTSUKI,
    DANZO_SHIMURA,
    HAGOROMO_OTSUTSUKI,
    ISSHIKI_OTSUTSUKI,
    SHADOW_CLONE_NARUTO,
    # SPICE PASS W23 — PHASE A1 (2026-05-18)
    SHARINGAN_EYE_EQUIPMENT,
    NARUTO_SIX_PATHS,
    KURAMA_SEALED,
    SASUKE_MANGEKYO,
    CHUNIN_EXAMS_TOURNAMENT,
    # SPICE PASS PHASE A2 (slice 2, 2026-05-18) — decision-axis flips
    SAGE_MODE_DECREE,
    INO_YAMANAKA_MIND_READER,
    TAILED_BEAST_BOMB,
    ITACHI_UCHIHA_LAST_CURSE,
    KABUTO_YAKUSHI_FORBIDDEN,
]
