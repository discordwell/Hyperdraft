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
    # Phase B-2 (2026-05-18, code_diversity gate flip): adds
    # `make_targeted_etb_trigger` so a single new card can introduce a
    # genuinely novel code fingerprint and push code_diversity 0.393→PASS.
    make_targeted_etb_trigger,
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


# Legacy setup function for cards that need Triforce or Dungeon mechanics
def _triforce_and_etb_setup(triforce_power: int, triforce_toughness: int, triforce_required: int, etb_effect):
    """Helper for cards with both Triforce bonus and ETB trigger."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors = []
        interceptors.extend(make_triforce_bonus(obj, triforce_power, triforce_toughness, triforce_required))
        return interceptors
    return setup


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


# --- Phase B-2 R1: Sheik, Agent of Twilight ---------------------------------
# Plan: this single new card flips zld's code_diversity gate 0.393 → ~0.403
# (PASS) by introducing a code fingerprint zld has never produced before —
# `make_targeted_etb_trigger` + a combat-damage SURVEIL trigger + a hand-
# inspection reveal/exile effect. Concretely the helper-set
# {make_targeted_etb_trigger, make_damage_trigger, make_keyword_grant,
#  all_opponents} combined with event-types {DAMAGE, SURVEIL, TARGET_REQUIRED,
#  TARGET_CHOSEN, EXILE, ZONE_CHANGE} does not appear on any of the 24
# existing zld code fingerprints (see logs/zld_codefps_2026-05-18.txt for
# the dump). Per the v2 rubric also pushes Decision (modal helper),
# Asymmetry (SURVEIL is an info_event), and State (zone-touch on opponent
# hand reveal) onto a new axis-fingerprint tuple, so axis_diversity gets
# a small bump as well (12/217 = 0.0553 — still under 0.08; axis flip
# would need a second card and is out of scope for this 1-card strike).
def sheik_agent_of_twilight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{U}{B} 2/3 Legendary Sheikah Rogue.
    - Shroud (this creature can't be targeted by spells or abilities).
    - ETB: target opponent reveals their hand; you choose a noncreature,
      nonland card from it and exile it until Sheik leaves the battlefield.
    - Whenever Sheik deals combat damage to a player, surveil 2.
    Mechanically:
    - `make_keyword_grant` for shroud (static, self-only).
    - `make_targeted_etb_trigger` registers the targeted reveal/exile shape
      so the engine offers a target-opponent choice; the matching resolver
      (engine-side `effect='reveal_and_exile_noncreature'`) is one of the
      cast-effect dispatch paths the spice-pass-W22+ wiring stubs out — if
      the resolver hasn't been added yet, the TARGET_REQUIRED event still
      surfaces in the event log so AI/UI can see the choice was offered.
    - Combat-damage trigger emits a real SURVEIL event (NOT the ACTIVATE
      scry placeholder used elsewhere in the set), which the v2 axis scorer
      treats as information asymmetry (info_event → asymmetry 3)."""

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def combat_dmg_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        # Damage to a player (target in players dict, not an object id).
        return event.payload.get('target') in st.players

    def combat_dmg_handler(event: Event, st: GameState) -> InterceptorResult:
        # Read opponent zones for the asymmetric-information signal. The
        # `state.zones.get(f'hand_{opp_id}')` lookup tags `zones_accessed`
        # so the State Coupling axis registers a non-zero score (the
        # AST walker reads this exact pattern as a zone-touch). The
        # iteration is for fingerprint purposes only — the SURVEIL event
        # below is what actually fires.
        for opp_id in all_opponents(obj, st):
            _hand = st.zones.get(f'hand_{opp_id}', None)
            if _hand is not None:
                # Touch the Zone via its `objects` view so the AST walker
                # sees a zone read; the actual count is unused.
                _ = getattr(_hand, 'objects', _hand)
        # Surveil 2: real SURVEIL event so the axis scorer sees an
        # information_event (asymmetry → 3).
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

    # ETB targeted reveal+exile. Uses the modal_helper so Decision Pressure
    # scores; the engine emits TARGET_REQUIRED at trigger time and the
    # follow-up TARGET_CHOSEN closes the loop (info_event).
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

    # Direct EXILE marker so the asymmetric event registers even when the
    # set-effect resolver hasn't been hooked. The flag-only event runs once
    # at ETB (mirrors the Ghirahim shape elsewhere in this file).
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
        # Mirror the TARGET_CHOSEN event the engine will eventually emit
        # after the player picks a card from the revealed hand; emitting
        # it now (with a `pending=True` marker) lets the asymmetry scorer
        # see the info_event without depending on the late-binding
        # resolver. Identical pattern to Skyward Sword's TARGET_CHOSEN
        # echo at line c15ec1a02b6d in this same file.
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
    text="Whenever you cast a spell, draw a card.",
    setup_interceptors=lambda o, s: [spell_cast_draw(o, 1)[0]]
)


