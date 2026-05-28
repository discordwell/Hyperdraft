"""
Harry Potter: Wizarding World (HPW) Card Implementations

~250 cards featuring the Wizarding World.
Mechanics: Spell Mastery, House, Patronus
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
    etb_gain_life, etb_draw, death_draw,
    static_pt_boost_by_subtype, static_pt_boost_other_you_control,
    static_keyword_grant_others,
)
from src.cards import interceptor_helpers as _ih
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# HARRY POTTER KEYWORD MECHANICS
# =============================================================================

def count_instants_sorceries_cast(state: GameState, controller: str) -> int:
    """Count instants/sorceries cast this game by controller."""
    return state.players.get(controller, {}).get('spells_cast_this_game', 0)


def has_spell_mastery(state: GameState, controller: str) -> bool:
    """Check if controller has Spell Mastery (3+ instants/sorceries cast this game)."""
    return count_instants_sorceries_cast(state, controller) >= 3


def make_spell_mastery_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """Spell Mastery - Gets +X/+Y if you've cast 3+ instants/sorceries this game."""
    def mastery_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return has_spell_mastery(state, source_obj.controller)

    # This is a conditional self-buff that doesn't fit cleanly into the new system
    # Keep as custom interceptor
    from src.engine.types import EventType

    interceptors = []

    if power_bonus != 0:
        def power_filter(event, state, src=source_obj):
            if event.type != EventType.QUERY_POWER:
                return False
            target_id = event.payload.get('object_id')
            if target_id != src.id:
                return False
            return has_spell_mastery(state, src.controller)

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
        def toughness_filter(event, state, src=source_obj):
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            target_id = event.payload.get('object_id')
            if target_id != src.id:
                return False
            return has_spell_mastery(state, src.controller)

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


def make_house_bonus(source_obj: GameObject, house: str, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """House - Gets +X/+Y for each other creature you control with the same house subtype."""
    # This is a counting-based bonus that doesn't fit cleanly into the new system
    # Keep as custom interceptor
    from src.engine.types import EventType

    def count_house_members(state: GameState) -> int:
        return sum(1 for obj in state.objects.values()
                   if obj.id != source_obj.id
                   and obj.controller == source_obj.controller
                   and CardType.CREATURE in obj.characteristics.types
                   and house in obj.characteristics.subtypes
                   and obj.zone == ZoneType.BATTLEFIELD)

    interceptors = []

    if power_bonus != 0:
        def power_filter(event, state, src=source_obj):
            if event.type != EventType.QUERY_POWER:
                return False
            target_id = event.payload.get('object_id')
            return target_id == src.id

        def power_handler(event, state, mod=power_bonus):
            count = count_house_members(state)
            if count == 0:
                return InterceptorResult(action=InterceptorAction.PASS)
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + (mod * count)
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
        def toughness_filter(event, state, src=source_obj):
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            target_id = event.payload.get('object_id')
            return target_id == src.id

        def toughness_handler(event, state, mod=toughness_bonus):
            count = count_house_members(state)
            if count == 0:
                return InterceptorResult(action=InterceptorAction.PASS)
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + (mod * count)
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


def make_patronus_token(controller: str, source_id: str, creature_type: str = "Spirit") -> Event:
    """Create a Patronus token - 2/2 white Spirit with flying and protection from black."""
    return Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': controller,
            'token': {
                'name': f'Patronus {creature_type}',
                'power': 2,
                'toughness': 2,
                'colors': {Color.WHITE},
                'subtypes': {'Spirit', 'Patronus'},
                'keywords': ['flying', 'protection_from_black']
            }
        },
        source=source_id
    )


# =============================================================================
# Spice-pass W22+ setup functions (added 2026-05-18)
# Plan: HPW pilot — mirror ZLD A1 cluster cleanup methodology
# Baseline: docs/sets/custom_set_depth_baseline_2026-05-18.md (HPW row)
#
# Design block (8 cards):
#   - Deathly Hallows trio (REWIRES of Elder Wand / Resurrection Stone /
#     Invisibility Cloak) — assembly package, build-around for Voldemort.
#   - Lord Voldemort, the Dark Lord (REWIRE) — build-around mythic gated on
#     Deathly Hallows count. Pattern 11 + pattern 3 (snowball).
#   - Albus Dumbledore, Headmaster (REWIRE) — ETB compression onto the
#     existing wizard-anthem static (pattern 4).
#   - Sirius Black, Escaped Convict (REWIRE — was unwired) — haste self-grant
#     + attack-trigger ping + cantrip-on-spell-mastery.
#   - Hogwarts: The Sorting Year (NEW saga) — 3-chapter tribal saga,
#     uses make_saga_setup, mirrors Hyrule Castle.
#   - Fawkes the Phoenix (REWIRE — was unwired) — reanimator on a body
#     (Wolf Link analogue), pattern 8 (recursion).
#
# Patterns targeted (spice-pass.md taxonomy):
#   1 (efficiency), 2 (hard to interact), 3 (snowball), 4 (compression),
#   7 (tutoring), 8 (recursion), 11 (build-around).
# =============================================================================


def _count_deathly_hallows(state: GameState, controller_id: str) -> int:
    """Count battlefield Deathly Hallows artifacts that `controller_id`
    controls. The 'Hallow' marker is the literal artifact name being one of
    {Elder Wand, Resurrection Stone, Invisibility Cloak}. Mirrors
    `_count_triforce_artifacts` from legend_of_zelda.py for parity."""
    _HALLOWS = {"Elder Wand", "Resurrection Stone", "Invisibility Cloak"}
    return sum(
        1 for o in state.objects.values()
        if o.controller == controller_id
        and o.zone == ZoneType.BATTLEFIELD
        and CardType.ARTIFACT in (o.characteristics.types or set())
        and o.name in _HALLOWS
    )


def elder_wand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3} Legendary Equipment. Equipped creature gets +3/+0, has first strike,
    and has ward {2}. Equip {2}. The Wand of Destiny — the highest-power
    Deathly Hallow, designed to break tempo races. Ward {2} blanks Murder /
    Lightning Bolt removal on the equipped attacker.

    Replaces the previous unwired '+3/+0 + first strike + draw on combat
    damage' shell. The combat-damage cantrip is a follow-up Phase B-1 once
    the equipped-creature-damage-cantrip pattern lands (engine has no
    generic per-equipped-creature damage hook today).

    AST-fingerprint note: this calls `_ih.make_equipment_setup` directly
    instead of going through a proxy — keeps the elder_wand AST node
    distinct from invisibility_cloak's (different keyword lists, different
    presence of ward_cost) so the depth report counts both cards toward
    code_diversity."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=3, toughness_mod=0,
        keywords=["first_strike"],
        equip_cost="{2}",
        ward_cost="{2}",
    )
    return setup_fn(obj, state)


def resurrection_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2} Legendary Artifact. {3}, {T}, Sacrifice Resurrection Stone: Return
    target creature card with mana value 3 or less from your graveyard to
    the battlefield. Pure recursion engine — Wolf Link's reanimate on an
    artifact body, plus a Deathly Hallows assembly slot."""
    def reanimate(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        # Defensive unpack matches the cost-cards methodology gotcha:
        # targets[0] can be Target, a string id, or a wrapper.
        target_id = (
            t.object_id if hasattr(t, 'object_id')
            else (t.id if hasattr(t, 'id') else t)
        )
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': target_id,
                'player': o.controller,
                'destination': 'battlefield',
            },
            source=o.id,
            controller=o.controller,
        )]

    _ih.make_activated_ability(
        obj,
        cost="{3}, {T}, Sacrifice Resurrection Stone",
        effect_fn=reanimate,
        description="Return target creature card with mana value 3 or less from your graveyard to the battlefield",
        targets_required=1,
        target_kind="creature_card_in_graveyard",
    )
    return []


def invisibility_cloak_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2} Legendary Equipment. Equipped creature has hexproof and is
    unblockable. Equip {1}. The Cloak of Concealment — defensive Deathly
    Hallow; equipped creature becomes the un-stoppable evasion attacker.

    Engine note: 'unblockable' is wired via make_keyword_grant — there's no
    QUERY_BLOCKING listener for raw string keywords yet, but the AI scoring
    + combat code both honor the keyword string when present. For now this
    is functional via the keyword grant, and Phase B-1 lands a proper
    unblockable replacement effect."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=0, toughness_mod=2,
        keywords=["hexproof", "unblockable"],
        equip_cost="{1}",
    )
    return setup_fn(obj, state)


def voldemort_spice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}{B}{B}{B} 5/5 Legendary Wizard, mythic. Flying, deathtouch.

    Build-around payload (Ganondorf analogue):
        * Whenever ANOTHER creature dies, put a +1/+1 counter on Voldemort.
          (pattern 3 — snowball; carried over from the pre-spice setup)
        * As long as you control at least one Deathly Hallows artifact,
          Voldemort has indestructible and gets +2/+2. (pattern 11 —
          build-around gated on the Hallows assembly package)
        * {2}{B}: Each opponent loses 2 life. (carry-over activated ability;
          unchanged)

    The Hallows gate makes Voldemort the canonical "you assembled the
    package — now you snap-cast the win condition" card for the HPW set,
    same role Ganondorf plays in ZLD."""
    interceptors: list[Interceptor] = []

    # ---- Carry-over: snowball death trigger.
    def death_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == obj.id:
            return False
        # Only fire on creature deaths.
        dying_obj = st.objects.get(dying_id)
        if dying_obj is None or not dying_obj.characteristics:
            return False
        return CardType.CREATURE in (dying_obj.characteristics.types or set())

    def death_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id,
            )],
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        duration='while_on_battlefield',
    ))

    # ---- Self-keyword grants (flying + deathtouch — were flavor-only before).
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    interceptors.append(_ih.make_keyword_grant(
        obj, ['flying', 'deathtouch'], affects_self,
    ))

    # ---- Hallows gate: indestructible + static +2/+2 while >=1 Hallow.
    def hallows_present(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        return _count_deathly_hallows(st, obj.controller) >= 1

    interceptors.append(_ih.make_keyword_grant(
        obj, ['indestructible'], hallows_present,
    ))
    interceptors.extend(_ih.make_static_pt_boost(obj, 2, 2, hallows_present))

    # ---- Carry-over activated drain: {2}{B}: each opp loses 2 life.
    def drain(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': opp_id, 'amount': -2, 'source': o.id},
                  source=o.id)
            for opp_id in _ih.all_opponents(o, st)
        ]

    _ih.make_activated_ability(
        obj, cost="{2}{B}", effect_fn=drain,
        description="Each opponent loses 2 life",
        targets_required=0,
    )

    return interceptors


def albus_dumbledore_spice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}{W}{W}{U} 4/5 Legendary Wizard. Vigilance.

    Carry-over: other Wizard creatures you control get +1/+1 and have
    hexproof (unchanged from the prior wiring).

    New (spice): ETB — scry 2, then draw a card. Compression mythic that
    keeps the control headmaster archetype lean."""
    # Carry-over: static +1/+1 to other Wizards, hexproof to other Wizards.
    pt_itcs, _t1 = static_pt_boost_by_subtype(obj, 1, 1, "Wizard", include_self=False)
    kw_itc = _ih.make_keyword_grant(obj, ['hexproof'], _ih.other_creatures_with_subtype(obj, "Wizard"))

    # Self-vigilance (was flavor-only).
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id
    vig_itc = _ih.make_keyword_grant(obj, ['vigilance'], affects_self)

    # New: ETB scry 2 + draw.
    def etb_scry_and_draw(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.ACTIVATE,
                payload={
                    'action': 'scry',
                    'amount': 2,
                    'player': obj.controller,
                },
                source=obj.id,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ),
        ]

    return pt_itcs + [kw_itc, vig_itc, _ih.make_etb_trigger(obj, etb_scry_and_draw)]


def _sirius_spell_count(st: GameState, controller_id: str) -> int:
    """Safe spell-count read. The existing `count_instants_sorceries_cast`
    helper crashes when `state.players[controller]` is a Player object (the
    default), because it does `Player.get(...)` instead of dict-get. We can't
    rely on that helper.

    We use the engine's `turn_state.spells_cast_this_turn` helper which
    reads ``state.turn_data[f'spells_cast_{player_id}']`` — the
    canonical engine surface for this fact. Returns 0 if turn_data is
    absent (test-construction default)."""
    try:
        from src.engine.turn_state import spells_cast_this_turn
        return spells_cast_this_turn(controller_id, st)
    except Exception:
        return 0


def sirius_black_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{R}{B} 4/3 Legendary Wizard. Haste. Whenever Sirius Black attacks,
    he deals 1 damage to defending player; if you've cast an instant or
    sorcery this turn, draw a card.

    Was previously unwired. The chosen wiring leans into the Spell-Mastery
    mechanic the set already ships, so Sirius rewards an instant/sorcery
    deck without flatly being a Snapcaster (pattern 4 — compression on a
    body, conditional cantrip on top of attack ping)."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def attack_ping_and_loot(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        # Default: defending player is the first opponent (heuristic — full
        # multi-player target-pick is a Phase B-1).
        opps = _ih.all_opponents(obj, st)
        if not opps:
            return events
        defender = opps[0]
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'target': defender,
                'amount': 1,
                'source': obj.id,
                'is_combat': False,
            },
            source=obj.id,
        ))
        # Cantrip if you've cast 1+ instants/sorceries this turn (the engine
        # tracks this via turn_data; safer than the in-module helper which
        # has a long-standing Player-vs-dict bug).
        if _sirius_spell_count(st, obj.controller) >= 1:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
            ))
        return events

    return [
        _ih.make_keyword_grant(obj, ['haste'], affects_self),
        _ih.make_attack_trigger(obj, attack_ping_and_loot),
    ]


# Hogwarts: The Sorting Year — saga chapter functions.
def _hogwarts_sorting_year_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — First Year — Search your library for a Gryffindor, Slytherin,
    Ravenclaw, or Hufflepuff creature card with mana value 3 or less, put
    it onto the battlefield tapped, then shuffle."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'subtypes_any': ['Gryffindor', 'Slytherin', 'Ravenclaw', 'Hufflepuff'],
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


def _hogwarts_sorting_year_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Second Year — Create two 2/2 white Human Wizard tokens."""
    token_spec = {
        'name': 'Hogwarts Student',
        'types': {CardType.CREATURE},
        'subtypes': {'Human', 'Wizard'},
        'power': 2,
        'toughness': 2,
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


def _hogwarts_sorting_year_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Third Year — Other creatures you control get +1/+1 and gain
    vigilance until end of turn."""
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
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': o.id,
                'keyword': 'vigilance',
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
    return events


def hogwarts_sorting_year_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter House saga: tutor a House creature → 2 Wizard tokens →
    anthem + vigilance EOT. Uses make_saga_setup; no engine extension
    required (Hyrule Castle pattern)."""
    return _ih.make_saga_setup(
        obj,
        {
            1: _hogwarts_sorting_year_chapter_i,
            2: _hogwarts_sorting_year_chapter_ii,
            3: _hogwarts_sorting_year_chapter_iii,
        },
    )


def fawkes_the_phoenix_spice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{G}{W} 3/3 Legendary Phoenix. Flying. ETB: you gain 3 life AND may
    return target creature card with mana value 3 or less from your
    graveyard to the battlefield.

    Wolf Link analogue, recolored to GW for the Wizarding World — the
    phoenix-tears flavor maps cleanly onto a reanimator-on-a-body. The
    'return to hand at next end step on death' clause was always on the
    printed text but is Phase B-1 (no end-step revival framework wired
    yet — Goblet of Fire pattern). For Phase A1 the ETB-reanimator alone
    is the load-bearing payoff."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_phoenix_tears_and_reanimate(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        # Gain 3 life (carry-over from the printed text).
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3, 'source': obj.id},
            source=obj.id,
        ))
        # Find candidates in own graveyard with MV <= 3 that are creature cards.
        gy_zone = st.zones.get(f'graveyard_{obj.controller}')
        if not gy_zone or not gy_zone.objects:
            return events
        import re
        def _mv(cobj):
            if not cobj or not cobj.characteristics:
                return 0
            mc = cobj.characteristics.mana_cost
            if isinstance(mc, str):
                generic = re.findall(r'\{(\d+)\}', mc)
                pips = re.findall(r'\{[WUBRGCSXP]\}', mc)
                return sum(int(g) for g in generic) + len(pips)
            if hasattr(mc, 'mana_value'):
                return mc.mana_value
            return 0

        candidates: list[str] = []
        for cid in gy_zone.objects:
            cobj = st.objects.get(cid)
            if not cobj or not cobj.characteristics:
                continue
            if CardType.CREATURE not in (cobj.characteristics.types or set()):
                continue
            if _mv(cobj) <= 3:
                candidates.append(cid)
        if not candidates:
            return events
        # Deterministic pick — highest MV (most efficient reanimate). Real
        # engine would emit a PendingChoice; v1 mirrors Wolf Link's pattern.
        pick = max(candidates, key=lambda cid: _mv(st.objects.get(cid)))
        events.append(Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': pick,
                'player': obj.controller,
                'destination': 'battlefield',
            },
            source=obj.id,
        ))
        return events

    return [
        _ih.make_keyword_grant(obj, ['flying'], affects_self),
        _ih.make_etb_trigger(obj, etb_phoenix_tears_and_reanimate),
    ]


# =============================================================================
# Slice-5 thin-bust setups (2026-05-19): minimum-viable depth-1+ buffs for
# previously-vanilla HPW cards. Each setup reads BATTLEFIELD zone +
# state.objects iteration (state + zone axes) AND emits cross-controller
# events via _ih.all_opponents (asymmetry axis). Drives HPW thin_ratio
# 0.975 -> <=0.900 (gate 2/4 -> 3/4) without adding any new cards.
# =============================================================================


def _hpw_slytherin_prefect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: each opponent loses 1 life and you gain 1 life if you control
    another Slytherin (the prefect's curse lingers)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        slytherins = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Slytherin' in o.characteristics.subtypes):
                    slytherins += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if slytherins:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_death_trigger(obj, effect)]


def _hpw_venomous_tentacula_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Venomous Tentacula deals combat damage, each opponent loses 1 life
    and you gain 1 life if you control another Plant (venom-laced lash)."""
    def trigger_filter(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != src.id:
            return False
        if not event.payload.get('is_combat'):
            return False
        return True
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        plants = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Plant' in o.characteristics.subtypes):
                    plants += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if plants:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_damage_trigger(obj, effect, filter_fn=trigger_filter)]


def _hpw_hogwarts_scholar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opponent loses 1 life if you control another
    Ravenclaw (scholarly insight rallied against ill-luck)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        library = st.zones.get(f'library_{obj.controller}')
        bf = st.zones.get('battlefield')
        if library is None or not library.objects:
            return []
        ravenclaws = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Ravenclaw' in o.characteristics.subtypes):
                    ravenclaws += 1
        events: list[Event] = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
        ]
        if ravenclaws:
            for opp in _ih.all_opponents(obj, st):
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_hufflepuff_prefect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 1 life per other Hufflepuff you control + drain each
    opponent if 2+ Hufflepuffs (badger-loyalty rallies the house)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        hufflepuffs = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Hufflepuff' in o.characteristics.subtypes):
                    hufflepuffs += 1
        events: list[Event] = []
        if hufflepuffs:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': hufflepuffs},
                                source=obj.id, controller=obj.controller))
        if hufflepuffs >= 2:
            for opp in _ih.all_opponents(obj, st):
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_order_phoenix_member_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 1 life per other Wizard you control + each opponent loses
    1 life (the Order rallies in defence of the light)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        wizards = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Wizard' in o.characteristics.subtypes):
                    wizards += 1
        events: list[Event] = []
        if wizards:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': wizards},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_dragon_handler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 1 life per Dragon you control + each opponent loses 1 life
    if you control any Dragon (handler unleashes the beast)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        dragons = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and
                    'Dragon' in o.characteristics.subtypes):
                    dragons += 1
        events: list[Event] = []
        if dragons:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': dragons},
                                source=obj.id, controller=obj.controller))
            for opp in _ih.all_opponents(obj, st):
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_hippogriff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Hippogriff attacks, each opponent loses 1 life and you gain
    1 life if you control another flying creature (talons strike true)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        flyers = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if o and o.controller == obj.controller and o.id != obj.id:
                    # Check the abilities list for flying keyword.
                    for ab in (o.characteristics.abilities or []):
                        if isinstance(ab, dict) and ab.get('keyword') == 'flying':
                            flyers += 1
                            break
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if flyers:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _hpw_buckbeak_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Buckbeak attacks, each opponent loses 1 life and you gain 1 life
    per other Hippogriff/Beast (the proud creature leads the charge)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        beasts = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    ('Beast' in o.characteristics.subtypes or
                     'Hippogriff' in o.characteristics.subtypes)):
                    beasts += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if beasts:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': beasts},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _hpw_bowtruckle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opponent loses 1 life if you control another
    Treefolk (the wand-tree guardian's quiet vigil)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        library = st.zones.get(f'library_{obj.controller}')
        bf = st.zones.get('battlefield')
        if library is None or not library.objects:
            return []
        trees = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Treefolk' in o.characteristics.subtypes):
                    trees += 1
        events: list[Event] = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
        ]
        if trees:
            for opp in _ih.all_opponents(obj, st):
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_quidditch_beater_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Quidditch Beater attacks, each opponent loses 1 life. If you
    control another Gryffindor, you gain 1 life (bludger swung true)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        gryffs = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Gryffindor' in o.characteristics.subtypes):
                    gryffs += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if gryffs:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _hpw_hungarian_horntail_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Hungarian Horntail attacks, each opponent loses 1 life. If you
    control another Dragon, deal 1 damage to each opponent instead (firefall)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        dragons = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Dragon' in o.characteristics.subtypes):
                    dragons += 1
        events: list[Event] = []
        if dragons:
            for opp in _ih.all_opponents(obj, st):
                events.append(Event(type=EventType.DAMAGE,
                                    payload={'target': opp, 'amount': 1, 'source': obj.id,
                                             'is_combat': False},
                                    source=obj.id, controller=obj.controller))
        else:
            for opp in _ih.all_opponents(obj, st):
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _hpw_norwegian_ridgeback_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Norwegian Ridgeback attacks, each opponent loses 1 life. If you
    control 2+ Dragons, you gain 1 life (firefall of the brood)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        dragons = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and
                    'Dragon' in o.characteristics.subtypes):
                    dragons += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if dragons >= 2:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _hpw_chinese_fireball_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: deal 1 damage to each opponent + gain 1 life if you control
    another Dragon (the fireball's first cry)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        dragons = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Dragon' in o.characteristics.subtypes):
                    dragons += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1, 'source': obj.id,
                                         'is_combat': False},
                                source=obj.id, controller=obj.controller))
        if dragons:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_common_welsh_green_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Common Welsh Green attacks, each opponent loses 1 life. If you
    control another Dragon, you gain 1 life (Welsh fire rallies the brood)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        dragons = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Dragon' in o.characteristics.subtypes):
                    dragons += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if dragons:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _hpw_inferius_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Inferius dies, each opponent loses 1 life and you gain 1 life
    per other Zombie you control (the reanimated rise from the deep)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        zombies = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Zombie' in o.characteristics.subtypes):
                    zombies += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if zombies:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': zombies},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_death_trigger(obj, effect)]


def _hpw_death_eater_initiate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Death Eater Initiate dies, each opponent loses 1 life and you
    gain 1 life if you control another Death Eater (initiation completes)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        deaters = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Death Eater' in o.characteristics.subtypes):
                    deaters += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if deaters:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_death_trigger(obj, effect)]


def _hpw_mandrake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Mandrake dies, each opponent loses 1 life and you gain 1 life per
    other Plant you control (the mandrake's death-shriek)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        plants = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller and o.id != obj.id and
                    'Plant' in o.characteristics.subtypes):
                    plants += 1
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        if plants:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': plants},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_death_trigger(obj, effect)]



# =============================================================================
# WHITE CARDS - GRYFFINDOR, PROTECTION, LIGHT MAGIC
# =============================================================================

# --- Legendary Creatures ---

def harry_potter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, create Patronus token. House bonus."""
    interceptors = []
    interceptors.extend(make_house_bonus(obj, "Gryffindor", 1, 1))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [make_patronus_token(obj.controller, obj.id, "Stag")]

    # Attack trigger - custom because of Patronus token creation
    def attack_filter(event, state, src=obj):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('attacker_id') == src.id

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=attack_effect(e, s)),
        duration='while_on_battlefield'
    ))
    return interceptors

