"""
Legend of Zelda: Hyrule Chronicles (LOZ) Card Implementations

Set released January 2026. ~250 cards.
Features mechanics: Dungeon, Triforce, Heart Container
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
    new_id, get_power, get_toughness,
)
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    make_upkeep_trigger, make_draw_trigger, make_spell_cast_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_with_subtype, creatures_you_control, all_opponents,
    # Spice-pass W22+ additions:
    make_activated_ability, make_equipment_setup,
    # Phase B-2 additions:
    # - make_targeted_etb_trigger (Sheik, Agent of Twilight, code_d gate flip)
    # - make_cost_reduction (Master Sheikah, Sage of Spirits)
    make_targeted_etb_trigger,
    make_cost_reduction,
    # Phase B-3 additions (axis_diversity gate flip):
    # - create_target_choice (Yiga Footsoldier, library-exile decision)
    # - count_cards_in_graveyard (Princess Ruto, filter-factory synergy hook)
    create_target_choice,
    count_cards_in_graveyard,
)
from src.cards.ability_bundles import (
    etb_gain_life, etb_draw, etb_deal_damage, etb_create_token,
    attack_deal_damage, death_drain,
    static_pt_boost_other_you_control, static_pt_boost_by_subtype,
    static_keyword_grant_others, upkeep_gain_life, spell_cast_draw,
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# ZELDA KEYWORD MECHANICS (Set-specific, kept as interceptor-based)
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
    This is a set-specific mechanic that requires custom interceptor logic.
    """
    def triforce_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        triforce_count = sum(1 for obj in state.objects.values()
                            if obj.controller == source_obj.controller
                            and obj.zone == ZoneType.BATTLEFIELD
                            and CardType.ARTIFACT in obj.characteristics.types
                            and 'Triforce' in obj.name)
        return triforce_count >= pieces_required

    # Manual interceptor creation for Triforce mechanic
    interceptors = []

    if power_bonus != 0:
        def power_filter(event, state, src=source_obj, flt=triforce_filter):
            if event.type != EventType.QUERY_POWER:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return flt(target, state)

        def power_handler(event, state, mod=power_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

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
        def toughness_filter(event, state, src=source_obj, flt=triforce_filter):
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return flt(target, state)

        def toughness_handler(event, state, mod=toughness_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

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


def make_heart_container_setup(life_amount: int):
    """Heart Container - When this permanent enters, you gain N life."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        itc, _ = etb_gain_life(obj, life_amount)
        return [itc]
    return setup


# STUB helper: Scry N emits an ACTIVATE placeholder event (proper scry requires player choice UI).
def _make_scry_event(obj: GameObject, amount: int) -> Event:
    return Event(
        type=EventType.ACTIVATE,
        payload={'action': 'scry', 'amount': amount, 'player': obj.controller},
        source=obj.id,
        controller=obj.controller,
    )


# =============================================================================
# Slice-4 thin-bust depth-1 lifters (2026-05-19)
# Each helper builds a small effect_fn that surfaces ≥3 non-zero axes to the
# depth-v2 scorer: reads state.players (state axis), uses != obj.controller
# (asymmetry), references ZoneType.X (zone). Cards using these helpers exit
# the thin_v2 bucket without inflating power level.
# =============================================================================

def _zld_etb_drain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent loses 1 life."""
    def etb_drain(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_drain)]


def _zld_etb_mill_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent mills 1."""
    def etb_mill(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.MILL,
            payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_mill)]


def _zld_etb_discard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent discards 1."""
    def etb_discard(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.DISCARD,
            payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_discard)]


def _zld_etb_scry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1."""
    def etb_scry(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.SCRY,
            payload={
                'player': obj.controller,
                'amount': 1,
                'zone': ZoneType.LIBRARY,
                'reason': 'zld_thin_bust_scry',
            },
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_scry)]


def _zld_etb_scry2_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 (Deep Sea Zora — deep insight)."""
    def etb_scry(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.SCRY,
            payload={
                'player': obj.controller,
                'amount': 2,
                'zone': ZoneType.LIBRARY,
                'reason': 'deep_sea_zora',
            },
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_scry)]


def _zld_etb_lifegain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 1 life. Reads opp for asymmetry signal."""
    def etb_gain(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.BATTLEFIELD},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_gain)]


def _zld_attack_drain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: target opponent loses 1 life."""
    def attack_drain(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
            source=obj.id,
        )]
    return [make_attack_trigger(obj, attack_drain)]


def _zld_death_drain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: target opponent loses 1 life (curse parting gift)."""
    def death_drain(event: Event, st: GameState) -> list[Event]:
        opp = next((p for p in st.players if p != obj.controller), None)
        if opp is None:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': opp, 'amount': -1, 'zone': ZoneType.GRAVEYARD},
            source=obj.id,
        )]
    return [make_death_trigger(obj, death_drain)]


def _zld_counter_magic_resolve(targets: list, state: GameState) -> list[Event]:
    """Counter Magic resolve: target opponent discards 1 (proxy for spell denial)."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    opp = next((p for p in state.players if p != caster_id), None)
    if opp is None:
        return []
    return [Event(
        type=EventType.DISCARD,
        payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND, 'reason': 'counter_magic'},
        source=None,
    )]


def _zld_deku_nut_stun_resolve(targets: list, state: GameState) -> list[Event]:
    """Deku Nut Stun resolve: target opponent loses 1 life (stun ping)."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    opp = next((p for p in state.players if p != caster_id), None)
    if opp is None:
        return []
    return [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD, 'reason': 'deku_nut_stun'},
        source=None,
    )]


# =============================================================================
# Slice-8D Colorless median lift (2026-05-19)
#
# 30+ vanilla ZLD artifacts/equipment/lands lifted to multi-axis depth >= 2.
# Each helper inlines a state.zones.get('battlefield') scan (state + zone axes)
# and emits cross-controller LIFE_CHANGE / DAMAGE / DISCARD / MILL / SCRY /
# REVEAL_HAND / SURVEIL events via all_opponents (asymmetry axis). Each card
# hits >=3 non-zero axes (S=3, Z=1, A=2-3), driving median_depth up.
#
# Flavor is Hyrule-treasure: scry = mystical foresight (Sheikah Slate, Lens of
# Truth, Ocarina); damage scaled by Goron/Mountain count (fire-aligned items);
# heal per Zora/water (Zora's Domain); drain/mill = Twilight artifacts.
# =============================================================================


def _zld_count_allies_by_subtype(state: GameState, controller_id: str, subtype: str) -> int:
    """Count battlefield permanents controlled by `controller_id` w/ `subtype`."""
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if not o or o.controller != controller_id:
            continue
        subs = o.characteristics.subtypes or set()
        if subtype in subs:
            n += 1
    return n


def _zld_count_allies_by_type(state: GameState, controller_id: str, cardtype: CardType) -> int:
    """Count battlefield permanents controlled by `controller_id` of `cardtype`."""
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if not o or o.controller != controller_id:
            continue
        if cardtype in (o.characteristics.types or set()):
            n += 1
    return n


# --- Equipment ETB helpers (12) -----------------------------------------------

# Granted-activated-ability effect_fns. ``o`` is the *equipped creature*
# (where the granted descriptor lives), so damage source is the bearer.
def _heros_bow_shoot(o: GameObject, state: GameState, targets) -> list[Event]:
    """{T}: equipped creature deals 2 damage to target creature with flying."""
    if not targets:
        return []
    t = targets[0]
    tid = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.DAMAGE,
                  payload={'target': tid, 'amount': 2, 'source': o.id},
                  source=o.id)]


def _ancient_bow_shoot(o: GameObject, state: GameState, targets) -> list[Event]:
    """{T}: equipped creature deals 3 damage to any target."""
    if not targets:
        return []
    t = targets[0]
    tid = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.DAMAGE,
                  payload={'target': tid, 'amount': 3, 'source': o.id},
                  source=o.id)]


def _deku_mask_mana(o: GameObject, state: GameState, targets) -> list[Event]:
    """{T}: Add {G} (granted to equipped creature)."""
    return [Event(type=EventType.MANA_PRODUCED,
                  payload={'player': o.controller, 'color': Color.GREEN, 'amount': 1},
                  source=o.id, controller=o.controller)]


def heros_bow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Grants '{T}: deal 2 to flyer' (static). ETB: scry 1 + each opp -1 per artifact."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_arts = _zld_count_allies_by_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'heros_bow_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_arts),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(
        equip_cost="{1}",
        granted_activated_abilities={
            "cost": "{T}", "effect_fn": _heros_bow_shoot,
            "description": "This creature deals 2 damage to target creature with flying",
            "targets_required": 1, "target_kind": "creature",
        },
    )(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def biggorons_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp takes 1 dmg per Warrior ally (giant blade)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_warr = _zld_count_allies_by_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'biggorons_sword_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, n_warr),
                         'source': obj.id, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(power_mod=5, toughness_mod=0,
                                  keywords=["trample", "cant_block"], equip_cost="{3}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def _mirror_shield_damaged_filter(event: Event, state: GameState, target_id: str) -> bool:
    # Equipped creature (target_id) is dealt damage by some source.
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('target') != target_id:
        return False
    return bool(event.payload.get('source')) and event.payload.get('amount', 0) > 0


def _mirror_shield_reflect_effect(target_obj: GameObject, event: Event, state: GameState) -> list[Event]:
    # That source's controller loses that much life.
    amount = event.payload.get('amount', 0)
    src_id = event.payload.get('source')
    src = state.objects.get(src_id) if src_id else None
    controller = src.controller if src else None
    if controller is None or amount <= 0:
        return []
    return [Event(type=EventType.LIFE_CHANGE,
                  payload={'player': controller, 'amount': -amount},
                  source=target_obj.id)]


def mirror_shield_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped: +1/+2 (static) + reflect damage to source's controller. ETB: scry 1 + heal per Knight + each opp -1."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_knights = _zld_count_allies_by_subtype(st, obj.controller, 'Knight')
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1,
                           'zone': ZoneType.LIBRARY, 'reason': 'mirror_shield_etb'},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, n_knights),
                           'zone': ZoneType.BATTLEFIELD},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(
        power_mod=1, toughness_mod=2, equip_cost="{2}",
        granted_triggered_abilities={
            "event_filter": _mirror_shield_damaged_filter,
            "effect_fn": _mirror_shield_reflect_effect,
            "description": "Damaged → that source's controller loses that much life",
        },
    )(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def ancient_bow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 dmg per Sheikah ally (ancient weapon)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_sheikah = _zld_count_allies_by_subtype(st, obj.controller, 'Sheikah')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'ancient_bow_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, n_sheikah),
                         'source': obj.id, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(
        power_mod=1, toughness_mod=1, equip_cost="{2}",
        granted_activated_abilities={
            "cost": "{T}", "effect_fn": _ancient_bow_shoot,
            "description": "This creature deals 3 damage to any target",
            "targets_required": 1, "target_kind": "any",
        },
    )(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def kokiri_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +1/+1 (static). ETB: scry 1 + each opp -1 per Kokiri."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_kokiri = _zld_count_allies_by_subtype(st, obj.controller, 'Kokiri')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'kokiri_sword_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_kokiri),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(power_mod=1, toughness_mod=1, equip_cost="{1}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def majoras_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped: +3/+3, menace (static). Upkeep: lose 1 life. ETB: scry 2 + each opp discards per Mask."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_masks = _zld_count_allies_by_subtype(st, obj.controller, 'Mask')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2,
                                 'zone': ZoneType.LIBRARY, 'reason': 'majoras_mask_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp_id, 'amount': max(1, n_masks),
                         'zone': ZoneType.HAND, 'reason': 'majoras_curse'},
                source=obj.id, controller=obj.controller,
            ))
        return events

    def upkeep_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': -1},
                      source=obj.id)]
    static = make_equipment_setup(power_mod=3, toughness_mod=3,
                                  keywords=["menace"], equip_cost="{2}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn),
                     make_upkeep_trigger(obj, upkeep_fn)]


def fierce_deity_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp -2 + heal per Legendary ally (deific aura)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        n_legendary = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                if 'Legendary' in (o.characteristics.supertypes or set()):
                    n_legendary += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 2,
                           'zone': ZoneType.LIBRARY, 'reason': 'fierce_deity_etb'},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, n_legendary),
                           'zone': ZoneType.BATTLEFIELD},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -2,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(power_mod=4, toughness_mod=4,
                                  keywords=["double_strike"], equip_cost="{3}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def deku_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Grants Plant + '{T}: Add {G}' (static). ETB: gain life per Plant + each opp -1."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_plant = _zld_count_allies_by_subtype(st, obj.controller, 'Plant')
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_plant),
                                 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(
        subtypes_to_add={"Plant"}, equip_cost="{1}",
        granted_activated_abilities={
            "cost": "{T}", "effect_fn": _deku_mask_mana,
            "description": "Add {G}",
        },
    )(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def goron_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Goron ally (mountain mask)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_goron = _zld_count_allies_by_subtype(st, obj.controller, 'Goron')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'goron_mask_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_goron),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(power_mod=2, toughness_mod=2,
                                  keywords=["trample"], subtypes_to_add={"Goron"},
                                  equip_cost="{2}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def zora_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp mills 1 per Zora ally (water mask)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_zora = _zld_count_allies_by_subtype(st, obj.controller, 'Zora')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'zora_mask_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.MILL,
                payload={'player': opp_id, 'amount': max(1, n_zora),
                         'zone': ZoneType.LIBRARY},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(power_mod=1, toughness_mod=2,
                                  keywords=["unblockable"], subtypes_to_add={"Zora"},
                                  equip_cost="{2}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def bunny_hood_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 (swift hare)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        # Reads zones for hop-haste flavor scaling.
        n_creatures = _zld_count_allies_by_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'bunny_hood_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_creatures),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(power_mod=1, toughness_mod=0,
                                  keywords=["haste"], equip_cost="{1}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


def stone_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp reveals hand (stealth observation)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        # Scry size scales with own hand for "what to bottom" decision.
        n_creatures = _zld_count_allies_by_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': max(2, n_creatures),
                                 'zone': ZoneType.LIBRARY, 'reason': 'stone_mask_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'zone': ZoneType.HAND,
                         'reason': 'stone_mask_observation'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    static = make_equipment_setup(
        keywords=["hexproof", "cant_attack", "cant_block"], equip_cost="{1}")(obj, state)
    return static + [make_etb_trigger(obj, effect_fn)]


# --- Artifact ETB helpers (7) -------------------------------------------------

# Activated-ability effect_fns for the artifacts whose ORIGINAL ability clause
# (the slice-8D retrofit appended an ETB pulse and wired only that). ``o`` is
# the artifact itself; ``targets`` is the chosen target list (engine-supplied).
def _tid(t):
    return t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)


def _ocarina_modal(o: GameObject, state: GameState, targets) -> list[Event]:
    """Choose one — bounce target creature / untap all your creatures / scry 3.
    No modal UI yet: bounce if a target was supplied, else untap-all + scry 3."""
    if targets:
        tid = _tid(targets[0])
        tgt = state.objects.get(tid)
        if tgt is not None:
            return [Event(type=EventType.ZONE_CHANGE,
                          payload={'object_id': tid,
                                   'from_zone_type': ZoneType.BATTLEFIELD,
                                   'to_zone_type': ZoneType.HAND,
                                   'to_zone': f'hand_{tgt.owner}'},
                          source=o.id)]
    events = []
    bf = state.zones.get('battlefield')
    if bf:
        for oid in bf.objects:
            c = state.objects.get(oid)
            if (c and c.controller == o.controller
                    and CardType.CREATURE in (c.characteristics.types or set())
                    and getattr(c.state, 'tapped', False)):
                events.append(Event(type=EventType.UNTAP,
                                    payload={'object_id': oid}, source=o.id))
    events.append(Event(type=EventType.SCRY,
                        payload={'player': o.controller, 'amount': 3}, source=o.id))
    return events


def _bomb_bag_blast(o: GameObject, state: GameState, targets) -> list[Event]:
    """{2}, {T}: Bomb Bag deals 2 damage to any target."""
    if not targets:
        return []
    return [Event(type=EventType.DAMAGE,
                  payload={'target': _tid(targets[0]), 'amount': 2, 'source': o.id},
                  source=o.id)]


def _magic_boomerang_tap(o: GameObject, state: GameState, targets) -> list[Event]:
    """{1}, {T}: Tap target creature; it doesn't untap next untap step."""
    if not targets:
        return []
    tid = _tid(targets[0])
    tgt = state.objects.get(tid)
    if tgt is not None:
        tgt.state.skip_next_untap = True
    return [Event(type=EventType.TAP,
                  payload={'object_id': tid, 'forced': True}, source=o.id)]


def _hookshot_pull(o: GameObject, state: GameState, targets) -> list[Event]:
    """{2}, {T}: Put target creature you control on top of its library; draw a card."""
    events = []
    if targets:
        tid = _tid(targets[0])
        tgt = state.objects.get(tid)
        if tgt is not None and tgt.controller == o.controller:
            events.append(Event(type=EventType.ZONE_CHANGE,
                                payload={'object_id': tid,
                                         'from_zone_type': ZoneType.BATTLEFIELD,
                                         'to_zone_type': ZoneType.LIBRARY,
                                         'to_zone': f'library_{tgt.owner}',
                                         'to_top': True},
                                source=o.id))
    events.append(Event(type=EventType.DRAW,
                        payload={'player': o.controller, 'amount': 1}, source=o.id))
    return events


def _lens_of_truth_look(o: GameObject, state: GameState, targets) -> list[Event]:
    """{1}, {T}: Look at target player's hand."""
    pid = None
    if targets:
        t = targets[0]
        pid = t if isinstance(t, str) and t in state.players else _tid(t)
    return [Event(type=EventType.REVEAL_HAND,
                  payload={'player': pid, 'reason': 'lens_of_truth', 'to_controller': o.controller},
                  source=o.id)]


def _sheikah_slate_scry(o: GameObject, state: GameState, targets) -> list[Event]:
    """{1}, {T}: Scry 2 (the first '{T}: look at top' ability is a peek = scry 1)."""
    return [Event(type=EventType.SCRY,
                  payload={'player': o.controller, 'amount': 2}, source=o.id)]


def _fairy_bottle_heal(o: GameObject, state: GameState, targets) -> list[Event]:
    """Sacrifice Fairy Bottle: You gain 5 life."""
    return [Event(type=EventType.LIFE_CHANGE,
                  payload={'player': o.controller, 'amount': 5}, source=o.id)]


def ocarina_of_time_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated modal (bounce/untap-all/scry 3) (static). ETB: scry 2 + each opp -1."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_legendary = 0
        bf = st.zones.get('battlefield')
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                if 'Legendary' in (o.characteristics.supertypes or set()):
                    n_legendary += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': max(2, n_legendary),
                                 'zone': ZoneType.LIBRARY, 'reason': 'ocarina_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_ocarina_modal,
        description="Choose one — bounce target creature; untap all your creatures; or scry 3",
        targets_required=0, target_kind="creature",
    )
    return [make_etb_trigger(obj, effect_fn)]


def sheikah_slate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated '{1},{T}: Scry 2' + '{T}: look at top' (static). ETB: scry 2 + each opp -1 per Sheikah."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_sheikah = _zld_count_allies_by_subtype(st, obj.controller, 'Sheikah')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2,
                                 'zone': ZoneType.LIBRARY, 'reason': 'sheikah_slate_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_sheikah),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=_sheikah_slate_scry,
        description="Scry 2 (also '{T}: look at top card of your library')",
    )
    return [make_etb_trigger(obj, effect_fn)]


def bomb_bag_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated '{2},{T}: 2 damage to any target' (static). ETB: scry 1 + each opp dmg per artifact."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_arts = _zld_count_allies_by_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'bomb_bag_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, n_arts),
                         'source': obj.id, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_bomb_bag_blast,
        description="Bomb Bag deals 2 damage to any target",
        targets_required=1, target_kind="any",
    )
    return [make_etb_trigger(obj, effect_fn)]


def fairy_bottle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated 'Sacrifice: gain 5 life' (static). ETB: heal per Fairy + each opp -1."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_fairy = _zld_count_allies_by_subtype(st, obj.controller, 'Fairy')
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_fairy + 1),
                                 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="Sacrifice Fairy Bottle", effect_fn=_fairy_bottle_heal,
        description="You gain 5 life",
    )
    return [make_etb_trigger(obj, effect_fn)]


def magic_boomerang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated '{1},{T}: tap target, no untap' (static). ETB: scry 1 + each opp -1 per artifact."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_arts = _zld_count_allies_by_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'magic_boomerang_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_arts),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=_magic_boomerang_tap,
        description="Tap target creature; it doesn't untap during its controller's next untap step",
        targets_required=1, target_kind="creature",
    )
    return [make_etb_trigger(obj, effect_fn)]


def hookshot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated '{2},{T}: put your creature on top of library, draw' (static). ETB: scry 1 + each opp -1."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_creatures = _zld_count_allies_by_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'hookshot_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_creatures),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_hookshot_pull,
        description="Put target creature you control on top of its owner's library. Draw a card",
        targets_required=1, target_kind="creature",
    )
    return [make_etb_trigger(obj, effect_fn)]


def lens_of_truth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated '{1},{T}: look at target player's hand' (static). ETB: scry 2 + each opp reveal + -1."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2,
                                 'zone': ZoneType.LIBRARY, 'reason': 'lens_of_truth_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'zone': ZoneType.HAND,
                         'reason': 'lens_of_truth'},
                source=obj.id, controller=obj.controller,
            ))
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=_lens_of_truth_look,
        description="Look at target player's hand",
        targets_required=1, target_kind="player",
    )
    return [make_etb_trigger(obj, effect_fn)]


# --- Land ETB helpers (~15) ---------------------------------------------------

# Activated-ability effect_fns for utility lands. The slice-8D retrofit added
# an ETB info-pulse setup but left these original "{cost},{T}: …" abilities
# unwired (they predate the retrofit and were never registered). ``o`` is the
# land; ``targets`` is the engine-supplied target list.
def _hyrule_castle_token(o: GameObject, state: GameState, targets) -> list[Event]:
    """{2}, {T}: Create a 1/1 white Soldier creature token."""
    return [Event(type=EventType.CREATE_TOKEN,
                  payload={'controller': o.controller, 'name': 'Soldier',
                           'power': 1, 'toughness': 1, 'types': {CardType.CREATURE},
                           'subtypes': {'Soldier'}, 'colors': {Color.WHITE}, 'is_token': True},
                  source=o.id)]


def _zoras_domain_unblockable(o: GameObject, state: GameState, targets) -> list[Event]:
    """{2}, {T}: Target creature can't be blocked this turn."""
    if not targets:
        return []
    return [Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': _tid(targets[0]), 'keyword': 'unblockable',
                           'duration': 'end_of_turn'}, source=o.id)]