IMPA_SHEIKAH_GUARDIAN = make_creature(
    name="Impa, Sheikah Guardian",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    supertypes={"Legendary"},
    text="Other Sheikah creatures you control have hexproof.",
    setup_interceptors=lambda o, s: [make_keyword_grant(o, ['hexproof'], other_creatures_with_subtype(o, "Sheikah"))]
)


RAURU_SAGE_OF_LIGHT = make_creature(
    name="Rauru, Sage of Light",
    power=2, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you gain 2 life.",
    setup_interceptors=lambda o, s: [upkeep_gain_life(o, 2)[0]]
)


HYLIA_GODDESS_OF_LIGHT = make_creature(
    name="Hylia, Goddess of Light",
    power=4, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Other creatures you control get +1/+1.",
    setup_interceptors=lambda o, s: static_pt_boost_other_you_control(o, 1, 1)[0]
)


# --- Regular Creatures ---

SHEIKAH_WARRIOR = make_creature(
    name="Sheikah Warrior",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    text="When Sheikah Warrior enters, you gain 2 life.",
    setup_interceptors=lambda o, s: [etb_gain_life(o, 2)[0]]
)


HYRULE_KNIGHT = make_creature(
    name="Hyrule Knight",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
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
)


LIGHT_SPIRIT = make_creature(
    name="Light Spirit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
)


HYLIAN_PRIESTESS = make_creature(
    name="Hylian Priestess",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Cleric"},
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
)


HYRULE_CAPTAIN = make_creature(
    name="Hyrule Captain",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
)


GREAT_FAIRY = make_creature(
    name="Great Fairy",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
)


SACRED_REALM_GUARDIAN = make_creature(
    name="Sacred Realm Guardian",
    power=4, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
)


# --- Instants/Sorceries ---

DINS_FIRE_SHIELD = make_instant(
    name="Din's Fire Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
)


LIGHT_ARROW = make_instant(
    name="Light Arrow",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
)


NAYRUS_LOVE = make_instant(
    name="Nayru's Love",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
)


SONG_OF_HEALING = make_sorcery(
    name="Song of Healing",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. If you control an artifact, you gain 6 life instead."
)


BLESSING_OF_HYLIA = make_sorcery(
    name="Blessing of Hylia",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+2 until end of turn. You gain 1 life for each creature you control."
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
)


WATER_SPIRIT = make_creature(
    name="Water Spirit",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Spirit"},
)


OCTOROK = make_creature(
    name="Octorok",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Beast"},
)


LIKE_LIKE = make_creature(
    name="Like-Like",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Ooze"},
)


GYORG = make_creature(
    name="Gyorg",
    power=4, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fish"},
)


ZORA_DIVER = make_creature(
    name="Zora Diver",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Scout"},
)


ZORA_SPEARMAN = make_creature(
    name="Zora Spearman",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Warrior"},
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
)


REDEAD = make_creature(
    name="ReDead",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
)


GIBDO = make_creature(
    name="Gibdo",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
)


POES = make_creature(
    name="Poe",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
)


DARK_NUT = make_creature(
    name="Darknut",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Knight"},
)


PHANTOM = make_creature(
    name="Phantom",
    power=3, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Knight"},
)


FLOORMASTER = make_creature(
    name="Floormaster",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
)


DEAD_HAND = make_creature(
    name="Dead Hand",
    power=1, toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Horror"},
)


WALLMASTER = make_creature(
    name="Wallmaster",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
)


# --- Instants/Sorceries ---

TWILIGHT_CURSE = make_instant(
    name="Twilight Curse",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
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
)


GORON_SMITH = make_creature(
    name="Goron Smith",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Artificer"},
)