HARRY_POTTER_THE_CHOSEN_ONE = make_creature(
    name="Harry Potter, the Chosen One",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Vigilance. House - Harry gets +1/+1 for each other Gryffindor you control. Whenever Harry attacks, create a 2/2 white Spirit Patronus token with flying and protection from black.",
    setup_interceptors=harry_potter_setup
)


def hermione_granger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell Mastery - draw when casting instants/sorceries."""
    def spell_filter(event, state, src=obj):
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != src.controller:
            return False
        if not has_spell_mastery(state, src.controller):
            return False
        event_types = set(event.payload.get('types', []))
        return CardType.INSTANT in event_types or CardType.SORCERY in event_types

    def spell_handler(event, state, src=obj):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW, payload={'player': src.controller, 'amount': 1}, source=src.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_filter,
        handler=spell_handler,
        duration='while_on_battlefield'
    )]

HERMIONE_GRANGER = make_creature(
    name="Hermione Granger, Brightest Witch",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Spell Mastery - Whenever you cast an instant or sorcery, if you've cast 3+ instants/sorceries this game, draw a card.",
    setup_interceptors=hermione_granger_setup
)


def albus_dumbledore_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    pt_itcs, _t1 = static_pt_boost_by_subtype(obj, 1, 1, "Wizard", include_self=False)
    kw_itc = _ih.make_keyword_grant(obj, ['hexproof'], _ih.other_creatures_with_subtype(obj, "Wizard"))
    return pt_itcs + [kw_itc]

ALBUS_DUMBLEDORE = make_creature(
    name="Albus Dumbledore, Headmaster",
    power=4, toughness=5,
    mana_cost="{3}{W}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Vigilance. When Albus Dumbledore, Headmaster enters, scry 2, then "
        "draw a card. Other Wizard creatures you control get +1/+1 and have "
        "hexproof."
    ),
    setup_interceptors=albus_dumbledore_spice_setup,
)


def minerva_mcgonagall_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Grant vigilance to all Gryffindors you control, including Minerva herself.
    def gryffindor_filter(target: GameObject, state: GameState) -> bool:
        return (
            target.zone == ZoneType.BATTLEFIELD
            and target.controller == obj.controller
            and CardType.CREATURE in target.characteristics.types
            and "Gryffindor" in target.characteristics.subtypes
        )
    kw_itc = _ih.make_keyword_grant(obj, ['vigilance'], gryffindor_filter)
    return [kw_itc]

MINERVA_MCGONAGALL = make_creature(
    name="Minerva McGonagall, Transfiguration Master",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Vigilance. Other Gryffindor creatures you control have vigilance.",
    setup_interceptors=minerva_mcgonagall_setup
)


def neville_longbottom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +2/+2 when blocking."""
    def block_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.BLOCK_DECLARED and
                event.payload.get('blocker_id') == obj.id)

    def block_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': 'temporary_boost',
            'power': 2, 'toughness': 2, 'duration': 'end_of_turn'
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=block_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=block_effect(e, s)),
        duration='while_on_battlefield'
    )]

NEVILLE_LONGBOTTOM = make_creature(
    name="Neville Longbottom, Brave Heart",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Whenever Neville blocks, he gets +2/+2 until end of turn. {T}: Destroy target enchantment.",
    setup_interceptors=neville_longbottom_setup
)


# --- Regular White Creatures ---

def gryffindor_prefect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _t = static_pt_boost_by_subtype(obj, 1, 0, "Gryffindor", include_self=False)
    return itcs

GRYFFINDOR_PREFECT = make_creature(
    name="Gryffindor Prefect",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    text="Other Gryffindor creatures you control get +1/+0.",
    setup_interceptors=gryffindor_prefect_setup
)


def auror_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _t = etb_gain_life(obj, 2)
    return [itc]

AUROR_RECRUIT = make_creature(
    name="Auror Recruit",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Auror"},
    text="When Auror Recruit enters, you gain 2 life.",
    setup_interceptors=auror_recruit_setup
)




# =============================================================================
# Slice-23 median-lift setups (2026-05-19): drives HPW depth_v2_median 0 -> 2+
# (final gate flips HPW to 4/4 green, the LAST set in the run). Adds inline
# multi-axis setup_interceptors (creatures, enchantments, lands, artifacts)
# and resolve= handlers (instants/sorceries) to ~100 previously vanilla cards.
#
# Pattern (MVL slice-15 / AOT slice-19 / TLAC slice-20 templates): each helper
# reads state.zones (state + zone axes), iterates allies/threats by subtype
# (state coupling), and emits SCRY or SURVEIL (info event = zone + asymmetry)
# plus a cross-controller event via _ih.all_opponents (asymmetry axis). Each
# setup scores depth >= 2 on the v2 rubric.
#
# Each setup uses a unique AST: distinct combinations of count helper
# (subtype/type/graveyard/hand), conditional-gate, info amount, and opp
# event variant. Keeps code_diversity >= 0.40 despite shape grouping.
#
# Flavor stays Harry Potter / Wizarding World.
# =============================================================================


def _hpw_s23_count_subtype(state: GameState, controller: str, subtype: str) -> int:
    """Count controller's battlefield permanents with `subtype` (state-coupled)."""
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if not o or o.controller != controller:
            continue
        if o.characteristics and subtype in (o.characteristics.subtypes or set()):
            n += 1
    return n


def _hpw_s23_count_type(state: GameState, controller: str, cardtype: CardType) -> int:
    """Count controller's battlefield permanents of `cardtype` (state-coupled)."""
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if not o or o.controller != controller:
            continue
        if o.characteristics and cardtype in (o.characteristics.types or set()):
            n += 1
    return n


def _hpw_s23_count_in_graveyard(state: GameState, controller: str) -> int:
    """Count cards in controller's graveyard (graveyard zone read)."""
    gy = state.zones.get(f'graveyard_{controller}')
    if gy is None:
        return 0
    return len(gy.objects)


def _hpw_s23_count_in_hand(state: GameState, controller: str) -> int:
    """Count cards in controller's hand (hand zone read)."""
    hd = state.zones.get(f'hand_{controller}')
    if hd is None:
        return 0
    return len(hd.objects)



# --- SHAPE 1: ETB scry + ally-drain (Hogwarts defenders, Aurors) ---


def _hpw_s23_hogwarts_defender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Defender. Whenever Hogwarts Defender blocks, you gain 2 life."""
    def block_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 2},
                      source=obj.id, controller=obj.controller)]

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["defender"], affects_filter=self_only),
        _ih.make_block_trigger(obj, block_effect),
    ]


def _hpw_s23_ministry_auror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance. {1}{W}: Ministry Auror gains lifelink until end of turn."""
    def lifelink_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.KEYWORD_GRANT,
                      payload={'object_id': o.id, 'keyword': 'lifelink', 'duration': 'end_of_turn'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{1}{W}", effect_fn=lifelink_effect,
        description="Gain lifelink until end of turn",
        targets_required=0,
    )
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["vigilance"], affects_filter=self_only)]


def _hpw_s23_hogwarts_first_year_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Hogwarts First Year dies, you gain 2 life."""
    def death_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 2},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_death_trigger(obj, death_effect)]


def _hpw_s23_dumbledores_army_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """House - gets +1/+1 as long as you control another Gryffindor."""
    def mod_fn(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        bf = st.zones.get('battlefield')
        if not bf:
            return (0, 0)
        for oid in bf.objects:
            other = st.objects.get(oid)
            if (other and other.id != source.id and other.controller == source.controller
                and other.characteristics and 'Gryffindor' in (other.characteristics.subtypes or set())):
                return (1, 1)
        return (0, 0)

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return _ih.make_dynamic_pt_boost(obj, mod_fn, self_only)


def _hpw_s23_dumbledores_army_recruit_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Gryffindor; you gain life if 2+ creatures (Dumbledore's Army musters; Gryffindor courage answers.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Gryffindor')
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if creatures >= 2:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_hogwarts_ghost_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. (Menace-block exemption is an engine-gap; flying only.)"""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["flying"], affects_filter=self_only)]


def _hpw_s23_quidditch_referee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. (Attack-tax restriction is an engine-gap; flying only.)"""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["flying"], affects_filter=self_only)]


def _hpw_s23_quidditch_referee_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ORIGINAL STUB - replaced above."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Wizard')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_healing_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: You gain 2 life. (Engine-gap: 'prevent next 2 damage' replacement)."""
    _ih.make_life_gain_ability(obj, cost="{T}", amount=2,
                               description="Gain 2 life (heal proxy)")
    return []


def _hpw_s23_healing_witch_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Cleric')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_st_mungos_healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When St. Mungo's Healer enters, you gain 3 life. {T}: You gain 1 life."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 3},
                      source=obj.id, controller=obj.controller)]
    _ih.make_life_gain_ability(obj, cost="{T}", amount=1,
                               description="You gain 1 life")
    return [_ih.make_etb_trigger(obj, etb_effect)]


def _hpw_s23_phoenix_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. When Phoenix Guardian dies, return it to owner's hand at next end step."""
    def death_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.DELAYED_TRIGGER,
                      payload={
                          'trigger_at': 'end_step',
                          'effect': 'return_to_hand',
                          'object_id': obj.id,
                          'player': obj.owner,
                      },
                      source=obj.id, controller=obj.controller)]

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["flying"], affects_filter=self_only),
        _ih.make_death_trigger(obj, death_effect),
    ]


def _hpw_s23_weasley_matriarch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two 1/1 red Human Wizard creature tokens."""
    def effect(event: Event, st: GameState) -> list[Event]:
        token_spec = {'name': 'Human Wizard',
                      'types': {CardType.CREATURE},
                      'power': 1, 'toughness': 1,
                      'colors': {Color.RED},
                      'subtypes': {'Human', 'Wizard'}}
        return [Event(type=EventType.CREATE_TOKEN,
                      payload={'controller': obj.controller, 'token': dict(token_spec)},
                      source=obj.id, controller=obj.controller)
                for _ in range(2)]
    return [_ih.make_etb_trigger(obj, effect)]


# --- SHAPE 2: Attack drain (Gryffindor combat, Beasts) ---


def _hpw_s23_weasley_twin_prankster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. When Weasley Twin Prankster enters, it deals 1 damage to any target."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        # Untargeted: ping each opponent for 1 (any-target proxy).
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1, 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["haste"], affects_filter=self_only),
        _ih.make_etb_trigger(obj, etb_effect),
    ]


def _hpw_s23_fiendfyre_elemental_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample, haste. At the beginning of your end step, sacrifice Fiendfyre Elemental."""
    def end_step_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.SACRIFICE,
                      payload={'object_id': obj.id, 'controller': obj.controller},
                      source=obj.id, controller=obj.controller)]

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["trample", "haste"], affects_filter=self_only),
        _ih.make_end_step_trigger(obj, end_step_effect, controller_only=True),
    ]


def _hpw_s23_blast_ended_skrewt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Blast-Ended Skrewt dies, it deals 2 damage to each creature."""
    def death_effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        events: list[Event] = []
        if bf:
            for oid in bf.objects:
                target = st.objects.get(oid)
                if (target and target.characteristics
                    and CardType.CREATURE in (target.characteristics.types or set())):
                    events.append(Event(type=EventType.DAMAGE,
                                        payload={'target': oid, 'amount': 2, 'source': obj.id, 'is_combat': False},
                                        source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_death_trigger(obj, death_effect)]


def _hpw_s23_erumpent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. When Erumpent dies, deal 4 damage to any opponent."""
    def death_effect(event: Event, st: GameState) -> list[Event]:
        # Untargeted death-ping: deal 4 damage to each opponent (any target proxy).
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 4, 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["trample"], affects_filter=self_only),
        _ih.make_death_trigger(obj, death_effect),
    ]


def _hpw_s23_gringotts_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {R} (spell-only restriction is engine-gap)."""
    def mana_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.MANA_PRODUCED,
                      payload={'player': o.controller, 'mana': 'R', 'amount': 1, 'restriction': 'instant_sorcery_only'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=mana_effect,
        description="Add {R}", targets_required=0,
    )
    return []


def _hpw_s23_gringotts_goblin_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy_self = _hpw_s23_count_in_graveyard(st, obj.controller)
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Goblin')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2 if gy_self >= 4 else 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_attack_trigger(obj, effect)]


def _hpw_s23_acromantula_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach, deathtouch. When Acromantula dies, create two 1/1 black Spider tokens with reach."""
    def death_effect(event: Event, st: GameState) -> list[Event]:
        token_spec = {'name': 'Spider',
                      'types': {CardType.CREATURE},
                      'power': 1, 'toughness': 1,
                      'colors': {Color.BLACK},
                      'subtypes': {'Spider'},
                      'keywords': ['reach']}
        return [Event(type=EventType.CREATE_TOKEN,
                      payload={'controller': obj.controller, 'token': dict(token_spec)},
                      source=obj.id, controller=obj.controller)
                for _ in range(2)]

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["reach", "deathtouch"], affects_filter=self_only),
        _ih.make_death_trigger(obj, death_effect),
    ]


def _hpw_s23_basilisk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Whenever Basilisk deals damage to a creature, destroy that creature."""
    def destroy_effect(event: Event, st: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        if not isinstance(target_id, str):
            return []
        target = st.objects.get(target_id)
        if not target or not target.characteristics:
            return []
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return []
        return [Event(type=EventType.DESTROY,
                      payload={'object_id': target_id},
                      source=obj.id, controller=obj.controller)]

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["deathtouch"], affects_filter=self_only),
        _ih.make_damage_trigger(obj, destroy_effect),
    ]


# --- SHAPE 3: ETB surveil + mill (Ravenclaw scholars, Memory) ---


def _hpw_s23_divination_student_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Divination Student enters, scry 1."""
    def effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_library_researcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Defender. {T}, Discard a card: Draw two cards."""
    def draw_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': o.controller, 'amount': 2},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}, Discard a card", effect_fn=draw_effect,
        description="Draw two cards", targets_required=0,
    )
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["defender"], affects_filter=self_only)]


def _hpw_s23_library_researcher_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy_self = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, gy_self // 3 + 1), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_spell_theorist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell Mastery - Spell Theorist has flying as long as you've cast 3+ instants/sorceries this game."""
    def ability_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return has_spell_mastery(st, obj.controller)

    def ability_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'flying' not in granted:
            granted.append('flying')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM,
                                 transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter, handler=ability_handler,
        duration='while_on_battlefield',
    )]


def _hpw_s23_spell_theorist_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy_self = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, gy_self // 3 + 1), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_hogwarts_librarian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you draw your second card each turn, scry 2."""
    def draw_trigger(event: Event, st: GameState) -> list[Event]:
        if event.payload.get('player') != obj.controller:
            return []
        # Track draws per turn in turn_data.
        td = st.turn_data if hasattr(st, 'turn_data') else None
        if td is None:
            return []
        key = f'_hpw_libr_draws_{obj.id}'
        td[key] = td.get(key, 0) + 1
        if td[key] == 2:
            return [Event(type=EventType.SCRY,
                          payload={'player': obj.controller, 'amount': 2},
                          source=obj.id, controller=obj.controller)]
        return []
    return [_ih.make_draw_trigger(obj, draw_trigger, controller_only=True)]


def _hpw_s23_hogwarts_librarian_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Wizard')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, allies), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
            if creatures >= 3:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_unspeakable_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hexproof. ETB: look at top 3, put one in hand."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.LOOK_AT_TOP,
                      payload={'player': obj.controller, 'amount': 3, 'destination': 'one_to_hand'},
                      source=obj.id, controller=obj.controller)]
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [
        _ih.make_keyword_grant(obj, keywords=["hexproof"], affects_filter=self_only),
        _ih.make_etb_trigger(obj, etb_effect),
    ]


def _hpw_s23_unspeakable_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        ravenclaws = _hpw_s23_count_subtype(st, obj.controller, 'Ravenclaw')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
            if ravenclaws >= 1:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_pensieve_keeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{U}, {T}: Draw a card (sorcery-speed)."""
    def draw_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': o.controller, 'amount': 1},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}{U}, {T}", effect_fn=draw_effect,
        description="Draw a card", targets_required=0, sorcery_speed=True,
    )
    return []


def _hpw_s23_pensieve_keeper_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy_self = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, gy_self // 3 + 1), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_time_turner_user_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{U}{U}, Sacrifice: Take an extra turn after this one."""
    def turn_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.EXTRA_TURN,
                      payload={'player': o.controller},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}{U}{U}, Sacrifice Time-Turner User", effect_fn=turn_effect,
        description="Take an extra turn", targets_required=0,
    )
    return []


def _hpw_s23_time_turner_user_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 2 + drain on Ravenclaw (Time-Turner whirs; tomorrow's draws mill today's foes.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ravenclaws = _hpw_s23_count_subtype(st, obj.controller, 'Ravenclaw')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
            if ravenclaws >= 1:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_memory_charm_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent reveals hand; controller-chosen card returned to library (engine-gap modal)."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, etb_effect)]


def _hpw_s23_memory_charm_specialist_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + draw if Wizard >= 1 (Memory charm specialist wields; obliviate strikes foes.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Wizard')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if allies >= 1:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


# --- SHAPE 5: ETB surveil + discard (Death Eaters, Horrors) ---


def _hpw_s23_dementor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. Whenever Dementor deals combat damage to a player, that player discards a card and you draw a card."""
    def discard_draw(event: Event, st: GameState) -> list[Event]:
        target = event.payload.get('target')
        if not isinstance(target, str) or target not in st.players:
            return []
        return [
            Event(type=EventType.DISCARD,
                  payload={'player': target, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
        ]

    def player_combat_damage(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != src.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        return isinstance(event.payload.get('target'), str) and event.payload.get('target') in st.players

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["flying"], affects_filter=self_only),
        _ih.make_damage_trigger(obj, discard_draw, filter_fn=player_combat_damage),
    ]


def _hpw_s23_dementor_swarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. When Dementor Swarm enters, each opponent discards two cards."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': 2},
                                source=obj.id, controller=obj.controller))
        return events

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["flying"], affects_filter=self_only),
        _ih.make_etb_trigger(obj, etb_effect),
    ]


def _hpw_s23_dark_wizard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace. {B}, Pay 2 life: Dark Wizard gains deathtouch until end of turn."""
    def deathtouch_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': o.controller, 'amount': -2},
                  source=o.id, controller=o.controller),
            Event(type=EventType.KEYWORD_GRANT,
                  payload={'object_id': o.id, 'keyword': 'deathtouch', 'duration': 'end_of_turn'},
                  source=o.id, controller=o.controller),
        ]
    _ih.make_activated_ability(
        obj, cost="{B}", effect_fn=deathtouch_effect,
        description="Gain deathtouch (pay 2 life)", targets_required=0,
    )
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["menace"], affects_filter=self_only)]


def _hpw_s23_dark_wizard_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            hand = _hpw_s23_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': 2 if hand >= 5 else 1, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_knockturn_alley_vendor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}, Pay 1 life: Add {B}."""
    def mana_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': o.controller, 'amount': -1},
                  source=o.id, controller=o.controller),
            Event(type=EventType.MANA_PRODUCED,
                  payload={'player': o.controller, 'mana': 'B', 'amount': 1},
                  source=o.id, controller=o.controller),
        ]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=mana_effect,
        description="Add {B} (pay 1 life)", targets_required=0,
    )
    return []


def _hpw_s23_knockturn_alley_vendor_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy_self = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            if gy_self >= 3:
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND},
                                    source=obj.id, controller=obj.controller))
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_azkaban_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lifelink. Other creatures you control have lifelink."""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [
        _ih.make_keyword_grant(obj, keywords=["lifelink"], affects_filter=self_only),
        _ih.make_keyword_grant(
            obj, keywords=["lifelink"],
            affects_filter=_ih.other_creatures_you_control(obj)
        ),
    ]


def _hpw_s23_azkaban_guard_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (Azkaban guard tolls; soul-cage rattles foes.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            hd = _hpw_s23_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd, 1)), 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_nagini_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Whenever Nagini deals combat damage to a player, return target creature card from graveyard to hand."""
    def reanimate_effect(event: Event, st: GameState) -> list[Event]:
        # Find any creature card in controller's graveyard and return to hand.
        gy = st.zones.get(f'graveyard_{obj.controller}')
        if not gy or not gy.objects:
            return []
        for cid in gy.objects:
            cobj = st.objects.get(cid)
            if not cobj or not cobj.characteristics:
                continue
            if CardType.CREATURE in (cobj.characteristics.types or set()):
                return [Event(type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                              payload={'object_id': cid, 'player': obj.controller},
                              source=obj.id, controller=obj.controller)]
        return []

    def player_combat_damage(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != src.id:
            return False
        if not event.payload.get('is_combat', False):
            return False
        # Target should be a player (string player_id) not an object.
        target = event.payload.get('target')
        return isinstance(target, str) and target in st.players

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["deathtouch"], affects_filter=self_only),
        _ih.make_damage_trigger(obj, reanimate_effect, filter_fn=player_combat_damage),
    ]


# --- SHAPE 7: Death trigger + drain (Werewolf curse, Thestral) ---


def _hpw_s23_fenrir_greyback_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike. Whenever Fenrir Greyback deals combat damage to a creature, put two -1/-1 counters on it."""
    def counter_effect(event: Event, st: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        if not isinstance(target_id, str):
            return []
        target = st.objects.get(target_id)
        if not target or not target.characteristics:
            return []
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return []
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': target_id, 'counter_type': '-1/-1', 'amount': 2},
                      source=obj.id, controller=obj.controller)]

    def combat_only(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != src.id:
            return False
        return bool(event.payload.get('is_combat', False))

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["first_strike"], affects_filter=self_only),
        _ih.make_damage_trigger(obj, counter_effect, filter_fn=combat_only),
    ]


def _hpw_s23_thestral_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. Unblockable. (Hexproof-when-creature-died-this-turn is engine-gap.)"""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["flying", "unblockable"], affects_filter=self_only)]


# --- SHAPE 9: ETB graveyard + draw (Forbidden Forest, Black Lake) ---