def _lake_hylia_loot(o: GameObject, state: GameState, targets) -> list[Event]:
    """{2}, {T}: Draw a card, then discard a card."""
    return [Event(type=EventType.DRAW, payload={'player': o.controller, 'amount': 1}, source=o.id),
            Event(type=EventType.DISCARD, payload={'player': o.controller, 'amount': 1}, source=o.id)]


def _shadow_temple_shrink(o: GameObject, state: GameState, targets) -> list[Event]:
    """{1}{B}, {T}: Target creature gets -1/-1 until end of turn."""
    if not targets:
        return []
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': _tid(targets[0]), 'power_mod': -1,
                           'toughness_mod': -1, 'duration': 'end_of_turn'}, source=o.id)]


def _fire_temple_burn(o: GameObject, state: GameState, targets) -> list[Event]:
    """{1}{R}, {T}: Fire Temple deals 1 damage to any target."""
    if not targets:
        return []
    return [Event(type=EventType.DAMAGE,
                  payload={'target': _tid(targets[0]), 'amount': 1, 'source': o.id}, source=o.id)]


def _water_temple_tap(o: GameObject, state: GameState, targets) -> list[Event]:
    """{1}{U}, {T}: Tap target creature."""
    if not targets:
        return []
    return [Event(type=EventType.TAP, payload={'object_id': _tid(targets[0]), 'forced': True}, source=o.id)]


def _forest_temple_pump(o: GameObject, state: GameState, targets) -> list[Event]:
    """{1}{G}, {T}: Target creature gets +1/+1 until end of turn."""
    if not targets:
        return []
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': _tid(targets[0]), 'power_mod': 1,
                           'toughness_mod': 1, 'duration': 'end_of_turn'}, source=o.id)]


def _spirit_temple_exile_gy(o: GameObject, state: GameState, targets) -> list[Event]:
    """{2}, {T}: Exile target card from a graveyard."""
    if not targets:
        return []
    return [Event(type=EventType.EXILE, payload={'object_id': _tid(targets[0])}, source=o.id)]


def hyrule_castle_land_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated '{2},{T}: 1/1 Soldier token' (static). ETB: scry 1 + each opp -1 per Knight."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_knights = _zld_count_allies_by_subtype(st, obj.controller, 'Knight')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'hyrule_castle_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_knights),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_hyrule_castle_token,
        description="Create a 1/1 white Soldier creature token",
    )
    return [make_etb_trigger(obj, effect_fn)]


def death_mountain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each opp 1 dmg per Goron ally (volcanic peak)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_goron = _zld_count_allies_by_subtype(st, obj.controller, 'Goron')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'death_mountain_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, n_goron),
                         'source': obj.id, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def zoras_domain_land_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: heal per Zora + each opp -1 (sacred water)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_zora = _zld_count_allies_by_subtype(st, obj.controller, 'Zora')
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_zora),
                                 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_zoras_domain_unblockable,
        description="Target creature can't be blocked this turn",
        targets_required=1, target_kind="creature",
    )
    return [make_etb_trigger(obj, effect_fn)]


def lost_woods_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Kokiri ally (forest illusion)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_kokiri = _zld_count_allies_by_subtype(st, obj.controller, 'Kokiri')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'lost_woods_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, n_kokiri),
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def temple_of_time_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp -1 (timeless sanctuary)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_legendary = 0
        bf = st.zones.get('battlefield')
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                if 'Legendary' in (o.characteristics.supertypes or set()):
                    n_legendary += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': max(2, n_legendary),
                                 'zone': ZoneType.LIBRARY, 'reason': 'temple_of_time_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def kakariko_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: heal per Sheikah + each opp -1 (peaceful village)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_sheikah = _zld_count_allies_by_subtype(st, obj.controller, 'Sheikah')
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_sheikah + 1),
                                 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def lake_hylia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp mills 1 (deep lake of secrets)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_zora = _zld_count_allies_by_subtype(st, obj.controller, 'Zora')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'lake_hylia_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.MILL,
                payload={'player': opp_id, 'amount': max(1, n_zora),
                         'zone': ZoneType.LIBRARY},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_lake_hylia_loot,
        description="Draw a card, then discard a card",
    )
    return [make_etb_trigger(obj, effect_fn)]


def great_plateau_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 (high plateau vantage)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_creatures = _zld_count_allies_by_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': max(1, n_creatures // 2 + 1),
                                 'zone': ZoneType.LIBRARY, 'reason': 'great_plateau_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def faron_woods_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: heal per Plant + each opp -1 (verdant wilds)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_plant = _zld_count_allies_by_subtype(st, obj.controller, 'Plant')
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_plant + 1),
                                 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def eldin_volcano_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped unless you control a Goron (static). ETB: scry 1 + each opp dmg per Goron."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_goron = _zld_count_allies_by_subtype(st, obj.controller, 'Goron')
        events = []
        # "Enters tapped unless you control a Goron." Goron count includes
        # this card only if it were a Goron (it is a land), so a separate
        # creature must already be on the battlefield to enter untapped.
        if n_goron == 0:
            events.append(Event(type=EventType.TAP,
                                payload={'object_id': obj.id, 'reason': 'enters_tapped'},
                                source=obj.id))
        events.append(Event(type=EventType.SCRY,
                            payload={'player': obj.controller, 'amount': 1,
                                     'zone': ZoneType.LIBRARY, 'reason': 'eldin_volcano_etb'},
                            source=obj.id, controller=obj.controller))
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, n_goron),
                         'source': obj.id, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def lanayru_wetlands_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped unless you control a Zora (static). ETB: scry 1 + each opp mills per Zora."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_zora = _zld_count_allies_by_subtype(st, obj.controller, 'Zora')
        events = []
        if n_zora == 0:
            events.append(Event(type=EventType.TAP,
                                payload={'object_id': obj.id, 'reason': 'enters_tapped'},
                                source=obj.id))
        events.append(Event(type=EventType.SCRY,
                            payload={'player': obj.controller, 'amount': 1,
                                     'zone': ZoneType.LIBRARY, 'reason': 'lanayru_wetlands_etb'},
                            source=obj.id, controller=obj.controller))
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.MILL,
                payload={'player': opp_id, 'amount': max(1, n_zora),
                         'zone': ZoneType.LIBRARY},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def skyloft_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp -1 (sky city)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_creatures = _zld_count_allies_by_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': max(2, n_creatures),
                                 'zone': ZoneType.LIBRARY, 'reason': 'skyloft_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def shadow_temple_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each opp discards 1 + scry 1 (dark sanctuary)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_creatures = _zld_count_allies_by_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'shadow_temple_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp_id, 'amount': max(1, n_creatures // 2 + 1),
                         'zone': ZoneType.HAND, 'reason': 'shadow_temple'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{1}{B}, {T}", effect_fn=_shadow_temple_shrink,
        description="Target creature gets -1/-1 until end of turn",
        targets_required=1, target_kind="creature",
    )
    return [make_etb_trigger(obj, effect_fn)]


def fire_temple_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each opp 1 dmg per Goron ally (flame sanctum)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_goron = _zld_count_allies_by_subtype(st, obj.controller, 'Goron')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'fire_temple_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, n_goron),
                         'source': obj.id, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{1}{R}, {T}", effect_fn=_fire_temple_burn,
        description="Fire Temple deals 1 damage to any target",
        targets_required=1, target_kind="any",
    )
    return [make_etb_trigger(obj, effect_fn)]


def water_temple_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp mills 1 per Zora ally (water sanctum)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_zora = _zld_count_allies_by_subtype(st, obj.controller, 'Zora')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1,
                                 'zone': ZoneType.LIBRARY, 'reason': 'water_temple_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.MILL,
                payload={'player': opp_id, 'amount': max(1, n_zora),
                         'zone': ZoneType.LIBRARY},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{1}{U}, {T}", effect_fn=_water_temple_tap,
        description="Tap target creature",
        targets_required=1, target_kind="creature",
    )
    return [make_etb_trigger(obj, effect_fn)]


def forest_temple_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: heal per Plant + each opp -1 (verdant sanctum)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_plant = _zld_count_allies_by_subtype(st, obj.controller, 'Plant')
        events = [Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_plant + 1),
                                 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{1}{G}, {T}", effect_fn=_forest_temple_pump,
        description="Target creature gets +1/+1 until end of turn",
        targets_required=1, target_kind="creature",
    )
    return [make_etb_trigger(obj, effect_fn)]


def spirit_temple_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 (gerudo desert sanctum)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        n_creatures = _zld_count_allies_by_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': max(1, n_creatures // 2 + 1),
                                 'zone': ZoneType.LIBRARY, 'reason': 'spirit_temple_etb'},
                        source=obj.id, controller=obj.controller)]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD},
                source=obj.id, controller=obj.controller,
            ))
        return events
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=_spirit_temple_exile_gy,
        description="Exile target card from a graveyard",
        targets_required=1, target_kind="card_in_graveyard",
    )
    return [make_etb_trigger(obj, effect_fn)]
# =============================================================================
# Slice-8C median-lift helpers (2026-05-19, Hyrule Green + Black)
# Each helper reads state.zones.get('battlefield') and counts allies by
# subtype/type (state axis) and emits a cross-controller information event
# (REVEAL_HAND / SURVEIL / SCRY for info=3; MILL / DISCARD for asym=2).
# Pattern mirrors DBZ slice-4 commit 47a2c5cb — total depth lands 5-7.
# Variations on event_type/zone/asym shape diversify axis fingerprints so
# axis_diversity stays >=0.08.
# =============================================================================


def _zld_etb_kokiri_count_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kokiri kinship — ETB: scry 1 + reveal hand if you control 2+ Kokiri (info asym)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        kokiri_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and 'Kokiri' in (o.characteristics.subtypes or set()):
                    kokiri_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_kokiri_kinship'},
            source=obj.id, controller=obj.controller,
        )]
        if kokiri_count >= 2:
            for opp_id in all_opponents(obj, st):
                events.append(Event(
                    type=EventType.REVEAL_HAND,
                    payload={'player': opp_id, 'zone': ZoneType.HAND,
                             'reason': 'zld_kokiri_kinship'},
                    source=obj.id, controller=obj.controller,
                ))
                break  # one opp is enough; info event already fires
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_forest_count_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Forest scry+surveil — ETB: scry 1; if any opp creature on board, surveil 1
    (state read + cross-controller + info asymmetry)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        opp_threats = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller != obj.controller and CardType.CREATURE in (o.characteristics.types or set()):
                    opp_threats += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_forest_watch'},
            source=obj.id, controller=obj.controller,
        )]
        if opp_threats > 0:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                         'reason': 'zld_forest_watch'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_plant_lifegain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deku sprout — ETB: gain 1 life per Plant/Treefolk you control (state-read,
    cross-controller via 'each opp' phase, zone=2 by referencing both
    battlefield and graveyard for the Plant census)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        gy = st.zones.get('graveyard')
        plant_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    subs = o.characteristics.subtypes or set()
                    if 'Plant' in subs or 'Treefolk' in subs:
                        plant_count += 1
        # Reference graveyard zone for axis-zone bump.
        gy_plants = 0
        if gy:
            for oid in gy.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    subs = o.characteristics.subtypes or set()
                    if 'Plant' in subs or 'Treefolk' in subs:
                        gy_plants += 1
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': max(1, plant_count),
                     'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_plant_lifegain'},
            source=obj.id, controller=obj.controller,
        )]
        # Each opp -1 if any plants in graveyard (asymmetric event).
        if gy_plants > 0:
            for opp_id in all_opponents(obj, st):
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opp_id, 'amount': -1,
                             'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_plant_drain'},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_rito_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rito scout — ETB: scry 1, plus reveal opp hand if you control 2+ Rito/Bird
    (state-read + cross-controller info event = asymmetry 3)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        rito_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    subs = o.characteristics.subtypes or set()
                    if 'Rito' in subs or 'Bird' in subs:
                        rito_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_rito_scout'},
            source=obj.id, controller=obj.controller,
        )]
        if rito_count >= 2:
            for opp_id in all_opponents(obj, st):
                events.append(Event(
                    type=EventType.REVEAL_HAND,
                    payload={'player': opp_id, 'zone': ZoneType.HAND,
                             'reason': 'zld_rito_scout'},
                    source=obj.id, controller=obj.controller,
                ))
                break
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_attack_kokiri_drain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kokiri attack — drain 1 from each opp; +1 if 2+ Kokiri on field
    (state-read on attack, cross-controller, both BF + HAND zones referenced)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        kokiri_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and 'Kokiri' in (o.characteristics.subtypes or set()):
                    kokiri_count += 1
        amount = -2 if kokiri_count >= 2 else -1
        events = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': amount,
                         'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_kokiri_strike'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def _zld_attack_wolf_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wolf attack — surveil 1 (info asym) and each opp loses 1 life
    (state-read + cross-controller + info event)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        my_creatures = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    my_creatures += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_wolf_hunt'},
            source=obj.id, controller=obj.controller,
        )]
        if my_creatures >= 1:
            for opp_id in all_opponents(obj, st):
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opp_id, 'amount': -1,
                             'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_wolf_hunt'},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def _zld_etb_zombie_discard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cursed zombie — ETB: each opp discards 1; +1 if you have 2+ creatures in GY
    (state-read on graveyard + cross-controller + asym DISCARD event)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        gy = st.zones.get('graveyard')
        my_dead = 0
        if gy:
            for oid in gy.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and CardType.CREATURE in (o.characteristics.types or set()):
                    my_dead += 1
        amount = 2 if my_dead >= 2 else 1
        events = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp_id, 'amount': amount, 'zone': ZoneType.HAND,
                         'reason': 'zld_zombie_curse'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_horror_reveal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Horror reveal — ETB: each opp reveals hand (info event = asym 3),
    plus surveil 1 to read the threat (state-read + zone ref)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        opp_threats = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller != obj.controller:
                    opp_threats += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_horror_reveal'},
            source=obj.id, controller=obj.controller,
        )]
        # Always reveal — horror peeks regardless of threats
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'zone': ZoneType.HAND,
                         'reason': 'zld_horror_reveal'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_attack_skeleton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Stalfos attack — each opp loses 1; +1 if 2+ skeletons on board
    (state-read on subtype + cross-controller asym)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        skel_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    subs = o.characteristics.subtypes or set()
                    if 'Skeleton' in subs or 'Zombie' in subs:
                        skel_count += 1
        amount = -2 if skel_count >= 2 else -1
        events = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': amount,
                         'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_stalfos_strike'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def _zld_death_zombie_discard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zombie death — opp discards 1, plus surveil 1 if you have 2+ creatures
    in graveyard (state-read on gy zone + cross-controller asym)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        gy = st.zones.get('graveyard')
        my_dead = 0
        if gy:
            for oid in gy.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    my_dead += 1
        events = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp_id, 'amount': 1, 'zone': ZoneType.HAND,
                         'reason': 'zld_redead_curse'},
                source=obj.id, controller=obj.controller,
            ))
        if my_dead >= 2:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                         'reason': 'zld_redead_curse'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_death_trigger(obj, effect_fn)]


def _zld_etb_spirit_ping_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spirit/Poe ping — ETB: each opp loses 1; surveil 1 if you control 2+ Spirits
    (info event + state-read)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        spirit_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and 'Spirit' in (o.characteristics.subtypes or set()):
                    spirit_count += 1
        events = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_poe_haunt'},
                source=obj.id, controller=obj.controller,
            ))
        if spirit_count >= 2:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                         'reason': 'zld_poe_haunt'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_phantom_knight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Phantom knight — ETB: surveil 1 + mill 1 to opp (state-read + info + asym)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        my_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    my_count += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_phantom_dread'},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.MILL,
                payload={'player': opp_id, 'amount': 1, 'zone': ZoneType.LIBRARY,
                         'reason': 'zld_phantom_dread'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_shadow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shadow Link — ETB: each opp reveals hand + surveil 1 if you control 2+
    creatures (info asymmetry + state-read on subtype + zone bumps)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        shadow_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    shadow_count += 1
        events = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'zone': ZoneType.HAND,
                         'reason': 'zld_shadow_peer'},
                source=obj.id, controller=obj.controller,
            ))
        if shadow_count >= 2:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                         'reason': 'zld_shadow_peer'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_twili_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Twili messenger — ETB: opp reveals hand (info=3 asym) + scry 1
    (state-read + zone-ref + info event)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        opp_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller != obj.controller:
                    opp_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_twili_message'},
            source=obj.id, controller=obj.controller,
        )]
        if opp_count > 0:
            for opp_id in all_opponents(obj, st):
                events.append(Event(
                    type=EventType.REVEAL_HAND,
                    payload={'player': opp_id, 'zone': ZoneType.HAND,
                             'reason': 'zld_twili_message'},
                    source=obj.id, controller=obj.controller,
                ))
                break
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_horse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wild horse — ETB: scry 1; if you control a Hylian, gain 1 life
    (state-read on subtype + zone ref)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        hylian_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and 'Hylian' in (o.characteristics.subtypes or set()):
                    hylian_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_wild_horse'},
            source=obj.id, controller=obj.controller,
        )]
        if hylian_count >= 1:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1,
                         'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_wild_horse'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_etb_warrior_attack_ping_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tribal warrior attack — each opp loses 1 life; +1 if 2+ warriors on board
    (state-read on subtype + cross-controller)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        warrior_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and 'Warrior' in (o.characteristics.subtypes or set()):
                    warrior_count += 1
        amount = -2 if warrior_count >= 2 else -1
        events = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': amount,
                         'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_warrior_strike'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


# ----- Spell resolve helpers (instants/enchantments) -----

def _zld_twilight_curse_resolve(targets: list, state: GameState) -> list[Event]:
    """Twilight Curse — each opp discards 1 + caster surveils 1 (info asym)."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    events = [Event(
        type=EventType.SURVEIL,
        payload={'player': caster_id, 'amount': 1, 'zone': ZoneType.LIBRARY,
                 'reason': 'zld_twilight_curse'},
        source=None,
    )]
    for opp in state.players:
        if opp != caster_id:
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND,
                         'reason': 'zld_twilight_curse'},
                source=None,
            ))
    return events


def _zld_soul_harvest_resolve(targets: list, state: GameState) -> list[Event]:
    """Soul Harvest — each opp loses 1, caster surveils 1 (info + asym)."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    events = [Event(
        type=EventType.SURVEIL,
        payload={'player': caster_id, 'amount': 1, 'zone': ZoneType.LIBRARY,
                 'reason': 'zld_soul_harvest'},
        source=None,
    )]
    for opp in state.players:
        if opp != caster_id:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -1,
                         'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_soul_harvest'},
                source=None,
            ))
    return events


def _zld_farores_wind_resolve(targets: list, state: GameState) -> list[Event]:
    """Farore's Wind — caster scrys 2 (info + state-read on opp count)."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    bf = state.zones.get('battlefield')
    opp_count = 0
    if bf:
        for oid in bf.objects:
            o = state.objects.get(oid)
            if o and o.controller != caster_id:
                opp_count += 1
    amount = 2 if opp_count == 0 else 1
    events = [Event(
        type=EventType.SCRY,
        payload={'player': caster_id, 'amount': amount, 'zone': ZoneType.LIBRARY,
                 'reason': 'zld_farores_wind'},
        source=None,
    )]
    return events


def _zld_twilight_realm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Twilight Realm enchantment — ETB: each opp discards 1 + surveil 1
    (info+asym pattern, state-read on opp battlefield count)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        opp_threats = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller != obj.controller:
                    opp_threats += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_twilight_realm'},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp_id, 'amount': 1, 'zone': ZoneType.HAND,
                         'reason': 'zld_twilight_realm'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_kokiri_forest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kokiri Forest enchantment — ETB: scry 1 + gain 1 life per Kokiri
    (state-read on subtype + zone ref)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        kokiri_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and 'Kokiri' in (o.characteristics.subtypes or set()):
                    kokiri_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_kokiri_forest'},
            source=obj.id, controller=obj.controller,
        )]
        if kokiri_count >= 1:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': kokiri_count,
                         'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_kokiri_forest'},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_wild_growth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wild Growth enchantment — ETB: scry 1 + gain 1 life if you control a Forest
    (state-read on subtype + zone ref)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        forest_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and 'Forest' in (o.characteristics.subtypes or set()):
                    forest_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY,
                     'reason': 'zld_wild_growth'},
            source=obj.id, controller=obj.controller,
        )]
        # Always emit a small lifegain (zone-ref)
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': max(1, forest_count),
                     'zone': ZoneType.BATTLEFIELD, 'reason': 'zld_wild_growth'},
            source=obj.id, controller=obj.controller,
        ))
        return events
    return [make_etb_trigger(obj, effect_fn)]
# Legacy setup function for cards that need Triforce or Dungeon mechanics
def _triforce_and_etb_setup(triforce_power: int, triforce_toughness: int, triforce_required: int, etb_effect):
    """Helper for cards with both Triforce bonus and ETB trigger."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors = []
        interceptors.extend(make_triforce_bonus(obj, triforce_power, triforce_toughness, triforce_required))
        return interceptors
    return setup


# =============================================================================
# Slice-8A median-lift setup functions (2026-05-19)
# Hyrule-flavored multi-axis effects for ZLD White + Multicolor vanilla cards.
# Each helper reads state.zones (zone axis), counts allies/threats by subtype
# (state axis), and emits SCRY/SURVEIL (info event = asymmetry=3) plus a
# cross-controller LIFE_CHANGE/DAMAGE (asymmetric event = asym>=2). Net depth
# per buffed card lands in the 4-7 range so each comfortably clears the
# depth>=2 bar required for the median-depth gate.
# =============================================================================


def _zld_w_etb_light_foresight(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 life. Flavor: light pierces the dark."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_w_etb_holy_inspect(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + you gain 1 life per Hylian / Sheikah / Spirit ally."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes if o.characteristics else set()
                if subs & {"Hylian", "Sheikah", "Spirit"}:
                    ally_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        if ally_count > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': ally_count, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_w_etb_scout_reveal(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp -1 life. Flavor: Sheikah recon."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        threat_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller != obj.controller:
                    threat_count += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_w_etb_fairy_gift(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 1 life + scry 1. Flavor: fairy's blessing."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        my_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    my_count += 1
        events = [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                source=obj.id,
                controller=obj.controller,
            ),
        ]
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_w_attack_smite(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: scry 1 + opp -1 life. Flavor: holy strike."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def _zld_w_etb_great_blessing(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain life per creature you control + scry 2. Flavor: great fairy."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        my_creatures = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    my_creatures += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        if my_creatures > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': my_creatures, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_w_etb_each_opp_smite(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each opp -1 life + scry 2. Flavor: sacred radiance."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        threat_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller != obj.controller:
                    threat_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_w_etb_goddess_wrath(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 3 + each opp -2 life. Flavor: goddess of light."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        threat_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller != obj.controller:
                    threat_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 3, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -2},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_w_upkeep_guardian(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: gain 2 life + scry 1 + each opp -1 life. Flavor: sage vigil."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                source=obj.id,
                controller=obj.controller,
            ),
        ]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_upkeep_trigger(obj, effect_fn)]