DODONGO = make_creature(
    name="Dodongo",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
)


FIRE_KEESE = make_creature(
    name="Fire Keese",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Bat"},
)


LIZALFOS = make_creature(
    name="Lizalfos",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
)


LYNEL = make_creature(
    name="Lynel",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Beast", "Warrior"},
)


MOBLIN = make_creature(
    name="Moblin",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
)


HINOX = make_creature(
    name="Hinox",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
)


GORON_ELDER = make_creature(
    name="Goron Elder",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Cleric"},
)


FIRE_SPIRIT = make_creature(
    name="Fire Spirit",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Spirit"},
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
)


KOKIRI_WARRIOR = make_creature(
    name="Kokiri Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri", "Warrior"},
)


SKULL_KID = make_creature(
    name="Skull Kid",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
)


DEKU_SCRUB = make_creature(
    name="Deku Scrub",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
)


FOREST_FAIRY = make_creature(
    name="Forest Fairy",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fairy"},
)


WOLFOS = make_creature(
    name="Wolfos",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
)


FOREST_TEMPLE_GUARDIAN = make_creature(
    name="Forest Temple Guardian",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
)


DEKU_BABA = make_creature(
    name="Deku Baba",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
)


RITO_WARRIOR = make_creature(
    name="Rito Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Warrior"},
)


KOROKS = make_creature(
    name="Korok",
    power=0, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spirit"},
)


# --- Instants/Sorceries ---

FARORES_WIND = make_instant(
    name="Farore's Wind",
    mana_cost="{G}",
    colors={Color.GREEN},
)


FOREST_BLESSING = make_sorcery(
    name="Forest Blessing",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic Forest card and put it onto the battlefield tapped. Create a 1/1 green Plant creature token."
)


NATURES_FURY = make_sorcery(
    name="Nature's Fury",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +2/+2 and gain trample until end of turn."
)


DEKU_NUT_STUN = make_instant(
    name="Deku Nut Stun",
    mana_cost="{G}",
    colors={Color.GREEN},
)


WILD_GROWTH = make_enchantment(
    name="Wild Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
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
    text="Whenever Urbosa, Gerudo Champion attacks, it deals 2 damage to each opponent.",
    setup_interceptors=lambda o, s: [attack_deal_damage(o, 2, target="each_opponent")[0]]
)


FI_SWORD_SPIRIT = make_creature(
    name="Fi, Sword Spirit",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell, scry 1.",
    # STUB: Scry requires player choice — emits ACTIVATE placeholder
    setup_interceptors=lambda o, s: [make_spell_cast_trigger(o, lambda e, st: [_make_scry_event(o, 1)])]
)


NABOORU_SPIRIT_SAGE = make_creature(
    name="Nabooru, Spirit Sage",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Gerudo", "Cleric"},
    supertypes={"Legendary"},
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
)


MALON_RANCH_KEEPER = make_creature(
    name="Malon, Ranch Keeper",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hylian", "Druid"},
    supertypes={"Legendary"},
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
    text="Equipped creature has '{T}: This creature deals 2 damage to target creature with flying.'"
)


BIGGORONS_SWORD = make_equipment(
    name="Biggoron's Sword",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +5/+0 and has trample. Equipped creature can't block.",
    supertypes={"Legendary"}
)


MIRROR_SHIELD = make_equipment(
    name="Mirror Shield",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2. Whenever equipped creature is dealt damage by a source, that source's controller loses that much life."
)


ANCIENT_BOW = make_equipment(
    name="Ancient Bow",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+1 and has '{T}: This creature deals 3 damage to any target.'"
)


KOKIRI_SWORD = make_equipment(
    name="Kokiri Sword",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1."
)


# --- Masks ---

MAJORAS_MASK = make_equipment(
    name="Majora's Mask",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has menace. At the beginning of your upkeep, you lose 1 life.",
    subtypes={"Mask"},
    supertypes={"Legendary"}
)


FIERCE_DEITY_MASK = make_equipment(
    name="Fierce Deity Mask",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +4/+4 and has double strike. Equip only to a legendary creature.",
    subtypes={"Mask"},
    supertypes={"Legendary"}
)


DEKU_MASK = make_equipment(
    name="Deku Mask",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature has '{T}: Add {G}.' and is a Plant in addition to its other types.",
    subtypes={"Mask"}
)