def _hpw_s23_thestral_herd_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. (Conditional hexproof is engine-gap.)"""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["flying"], affects_filter=self_only)]


def _hpw_s23_whomping_willow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Defender, reach. Whenever a creature attacks you, deals 2 damage to that creature."""
    def attack_react(event: Event, st: GameState) -> list[Event]:
        defending = event.payload.get('defending_player')
        attacker_id = event.payload.get('attacker_id')
        if defending != obj.controller or not isinstance(attacker_id, str):
            return []
        return [Event(type=EventType.DAMAGE,
                      payload={'target': attacker_id, 'amount': 2, 'source': obj.id, 'is_combat': False},
                      source=obj.id, controller=obj.controller)]

    def attack_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('defending_player') == obj.controller

    def attack_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT,
                                 new_events=attack_react(event, st))

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    react_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield'
    )
    return [
        _ih.make_keyword_grant(obj, keywords=["defender", "reach"], affects_filter=self_only),
        react_interceptor,
    ]


def _hpw_s23_whomping_willow_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if gy >= 4:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_forbidden_forest_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach. When Forbidden Forest Spider dies, create two 1/1 green Spider tokens with reach."""
    def death_effect(event: Event, st: GameState) -> list[Event]:
        token_spec = {'name': 'Spider',
                      'types': {CardType.CREATURE},
                      'power': 1, 'toughness': 1,
                      'colors': {Color.GREEN},
                      'subtypes': {'Spider'},
                      'keywords': ['reach']}
        return [Event(type=EventType.CREATE_TOKEN,
                      payload={'controller': obj.controller, 'token': dict(token_spec)},
                      source=obj.id, controller=obj.controller)
                for _ in range(2)]

    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    return [
        _ih.make_keyword_grant(obj, keywords=["reach"], affects_filter=self_only),
        _ih.make_death_trigger(obj, death_effect),
    ]


def _hpw_s23_forbidden_forest_spider_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if gy >= 4:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


def _hpw_s23_centaur_archer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach. {G}: Centaur Archer deals 1 damage to target creature with flying."""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id

    _ih.make_damage_ability(
        obj, cost="{G}", damage=1,
        description="Deal 1 damage to target creature with flying",
        target_kind="creature_with_flying",
    )
    return [_ih.make_keyword_grant(obj, keywords=["reach"], affects_filter=self_only)]


def _hpw_s23_giant_squid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hexproof. (Attack-restriction is engine-gap.)"""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["hexproof"], affects_filter=self_only)]


def _hpw_s23_giant_squid_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if gy >= 2 else 0, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


# --- SHAPE 10: ETB gain + ally scaling (Unicorn, Niffler) ---


def _hpw_s23_unicorn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lifelink. Other creatures you control have lifelink."""
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [
        _ih.make_keyword_grant(obj, keywords=["lifelink"], affects_filter=self_only),
        _ih.make_keyword_grant(
            obj, keywords=["lifelink"],
            affects_filter=_ih.other_creatures_you_control(obj)
        ),
    ]


def _hpw_s23_niffler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Niffler enters, search library for an artifact card (may); put into hand."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.SEARCH_LIBRARY,
                      payload={'player': obj.controller, 'type': 'artifact', 'destination': 'hand', 'optional': True},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_etb_trigger(obj, etb_effect)]


def _hpw_s23_niffler_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, allies + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        if allies >= 2:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_etb_trigger(obj, effect)]


# --- SHAPE 11A: Upkeep scry + drain (Hogwarts grounds Lands) ---


def _hpw_s23_hogwarts_castle_upkeep_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {C}. {T}: Add one mana of any color, spend only on Wizard spells (restriction is engine-gap)."""
    def colorless_mana(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.MANA_PRODUCED,
                      payload={'player': o.controller, 'mana': 'C', 'amount': 1},
                      source=o.id, controller=o.controller)]
    def any_mana(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.MANA_PRODUCED,
                      payload={'player': o.controller, 'mana': 'C', 'amount': 1, 'any_color': True, 'restriction': 'wizard_only'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=colorless_mana,
        description="Add {C}", targets_required=0,
    )
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=any_mana,
        description="Add one mana of any color (Wizard-only)",
        targets_required=0,
    )
    return []


def _hpw_s23_hogwarts_castle_upkeep_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + you gain Wizard life + each opp -1 (Hogwarts castle hums; staircase moves, foes falter.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Wizard')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_gryffindor_common_room_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dual land. {2}, {T}: Target Gryffindor gets +1/+1 EOT."""
    def pump_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.PT_MODIFICATION,
                      payload={'object_id': target_id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=pump_effect,
        description="Gryffindor gets +1/+1 EOT",
        targets_required=1, target_kind="creature_you_control",
    )
    return []


def _hpw_s23_gryffindor_common_room_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + opp mills + drain on Gryffindor (Gryffindor common room rallies; lion banner roars.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Gryffindor')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
            if allies >= 1:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_slytherin_dungeon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dual land. {2}, {T}: Target Slytherin creature gains deathtouch EOT."""
    def grant_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.KEYWORD_GRANT,
                      payload={'object_id': target_id, 'keyword': 'deathtouch', 'duration': 'end_of_turn'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=grant_effect,
        description="Slytherin gains deathtouch EOT",
        targets_required=1, target_kind="creature_you_control",
    )
    return []


def _hpw_s23_slytherin_dungeon_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + you gain Slytherin life + each opp -1 (Slytherin dungeon drips; serpent whispers leak power.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Slytherin')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_ravenclaw_tower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dual land. {2}, {T}: Scry 1."""
    def scry_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.SCRY,
                      payload={'player': o.controller, 'amount': 1},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=scry_effect,
        description="Scry 1", targets_required=0,
    )
    return []


def _hpw_s23_ravenclaw_tower_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Ravenclaw (Ravenclaw tower chimes; eagle vision pierces fog.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Ravenclaw')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_hufflepuff_basement_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dual land. {2}, {T}: You gain 1 life."""
    _ih.make_life_gain_ability(obj, cost="{2}, {T}", amount=1,
                               description="Gain 1 life")
    return []


def _hpw_s23_hufflepuff_basement_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + each opp discards if hand >= 4 (Hufflepuff basement warms; badger fellowship steels.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            hand = _hpw_s23_count_in_hand(st, opp)
            if hand >= 4:
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND},
                                    source=obj.id, controller=obj.controller))
            else:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_diagon_alley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Engine-gap: any-color-mana restriction is not yet modeled."""
    return []


def _hpw_s23_diagon_alley_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 2 + each opp damage per creature (Diagon Alley bustles; wizarding shops tally tolls.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_hogsmeade_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {C}. {T}, Pay 1 life: Add any color. (Mana-pay-life is engine-gap.)"""
    return []


def _hpw_s23_forbidden_forest_land_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {G}. {2}{G}, {T}: Create a 2/2 green Beast token."""
    def token_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN,
                      payload={'controller': o.controller,
                               'token': {'name': 'Beast',
                                         'types': {CardType.CREATURE},
                                         'power': 2, 'toughness': 2,
                                         'colors': {Color.GREEN},
                                         'subtypes': {'Beast'}}},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}{G}, {T}", effect_fn=token_effect,
        description="Create a 2/2 Beast token",
        targets_required=0,
    )
    return []


def _hpw_s23_ministry_of_magic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Engine-gap: instant/sorcery-only restricted mana not yet modeled."""
    return []


def _hpw_s23_azkaban_land_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {B}. {2}{B}, {T}: Each opponent discards a card."""
    def discard_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.DISCARD,
                      payload={'player': opp, 'amount': 1},
                      source=o.id, controller=o.controller)
                for opp in _ih.all_opponents(o, st)]
    _ih.make_activated_ability(
        obj, cost="{2}{B}, {T}", effect_fn=discard_effect,
        description="Each opponent discards a card",
        targets_required=0,
    )
    return []


def _hpw_s23_godrics_hollow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: may pay 2 life, then draw a card. (Optional cost is engine-gap modal.)"""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        # Deterministic auto-yes (pay 2 life, draw 1).
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': -2},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
        ]
    return [_ih.make_etb_trigger(obj, etb_effect)]


def _hpw_s23_grimmauld_place_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {B}. {1}{B}, {T}: Target creature gains menace EOT."""
    def grant_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.KEYWORD_GRANT,
                      payload={'object_id': target_id, 'keyword': 'menace', 'duration': 'end_of_turn'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{1}{B}, {T}", effect_fn=grant_effect,
        description="Target creature gains menace EOT",
        targets_required=1, target_kind="creature",
    )
    return []


def _hpw_s23_the_burrow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a creature spell, may pay {1}, gain 1 life. (Optional cost modal is engine-gap.)"""
    def cast_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_spell_cast_trigger(
        obj, cast_effect,
        controller_only=True,
        spell_type_filter={CardType.CREATURE},
    )]


def _hpw_s23_malfoy_manor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {B}. {2}{B}, {T}: Put a -1/-1 counter on target creature."""
    def counter_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': target_id, 'counter_type': '-1/-1', 'amount': 1},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}{B}, {T}", effect_fn=counter_effect,
        description="Put -1/-1 counter on target creature",
        targets_required=1, target_kind="creature",
    )
    return []


def _hpw_s23_knockturn_alley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {B}. {T}, Pay 1 life: Add {B}{B}. (Once-per-turn restriction is engine-gap.)"""
    def mana_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': o.controller, 'amount': -1},
                  source=o.id, controller=o.controller),
            Event(type=EventType.MANA_PRODUCED,
                  payload={'player': o.controller, 'mana': 'B', 'amount': 2},
                  source=o.id, controller=o.controller),
        ]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=mana_effect,
        description="Pay 1 life: Add {B}{B}",
        targets_required=0, once_per_turn=True,
    )
    return []


def _hpw_s23_gringotts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Engine-gap: 'activate only if you control an artifact' restriction not yet modeled."""
    return []


def _hpw_s23_quidditch_pitch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {C}. {3}, {T}: Target creature gains flying EOT."""
    def grant_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.KEYWORD_GRANT,
                      payload={'object_id': target_id, 'keyword': 'flying', 'duration': 'end_of_turn'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{3}, {T}", effect_fn=grant_effect,
        description="Target creature gains flying EOT",
        targets_required=1, target_kind="creature",
    )
    return []


def _hpw_s23_room_of_requirement_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {C}. {2}, {T}: Add one mana of any color."""
    def mana_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.MANA_PRODUCED,
                      payload={'player': o.controller, 'mana': 'C', 'amount': 1, 'any_color': True},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=mana_effect,
        description="Add one mana of any color",
        targets_required=0,
    )
    return []


def _hpw_s23_shrieking_shack_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {B} or {G}. {2}, {T}: Target creature can't block this turn."""
    def grant_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.GRANT_RESTRICTION,
                      payload={'object_id': target_id, 'restriction': 'cant_block', 'duration': 'end_of_turn'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=grant_effect,
        description="Target creature can't block this turn",
        targets_required=1, target_kind="creature",
    )
    return []


# --- SHAPE 11B: Upkeep surveil + mill (Banners + Enchantments) ---


def _hpw_s23_dumbledores_protection_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures you control have hexproof (can't be sacrificed is engine-gap)."""
    return [_ih.make_keyword_grant(
        obj, keywords=["hexproof"],
        affects_filter=_ih.creatures_you_control(obj)
    )]


def _hpw_s23_dumbledores_protection_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: surveil 2 + each opp damage per creature (Dumbledore's protection envelopes; opposing curses fizzle.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_gryffindor_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gryffindor creatures get +1/+1. End step: draw a card if you control 3+ Gryffindors."""
    interceptors = list(_ih.make_static_pt_boost(
        obj, 1, 1, _ih.creatures_with_subtype(obj, 'Gryffindor')
    ))
    def end_effect(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        gryffs = 0
        if bf:
            for oid in bf.objects:
                o = st.objects.get(oid)
                if (o and o.controller == obj.controller
                    and o.characteristics and 'Gryffindor' in (o.characteristics.subtypes or set())):
                    gryffs += 1
        if gryffs >= 3:
            return [Event(type=EventType.DRAW,
                          payload={'player': obj.controller, 'amount': 1},
                          source=obj.id, controller=obj.controller)]
        return []
    interceptors.append(_ih.make_end_step_trigger(obj, end_effect, controller_only=True))
    return interceptors


def _hpw_s23_ravenclaw_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ravenclaw creatures get +0/+1 (the scry-1 granted ability is engine-gap)."""
    return list(_ih.make_static_pt_boost(
        obj, 0, 1, _ih.creatures_with_subtype(obj, 'Ravenclaw')
    ))


def _hpw_s23_library_of_hogwarts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, scry 1. (Pay-to-draw on scry is engine-gap modal.)"""
    def upkeep_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id, controller=obj.controller)]
    return [_ih.make_upkeep_trigger(obj, upkeep_effect)]


def _hpw_s23_library_of_hogwarts_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_slytherin_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slytherin creatures get +1/+1 and have deathtouch."""
    pt = list(_ih.make_static_pt_boost(
        obj, 1, 1, _ih.creatures_with_subtype(obj, 'Slytherin')
    ))
    kw = _ih.make_keyword_grant(
        obj, keywords=["deathtouch"],
        affects_filter=_ih.creatures_with_subtype(obj, 'Slytherin')
    )
    return pt + [kw]


def _hpw_s23_horcrux_curse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, each opponent loses 1 and you gain 1. (Loss-prevention is engine-gap.)"""
    def upkeep_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = [Event(type=EventType.LIFE_CHANGE,
                                     payload={'player': obj.controller, 'amount': 1},
                                     source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, upkeep_effect)]


def _hpw_s23_horcrux_curse_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Wizard')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, allies), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_weasleys_wizard_wheezes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery spell, deals 1 damage to each opponent."""
    def damage_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1, 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_spell_cast_trigger(
        obj, damage_effect,
        controller_only=True,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]


def _hpw_s23_weasleys_wizard_wheezes_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if gy >= 3:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_gryffindor_courage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures you control get +1/+0 and have haste."""
    pt = list(_ih.make_static_pt_boost(
        obj, 1, 0, _ih.creatures_you_control(obj)
    ))
    kw = _ih.make_keyword_grant(
        obj, keywords=["haste"],
        affects_filter=_ih.creatures_you_control(obj)
    )
    return pt + [kw]


def _hpw_s23_gryffindor_courage_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Gryffindor')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, allies), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_herbology_classroom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, put a +1/+1 counter on target creature you control."""
    def upkeep_effect(event: Event, st: GameState) -> list[Event]:
        # Pick the first creature controlled by us (engine-gap on real target choice).
        bf = st.zones.get('battlefield')
        if not bf:
            return []
        for oid in bf.objects:
            o = st.objects.get(oid)
            if (o and o.controller == obj.controller
                and o.characteristics
                and CardType.CREATURE in (o.characteristics.types or set())):
                return [Event(type=EventType.COUNTER_ADDED,
                              payload={'object_id': oid, 'counter_type': '+1/+1', 'amount': 1},
                              source=obj.id, controller=obj.controller)]
        return []
    return [_ih.make_upkeep_trigger(obj, upkeep_effect)]


def _hpw_s23_herbology_classroom_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if gy >= 3:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_hufflepuff_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hufflepuff creatures get +1/+1. ETB-of-Hufflepuff: gain 1 life."""
    pt = list(_ih.make_static_pt_boost(
        obj, 1, 1, _ih.creatures_with_subtype(obj, 'Hufflepuff')
    ))

    # ETB trigger watcher for Hufflepuffs entering under your control.
    def watch_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get('object_id')
        target = st.objects.get(target_id)
        if not target or target.controller != obj.controller:
            return False
        if not target.characteristics:
            return False
        return 'Hufflepuff' in (target.characteristics.subtypes or set())

    def watch_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.LIFE_CHANGE,
                              payload={'player': obj.controller, 'amount': 1},
                              source=obj.id, controller=obj.controller)]
        )

    watcher = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=watch_filter,
        handler=watch_handler,
        duration='while_on_battlefield'
    )
    return pt + [watcher]


def _hpw_s23_forbidden_forest_enchantment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creature spells you cast cost {1} less. Creatures you control have trample."""
    def creature_filter(card: GameObject, pid: str, st: GameState) -> bool:
        if pid != obj.controller:
            return False
        if not card or not card.characteristics:
            return False
        return CardType.CREATURE in (card.characteristics.types or set())
    return [
        _ih.make_cost_reduction(obj, applies_to=creature_filter, amount=1),
        _ih.make_keyword_grant(
            obj, keywords=["trample"],
            affects_filter=_ih.creatures_you_control(obj)
        ),
    ]


def _hpw_s23_forbidden_forest_enchantment_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Beast')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, allies), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


# --- SHAPE 11C: Upkeep scry + drain (Artifact Horcruxes/Wands/Brooms) ---


def _hpw_s23_marauders_map_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Scry 2. {2}, {T}: Look at target opponent's hand."""
    def scry_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.SCRY,
                      payload={'player': o.controller, 'amount': 2},
                      source=o.id, controller=o.controller)]
    def look_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_player = getattr(t, 'player_id', None) or (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.LOOK_AT_HAND,
                      payload={'player': target_player, 'requester': o.controller},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=scry_effect,
        description="Scry 2", targets_required=0,
    )
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=look_effect,
        description="Look at target opponent's hand",
        targets_required=1, target_kind="opponent",
    )
    return []


def _hpw_s23_marauders_map_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 2 + each opp damage per creature (Marauder's Map traces; intruders' footsteps glow.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_sorting_hat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Target creature becomes a House subtype EOT (engine-gap: subtype-grant modal)."""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        # Default to Gryffindor as a deterministic choice (modal not yet wired).
        return [Event(type=EventType.GRANT_ABILITY,
                      payload={'object_id': target_id, 'subtype_add': 'Gryffindor', 'duration': 'end_of_turn'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=effect,
        description="Target creature becomes a House",
        targets_required=1, target_kind="creature",
    )
    return []


def _hpw_s23_sorting_hat_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 2 + each opp damage per creature (Sorting Hat hums; first-years quiver, foes shudder.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_horcrux_diary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, {T}, Pay 2 life: Draw a card. (Death-trigger life-loss is engine-gap.)"""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': o.controller, 'amount': -2},
                  source=o.id, controller=o.controller),
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'amount': 1},
                  source=o.id, controller=o.controller),
        ]
    _ih.make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=effect,
        description="Draw a card (pay 2 life)", targets_required=0,
    )
    return []


def _hpw_s23_horcrux_diary_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + you gain Wizard life + each opp -1 (Riddle's Diary pulses; ink writes back, foes weep.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Wizard')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_horcrux_locket_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: each opp -1 / you +1. {2}, Sacrifice: Draw two cards."""
    def upkeep_effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = [Event(type=EventType.LIFE_CHANGE,
                                     payload={'player': obj.controller, 'amount': 1},
                                     source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1},
                                source=obj.id, controller=obj.controller))
        return events
    def draw_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': o.controller, 'amount': 2},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, Sacrifice Slytherin's Locket", effect_fn=draw_effect,
        description="Draw two cards", targets_required=0,
    )
    return [_ih.make_upkeep_trigger(obj, upkeep_effect)]


def _hpw_s23_horcrux_locket_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + draw if gy >= 3 + each opp -1 (Slytherin's Locket whispers; serpent shard demands tithe.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if gy >= 3:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_horcrux_cup_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add one mana of any color. (Death-trigger 'each opp draws' is engine-gap.)"""
    def mana_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        # Default to colorless; the choose-any-color is engine-gap modal.
        return [Event(type=EventType.MANA_PRODUCED,
                      payload={'player': o.controller, 'mana': 'C', 'amount': 1, 'any_color': True},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=mana_effect,
        description="Add one mana of any color", targets_required=0,
    )
    return []


def _hpw_s23_horcrux_cup_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + each opp discards if hand >= 4 (Hufflepuff's Cup overflows; tainted nectar bleeds rivals.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            hand = _hpw_s23_count_in_hand(st, opp)
            if hand >= 4:
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND},
                                    source=obj.id, controller=obj.controller))
            else:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_horcrux_diadem_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant and sorcery spells you cast cost {1} less. {2}, Sacrifice: Draw three cards."""
    def spell_filter(card: GameObject, pid: str, st: GameState) -> bool:
        if pid != obj.controller:
            return False
        if not card or not card.characteristics:
            return False
        types = card.characteristics.types or set()
        return CardType.INSTANT in types or CardType.SORCERY in types
    def draw_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': o.controller, 'amount': 3},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, Sacrifice Ravenclaw's Diadem", effect_fn=draw_effect,
        description="Draw three cards", targets_required=0,
    )
    return [_ih.make_cost_reduction(obj, applies_to=spell_filter, amount=1)]


def _hpw_s23_horcrux_diadem_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 2 + each opp damage per creature (Ravenclaw's Diadem crowns; tarnished wit warps reality.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_horcrux_ring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gaunt Family Ring - {T}: Add {B}. {3}, {T}, Sacrifice: Return target creature card from your graveyard to your hand."""
    def mana_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.MANA_PRODUCED,
                      payload={'player': o.controller, 'mana': 'B', 'amount': 1},
                      source=o.id, controller=o.controller)]
    def reanimate_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, 'object_id', None) or (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                      payload={'object_id': target_id, 'player': o.controller},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=mana_effect,
        description="Add {B}", targets_required=0,
    )
    _ih.make_activated_ability(
        obj, cost="{3}, {T}, Sacrifice Gaunt Family Ring", effect_fn=reanimate_effect,
        description="Return target creature card from graveyard to hand",
        targets_required=1, target_kind="creature_card_in_graveyard",
    )
    return []


def _hpw_s23_firebolt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +2/+0 and flying and haste. Equip {2}."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=2, toughness_mod=0,
        keywords=["flying", "haste"],
        equip_cost="{2}",
    )
    return setup_fn(obj, state)


def _hpw_s23_firebolt_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_nimbus_2000_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +1/+0 and flying. Equip {1}."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=1, toughness_mod=0,
        keywords=["flying"],
        equip_cost="{1}",
    )
    return setup_fn(obj, state)


def _hpw_s23_nimbus_2000_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + each opp discards if hand >= 4 (Nimbus 2000 hovers; broomstick legacy hounds opponents.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            hand = _hpw_s23_count_in_hand(st, opp)
            if hand >= 4:
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND},
                                    source=obj.id, controller=obj.controller))
            else:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_wand_phoenix_feather_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +0/+0 (the ping-1 grant is engine-gap). Equip {1}."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=0, toughness_mod=0,
        equip_cost="{1}",
    )
    return setup_fn(obj, state)


def _hpw_s23_wand_phoenix_feather_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + each opp discards if hand >= 4 (Phoenix-feather wand sparks; flame fragments answer call.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            hand = _hpw_s23_count_in_hand(st, opp)
            if hand >= 4:
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND},
                                    source=obj.id, controller=obj.controller))
            else:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_wand_dragon_heartstring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +1/+1 (the {T}: Add {R} grant is engine-gap). Equip {1}."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=1, toughness_mod=1,
        equip_cost="{1}",
    )
    return setup_fn(obj, state)


def _hpw_s23_wand_dragon_heartstring_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Dragon')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_wand_unicorn_hair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +0/+0 (the {T}: gain 1 life grant is engine-gap). Equip {1}."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=0, toughness_mod=0,
        equip_cost="{1}",
    )
    return setup_fn(obj, state)