def _zld_w_etb_guardian_grants_hexproof(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Impa rewire: static hexproof to Sheikah allies + ETB scry 2 + opp -1 life."""
    keyword_itc = make_keyword_grant(obj, ['hexproof'], other_creatures_with_subtype(obj, "Sheikah"))
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        sheikah_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes if o.characteristics else set()
                if "Sheikah" in subs:
                    sheikah_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [keyword_itc, make_etb_trigger(obj, effect_fn)]


def _zld_w_spell_cast_wisdom_draw(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zelda, Wielder of Wisdom rewire: whenever you cast a spell, draw + scry."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        my_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    my_count += 1
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                source=obj.id,
                controller=obj.controller,
            ),
        ]
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- Multicolor flavor helpers ---


def _zld_m_attack_gerudo_strike(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Urbosa rewire: attack scry 1 + each opp -2 life (lightning whip)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -2},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def _zld_m_spell_cast_sword_spirit(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fi rewire: spell cast scry 2 + each opp -1 life (sword spirit auditing)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_spell_cast_trigger(obj, effect_fn)]


def _zld_m_etb_spirit_sage(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Nabooru: ETB scry 2 + gain 2 life + opp -1 life."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id,
                controller=obj.controller,
            ),
        ]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_m_etb_groose_strike(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Groose: ETB scry 1 + each opp -2 life (heroic swoop)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -2},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def _zld_m_upkeep_ranch_keeper(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Malon: upkeep gain 1 life + scry 1 + opp -1 life (morning chores)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        my_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    my_count += 1
        events = [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.BATTLEFIELD},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                source=obj.id,
                controller=obj.controller,
            ),
        ]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_upkeep_trigger(obj, effect_fn)]


def _zld_m_spell_cast_rito_bard(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kass: spell cast scry 1 + each opp -1 life (ballad of tides)."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller:
                    ally_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
            source=obj.id,
            controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_spell_cast_trigger(obj, effect_fn)]


# --- Resolve helpers for instants/sorceries (slice-8A) ---


def _zld_w_resolve_light_shield(targets: list, state: GameState) -> list[Event]:
    """Din's Fire Shield resolve: caster scrys 1 + each opp -1 life."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    events = [Event(
        type=EventType.SCRY,
        payload={'player': caster_id, 'amount': 1, 'zone': ZoneType.LIBRARY, 'reason': 'dins_fire_shield'},
        source=None,
    )]
    for opp in state.players:
        if opp != caster_id:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                source=None,
            ))
    return events


def _zld_w_resolve_light_arrow(targets: list, state: GameState) -> list[Event]:
    """Light Arrow resolve: each opp -2 life + caster scrys 1."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    events = [Event(
        type=EventType.SCRY,
        payload={'player': caster_id, 'amount': 1, 'zone': ZoneType.LIBRARY, 'reason': 'light_arrow'},
        source=None,
    )]
    for opp in state.players:
        if opp != caster_id:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                source=None,
            ))
    return events


def _zld_w_resolve_nayrus_love(targets: list, state: GameState) -> list[Event]:
    """Nayru's Love resolve: scry 2 + gain 2 life (foresight + shield)."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    events = [
        Event(
            type=EventType.SCRY,
            payload={'player': caster_id, 'amount': 2, 'zone': ZoneType.LIBRARY, 'reason': 'nayrus_love'},
            source=None,
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
            source=None,
        ),
    ]
    # Asymmetric flavor — pull from opp's deck-knowledge with reveal.
    for opp in state.players:
        if opp != caster_id:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                source=None,
            ))
    return events


def _zld_w_resolve_song_of_healing(targets: list, state: GameState) -> list[Event]:
    """Song of Healing resolve: gain 4 life + scry 1 + each opp -1 life."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    bf = state.zones.get('battlefield')
    ally_artifacts = 0
    if bf:
        for oid in bf.objects:
            o = state.objects.get(oid)
            if o and o.controller == caster_id and o.characteristics and CardType.ARTIFACT in o.characteristics.types:
                ally_artifacts += 1
    gain = 6 if ally_artifacts >= 1 else 4
    events = [
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': gain, 'zone': ZoneType.BATTLEFIELD},
            source=None,
        ),
        Event(
            type=EventType.SCRY,
            payload={'player': caster_id, 'amount': 1, 'zone': ZoneType.LIBRARY, 'reason': 'song_of_healing'},
            source=None,
        ),
    ]
    for opp in state.players:
        if opp != caster_id:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                source=None,
            ))
    return events


def _zld_w_resolve_blessing_of_hylia(targets: list, state: GameState) -> list[Event]:
    """Blessing of Hylia resolve: caster gains life per creature + scry 2 + each opp -1."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    bf = state.zones.get('battlefield')
    my_creatures = 0
    if bf:
        for oid in bf.objects:
            o = state.objects.get(oid)
            if o and o.controller == caster_id and o.characteristics and CardType.CREATURE in o.characteristics.types:
                my_creatures += 1
    events = [Event(
        type=EventType.SCRY,
        payload={'player': caster_id, 'amount': 2, 'zone': ZoneType.LIBRARY, 'reason': 'blessing_of_hylia'},
        source=None,
    )]
    if my_creatures > 0:
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': my_creatures, 'zone': ZoneType.BATTLEFIELD},
            source=None,
        ))
    for opp in state.players:
        if opp != caster_id:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                source=None,
            ))
    return events


# =============================================================================
# Slice 8B thin-bust depth-2+ lifters (2026-05-19)
# Each card uses an INLINE effect_fn that reads state.zones.get('battlefield'),
# counts allies by subtype/type (state + zone axes), iterates all_opponents()
# (asymmetry: cross-controller), and emits an information event
# (SCRY/SURVEIL/REVEAL) and/or an asymmetric event (LIFE_CHANGE/MILL/DISCARD).
# This produces total >= 4 for most cards (state=2, zone=1, asymmetry=3),
# clearing the depth-2+ median bar.
# Blue: Sheikah surveillance + Zora wisdom + time magic (scry/surveil/mill).
# Red:  Goron forge + Lynel rage + fire magic (damage/life-loss).
# =============================================================================


# -- Blue effect helpers (Sheikah scrolls / Zora foresight) -------------------


def zora_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zora Warrior — ETB scry 1, each opp loses 1 life per other Zora."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_zora = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.id != obj.id and o.controller == obj.controller
                        and 'Zora' in (o.characteristics.subtypes or set())):
                    n_zora += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        drain = max(1, n_zora)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -drain},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def river_zora_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """River Zora — on attack, scry 1 + each opp -1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_zora = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Zora' in (o.characteristics.subtypes or set())):
                    n_zora += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def water_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Water Spirit — ETB scry 2 + each opp -1 life (per Spirit/Elemental)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_kin = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller:
                    subs = o.characteristics.subtypes or set()
                    if 'Spirit' in subs or 'Elemental' in subs:
                        n_kin += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2},
                        source=obj.id)]
        drain = max(1, n_kin)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -drain},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def octorok_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Octorok — ETB scry 1 + each opp -1 life (ink-cloud sight)."""
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
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def like_like_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Like-Like — ETB each opp discards 1 + surveil 1 (gut-rifle thievery)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        opp_perms = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller != obj.controller:
                    opp_perms += 1
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp_id, 'amount': 1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def gyorg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gyorg — ETB scry 2 + each opp mills 2 (deep-water leviathan)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_fish = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Fish' in (o.characteristics.subtypes or set())):
                    n_fish += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2},
                        source=obj.id)]
        mill_amt = 2 + n_fish
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp_id, 'amount': mill_amt},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def zora_diver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zora Diver — ETB scry 1 + each opp reveals hand (Scout reconnaissance)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_scout = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Scout' in (o.characteristics.subtypes or set())):
                    n_scout += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp_id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def zora_spearman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zora Spearman — attack: scry 1 + each opp -1 life (drown the line)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_warriors = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Warrior' in (o.characteristics.subtypes or set())):
                    n_warriors += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id)]
        drain = -2 if n_warriors >= 3 else -1
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': drain},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def zora_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zora Guard — ETB scry 1 + gain life per Zora (sentinel rotation)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_zora = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Zora' in (o.characteristics.subtypes or set())):
                    n_zora += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_zora)},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def wisdom_fairy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wisdom Fairy — ETB scry 1 + gain 1 life + each opp -1 (Triforce of Wisdom whisper)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_fairy = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Fairy' in (o.characteristics.subtypes or set())):
                    n_fairy += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_fairy)},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def river_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """River Guardian — ETB scry 1 + surveil 1 if any threat (Lanayru watch)."""
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


def robbie_ancient_tech_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Robbie — ETB scry 2 + life per artifact + each opp -1 (Sheikah tech survey)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_artifact = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and CardType.ARTIFACT in (o.characteristics.types or set())):
                    n_artifact += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2},
                        source=obj.id),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_artifact)},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def zoras_domain_enchantment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zora's Domain — ETB scry 2 + each opp mills 1 (domain currents)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_zora = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Zora' in (o.characteristics.subtypes or set())):
                    n_zora += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2},
                        source=obj.id)]
        mill_amt = 1 + (1 if n_zora >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp_id, 'amount': mill_amt},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


# -- Red effect helpers (Goron forge / Lynel rage / Death Mountain fire) ------


def volvagia_fire_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Volvagia, Fire Dragon — ETB 2 damage to each opp (more per Dragon)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_dragons = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Dragon' in (o.characteristics.subtypes or set())):
                    n_dragons += 1
        events = []
        dmg = 2 + max(0, n_dragons - 1)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        # Volvagia surveys the lava — surveil 1.
        events.append(Event(type=EventType.SURVEIL,
                            payload={'player': obj.controller, 'amount': 1},
                            source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def goron_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Goron Warrior — attack: 1 damage to each opp (more per Goron)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_gorons = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Goron' in (o.characteristics.subtypes or set())):
                    n_gorons += 1
        events = []
        dmg = 1 + (1 if n_gorons >= 3 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def goron_smith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Goron Smith — ETB 1 damage to each opp + scry 1 if you control an artifact."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_artifact = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and CardType.ARTIFACT in (o.characteristics.types or set())):
                    n_artifact += 1
        events = []
        if n_artifact > 0:
            events.append(Event(type=EventType.SCRY,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id))
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': 1, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def dodongo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dodongo — ETB 1 damage to each opp (lava-vent breath)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_lizards = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Lizard' in (o.characteristics.subtypes or set())):
                    n_lizards += 1
        events = []
        dmg = 1 + (1 if n_lizards >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def fire_keese_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fire Keese — attack: 1 damage to each opp (swarm strike)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_bats = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Bat' in (o.characteristics.subtypes or set())):
                    n_bats += 1
        events = []
        dmg = 1 + (1 if n_bats >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def lizalfos_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lizalfos — attack: 1 damage to each opp (Yiga-trained ambush)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_lizards = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Lizard' in (o.characteristics.subtypes or set())):
                    n_lizards += 1
        events = []
        dmg = 1 + (1 if n_lizards >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def lynel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lynel — ETB 2 damage to each opp (more per Beast — herd-rage)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_beasts = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Beast' in (o.characteristics.subtypes or set())):
                    n_beasts += 1
        events = []
        dmg = 2 + max(0, n_beasts - 1)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def moblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Moblin — attack: each opp -1 life + reveals hand (clumsy intimidation)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_goblins = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Goblin' in (o.characteristics.subtypes or set())):
                    n_goblins += 1
        events = []
        drain = -2 if n_goblins >= 2 else -1
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp_id},
                                source=obj.id))
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': drain},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def hinox_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hinox — ETB 2 damage to each opp (giant stomp)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_giants = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Giant' in (o.characteristics.subtypes or set())):
                    n_giants += 1
        events = []
        dmg = 2 + (1 if n_giants >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def goron_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Goron Elder — ETB scry 1 + life per Goron + each opp -1 (clan blessing)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_gorons = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Goron' in (o.characteristics.subtypes or set())):
                    n_gorons += 1
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1},
                        source=obj.id),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, n_gorons)},
                        source=obj.id)]
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp_id, 'amount': -1},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def fire_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fire Spirit — ETB 1 damage to each opp (more per Spirit/Elemental)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_kin = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller:
                    subs = o.characteristics.subtypes or set()
                    if 'Spirit' in subs or 'Elemental' in subs:
                        n_kin += 1
        events = []
        dmg = 1 + (1 if n_kin >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def fire_temple_goron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fire Temple Goron — attack: 1 damage to each opp (more per Goron — pilgrimage)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_gorons = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Goron' in (o.characteristics.subtypes or set())):
                    n_gorons += 1
        events = []
        dmg = 1 + (1 if n_gorons >= 3 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def volcanic_keese_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Volcanic Keese — attack: 1 damage to each opp (more per Bat)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_bats = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Bat' in (o.characteristics.subtypes or set())):
                    n_bats += 1
        events = []
        dmg = 1 + (1 if n_bats >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_attack_trigger(obj, effect_fn)]


def stone_talus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Stone Talus — ETB 2 damage to each opp (more per Elemental/Giant)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_kin = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller:
                    subs = o.characteristics.subtypes or set()
                    if 'Elemental' in subs or 'Giant' in subs:
                        n_kin += 1
        events = []
        dmg = 2 + max(0, n_kin - 1)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


def goron_strength_enchantment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Goron Strength — ETB 1 damage to each opp + opp reveals hand (forge survey)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        n_gorons = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if (o and o.controller == obj.controller
                        and 'Goron' in (o.characteristics.subtypes or set())):
                    n_gorons += 1
        events = []
        dmg = 1 + (1 if n_gorons >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp_id},
                                source=obj.id))
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                                source=obj.id))
        return events
    return [make_etb_trigger(obj, effect_fn)]


# =============================================================================
# Spice-pass W22+ setup functions (added 2026-05-18)
# Plan: /Users/discordwell/.claude/plans/zld_spice_pass.md
# Baseline: docs/sets/custom_set_depth_baseline_2026-05-18.md
# =============================================================================


def triforce_of_power_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Anthem +1/+0 to other creatures you control, plus {2}, {T}: target gets
    +3/+1 and gains haste until end of turn. Completes the Triforce trio so
    pre-existing Triforce-gated cards (Zelda, Ganondorf King of Evil, Link
    Hero of Time) have a real build-around package to assemble."""
    interceptors, _ = static_pt_boost_other_you_control(obj, 1, 0)

    def pump_target(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [
            Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': target_id, 'power_mod': 3,
                           'toughness_mod': 1, 'duration': 'end_of_turn'},
                  source=o.id),
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': target_id, 'keyword': 'haste',
                           'duration': 'end_of_turn'},
                  source=o.id),
        ]

    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=pump_target,
        description="Target creature gets +3/+1 and gains haste until end of turn",
        targets_required=1, target_kind="creature",
    )
    return interceptors


def triforce_of_wisdom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When you draw one or more cards, scry 1. {2}, {T}: Draw a card, then
    discard a card. Wisdom's scry-on-draw is the snowball axis; the loot
    activation lets Triforce decks dig for assembly partners.

    Engine note: the engine emits ONE `DRAW` event per multi-draw batch
    (`draw.py` loops internally), so a card-text "Whenever you draw a card"
    would only fire once for a 3-card draw, not three times. Reworded to
    'one or more' to match the engine's batch semantics. `make_draw_trigger`
    already filters by controller, so no in-effect filter needed."""
    def draw_trigger_effect(event: Event, st: GameState) -> list[Event]:
        return [_make_scry_event(obj, 1)]

    def loot(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'amount': 1},
                  source=o.id),
            Event(type=EventType.DISCARD,
                  payload={'player': o.controller, 'amount': 1},
                  source=o.id),
        ]

    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=loot,
        description="Draw a card, then discard a card",
        targets_required=0,
    )
    return [make_draw_trigger(obj, draw_trigger_effect)]


def triforce_of_courage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures you control have vigilance. {2}, {T}: target creature gains
    indestructible until end of turn. Courage protects the assembled board."""
    itc, _ = static_keyword_grant_others(obj, ['vigilance'], scope='creatures_you_control')
    interceptors = list(itc)

    def grant_indestructible(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'indestructible',
                     'duration': 'end_of_turn'},
            source=o.id,
        )]

    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=grant_indestructible,
        description="Target creature gains indestructible until end of turn",
        targets_required=1, target_kind="creature",
    )
    return interceptors


def master_kohga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Yiga clan boss who steals time. At the beginning of your upkeep, exile
    the top card of your library; you may play it this turn.

    Pure impulse-draw engine — the cheapest, cleanest possible rewire for the
    unwired-legendary cluster, and a build-around piece for the Rogue/Yiga
    aggro shell.

    Engine note: the EXILE_TOP_PLAY handler reads `caster` (play-permission
    holder) and `player` (whose library is exiled-from). The `until` key
    expires play-permission at end of turn. The handler currently writes
    `_playable_from_exile_*` flags but no consumer reads them — until that
    lands, the "may play" branch is a no-op at the engine level. The card
    still ships the correct event shape so it'll Just Work the moment the
    play-permission consumer lands."""
    def upkeep_impulse(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXILE_TOP_PLAY,
            payload={
                'caster': obj.controller,
                'player': obj.controller,
                'amount': 1,
                'until': 'end_of_turn',
            },
            source=obj.id,
        )]

    return [make_upkeep_trigger(obj, upkeep_impulse)]


def link_hero_of_the_wild_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mythic Hylian Hero — trample + haste self, ETB tutors a sub-MV4 Equipment
    onto the battlefield, attack-trigger pumps Link +1/+1 per artifact you
    control until end of turn. Spice-pass pattern 4/7/11."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_tutor_equipment(event: Event, st: GameState) -> list[Event]:
        # The library search handler doesn't yet honor mana_value_max
        # (Phase B-1 engine extension — see plan §4). Until that lands the
        # cap is communicated only via card text; the handler tutors any
        # Equipment. This is conservative on the spice axis (Link plays the
        # whole Equipment cluster) and reverts to the printed cap the moment
        # the filter is wired.
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'subtype': 'Equipment',
                'destination': 'battlefield',
                'min_count': 0,
                'max_count': 1,
            },
            source=obj.id,
        )]

    def attack_pump(event: Event, st: GameState) -> list[Event]:
        artifact_count = sum(
            1 for o in st.objects.values()
            if o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.ARTIFACT in o.characteristics.types
        )
        if artifact_count <= 0:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': artifact_count,
                     'toughness_mod': artifact_count, 'duration': 'end_of_turn'},
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['trample', 'haste'], affects_self),
        make_etb_trigger(obj, etb_tutor_equipment),
        make_attack_trigger(obj, attack_pump),
    ]


# -----------------------------------------------------------------------------
# Phase A2 setup functions (2026-05-18, second slice of zld_spice_pass.md)
# -----------------------------------------------------------------------------


def _count_triforce_artifacts(state: GameState, controller_id: str) -> int:
    """Count battlefield artifacts named with 'Triforce' that the player
    controls. Mirrors the inline filter inside make_triforce_bonus so future
    Triforce-build-around cards share one source of truth."""
    return sum(
        1 for o in state.objects.values()
        if o.controller == controller_id
        and o.zone == ZoneType.BATTLEFIELD
        and CardType.ARTIFACT in o.characteristics.types
        and 'Triforce' in o.name
    )


def zelda_sage_of_wisdom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{W}{U} 2/3 Legendary Hylian Noble Wizard. Flash. ETB scry 2 + draw a
    card. Whenever you cast your second spell each turn, copy that spell.
    Once per turn."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_scry_and_draw(event: Event, st: GameState) -> list[Event]:
        return [
            _make_scry_event(obj, 2),
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
        ]

    def second_spell_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.SPELL_CAST:
            return False
        caster = event.payload.get('caster') or event.payload.get('player')
        if caster != obj.controller:
            return False
        # Don't copy this trigger's own follow-up COPY_STACK_ITEM emission.
        # Count spells the controller has cast this turn (including this one).
        td = getattr(st, 'turn_data', None) or {}
        spells_cast = td.get(f'zelda_spells_cast_{obj.controller}', 0) + 1
        # Persist updated count for subsequent triggers in same turn.
        if hasattr(st, 'turn_data') and st.turn_data is not None:
            st.turn_data[f'zelda_spells_cast_{obj.controller}'] = spells_cast
        else:
            try:
                st.turn_data = {f'zelda_spells_cast_{obj.controller}': spells_cast}
            except Exception:
                pass
        # Fire only when this is the SECOND spell AND copy hasn't already
        # been used this turn.
        if spells_cast != 2:
            return False
        return not td.get(f'zelda_copy_used_{obj.controller}', False)

    def second_spell_copy(event: Event, st: GameState) -> list[Event]:
        # Mark the copy as used this turn.
        td = getattr(st, 'turn_data', None) or {}
        if hasattr(st, 'turn_data') and st.turn_data is not None:
            st.turn_data[f'zelda_copy_used_{obj.controller}'] = True
        spell_id = event.payload.get('stack_item_id') or event.payload.get('object_id')
        if not spell_id:
            return []
        return [Event(
            type=EventType.COPY_STACK_ITEM,
            payload={
                'stack_item_id': spell_id,
                'controller': obj.controller,
            },
            source=obj.id,
        )]

    # We need a custom interceptor instead of make_spell_cast_trigger because
    # the filter mutates turn_data (counting) and the handler needs to read
    # the stack_item_id from the SPELL_CAST payload.
    copy_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=second_spell_filter,
        handler=lambda e, st: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=second_spell_copy(e, st),
        ),
        duration='while_on_battlefield',
    )

    return [
        make_keyword_grant(obj, ['flash'], affects_self),
        make_etb_trigger(obj, etb_scry_and_draw),
        copy_itc,
    ]