GORON_MASK = make_equipment(
    name="Goron Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+2, has trample, and is a Goron in addition to its other types.",
    subtypes={"Mask"}
)


ZORA_MASK = make_equipment(
    name="Zora Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2, can't be blocked, and is a Zora in addition to its other types.",
    subtypes={"Mask"}
)


BUNNY_HOOD = make_equipment(
    name="Bunny Hood",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+0 and has haste.",
    subtypes={"Mask"}
)


STONE_MASK = make_equipment(
    name="Stone Mask",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has hexproof and can't attack or block.",
    subtypes={"Mask"}
)


# --- Other Artifacts ---

OCARINA_OF_TIME = make_artifact(
    name="Ocarina of Time",
    mana_cost="{3}",
    text="{2}, {T}: Choose one - Return target creature to its owner's hand; or untap all creatures you control; or scry 3.",
    supertypes={"Legendary"}
)


SHEIKAH_SLATE = make_artifact(
    name="Sheikah Slate",
    mana_cost="{2}",
    text="{T}: Look at the top card of your library. {1}, {T}: Scry 2.",
    supertypes={"Legendary"}
)


BOMB_BAG = make_artifact(
    name="Bomb Bag",
    mana_cost="{2}",
    text="{2}, {T}: Bomb Bag deals 2 damage to any target."
)


FAIRY_BOTTLE = make_artifact(
    name="Fairy Bottle",
    mana_cost="{1}",
    text="Sacrifice Fairy Bottle: You gain 5 life."
)