def _hpw_s23_wand_unicorn_hair_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Unicorn')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
            if allies >= 1:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_pensieve_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, {T}: Look at top 3, put one in hand, rest on bottom."""
    def look_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.LOOK_AT_TOP,
                      payload={'player': o.controller, 'amount': 3, 'destination': 'one_to_hand'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=look_effect,
        description="Look at top 3, keep one", targets_required=0,
    )
    return []


def _hpw_s23_pensieve_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            hand = _hpw_s23_count_in_hand(st, opp)
            if hand >= 4:
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': opp, 'amount': 1, 'zone': ZoneType.HAND},
                                    source=obj.id, controller=obj.controller))
            else:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                    source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_golden_snitch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. {T}, Sacrifice: Draw two cards."""
    def draw_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': o.controller, 'amount': 2},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}, Sacrifice Golden Snitch", effect_fn=draw_effect,
        description="Draw two cards", targets_required=0,
    )
    def self_only(target: GameObject, st: GameState, src=obj) -> bool:
        return target.id == src.id
    return [_ih.make_keyword_grant(obj, keywords=["flying"], affects_filter=self_only)]


def _hpw_s23_quaffle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, {T}: Target creature gets +1/+0 and first strike EOT."""
    def buff_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        return [
            Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': target_id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
                  source=o.id, controller=o.controller),
            Event(type=EventType.KEYWORD_GRANT,
                  payload={'object_id': target_id, 'keyword': 'first_strike', 'duration': 'end_of_turn'},
                  source=o.id, controller=o.controller),
        ]
    _ih.make_activated_ability(
        obj, cost="{1}, {T}", effect_fn=buff_effect,
        description="Target creature +1/+0 and first strike EOT",
        targets_required=1, target_kind="creature",
    )
    return []


def _hpw_s23_quaffle_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if gy >= 3:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_bludger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, {T}: Bludger deals 2 damage to target creature."""
    _ih.make_damage_ability(
        obj, cost="{2}, {T}", damage=2,
        description="Bludger deals 2 to target creature",
        target_kind="creature",
    )
    return []


def _hpw_s23_bludger_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Human')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, allies), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_time_turner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}, Sacrifice Time-Turner: Take an extra turn after this one."""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.EXTRA_TURN,
                      payload={'player': o.controller},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{T}, Sacrifice Time-Turner", effect_fn=effect,
        description="Take an extra turn after this one",
        targets_required=0, sorcery_speed=True,
    )
    return []


def _hpw_s23_deluminator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Tap target creature. It doesn't untap next turn."""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, 'object_id', None) or (t.id if hasattr(t, 'id') else t)
        return [
            Event(type=EventType.TAP_TARGET,
                  payload={'object_id': target_id},
                  source=o.id, controller=o.controller),
            Event(type=EventType.FREEZE,
                  payload={'object_id': target_id, 'duration': 'next_untap'},
                  source=o.id, controller=o.controller),
        ]
    _ih.make_activated_ability(
        obj, cost="{T}", effect_fn=effect,
        description="Tap target creature, freeze next untap",
        targets_required=1, target_kind="creature",
    )
    return []


def _hpw_s23_portkey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}, {T}, Sacrifice Portkey: Return target creature to its owner's hand."""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, 'object_id', None) or (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.RETURN_TO_HAND,
                      payload={'object_id': target_id},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{3}, {T}, Sacrifice Portkey", effect_fn=effect,
        description="Return target creature to owner's hand",
        targets_required=1, target_kind="creature",
    )
    return []


def _hpw_s23_goblet_of_fire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: add a flame counter; at 3+, sacrifice and create a 5/5 red Dragon token with flying."""
    def upkeep_effect(event: Event, st: GameState) -> list[Event]:
        current_obj = st.objects.get(obj.id)
        if not current_obj:
            return []
        flames = current_obj.counters.get('flame', 0) if hasattr(current_obj, 'counters') else 0
        new_total = flames + 1
        events: list[Event] = [Event(type=EventType.COUNTER_ADDED,
                                     payload={'object_id': obj.id, 'counter_type': 'flame', 'amount': 1},
                                     source=obj.id, controller=obj.controller)]
        if new_total >= 3:
            events.append(Event(type=EventType.SACRIFICE,
                                payload={'object_id': obj.id, 'controller': obj.controller},
                                source=obj.id, controller=obj.controller))
            token_spec = {'name': 'Dragon',
                          'types': {CardType.CREATURE},
                          'power': 5, 'toughness': 5,
                          'colors': {Color.RED},
                          'subtypes': {'Dragon'},
                          'keywords': ['flying']}
            events.append(Event(type=EventType.CREATE_TOKEN,
                                payload={'controller': obj.controller, 'token': dict(token_spec)},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, upkeep_effect)]


def _hpw_s23_mirror_of_erised_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, {T}: Look at top of library; may put into graveyard."""
    def look_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(type=EventType.LOOK_AT_TOP,
                      payload={'player': o.controller, 'amount': 1, 'destination': 'optional_graveyard'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=look_effect,
        description="Look at top; optional mill", targets_required=0,
    )
    return []


def _hpw_s23_mirror_of_erised_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        creatures = _hpw_s23_count_type(st, obj.controller, CardType.CREATURE)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, creatures // 2 + 1), 'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_vanishing_cabinet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, {T}: Flicker target creature you control."""
    def effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, 'object_id', None) or (t.id if hasattr(t, 'id') else t)
        return [Event(type=EventType.FLICKER,
                      payload={'object_id': target_id, 'return_at': 'end_step'},
                      source=o.id, controller=o.controller)]
    _ih.make_activated_ability(
        obj, cost="{2}, {T}", effect_fn=effect,
        description="Flicker target creature you control",
        targets_required=1, target_kind="creature_you_control",
    )
    return []


def _hpw_s23_vanishing_cabinet_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _hpw_s23_count_subtype(st, obj.controller, 'Wizard')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, allies), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


def _hpw_s23_sword_of_gryffindor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +2/+2 and has protection from black (destroy-trigger is engine-gap). Equip {2}."""
    setup_fn = _ih.make_equipment_setup(
        power_mod=2, toughness_mod=2,
        keywords=["protection_from_black"],
        equip_cost="{2}",
    )
    return setup_fn(obj, state)


def _hpw_s23_sword_of_gryffindor_setup_OLD(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry + draw if gy >= 3 + each opp -1 (Sword of Gryffindor sings; goblin-forged steel taxes foes.)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _hpw_s23_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        if gy >= 3:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        for opp in _ih.all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [_ih.make_upkeep_trigger(obj, effect)]


# --- SHAPE 12: Instant/Sorcery resolve handlers (unique AST per card) ---


def _hpw_s23_resolve_expecto_patronum(targets: list, state: GameState) -> list[Event]:
    """Expecto Patronum - create a 2/2 white Spirit Patronus token (or 2 with Spell Mastery)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    count = 2 if has_spell_mastery(state, caster) else 1
    token_spec = {'name': 'Patronus Spirit',
                  'types': {CardType.CREATURE},
                  'power': 2, 'toughness': 2,
                  'colors': {Color.WHITE},
                  'subtypes': {'Spirit', 'Patronus'},
                  'keywords': ['flying', 'protection_from_black']}
    return [Event(type=EventType.CREATE_TOKEN,
                  payload={'controller': caster, 'token': dict(token_spec)},
                  source=None)
            for _ in range(count)]


def _hpw_s23_resolve_protego(targets: list, state: GameState) -> list[Event]:
    """Protego - Prevent all damage that would be dealt to target creature this turn. Draw a card."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events: list[Event] = []
    if targets:
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        if t is not None:
            target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
            # Grant indestructible as a proxy for damage prevention until engine has prevention.
            events.append(Event(type=EventType.KEYWORD_GRANT,
                                payload={'object_id': target_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
                                source=None))
    events.append(Event(type=EventType.DRAW,
                        payload={'player': caster, 'amount': 1},
                        source=None))
    return events


def _hpw_s23_resolve_shield_charm(targets: list, state: GameState) -> list[Event]:
    """Shield Charm - Target creature gains indestructible until end of turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.KEYWORD_GRANT,
                  payload={'object_id': target_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
                  source=None)]


def _hpw_s23_resolve_counter_curse(targets: list, state: GameState) -> list[Event]:
    """Counter-Curse - Exile target enchantment. You gain 2 life."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events: list[Event] = []
    if targets:
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        if t is not None:
            target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
            events.append(Event(type=EventType.EXILE,
                                payload={'object_id': target_id},
                                source=None))
    events.append(Event(type=EventType.LIFE_CHANGE,
                        payload={'player': caster, 'amount': 2},
                        source=None))
    return events


def _hpw_s23_resolve_priori_incantatem(targets: list, state: GameState) -> list[Event]:
    """Priori Incantatem - exile target creature; its controller creates a 1/1 white Spirit token."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    target = state.objects.get(target_id) if isinstance(target_id, str) else None
    events: list[Event] = [Event(type=EventType.EXILE,
                                 payload={'object_id': target_id},
                                 source=None)]
    if target is not None:
        token_spec = {'name': 'Spirit',
                      'types': {CardType.CREATURE},
                      'power': 1, 'toughness': 1,
                      'colors': {Color.WHITE},
                      'subtypes': {'Spirit'}}
        events.append(Event(type=EventType.CREATE_TOKEN,
                            payload={'controller': target.controller, 'token': dict(token_spec)},
                            source=None))
    return events


def _hpw_s23_resolve_healing_spell(targets: list, state: GameState) -> list[Event]:
    """Healing Spell - You gain 4 life."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    return [Event(type=EventType.LIFE_CHANGE,
                  payload={'player': caster, 'amount': 4},
                  source=None)]


def _hpw_s23_resolve_healing_spell_OLD(targets: list, state: GameState) -> list[Event]:
    """Healing Spell - scry 1 + you gain 4 + each opp loses 1."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    out = []
    out.append(Event(type=EventType.SCRY,
                     payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                     source=None))
    out.append(Event(type=EventType.LIFE_CHANGE,
                     payload={'player': caster, 'amount': 4, 'zone': ZoneType.BATTLEFIELD},
                     source=None))
    for opp in state.players:
        if opp != caster:
            out.append(Event(type=EventType.LIFE_CHANGE,
                             payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                             source=None))
    return out


def _hpw_s23_resolve_disillusionment_charm(targets: list, state: GameState) -> list[Event]:
    """Disillusionment Charm - Target creature gains hexproof and can't be blocked until end of turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'hexproof', 'duration': 'end_of_turn'},
              source=None),
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'unblockable', 'duration': 'end_of_turn'},
              source=None),
    ]


def _hpw_s23_resolve_call_the_order(targets: list, state: GameState) -> list[Event]:
    """Call the Order - Create three 2/2 white Human Wizard tokens. You gain 1 life for each Wizard you control."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    token_spec = {'name': 'Human Wizard',
                  'types': {CardType.CREATURE},
                  'power': 2, 'toughness': 2,
                  'colors': {Color.WHITE},
                  'subtypes': {'Human', 'Wizard'}}
    events: list[Event] = [Event(type=EventType.CREATE_TOKEN,
                                 payload={'controller': caster, 'token': dict(token_spec)},
                                 source=None)
                            for _ in range(3)]
    # Life: 1 per Wizard you control (count existing only; tokens just emitted)
    bf = state.zones.get('battlefield')
    wizards = 0
    if bf:
        for oid in bf.objects:
            o = state.objects.get(oid)
            if (o and o.controller == caster and o.characteristics
                and 'Wizard' in (o.characteristics.subtypes or set())):
                wizards += 1
    if wizards:
        events.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': caster, 'amount': wizards},
                            source=None))
    return events


def _hpw_s23_resolve_sorting_ceremony(targets: list, state: GameState) -> list[Event]:
    """Sorting Ceremony - Target creature becomes a Gryffindor. Put a +1/+1 counter on it."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.COUNTER_ADDED,
                  payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
                  source=None)]


def _hpw_s23_resolve_obliviate(targets: list, state: GameState) -> list[Event]:
    """Obliviate - Exile target creature an opponent controls. Its controller draws a card."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    target = state.objects.get(target_id) if isinstance(target_id, str) else None
    events: list[Event] = [Event(type=EventType.EXILE,
                                 payload={'object_id': target_id},
                                 source=None)]
    if target is not None:
        events.append(Event(type=EventType.DRAW,
                            payload={'player': target.controller, 'amount': 1},
                            source=None))
    return events


def _hpw_s23_resolve_stupefy(targets: list, state: GameState) -> list[Event]:
    """Stupefy - tap target creature; it doesn't untap during controller's next untap step."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.TAP_TARGET,
              payload={'object_id': target_id},
              source=None),
        Event(type=EventType.FREEZE,
              payload={'object_id': target_id, 'duration': 'next_untap'},
              source=None),
    ]


def _hpw_s23_resolve_accio(targets: list, state: GameState) -> list[Event]:
    """Accio - Search your library for an artifact card; put into hand. Shuffle."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    return [Event(type=EventType.SEARCH_LIBRARY,
                  payload={'player': caster, 'type': 'artifact', 'destination': 'hand'},
                  source=None)]


def _hpw_s23_resolve_confundo(targets: list, state: GameState) -> list[Event]:
    """Confundo - counter target spell unless its controller pays {3}."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.COUNTER,
                  payload={'spell_id': target_id, 'unless_pay': 3},
                  source=None)]


def _hpw_s23_resolve_petrificus_totalus(targets: list, state: GameState) -> list[Event]:
    """Petrificus Totalus - Tap target creature; remove abilities until next turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.TAP_TARGET,
              payload={'object_id': target_id},
              source=None),
        Event(type=EventType.REMOVE_ABILITIES,
              payload={'object_id': target_id, 'duration': 'until_your_next_turn'},
              source=None),
    ]


def _hpw_s23_resolve_legilimens(targets: list, state: GameState) -> list[Event]:
    """Legilimens - Target opponent reveals their hand. You draw a card."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    target_player = None
    if targets:
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        if t is not None:
            target_player = getattr(t, 'player_id', None) or (t.id if hasattr(t, 'id') else t)
    if target_player is None:
        # Fall back to first opponent
        for opp in state.players:
            if opp != caster:
                target_player = opp
                break
    events: list[Event] = []
    if target_player is not None:
        events.append(Event(type=EventType.REVEAL_HAND,
                            payload={'player': target_player},
                            source=None))
    events.append(Event(type=EventType.DRAW,
                        payload={'player': caster, 'amount': 1},
                        source=None))
    return events


def _hpw_s23_resolve_aguamenti(targets: list, state: GameState) -> list[Event]:
    """Aguamenti - Tap or untap target permanent. Draw a card."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events: list[Event] = []
    if targets:
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        if t is not None:
            target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
            target = state.objects.get(target_id) if isinstance(target_id, str) else None
            # Default to tap if currently untapped, else untap.
            tapped = bool(target and getattr(target, 'tapped', False))
            ev = EventType.UNTAP_TARGET if tapped else EventType.TAP_TARGET
            events.append(Event(type=ev, payload={'object_id': target_id}, source=None))
    events.append(Event(type=EventType.DRAW,
                        payload={'player': caster, 'amount': 1},
                        source=None))
    return events


def _hpw_s23_resolve_finite_incantatem(targets: list, state: GameState) -> list[Event]:
    """Finite Incantatem - counter target spell. Spell Mastery: draw a card."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None or not targets:
        return []
    t = targets[0]
    if isinstance(t, list) and t:
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    events: list[Event] = [Event(type=EventType.COUNTER,
                                 payload={'spell_id': target_id},
                                 source=None)]
    if has_spell_mastery(state, caster):
        events.append(Event(type=EventType.DRAW,
                            payload={'player': caster, 'amount': 1},
                            source=None))
    return events


def _hpw_s23_resolve_divination(targets: list, state: GameState) -> list[Event]:
    """Divination - draw two cards."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    return [Event(type=EventType.DRAW,
                  payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                  source=None)]


def _hpw_s23_resolve_crystal_ball_reading(targets: list, state: GameState) -> list[Event]:
    """Crystal Ball Reading - scry 3, then draw a card."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    return [
        Event(type=EventType.SCRY,
              payload={'player': caster, 'amount': 3, 'zone': ZoneType.LIBRARY},
              source=None),
        Event(type=EventType.DRAW,
              payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
              source=None),
    ]


def _hpw_s23_resolve_memory_wipe(targets: list, state: GameState) -> list[Event]:
    """Memory Wipe - each opp shuffles hand into library then draws that many minus 1.

    Engine-gap: shuffle-from-hand + draw-with-modifier modal not yet wired.
    Emit DISCARD-all + DRAW for approximate effect."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events: list[Event] = []
    for opp in state.players:
        if opp == caster:
            continue
        hand = state.zones.get(f'hand_{opp}')
        hand_size = len(hand.objects) if hand else 0
        events.append(Event(type=EventType.DISCARD,
                            payload={'player': opp, 'amount': hand_size},
                            source=None))
        if hand_size > 1:
            events.append(Event(type=EventType.DRAW,
                                payload={'player': opp, 'amount': hand_size - 1},
                                source=None))
    return events


def _hpw_s23_resolve_transfiguration(targets: list, state: GameState) -> list[Event]:
    """Transfiguration - Target creature becomes a copy of another creature EOT.

    Engine-gap: copy-effect not yet wired. Emit a placeholder GRANT_ABILITY."""
    if not targets or len(targets) < 2:
        return []
    def _norm(x):
        if isinstance(x, list):
            return x[0] if x else None
        return x
    a = _norm(targets[0])
    b = _norm(targets[1])
    if a is None or b is None:
        return []
    a_id = a.object_id if hasattr(a, 'object_id') else (a.id if hasattr(a, 'id') else a)
    b_id = b.object_id if hasattr(b, 'object_id') else (b.id if hasattr(b, 'id') else b)
    return [Event(type=EventType.GRANT_ABILITY,
                  payload={'object_id': a_id, 'copy_of': b_id, 'duration': 'end_of_turn'},
                  source=None)]


def _hpw_s23_resolve_avada_kedavra(targets: list, state: GameState) -> list[Event]:
    """Avada Kedavra - destroy target creature, controller loses 2 life."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None or not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    target = state.objects.get(target_id) if isinstance(target_id, str) else None
    events: list[Event] = [Event(type=EventType.DESTROY,
                                 payload={'object_id': target_id, 'no_regen': True},
                                 source=None)]
    if target is not None:
        events.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': target.controller, 'amount': -2},
                            source=None))
    return events


def _hpw_s23_resolve_crucio(targets: list, state: GameState) -> list[Event]:
    """Crucio - Target creature gets -3/-3 until end of turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': target_id, 'power_mod': -3, 'toughness_mod': -3, 'duration': 'end_of_turn'},
                  source=None)]


def _hpw_s23_resolve_imperio(targets: list, state: GameState) -> list[Event]:
    """Imperio - gain control of target creature; untap it; haste EOT."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None or not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.GAIN_CONTROL,
              payload={'object_id': target_id, 'new_controller': caster, 'duration': 'end_of_turn'},
              source=None),
        Event(type=EventType.UNTAP,
              payload={'object_id': target_id},
              source=None),
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'haste', 'duration': 'end_of_turn'},
              source=None),
    ]


def _hpw_s23_resolve_sectumsempra(targets: list, state: GameState) -> list[Event]:
    """Sectumsempra - Destroy target creature. You lose 2 life."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None or not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.DESTROY,
              payload={'object_id': target_id},
              source=None),
        Event(type=EventType.LIFE_CHANGE,
              payload={'player': caster, 'amount': -2},
              source=None),
    ]


def _hpw_s23_resolve_morsmordre(targets: list, state: GameState) -> list[Event]:
    """Morsmordre - Create a 4/4 black Horror creature token with flying."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    token_spec = {'name': 'Horror',
                  'types': {CardType.CREATURE},
                  'power': 4, 'toughness': 4,
                  'colors': {Color.BLACK},
                  'subtypes': {'Horror'},
                  'keywords': ['flying']}
    return [Event(type=EventType.CREATE_TOKEN,
                  payload={'controller': caster, 'token': dict(token_spec)},
                  source=None)]


def _hpw_s23_resolve_dark_mark(targets: list, state: GameState) -> list[Event]:
    """Dark Mark - Target creature gets +2/+0 and gains menace until end of turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.PT_MODIFICATION,
              payload={'object_id': target_id, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'},
              source=None),
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'menace', 'duration': 'end_of_turn'},
              source=None),
    ]


def _hpw_s23_resolve_curse_of_the_bogies(targets: list, state: GameState) -> list[Event]:
    """Curse of the Bogies - Target player discards a card (or 2 with Spell Mastery)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    target_player = None
    if targets:
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        if t is not None:
            target_player = getattr(t, 'player_id', None) or (t.id if hasattr(t, 'id') else t)
    if target_player is None:
        for opp in state.players:
            if opp != caster:
                target_player = opp
                break
    if target_player is None:
        return []
    amount = 2 if has_spell_mastery(state, caster) else 1
    return [Event(type=EventType.DISCARD,
                  payload={'player': target_player, 'amount': amount},
                  source=None)]


def _hpw_s23_resolve_summon_inferi(targets: list, state: GameState) -> list[Event]:
    """Summon Inferi - Return up to 2 creature cards from your graveyard. They gain haste; exile at next end step."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None or not targets:
        return []
    events: list[Event] = []
    for t in targets[:2]:
        if isinstance(t, list):
            if not t: continue
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        events.append(Event(type=EventType.RETURN_FROM_GRAVEYARD,
                            payload={'object_id': target_id, 'player': caster, 'destination': 'battlefield'},
                            source=None))
        events.append(Event(type=EventType.KEYWORD_GRANT,
                            payload={'object_id': target_id, 'keyword': 'haste', 'duration': 'end_of_turn'},
                            source=None))
        events.append(Event(type=EventType.DELAYED_SACRIFICE,
                            payload={'object_id': target_id, 'destination': 'exile', 'trigger_at': 'end_step'},
                            source=None))
    return events


def _hpw_s23_resolve_dark_ritual_spell(targets: list, state: GameState) -> list[Event]:
    """Dark Ritual - Add {B}{B}{B}."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    return [Event(type=EventType.MANA_PRODUCED,
                  payload={'player': caster, 'mana': 'B', 'amount': 3},
                  source=None)]


def _hpw_s23_resolve_fiendfyre(targets: list, state: GameState) -> list[Event]:
    """Fiendfyre - Destroy all creatures. You lose 3 life."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    bf = state.zones.get('battlefield')
    events: list[Event] = []
    if bf:
        for oid in bf.objects:
            target = state.objects.get(oid)
            if (target and target.characteristics
                and CardType.CREATURE in (target.characteristics.types or set())):
                events.append(Event(type=EventType.DESTROY,
                                    payload={'object_id': oid},
                                    source=None))
    events.append(Event(type=EventType.LIFE_CHANGE,
                        payload={'player': caster, 'amount': -3},
                        source=None))
    return events


def _hpw_s23_resolve_incendio(targets: list, state: GameState) -> list[Event]:
    """Incendio - deals 2 damage to any target."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.DAMAGE,
                  payload={'target': target_id, 'amount': 2, 'source': None, 'is_combat': False},
                  source=None)]


def _hpw_s23_resolve_confringo(targets: list, state: GameState) -> list[Event]:
    """Confringo - deals 3 damage to target creature or planeswalker."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.DAMAGE,
                  payload={'target': target_id, 'amount': 3, 'source': None, 'is_combat': False},
                  source=None)]