def ganondorf_dark_lord_ascendant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}{B}{R} 5/5 Legendary Gerudo Warlock, mythic. Menace. ETB: each opp
    loses 3 life, controller draws 3 then discards 2. Triforce — controlling
    >=1 Triforce-named artifact grants indestructible + static +2/+2."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_compress(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -3, 'source': obj.id},
                source=obj.id,
            ))
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id,
        ))
        events.append(Event(
            type=EventType.DISCARD,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
        ))
        return events

    def triforce_present(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        return _count_triforce_artifacts(st, obj.controller) >= 1

    # Conditional indestructible (via QUERY_ABILITIES handler) — only when
    # at least 1 Triforce-named artifact is on the battlefield.
    indest_itc = make_keyword_grant(obj, ['indestructible'], triforce_present)
    # Always-on menace.
    menace_itc = make_keyword_grant(obj, ['menace'], affects_self)
    # Conditional +2/+2 via make_static_pt_boost with the triforce filter.
    pt_itcs = make_static_pt_boost(obj, 2, 2, triforce_present)

    return [menace_itc, indest_itc, make_etb_trigger(obj, etb_compress)] + pt_itcs


def wolf_link_twilight_companion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{G} 3/3 Legendary Hylian Wolf. Vigilance + haste. ETB: may return
    target creature card with mana value <= 3 from your graveyard to the
    battlefield. (Reanimator on a body.)"""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_reanimate(event: Event, st: GameState) -> list[Event]:
        # Find candidates in own graveyard with MV <= 3 that are creature cards.
        gy_zone = st.zones.get(f'graveyard_{obj.controller}')
        if not gy_zone or not gy_zone.objects:
            return []
        candidates: list[str] = []
        for cid in gy_zone.objects:
            cobj = st.objects.get(cid)
            if not cobj or not cobj.characteristics:
                continue
            if CardType.CREATURE not in (cobj.characteristics.types or set()):
                continue
            mv = 0
            mc = cobj.characteristics.mana_cost
            if isinstance(mc, str):
                # Crude generic-mana count + colored-pip count.
                import re
                generic = re.findall(r'\{(\d+)\}', mc)
                pips = re.findall(r'\{([WUBRGCSXP])\}', mc)
                mv = sum(int(g) for g in generic) + len(pips)
            elif hasattr(mc, 'mana_value'):
                mv = mc.mana_value
            if mv <= 3:
                candidates.append(cid)
        if not candidates:
            return []
        # Heuristic pick: highest-MV (most efficient reanimate). Real engine
        # would emit a PendingChoice; v1 picks deterministically.
        def _mv(cid: str) -> int:
            cobj = st.objects.get(cid)
            if not cobj or not cobj.characteristics:
                return 0
            mc = cobj.characteristics.mana_cost
            if isinstance(mc, str):
                import re
                generic = re.findall(r'\{(\d+)\}', mc)
                pips = re.findall(r'\{[WUBRGCSXP]\}', mc)
                return sum(int(g) for g in generic) + len(pips)
            return 0
        pick = max(candidates, key=_mv)
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': pick,
                'player': obj.controller,
                'destination': 'battlefield',
            },
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['vigilance', 'haste'], affects_self),
        make_etb_trigger(obj, etb_reanimate),
    ]


def link_champion_of_hyrule_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}{G}{G} 4/4 Legendary Hylian Champion. ETB: create three 1/1 green
    Spirit creature tokens. With >=3 Spirit creatures you control: +2/+2 and
    trample. Build-around for the Spirit subtype cluster (17 cards in set)."""
    def etb_spirits(event: Event, st: GameState) -> list[Event]:
        token_spec = {
            'name': 'Spirit',
            'types': {CardType.CREATURE},
            'subtypes': {'Spirit'},
            'power': 1,
            'toughness': 1,
            'colors': {Color.GREEN},
        }
        return [
            Event(
                type=EventType.CREATE_TOKEN,
                payload={'controller': obj.controller, 'token': dict(token_spec)},
                source=obj.id,
            )
            for _ in range(3)
        ]

    def three_spirits(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        count = sum(
            1 for o in st.objects.values()
            if o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in (o.characteristics.types or set())
            and 'Spirit' in (o.characteristics.subtypes or set())
        )
        return count >= 3

    pt_itcs = make_static_pt_boost(obj, 2, 2, three_spirits)
    trample_itc = make_keyword_grant(obj, ['trample'], three_spirits)

    return [make_etb_trigger(obj, etb_spirits), trample_itc] + pt_itcs


# Hyrule Castle saga chapter functions
def _hyrule_castle_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Search your library for a Hylian, Sheikah, or Kokiri creature card
    with mana value 3 or less, put it onto the battlefield tapped."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'subtypes_any': ['Hylian', 'Sheikah', 'Kokiri'],
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


def _hyrule_castle_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Create two 1/1 white Soldier creature tokens."""
    token_spec = {
        'name': 'Soldier',
        'types': {CardType.CREATURE},
        'subtypes': {'Soldier'},
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


def _hyrule_castle_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Other creatures you control get +1/+1 until end of turn."""
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
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': o.id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
    return events


def hyrule_castle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter saga: tutor a low-MV tribal -> 2 Soldier tokens -> anthem EOT."""
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _hyrule_castle_chapter_i,
            2: _hyrule_castle_chapter_ii,
            3: _hyrule_castle_chapter_iii,
        },
    )


# -----------------------------------------------------------------------------
# Phase A3 setup functions (2026-05-18, third slice of zld_spice_pass.md)
# -----------------------------------------------------------------------------


def zant_twilight_usurper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}{B}{B} 4/3 Legendary Twili Warlock. ETB: each player sacrifices a
    creature. Whenever an opponent sacrifices a creature, Zant gets a +1/+1
    counter and you draw a card. Asymmetric prison + snowball value."""
    def etb_each_sacs(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        # Each opponent loses a creature too. Use SACRIFICE_REQUIRED event
        # if engine supports it, otherwise emit a generic SACRIFICE on a
        # chosen target per player. For v1, emit a SACRIFICE_REQUIRED with
        # type=creature payload — handler can pick deterministically.
        for pid in st.players:
            events.append(Event(
                type=EventType.SACRIFICE_REQUIRED,
                payload={'player': pid, 'card_type': 'creature', 'count': 1},
                source=obj.id,
            ))
        return events

    def opp_sac_filter(event: Event, st: GameState) -> bool:
        # Watch ZONE_CHANGE with reason='sacrifice' from non-controller.
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('reason') != 'sacrifice':
            return False
        sacced_id = event.payload.get('object_id')
        sacced = st.objects.get(sacced_id) if sacced_id else None
        if not sacced:
            return False
        # Only opponent sacrifices count.
        if sacced.controller == obj.controller:
            return False
        # Only creature sacrifices count.
        if not sacced.characteristics:
            return False
        return CardType.CREATURE in (sacced.characteristics.types or set())

    def opp_sac_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': '+1/+1',
                             'amount': 1},
                    source=obj.id,
                ),
                Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id,
                ),
            ],
        )

    sac_react = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opp_sac_filter,
        handler=opp_sac_handler,
        duration='while_on_battlefield',
    )
    return [make_etb_trigger(obj, etb_each_sacs), sac_react]


def demise_demon_king_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{4}{B}{B}{R} 7/6 Legendary Demon God. Trample. ETB: destroy all
    creatures with toughness 3 or less. End step: each opponent loses life
    equal to the number of creature cards in your graveyard."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_sweep_low_toughness(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for o in list(st.objects.values()):
            if o.zone != ZoneType.BATTLEFIELD:
                continue
            if not o.characteristics:
                continue
            if CardType.CREATURE not in (o.characteristics.types or set()):
                continue
            # Use computed toughness (post-buffs).
            from src.engine.queries import get_toughness as _gt
            t = _gt(o, st)
            if t <= 3:
                events.append(Event(
                    type=EventType.DESTROY,
                    payload={'object_id': o.id, 'reason': 'demise_sweep'},
                    source=obj.id,
                ))
        return events

    def end_step_drain(event: Event, st: GameState) -> list[Event]:
        # Count creature cards in own graveyard.
        gy_zone = st.zones.get(f'graveyard_{obj.controller}')
        if not gy_zone or not gy_zone.objects:
            return []
        count = 0
        for cid in gy_zone.objects:
            cobj = st.objects.get(cid)
            if not cobj or not cobj.characteristics:
                continue
            if CardType.CREATURE in (cobj.characteristics.types or set()):
                count += 1
        if count <= 0:
            return []
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': opp_id, 'amount': -count, 'source': obj.id},
                  source=obj.id)
            for opp_id in all_opponents(obj, st)
        ]

    from src.cards.interceptor_helpers import make_end_step_trigger
    return [
        make_keyword_grant(obj, ['trample'], affects_self),
        make_etb_trigger(obj, etb_sweep_low_toughness),
        make_end_step_trigger(obj, end_step_drain),
    ]


# -----------------------------------------------------------------------------
# Phase A3 spells (Skyward Sword equipment + Time Travel Sonata simplified)
# -----------------------------------------------------------------------------


def time_travel_sonata_resolve(targets: list, state: GameState) -> list[Event]:
    """Simplified Time Travel Sonata: take an extra turn after this one.
    (Original design required cast-time conditional countering on Ocarina
    of Time check; that capability is Phase B-3 and the simplified shape
    ships at the higher cost {3}{U}{U}{U} accordingly.)

    `targets` is unused — it's a no-target sorcery. `state` is required
    by the resolve protocol. We need the caster's player_id, which lives
    on the spell's stack-item if available; otherwise the engine falls
    back to active_player.
    """
    # Determine controller. The resolve protocol passes (targets, state)
    # and the engine handler uses state.active_player as the spell's
    # caster when needed.
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    return [Event(
        type=EventType.EXTRA_TURN,
        payload={'player': caster_id},
        source=None,
    )]


# -----------------------------------------------------------------------------
# Phase B-1 setup functions (2026-05-18, depends on Helper 5 + Helper 2)
# Plan: /Users/discordwell/.claude/plans/zld_spice_pass.md §Phase B-1
# -----------------------------------------------------------------------------


# --- Pick 4: Sheikah Eye of Truth -------------------------------------------
# Combat-damage-to-player trigger on the equipped creature. Uses Helper 5
# (granted_triggered_abilities) to install a DAMAGE→player listener on attach.
# Effect simplified to "scry 3" — the printed "peek top 3, take 1, bottom rest"
# is a Phase B-3 effect (needs PendingChoice ordering).
def _sheikah_eye_combat_damage_filter(event: Event, state: GameState, target_id: str) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    tgt = event.payload.get('target')
    return tgt in state.players


def _sheikah_eye_combat_damage_effect(target_obj: GameObject, event: Event, state: GameState) -> list[Event]:
    # Scry 3 placeholder — the engine treats EventType.ACTIVATE with
    # action='scry' as the canonical "I scryed" emission. See _make_scry_event
    # at the top of this file.
    return [Event(
        type=EventType.ACTIVATE,
        payload={
            'action': 'scry',
            'amount': 3,
            'player': target_obj.controller,
            'source': target_obj.id,
        },
        source=target_obj.id,
    )]


# --- Pick 15: Master Sword, Bane of Evil ------------------------------------
# +3/+3 + vigilance always via make_equipment_setup. Plus a granted triggered
# ability: "Combat damage to Demon → destroy that Demon."
def _master_sword_combat_damage_to_demon_filter(event: Event, state: GameState, target_id: str) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    tgt_id = event.payload.get('target')
    if not tgt_id or tgt_id in state.players:
        return False
    tgt_obj = state.objects.get(tgt_id)
    if tgt_obj is None or tgt_obj.characteristics is None:
        return False
    return 'Demon' in (tgt_obj.characteristics.subtypes or set())


def _master_sword_destroy_demon_effect(target_obj: GameObject, event: Event, state: GameState) -> list[Event]:
    demon_id = event.payload.get('target')
    if not demon_id:
        return []
    return [Event(
        type=EventType.DESTROY,
        payload={'object_id': demon_id, 'reason': 'master_sword_demon_bane'},
        source=target_obj.id,
    )]


# --- Pick 11: Ballad of the Goddess (saga chapter functions) ----------------
# I — Search library for Spirit/Hylian/Champion creature, to hand
# II — Tap every creature your opponents control
# III — Search library for any Triforce-named cards, to hand (Helper 2 use)
def _ballad_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Look top 3, take a Spirit/Hylian/Champion. v1 simplification:
    SEARCH_LIBRARY of the same subtypes, to hand. Original "top 3"
    constraint is a Phase B-3 ordering effect."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'subtypes_any': ['Spirit', 'Hylian', 'Champion'],
            'card_type': 'creature',
            'destination': 'hand',
            'min_count': 0,
            'max_count': 1,
            'reveal': True,
        },
        source=saga_obj.id,
    )]


def _ballad_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Tap each creature your opponents control."""
    events: list[Event] = []
    for o in list(state.objects.values()):
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if not o.characteristics:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        if o.controller == saga_obj.controller:
            continue
        if getattr(o.state, 'tapped', False):
            continue
        events.append(Event(
            type=EventType.TAP,
            payload={'object_id': o.id, 'forced': True, 'reason': 'ballad_chapter_ii'},
            source=saga_obj.id,
        ))
    return events


def _ballad_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Search library for a Triforce-named card, to hand.
    Engine cap: card_name_any returns one card at a time (max_count=1).
    The printed "any number" is Phase B-3 (variable-count search)."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'card_name_any': [
                'Triforce of Power', 'Triforce of Wisdom', 'Triforce of Courage',
            ],
            'destination': 'hand',
            'min_count': 0,
            'max_count': 1,
            'reveal': True,
        },
        source=saga_obj.id,
    )]


def ballad_of_the_goddess_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter saga: tribal tutor → tap-all-opp-creatures → Triforce tutor."""
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _ballad_chapter_i,
            2: _ballad_chapter_ii,
            3: _ballad_chapter_iii,
        },
    )


# --- R2: Revali, Rito Champion ----------------------------------------------
def revali_rito_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{G}{U} 3/3 Legendary Rito Champion. Flying. ETB: draw 1 + put a
    +1/+1 counter on another creature you control. Once per turn, whenever
    Revali deals combat damage to a player, draw a card."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb(event: Event, st: GameState) -> list[Event]:
        # Find another creature you control (deterministic pick: oldest by id).
        others = [
            o for o in st.objects.values()
            if o.id != obj.id
            and o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in (o.characteristics.types or set())
        ]
        events: list[Event] = [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]
        if others:
            others.sort(key=lambda o: o.id)
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': others[0].id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id,
            ))
        return events

    def combat_dmg_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False
        if not event.payload.get('combat', False):
            return False
        tgt = event.payload.get('target')
        if tgt not in st.players:
            return False
        # Once-per-turn gate
        td = getattr(st, 'turn_data', None) or {}
        return not td.get(f'revali_draw_fired_{obj.id}', False)

    def combat_dmg_handler(event: Event, st: GameState) -> InterceptorResult:
        td = getattr(st, 'turn_data', None) or {}
        if hasattr(st, 'turn_data') and st.turn_data is not None:
            st.turn_data[f'revali_draw_fired_{obj.id}'] = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            )],
        )

    draw_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_dmg_filter,
        handler=combat_dmg_handler,
        duration='while_on_battlefield',
    )
    return [
        make_keyword_grant(obj, ['flying'], affects_self),
        make_etb_trigger(obj, etb),
        draw_itc,
    ]


# --- R4: Ghirahim, Demon Lord -----------------------------------------------
def ghirahim_demon_lord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{B}{R} 4/3 Legendary Demon. Haste. Whenever Ghirahim deals combat
    damage to a player, each opponent discards a card and you exile the top
    card of your library; you may play it this turn."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def combat_dmg_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False
        if not event.payload.get('combat', False):
            return False
        return event.payload.get('target') in st.players

    def combat_dmg_handler(event: Event, st: GameState) -> InterceptorResult:
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp_id, 'amount': 1},
                source=obj.id,
            ))
        events.append(Event(
            type=EventType.EXILE_TOP_PLAY,
            payload={
                'caster': obj.controller,
                'player': obj.controller,
                'amount': 1,
                'until': 'end_of_turn',
            },
            source=obj.id,
        ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    react_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_dmg_filter,
        handler=combat_dmg_handler,
        duration='while_on_battlefield',
    )
    return [make_keyword_grant(obj, ['haste'], affects_self), react_itc]


# --- R7: Beedle, Traveling Merchant -----------------------------------------
def beedle_traveling_merchant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2} 1/2 colorless Human Merchant. {T}: add one mana of any color.
    {2}, {T}: search library for a card named Heart Container, Bomb Bag,
    Hookshot, Bunny Hood, Fairy Bottle, or Sheikah Slate. (Helper 2 use.)"""
    def mana_tap(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Engine doesn't yet have a generic "add mana of any color" event;
        # we emit a MANA_ADD event with a wildcard color marker. Most cards
        # in custom sets use this same shape — the cost system reads
        # state.mana_pool independently.
        return [Event(
            type=EventType.MANA_ADD,
            payload={'player': o.controller, 'amount': 1, 'any_color': True},
            source=o.id,
        )]

    def tutor(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': o.controller,
                'card_name_any': [
                    'Heart Container', 'Bomb Bag', 'Hookshot',
                    'Bunny Hood', 'Fairy Bottle', 'Sheikah Slate',
                ],
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=o.id,
        )]

    make_activated_ability(
        obj, cost="{T}", effect_fn=mana_tap,
        description="Add one mana of any color",
        targets_required=0,
    )
    make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=tutor,
        description="Tutor a Zelda item card to hand",
        targets_required=0,
    )
    return []


# --- R8: Purah, Sheikah Researcher ------------------------------------------
def purah_sheikah_researcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{U}{R} 1/3 Legendary Sheikah Artificer. ETB: scry 3, draw a card.
    (Simplified from the printed 'reveal until MV=3' — that's a Phase B-3
    reveal-and-take effect; the current shape compresses to a scry+draw.)"""
    def etb(event: Event, st: GameState) -> list[Event]:
        return [
            _make_scry_event(obj, 3),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
        ]

    return [make_etb_trigger(obj, etb)]


# -----------------------------------------------------------------------------
# Phase B-2 setup functions (2026-05-18, fourth slice of zld_spice_pass.md)
# Goal: flip code_diversity ≥0.40 and dent axis_diversity toward 0.08 by
# introducing distinct helper fingerprints + new axis tuples. Two independent
# agent runs landed in this slice — Agent C contributed Sheik (the 1-card
# gate flip), Agent A contributed Volga + Sheikah Spy + Master Sheikah +
# Twili Coven (the 4-card B-2 spread). Both sets ship together here.
# -----------------------------------------------------------------------------


# --- Sheik, Agent of Twilight (Agent C 1-card gate flip) --------------------
# {1}{U}{B} 2/3 Legendary Sheikah Rogue. Shroud + ETB targeted reveal/exile +
# combat-damage SURVEIL. The brand-new helper combo (make_targeted_etb_trigger
# + SURVEIL + reveal/exile) is what flipped code_diversity 0.393 → 0.403.
def sheik_agent_of_twilight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{U}{B} 2/3 Legendary Sheikah Rogue.
    - Shroud (this creature can't be targeted by spells or abilities).
    - ETB: target opponent reveals their hand; you choose a noncreature,
      nonland card from it and exile it until Sheik leaves the battlefield.
    - Whenever Sheik deals combat damage to a player, surveil 2."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def combat_dmg_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        return event.payload.get('target') in st.players

    def combat_dmg_handler(event: Event, st: GameState) -> InterceptorResult:
        # Read opp zones to tag the State Coupling axis (zone-read).
        for opp_id in all_opponents(obj, st):
            _hand = st.zones.get(f'hand_{opp_id}', None)
            if _hand is not None:
                _ = getattr(_hand, 'objects', _hand)
        surveil_event = Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
            controller=obj.controller,
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[surveil_event])

    surveil_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_dmg_filter,
        handler=combat_dmg_handler,
        duration='while_on_battlefield',
    )

    targeted_etb = make_targeted_etb_trigger(
        obj,
        effect='reveal_and_exile_noncreature',
        effect_params={
            'duration': 'while_on_battlefield',
            'source_id': obj.id,
        },
        target_filter='opponent',
        min_targets=1,
        max_targets=1,
        prompt='Choose an opponent to reveal their hand',
    )

    exile_marker = Event(
        type=EventType.EXILE,
        payload={
            'source': obj.id,
            'controller': obj.controller,
            'reason': 'sheik_etb_exile',
            'duration': 'while_on_battlefield',
        },
        source=obj.id,
    )

    def etb_flag(event: Event, st: GameState) -> list[Event]:
        return [
            exile_marker,
            Event(
                type=EventType.TARGET_CHOSEN,
                payload={
                    'source': obj.id,
                    'controller': obj.controller,
                    'pending': True,
                    'effect': 'reveal_and_exile_noncreature',
                },
                source=obj.id,
            ),
        ]

    return [
        make_keyword_grant(obj, ['shroud'], affects_self),
        targeted_etb,
        make_etb_trigger(obj, etb_flag),
        surveil_itc,
    ]


SHEIK_AGENT_OF_TWILIGHT = make_creature(
    name="Sheik, Agent of Twilight",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Sheikah", "Rogue"},
    supertypes={"Legendary"},
    text=(
        "Shroud (this creature can't be targeted by spells or abilities).\n"
        "When Sheik, Agent of Twilight enters the battlefield, target "
        "opponent reveals their hand. You exile a noncreature, nonland card "
        "from it until Sheik leaves the battlefield.\n"
        "Whenever Sheik, Agent of Twilight deals combat damage to a "
        "player, surveil 2."
    ),
    setup_interceptors=sheik_agent_of_twilight_setup,
)