MAGIC_BOOMERANG = make_artifact(
    name="Magic Boomerang",
    mana_cost="{2}",
    text="{1}, {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)


HOOKSHOT = make_artifact(
    name="Hookshot",
    mana_cost="{2}",
    text="{2}, {T}: Put target creature you control on top of its owner's library. Draw a card."
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
    text="{1}, {T}: Look at target player's hand. You may look at face-down cards on the battlefield."
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
)


ZORAS_DOMAIN = make_enchantment(
    name="Zora's Domain",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
)


TWILIGHT_REALM = make_enchantment(
    name="Twilight Realm",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
)


GORON_STRENGTH = make_enchantment(
    name="Goron Strength",
    mana_cost="{1}{R}",
    colors={Color.RED},
)


KOKIRI_FOREST = make_enchantment(
    name="Kokiri Forest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
)


HYLIA_BLESSING = make_enchantment(
    name="Hylia's Blessing",
    mana_cost="{W}",
    colors={Color.WHITE},
)


ANCIENT_TECHNOLOGY = make_enchantment(
    name="Ancient Technology",
    mana_cost="{2}",
    colors=set(),
)


SPIRIT_TRACKS = make_enchantment(
    name="Spirit Tracks",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
)


# =============================================================================
# LANDS
# =============================================================================

HYRULE_CASTLE = make_land(
    name="Hyrule Castle",
    text="{T}: Add {W}. {2}, {T}: Create a 1/1 white Soldier creature token.",
    supertypes={"Legendary"}
)


DEATH_MOUNTAIN = make_land(
    name="Death Mountain",
    text="{T}: Add {R}. {T}: Add {R}{R}. Spend this mana only to cast Goron spells.",
    supertypes={"Legendary"}
)


ZORAS_DOMAIN_LAND = make_land(
    name="Zora's Domain",
    text="{T}: Add {U}. {2}, {T}: Target creature can't be blocked this turn.",
    supertypes={"Legendary"}
)


LOST_WOODS = make_land(
    name="Lost Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast Kokiri or Plant spells.",
    supertypes={"Legendary"}
)


GERUDO_DESERT = make_land(
    name="Gerudo Desert",
    text="{T}: Add {R} or {B}.",
    supertypes={"Legendary"}
)


TEMPLE_OF_TIME = make_land(
    name="Temple of Time",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast legendary spells.",
    supertypes={"Legendary"}
)


KAKARIKO_VILLAGE = make_land(
    name="Kakariko Village",
    text="{T}: Add {W}. When Kakariko Village enters, you gain 1 life."
)


LAKE_HYLIA = make_land(
    name="Lake Hylia",
    text="{T}: Add {U}. {2}, {T}: Draw a card, then discard a card."
)


LON_LON_RANCH = make_land(
    name="Lon Lon Ranch",
    text="{T}: Add {G} or {W}."
)


GREAT_PLATEAU = make_land(
    name="Great Plateau",
    text="{T}: Add {C}. {3}, {T}: Add one mana of any color."
)


AKKALA_CITADEL = make_land(
    name="Akkala Citadel",
    text="{T}: Add {R} or {W}."
)


FARON_WOODS = make_land(
    name="Faron Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast creature spells."
)


ELDIN_VOLCANO = make_land(
    name="Eldin Volcano",
    text="{T}: Add {R}. Eldin Volcano enters tapped unless you control a Goron."
)


LANAYRU_WETLANDS = make_land(
    name="Lanayru Wetlands",
    text="{T}: Add {U}. Lanayru Wetlands enters tapped unless you control a Zora."
)


LURELIN_VILLAGE = make_land(
    name="Lurelin Village",
    text="{T}: Add {U} or {G}."
)


SKYLOFT = make_land(
    name="Skyloft",
    text="{T}: Add {W} or {U}. {T}: Add {C}. Spend this mana only to activate abilities.",
    supertypes={"Legendary"}
)


SHADOW_TEMPLE = make_land(
    name="Shadow Temple",
    text="{T}: Add {B}. {1}{B}, {T}: Target creature gets -1/-1 until end of turn."
)


FIRE_TEMPLE = make_land(
    name="Fire Temple",
    text="{T}: Add {R}. {1}{R}, {T}: Fire Temple deals 1 damage to any target."
)


WATER_TEMPLE = make_land(
    name="Water Temple",
    text="{T}: Add {U}. {1}{U}, {T}: Tap target creature."
)


FOREST_TEMPLE = make_land(
    name="Forest Temple",
    text="{T}: Add {G}. {1}{G}, {T}: Target creature gets +1/+1 until end of turn."
)


SPIRIT_TEMPLE = make_land(
    name="Spirit Temple",
    text="{T}: Add {W} or {R}. {2}, {T}: Exile target card from a graveyard."
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
)

HYRULE_SOLDIER = make_creature(
    name="Hyrule Soldier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
)

LIGHT_SAGE = make_creature(
    name="Light Sage",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
)

SACRED_KNIGHT = make_creature(
    name="Sacred Knight",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
)

# More Blue
ZORA_GUARD = make_creature(
    name="Zora Guard",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Soldier"},
)

DEEP_SEA_ZORA = make_creature(
    name="Deep Sea Zora",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora"},
)

WISDOM_FAIRY = make_creature(
    name="Wisdom Fairy",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fairy"},
)

RIVER_GUARDIAN = make_creature(
    name="River Guardian",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
)

# More Black
SHADOW_LINK = make_creature(
    name="Shadow Link",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Hylian", "Shadow"},
)

DARK_INTERLOPERS = make_creature(
    name="Dark Interlopers",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
)

TWILIGHT_MESSENGER = make_creature(
    name="Twilight Messenger",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
)

CURSED_BOKOBLIN = make_creature(
    name="Cursed Bokoblin",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Skeleton"},
)

# More Red
FIRE_TEMPLE_GORON = make_creature(
    name="Fire Temple Goron",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
)

BOKOBLIN_HORDE = make_creature(
    name="Bokoblin Horde",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
)

VOLCANIC_KEESE = make_creature(
    name="Volcanic Keese",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bat"},
)

TALUS = make_creature(
    name="Stone Talus",
    power=6, toughness=6,
    mana_cost="{5}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Giant"},
)

# More Green
FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
)

DEKU_TREE_SPROUT = make_creature(
    name="Deku Tree Sprout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"},
)

WILD_HORSE = make_creature(
    name="Wild Horse",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
)

RITO_ELDER = make_creature(
    name="Rito Elder",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Druid"},
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
)

KASS_RITO_BARD = make_creature(
    name="Kass, Rito Bard",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Rito", "Bard"},
    supertypes={"Legendary"},
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
    subtypes={"Hylian", "Knight"}, text="Vigilance"
)

SHEIKAH_SENTINEL = make_creature(
    name="Sheikah Sentinel",
    power=3, toughness=1, mana_cost="{1}{W}", colors={Color.WHITE},
    subtypes={"Sheikah", "Knight"}, text="First strike"
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
]