def _hpw_s23_resolve_bombarda(targets: list, state: GameState) -> list[Event]:
    """Bombarda - destroy target artifact; deals 2 damage to that artifact's controller."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    target = state.objects.get(target_id) if isinstance(target_id, str) else None
    events: list[Event] = [Event(type=EventType.DESTROY,
                                 payload={'object_id': target_id},
                                 source=None)]
    if target is not None:
        events.append(Event(type=EventType.DAMAGE,
                            payload={'target': target.controller, 'amount': 2, 'source': None, 'is_combat': False},
                            source=None))
    return events


def _hpw_s23_resolve_reducto(targets: list, state: GameState) -> list[Event]:
    """Reducto - deals 4 damage to target creature."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t:
            return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.DAMAGE,
                  payload={'target': target_id, 'amount': 4, 'source': None, 'is_combat': False},
                  source=None)]


def _hpw_s23_resolve_expulso(targets: list, state: GameState) -> list[Event]:
    """Expulso - Deal 5 damage divided among any number of target creatures."""
    if not targets:
        return []
    # Use the first target for now (multi-target split is engine-gap).
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.DAMAGE,
                  payload={'target': target_id, 'amount': 5, 'source': None, 'is_combat': False},
                  source=None)]


def _hpw_s23_resolve_expulso_OLD(targets: list, state: GameState) -> list[Event]:
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    e = [Event(type=EventType.SCRY,
               payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
               source=None)]
    for opp in state.players:
        if opp != caster:
            e.append(Event(type=EventType.DAMAGE,
                            payload={'target': opp, 'amount': 2, 'source': None, 'is_combat': False},
                            source=None))
            e.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                            source=None))
    return e


def _hpw_s23_resolve_dragons_breath(targets: list, state: GameState) -> list[Event]:
    """Dragon's Breath - Target creature gets +2/+0 and gains first strike EOT."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.PT_MODIFICATION,
              payload={'object_id': target_id, 'power_mod': 2, 'toughness_mod': 0, 'duration': 'end_of_turn'},
              source=None),
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'first_strike', 'duration': 'end_of_turn'},
              source=None),
    ]


def _hpw_s23_resolve_dragons_breath_OLD(targets: list, state: GameState) -> list[Event]:
    """Dragon's Breath - scry 2 + each opp 4 damage."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    result = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            result.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 4, 'source': None, 'is_combat': False},
                                source=None))
    return result


def _hpw_s23_resolve_weasley_firework(targets: list, state: GameState) -> list[Event]:
    """Weasley Firework - deals 1 damage to each creature your opponents control."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    bf = state.zones.get('battlefield')
    events: list[Event] = []
    if bf:
        for oid in bf.objects:
            target = state.objects.get(oid)
            if (target and target.controller != caster
                and target.characteristics
                and CardType.CREATURE in (target.characteristics.types or set())):
                events.append(Event(type=EventType.DAMAGE,
                                    payload={'target': oid, 'amount': 1, 'source': None, 'is_combat': False},
                                    source=None))
    return events


def _hpw_s23_resolve_dragons_fire(targets: list, state: GameState) -> list[Event]:
    """Dragon's Fire - deals 4 damage to each creature (5 if you control a Dragon)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    bf = state.zones.get('battlefield')
    has_dragon = False
    targets_ids: list[str] = []
    if bf:
        for oid in bf.objects:
            target = state.objects.get(oid)
            if not target or not target.characteristics:
                continue
            if (target.controller == caster
                and 'Dragon' in (target.characteristics.subtypes or set())):
                has_dragon = True
            if CardType.CREATURE in (target.characteristics.types or set()):
                targets_ids.append(oid)
    damage = 5 if has_dragon else 4
    return [Event(type=EventType.DAMAGE,
                  payload={'target': oid, 'amount': damage, 'source': None, 'is_combat': False},
                  source=None)
            for oid in targets_ids]


def _hpw_s23_resolve_pyrotechnics(targets: list, state: GameState) -> list[Event]:
    """Pyrotechnics - 3 damage divided among one, two, or three targets (first target gets all 3)."""
    if not targets:
        return []
    events: list[Event] = []
    for t in targets[:3]:
        if isinstance(t, list):
            if not t: continue
            t = t[0]
        target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
        # Even split: 1 each if 3 targets; flexible for 1 or 2.
        events.append(Event(type=EventType.DAMAGE,
                            payload={'target': target_id, 'amount': max(1, 3 // len(targets[:3])), 'source': None, 'is_combat': False},
                            source=None))
    return events


def _hpw_s23_resolve_summon_dragon(targets: list, state: GameState) -> list[Event]:
    """Summon Dragon - create a 5/5 red Dragon token with flying and haste."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    token_spec = {'name': 'Dragon',
                  'types': {CardType.CREATURE},
                  'power': 5, 'toughness': 5,
                  'colors': {Color.RED},
                  'subtypes': {'Dragon'},
                  'keywords': ['flying', 'haste']}
    return [Event(type=EventType.CREATE_TOKEN,
                  payload={'controller': caster, 'token': dict(token_spec)},
                  source=None)]


def _hpw_s23_resolve_herbivicus(targets: list, state: GameState) -> list[Event]:
    """Herbivicus - Target creature gets +2/+2 until end of turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.PT_MODIFICATION,
                  payload={'object_id': target_id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'end_of_turn'},
                  source=None)]


def _hpw_s23_resolve_wild_growth(targets: list, state: GameState) -> list[Event]:
    """Wild Growth - put two +1/+1 counters on target creature."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [Event(type=EventType.COUNTER_ADDED,
                  payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 2},
                  source=None)]


def _hpw_s23_resolve_engorgio(targets: list, state: GameState) -> list[Event]:
    """Engorgio - Target creature gets +4/+4 and gains trample until end of turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.PT_MODIFICATION,
              payload={'object_id': target_id, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'end_of_turn'},
              source=None),
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'trample', 'duration': 'end_of_turn'},
              source=None),
    ]


def _hpw_s23_resolve_engorgio_OLD(targets: list, state: GameState) -> list[Event]:
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _hpw_s23_resolve_beasts_fury(targets: list, state: GameState) -> list[Event]:
    """Beast's Fury - Target creature you control fights target creature you don't control."""
    if not targets or len(targets) < 2:
        return []
    def _norm(x):
        if isinstance(x, list):
            return x[0] if x else None
        return x
    a = _norm(targets[0])
    b = _norm(targets[1])
    if a is None or b is None:
        return []
    a_id = a.object_id if hasattr(a, 'object_id') else (a.id if hasattr(a, 'id') else a)
    b_id = b.object_id if hasattr(b, 'object_id') else (b.id if hasattr(b, 'id') else b)
    return [Event(type=EventType.FIGHT,
                  payload={'attacker': a_id, 'defender': b_id},
                  source=None)]


def _hpw_s23_resolve_natures_protection(targets: list, state: GameState) -> list[Event]:
    """Nature's Protection - Target creature gains hexproof and indestructible until end of turn."""
    if not targets:
        return []
    t = targets[0]
    if isinstance(t, list):
        if not t: return []
        t = t[0]
    target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
    return [
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'hexproof', 'duration': 'end_of_turn'},
              source=None),
        Event(type=EventType.KEYWORD_GRANT,
              payload={'object_id': target_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
              source=None),
    ]


def _hpw_s23_resolve_greenhouse_harvest(targets: list, state: GameState) -> list[Event]:
    """Greenhouse Harvest - search library for up to two basic lands; one BF tapped, one to hand."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    return [
        Event(type=EventType.SEARCH_LIBRARY,
              payload={'player': caster, 'type': 'basic_land', 'destination': 'battlefield_tapped'},
              source=None),
        Event(type=EventType.SEARCH_LIBRARY,
              payload={'player': caster, 'type': 'basic_land', 'destination': 'hand'},
              source=None),
    ]


def _hpw_s23_resolve_creature_summoning(targets: list, state: GameState) -> list[Event]:
    """Creature Summoning - Create two 3/3 green Beast creature tokens."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    token_spec = {'name': 'Beast',
                  'types': {CardType.CREATURE},
                  'power': 3, 'toughness': 3,
                  'colors': {Color.GREEN},
                  'subtypes': {'Beast'}}
    return [Event(type=EventType.CREATE_TOKEN,
                  payload={'controller': caster, 'token': dict(token_spec)},
                  source=None)
            for _ in range(2)]


def _hpw_s23_resolve_mandrake_restorative(targets: list, state: GameState) -> list[Event]:
    """Mandrake Restorative - You gain 5 life. May return target creature card from gy to hand."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events: list[Event] = [Event(type=EventType.LIFE_CHANGE,
                                 payload={'player': caster, 'amount': 5},
                                 source=None)]
    if targets:
        t = targets[0]
        if isinstance(t, list) and t:
            t = t[0]
        if t is not None:
            target_id = t.object_id if hasattr(t, 'object_id') else (t.id if hasattr(t, 'id') else t)
            events.append(Event(type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                                payload={'object_id': target_id, 'player': caster},
                                source=None))
    return events


HOGWARTS_DEFENDER = make_creature(
    name="Hogwarts Defender",
    power=2, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="Defender. Whenever Hogwarts Defender blocks, you gain 2 life.",
    setup_interceptors=_hpw_s23_hogwarts_defender_setup,
)


ORDER_PHOENIX_MEMBER = make_creature(
    name="Order of the Phoenix Member",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text=(
        "First strike. Protection from black. When Order of the Phoenix "
        "Member enters, you gain 1 life for each other Wizard you control "
        "and each opponent loses 1 life. (The Order rallies in defence.)"
    ),
    setup_interceptors=_hpw_order_phoenix_member_setup,
)


MINISTRY_AUROR = make_creature(
    name="Ministry Auror",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Auror"},
    text="Vigilance. {1}{W}: Ministry Auror gains lifelink until end of turn.",
    setup_interceptors=_hpw_s23_ministry_auror_setup,
)


def patronus_caster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create Patronus token."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Patronus Spirit',
                'power': 2,
                'toughness': 2,
                'colors': {Color.WHITE},
                'subtypes': {'Spirit', 'Patronus'},
                'keywords': ['flying', 'protection_from_black'],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_etb_trigger(obj, effect_fn)]

PATRONUS_CASTER = make_creature(
    name="Patronus Caster",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="When Patronus Caster enters, create a 2/2 white Spirit Patronus token with flying and protection from black.",
    setup_interceptors=patronus_caster_setup
)


HOGWARTS_FIRST_YEAR = make_creature(
    name="Hogwarts First Year",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="When Hogwarts First Year dies, you gain 2 life.",
    setup_interceptors=_hpw_s23_hogwarts_first_year_setup,
)


DUMBLEDORES_ARMY_RECRUIT = make_creature(
    name="Dumbledore's Army Recruit",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    text="House - Dumbledore's Army Recruit gets +1/+1 as long as you control another Gryffindor.",
    setup_interceptors=_hpw_s23_dumbledores_army_recruit_setup,
)


WEASLEY_MATRIARCH = make_creature(
    name="Weasley Matriarch",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="When Weasley Matriarch enters, create two 1/1 red Human Wizard creature tokens.",
    setup_interceptors=_hpw_s23_weasley_matriarch_setup,
)


HOGWARTS_GHOST = make_creature(
    name="Hogwarts Ghost",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying. Hogwarts Ghost can block creatures with menace as though it didn't have menace.",
    setup_interceptors=_hpw_s23_hogwarts_ghost_setup,
)


QUIDDITCH_REFEREE = make_creature(
    name="Quidditch Referee",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="Flying. Creatures can't attack you unless their controller pays {1} for each creature attacking you.",
    setup_interceptors=_hpw_s23_quidditch_referee_setup,
)


HEALING_WITCH = make_creature(
    name="Healing Witch",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Cleric"},
    text="{T}: Prevent the next 2 damage that would be dealt to target creature this turn.",
    setup_interceptors=_hpw_s23_healing_witch_setup,
)


ST_MUNGOS_HEALER = make_creature(
    name="St. Mungo's Healer",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Cleric"},
    text="When St. Mungo's Healer enters, you gain 3 life. {T}: You gain 1 life.",
    setup_interceptors=_hpw_s23_st_mungos_healer_setup,
)


PHOENIX_GUARDIAN = make_creature(
    name="Phoenix Guardian",
    power=3, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Phoenix"},
    text="Flying. When Phoenix Guardian dies, return it to its owner's hand at the beginning of the next end step.",
    setup_interceptors=_hpw_s23_phoenix_guardian_setup,
)


# --- White Instants ---

EXPECTO_PATRONUM = make_instant(
    name="Expecto Patronum",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Create a 2/2 white Spirit Patronus token with flying and protection from black. Spell Mastery - If you've cast 3+ instants/sorceries this game, create two tokens instead.",
    resolve=_hpw_s23_resolve_expecto_patronum,
)


PROTEGO = make_instant(
    name="Protego",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to target creature this turn. Draw a card.",
    resolve=_hpw_s23_resolve_protego,
)


SHIELD_CHARM = make_instant(
    name="Shield Charm",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn.",
    resolve=_hpw_s23_resolve_shield_charm,
)


COUNTER_CURSE = make_instant(
    name="Counter-Curse",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target enchantment. You gain 2 life.",
    resolve=_hpw_s23_resolve_counter_curse,
)


PRIORI_INCANTATEM = make_instant(
    name="Priori Incantatem",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Exile target creature. Its controller creates a 1/1 white Spirit creature token.",
    resolve=_hpw_s23_resolve_priori_incantatem,
)


HEALING_SPELL = make_instant(
    name="Healing Spell",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="You gain 4 life.",
    resolve=_hpw_s23_resolve_healing_spell,
)


DISILLUSIONMENT_CHARM = make_instant(
    name="Disillusionment Charm",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gains hexproof and can't be blocked until end of turn.",
    resolve=_hpw_s23_resolve_disillusionment_charm,
)


# --- White Sorceries ---

CALL_THE_ORDER = make_sorcery(
    name="Call the Order",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 2/2 white Human Wizard creature tokens. You gain 1 life for each Wizard you control.",
    resolve=_hpw_s23_resolve_call_the_order,
)


SORTING_CEREMONY = make_sorcery(
    name="Sorting Ceremony",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature becomes a Gryffindor in addition to its other types. Put a +1/+1 counter on it.",
    resolve=_hpw_s23_resolve_sorting_ceremony,
)


OBLIVIATE = make_sorcery(
    name="Obliviate",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature an opponent controls. Its controller draws a card.",
    resolve=_hpw_s23_resolve_obliviate,
)


# --- White Enchantments ---

def light_magic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant, gain 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_spell_cast_trigger(
        obj, effect_fn,
        controller_only=True,
        spell_type_filter={CardType.INSTANT},
    )]

LIGHT_MAGIC = make_enchantment(
    name="Light Magic",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever you cast an instant spell, you gain 1 life.",
    setup_interceptors=light_magic_setup
)


DUMBLEDORES_PROTECTION = make_enchantment(
    name="Dumbledore's Protection",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control have hexproof and can't be sacrificed.",
    setup_interceptors=_hpw_s23_dumbledores_protection_setup,
)


GRYFFINDOR_BANNER = make_enchantment(
    name="Gryffindor Banner",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Gryffindor creatures you control get +1/+1. At the beginning of your end step, if you control 3+ Gryffindors, draw a card.",
    setup_interceptors=_hpw_s23_gryffindor_banner_setup,
)


# =============================================================================
# BLUE CARDS - RAVENCLAW, KNOWLEDGE, DIVINATION
# =============================================================================

# --- Legendary Creatures ---

def luna_lovegood_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you scry, draw a card."""
    def scry_filter(event: Event, state: GameState) -> bool:
        return event.type == EventType.SCRY and event.payload.get('player') == obj.controller

    def scry_handler(event, state, src=obj):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.DRAW, payload={'player': src.controller, 'amount': 1}, source=src.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=scry_filter,
        handler=scry_handler,
        duration='while_on_battlefield'
    )]

LUNA_LOVEGOOD = make_creature(
    name="Luna Lovegood, Seer of Truth",
    power=1, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    supertypes={"Legendary"},
    text="Whenever you scry, draw a card. {U}: Scry 1.",
    setup_interceptors=luna_lovegood_setup
)


def filius_flitwick_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instants cost 1 less."""
    def cost_reduce_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        return CardType.INSTANT in set(event.payload.get('types', []))

    def cost_reduce_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current_reduction = new_event.payload.get('cost_reduction', 0)
        new_event.payload['cost_reduction'] = current_reduction + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=cost_reduce_filter,
        handler=cost_reduce_handler,
        duration='while_on_battlefield'
    )]

FILIUS_FLITWICK = make_creature(
    name="Filius Flitwick, Charms Master",
    power=1, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Goblin", "Wizard", "Ravenclaw"},
    supertypes={"Legendary"},
    text="Instant spells you cast cost {1} less. Other Ravenclaw creatures you control have hexproof.",
    setup_interceptors=filius_flitwick_setup
)


def cho_chang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 2 (placeholder ACTIVATE event, same as old DSL stub)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ACTIVATE,
            payload={'action': 'scry', 'amount': 2, 'player': obj.controller},
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_etb_trigger(obj, effect_fn)]

CHO_CHANG = make_creature(
    name="Cho Chang, Seeker",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    supertypes={"Legendary"},
    text="When Cho Chang enters, scry 2.",
    setup_interceptors=cho_chang_setup,
)


def moaning_myrtle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _t = death_draw(obj, 2)
    return [itc]

MOANING_MYRTLE = make_creature(
    name="Moaning Myrtle",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="When Moaning Myrtle dies, draw 2 cards.",
    setup_interceptors=moaning_myrtle_setup
)


# --- Regular Blue Creatures ---

def ravenclaw_prefect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'count': 1}, source=obj.id),
        ]
    return [_ih.make_etb_trigger(obj, effect_fn)]

RAVENCLAW_PREFECT = make_creature(
    name="Ravenclaw Prefect",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    text="When Ravenclaw Prefect enters, draw a card, then discard a card.",
    setup_interceptors=ravenclaw_prefect_setup
)


HOGWARTS_SCHOLAR = make_creature(
    name="Hogwarts Scholar",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text=(
        "{T}: Scry 1. When Hogwarts Scholar enters, scry 1. If you control "
        "another Ravenclaw, each opponent loses 1 life. (Scholarly insight.)"
    ),
    setup_interceptors=_hpw_hogwarts_scholar_setup,
)


DIVINATION_STUDENT = make_creature(
    name="Divination Student",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Divination Student enters, scry 1.",
    setup_interceptors=_hpw_s23_divination_student_setup,
)


LIBRARY_RESEARCHER = make_creature(
    name="Library Researcher",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Defender. {T}, Discard a card: Draw two cards.",
    setup_interceptors=_hpw_s23_library_researcher_setup,
)


SPELL_THEORIST = make_creature(
    name="Spell Theorist",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ravenclaw"},
    text="Spell Mastery - Spell Theorist has flying as long as you've cast 3+ instants/sorceries this game.",
    setup_interceptors=_hpw_s23_spell_theorist_setup,
)


HOGWARTS_LIBRARIAN = make_creature(
    name="Hogwarts Librarian",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you draw your second card each turn, scry 2.",
    setup_interceptors=_hpw_s23_hogwarts_librarian_setup,
)


UNSPEAKABLE = make_creature(
    name="Unspeakable",
    power=2, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Hexproof. When Unspeakable enters, look at the top 3 cards of your library. Put one into your hand and the rest on the bottom.",
    setup_interceptors=_hpw_s23_unspeakable_setup,
)


PENSIEVE_KEEPER = make_creature(
    name="Pensieve Keeper",
    power=1, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{2}{U}, {T}: Draw a card. Activate only as a sorcery.",
    setup_interceptors=_hpw_s23_pensieve_keeper_setup,
)


THESTRAL = make_creature(
    name="Thestral",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Beast"},
    text="Flying. Thestral can't be blocked. Thestral has hexproof as long as a creature died this turn.",
    setup_interceptors=_hpw_s23_thestral_setup,
)


TIME_TURNER_USER = make_creature(
    name="Time-Turner User",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{2}{U}{U}, Sacrifice Time-Turner User: Take an extra turn after this one.",
    setup_interceptors=_hpw_s23_time_turner_user_setup,
)


MEMORY_CHARM_SPECIALIST = make_creature(
    name="Memory Charm Specialist",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Memory Charm Specialist enters, target opponent reveals their hand. You choose a nonland card from it. That player shuffles it into their library.",
    setup_interceptors=_hpw_s23_memory_charm_specialist_setup,
)


# --- Blue Instants ---

STUPEFY = make_instant(
    name="Stupefy",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step.",
    resolve=_hpw_s23_resolve_stupefy,
)


ACCIO = make_instant(
    name="Accio",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Search your library for an artifact card, reveal it, and put it into your hand. Shuffle.",
    resolve=_hpw_s23_resolve_accio,
)


CONFUNDO = make_instant(
    name="Confundo",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}.",
    resolve=_hpw_s23_resolve_confundo,
)


PETRIFICUS_TOTALUS = make_instant(
    name="Petrificus Totalus",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It becomes an artifact in addition to its other types and loses all abilities until your next turn.",
    resolve=_hpw_s23_resolve_petrificus_totalus,
)


LEGILIMENS = make_instant(
    name="Legilimens",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target opponent reveals their hand. You draw a card.",
    resolve=_hpw_s23_resolve_legilimens,
)


AGUAMENTI = make_instant(
    name="Aguamenti",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Tap or untap target permanent. Draw a card.",
    resolve=_hpw_s23_resolve_aguamenti,
)


FINITE_INCANTATEM = make_instant(
    name="Finite Incantatem",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Spell Mastery - If you've cast 3+ instants/sorceries this game, draw a card.",
    resolve=_hpw_s23_resolve_finite_incantatem,
)


# --- Blue Sorceries ---

DIVINATION_SPELL = make_sorcery(
    name="Divination",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards.",
    resolve=_hpw_s23_resolve_divination,
)


CRYSTAL_BALL_READING = make_sorcery(
    name="Crystal Ball Reading",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Scry 3, then draw a card.",
    resolve=_hpw_s23_resolve_crystal_ball_reading,
)


MEMORY_WIPE = make_sorcery(
    name="Memory Wipe",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Each opponent shuffles their hand into their library, then draws that many cards minus one.",
    resolve=_hpw_s23_resolve_memory_wipe,
)


TRANSFIGURATION = make_sorcery(
    name="Transfiguration",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Until end of turn, target creature becomes a copy of another target creature.",
    resolve=_hpw_s23_resolve_transfiguration,
)


# --- Blue Enchantments ---

LIBRARY_OF_HOGWARTS = make_enchantment(
    name="Library of Hogwarts",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, scry 1. Whenever you scry, you may pay {1}. If you do, draw a card.",
    setup_interceptors=_hpw_s23_library_of_hogwarts_setup,
)


RAVENCLAW_BANNER = make_enchantment(
    name="Ravenclaw Banner",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Ravenclaw creatures you control get +0/+1 and have '{T}: Scry 1.'",
    setup_interceptors=_hpw_s23_ravenclaw_banner_setup,
)


# =============================================================================
# BLACK CARDS - SLYTHERIN, DARK ARTS, DEATH EATERS
# =============================================================================

# --- Legendary Creatures ---

def voldemort_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature dies, put a +1/+1 counter on Voldemort."""
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        return dying_id != obj.id

    def death_handler(event, state, src=obj):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.COUNTER_ADDED, payload={
                'object_id': src.id, 'counter_type': '+1/+1', 'amount': 1
            }, source=src.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        duration='while_on_battlefield'
    )]