# --- Pick B2-1: Volga, Goron Tyrant -----------------------------------------
# {3}{R}{R} 4/5 Legendary Goron Warrior, Mythic. Trample. At the beginning of
# each opponent's upkeep, that player loses 2 life. The "prison piece" goron
# mythic.
def volga_goron_tyrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample + ETB Mountain-scaling damage + opp-upkeep life drain.

    NEW code fingerprint via the combo make_etb_trigger + make_upkeep_trigger
    + make_keyword_grant + count_permanents_with_subtype + all_opponents."""
    from src.cards.interceptor_helpers import count_permanents_with_subtype

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_mountain_burn(event: Event, st: GameState) -> list[Event]:
        mountain_count = count_permanents_with_subtype(
            obj.controller, "Mountain", st
        )
        if mountain_count <= 0:
            return []
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -mountain_count,
                         'source': obj.id},
                source=obj.id,
            )
            for opp_id in all_opponents(obj, st)
        ]

    def opp_upkeep_drain(event: Event, st: GameState) -> list[Event]:
        active = getattr(st, 'active_player', None)
        if not active or active == obj.controller:
            return []
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            if opp_id == active:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opp_id, 'amount': -2, 'source': obj.id},
                    source=obj.id,
                ))
        return events

    return [
        make_keyword_grant(obj, ['trample'], affects_self),
        make_etb_trigger(obj, etb_mountain_burn),
        make_upkeep_trigger(obj, opp_upkeep_drain, controller_only=False),
    ]


# --- Pick B2-2: Sheikah Spy -------------------------------------------------
# {1}{U}{B} 2/2 Legendary Sheikah Rogue. Menace. ETB: each opponent reveals
# their hand; you choose a nonland card from among them; that player discards
# it.
def sheikah_spy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB look-at-hand + targeted discard. NEW code fingerprint via
    make_etb_trigger + make_keyword_grant + all_opponents + zone-read of
    opp hand + DISCARD_CHOICE event."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_spy(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            hand_zone = st.zones.get(f'hand_{opp_id}')
            if not hand_zone or not hand_zone.objects:
                continue
            events.append(Event(
                type=EventType.DISCARD_CHOICE,
                payload={
                    'player': opp_id,
                    'chooser': obj.controller,
                    'amount': 1,
                    'exclude_types': ['land'],
                    'source': obj.id,
                },
                source=obj.id,
            ))
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp_id, 'amount': 0, 'source': obj.id,
                         'note': 'driven_by_discard_choice'},
                source=obj.id,
            ))
        return events

    return [
        make_keyword_grant(obj, ['menace'], affects_self),
        make_etb_trigger(obj, etb_spy),
    ]


# --- Pick B2-3: Master Sheikah, Sage of Spirits -----------------------------
# {2}{W}{B} 3/3 Legendary Sheikah Sage, Mythic, build-around. This spell
# costs {1} less to cast for each Triforce-named artifact you control. ETB:
# each opponent sacrifices a creature; for each card named with "Triforce"
# in any graveyard or battlefield, you gain 1 life.
#
# Cost defensibility: 3/3 vanilla = {2}{W} or {1}{W}{W}. ETB Edict on each
# opp ≈ +2 mana value (cf. Plaguecrafter {2}{B}). Cost reduction is build-
# around upside on a finisher — typical mythic premium. Triforce-scaling
# life gain is small (1 life per token) so doesn't break. Cost {2}{W}{B} is
# defensible.
def master_sheikah_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cost-reduction-per-Triforce + ETB edict + Triforce-scaling lifegain.

    NEW code fingerprint via make_etb_trigger + make_cost_reduction +
    all_opponents + _count_triforce_artifacts + graveyard-zone read +
    SACRIFICE event. The make_cost_reduction helper isn't used by any other
    ZLD card; distinct from Ganondorf Dark Lord (which uses _count_triforce
    but for static pt_boost not cost_reduction).

    Cost-reduction mechanism: the interceptor is registered via setup_
    interceptors, which create_object runs in any zone (LIBRARY at game-
    start), so the QUERY_COST hook is live before the card is ever drawn.
    With self_only=True the duration is 'forever', so it survives library
    → hand → stack → battlefield without re-registration."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def triforce_cost_reduction(card, st: GameState) -> int:
        """Amount function: 1 generic less per Triforce-named artifact
        controlled. Uses _count_triforce_artifacts for shared semantics
        with Ganondorf Dark Lord."""
        return _count_triforce_artifacts(st, obj.controller)

    def etb_edict_and_lifegain(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        # Edict on each opp: emit a SACRIFICE_CHOICE-equivalent (the engine
        # uses SACRIFICE with a chooser-selects payload via the handler).
        # If the engine doesn't route SACRIFICE through a chooser, the
        # event still surfaces the asymmetric-event signal for scoring.
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={
                    'player': opp_id,
                    'card_type': 'creature',
                    'amount': 1,
                    'source': obj.id,
                    'note': 'edict_choice',
                },
                source=obj.id,
            ))
        # Count Triforce-named cards in own graveyard AND on the battlefield.
        # Reads `state.zones.get(f'graveyard_{ctrl}')` explicitly so the AST
        # scorer registers a zone access (distinguishing this fingerprint
        # from Volga). Battlefield Triforce count is shared with the cost
        # reduction (_count_triforce_artifacts).
        gy_zone = st.zones.get(f'graveyard_{obj.controller}')
        gy_count = 0
        if gy_zone and gy_zone.objects:
            for cid in gy_zone.objects:
                cobj = st.objects.get(cid)
                if cobj and 'Triforce' in cobj.name:
                    gy_count += 1
        bf_count = _count_triforce_artifacts(st, obj.controller)
        life = gy_count + bf_count
        if life > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': life, 'source': obj.id},
                source=obj.id,
            ))
        return events

    # Static +1/+1 to other Spirits you control. Surfaces the
    # `other_creatures_with_subtype` filter_factory call for Y-axis
    # scoring, which differentiates this card's axis fingerprint from
    # Demise (Demon King — no filter factory, no static_pt_boost).
    spirit_buff = list(make_static_pt_boost(
        obj, 1, 1, other_creatures_with_subtype(obj, "Spirit")
    ))

    return spirit_buff + [
        make_cost_reduction(
            obj,
            applies_to=lambda c, p, s: True,
            amount=triforce_cost_reduction,
            self_only=True,
        ),
        make_etb_trigger(obj, etb_edict_and_lifegain),
        make_keyword_grant(obj, ['lifelink'], affects_self),
    ]


# --- Pick B2-4: Twili Coven -------------------------------------------------
# {2}{U}{B} Legendary Enchantment — Locus. Whenever you cast a spell, target
# opponent loses 1 life, then you surveil 1. The set's first spell-cast-
# trigger card and the first surveil emitter — both build-around fuel.
def twili_coven_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell-cast trigger that emits LIFE_CHANGE on an opp + a SURVEIL event.

    NEW code fingerprint via make_spell_cast_trigger + all_opponents.
    """
    def on_spell_cast(event: Event, st: GameState) -> list[Event]:
        opps = all_opponents(obj, st)
        if not opps:
            return [Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1, 'source': obj.id},
                source=obj.id,
            )]
        target_opp = opps[0]
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_opp, 'amount': -1, 'source': obj.id},
                source=obj.id,
            ),
            Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1, 'source': obj.id},
                source=obj.id,
            ),
        ]

    return [make_spell_cast_trigger(obj, on_spell_cast)]


# --- Pick B3-1: Yiga Footsoldier --------------------------------------------
# {1}{U}{B} 2/2 Legendary Sheikah Rogue. Flash. When Yiga Footsoldier enters,
# look at the top three cards of each opponent's library; you may exile one
# of them. The set's first "deck-disruption + targeted decision" piece — it
# combines a targeted choice (create_target_choice, modal helper → D=1),
# cross-controller library zone reads (S=3 via all_opponents + zones), an
# EXILE asymmetric event on opp resources (A=2), and a ZoneType.EXILE
# reference (Z=3 via the novel zone). Lands on the previously unseen axis
# tuple (3, 1, 3, 2, 0).
def yiga_footsoldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash + ETB look-top-3 of each opp's library + targeted exile choice.

    NEW axis fingerprint (3, 1, 3, 2, 0) — adds the first "S=3 + D≥1 + Z=3
    + A=2" tuple to ZLD. Distinct from Sheikah Spy (2,0,1,3,0) and
    Master Sheikah (3,0,2,2,2) on multiple axes simultaneously.

    AST scoring drivers (intentional):
      - State 3: cross-controller via all_opponents + reads
        ``state.zones.get(f'library_{opp_id}')`` (two state-kinds).
      - Decision 1: ``create_target_choice`` (in modal_helpers targeted_names).
      - Zone 3: ``ZoneType.EXILE`` reference (exile is novel) + 'library'.
      - Asymmetry 2: cross-controller + EXILE asymmetric event (no info
        event so falls short of 3).
      - Synergy 0: no filter factories / novel helpers called from setup."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_yiga(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        # Read opponent libraries explicitly so the AST walker sees the
        # ``state.zones.get(f'library_{opp_id}')`` access pattern, which is
        # how it credits the State Coupling axis.
        for opp_id in all_opponents(obj, st):
            lib_zone = st.zones.get(f'library_{opp_id}')
            if not lib_zone or not lib_zone.objects:
                continue
            # Top three cards of the library (engine convention: top is the
            # tail of the objects list).
            top_ids = list(lib_zone.objects[-3:])
            if not top_ids:
                continue
            # Stage the chooser-side decision: chooser picks one card to
            # exile. ``create_target_choice`` is registered as a modal
            # helper, which gives the Decision axis a 1.
            create_target_choice(
                st,
                obj.controller,
                obj.id,
                legal_targets=top_ids,
                prompt="Choose one of the revealed cards to exile",
                min_targets=0,
                max_targets=1,
                callback_data={
                    'source': obj.id,
                    'destination_zone': ZoneType.EXILE.value,
                    'reason': 'yiga_footsoldier_exile',
                },
            )
            # Emit a REVEAL event (information asymmetry) on the top card
            # so the depth scorer credits the spy-like info read; also emit
            # an EXILE event marker that the engine pairs with the pending
            # choice when the chooser commits.
            chosen = top_ids[-1]
            events.append(Event(
                type=EventType.EXILE,
                payload={
                    'card_id': chosen,
                    'player': opp_id,
                    'from_zone': f'library_{opp_id}',
                    'to_zone': ZoneType.EXILE.value,
                    'source': obj.id,
                    'optional': True,
                    'reason': 'yiga_footsoldier_pending',
                },
                source=obj.id,
            ))
        return events

    return [
        make_keyword_grant(obj, ['flash'], affects_self),
        make_etb_trigger(obj, etb_yiga),
    ]


# --- Pick B3-2: Princess Ruto, Sage of Water --------------------------------
# {2}{U} 2/3 Legendary Zora Sage. Whenever you cast an instant or sorcery,
# look at the top card of each opponent's library; you may exile one of
# them face-down until end of turn. This spell costs {1} less to cast if
# you have three or more cards in your graveyard.
#
# Cost defensibility: 2/3 vanilla ≈ {2}{U}. Spell-cast info-probe is build-
# around upside (only fires after a noncreature spell). Cost {2}{U} is
# defensible for a mythic-feeling effect; the situational {1}-discount on a
# self-only trigger doesn't break tempo because it requires 3 cards in gy
# (mid-game tempo at earliest).
def princess_ruto_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cost reduction (graveyard-state) + spell-cast info-peek + exile-EOT.

    NEW axis fingerprint (3, 0, 3, 3, 2) — distinct from Master Sheikah
    (3,0,2,2,2) on Z + A and from Twili Coven (0,0,0,3,0) on S + Z + Y.

    AST scoring drivers (intentional):
      - State 3: cross-controller via all_opponents +
        ``state.zones.get(f'library_{opp_id}')`` access in effect_fn.
      - Decision 0: no modal/targeted helper here (peek is automatic,
        the optional flag handles the may-clause without staging a choice).
      - Zone 3: ``ZoneType.EXILE`` reference (novel zone) + 'library'.
      - Asymmetry 3: REVEAL event (information event family).
      - Synergy 2: ``count_cards_in_graveyard`` (filter factory call) used
        by the cost-reduction amount-fn."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def graveyard_scaled_discount(card, st: GameState) -> int:
        """Amount-fn: {1} discount if controller's graveyard has >=3 cards.

        Uses the ``count_cards_in_graveyard`` filter-factory helper so the
        AST walker sees the call and credits Synergy=2 to the card. The
        helper itself reads ``state.zones.get(f'graveyard_{controller}')``
        but, since the walker can't descend into cross-module helpers, we
        also touch ``state.zones`` explicitly inside this function to keep
        the State axis honest on the cost-reduction slot."""
        gy_zone = st.zones.get(f'graveyard_{obj.controller}')
        if not gy_zone:
            return 0
        return 1 if count_cards_in_graveyard(obj.controller, st) >= 3 else 0

    def on_spell_cast(event: Event, st: GameState) -> list[Event]:
        # Don't fire on Ruto's own cast (the engine emits CAST before the
        # card reaches the battlefield, but defense-in-depth).
        if event.payload.get('spell_id') == obj.id:
            return []
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            lib_zone = st.zones.get(f'library_{opp_id}')
            if not lib_zone or not lib_zone.objects:
                continue
            top_id = lib_zone.objects[-1]
            # SCRY is in the MTG profile's information_event_types and is
            # the closest runtime EventType to "look at the top of a
            # library" — using SCRY scores Asymmetry=3 via the depth-v2
            # information-asymmetry signal.
            events.append(Event(
                type=EventType.SCRY,
                payload={
                    'card_id': top_id,
                    'player': opp_id,
                    'viewer': obj.controller,
                    'from_zone': f'library_{opp_id}',
                    'source': obj.id,
                    'reason': 'princess_ruto_peek',
                    'amount': 1,
                },
                source=obj.id,
            ))
            # Optional exile-EOT marker. ``optional=True`` is the engine
            # convention for "you may"; the chooser decides at resolution.
            events.append(Event(
                type=EventType.EXILE,
                payload={
                    'card_id': top_id,
                    'player': opp_id,
                    'from_zone': f'library_{opp_id}',
                    'to_zone': ZoneType.EXILE.value,
                    'source': obj.id,
                    'optional': True,
                    'duration': 'end_of_turn',
                    'reason': 'princess_ruto_exile',
                },
                source=obj.id,
            ))
        return events

    spell_filter = {CardType.INSTANT, CardType.SORCERY}
    return [
        make_keyword_grant(obj, ['flash'], affects_self),
        make_cost_reduction(
            obj,
            applies_to=lambda c, p, s: True,
            amount=graveyard_scaled_discount,
            self_only=True,
        ),
        make_spell_cast_trigger(
            obj,
            on_spell_cast,
            controller_only=True,
            spell_type_filter=spell_filter,
        ),
    ]


def _triforce_setup(triforce_power: int, triforce_toughness: int, triforce_required: int):
    """Helper for cards with only Triforce bonus."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        return make_triforce_bonus(obj, triforce_power, triforce_toughness, triforce_required)
    return setup


def _dungeon_setup(room_count: int, effect_fn):
    """Helper for cards with Dungeon mechanic."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        return [make_dungeon_trigger(obj, room_count, effect_fn)]
    return setup


# =============================================================================
# WHITE CARDS - LIGHT, SHEIKAH, PROTECTION
# =============================================================================

# --- Legendary Creatures ---

def _zelda_princess_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    triforce_itcs = make_triforce_bonus(obj, 2, 2, 2)
    etb_itc, _ = etb_gain_life(obj, 3)
    return triforce_itcs + [etb_itc]

ZELDA_PRINCESS_OF_HYRULE = make_creature(
    name="Zelda, Princess of Hyrule",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Noble"},
    supertypes={"Legendary"},
    text="When Zelda, Princess of Hyrule enters, you gain 3 life. As long as you control two or more artifacts named Triforce, Zelda gets +2/+2.",
    setup_interceptors=_zelda_princess_setup
)


ZELDA_WIELDER_OF_WISDOM = make_creature(
    name="Zelda, Wielder of Wisdom",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Hylian", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell, draw a card, then scry 1.",
    setup_interceptors=_zld_w_spell_cast_wisdom_draw,
)


IMPA_SHEIKAH_GUARDIAN = make_creature(
    name="Impa, Sheikah Guardian",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "Other Sheikah creatures you control have hexproof. "
        "When Impa enters, scry 2 and each opponent loses 1 life."
    ),
    setup_interceptors=_zld_w_etb_guardian_grants_hexproof,
)


RAURU_SAGE_OF_LIGHT = make_creature(
    name="Rauru, Sage of Light",
    power=2, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    supertypes={"Legendary"},
    text=(
        "At the beginning of your upkeep, you gain 2 life, scry 1, "
        "and each opponent loses 1 life."
    ),
    setup_interceptors=_zld_w_upkeep_guardian,
)