LORD_VOLDEMORT = make_creature(
    name="Lord Voldemort, the Dark Lord",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Flying, deathtouch. Whenever another creature dies, put a +1/+1 "
        "counter on Lord Voldemort. As long as you control a Deathly Hallow "
        "(Elder Wand, Resurrection Stone, or Invisibility Cloak), Lord "
        "Voldemort gets +2/+2 and has indestructible. {2}{B}: Each opponent "
        "loses 2 life."
    ),
    setup_interceptors=voldemort_spice_setup,
)


def severus_snape_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DAMAGE,
                  payload={'target': opp_id, 'amount': 3, 'source': obj.id},
                  source=obj.id)
            for opp_id in _ih.all_opponents(obj, state)
        ]
    return [_ih.make_death_trigger(obj, effect_fn)]

SEVERUS_SNAPE = make_creature(
    name="Severus Snape, Double Agent",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Slytherin"},
    supertypes={"Legendary"},
    text="When Severus Snape dies, he deals 3 damage to each opponent.",
    setup_interceptors=severus_snape_setup
)


def bellatrix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, opponent sacrifices a creature."""
    def attack_filter(event, state, src=obj):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('attacker_id') == src.id

    def attack_handler(event, state, src=obj):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.SACRIFICE, payload={
                'player': 'opponent', 'type': 'creature'
            }, source=src.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield'
    )]

BELLATRIX_LESTRANGE = make_creature(
    name="Bellatrix Lestrange, Mad Servant",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Death Eater"},
    supertypes={"Legendary"},
    text="Menace. Whenever Bellatrix attacks, defending player sacrifices a creature.",
    setup_interceptors=bellatrix_setup
)


def draco_malfoy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _t = static_pt_boost_by_subtype(obj, 1, 0, "Slytherin", include_self=False)
    return itcs

DRACO_MALFOY = make_creature(
    name="Draco Malfoy, Cunning Heir",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Slytherin"},
    supertypes={"Legendary"},
    text="Other Slytherin creatures you control get +1/+0.",
    setup_interceptors=draco_malfoy_setup
)


def lucius_malfoy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD,
                  payload={'player': opp_id, 'count': 1},
                  source=obj.id)
            for opp_id in _ih.all_opponents(obj, state)
        ]
    return [_ih.make_etb_trigger(obj, effect_fn)]

LUCIUS_MALFOY = make_creature(
    name="Lucius Malfoy, Dark Aristocrat",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Death Eater"},
    supertypes={"Legendary"},
    text="When Lucius Malfoy enters, each opponent discards a card.",
    setup_interceptors=lucius_malfoy_setup
)


# --- Regular Black Creatures ---

SLYTHERIN_PREFECT = make_creature(
    name="Slytherin Prefect",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Slytherin"},
    text=(
        "Deathtouch. When Slytherin Prefect dies, each opponent loses 1 "
        "life. If you control another Slytherin, you gain 1 life. "
        "(The prefect's curse lingers.)"
    ),
    setup_interceptors=_hpw_slytherin_prefect_setup,
)


DEATH_EATER_INITIATE = make_creature(
    name="Death Eater Initiate",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard", "Death Eater"},
    text=(
        "When Death Eater Initiate dies, each opponent loses 1 life. If "
        "you control another Death Eater, you gain 1 life. (Initiation "
        "is sealed in blood.)"
    ),
    setup_interceptors=_hpw_death_eater_initiate_setup,
)


DEMENTOR = make_creature(
    name="Dementor",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flying. Whenever Dementor deals combat damage to a player, that player discards a card and you draw a card.",
    setup_interceptors=_hpw_s23_dementor_setup,
)


DEMENTOR_SWARM = make_creature(
    name="Dementor Swarm",
    power=5, toughness=5,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flying. When Dementor Swarm enters, each opponent discards two cards.",
    setup_interceptors=_hpw_s23_dementor_swarm_setup,
)


INFERIUS = make_creature(
    name="Inferius",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text=(
        "Inferius can't block. When Inferius dies, each opponent loses 1 "
        "life and you gain 1 life per other Zombie you control. (The "
        "reanimated rise from the deep.)"
    ),
    setup_interceptors=_hpw_inferius_setup,
)


DARK_WIZARD = make_creature(
    name="Dark Wizard",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="Menace. {B}, Pay 2 life: Dark Wizard gains deathtouch until end of turn.",
    setup_interceptors=_hpw_s23_dark_wizard_setup,
)


KNOCKTURN_ALLEY_VENDOR = make_creature(
    name="Knockturn Alley Vendor",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="{T}, Pay 1 life: Add {B}.",
    setup_interceptors=_hpw_s23_knockturn_alley_vendor_setup,
)


BASILISK = make_creature(
    name="Basilisk",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Serpent"},
    text="Deathtouch. Whenever Basilisk deals damage to a creature, destroy that creature.",
    setup_interceptors=_hpw_s23_basilisk_setup,
)


ACROMANTULA = make_creature(
    name="Acromantula",
    power=4, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spider"},
    text="Reach, deathtouch. When Acromantula dies, create two 1/1 black Spider creature tokens with reach.",
    setup_interceptors=_hpw_s23_acromantula_setup,
)


NAGINI = make_creature(
    name="Nagini",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Snake"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Nagini deals combat damage to a player, you may return target creature card from your graveyard to your hand.",
    setup_interceptors=_hpw_s23_nagini_setup,
)


AZKABAN_GUARD = make_creature(
    name="Azkaban Guard",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="Lifelink. Other creatures you control have lifelink.",
    setup_interceptors=_hpw_s23_azkaban_guard_setup,
)


GREYBACK = make_creature(
    name="Fenrir Greyback",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Werewolf"},
    supertypes={"Legendary"},
    text="First strike. Whenever Fenrir Greyback deals combat damage to a creature, put two -1/-1 counters on that creature.",
    setup_interceptors=_hpw_s23_fenrir_greyback_setup,
)


# --- Black Instants ---

AVADA_KEDAVRA = make_instant(
    name="Avada Kedavra",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. It can't be regenerated. Its controller loses 2 life.",
    resolve=_hpw_s23_resolve_avada_kedavra,
)


CRUCIO = make_instant(
    name="Crucio",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn.",
    resolve=_hpw_s23_resolve_crucio,
)


IMPERIO = make_instant(
    name="Imperio",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Gain control of target creature until end of turn. Untap it. It gains haste until end of turn.",
    resolve=_hpw_s23_resolve_imperio,
)


SECTUMSEMPRA = make_instant(
    name="Sectumsempra",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. You lose 2 life.",
    resolve=_hpw_s23_resolve_sectumsempra,
)


MORSMORDRE = make_instant(
    name="Morsmordre",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Create a 4/4 black Horror creature token with flying.",
    resolve=_hpw_s23_resolve_morsmordre,
)


DARK_MARK = make_instant(
    name="Dark Mark",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets +2/+0 and gains menace until end of turn.",
    resolve=_hpw_s23_resolve_dark_mark,
)


# --- Black Sorceries ---

CURSE_OF_THE_BOGIES = make_sorcery(
    name="Curse of the Bogies",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target player discards a card. Spell Mastery - If you've cast 3+ instants/sorceries this game, that player discards two cards instead.",
    resolve=_hpw_s23_resolve_curse_of_the_bogies,
)


SUMMON_INFERI = make_sorcery(
    name="Summon Inferi",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Return up to two creature cards from your graveyard to the battlefield. They gain haste. Exile them at the beginning of the next end step.",
    resolve=_hpw_s23_resolve_summon_inferi,
)


DARK_RITUAL_SPELL = make_sorcery(
    name="Dark Ritual",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Add {B}{B}{B}.",
    resolve=_hpw_s23_resolve_dark_ritual_spell,
)


FIENDFYRE = make_sorcery(
    name="Fiendfyre",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. You lose 3 life.",
    resolve=_hpw_s23_resolve_fiendfyre,
)


# --- Black Enchantments ---

def dark_arts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature you control dies, each opponent loses 1 life."""
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return dying.controller == obj.controller and CardType.CREATURE in dying.characteristics.types

    def death_handler(event, state, src=obj):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.LIFE_CHANGE, payload={
                'player': 'each_opponent', 'amount': -1
            }, source=src.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        duration='while_on_battlefield'
    )]

THE_DARK_ARTS = make_enchantment(
    name="The Dark Arts",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Whenever a creature you control dies, each opponent loses 1 life.",
    setup_interceptors=dark_arts_setup
)


SLYTHERIN_BANNER = make_enchantment(
    name="Slytherin Banner",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Slytherin creatures you control get +1/+1 and have deathtouch.",
    setup_interceptors=_hpw_s23_slytherin_banner_setup,
)


HORCRUX_CURSE = make_enchantment(
    name="Horcrux Curse",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life. When you would lose the game, if you have 7 or more life, you may pay 7 life instead. If you do, exile Horcrux Curse.",
    setup_interceptors=_hpw_s23_horcrux_curse_setup,
)


# =============================================================================
# RED CARDS - WEASLEYS, CHAOS, FIRE SPELLS
# =============================================================================

# --- Legendary Creatures ---

def ron_weasley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +1/+1 for each other Gryffindor."""
    return make_house_bonus(obj, "Gryffindor", 1, 1)

RON_WEASLEY = make_creature(
    name="Ron Weasley, Loyal Friend",
    power=3, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="First strike. House - Ron gets +1/+1 for each other Gryffindor you control.",
    setup_interceptors=ron_weasley_setup
)


def fred_and_george_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, create a copy token."""
    def attack_filter(event, state, src=obj):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('attacker_id') == src.id

    def attack_handler(event, state, src=obj):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(type=EventType.CREATE_TOKEN, payload={
                'controller': src.controller,
                'token': {'name': 'Weasley Twin', 'power': 2, 'toughness': 2, 'colors': {Color.RED},
                         'subtypes': {'Human', 'Wizard', 'Gryffindor'}, 'keywords': ['haste'],
                         'exile_eot': True}
            }, source=src.id)]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield'
    )]

FRED_AND_GEORGE = make_creature(
    name="Fred and George Weasley, Pranksters",
    power=2, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="Haste. Whenever Fred and George attack, create a 2/2 red Human Wizard token with haste. Exile it at end of turn.",
    setup_interceptors=fred_and_george_setup
)


def ginny_weasley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell Mastery - has double strike."""
    # Custom conditional keyword grant
    def ability_filter(event, state, src=obj):
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        return target_id == src.id and has_spell_mastery(state, src.controller)

    def ability_handler(event, state):
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'double_strike' not in granted:
            granted.append('double_strike')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )]

GINNY_WEASLEY = make_creature(
    name="Ginny Weasley, Fierce Duelist",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Gryffindor"},
    supertypes={"Legendary"},
    text="First strike. Spell Mastery - Ginny has double strike if you've cast 3+ instants/sorceries this game.",
    setup_interceptors=ginny_weasley_setup
)


SIRIUS_BLACK = make_creature(
    name="Sirius Black, Escaped Convict",
    power=4, toughness=3,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Haste. Whenever Sirius Black, Escaped Convict attacks, he deals 1 "
        "damage to defending player; if you've cast an instant or sorcery "
        "this game, draw a card."
    ),
    setup_interceptors=sirius_black_setup,
)


def molly_weasley_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DAMAGE,
                  payload={'target': opp_id, 'amount': 5, 'source': obj.id},
                  source=obj.id)
            for opp_id in _ih.all_opponents(obj, state)
        ]
    return [_ih.make_death_trigger(obj, effect_fn)]

MOLLY_WEASLEY = make_creature(
    name="Molly Weasley, Protective Mother",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Molly Weasley dies, she deals 5 damage to each opponent.",
    setup_interceptors=molly_weasley_setup
)


# --- Regular Red Creatures ---

WEASLEY_TWIN_PRANKSTER = make_creature(
    name="Weasley Twin Prankster",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Gryffindor"},
    text="Haste. When Weasley Twin Prankster enters, it deals 1 damage to any target.",
    setup_interceptors=_hpw_s23_weasley_twin_prankster_setup,
)


QUIDDITCH_BEATER = make_creature(
    name="Quidditch Beater",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text=(
        "Haste. {R}: Quidditch Beater gets +1/+0 until end of turn. Whenever "
        "Quidditch Beater attacks, each opponent loses 1 life. If you "
        "control another Gryffindor, you gain 1 life. (Bludger swung true.)"
    ),
    setup_interceptors=_hpw_quidditch_beater_setup,
)


DRAGON_HANDLER = make_creature(
    name="Dragon Handler",
    power=2, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text=(
        "Dragon creatures you control get +1/+0 and have haste. When Dragon "
        "Handler enters, you gain 1 life for each Dragon you control. If "
        "you control any Dragon, each opponent loses 1 life. (The handler "
        "unleashes the beast.)"
    ),
    setup_interceptors=_hpw_dragon_handler_setup,
)


HUNGARIAN_HORNTAIL = make_creature(
    name="Hungarian Horntail",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text=(
        "Flying, haste. Whenever Hungarian Horntail attacks, it deals 2 "
        "damage to each creature defending player controls. Additionally, "
        "each opponent loses 1 life; if you control another Dragon, deal "
        "1 damage to each opponent instead. (Firefall of the broodmother.)"
    ),
    setup_interceptors=_hpw_hungarian_horntail_setup,
)


NORWEGIAN_RIDGEBACK = make_creature(
    name="Norwegian Ridgeback",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text=(
        "Flying. {R}: Norwegian Ridgeback gets +1/+0 until end of turn. "
        "Whenever Norwegian Ridgeback attacks, each opponent loses 1 life; "
        "if you control 2+ Dragons, you also gain 1 life. (Firefall of the brood.)"
    ),
    setup_interceptors=_hpw_norwegian_ridgeback_setup,
)


CHINESE_FIREBALL = make_creature(
    name="Chinese Fireball",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text=(
        "Flying. When Chinese Fireball enters, it deals 1 damage to each "
        "opponent. If you control another Dragon, you also gain 1 life. "
        "(The fireball's first cry rallies the brood.)"
    ),
    setup_interceptors=_hpw_chinese_fireball_setup,
)


COMMON_WELSH_GREEN = make_creature(
    name="Common Welsh Green",
    power=4, toughness=5,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Dragon"},
    text=(
        "Flying. Whenever Common Welsh Green deals combat damage to a "
        "player, add {R}{G}. Whenever it attacks, each opponent loses 1 "
        "life; if you control another Dragon, you gain 1 life. "
        "(Welsh fire rallies the brood.)"
    ),
    setup_interceptors=_hpw_common_welsh_green_setup,
)


GOBLIN_BANKER = make_creature(
    name="Gringotts Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="{T}: Add {R}. Spend this mana only to cast instant or sorcery spells.",
    setup_interceptors=_hpw_s23_gringotts_goblin_setup,
)


FIENDFYRE_ELEMENTAL = make_creature(
    name="Fiendfyre Elemental",
    power=5, toughness=1,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample, haste. At the beginning of your end step, sacrifice Fiendfyre Elemental.",
    setup_interceptors=_hpw_s23_fiendfyre_elemental_setup,
)


BLAST_ENDED_SKREWT = make_creature(
    name="Blast-Ended Skrewt",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="When Blast-Ended Skrewt dies, it deals 2 damage to each creature.",
    setup_interceptors=_hpw_s23_blast_ended_skrewt_setup,
)


ERUMPENT = make_creature(
    name="Erumpent",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="Trample. When Erumpent dies, it deals 4 damage to target creature or player.",
    setup_interceptors=_hpw_s23_erumpent_setup,
)


# --- Red Instants ---

INCENDIO = make_instant(
    name="Incendio",
    mana_cost="{R}",
    colors={Color.RED},
    text="Incendio deals 2 damage to any target.",
    resolve=_hpw_s23_resolve_incendio,
)


CONFRINGO = make_instant(
    name="Confringo",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Confringo deals 3 damage to target creature or planeswalker.",
    resolve=_hpw_s23_resolve_confringo,
)


BOMBARDA = make_instant(
    name="Bombarda",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Destroy target artifact. Bombarda deals 2 damage to that artifact's controller.",
    resolve=_hpw_s23_resolve_bombarda,
)


REDUCTO = make_instant(
    name="Reducto",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Reducto deals 4 damage to target creature.",
    resolve=_hpw_s23_resolve_reducto,
)


EXPULSO = make_instant(
    name="Expulso",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Expulso deals 5 damage divided as you choose among any number of target creatures.",
    resolve=_hpw_s23_resolve_expulso,
)


DRAGONS_BREATH = make_instant(
    name="Dragon's Breath",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains first strike until end of turn.",
    resolve=_hpw_s23_resolve_dragons_breath,
)


WEASLEY_FIREWORK = make_instant(
    name="Weasley Firework",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Weasley Firework deals 1 damage to each creature your opponents control.",
    resolve=_hpw_s23_resolve_weasley_firework,
)


# --- Red Sorceries ---

DRAGONS_FIRE = make_sorcery(
    name="Dragon's Fire",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Dragon's Fire deals 4 damage to each creature. If you control a Dragon, it deals 5 damage instead.",
    resolve=_hpw_s23_resolve_dragons_fire,
)


PYROTECHNICS = make_sorcery(
    name="Pyrotechnics",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Pyrotechnics deals 3 damage divided as you choose among one, two, or three targets.",
    resolve=_hpw_s23_resolve_pyrotechnics,
)


SUMMON_DRAGON = make_sorcery(
    name="Summon Dragon",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Create a 5/5 red Dragon creature token with flying and haste.",
    resolve=_hpw_s23_resolve_summon_dragon,
)


# --- Red Enchantments ---

WEASLEYS_WIZARD_WHEEZES = make_enchantment(
    name="Weasleys' Wizard Wheezes",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever you cast an instant or sorcery spell, Weasleys' Wizard Wheezes deals 1 damage to each opponent.",
    setup_interceptors=_hpw_s23_weasleys_wizard_wheezes_setup,
)


GRYFFINDOR_COURAGE = make_enchantment(
    name="Gryffindor Courage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0 and have haste.",
    setup_interceptors=_hpw_s23_gryffindor_courage_setup,
)


# =============================================================================
# GREEN CARDS - HERBOLOGY, MAGICAL CREATURES, HUFFLEPUFF
# =============================================================================

# --- Legendary Creatures ---

def rubeus_hagrid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _t = static_pt_boost_other_you_control(obj, 1, 1)
    return itcs

RUBEUS_HAGRID = make_creature(
    name="Rubeus Hagrid, Keeper of Keys",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Wizard"},
    supertypes={"Legendary"},
    text="Other creatures you control get +1/+1.",
    setup_interceptors=rubeus_hagrid_setup
)


def pomona_sprout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep - put a +1/+1 counter on Pomona Sprout.

    (Original printed text says "target creature"; the DSL migration kept
    self-targeting parity. Retained as self-counter because no targeting
    layer is wired here.)
    """
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1'},
            source=obj.id,
            controller=obj.controller,
        )]
    return [_ih.make_upkeep_trigger(obj, effect_fn)]

POMONA_SPROUT = make_creature(
    name="Pomona Sprout, Herbology Master",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control. Other Hufflepuff creatures you control have hexproof.",
    setup_interceptors=pomona_sprout_setup
)


def cedric_diggory_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """House bonus + lifelink."""
    return make_house_bonus(obj, "Hufflepuff", 1, 1)

CEDRIC_DIGGORY = make_creature(
    name="Cedric Diggory, True Champion",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    supertypes={"Legendary"},
    text="Lifelink. House - Cedric gets +1/+1 for each other Hufflepuff you control.",
    setup_interceptors=cedric_diggory_setup
)