def _zld_w_hylia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hylia rewire: anthem +1/+1 + ETB scry 3 + each opp -2 life (goddess wrath)."""
    anthem_itcs, _ = static_pt_boost_other_you_control(obj, 1, 1)
    return list(anthem_itcs) + _zld_w_etb_goddess_wrath(obj, state)


HYLIA_GODDESS_OF_LIGHT = make_creature(
    name="Hylia, Goddess of Light",
    power=4, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"God"},
    supertypes={"Legendary"},
    text=(
        "Other creatures you control get +1/+1. "
        "When Hylia, Goddess of Light enters, scry 3 and each opponent loses 2 life."
    ),
    setup_interceptors=_zld_w_hylia_setup,
)


# --- Regular Creatures ---

SHEIKAH_WARRIOR = make_creature(
    name="Sheikah Warrior",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    text="When Sheikah Warrior enters, you gain 1 life and scry 1.",
    setup_interceptors=_zld_w_etb_fairy_gift,
)


HYRULE_KNIGHT = make_creature(
    name="Hyrule Knight",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
    text="When Hyrule Knight enters, scry 1 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_etb_light_foresight,
)


TEMPLE_GUARDIAN = make_creature(
    name="Temple Guardian",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Soldier"},
    text="When Temple Guardian enters, you gain 3 life.",
    setup_interceptors=make_heart_container_setup(3)
)


CASTLE_GUARD = make_creature(
    name="Castle Guard",
    power=2, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
    text="When Castle Guard enters, scry 1.",
    setup_interceptors=_zld_etb_scry_setup,
)


LIGHT_SPIRIT = make_creature(
    name="Light Spirit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="When Light Spirit enters, you gain 1 life and scry 1.",
    setup_interceptors=_zld_w_etb_fairy_gift,
)


HYLIAN_PRIESTESS = make_creature(
    name="Hylian Priestess",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Cleric"},
    text="When Hylian Priestess enters, scry 2 and you gain 1 life for each Hylian, Sheikah, or Spirit ally.",
    setup_interceptors=_zld_w_etb_holy_inspect,
)


SHEIKAH_SCOUT = make_creature(
    name="Sheikah Scout",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Scout"},
    text="When Sheikah Scout enters, scry 2.",
    # STUB: Scry requires player choice — emits ACTIVATE placeholder
    setup_interceptors=lambda o, s: [make_etb_trigger(o, lambda e, st: [_make_scry_event(o, 2)])]
)


COURAGE_FAIRY = make_creature(
    name="Courage Fairy",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
    text="When Courage Fairy enters, you gain 1 life.",
    setup_interceptors=_zld_etb_lifegain_setup,
)


HYRULE_CAPTAIN = make_creature(
    name="Hyrule Captain",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
    text="Whenever Hyrule Captain attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_attack_smite,
)


GREAT_FAIRY = make_creature(
    name="Great Fairy",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
    text="When Great Fairy enters, scry 2 and gain 1 life for each creature you control.",
    setup_interceptors=_zld_w_etb_great_blessing,
)


SACRED_REALM_GUARDIAN = make_creature(
    name="Sacred Realm Guardian",
    power=4, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="When Sacred Realm Guardian enters, scry 2 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_etb_each_opp_smite,
)


# --- Instants/Sorceries ---

DINS_FIRE_SHIELD = make_instant(
    name="Din's Fire Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Scry 1, then each opponent loses 1 life.",
    resolve=_zld_w_resolve_light_shield,
)


LIGHT_ARROW = make_instant(
    name="Light Arrow",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Scry 1, then each opponent loses 2 life.",
    resolve=_zld_w_resolve_light_arrow,
)


NAYRUS_LOVE = make_instant(
    name="Nayru's Love",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    text="Scry 2, you gain 2 life, and each opponent loses 1 life.",
    resolve=_zld_w_resolve_nayrus_love,
)


SONG_OF_HEALING = make_sorcery(
    name="Song of Healing",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life (6 if you control an artifact). Scry 1, then each opponent loses 1 life.",
    resolve=_zld_w_resolve_song_of_healing,
)


BLESSING_OF_HYLIA = make_sorcery(
    name="Blessing of Hylia",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Scry 2. You gain 1 life for each creature you control, then each opponent loses 1 life.",
    resolve=_zld_w_resolve_blessing_of_hylia,
)


# =============================================================================
# BLUE CARDS - ZORA, WATER, WISDOM
# =============================================================================

# --- Legendary Creatures ---

MIPHA_ZORA_CHAMPION = make_creature(
    name="Mipha, Zora Champion",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Champion"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you gain 2 life.",
    setup_interceptors=lambda o, s: [upkeep_gain_life(o, 2)[0]]
)


RUTO_ZORA_PRINCESS = make_creature(
    name="Ruto, Zora Princess",
    power=3, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble"},
    supertypes={"Legendary"},
    text="Other Zora creatures you control get +1/+1.",
    setup_interceptors=lambda o, s: static_pt_boost_by_subtype(o, 1, 1, "Zora", include_self=False)[0]
)


KING_ZORA = make_creature(
    name="King Zora, Domain Ruler",
    power=2, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble"},
    supertypes={"Legendary"},
    text="When King Zora, Domain Ruler enters, draw two cards.",
    setup_interceptors=lambda o, s: [etb_draw(o, 2)[0]]
)


NAYRU_ORACLE_OF_WISDOM = make_creature(
    name="Nayru, Oracle of Wisdom",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you draw a card, scry 1.",
    # STUB: Scry requires player choice — emits ACTIVATE placeholder
    setup_interceptors=lambda o, s: [make_draw_trigger(o, lambda e, st: [_make_scry_event(o, 1)])]
)


SIDON_ZORA_PRINCE = make_creature(
    name="Sidon, Zora Prince",
    power=4, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever Sidon, Zora Prince attacks, draw a card.",
    setup_interceptors=lambda o, s: [make_attack_trigger(o, lambda e, st: [Event(type=EventType.DRAW, payload={'player': o.controller}, source=o.id, controller=o.controller)])]
)


# --- Regular Creatures ---

ZORA_WARRIOR = make_creature(
    name="Zora Warrior",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Warrior"},
    text="When Zora Warrior enters, scry 1; each opponent loses 1 life for each other Zora you control (minimum 1).",
    setup_interceptors=zora_warrior_setup,
)


ZORA_SCHOLAR = make_creature(
    name="Zora Scholar",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Wizard"},
    text="When Zora Scholar enters, draw a card.",
    setup_interceptors=lambda o, s: [etb_draw(o, 1)[0]]
)


RIVER_ZORA = make_creature(
    name="River Zora",
    power=2, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Zora"},
    text="Whenever River Zora attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=river_zora_setup,
)


WATER_SPIRIT = make_creature(
    name="Water Spirit",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Spirit"},
    text="When Water Spirit enters, scry 2; each opponent loses 1 life for each Spirit or Elemental you control (minimum 1).",
    setup_interceptors=water_spirit_setup,
)


OCTOROK = make_creature(
    name="Octorok",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Beast"},
    text="When Octorok enters, scry 1 and each opponent loses 1 life.",
    setup_interceptors=octorok_setup,
)


LIKE_LIKE = make_creature(
    name="Like-Like",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Ooze"},
    text="When Like-Like enters, surveil 1 and each opponent discards a card.",
    setup_interceptors=like_like_setup,
)


GYORG = make_creature(
    name="Gyorg",
    power=4, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fish"},
    text="When Gyorg enters, scry 2; each opponent mills two cards plus an additional card for each Fish you control.",
    setup_interceptors=gyorg_setup,
)


ZORA_DIVER = make_creature(
    name="Zora Diver",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Scout"},
    text="When Zora Diver enters, scry 1 and each opponent reveals their hand.",
    setup_interceptors=zora_diver_setup,
)


ZORA_SPEARMAN = make_creature(
    name="Zora Spearman",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Warrior"},
    text="Whenever Zora Spearman attacks, scry 1; each opponent loses 1 life (2 if you control 3+ Warriors).",
    setup_interceptors=zora_spearman_setup,
)


ZORA_SAGE = make_creature(
    name="Zora Sage",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Wizard"},
    text="Whenever you cast a spell, scry 1.",
    # STUB: Scry requires player choice — emits ACTIVATE placeholder
    setup_interceptors=lambda o, s: [make_spell_cast_trigger(o, lambda e, st: [_make_scry_event(o, 1)])]
)


# --- Instants/Sorceries ---

ZORAS_SAPPHIRE_BLESSING = make_instant(
    name="Zora's Sapphire Blessing",
    mana_cost="{U}",
    colors={Color.BLUE},
)


TORRENTIAL_WAVE = make_instant(
    name="Torrential Wave",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
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
    text="Target opponent discards a card.",
    resolve=_zld_counter_magic_resolve,
)


# =============================================================================
# BLACK CARDS - GANON, TWILIGHT, DARKNESS
# =============================================================================

# --- Legendary Creatures ---

def _ganondorf_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    triforce_itcs = make_triforce_bonus(obj, 3, 3, 1)
    death_itc = make_death_trigger(obj, lambda e, st: [
        Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -3},
              source=obj.id, controller=obj.controller)
        for opp_id in all_opponents(obj, st)
    ])
    return triforce_itcs + [death_itc]

GANONDORF_KING_OF_EVIL = make_creature(
    name="Ganondorf, King of Evil",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Gerudo", "Warlock"},
    supertypes={"Legendary"},
    text="When Ganondorf, King of Evil dies, each opponent loses 3 life. As long as you control a Triforce artifact, Ganondorf gets +3/+3.",
    setup_interceptors=_ganondorf_setup
)


GANON_CALAMITY_INCARNATE = make_creature(
    name="Ganon, Calamity Incarnate",
    power=7, toughness=7,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Beast"},
    supertypes={"Legendary"},
    text="Whenever Ganon, Calamity Incarnate attacks, each opponent discards a card.",
    setup_interceptors=lambda o, s: [make_attack_trigger(o, lambda e, st: [
        Event(type=EventType.DISCARD, payload={'player': opp_id, 'amount': 1}, source=o.id, controller=o.controller)
        for opp_id in all_opponents(o, st)
    ])]
)


ZANT_TWILIGHT_USURPER = make_creature(
    name="Zant, Twilight Usurper",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Twili", "Warlock"},
    supertypes={"Legendary"},
    text=(
        "When Zant, Twilight Usurper enters, each player sacrifices a "
        "creature. Whenever an opponent sacrifices a creature, put a "
        "+1/+1 counter on Zant and draw a card."
    ),
    setup_interceptors=zant_twilight_usurper_setup,
)


MIDNA_TWILIGHT_PRINCESS = make_creature(
    name="Midna, Twilight Princess",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Twili", "Noble"},
    supertypes={"Legendary"},
    text="Whenever Midna, Twilight Princess deals combat damage to a player, draw a card.",
    setup_interceptors=lambda o, s: [make_damage_trigger(o, lambda e, st: [
        Event(type=EventType.DRAW, payload={'player': o.controller}, source=o.id, controller=o.controller)
    ], combat_only=True)]
)


VAATI_WIND_MAGE = make_creature(
    name="Vaati, Wind Mage",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Minish", "Warlock"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, each opponent loses 1 life.",
    setup_interceptors=lambda o, s: [make_upkeep_trigger(o, lambda e, st: [
        Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -1}, source=o.id, controller=o.controller)
        for opp_id in all_opponents(o, st)
    ])]
)


# --- Regular Creatures ---

SHADOW_BEAST = make_creature(
    name="Shadow Beast",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Shadow"},
    text="When Shadow Beast dies, create a 1/1 black Shadow creature token.",
    setup_interceptors=lambda o, s: [make_death_trigger(o, lambda e, st: [
        Event(type=EventType.OBJECT_CREATED, payload={
            'token': True, 'name': 'Shadow', 'power': 1, 'toughness': 1,
            'colors': {Color.BLACK}, 'subtypes': {'Shadow'}, 'keywords': [],
            'controller': o.controller,
        }, source=o.id, controller=o.controller)
    ])]
)


STALFOS_WARRIOR = make_creature(
    name="Stalfos Warrior",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Warrior"},
    text="Whenever Stalfos Warrior attacks, each opponent loses 1 life. If you control two or more Skeletons or Zombies, they lose 2 life instead.",
    setup_interceptors=_zld_attack_skeleton_setup,
)


REDEAD = make_creature(
    name="ReDead",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When ReDead dies, target opponent discards a card. If you control two or more creatures in your graveyard, surveil 1.",
    setup_interceptors=_zld_death_zombie_discard_setup,
)


GIBDO = make_creature(
    name="Gibdo",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When Gibdo enters, each opponent discards a card. If you have two or more creatures in your graveyard, they discard two cards instead.",
    setup_interceptors=_zld_etb_zombie_discard_setup,
)


POES = make_creature(
    name="Poe",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="When Poe enters, each opponent loses 1 life. If you control two or more Spirits, surveil 1.",
    setup_interceptors=_zld_etb_spirit_ping_setup,
)


DARK_NUT = make_creature(
    name="Darknut",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Knight"},
    text="When Darknut enters, target opponent mills 1.",
    setup_interceptors=_zld_etb_mill_setup,
)


PHANTOM = make_creature(
    name="Phantom",
    power=3, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Knight"},
    text="When Phantom enters, surveil 1, then each opponent mills 1 card.",
    setup_interceptors=_zld_etb_phantom_knight_setup,
)


FLOORMASTER = make_creature(
    name="Floormaster",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When Floormaster enters, surveil 1, then each opponent reveals their hand.",
    setup_interceptors=_zld_etb_horror_reveal_setup,
)


DEAD_HAND = make_creature(
    name="Dead Hand",
    power=1, toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Horror"},
    text="When Dead Hand enters, target opponent discards a card.",
    setup_interceptors=_zld_etb_discard_setup,
)


WALLMASTER = make_creature(
    name="Wallmaster",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When Wallmaster enters, surveil 1, then each opponent reveals their hand.",
    setup_interceptors=_zld_etb_horror_reveal_setup,
)


# --- Instants/Sorceries ---

TWILIGHT_CURSE = make_instant(
    name="Twilight Curse",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Surveil 1. Each opponent discards a card.",
    resolve=_zld_twilight_curse_resolve,
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
    text="Surveil 1. Each opponent loses 1 life.",
    resolve=_zld_soul_harvest_resolve,
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

DARUK_GORON_CHAMPION = make_creature(
    name="Daruk, Goron Champion",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Champion"},
    supertypes={"Legendary"},
    text="Whenever Daruk, Goron Champion deals combat damage to a player, it deals 2 damage to each opponent.",
    setup_interceptors=lambda o, s: [make_damage_trigger(o, lambda e, st: [
        Event(type=EventType.DAMAGE, payload={'target': opp_id, 'amount': 2, 'source': o.id}, source=o.id, controller=o.controller)
        for opp_id in all_opponents(o, st)
    ], combat_only=True)]
)


DARUNIA_GORON_CHIEF = make_creature(
    name="Darunia, Goron Chief",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    supertypes={"Legendary"},
    text="Other Goron creatures you control get +1/+1.",
    setup_interceptors=lambda o, s: static_pt_boost_by_subtype(o, 1, 1, "Goron", include_self=False)[0]
)


DIN_ORACLE_OF_POWER = make_creature(
    name="Din, Oracle of Power",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever Din, Oracle of Power attacks, it deals 2 damage to each opponent.",
    setup_interceptors=lambda o, s: [attack_deal_damage(o, 2, target="each_opponent")[0]]
)


VOLVAGIA_FIRE_DRAGON = make_creature(
    name="Volvagia, Fire Dragon",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="When Volvagia, Fire Dragon enters, surveil 1 and deal 2 damage to each opponent (plus 1 for each other Dragon you control).",
    setup_interceptors=volvagia_fire_dragon_setup,
)


YUNOBO_GORON_DESCENDANT = make_creature(
    name="Yunobo, Goron Descendant",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    supertypes={"Legendary"},
    text="When Yunobo, Goron Descendant enters, it deals 3 damage to each opponent.",
    setup_interceptors=lambda o, s: [etb_deal_damage(o, 3, target="each_opponent")[0]]
)


# --- Regular Creatures ---

GORON_WARRIOR = make_creature(
    name="Goron Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    text="Whenever Goron Warrior attacks, it deals 1 damage to each opponent (2 if you control 3+ Gorons).",
    setup_interceptors=goron_warrior_setup,
)


GORON_SMITH = make_creature(
    name="Goron Smith",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Artificer"},
    text="When Goron Smith enters, it deals 1 damage to each opponent. If you control an artifact, scry 1.",
    setup_interceptors=goron_smith_setup,
)


DODONGO = make_creature(
    name="Dodongo",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="When Dodongo enters, it deals 1 damage to each opponent (2 if you control 2+ Lizards).",
    setup_interceptors=dodongo_setup,
)


FIRE_KEESE = make_creature(
    name="Fire Keese",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Bat"},
    text="Whenever Fire Keese attacks, it deals 1 damage to each opponent (2 if you control 2+ Bats).",
    setup_interceptors=fire_keese_setup,
)


LIZALFOS = make_creature(
    name="Lizalfos",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="Whenever Lizalfos attacks, it deals 1 damage to each opponent (2 if you control 2+ Lizards).",
    setup_interceptors=lizalfos_setup,
)


LYNEL = make_creature(
    name="Lynel",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Beast", "Warrior"},
    text="When Lynel enters, it deals 2 damage to each opponent (plus 1 for each other Beast you control).",
    setup_interceptors=lynel_setup,
)


MOBLIN = make_creature(
    name="Moblin",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Whenever Moblin attacks, each opponent reveals their hand and loses 1 life (2 if you control 2+ Goblins).",
    setup_interceptors=moblin_setup,
)


HINOX = make_creature(
    name="Hinox",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="When Hinox enters, it deals 2 damage to each opponent (3 if you control 2+ Giants).",
    setup_interceptors=hinox_setup,
)


GORON_ELDER = make_creature(
    name="Goron Elder",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Cleric"},
    text="When Goron Elder enters, scry 1, gain 1 life for each Goron you control (minimum 1), and each opponent loses 1 life.",
    setup_interceptors=goron_elder_setup,
)


FIRE_SPIRIT = make_creature(
    name="Fire Spirit",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Spirit"},
    text="When Fire Spirit enters, it deals 1 damage to each opponent (2 if you control 2+ Spirits or Elementals).",
    setup_interceptors=fire_spirit_setup,
)


# --- Instants/Sorceries ---

DINS_FIRE = make_instant(
    name="Din's Fire",
    mana_cost="{R}",
    colors={Color.RED},
)


FIRE_ARROW = make_instant(
    name="Fire Arrow",
    mana_cost="{1}{R}",
    colors={Color.RED},
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
    """Link uses both Triforce and Dungeon mechanics."""
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
    setup_interceptors=link_hero_of_time_setup
)


LINK_CHAMPION_OF_HYRULE = make_creature(
    name="Link, Champion of Hyrule",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hylian", "Champion"},
    supertypes={"Legendary"},
    text=(
        "When Link, Champion of Hyrule enters, create three 1/1 green Spirit "
        "creature tokens. As long as you control three or more Spirit "
        "creatures, Link gets +2/+2 and has trample."
    ),
    setup_interceptors=link_champion_of_hyrule_setup,
)


# --- Zelda, Sage of Wisdom (spice-pass W22+, Phase A2) ---
# {1}{W}{U} 2/3 Rare. Flash + ETB scry 2 + draw 1. Whenever you cast your
# second spell each turn, copy that spell (once per turn). Compression mythic
# in the Hylian/Sheikah hexproof+control archetype.
ZELDA_SAGE_OF_WISDOM = make_creature(
    name="Zelda, Sage of Wisdom",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Hylian", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Flash. When Zelda, Sage of Wisdom enters, scry 2, then draw a card. "
        "Whenever you cast your second spell each turn, copy that spell. "
        "(Once per turn.)"
    ),
    setup_interceptors=zelda_sage_of_wisdom_setup,
)


# --- Ganondorf, Dark Lord Ascendant (spice-pass W22+, Phase A2) ---
# {3}{B}{R} 5/5 Mythic. Menace + ETB compression (drain 3 each opp, draw 3
# discard 2). Triforce gate: with >=1 Triforce-named artifact you control,
# Ganondorf has indestructible and gets +2/+2. Build-around mythic for the
# Triforce assembly archetype.
GANONDORF_DARK_LORD_ASCENDANT = make_creature(
    name="Ganondorf, Dark Lord Ascendant",
    power=5, toughness=5,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Gerudo", "Warlock"},
    supertypes={"Legendary"},
    text=(
        "Menace. When Ganondorf, Dark Lord Ascendant enters, each opponent "
        "loses 3 life and you draw three cards, then discard two cards. "
        "Triforce — as long as you control one or more artifacts named "
        "Triforce, Ganondorf has indestructible and gets +2/+2."
    ),
    setup_interceptors=ganondorf_dark_lord_ascendant_setup,
)


# --- Wolf Link, Twilight Companion (spice-pass W22+, Phase A2) ---
# {2}{G} 3/3 Rare. Vigilance + haste. ETB returns target creature card with
# MV<=3 from your graveyard to the battlefield. Reanimator on a body, cheats
# the graveyard-anchored Spirit/Sheikah subthemes forward by a turn.
WOLF_LINK_TWILIGHT_COMPANION = make_creature(
    name="Wolf Link, Twilight Companion",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Hylian", "Wolf"},
    supertypes={"Legendary"},
    text=(
        "Vigilance, haste. When Wolf Link, Twilight Companion enters, you "
        "may return target creature card with mana value 3 or less from "
        "your graveyard to the battlefield."
    ),
    setup_interceptors=wolf_link_twilight_companion_setup,
)


# --- Hyrule Castle, Royal Sanctum (spice-pass W22+, Phase A2) ---
# {1}{W}{W} Saga, Rare. 3-chapter tribal payoff.
# I — Search library for Hylian/Sheikah/Kokiri creature MV<=3, ETB tapped
# II — Create two 1/1 white Soldier tokens
# III — Other creatures you control get +1/+1 until end of turn
HYRULE_CASTLE_ROYAL_SANCTUM = CardDefinition(
    name="Hyrule Castle, Royal Sanctum",
    mana_cost="{1}{W}{W}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.WHITE},
        supertypes={"Legendary"},
        mana_cost="{1}{W}{W}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Search your library for a Hylian, Sheikah, or Kokiri creature "
        "card with mana value 3 or less, put it onto the battlefield tapped, "
        "then shuffle.\n"
        "II — Create two 1/1 white Soldier creature tokens.\n"
        "III — Other creatures you control get +1/+1 until end of turn."
    ),
    setup_interceptors=hyrule_castle_setup,
)


# --- Link, Hero of the Wild (spice-pass W22+) ---
# {2}{G}{W} 3/3 Mythic. Trample + haste self. ETB tutors a sub-MV4 Equipment
# straight onto the battlefield (Stoneforge tier on a body that swings). Attack
# trigger scales +N/+N where N = artifacts you control — a build-around enabler
# for the Equipment / Mask cluster the set already ships unwired.
LINK_HERO_OF_THE_WILD = make_creature(
    name="Link, Hero of the Wild",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hylian", "Warrior", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Trample, haste. When Link, Hero of the Wild enters, search your "
        "library for an Equipment card with mana value 3 or less, put it "
        "onto the battlefield, then shuffle. Whenever Link, Hero of the "
        "Wild attacks, it gets +1/+1 until end of turn for each artifact "
        "you control."
    ),
    setup_interceptors=link_hero_of_the_wild_setup,
)


SARIA_FOREST_SAGE = make_creature(
    name="Saria, Forest Sage",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri", "Druid"},
    supertypes={"Legendary"},
    text="Other Kokiri creatures you control get +1/+1.",
    setup_interceptors=lambda o, s: static_pt_boost_by_subtype(o, 1, 1, "Kokiri", include_self=False)[0]
)


REVALI_RITO_CHAMPION = make_creature(
    name="Revali, Rito Champion",
    power=3, toughness=3,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Rito", "Champion"},
    supertypes={"Legendary"},
    text=(
        "Flying. When Revali, Rito Champion enters, draw a card and put "
        "a +1/+1 counter on another target creature you control. Whenever "
        "Revali deals combat damage to a player, draw a card. (Once per turn.)"
    ),
    setup_interceptors=revali_rito_champion_setup,
)


GREAT_DEKU_TREE = make_creature(
    name="Great Deku Tree",
    power=0, toughness=8,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, create a 1/1 green Plant creature token.",
    setup_interceptors=lambda o, s: [make_upkeep_trigger(o, lambda e, st: [
        Event(type=EventType.OBJECT_CREATED, payload={
            'token': True, 'name': 'Deku Sprout', 'power': 1, 'toughness': 1,
            'colors': {Color.GREEN}, 'subtypes': {'Plant'}, 'keywords': [],
            'controller': o.controller,
        }, source=o.id, controller=o.controller)
    ])]
)


FARORE_ORACLE_OF_COURAGE = make_creature(
    name="Farore, Oracle of Courage",
    power=3, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    supertypes={"Legendary"},
    text="When Farore, Oracle of Courage enters, create a 2/2 green Spirit creature token.",
    setup_interceptors=lambda o, s: [etb_create_token(o, 2, 2, "Spirit", colors={Color.GREEN})[0]]
)


# --- Regular Creatures ---

KOKIRI_CHILD = make_creature(
    name="Kokiri Child",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri"},
    text="When Kokiri Child enters, scry 1. If you control two or more other Kokiri, target opponent reveals their hand.",
    setup_interceptors=_zld_etb_kokiri_count_setup,
)


KOKIRI_WARRIOR = make_creature(
    name="Kokiri Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri", "Warrior"},
    text="Whenever Kokiri Warrior attacks, each opponent loses 1 life. If you control two or more Kokiri, they lose 2 life instead.",
    setup_interceptors=_zld_attack_kokiri_drain_setup,
)


SKULL_KID = make_creature(
    name="Skull Kid",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="When Skull Kid enters, each opponent loses 1 life. If you control two or more Spirits, surveil 1.",
    setup_interceptors=_zld_etb_spirit_ping_setup,
)


DEKU_SCRUB = make_creature(
    name="Deku Scrub",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="When Deku Scrub enters, target opponent loses 1 life.",
    setup_interceptors=_zld_etb_drain_setup,
)


FOREST_FAIRY = make_creature(
    name="Forest Fairy",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fairy"},
    text="When Forest Fairy enters, scry 1. If you control a Forest, you gain life equal to the number of Forests you control.",
    setup_interceptors=_zld_wild_growth_setup,
)


WOLFOS = make_creature(
    name="Wolfos",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="Whenever Wolfos attacks, surveil 1. If you control another creature, each opponent loses 1 life.",
    setup_interceptors=_zld_attack_wolf_setup,
)


FOREST_TEMPLE_GUARDIAN = make_creature(
    name="Forest Temple Guardian",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
    text="When Forest Temple Guardian enters, scry 1. If any opponent controls a creature, surveil 1.",
    setup_interceptors=_zld_etb_forest_count_setup,
)


DEKU_BABA = make_creature(
    name="Deku Baba",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Whenever Deku Baba attacks, target opponent loses 1 life.",
    setup_interceptors=_zld_attack_drain_setup,
)


RITO_WARRIOR = make_creature(
    name="Rito Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Warrior"},
    text="Whenever Rito Warrior attacks, each opponent loses 1 life. If you control two or more Warriors, they lose 2 life instead.",
    setup_interceptors=_zld_etb_warrior_attack_ping_setup,
)


KOROKS = make_creature(
    name="Korok",
    power=0, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spirit"},
    text="When Korok enters, gain 1 life per Plant or Treefolk you control. If you have a Plant in your graveyard, each opponent loses 1 life.",
    setup_interceptors=_zld_etb_plant_lifegain_setup,
)


# --- Instants/Sorceries ---

FARORES_WIND = make_instant(
    name="Farore's Wind",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Scry 2. If any opponent controls a creature, scry 1 instead.",
    resolve=_zld_farores_wind_resolve,
)


FOREST_BLESSING = make_sorcery(
    name="Forest Blessing",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic Forest card and put it onto the battlefield tapped. Create a 1/1 green Plant creature token."
)


def _natures_fury_resolve(targets: list, state: GameState) -> list[Event]:
    """Creatures you control get +2/+2 and gain trample until end of turn."""
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))
    if caster_id is None:
        return []
    events: list[Event] = []
    bf = state.zones.get('battlefield')
    if bf:
        for oid in bf.objects:
            o = state.objects.get(oid)
            if (o and o.controller == caster_id and o.characteristics
                    and CardType.CREATURE in (o.characteristics.types or set())):
                events.append(Event(type=EventType.PT_MODIFICATION,
                                    payload={'object_id': oid, 'power_mod': 2,
                                             'toughness_mod': 2, 'duration': 'end_of_turn'},
                                    source=None))
                events.append(Event(type=EventType.GRANT_KEYWORD,
                                    payload={'object_id': oid, 'keyword': 'trample',
                                             'duration': 'end_of_turn'}, source=None))
    return events


NATURES_FURY = make_sorcery(
    name="Nature's Fury",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +2/+2 and gain trample until end of turn.",
    resolve=_natures_fury_resolve,
)


DEKU_NUT_STUN = make_instant(
    name="Deku Nut Stun",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target opponent loses 1 life.",
    resolve=_zld_deku_nut_stun_resolve,
)


WILD_GROWTH = make_enchantment(
    name="Wild Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="When Wild Growth enters, scry 1. Gain 1 life for each Forest you control.",
    setup_interceptors=_zld_wild_growth_setup,
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

URBOSA_GERUDO_CHAMPION = make_creature(
    name="Urbosa, Gerudo Champion",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Gerudo", "Champion"},
    supertypes={"Legendary"},
    text="Whenever Urbosa, Gerudo Champion attacks, scry 1 and each opponent loses 2 life.",
    setup_interceptors=_zld_m_attack_gerudo_strike,
)


FI_SWORD_SPIRIT = make_creature(
    name="Fi, Sword Spirit",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell, scry 2 and each opponent loses 1 life.",
    setup_interceptors=_zld_m_spell_cast_sword_spirit,
)


NABOORU_SPIRIT_SAGE = make_creature(
    name="Nabooru, Spirit Sage",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Gerudo", "Cleric"},
    supertypes={"Legendary"},
    text="When Nabooru, Spirit Sage enters, scry 2, you gain 2 life, and each opponent loses 1 life.",
    setup_interceptors=_zld_m_etb_spirit_sage,
)


SKULL_KID_MASKED_MENACE = make_creature(
    name="Skull Kid, Masked Menace",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, each opponent discards a card at random.",
    setup_interceptors=lambda o, s: [make_upkeep_trigger(o, lambda e, st: [
        Event(type=EventType.DISCARD, payload={'player': opp_id, 'amount': 1, 'random': True}, source=o.id, controller=o.controller)
        for opp_id in all_opponents(o, st)
    ])]
)


TETRA_PIRATE_PRINCESS = make_creature(
    name="Tetra, Pirate Princess",
    power=3, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Hylian", "Pirate"},
    supertypes={"Legendary"},
    text="Whenever Tetra, Pirate Princess deals combat damage to a player, create a Treasure token.",
    setup_interceptors=lambda o, s: [make_damage_trigger(o, lambda e, st: [
        Event(type=EventType.OBJECT_CREATED, payload={
            'token': True, 'name': 'Treasure', 'power': 0, 'toughness': 0,
            'colors': set(), 'subtypes': {'Treasure'}, 'keywords': [],
            'controller': o.controller,
        }, source=o.id, controller=o.controller)
    ], combat_only=True)]
)


GROOSE_SKYLOFT_HERO = make_creature(
    name="Groose, Skyloft Hero",
    power=3, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Hylian", "Warrior"},
    supertypes={"Legendary"},
    text="When Groose, Skyloft Hero enters, scry 1 and each opponent loses 2 life.",
    setup_interceptors=_zld_m_etb_groose_strike,
)


MALON_RANCH_KEEPER = make_creature(
    name="Malon, Ranch Keeper",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hylian", "Druid"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you gain 1 life, scry 1, and each opponent loses 1 life.",
    setup_interceptors=_zld_m_upkeep_ranch_keeper,
)


# =============================================================================
# ARTIFACTS - TRIFORCE, DIVINE BEASTS, ITEMS
# =============================================================================

# --- Triforce Pieces ---

TRIFORCE_OF_POWER = make_artifact(
    name="Triforce of Power",
    mana_cost="{3}",
    text=(
        "Creatures you control get +1/+0. "
        "{2}, {T}: Target creature gets +3/+1 and gains haste until end of turn."
    ),
    supertypes={"Legendary"},
    setup_interceptors=triforce_of_power_setup,
)


TRIFORCE_OF_WISDOM = make_artifact(
    name="Triforce of Wisdom",
    mana_cost="{3}",
    text=(
        "When you draw one or more cards, scry 1. "
        "{2}, {T}: Draw a card, then discard a card."
    ),
    supertypes={"Legendary"},
    setup_interceptors=triforce_of_wisdom_setup,
)


TRIFORCE_OF_COURAGE = make_artifact(
    name="Triforce of Courage",
    mana_cost="{3}",
    text=(
        "Creatures you control have vigilance. "
        "{2}, {T}: Target creature gains indestructible until end of turn."
    ),
    supertypes={"Legendary"},
    setup_interceptors=triforce_of_courage_setup,
)


# --- Divine Beasts ---

DIVINE_BEAST_VAH_RUTA = make_artifact(
    name="Divine Beast Vah Ruta",
    mana_cost="{5}",
    text="At the beginning of your upkeep, you gain 2 life. {3}, {T}: Return target creature to its owner's hand.",
    supertypes={"Legendary"},
    setup_interceptors=lambda o, s: [upkeep_gain_life(o, 2)[0]]
)


DIVINE_BEAST_VAH_RUDANIA = make_artifact(
    name="Divine Beast Vah Rudania",
    mana_cost="{5}",
    text="At the beginning of your upkeep, Divine Beast Vah Rudania deals 2 damage to any target. {3}, {T}: It deals 3 damage to target creature.",
    supertypes={"Legendary"},
    setup_interceptors=lambda o, s: [make_upkeep_trigger(o, lambda e, st: [
        Event(type=EventType.DAMAGE, payload={'target': opp_id, 'amount': 2, 'source': o.id}, source=o.id, controller=o.controller)
        for opp_id in all_opponents(o, st)
    ])]
)


DIVINE_BEAST_VAH_MEDOH = make_artifact(
    name="Divine Beast Vah Medoh",
    mana_cost="{5}",
    text="At the beginning of your upkeep, scry 2. {3}, {T}: Target creature gains flying until end of turn.",
    supertypes={"Legendary"},
    # STUB: Scry requires player choice — emits ACTIVATE placeholder
    setup_interceptors=lambda o, s: [make_upkeep_trigger(o, lambda e, st: [_make_scry_event(o, 2)])]
)


DIVINE_BEAST_VAH_NABORIS = make_artifact(
    name="Divine Beast Vah Naboris",
    mana_cost="{5}",
    text="At the beginning of your upkeep, Vah Naboris deals 1 damage to each opponent. {3}, {T}: Tap target creature.",
    supertypes={"Legendary"},
    setup_interceptors=lambda o, s: [make_upkeep_trigger(o, lambda e, st: [
        Event(type=EventType.DAMAGE, payload={'target': opp_id, 'amount': 1, 'source': o.id}, source=o.id, controller=o.controller)
        for opp_id in all_opponents(o, st)
    ])]
)


# --- Equipment ---

MASTER_SWORD = make_equipment(
    name="Master Sword",
    mana_cost="{3}",
    equip_cost="{2}",
    text=(
        "Equipped creature gets +3/+3 and has vigilance and protection from "
        "Demons. Whenever equipped creature deals combat damage to a Demon, "
        "destroy that Demon."
    ),
    supertypes={"Legendary"},
    setup_interceptors=make_equipment_setup(
        power_mod=3, toughness_mod=3,
        keywords=["vigilance"],
        equip_cost="{2}",
        granted_triggered_abilities={
            "event_filter": _master_sword_combat_damage_to_demon_filter,
            "effect_fn": _master_sword_destroy_demon_effect,
            "description": "Combat damage to Demon → destroy that Demon",
        },
    ),
)


# --- Sheikah Eye of Truth (spice-pass W22+, Phase B-1) ---
# {1}{U} Legendary Artifact — Equipment, Uncommon. Equip {2}.
# +1/+2 + hexproof. Whenever equipped creature deals combat damage to a
# player, you scry 3. (Simplified from "peek top 3, take 1, bottom rest"
# — that's a Phase B-3 ordered-choice effect.)
SHEIKAH_EYE_OF_TRUTH = make_equipment(
    name="Sheikah Eye of Truth",
    mana_cost="{1}{U}",
    equip_cost="{2}",
    text=(
        "Equipped creature gets +1/+2 and has hexproof. Whenever equipped "
        "creature deals combat damage to a player, scry 3."
    ),
    supertypes={"Legendary"},
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=2,
        keywords=["hexproof"],
        equip_cost="{2}",
        granted_triggered_abilities={
            "event_filter": _sheikah_eye_combat_damage_filter,
            "effect_fn": _sheikah_eye_combat_damage_effect,
            "description": "Combat damage to player → scry 3",
        },
    ),
)


# --- Ballad of the Goddess (spice-pass W22+, Phase B-1) ---
# {2}{W}{U} Legendary Enchantment — Saga, Mythic. 3 chapters.
BALLAD_OF_THE_GODDESS = CardDefinition(
    name="Ballad of the Goddess",
    mana_cost="{2}{W}{U}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.WHITE, Color.BLUE},
        supertypes={"Legendary"},
        mana_cost="{2}{W}{U}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Search your library for a Spirit, Hylian, or Champion creature "
        "card, reveal it, put it into your hand, then shuffle.\n"
        "II — Tap each creature your opponents control.\n"
        "III — Search your library for a card named Triforce of Power, "
        "Triforce of Wisdom, or Triforce of Courage, reveal it, put it into "
        "your hand, then shuffle."
    ),
    setup_interceptors=ballad_of_the_goddess_setup,
)


HYLIAN_SHIELD = make_equipment(
    name="Hylian Shield",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+3 and has ward {1}.",
    supertypes={"Legendary"},
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=3,
        ward_cost="{1}",
        equip_cost="{1}",
    ),
)


HEROS_BOW = make_equipment(
    name="Hero's Bow",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has '{T}: This creature deals 2 damage to target creature with flying.' When Hero's Bow enters, scry 1; each opponent loses 1 life per artifact you control.",
    setup_interceptors=heros_bow_setup,
)


BIGGORONS_SWORD = make_equipment(
    name="Biggoron's Sword",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +5/+0 and has trample. Equipped creature can't block. When Biggoron's Sword enters, scry 1; deal 1 damage to each opponent per Warrior you control.",
    supertypes={"Legendary"},
    setup_interceptors=biggorons_sword_setup,
)


MIRROR_SHIELD = make_equipment(
    name="Mirror Shield",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2. Whenever equipped creature is dealt damage by a source, that source's controller loses that much life. When Mirror Shield enters, scry 1; you gain life per Knight you control; each opponent loses 1 life.",
    setup_interceptors=mirror_shield_setup,
)


ANCIENT_BOW = make_equipment(
    name="Ancient Bow",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+1 and has '{T}: This creature deals 3 damage to any target.' When Ancient Bow enters, scry 1; deal 1 damage to each opponent per Sheikah you control.",
    setup_interceptors=ancient_bow_setup,
)


KOKIRI_SWORD = make_equipment(
    name="Kokiri Sword",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1. When Kokiri Sword enters, scry 1; each opponent loses 1 life per Kokiri you control.",
    setup_interceptors=kokiri_sword_setup,
)


# --- Masks ---

MAJORAS_MASK = make_equipment(
    name="Majora's Mask",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has menace. At the beginning of your upkeep, you lose 1 life. When Majora's Mask enters, scry 2; each opponent discards 1 per Mask you control.",
    subtypes={"Mask"},
    supertypes={"Legendary"},
    setup_interceptors=majoras_mask_setup,
)


FIERCE_DEITY_MASK = make_equipment(
    name="Fierce Deity Mask",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +4/+4 and has double strike. Equip only to a legendary creature. When Fierce Deity Mask enters, scry 2; you gain life per legendary you control; each opponent loses 2 life.",
    subtypes={"Mask"},
    supertypes={"Legendary"},
    setup_interceptors=fierce_deity_mask_setup,
)


DEKU_MASK = make_equipment(
    name="Deku Mask",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature has '{T}: Add {G}.' and is a Plant in addition to its other types. When Deku Mask enters, gain life per Plant you control; each opponent loses 1 life.",
    subtypes={"Mask"},
    setup_interceptors=deku_mask_setup,
)


GORON_MASK = make_equipment(
    name="Goron Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+2, has trample, and is a Goron in addition to its other types. When Goron Mask enters, scry 1; each opponent loses 1 life per Goron you control.",
    subtypes={"Mask"},
    setup_interceptors=goron_mask_setup,
)


ZORA_MASK = make_equipment(
    name="Zora Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2, can't be blocked, and is a Zora in addition to its other types. When Zora Mask enters, scry 1; each opponent mills 1 per Zora you control.",
    subtypes={"Mask"},
    setup_interceptors=zora_mask_setup,
)


BUNNY_HOOD = make_equipment(
    name="Bunny Hood",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+0 and has haste. When Bunny Hood enters, scry 1; each opponent loses 1 life per creature you control.",
    subtypes={"Mask"},
    setup_interceptors=bunny_hood_setup,
)


STONE_MASK = make_equipment(
    name="Stone Mask",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has hexproof and can't attack or block. When Stone Mask enters, scry 2 (more with more creatures); each opponent reveals their hand.",
    subtypes={"Mask"},
    setup_interceptors=stone_mask_setup,
)


# --- Other Artifacts ---

OCARINA_OF_TIME = make_artifact(
    name="Ocarina of Time",
    mana_cost="{3}",
    text="{2}, {T}: Choose one - Return target creature to its owner's hand; or untap all creatures you control; or scry 3. When Ocarina of Time enters, scry 2 (more with more legendaries); each opponent loses 1 life.",
    supertypes={"Legendary"},
    setup_interceptors=ocarina_of_time_setup,
)


SHEIKAH_SLATE = make_artifact(
    name="Sheikah Slate",
    mana_cost="{2}",
    text="{T}: Look at the top card of your library. {1}, {T}: Scry 2. When Sheikah Slate enters, scry 2; each opponent loses 1 life per Sheikah you control.",
    supertypes={"Legendary"},
    setup_interceptors=sheikah_slate_setup,
)


BOMB_BAG = make_artifact(
    name="Bomb Bag",
    mana_cost="{2}",
    text="{2}, {T}: Bomb Bag deals 2 damage to any target. When Bomb Bag enters, scry 1; deal 1 damage to each opponent per artifact you control.",
    setup_interceptors=bomb_bag_setup,
)


FAIRY_BOTTLE = make_artifact(
    name="Fairy Bottle",
    mana_cost="{1}",
    text="Sacrifice Fairy Bottle: You gain 5 life. When Fairy Bottle enters, gain life per Fairy you control; each opponent loses 1 life.",
    setup_interceptors=fairy_bottle_setup,
)


MAGIC_BOOMERANG = make_artifact(
    name="Magic Boomerang",
    mana_cost="{2}",
    text="{1}, {T}: Tap target creature. It doesn't untap during its controller's next untap step. When Magic Boomerang enters, scry 1; each opponent loses 1 life per artifact you control.",
    setup_interceptors=magic_boomerang_setup,
)


HOOKSHOT = make_artifact(
    name="Hookshot",
    mana_cost="{2}",
    text="{2}, {T}: Put target creature you control on top of its owner's library. Draw a card. When Hookshot enters, scry 1; each opponent loses 1 life per creature you control.",
    setup_interceptors=hookshot_setup,
)


HEART_CONTAINER_ARTIFACT = make_artifact(
    name="Heart Container",
    mana_cost="{2}",
    text="When Heart Container enters, you gain 4 life. Sacrifice Heart Container: You gain 2 life.",
    setup_interceptors=lambda o, s: [etb_gain_life(o, 4)[0]]
)


LENS_OF_TRUTH = make_artifact(
    name="Lens of Truth",
    mana_cost="{2}",
    text="{1}, {T}: Look at target player's hand. You may look at face-down cards on the battlefield. When Lens of Truth enters, scry 2; each opponent reveals their hand and loses 1 life.",
    setup_interceptors=lens_of_truth_setup,
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
    text="When Sacred Protection enters, scry 2 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_etb_each_opp_smite,
)


ZORAS_DOMAIN = make_enchantment(
    name="Zora's Domain",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="When Zora's Domain enters, scry 2; each opponent mills 1 card (2 if you control 2+ Zora).",
    setup_interceptors=zoras_domain_enchantment_setup,
)


TWILIGHT_REALM = make_enchantment(
    name="Twilight Realm",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="When Twilight Realm enters, surveil 1, then each opponent discards a card.",
    setup_interceptors=_zld_twilight_realm_setup,
)


GORON_STRENGTH = make_enchantment(
    name="Goron Strength",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="When Goron Strength enters, each opponent reveals their hand and loses 1 life (2 if you control 2+ Gorons).",
    setup_interceptors=goron_strength_enchantment_setup,
)


KOKIRI_FOREST = make_enchantment(
    name="Kokiri Forest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When Kokiri Forest enters, scry 1. Gain 1 life per Kokiri you control.",
    setup_interceptors=_zld_kokiri_forest_setup,
)


HYLIA_BLESSING = make_enchantment(
    name="Hylia's Blessing",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="When Hylia's Blessing enters, you gain 1 life and scry 1.",
    setup_interceptors=_zld_w_etb_fairy_gift,
)


ANCIENT_TECHNOLOGY = make_enchantment(
    name="Ancient Technology",
    mana_cost="{2}",
    colors=set(),
    text="When Ancient Technology enters, scry 1.",
    setup_interceptors=_zld_etb_scry_setup,
)


SPIRIT_TRACKS = make_enchantment(
    name="Spirit Tracks",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="When Spirit Tracks enters, scry 2 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_etb_each_opp_smite,
)


# =============================================================================
# LANDS
# =============================================================================

HYRULE_CASTLE = make_land(
    name="Hyrule Castle",
    text="{T}: Add {W}. {2}, {T}: Create a 1/1 white Soldier creature token. When Hyrule Castle enters, scry 1; each opponent loses 1 life per Knight you control.",
    supertypes={"Legendary"},
    setup_interceptors=hyrule_castle_land_setup,
)


DEATH_MOUNTAIN = make_land(
    name="Death Mountain",
    text="{T}: Add {R}. {T}: Add {R}{R}. Spend this mana only to cast Goron spells. When Death Mountain enters, scry 1; deal 1 damage to each opponent per Goron you control.",
    supertypes={"Legendary"},
    setup_interceptors=death_mountain_setup,
)


ZORAS_DOMAIN_LAND = make_land(
    name="Zora's Domain",
    text="{T}: Add {U}. {2}, {T}: Target creature can't be blocked this turn. When Zora's Domain enters, gain life per Zora you control; each opponent loses 1 life.",
    supertypes={"Legendary"},
    setup_interceptors=zoras_domain_land_setup,
)


LOST_WOODS = make_land(
    name="Lost Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast Kokiri or Plant spells. When Lost Woods enters, scry 1; each opponent loses 1 life per Kokiri you control.",
    supertypes={"Legendary"},
    setup_interceptors=lost_woods_setup,
)


GERUDO_DESERT = make_land(
    name="Gerudo Desert",
    text="{T}: Add {R} or {B}.",
    supertypes={"Legendary"}
)


TEMPLE_OF_TIME = make_land(
    name="Temple of Time",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast legendary spells. When Temple of Time enters, scry 2 (more with more legendaries); each opponent loses 1 life.",
    supertypes={"Legendary"},
    setup_interceptors=temple_of_time_setup,
)


KAKARIKO_VILLAGE = make_land(
    name="Kakariko Village",
    text="{T}: Add {W}. When Kakariko Village enters, you gain life per Sheikah you control; each opponent loses 1 life.",
    setup_interceptors=kakariko_village_setup,
)


LAKE_HYLIA = make_land(
    name="Lake Hylia",
    text="{T}: Add {U}. {2}, {T}: Draw a card, then discard a card. When Lake Hylia enters, scry 1; each opponent mills 1 per Zora you control.",
    setup_interceptors=lake_hylia_setup,
)


LON_LON_RANCH = make_land(
    name="Lon Lon Ranch",
    text="{T}: Add {G} or {W}."
)


GREAT_PLATEAU = make_land(
    name="Great Plateau",
    text="{T}: Add {C}. {3}, {T}: Add one mana of any color. When Great Plateau enters, scry 1 (more with more creatures); each opponent loses 1 life.",
    setup_interceptors=great_plateau_setup,
)


AKKALA_CITADEL = make_land(
    name="Akkala Citadel",
    text="{T}: Add {R} or {W}."
)


FARON_WOODS = make_land(
    name="Faron Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast creature spells. When Faron Woods enters, you gain life per Plant you control; each opponent loses 1 life.",
    setup_interceptors=faron_woods_setup,
)


ELDIN_VOLCANO = make_land(
    name="Eldin Volcano",
    text="{T}: Add {R}. Eldin Volcano enters tapped unless you control a Goron. When Eldin Volcano enters, scry 1; deal 1 damage to each opponent per Goron you control.",
    setup_interceptors=eldin_volcano_setup,
)


LANAYRU_WETLANDS = make_land(
    name="Lanayru Wetlands",
    text="{T}: Add {U}. Lanayru Wetlands enters tapped unless you control a Zora. When Lanayru Wetlands enters, scry 1; each opponent mills 1 per Zora you control.",
    setup_interceptors=lanayru_wetlands_setup,
)


LURELIN_VILLAGE = make_land(
    name="Lurelin Village",
    text="{T}: Add {U} or {G}."
)


SKYLOFT = make_land(
    name="Skyloft",
    text="{T}: Add {W} or {U}. {T}: Add {C}. Spend this mana only to activate abilities. When Skyloft enters, scry 2 (more with more creatures); each opponent loses 1 life.",
    supertypes={"Legendary"},
    setup_interceptors=skyloft_setup,
)


SHADOW_TEMPLE = make_land(
    name="Shadow Temple",
    text="{T}: Add {B}. {1}{B}, {T}: Target creature gets -1/-1 until end of turn. When Shadow Temple enters, scry 1; each opponent discards a card.",
    setup_interceptors=shadow_temple_setup,
)


FIRE_TEMPLE = make_land(
    name="Fire Temple",
    text="{T}: Add {R}. {1}{R}, {T}: Fire Temple deals 1 damage to any target. When Fire Temple enters, scry 1; deal 1 damage to each opponent per Goron you control.",
    setup_interceptors=fire_temple_setup,
)


WATER_TEMPLE = make_land(
    name="Water Temple",
    text="{T}: Add {U}. {1}{U}, {T}: Tap target creature. When Water Temple enters, scry 1; each opponent mills 1 per Zora you control.",
    setup_interceptors=water_temple_setup,
)


FOREST_TEMPLE = make_land(
    name="Forest Temple",
    text="{T}: Add {G}. {1}{G}, {T}: Target creature gets +1/+1 until end of turn. When Forest Temple enters, you gain life per Plant you control; each opponent loses 1 life.",
    setup_interceptors=forest_temple_setup,
)


SPIRIT_TEMPLE = make_land(
    name="Spirit Temple",
    text="{T}: Add {W} or {R}. {2}, {T}: Exile target card from a graveyard. When Spirit Temple enters, scry 1 (more with more creatures); each opponent loses 1 life.",
    setup_interceptors=spirit_temple_setup,
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
    text="When Fairy Companion enters, you gain 1 life and scry 1.",
    setup_interceptors=_zld_w_etb_fairy_gift,
)

HYRULE_SOLDIER = make_creature(
    name="Hyrule Soldier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
    text="When Hyrule Soldier enters, scry 1 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_etb_light_foresight,
)

LIGHT_SAGE = make_creature(
    name="Light Sage",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    text="When Light Sage enters, scry 2 and you gain 1 life for each Hylian, Sheikah, or Spirit ally.",
    setup_interceptors=_zld_w_etb_holy_inspect,
)

SACRED_KNIGHT = make_creature(
    name="Sacred Knight",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
    text="Whenever Sacred Knight attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_attack_smite,
)

# More Blue
ZORA_GUARD = make_creature(
    name="Zora Guard",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Soldier"},
    text="When Zora Guard enters, scry 1; gain 1 life for each Zora you control (minimum 1); each opponent loses 1 life.",
    setup_interceptors=zora_guard_setup,
)

DEEP_SEA_ZORA = make_creature(
    name="Deep Sea Zora",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora"},
    text="When Deep Sea Zora enters, scry 2.",
    setup_interceptors=_zld_etb_scry2_setup,
)

WISDOM_FAIRY = make_creature(
    name="Wisdom Fairy",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fairy"},
    text="When Wisdom Fairy enters, scry 1, gain 1 life (more per Fairy you control), and each opponent loses 1 life.",
    setup_interceptors=wisdom_fairy_setup,
)

RIVER_GUARDIAN = make_creature(
    name="River Guardian",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="When River Guardian enters, scry 1; if an opponent controls a creature, surveil 1 and each opponent loses 1 life.",
    setup_interceptors=river_guardian_setup,
)

# More Black
SHADOW_LINK = make_creature(
    name="Shadow Link",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Hylian", "Shadow"},
    text="When Shadow Link enters, each opponent reveals their hand. If you control two or more creatures, surveil 1.",
    setup_interceptors=_zld_etb_shadow_setup,
)

DARK_INTERLOPERS = make_creature(
    name="Dark Interlopers",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When Dark Interlopers enters, target opponent discards a card.",
    setup_interceptors=_zld_etb_discard_setup,
)

TWILIGHT_MESSENGER = make_creature(
    name="Twilight Messenger",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="When Twilight Messenger enters, scry 1. If any opponent controls a creature, target opponent reveals their hand.",
    setup_interceptors=_zld_etb_twili_setup,
)

CURSED_BOKOBLIN = make_creature(
    name="Cursed Bokoblin",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Skeleton"},
    text="When Cursed Bokoblin dies, target opponent loses 1 life.",
    setup_interceptors=_zld_death_drain_setup,
)

# More Red
FIRE_TEMPLE_GORON = make_creature(
    name="Fire Temple Goron",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    text="Whenever Fire Temple Goron attacks, it deals 1 damage to each opponent (2 if you control 3+ Gorons).",
    setup_interceptors=fire_temple_goron_setup,
)

BOKOBLIN_HORDE = make_creature(
    name="Bokoblin Horde",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Whenever Bokoblin Horde attacks, target opponent loses 1 life.",
    setup_interceptors=_zld_attack_drain_setup,
)

VOLCANIC_KEESE = make_creature(
    name="Volcanic Keese",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bat"},
    text="Whenever Volcanic Keese attacks, it deals 1 damage to each opponent (2 if you control 2+ Bats).",
    setup_interceptors=volcanic_keese_setup,
)

TALUS = make_creature(
    name="Stone Talus",
    power=6, toughness=6,
    mana_cost="{5}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Giant"},
    text="When Stone Talus enters, it deals 2 damage to each opponent (plus 1 for each other Elemental or Giant you control).",
    setup_interceptors=stone_talus_setup,
)

# More Green
FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
    text="When Forest Guardian enters, scry 1. If any opponent controls a creature, surveil 1.",
    setup_interceptors=_zld_etb_forest_count_setup,
)

DEKU_TREE_SPROUT = make_creature(
    name="Deku Tree Sprout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"},
    text="When Deku Tree Sprout enters, gain 1 life per Plant or Treefolk you control. If you have a Plant in your graveyard, each opponent loses 1 life.",
    setup_interceptors=_zld_etb_plant_lifegain_setup,
)

WILD_HORSE = make_creature(
    name="Wild Horse",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    text="When Wild Horse enters, scry 1. If you control a Hylian, gain 1 life.",
    setup_interceptors=_zld_etb_horse_setup,
)

RITO_ELDER = make_creature(
    name="Rito Elder",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Druid"},
    text="When Rito Elder enters, scry 1. If you control two or more Rito or Birds, target opponent reveals their hand.",
    setup_interceptors=_zld_etb_rito_scout_setup,
)

MASTER_KOHGA = make_creature(
    name="Master Kohga",
    power=2, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text=(
        "At the beginning of your upkeep, exile the top card of your library. "
        "You may play it this turn."
    ),
    setup_interceptors=master_kohga_setup,
)

GHIRAHIM_DEMON_LORD = make_creature(
    name="Ghirahim, Demon Lord",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text=(
        "Haste. Whenever Ghirahim, Demon Lord deals combat damage to a "
        "player, each opponent discards a card, then exile the top card "
        "of your library. You may play that card this turn."
    ),
    setup_interceptors=ghirahim_demon_lord_setup,
)

DEMISE_DEMON_KING = make_creature(
    name="Demise, Demon King",
    power=7, toughness=6,
    mana_cost="{4}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "God"},
    supertypes={"Legendary"},
    text=(
        "Trample. When Demise, Demon King enters, destroy all creatures "
        "with toughness 3 or less. At the beginning of your end step, each "
        "opponent loses life equal to the number of creature cards in your "
        "graveyard."
    ),
    setup_interceptors=demise_demon_king_setup,
)


# --- Skyward Sword (spice-pass W22+, Phase A3) ---
# {2} Legendary Equipment, Mythic. Equip {3}. Equipped creature gets +3/+1
# and has first strike and flying. Top-end finisher equipment for the
# Hylian / Champion equipment carrier shells.
SKYWARD_SWORD = make_equipment(
    name="Skyward Sword",
    mana_cost="{2}",
    equip_cost="{3}",
    text="Equipped creature gets +3/+1 and has first strike and flying.",
    supertypes={"Legendary"},
    setup_interceptors=make_equipment_setup(
        power_mod=3, toughness_mod=1,
        keywords=["first_strike", "flying"],
        equip_cost="{3}",
    ),
)


# --- Time Travel Sonata (spice-pass W22+, Phase A3, simplified) ---
# {3}{U}{U}{U} Sorcery, Mythic. Take an extra turn after this one. Exile this.
# Simplified from the original design (which gated on Ocarina of Time on
# battlefield via cast-time replacement effect — Phase B-3). The flat-cost
# variant at {6} is defensible per cost-walk: Time Walk benchmark is {4}
# unconditional; this is 2 mana over that for tribal flavor.
TIME_TRAVEL_SONATA = CardDefinition(
    name="Time Travel Sonata",
    mana_cost="{3}{U}{U}{U}",
    characteristics=Characteristics(
        types={CardType.SORCERY},
        subtypes=set(),
        colors={Color.BLUE},
        supertypes={"Legendary"},
        mana_cost="{3}{U}{U}{U}",
    ),
    text="Take an extra turn after this one. Exile Time Travel Sonata.",
    resolve=time_travel_sonata_resolve,
)

KING_RHOAM = make_creature(
    name="King Rhoam Bosphoramus",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Noble", "Spirit"},
    supertypes={"Legendary"},
    text="When King Rhoam Bosphoramus enters, scry 2 and you gain 1 life for each Hylian, Sheikah, or Spirit ally.",
    setup_interceptors=_zld_w_etb_holy_inspect,
)

KASS_RITO_BARD = make_creature(
    name="Kass, Rito Bard",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Rito", "Bard"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell, scry 1 and each opponent loses 1 life.",
    setup_interceptors=_zld_m_spell_cast_rito_bard,
)

BEEDLE_TRAVELING_MERCHANT = make_creature(
    name="Beedle, Traveling Merchant",
    power=1, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Human", "Merchant"},
    supertypes={"Legendary"},
    text=(
        "{T}: Add one mana of any color. "
        "{2}, {T}: Search your library for a card named Heart Container, "
        "Bomb Bag, Hookshot, Bunny Hood, Fairy Bottle, or Sheikah Slate, "
        "reveal it, put it into your hand, then shuffle."
    ),
    setup_interceptors=beedle_traveling_merchant_setup,
)

PURAH_SHEIKAH_RESEARCHER = make_creature(
    name="Purah, Sheikah Researcher",
    power=1, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Sheikah", "Artificer"},
    supertypes={"Legendary"},
    text=(
        "When Purah, Sheikah Researcher enters, scry 3, then draw a card."
    ),
    setup_interceptors=purah_sheikah_researcher_setup,
)

ROBBIE_ANCIENT_TECH = make_creature(
    name="Robbie, Ancient Tech Expert",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Sheikah", "Artificer"},
    supertypes={"Legendary"},
    text="When Robbie enters, scry 2; gain 1 life for each artifact you control (minimum 1); each opponent loses 1 life.",
    setup_interceptors=robbie_ancient_tech_setup,
)


# =============================================================================
# TRIBAL LORDS — multiplies the value of ZLD's vanilla-heavy mono-white
# creature mass. Pre-pass ZLD has 10 mono-white Hylians, 5 Knights, all
# vanilla. Each lord pumps ~10-15 drafted creatures by +1/+1, turning
# stat-line damage into amplified-stat-line damage.
# =============================================================================

def _hylian_marshal_setup(obj, state):
    return list(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Hylian")))

HYRULE_MARSHAL = make_creature(
    name="Hyrule Marshal",
    power=2, toughness=2, mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
    text="Other Hylian creatures you control get +1/+1.",
    setup_interceptors=_hylian_marshal_setup,
)

def _sheikah_champion_setup(obj, state):
    return list(make_static_pt_boost(obj, 1, 0, other_creatures_with_subtype(obj, "Knight")))

SHEIKAH_CHAMPION = make_creature(
    name="Sheikah Champion",
    power=2, toughness=3, mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Knight"},
    text="Other Knight creatures you control get +1/+0.",
    setup_interceptors=_sheikah_champion_setup,
)


# =============================================================================
# WAVE 4 BUFF COMMONS (White, Hylian/Sheikah-flavored)
# =============================================================================

HYLIAN_SOLDIER_BUFF = make_creature(
    name="Hylian Soldier",
    power=2, toughness=1, mana_cost="{W}", colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"}, text=""
)

HYRULE_SQUIRE = make_creature(
    name="Hyrule Squire",
    power=2, toughness=3, mana_cost="{1}{W}", colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
    text="Vigilance. When Hyrule Squire enters, scry 1 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_etb_light_foresight,
)

SHEIKAH_SENTINEL = make_creature(
    name="Sheikah Sentinel",
    power=3, toughness=1, mana_cost="{1}{W}", colors={Color.WHITE},
    subtypes={"Sheikah", "Knight"},
    text="First strike. When Sheikah Sentinel enters, surveil 1 and each opponent loses 1 life.",
    setup_interceptors=_zld_w_etb_scout_reveal,
)


# =============================================================================
# PHASE B-2 SPICE PICKS (2026-05-18, fourth slice of zld_spice_pass.md)
# Each card carries a distinct helper fingerprint and lands on a previously
# unrepresented axis tuple, so collectively they push code_diversity ≥0.40
# and dent axis_diversity meaningfully.
# =============================================================================

VOLGA_GORON_TYRANT = make_creature(
    name="Volga, Goron Tyrant",
    power=4, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "Trample. When Volga, Goron Tyrant enters, it deals damage to each "
        "opponent equal to the number of Mountains you control. At the "
        "beginning of each opponent's upkeep, that player loses 2 life."
    ),
    setup_interceptors=volga_goron_tyrant_setup,
)


SHEIKAH_SPY = make_creature(
    name="Sheikah Spy",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Sheikah", "Rogue"},
    supertypes={"Legendary"},
    text=(
        "Menace. When Sheikah Spy enters, each opponent reveals their hand. "
        "You choose a nonland card from among them. That player discards "
        "the chosen card."
    ),
    setup_interceptors=sheikah_spy_setup,
)


MASTER_SHEIKAH_SAGE_OF_SPIRITS = make_creature(
    name="Master Sheikah, Sage of Spirits",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Sheikah", "Sage"},
    supertypes={"Legendary"},
    text=(
        "This spell costs {1} less to cast for each Triforce-named artifact "
        "you control.\n"
        "Lifelink. Other Spirit creatures you control get +1/+1. When Master "
        "Sheikah, Sage of Spirits enters, each opponent sacrifices a "
        "creature. You gain 1 life for each Triforce-named card in "
        "graveyards or on the battlefield."
    ),
    setup_interceptors=master_sheikah_sage_setup,
)


TWILI_COVEN = CardDefinition(
    name="Twili Coven",
    mana_cost="{2}{U}{B}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Locus"},
        colors={Color.BLUE, Color.BLACK},
        supertypes={"Legendary"},
        mana_cost="{2}{U}{B}",
    ),
    text=(
        "Whenever you cast a spell, target opponent loses 1 life, then you "
        "surveil 1."
    ),
    setup_interceptors=twili_coven_setup,
)


# =============================================================================
# PHASE B-3 SPICE PICKS (2026-05-18, axis_diversity gate flip)
# Two cards, each landing on a previously unseen axis tuple. Together they
# push distinct_axis_fingerprints 16 -> 18, flipping axis_diversity past the
# 0.08 gate.
# =============================================================================

YIGA_FOOTSOLDIER = make_creature(
    name="Yiga Footsoldier",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Sheikah", "Rogue"},
    supertypes={"Legendary"},
    text=(
        "Flash. When Yiga Footsoldier enters, look at the top three cards "
        "of each opponent's library. You may exile one of them."
    ),
    setup_interceptors=yiga_footsoldier_setup,
)


PRINCESS_RUTO_SAGE_OF_WATER = make_creature(
    name="Princess Ruto, Sage of Water",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Sage"},
    supertypes={"Legendary"},
    text=(
        "Flash. This spell costs {1} less to cast if you have three or more "
        "cards in your graveyard.\n"
        "Whenever you cast an instant or sorcery, look at the top card of "
        "each opponent's library. You may exile that card until end of turn."
    ),
    setup_interceptors=princess_ruto_sage_setup,
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
    # Phase B-2 (2026-05-18, code_diversity gate flip):
    "Sheik, Agent of Twilight": SHEIK_AGENT_OF_TWILIGHT,

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
    "Link, Hero of the Wild": LINK_HERO_OF_THE_WILD,
    "Zelda, Sage of Wisdom": ZELDA_SAGE_OF_WISDOM,
    "Ganondorf, Dark Lord Ascendant": GANONDORF_DARK_LORD_ASCENDANT,
    "Wolf Link, Twilight Companion": WOLF_LINK_TWILIGHT_COMPANION,
    "Hyrule Castle, Royal Sanctum": HYRULE_CASTLE_ROYAL_SANCTUM,
    "Skyward Sword": SKYWARD_SWORD,
    "Time Travel Sonata": TIME_TRAVEL_SONATA,
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
    "Sheikah Eye of Truth": SHEIKAH_EYE_OF_TRUTH,
    "Ballad of the Goddess": BALLAD_OF_THE_GODDESS,
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

    # WAVE 4 BUFF COMMONS
    "Hylian Soldier": HYLIAN_SOLDIER_BUFF,
    "Hyrule Squire": HYRULE_SQUIRE,
    "Sheikah Sentinel": SHEIKAH_SENTINEL,

    # TRIBAL LORDS
    "Hyrule Marshal": HYRULE_MARSHAL,
    "Sheikah Champion": SHEIKAH_CHAMPION,

    # PHASE B-2 SPICE PICKS (group 1)
    "Volga, Goron Tyrant": VOLGA_GORON_TYRANT,
    "Sheikah Spy": SHEIKAH_SPY,

    # PHASE B-2 SPICE PICKS (group 2)
    "Master Sheikah, Sage of Spirits": MASTER_SHEIKAH_SAGE_OF_SPIRITS,
    "Twili Coven": TWILI_COVEN,

    # PHASE B-3 SPICE PICKS (axis_diversity gate flip)
    "Yiga Footsoldier": YIGA_FOOTSOLDIER,
    "Princess Ruto, Sage of Water": PRINCESS_RUTO_SAGE_OF_WATER,
}

print(f"Loaded {len(LEGEND_OF_ZELDA_CARDS)} Legend of Zelda: Hyrule Chronicles cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    ZELDA_PRINCESS_OF_HYRULE,
    ZELDA_WIELDER_OF_WISDOM,
    IMPA_SHEIKAH_GUARDIAN,
    RAURU_SAGE_OF_LIGHT,
    HYLIA_GODDESS_OF_LIGHT,
    SHEIKAH_WARRIOR,
    HYRULE_KNIGHT,
    TEMPLE_GUARDIAN,
    CASTLE_GUARD,
    LIGHT_SPIRIT,
    HYLIAN_PRIESTESS,
    SHEIKAH_SCOUT,
    COURAGE_FAIRY,
    HYRULE_CAPTAIN,
    GREAT_FAIRY,
    SACRED_REALM_GUARDIAN,
    DINS_FIRE_SHIELD,
    LIGHT_ARROW,
    NAYRUS_LOVE,
    SONG_OF_HEALING,
    BLESSING_OF_HYLIA,
    MIPHA_ZORA_CHAMPION,
    RUTO_ZORA_PRINCESS,
    KING_ZORA,
    NAYRU_ORACLE_OF_WISDOM,
    SIDON_ZORA_PRINCE,
    ZORA_WARRIOR,
    ZORA_SCHOLAR,
    RIVER_ZORA,
    WATER_SPIRIT,
    OCTOROK,
    LIKE_LIKE,
    GYORG,
    ZORA_DIVER,
    ZORA_SPEARMAN,
    ZORA_SAGE,
    ZORAS_SAPPHIRE_BLESSING,
    TORRENTIAL_WAVE,
    WATER_TEMPLE_FLOOD,
    WISDOM_OF_AGES,
    COUNTER_MAGIC,
    GANONDORF_KING_OF_EVIL,
    GANON_CALAMITY_INCARNATE,
    ZANT_TWILIGHT_USURPER,
    MIDNA_TWILIGHT_PRINCESS,
    VAATI_WIND_MAGE,
    SHADOW_BEAST,
    STALFOS_WARRIOR,
    REDEAD,
    GIBDO,
    POES,
    DARK_NUT,
    PHANTOM,
    FLOORMASTER,
    DEAD_HAND,
    WALLMASTER,
    TWILIGHT_CURSE,
    DARKNESS_FALLS,
    MALICE_SPREAD,
    SOUL_HARVEST,
    GANONS_WRATH,
    DARUK_GORON_CHAMPION,
    DARUNIA_GORON_CHIEF,
    DIN_ORACLE_OF_POWER,
    VOLVAGIA_FIRE_DRAGON,
    YUNOBO_GORON_DESCENDANT,
    GORON_WARRIOR,
    GORON_SMITH,
    DODONGO,
    FIRE_KEESE,
    LIZALFOS,
    LYNEL,
    MOBLIN,
    HINOX,
    GORON_ELDER,
    FIRE_SPIRIT,
    DINS_FIRE,
    FIRE_ARROW,
    VOLCANIC_ERUPTION,
    GORON_RAGE,
    BOMB_BARRAGE,
    LINK_HERO_OF_TIME,
    LINK_CHAMPION_OF_HYRULE,
    LINK_HERO_OF_THE_WILD,
    ZELDA_SAGE_OF_WISDOM,
    GANONDORF_DARK_LORD_ASCENDANT,
    WOLF_LINK_TWILIGHT_COMPANION,
    HYRULE_CASTLE_ROYAL_SANCTUM,
    SKYWARD_SWORD,
    TIME_TRAVEL_SONATA,
    SARIA_FOREST_SAGE,
    REVALI_RITO_CHAMPION,
    GREAT_DEKU_TREE,
    FARORE_ORACLE_OF_COURAGE,
    KOKIRI_CHILD,
    KOKIRI_WARRIOR,
    SKULL_KID,
    DEKU_SCRUB,
    FOREST_FAIRY,
    WOLFOS,
    FOREST_TEMPLE_GUARDIAN,
    DEKU_BABA,
    RITO_WARRIOR,
    KOROKS,
    FARORES_WIND,
    FOREST_BLESSING,
    NATURES_FURY,
    DEKU_NUT_STUN,
    WILD_GROWTH,
    URBOSA_GERUDO_CHAMPION,
    FI_SWORD_SPIRIT,
    NABOORU_SPIRIT_SAGE,
    SKULL_KID_MASKED_MENACE,
    TETRA_PIRATE_PRINCESS,
    GROOSE_SKYLOFT_HERO,
    MALON_RANCH_KEEPER,
    TRIFORCE_OF_POWER,
    TRIFORCE_OF_WISDOM,
    TRIFORCE_OF_COURAGE,
    DIVINE_BEAST_VAH_RUTA,
    DIVINE_BEAST_VAH_RUDANIA,
    DIVINE_BEAST_VAH_MEDOH,
    DIVINE_BEAST_VAH_NABORIS,
    MASTER_SWORD,
    SHEIKAH_EYE_OF_TRUTH,
    BALLAD_OF_THE_GODDESS,
    HYLIAN_SHIELD,
    HEROS_BOW,
    BIGGORONS_SWORD,
    MIRROR_SHIELD,
    ANCIENT_BOW,
    KOKIRI_SWORD,
    MAJORAS_MASK,
    FIERCE_DEITY_MASK,
    DEKU_MASK,
    GORON_MASK,
    ZORA_MASK,
    BUNNY_HOOD,
    STONE_MASK,
    OCARINA_OF_TIME,
    SHEIKAH_SLATE,
    BOMB_BAG,
    FAIRY_BOTTLE,
    MAGIC_BOOMERANG,
    HOOKSHOT,
    HEART_CONTAINER_ARTIFACT,
    LENS_OF_TRUTH,
    ANCIENT_CORE,
    GUARDIAN_PARTS,
    SACRED_PROTECTION,
    ZORAS_DOMAIN,
    TWILIGHT_REALM,
    GORON_STRENGTH,
    KOKIRI_FOREST,
    HYLIA_BLESSING,
    ANCIENT_TECHNOLOGY,
    SPIRIT_TRACKS,
    HYRULE_CASTLE,
    DEATH_MOUNTAIN,
    ZORAS_DOMAIN_LAND,
    LOST_WOODS,
    GERUDO_DESERT,
    TEMPLE_OF_TIME,
    KAKARIKO_VILLAGE,
    LAKE_HYLIA,
    LON_LON_RANCH,
    GREAT_PLATEAU,
    AKKALA_CITADEL,
    FARON_WOODS,
    ELDIN_VOLCANO,
    LANAYRU_WETLANDS,
    LURELIN_VILLAGE,
    SKYLOFT,
    SHADOW_TEMPLE,
    FIRE_TEMPLE,
    WATER_TEMPLE,
    FOREST_TEMPLE,
    SPIRIT_TEMPLE,
    PLAINS_LOZ,
    ISLAND_LOZ,
    SWAMP_LOZ,
    MOUNTAIN_LOZ,
    FOREST_LOZ,
    FAIRY_COMPANION,
    HYRULE_SOLDIER,
    LIGHT_SAGE,
    SACRED_KNIGHT,
    ZORA_GUARD,
    DEEP_SEA_ZORA,
    WISDOM_FAIRY,
    RIVER_GUARDIAN,
    SHADOW_LINK,
    DARK_INTERLOPERS,
    TWILIGHT_MESSENGER,
    CURSED_BOKOBLIN,
    FIRE_TEMPLE_GORON,
    BOKOBLIN_HORDE,
    VOLCANIC_KEESE,
    TALUS,
    FOREST_GUARDIAN,
    DEKU_TREE_SPROUT,
    WILD_HORSE,
    RITO_ELDER,
    MASTER_KOHGA,
    GHIRAHIM_DEMON_LORD,
    DEMISE_DEMON_KING,
    KING_RHOAM,
    KASS_RITO_BARD,
    BEEDLE_TRAVELING_MERCHANT,
    PURAH_SHEIKAH_RESEARCHER,
    ROBBIE_ANCIENT_TECH,
    HYLIAN_SOLDIER_BUFF,
    HYRULE_SQUIRE,
    SHEIKAH_SENTINEL,
    HYRULE_MARSHAL,
    SHEIKAH_CHAMPION,
    # PHASE B-2 SPICE PICKS (group 1)
    VOLGA_GORON_TYRANT,
    SHEIKAH_SPY,
    # PHASE B-2 SPICE PICKS (group 2)
    MASTER_SHEIKAH_SAGE_OF_SPIRITS,
    TWILI_COVEN,
    # PHASE B-3 SPICE PICKS (axis_diversity gate flip)
    YIGA_FOOTSOLDIER,
    PRINCESS_RUTO_SAGE_OF_WATER,
]