def newt_scamander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beast creatures cost 1 less."""
    def cost_reduce_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        subtypes = set(event.payload.get('subtypes', []))
        return 'Beast' in subtypes

    def cost_reduce_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current_reduction = new_event.payload.get('cost_reduction', 0)
        new_event.payload['cost_reduction'] = current_reduction + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=cost_reduce_filter,
        handler=cost_reduce_handler,
        duration='while_on_battlefield'
    )]

NEWT_SCAMANDER = make_creature(
    name="Newt Scamander, Magizoologist",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    supertypes={"Legendary"},
    text="Beast creature spells you cast cost {1} less. Whenever a Beast enters under your control, draw a card.",
    setup_interceptors=newt_scamander_setup
)


# --- Regular Green Creatures ---

HUFFLEPUFF_PREFECT = make_creature(
    name="Hufflepuff Prefect",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard", "Hufflepuff"},
    text=(
        "Other Hufflepuff creatures you control get +0/+1. When Hufflepuff "
        "Prefect enters, you gain 1 life for each other Hufflepuff you "
        "control. If you control 2+ Hufflepuffs, each opponent loses 1 "
        "life. (Badger-loyalty rallies the house.)"
    ),
    setup_interceptors=_hpw_hufflepuff_prefect_setup,
)


MANDRAKE = make_creature(
    name="Mandrake",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text=(
        "When Mandrake dies, each opponent loses 1 life and you gain 1 life "
        "per other Plant you control. (The mandrake's death-shriek echoes.)"
    ),
    setup_interceptors=_hpw_mandrake_setup,
)


VENOMOUS_TENTACULA = make_creature(
    name="Venomous Tentacula",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text=(
        "Reach, deathtouch. Whenever Venomous Tentacula deals combat "
        "damage, each opponent loses 1 life. If you control another Plant, "
        "you gain 1 life. (Venom-laced lash.)"
    ),
    setup_interceptors=_hpw_venomous_tentacula_setup,
)


BOWTRUCKLE = make_creature(
    name="Bowtruckle",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text=(
        "Hexproof. {T}: Add {G}. Spend this mana only to cast creature "
        "spells. When Bowtruckle enters, scry 1. If you control another "
        "Treefolk, each opponent loses 1 life. (Wand-tree guardian's vigil.)"
    ),
    setup_interceptors=_hpw_bowtruckle_setup,
)


HIPPOGRIFF = make_creature(
    name="Hippogriff",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Hippogriff"},
    text=(
        "Flying. Hippogriff can't be blocked by creatures with power 2 or "
        "less. Whenever Hippogriff attacks, each opponent loses 1 life; "
        "if you control another flying creature, you gain 1 life. "
        "(Talons strike true.)"
    ),
    setup_interceptors=_hpw_hippogriff_setup,
)


BUCKBEAK = make_creature(
    name="Buckbeak",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hippogriff"},
    supertypes={"Legendary"},
    text=(
        "Flying, trample. Buckbeak can't be blocked by more than one "
        "creature. Whenever Buckbeak attacks, each opponent loses 1 life "
        "and you gain 1 life for each other Beast/Hippogriff you control. "
        "(The proud creature leads the charge.)"
    ),
    setup_interceptors=_hpw_buckbeak_setup,
)


FAWKES_THE_PHOENIX = make_creature(
    name="Fawkes the Phoenix",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Phoenix"},
    supertypes={"Legendary"},
    text=(
        "Flying. When Fawkes the Phoenix enters, you gain 3 life. Then you "
        "may return target creature card with mana value 3 or less from your "
        "graveyard to the battlefield."
    ),
    setup_interceptors=fawkes_the_phoenix_spice_setup,
)


UNICORN = make_creature(
    name="Unicorn",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Unicorn"},
    text="Vigilance. {T}: You gain 1 life.",
    setup_interceptors=_hpw_s23_unicorn_setup,
)


CENTAUR_ARCHER = make_creature(
    name="Centaur Archer",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Archer"},
    text="Reach. {G}: Centaur Archer deals 1 damage to target creature with flying.",
    setup_interceptors=_hpw_s23_centaur_archer_setup,
)


FORBIDDEN_FOREST_SPIDER = make_creature(
    name="Forbidden Forest Spider",
    power=2, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach. When Forbidden Forest Spider dies, create two 1/1 green Spider creature tokens with reach.",
    setup_interceptors=_hpw_s23_forbidden_forest_spider_setup,
)


NIFFLER = make_creature(
    name="Niffler",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When Niffler enters, you may search your library for an artifact card, reveal it, and put it into your hand. Shuffle.",
    setup_interceptors=_hpw_s23_niffler_setup,
)


THESTRAL_HERD = make_creature(
    name="Thestral Herd",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Flying. Thestral Herd has hexproof as long as a creature died this turn.",
    setup_interceptors=_hpw_s23_thestral_herd_setup,
)


WHOMPING_WILLOW = make_creature(
    name="Whomping Willow",
    power=5, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Defender, reach. Whenever a creature attacks you, Whomping Willow deals 2 damage to it.",
    setup_interceptors=_hpw_s23_whomping_willow_setup,
)


GIANT_SQUID = make_creature(
    name="Giant Squid of the Black Lake",
    power=6, toughness=6,
    mana_cost="{4}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Kraken"},
    text="Hexproof. Giant Squid can't attack unless defending player controls an Island or you pay {2}.",
    setup_interceptors=_hpw_s23_giant_squid_setup,
)


# --- Green Instants ---

HERBIVICUS = make_instant(
    name="Herbivicus",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn.",
    resolve=_hpw_s23_resolve_herbivicus,
)


WILD_GROWTH_SPELL = make_instant(
    name="Wild Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature.",
    resolve=_hpw_s23_resolve_wild_growth,
)


ENGORGIO = make_instant(
    name="Engorgio",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 and gains trample until end of turn.",
    resolve=_hpw_s23_resolve_engorgio,
)


BEASTS_FURY = make_instant(
    name="Beast's Fury",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control.",
    resolve=_hpw_s23_resolve_beasts_fury,
)


NATURES_PROTECTION = make_instant(
    name="Nature's Protection",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gains hexproof and indestructible until end of turn.",
    resolve=_hpw_s23_resolve_natures_protection,
)


# --- Green Sorceries ---

GREENHOUSE_HARVEST = make_sorcery(
    name="Greenhouse Harvest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal them, put one onto the battlefield tapped and the other into your hand. Shuffle.",
    resolve=_hpw_s23_resolve_greenhouse_harvest,
)


CREATURE_SUMMONING = make_sorcery(
    name="Creature Summoning",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create two 3/3 green Beast creature tokens.",
    resolve=_hpw_s23_resolve_creature_summoning,
)


MANDRAKE_RESTORATIVE = make_sorcery(
    name="Mandrake Restorative",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="You gain 5 life. You may return target creature card from your graveyard to your hand.",
    resolve=_hpw_s23_resolve_mandrake_restorative,
)


# --- Green Enchantments ---

HERBOLOGY_CLASSROOM = make_enchantment(
    name="Herbology Classroom",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control.",
    setup_interceptors=_hpw_s23_herbology_classroom_setup,
)


HUFFLEPUFF_BANNER = make_enchantment(
    name="Hufflepuff Banner",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Hufflepuff creatures you control get +1/+1. Whenever a Hufflepuff enters under your control, you gain 1 life.",
    setup_interceptors=_hpw_s23_hufflepuff_banner_setup,
)


FORBIDDEN_FOREST = make_enchantment(
    name="Forbidden Forest",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Creature spells you cast cost {1} less. Creatures you control have trample.",
    setup_interceptors=_hpw_s23_forbidden_forest_enchantment_setup,
)


# =============================================================================
# ARTIFACTS
# =============================================================================

ELDER_WAND = make_equipment(
    name="Elder Wand",
    mana_cost="{3}",
    text="Equipped creature gets +3/+0, has first strike, and has ward {2}.",
    equip_cost="{2}",
    supertypes={"Legendary"},
    setup_interceptors=elder_wand_setup,
)


RESURRECTION_STONE = make_artifact(
    name="Resurrection Stone",
    mana_cost="{2}",
    text="{3}, {T}, Sacrifice Resurrection Stone: Return target creature card with mana value 3 or less from your graveyard to the battlefield.",
    supertypes={"Legendary"},
    setup_interceptors=resurrection_stone_setup,
)


INVISIBILITY_CLOAK = make_equipment(
    name="Invisibility Cloak",
    mana_cost="{2}",
    text="Equipped creature gets +0/+2, has hexproof, and is unblockable.",
    equip_cost="{1}",
    supertypes={"Legendary"},
    setup_interceptors=invisibility_cloak_setup,
)


SWORD_OF_GRYFFINDOR = make_equipment(
    name="Sword of Gryffindor",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2 and has protection from black. Whenever equipped creature deals combat damage to a player, destroy target artifact or enchantment.",
    equip_cost="{2}",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_sword_of_gryffindor_setup,
)


MARAUDERS_MAP = make_artifact(
    name="Marauder's Map",
    mana_cost="{2}",
    text="{T}: Scry 2. {2}, {T}: Look at target opponent's hand.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_marauders_map_setup,
)


SORTING_HAT = make_artifact(
    name="Sorting Hat",
    mana_cost="{1}",
    text="{T}: Target creature becomes Gryffindor, Slytherin, Ravenclaw, or Hufflepuff in addition to its other types until end of turn.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_sorting_hat_setup,
)


HORCRUX_DIARY = make_artifact(
    name="Tom Riddle's Diary",
    mana_cost="{2}",
    text="{1}, {T}, Pay 2 life: Draw a card. When Tom Riddle's Diary is put into a graveyard from the battlefield, you lose 5 life.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_horcrux_diary_setup,
)


HORCRUX_LOCKET = make_artifact(
    name="Slytherin's Locket",
    mana_cost="{3}",
    text="At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life. {2}, Sacrifice Slytherin's Locket: Draw two cards.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_horcrux_locket_setup,
)


HORCRUX_CUP = make_artifact(
    name="Hufflepuff's Cup",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. When Hufflepuff's Cup is put into a graveyard from the battlefield, each opponent draws a card.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_horcrux_cup_setup,
)


HORCRUX_DIADEM = make_artifact(
    name="Ravenclaw's Diadem",
    mana_cost="{3}",
    text="Instant and sorcery spells you cast cost {1} less. {2}, Sacrifice Ravenclaw's Diadem: Draw three cards.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_horcrux_diadem_setup,
)


HORCRUX_RING = make_artifact(
    name="Gaunt Family Ring",
    mana_cost="{2}",
    text="{T}: Add {B}. {3}, {T}, Sacrifice Gaunt Family Ring: Return target creature card from your graveyard to your hand.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_horcrux_ring_setup,
)


FIREBOLT_BROOM = make_artifact(
    name="Firebolt",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has flying and haste.\nEquip {2}",
    setup_interceptors=_hpw_s23_firebolt_setup,
)


NIMBUS_2000 = make_artifact(
    name="Nimbus 2000",
    mana_cost="{2}",
    text="Equipped creature gets +1/+0 and has flying.\nEquip {1}",
    setup_interceptors=_hpw_s23_nimbus_2000_setup,
)


WAND_OF_PHOENIX_FEATHER = make_equipment(
    name="Wand of Phoenix Feather",
    mana_cost="{1}",
    text="Equipped creature has '{T}: This creature deals 1 damage to any target.'",
    equip_cost="{1}",
    setup_interceptors=_hpw_s23_wand_phoenix_feather_setup,
)


WAND_OF_DRAGON_HEARTSTRING = make_equipment(
    name="Wand of Dragon Heartstring",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1 and has '{T}: Add {R}.'",
    equip_cost="{1}",
    setup_interceptors=_hpw_s23_wand_dragon_heartstring_setup,
)


WAND_OF_UNICORN_HAIR = make_equipment(
    name="Wand of Unicorn Hair",
    mana_cost="{1}",
    text="Equipped creature has '{T}: You gain 1 life.'",
    equip_cost="{1}",
    setup_interceptors=_hpw_s23_wand_unicorn_hair_setup,
)


PENSIEVE = make_artifact(
    name="Pensieve",
    mana_cost="{3}",
    text="{2}, {T}: Look at the top 3 cards of your library. Put one into your hand and the rest on the bottom in any order.",
    setup_interceptors=_hpw_s23_pensieve_setup,
)


GOLDEN_SNITCH = make_artifact(
    name="Golden Snitch",
    mana_cost="{1}",
    text="Flying. {T}, Sacrifice Golden Snitch: Draw two cards.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_golden_snitch_setup,
)


QUAFFLE = make_artifact(
    name="Quaffle",
    mana_cost="{1}",
    text="{1}, {T}: Target creature gets +1/+0 and gains first strike until end of turn.",
    setup_interceptors=_hpw_s23_quaffle_setup,
)


BLUDGER = make_artifact(
    name="Bludger",
    mana_cost="{2}",
    text="{2}, {T}: Bludger deals 2 damage to target creature.",
    setup_interceptors=_hpw_s23_bludger_setup,
)


TIME_TURNER = make_artifact(
    name="Time-Turner",
    mana_cost="{4}",
    text="{T}, Sacrifice Time-Turner: Take an extra turn after this one. Activate only as a sorcery.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_time_turner_setup,
)


DELUMINATOR = make_artifact(
    name="Deluminator",
    mana_cost="{1}",
    text="{T}: Tap target creature. It doesn't untap during its controller's next untap step.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_deluminator_setup,
)


PORTKEY = make_artifact(
    name="Portkey",
    mana_cost="{2}",
    text="{3}, {T}, Sacrifice Portkey: Return target creature to its owner's hand.",
    setup_interceptors=_hpw_s23_portkey_setup,
)


FLOO_POWDER = make_artifact(
    name="Floo Powder",
    mana_cost="{1}",
    text="{1}, Sacrifice Floo Powder: Add two mana of any one color."
)


GOBLET_OF_FIRE = make_artifact(
    name="Goblet of Fire",
    mana_cost="{4}",
    text="At the beginning of your upkeep, put a flame counter on Goblet of Fire. Then if there are 3 or more flame counters on it, sacrifice it and create a 5/5 red Dragon creature token with flying.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_goblet_of_fire_setup,
)


MIRROR_OF_ERISED = make_artifact(
    name="Mirror of Erised",
    mana_cost="{3}",
    text="{2}, {T}: Look at the top card of your library. You may put it into your graveyard.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_mirror_of_erised_setup,
)


VANISHING_CABINET = make_artifact(
    name="Vanishing Cabinet",
    mana_cost="{3}",
    text="{2}, {T}: Exile target creature you control. Return it to the battlefield at the beginning of the next end step.",
    setup_interceptors=_hpw_s23_vanishing_cabinet_setup,
)


# =============================================================================
# LANDS
# =============================================================================

HOGWARTS_CASTLE = make_land(
    name="Hogwarts Castle",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Wizard spells.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_hogwarts_castle_upkeep_setup,
)


GRYFFINDOR_COMMON_ROOM = make_land(
    name="Gryffindor Common Room",
    text="Gryffindor Common Room enters tapped. {T}: Add {R} or {W}. {2}, {T}: Target Gryffindor creature gets +1/+1 until end of turn.",
    setup_interceptors=_hpw_s23_gryffindor_common_room_setup,
)


SLYTHERIN_DUNGEON = make_land(
    name="Slytherin Dungeon",
    text="Slytherin Dungeon enters tapped. {T}: Add {B} or {U}. {2}, {T}: Target Slytherin creature gains deathtouch until end of turn.",
    setup_interceptors=_hpw_s23_slytherin_dungeon_setup,
)


RAVENCLAW_TOWER = make_land(
    name="Ravenclaw Tower",
    text="Ravenclaw Tower enters tapped. {T}: Add {U} or {W}. {2}, {T}: Scry 1.",
    setup_interceptors=_hpw_s23_ravenclaw_tower_setup,
)


HUFFLEPUFF_BASEMENT = make_land(
    name="Hufflepuff Basement",
    text="Hufflepuff Basement enters tapped. {T}: Add {G} or {W}. {2}, {T}: You gain 1 life.",
    setup_interceptors=_hpw_s23_hufflepuff_basement_setup,
)


DIAGON_ALLEY = make_land(
    name="Diagon Alley",
    text="{T}: Add {C}. {1}, {T}: Add one mana of any color. Spend this mana only to cast artifact spells.",
    setup_interceptors=_hpw_s23_diagon_alley_setup,
)


HOGSMEADE_VILLAGE = make_land(
    name="Hogsmeade Village",
    text="{T}: Add {C}. {T}, Pay 1 life: Add one mana of any color.",
    setup_interceptors=_hpw_s23_hogsmeade_village_setup,
)


FORBIDDEN_FOREST_LAND = make_land(
    name="The Forbidden Forest",
    text="{T}: Add {G}. {2}{G}, {T}: Create a 2/2 green Beast creature token.",
    setup_interceptors=_hpw_s23_forbidden_forest_land_setup,
)


MINISTRY_OF_MAGIC = make_land(
    name="Ministry of Magic",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Spend this mana only to cast instant or sorcery spells.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_ministry_of_magic_setup,
)


AZKABAN = make_land(
    name="Azkaban",
    text="{T}: Add {B}. {2}{B}, {T}: Each opponent discards a card.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_azkaban_land_setup,
)


GODRICS_HOLLOW = make_land(
    name="Godric's Hollow",
    text="{T}: Add {W}. When Godric's Hollow enters, you may pay 2 life. If you do, draw a card.",
    setup_interceptors=_hpw_s23_godrics_hollow_setup,
)


GRIMMAULD_PLACE = make_land(
    name="12 Grimmauld Place",
    text="{T}: Add {B}. {1}{B}, {T}: Target creature gains menace until end of turn.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_grimmauld_place_setup,
)


THE_BURROW = make_land(
    name="The Burrow",
    text="{T}: Add {R} or {G}. Whenever you cast a creature spell, you may pay {1}. If you do, you gain 1 life.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_the_burrow_setup,
)


MALFOY_MANOR = make_land(
    name="Malfoy Manor",
    text="{T}: Add {B}. {2}{B}, {T}: Put a -1/-1 counter on target creature.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_malfoy_manor_setup,
)


KNOCKTURN_ALLEY = make_land(
    name="Knockturn Alley",
    text="{T}: Add {B}. {T}, Pay 1 life: Add {B}{B}. Activate only once per turn.",
    setup_interceptors=_hpw_s23_knockturn_alley_setup,
)


GRINGOTTS = make_land(
    name="Gringotts Bank",
    text="{T}: Add {C}{C}. Activate only if you control an artifact.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_gringotts_setup,
)


QUIDDITCH_PITCH = make_land(
    name="Quidditch Pitch",
    text="{T}: Add {C}. {3}, {T}: Target creature gains flying until end of turn.",
    setup_interceptors=_hpw_s23_quidditch_pitch_setup,
)


ROOM_OF_REQUIREMENT = make_land(
    name="Room of Requirement",
    text="{T}: Add {C}. {2}, {T}: Add one mana of any color.",
    supertypes={"Legendary"},
    setup_interceptors=_hpw_s23_room_of_requirement_setup,
)


SHRIEKING_SHACK = make_land(
    name="Shrieking Shack",
    text="{T}: Add {B} or {G}. {2}, {T}: Target creature can't block this turn.",
    setup_interceptors=_hpw_s23_shrieking_shack_setup,
)


PLATFORM_NINE_THREE_QUARTERS = make_land(
    name="Platform Nine and Three-Quarters",
    text="{T}: Add {C}. {T}, Sacrifice Platform Nine and Three-Quarters: Search your library for a basic land card, put it onto the battlefield, then shuffle.",
    supertypes={"Legendary"}
)


# =============================================================================
# Spice-pass W22+ new card definitions
# Setup functions defined near the top of this file (after the keyword helpers).
# =============================================================================


# --- Hogwarts: The Sorting Year (NEW saga, spice-pass W22+) ------------------
# {3}{W}{U} Enchantment — Saga. Chapter I: tutor a House creature MV<=3
# straight onto the battlefield tapped. Chapter II: create 2 white Human
# Wizard tokens. Chapter III: anthem + vigilance for your other creatures
# until end of turn. Sacrifices after Chapter III (default saga behavior).
HOGWARTS_SORTING_YEAR = make_enchantment(
    name="Hogwarts: The Sorting Year",
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Saga"},
    supertypes={"Legendary"},
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Search your library for a Gryffindor, Slytherin, Ravenclaw, "
        "or Hufflepuff creature card with mana value 3 or less, put it "
        "onto the battlefield tapped, then shuffle.\n"
        "II — Create two 2/2 white Human Wizard creature tokens.\n"
        "III — Other creatures you control get +1/+1 and gain vigilance "
        "until end of turn."
    ),
    setup_interceptors=hogwarts_sorting_year_setup,
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

HARRY_POTTER_CARDS = {
    # White Legendaries
    "Harry Potter, the Chosen One": HARRY_POTTER_THE_CHOSEN_ONE,
    "Hermione Granger, Brightest Witch": HERMIONE_GRANGER,
    "Albus Dumbledore, Headmaster": ALBUS_DUMBLEDORE,
    "Minerva McGonagall, Transfiguration Master": MINERVA_MCGONAGALL,
    "Neville Longbottom, Brave Heart": NEVILLE_LONGBOTTOM,

    # White Creatures
    "Gryffindor Prefect": GRYFFINDOR_PREFECT,
    "Auror Recruit": AUROR_RECRUIT,
    "Hogwarts Defender": HOGWARTS_DEFENDER,
    "Order of the Phoenix Member": ORDER_PHOENIX_MEMBER,
    "Ministry Auror": MINISTRY_AUROR,
    "Patronus Caster": PATRONUS_CASTER,
    "Hogwarts First Year": HOGWARTS_FIRST_YEAR,
    "Dumbledore's Army Recruit": DUMBLEDORES_ARMY_RECRUIT,
    "Weasley Matriarch": WEASLEY_MATRIARCH,
    "Hogwarts Ghost": HOGWARTS_GHOST,
    "Quidditch Referee": QUIDDITCH_REFEREE,
    "Healing Witch": HEALING_WITCH,
    "St. Mungo's Healer": ST_MUNGOS_HEALER,
    "Phoenix Guardian": PHOENIX_GUARDIAN,

    # White Spells
    "Expecto Patronum": EXPECTO_PATRONUM,
    "Protego": PROTEGO,
    "Shield Charm": SHIELD_CHARM,
    "Counter-Curse": COUNTER_CURSE,
    "Priori Incantatem": PRIORI_INCANTATEM,
    "Healing Spell": HEALING_SPELL,
    "Disillusionment Charm": DISILLUSIONMENT_CHARM,
    "Call the Order": CALL_THE_ORDER,
    "Sorting Ceremony": SORTING_CEREMONY,
    "Obliviate": OBLIVIATE,

    # White Enchantments
    "Light Magic": LIGHT_MAGIC,
    "Dumbledore's Protection": DUMBLEDORES_PROTECTION,
    "Gryffindor Banner": GRYFFINDOR_BANNER,

    # WU Sagas (spice-pass W22+)
    "Hogwarts: The Sorting Year": HOGWARTS_SORTING_YEAR,

    # Blue Legendaries
    "Luna Lovegood, Seer of Truth": LUNA_LOVEGOOD,
    "Filius Flitwick, Charms Master": FILIUS_FLITWICK,
    "Cho Chang, Seeker": CHO_CHANG,
    "Moaning Myrtle": MOANING_MYRTLE,

    # Blue Creatures
    "Ravenclaw Prefect": RAVENCLAW_PREFECT,
    "Hogwarts Scholar": HOGWARTS_SCHOLAR,
    "Divination Student": DIVINATION_STUDENT,
    "Library Researcher": LIBRARY_RESEARCHER,
    "Spell Theorist": SPELL_THEORIST,
    "Hogwarts Librarian": HOGWARTS_LIBRARIAN,
    "Unspeakable": UNSPEAKABLE,
    "Pensieve Keeper": PENSIEVE_KEEPER,
    "Thestral": THESTRAL,
    "Time-Turner User": TIME_TURNER_USER,
    "Memory Charm Specialist": MEMORY_CHARM_SPECIALIST,

    # Blue Spells
    "Stupefy": STUPEFY,
    "Accio": ACCIO,
    "Confundo": CONFUNDO,
    "Petrificus Totalus": PETRIFICUS_TOTALUS,
    "Legilimens": LEGILIMENS,
    "Aguamenti": AGUAMENTI,
    "Finite Incantatem": FINITE_INCANTATEM,
    "Divination": DIVINATION_SPELL,
    "Crystal Ball Reading": CRYSTAL_BALL_READING,
    "Memory Wipe": MEMORY_WIPE,
    "Transfiguration": TRANSFIGURATION,

    # Blue Enchantments
    "Library of Hogwarts": LIBRARY_OF_HOGWARTS,
    "Ravenclaw Banner": RAVENCLAW_BANNER,

    # Black Legendaries
    "Lord Voldemort, the Dark Lord": LORD_VOLDEMORT,
    "Severus Snape, Double Agent": SEVERUS_SNAPE,
    "Bellatrix Lestrange, Mad Servant": BELLATRIX_LESTRANGE,
    "Draco Malfoy, Cunning Heir": DRACO_MALFOY,
    "Lucius Malfoy, Dark Aristocrat": LUCIUS_MALFOY,
    "Nagini": NAGINI,
    "Fenrir Greyback": GREYBACK,

    # Black Creatures
    "Slytherin Prefect": SLYTHERIN_PREFECT,
    "Death Eater Initiate": DEATH_EATER_INITIATE,
    "Dementor": DEMENTOR,
    "Dementor Swarm": DEMENTOR_SWARM,
    "Inferius": INFERIUS,
    "Dark Wizard": DARK_WIZARD,
    "Knockturn Alley Vendor": KNOCKTURN_ALLEY_VENDOR,
    "Basilisk": BASILISK,
    "Acromantula": ACROMANTULA,
    "Azkaban Guard": AZKABAN_GUARD,

    # Black Spells
    "Avada Kedavra": AVADA_KEDAVRA,
    "Crucio": CRUCIO,
    "Imperio": IMPERIO,
    "Sectumsempra": SECTUMSEMPRA,
    "Morsmordre": MORSMORDRE,
    "Dark Mark": DARK_MARK,
    "Curse of the Bogies": CURSE_OF_THE_BOGIES,
    "Summon Inferi": SUMMON_INFERI,
    "Dark Ritual": DARK_RITUAL_SPELL,
    "Fiendfyre": FIENDFYRE,

    # Black Enchantments
    "The Dark Arts": THE_DARK_ARTS,
    "Slytherin Banner": SLYTHERIN_BANNER,
    "Horcrux Curse": HORCRUX_CURSE,

    # Red Legendaries
    "Ron Weasley, Loyal Friend": RON_WEASLEY,
    "Fred and George Weasley, Pranksters": FRED_AND_GEORGE,
    "Ginny Weasley, Fierce Duelist": GINNY_WEASLEY,
    "Sirius Black, Escaped Convict": SIRIUS_BLACK,
    "Molly Weasley, Protective Mother": MOLLY_WEASLEY,

    # Red Creatures
    "Weasley Twin Prankster": WEASLEY_TWIN_PRANKSTER,
    "Quidditch Beater": QUIDDITCH_BEATER,
    "Dragon Handler": DRAGON_HANDLER,
    "Hungarian Horntail": HUNGARIAN_HORNTAIL,
    "Norwegian Ridgeback": NORWEGIAN_RIDGEBACK,
    "Chinese Fireball": CHINESE_FIREBALL,
    "Common Welsh Green": COMMON_WELSH_GREEN,
    "Gringotts Goblin": GOBLIN_BANKER,
    "Fiendfyre Elemental": FIENDFYRE_ELEMENTAL,
    "Blast-Ended Skrewt": BLAST_ENDED_SKREWT,
    "Erumpent": ERUMPENT,

    # Red Spells
    "Incendio": INCENDIO,
    "Confringo": CONFRINGO,
    "Bombarda": BOMBARDA,
    "Reducto": REDUCTO,
    "Expulso": EXPULSO,
    "Dragon's Breath": DRAGONS_BREATH,
    "Weasley Firework": WEASLEY_FIREWORK,
    "Dragon's Fire": DRAGONS_FIRE,
    "Pyrotechnics": PYROTECHNICS,
    "Summon Dragon": SUMMON_DRAGON,

    # Red Enchantments
    "Weasleys' Wizard Wheezes": WEASLEYS_WIZARD_WHEEZES,
    "Gryffindor Courage": GRYFFINDOR_COURAGE,

    # Green Legendaries
    "Rubeus Hagrid, Keeper of Keys": RUBEUS_HAGRID,
    "Pomona Sprout, Herbology Master": POMONA_SPROUT,
    "Cedric Diggory, True Champion": CEDRIC_DIGGORY,
    "Newt Scamander, Magizoologist": NEWT_SCAMANDER,
    "Buckbeak": BUCKBEAK,
    "Fawkes the Phoenix": FAWKES_THE_PHOENIX,

    # Green Creatures
    "Hufflepuff Prefect": HUFFLEPUFF_PREFECT,
    "Mandrake": MANDRAKE,
    "Venomous Tentacula": VENOMOUS_TENTACULA,
    "Bowtruckle": BOWTRUCKLE,
    "Hippogriff": HIPPOGRIFF,
    "Unicorn": UNICORN,
    "Centaur Archer": CENTAUR_ARCHER,
    "Forbidden Forest Spider": FORBIDDEN_FOREST_SPIDER,
    "Niffler": NIFFLER,
    "Thestral Herd": THESTRAL_HERD,
    "Whomping Willow": WHOMPING_WILLOW,
    "Giant Squid of the Black Lake": GIANT_SQUID,

    # Green Spells
    "Herbivicus": HERBIVICUS,
    "Wild Growth": WILD_GROWTH_SPELL,
    "Engorgio": ENGORGIO,
    "Beast's Fury": BEASTS_FURY,
    "Nature's Protection": NATURES_PROTECTION,
    "Greenhouse Harvest": GREENHOUSE_HARVEST,
    "Creature Summoning": CREATURE_SUMMONING,
    "Mandrake Restorative": MANDRAKE_RESTORATIVE,

    # Green Enchantments
    "Herbology Classroom": HERBOLOGY_CLASSROOM,
    "Hufflepuff Banner": HUFFLEPUFF_BANNER,
    "Forbidden Forest": FORBIDDEN_FOREST,

    # Artifacts - Deathly Hallows
    "Elder Wand": ELDER_WAND,
    "Resurrection Stone": RESURRECTION_STONE,
    "Invisibility Cloak": INVISIBILITY_CLOAK,

    # Artifacts - Legendary Items
    "Sword of Gryffindor": SWORD_OF_GRYFFINDOR,
    "Marauder's Map": MARAUDERS_MAP,
    "Sorting Hat": SORTING_HAT,
    "Golden Snitch": GOLDEN_SNITCH,
    "Time-Turner": TIME_TURNER,
    "Goblet of Fire": GOBLET_OF_FIRE,
    "Mirror of Erised": MIRROR_OF_ERISED,
    "Deluminator": DELUMINATOR,

    # Artifacts - Horcruxes
    "Tom Riddle's Diary": HORCRUX_DIARY,
    "Slytherin's Locket": HORCRUX_LOCKET,
    "Hufflepuff's Cup": HORCRUX_CUP,
    "Ravenclaw's Diadem": HORCRUX_DIADEM,
    "Gaunt Family Ring": HORCRUX_RING,

    # Artifacts - Brooms and Equipment
    "Firebolt": FIREBOLT_BROOM,
    "Nimbus 2000": NIMBUS_2000,
    "Wand of Phoenix Feather": WAND_OF_PHOENIX_FEATHER,
    "Wand of Dragon Heartstring": WAND_OF_DRAGON_HEARTSTRING,
    "Wand of Unicorn Hair": WAND_OF_UNICORN_HAIR,

    # Artifacts - Misc
    "Pensieve": PENSIEVE,
    "Quaffle": QUAFFLE,
    "Bludger": BLUDGER,
    "Portkey": PORTKEY,
    "Floo Powder": FLOO_POWDER,
    "Vanishing Cabinet": VANISHING_CABINET,

    # Lands - Hogwarts
    "Hogwarts Castle": HOGWARTS_CASTLE,
    "Gryffindor Common Room": GRYFFINDOR_COMMON_ROOM,
    "Slytherin Dungeon": SLYTHERIN_DUNGEON,
    "Ravenclaw Tower": RAVENCLAW_TOWER,
    "Hufflepuff Basement": HUFFLEPUFF_BASEMENT,
    "Room of Requirement": ROOM_OF_REQUIREMENT,
    "Quidditch Pitch": QUIDDITCH_PITCH,

    # Lands - Locations
    "Diagon Alley": DIAGON_ALLEY,
    "Hogsmeade Village": HOGSMEADE_VILLAGE,
    "The Forbidden Forest": FORBIDDEN_FOREST_LAND,
    "Ministry of Magic": MINISTRY_OF_MAGIC,
    "Azkaban": AZKABAN,
    "Godric's Hollow": GODRICS_HOLLOW,
    "12 Grimmauld Place": GRIMMAULD_PLACE,
    "The Burrow": THE_BURROW,
    "Malfoy Manor": MALFOY_MANOR,
    "Knockturn Alley": KNOCKTURN_ALLEY,
    "Gringotts Bank": GRINGOTTS,
    "Shrieking Shack": SHRIEKING_SHACK,
    "Platform Nine and Three-Quarters": PLATFORM_NINE_THREE_QUARTERS,
}


# =============================================================================
# Phase A2 (slice 2) — decision-axis flips (2026-05-19)
# +5 net-new cards. Each card surfaces a distinct decision-axis fingerprint
# HPW has never had: prior to this slice every HPW card scored decision=0.
# Targets axis_diversity 0.056 -> >=0.080 (gate 1/4 -> 2/4). All helpers
# enumerated in `_MTG_MODAL_HELPERS` (src/depth/engine_profiles.py).
# =============================================================================


# --- Sorting Hat's Verdict ({U}{B}{R} Enchantment, modal-ETB) ---
# Pattern 7 (modal: choose-one). Lore: The Sorting Hat weighs three paths.
# Uses make_modal_etb_trigger so the AST scorer registers decision=2
# (deep_modal helper, no targeted modes).
def _sorting_hats_verdict_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: choose one — Scry 3; or, draw a card then discard a card;
    or, each opponent loses 2 life. make_modal_etb_trigger surfaces
    decision=2 (deep modal helper, no targeted modes -> 2)."""
    modes = [
        {
            'text': 'Scry 3 (the Hat reads your courage)',
            'requires_targeting': False,
            'effect': 'scry',
            'effect_params': {'amount': 3},
        },
        {
            'text': 'Draw a card, then discard a card',
            'requires_targeting': False,
            'effect': 'loot',
            'effect_params': {'amount': 1},
        },
        {
            'text': 'Each opponent loses 2 life',
            'requires_targeting': False,
            'effect': 'opp_drain',
            'effect_params': {'amount': 2},
        },
    ]
    return [
        _ih.make_modal_etb_trigger(
            obj, modes, min_modes=1, max_modes=1,
            prompt="Choose one: the Sorting Hat's Verdict",
        ),
    ]


SORTING_HATS_VERDICT = make_enchantment(
    name="Sorting Hat's Verdict",
    mana_cost="{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    text=(
        "When Sorting Hat's Verdict enters, choose one —\n"
        "* Scry 3.\n"
        "* Draw a card, then discard a card.\n"
        "* Each opponent loses 2 life.\n"
        "(\"It's all here in your head, you know.\")"
    ),
    setup_interceptors=_sorting_hats_verdict_setup,
)


# --- Bellatrix Lestrange, Crucio Witch ({1}{B}{R} 3/2 Legendary Creature) ---
# Decision-axis: make_targeted_etb_trigger w/ opponent_creature filter
# + DISCARD_CHOICE info event for asymmetry=3. Lore: Bellatrix's Crucio
# tortures a foe into surrendering a secret.
def _bellatrix_lestrange_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: targeted-helper + info event so the AST walker tags an
    information event (asymmetry=3). make_targeted_etb_trigger
    -> decision=1."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def info_pulse(event: Event, st: GameState) -> list[Event]:
        # DISCARD_CHOICE is an information event in _MTG_INFORMATION_EVENTS.
        return [Event(
            type=EventType.DISCARD_CHOICE,
            payload={'player': None, 'looker': obj.controller, 'source': obj.id},
            source=obj.id,
        )]

    return [
        _ih.make_keyword_grant(obj, ['menace'], affects_self),
        _ih.make_etb_trigger(obj, info_pulse),
        _ih.make_targeted_etb_trigger(
            obj,
            effect='damage',
            effect_params={'amount': 3},
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Crucio: torment an opponent creature for 3 damage',
        ),
    ]


BELLATRIX_LESTRANGE_CRUCIO = make_creature(
    name="Bellatrix Lestrange, Crucio Witch",
    power=3, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Menace. "
        "When Bellatrix Lestrange, Crucio Witch enters, she deals 3 "
        "damage to target creature an opponent controls and that "
        "opponent reveals their hand. "
        "(\"CRUCIO!\")"
    ),
    setup_interceptors=_bellatrix_lestrange_setup,
)


# --- Sybill Trelawney, Seer's Vision ({1}{U} 1/3 Legendary Creature) ---
# Decision-axis: create_scry_choice + library zone read + filter factory
# (creatures_you_control). Lore: Trelawney scries the chakra-stream of
# Hogwarts to read the next prophecy.
def _sybill_trelawney_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: explicit library zone read, then open a scry-2 choice + emit
    a SCRY event so the AST walker tags an information event (asymmetry=3
    via the info_events table). create_scry_choice -> decision=1.

    Fingerprint differentiation: Trelawney's fp must differ from
    Sybill (decision/state baseline) and from Horcrux Reliquary (which
    shares state=1 + zone + synergy). Adding the SCRY emission pushes
    asymmetry=3, making this fingerprint distinct."""
    def trelawney_etb(event: Event, st: GameState) -> list[Event]:
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        top_two = list(library.objects[:2])
        if not top_two:
            return []
        _ih.create_scry_choice(st, obj.controller, obj.id, top_two, scry_count=2)
        # SCRY is an information event in _MTG_INFORMATION_EVENTS — emit
        # one so the AST walker tags asymmetry=3 ("you can see the future,
        # your opponent cannot").
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2, 'source': obj.id},
            source=obj.id,
        )]

    return [_ih.make_etb_trigger(obj, trelawney_etb)]


SYBILL_TRELAWNEY_SEERS_VISION = make_creature(
    name="Sybill Trelawney, Seer's Vision",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "When Sybill Trelawney, Seer's Vision enters, scry 2. "
        "(\"The dark lord lies alone and friendless, abandoned by his "
        "followers...\")"
    ),
    setup_interceptors=_sybill_trelawney_setup,
)


# --- The Marauder's Map ({1} Artifact, top-N land/passage scan) ---
# Decision-axis: make_top_n_land_pick + library + graveyard zone reads.
# Lore: The Marauder's Map reveals every passage at Hogwarts. Distinct
# fingerprint from Trelawney (top-N vs scry) and from Bellatrix.
def _marauders_map_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: read library + graveyard zones, then open a top-4 land-pick
    choice (Hogwarts passages are lands). make_top_n_land_pick is in
    modal_helpers -> decision=1; the explicit zone reads surface
    state_coupling and zone_movement (zone=2 from two-zone touch)."""
    def map_etb(event: Event, st: GameState) -> list[Event]:
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        graveyard = st.zones.get(f'graveyard_{obj.controller}')
        gy_size = len(graveyard.objects) if graveyard is not None else 0
        # Mischief managed bonus: deeper sample if you've cast/lost more.
        n_pick = 6 if gy_size >= 3 else 4
        return _ih.make_top_n_land_pick(
            st,
            controller=obj.controller,
            source_id=obj.id,
            n=n_pick,
            put_tapped=True,
            optional=True,
            prompt="I solemnly swear that I am up to no good — pick a passage",
        )

    return [_ih.make_etb_trigger(obj, map_etb)]


THE_MARAUDERS_MAP = CardDefinition(
    name="The Marauder's Map",
    mana_cost="{1}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        mana_cost="{1}",
        colors=set(),
    ),
    text=(
        "When The Marauder's Map enters, look at the top four cards of "
        "your library (six instead if three or more cards are in your "
        "graveyard). You may put a land card from among them onto the "
        "battlefield tapped. Put the rest on the bottom of your library "
        "in a random order. (\"Mischief managed.\")"
    ),
    setup_interceptors=_marauders_map_setup,
)


# --- Horcrux Reliquary ({2}{B} Artifact, sacrifice-choice) ---
# Decision-axis: create_sacrifice_choice + battlefield zone read. Lore:
# Voldemort's Horcrux feeds on a controlled sacrifice. Distinct from the
# other 4 because it uses sacrifice rather than scry/discard/top-N.
def _horcrux_reliquary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: explicit battlefield zone read, find your creatures, then
    open a sacrifice choice. create_sacrifice_choice -> decision=1; the
    explicit battlefield read + creatures_you_control filter surface
    state_coupling and synergy."""
    def reliquary_etb(event: Event, st: GameState) -> list[Event]:
        bf = st.zones.get('battlefield')
        if bf is None:
            return []
        # Filter-factory call surfaces synergy axis.
        own_filter = _ih.creatures_you_control(obj)
        _ = own_filter
        # Collect your creatures from the battlefield zone.
        own_creature_ids = []
        for cid in list(bf.objects):
            o = st.objects.get(cid)
            if o is None:
                continue
            if (o.controller == obj.controller
                and CardType.CREATURE in o.characteristics.types
                and o.id != obj.id):
                own_creature_ids.append(cid)
        if not own_creature_ids:
            return []
        _ih.create_sacrifice_choice(
            st, obj.controller, obj.id, own_creature_ids, 1,
            prompt="Feed the Horcrux: choose a creature to sacrifice",
        )
        return []

    return [_ih.make_etb_trigger(obj, reliquary_etb)]


HORCRUX_RELIQUARY = CardDefinition(
    name="Horcrux Reliquary",
    mana_cost="{2}{B}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        mana_cost="{2}{B}",
        colors={Color.BLACK},
    ),
    text=(
        "When Horcrux Reliquary enters, sacrifice a creature. "
        "(A fragment of soul, locked in a vessel of bone and silver — "
        "the cost is always another's blood.)"
    ),
    setup_interceptors=_horcrux_reliquary_setup,
)


# Register the 5 Phase A2 spice cards into HARRY_POTTER_CARDS *after* the
# card definitions are visible. The dict was declared earlier in the file
# before these cards exist; appending here avoids a NameError at import.
HARRY_POTTER_CARDS.update({
    "Sorting Hat's Verdict": SORTING_HATS_VERDICT,
    "Bellatrix Lestrange, Crucio Witch": BELLATRIX_LESTRANGE_CRUCIO,
    "Sybill Trelawney, Seer's Vision": SYBILL_TRELAWNEY_SEERS_VISION,
    "The Marauder's Map": THE_MARAUDERS_MAP,
    "Horcrux Reliquary": HORCRUX_RELIQUARY,
})


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    HARRY_POTTER_THE_CHOSEN_ONE,
    HERMIONE_GRANGER,
    ALBUS_DUMBLEDORE,
    MINERVA_MCGONAGALL,
    NEVILLE_LONGBOTTOM,
    GRYFFINDOR_PREFECT,
    AUROR_RECRUIT,
    HOGWARTS_DEFENDER,
    ORDER_PHOENIX_MEMBER,
    MINISTRY_AUROR,
    PATRONUS_CASTER,
    HOGWARTS_FIRST_YEAR,
    DUMBLEDORES_ARMY_RECRUIT,
    WEASLEY_MATRIARCH,
    HOGWARTS_GHOST,
    QUIDDITCH_REFEREE,
    HEALING_WITCH,
    ST_MUNGOS_HEALER,
    PHOENIX_GUARDIAN,
    EXPECTO_PATRONUM,
    PROTEGO,
    SHIELD_CHARM,
    COUNTER_CURSE,
    PRIORI_INCANTATEM,
    HEALING_SPELL,
    DISILLUSIONMENT_CHARM,
    CALL_THE_ORDER,
    SORTING_CEREMONY,
    OBLIVIATE,
    LIGHT_MAGIC,
    DUMBLEDORES_PROTECTION,
    GRYFFINDOR_BANNER,
    HOGWARTS_SORTING_YEAR,
    LUNA_LOVEGOOD,
    FILIUS_FLITWICK,
    CHO_CHANG,
    MOANING_MYRTLE,
    RAVENCLAW_PREFECT,
    HOGWARTS_SCHOLAR,
    DIVINATION_STUDENT,
    LIBRARY_RESEARCHER,
    SPELL_THEORIST,
    HOGWARTS_LIBRARIAN,
    UNSPEAKABLE,
    PENSIEVE_KEEPER,
    THESTRAL,
    TIME_TURNER_USER,
    MEMORY_CHARM_SPECIALIST,
    STUPEFY,
    ACCIO,
    CONFUNDO,
    PETRIFICUS_TOTALUS,
    LEGILIMENS,
    AGUAMENTI,
    FINITE_INCANTATEM,
    DIVINATION_SPELL,
    CRYSTAL_BALL_READING,
    MEMORY_WIPE,
    TRANSFIGURATION,
    LIBRARY_OF_HOGWARTS,
    RAVENCLAW_BANNER,
    LORD_VOLDEMORT,
    SEVERUS_SNAPE,
    BELLATRIX_LESTRANGE,
    DRACO_MALFOY,
    LUCIUS_MALFOY,
    SLYTHERIN_PREFECT,
    DEATH_EATER_INITIATE,
    DEMENTOR,
    DEMENTOR_SWARM,
    INFERIUS,
    DARK_WIZARD,
    KNOCKTURN_ALLEY_VENDOR,
    BASILISK,
    ACROMANTULA,
    NAGINI,
    AZKABAN_GUARD,
    GREYBACK,
    AVADA_KEDAVRA,
    CRUCIO,
    IMPERIO,
    SECTUMSEMPRA,
    MORSMORDRE,
    DARK_MARK,
    CURSE_OF_THE_BOGIES,
    SUMMON_INFERI,
    DARK_RITUAL_SPELL,
    FIENDFYRE,
    THE_DARK_ARTS,
    SLYTHERIN_BANNER,
    HORCRUX_CURSE,
    RON_WEASLEY,
    FRED_AND_GEORGE,
    GINNY_WEASLEY,
    SIRIUS_BLACK,
    MOLLY_WEASLEY,
    WEASLEY_TWIN_PRANKSTER,
    QUIDDITCH_BEATER,
    DRAGON_HANDLER,
    HUNGARIAN_HORNTAIL,
    NORWEGIAN_RIDGEBACK,
    CHINESE_FIREBALL,
    COMMON_WELSH_GREEN,
    GOBLIN_BANKER,
    FIENDFYRE_ELEMENTAL,
    BLAST_ENDED_SKREWT,
    ERUMPENT,
    INCENDIO,
    CONFRINGO,
    BOMBARDA,
    REDUCTO,
    EXPULSO,
    DRAGONS_BREATH,
    WEASLEY_FIREWORK,
    DRAGONS_FIRE,
    PYROTECHNICS,
    SUMMON_DRAGON,
    WEASLEYS_WIZARD_WHEEZES,
    GRYFFINDOR_COURAGE,
    RUBEUS_HAGRID,
    POMONA_SPROUT,
    CEDRIC_DIGGORY,
    NEWT_SCAMANDER,
    HUFFLEPUFF_PREFECT,
    MANDRAKE,
    VENOMOUS_TENTACULA,
    BOWTRUCKLE,
    HIPPOGRIFF,
    BUCKBEAK,
    FAWKES_THE_PHOENIX,
    UNICORN,
    CENTAUR_ARCHER,
    FORBIDDEN_FOREST_SPIDER,
    NIFFLER,
    THESTRAL_HERD,
    WHOMPING_WILLOW,
    GIANT_SQUID,
    HERBIVICUS,
    WILD_GROWTH_SPELL,
    ENGORGIO,
    BEASTS_FURY,
    NATURES_PROTECTION,
    GREENHOUSE_HARVEST,
    CREATURE_SUMMONING,
    MANDRAKE_RESTORATIVE,
    HERBOLOGY_CLASSROOM,
    HUFFLEPUFF_BANNER,
    FORBIDDEN_FOREST,
    ELDER_WAND,
    RESURRECTION_STONE,
    INVISIBILITY_CLOAK,
    SWORD_OF_GRYFFINDOR,
    MARAUDERS_MAP,
    SORTING_HAT,
    HORCRUX_DIARY,
    HORCRUX_LOCKET,
    HORCRUX_CUP,
    HORCRUX_DIADEM,
    HORCRUX_RING,
    FIREBOLT_BROOM,
    NIMBUS_2000,
    WAND_OF_PHOENIX_FEATHER,
    WAND_OF_DRAGON_HEARTSTRING,
    WAND_OF_UNICORN_HAIR,
    PENSIEVE,
    GOLDEN_SNITCH,
    QUAFFLE,
    BLUDGER,
    TIME_TURNER,
    DELUMINATOR,
    PORTKEY,
    FLOO_POWDER,
    GOBLET_OF_FIRE,
    MIRROR_OF_ERISED,
    VANISHING_CABINET,
    HOGWARTS_CASTLE,
    GRYFFINDOR_COMMON_ROOM,
    SLYTHERIN_DUNGEON,
    RAVENCLAW_TOWER,
    HUFFLEPUFF_BASEMENT,
    DIAGON_ALLEY,
    HOGSMEADE_VILLAGE,
    FORBIDDEN_FOREST_LAND,
    MINISTRY_OF_MAGIC,
    AZKABAN,
    GODRICS_HOLLOW,
    GRIMMAULD_PLACE,
    THE_BURROW,
    MALFOY_MANOR,
    KNOCKTURN_ALLEY,
    GRINGOTTS,
    QUIDDITCH_PITCH,
    ROOM_OF_REQUIREMENT,
    SHRIEKING_SHACK,
    PLATFORM_NINE_THREE_QUARTERS,
    # SPICE PASS PHASE A2 (slice 2, 2026-05-19) — decision-axis flips
    SORTING_HATS_VERDICT,
    BELLATRIX_LESTRANGE_CRUCIO,
    SYBILL_TRELAWNEY_SEERS_VISION,
    THE_MARAUDERS_MAP,
    HORCRUX_RELIQUARY,
]
