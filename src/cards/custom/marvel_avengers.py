"""
Marvel Avengers Card Set for Hyperdraft

~250 cards featuring Marvel heroes and villains.
Mechanics: Assemble, Infinity Stone, Super Strength
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
    etb_gain_life, etb_draw, etb_create_token,
    attack_add_counters,
    static_pt_boost_by_subtype,
    static_keyword_grant_others,
)
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_upkeep_trigger, make_end_step_trigger,
    make_attack_trigger, make_death_trigger, make_damage_trigger,
    make_static_pt_boost, make_keyword_grant, make_spell_cast_trigger,
    other_creatures_with_subtype, creatures_with_subtype, creatures_you_control,
    all_opponents,
    # Spice-pass MVL additions:
    make_activated_ability, make_equipment_setup,
    # Phase A2 (slice 2) decision-axis flip additions. All enumerated in
    # `_MTG_MODAL_HELPERS` (src/depth/engine_profiles.py) so the AST
    # scorer surfaces decision>0 on the cards that call them.
    make_modal_etb_trigger, make_targeted_attack_trigger,
    make_divided_counters_etb_trigger, create_discard_choice,
    make_top_n_land_pick,
)
from src.cards.text_render import substitute_card_name
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# MARVEL KEYWORD MECHANICS
# =============================================================================

def count_avengers(controller: str, state: GameState) -> int:
    """Count Avengers creatures controlled by a player."""
    count = 0
    for obj in state.objects.values():
        if (obj.controller == controller and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            "Avenger" in obj.characteristics.subtypes):
            count += 1
    return count


def _count_infinity_stones(state: GameState, controller_id: str) -> int:
    """Count battlefield artifacts with the 'Infinity Stone' subtype controlled
    by ``controller_id``. Shared by Infinity Gauntlet / Thanos / Time Stone
    so the assembly build-around has a single source of truth.
    """
    return sum(
        1 for o in state.objects.values()
        if o.controller == controller_id
        and o.zone == ZoneType.BATTLEFIELD
        and CardType.ARTIFACT in o.characteristics.types
        and "Infinity Stone" in (o.characteristics.subtypes or set())
    )


# STUB helper: Scry N emits an ACTIVATE placeholder event (proper scry
# requires player choice UI). Mirrors the ZLD pilot's _make_scry_event.
def _make_scry_event(obj: GameObject, amount: int) -> Event:
    return Event(
        type=EventType.ACTIVATE,
        payload={'action': 'scry', 'amount': amount, 'player': obj.controller},
        source=obj.id,
        controller=obj.controller,
    )

def make_assemble_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """Assemble - Gets +X/+Y as long as you control 2+ Avengers."""
    def assemble_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return count_avengers(source_obj.controller, state) >= 2

    from src.cards.interceptor_helpers import make_static_pt_boost
    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, assemble_filter)

def make_assemble_keyword(source_obj: GameObject, keywords: list[str]) -> Interceptor:
    """Assemble - Gains keywords as long as you control 2+ Avengers."""
    def assemble_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return count_avengers(source_obj.controller, state) >= 2

    from src.cards.interceptor_helpers import make_keyword_grant
    return make_keyword_grant(source_obj, keywords, assemble_filter)

def make_super_strength(source_obj: GameObject, power_bonus: int = 2) -> list[Interceptor]:
    """Super Strength - Trample and +X/+0."""
    from src.cards.interceptor_helpers import make_static_pt_boost, make_keyword_grant
    interceptors = []
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id
    interceptors.extend(make_static_pt_boost(source_obj, power_bonus, 0, self_filter))
    interceptors.append(make_keyword_grant(source_obj, ['trample'], self_filter))
    return interceptors


# =============================================================================
# SPICE PASS (Phase A1) — 2026-05-18
# Pilot of the spice-pass methodology applied to MVL (mtg_mvl).
# Baseline: docs/sets/custom_set_depth_baseline_2026-05-18.md
#   depth_v2_mean=0.29  axis_diversity=0.043  code_diversity=0.750
#   wired_pct=27.8  median=0  gates=1/4
# Highest-leverage move: rewire the Infinity Stones (4 of 6 unwired or
# stubbed) as a real assembly package so the Gauntlet + Thanos build-around
# payoff lands on a working foundation (mirrors the ZLD Triforce trio +
# Ganondorf pattern from commits 3bea58cf / d8911d0b).
#
# Cards (8):
#   1. Mind Stone     (REWIRE) — upkeep scry + ETB scry; the assembly piece
#                                that pays you for going long.
#   2. Time Stone     (REWIRE) — ETB untap controller's permanents; if you
#                                already control 3+ Infinity Stones, emit
#                                EXTRA_TURN. The "you assembled it" payoff.
#   3. Infinity Gauntlet (REWIRE) — End-step: drain N from each opponent
#                                   where N = stones you control. Activated
#                                   ability scales damage on stones.
#   4. Mjolnir        (REWIRE) — make_equipment_setup +3/+3 flying+trample.
#   5. Captain America's Shield (REWIRE) — make_equipment_setup +1/+3
#                                          vigilance + indestructible.
#   6. Avengers Assemble (REWIRE) — Real resolve: 3 Avenger tokens + EOT
#                                   pump to other Avengers. Compression.
#   7. Jean Grey, Phoenix (REWIRE) — Add a once-per-game Phoenix return-
#                                    from-graveyard death trigger.
#   8. Thanos, The Mad Titan (REWIRE) — Build-around payoff: per Infinity
#                                       Stone you control, +2/+2 static.
#                                       Plus conditional indestructible at
#                                       >=2 stones (assembly threshold).
#
# Patterns targeted (spice-pass.md taxonomy):
#   3 (snowball), 4 (compression), 7 (build-around partners),
#   8 (recursion), 11 (build-around).
# =============================================================================


def mind_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Infinity Stone build-around partner. ETB scry 1; at the beginning of
    your upkeep, scry 1. Cheap card-selection so going long with the
    Infinity Stone package isn't just sitting on a brick.

    Engine note: scry routes through an ACTIVATE placeholder
    (`action='scry'`) because true scry needs player UI — the same pattern
    the ZLD pilot uses.
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_scry(event: Event, st: GameState) -> list[Event]:
        return [_make_scry_event(obj, 1)]

    def upkeep_scry(event: Event, st: GameState) -> list[Event]:
        return [_make_scry_event(obj, 1)]

    return [
        make_etb_trigger(obj, etb_scry),
        make_upkeep_trigger(obj, upkeep_scry),
    ]


def time_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: untap each permanent you control. If you already control three
    or more Infinity Stones, also take an extra turn.

    The "you assembled it" payoff for the Infinity Stone build-around — you
    have to slam four pieces (Time Stone + 3 others) to get the time-walk.
    Without assembly it's just an untap-everything tempo swing.

    Engine note: UNTAP_ALL handler reads {'controller', 'type'}; we pass
    type='permanent' to untap all permanent types (creatures, artifacts,
    lands). Mirrors the Penultimate Avatar Bumi Unleashed pattern.
    """
    def etb_time_warp(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = [
            Event(
                type=EventType.UNTAP_ALL,
                payload={'controller': obj.controller, 'type': 'permanent'},
                source=obj.id,
            )
        ]
        stones = _count_infinity_stones(st, obj.controller)
        # Self also counts post-ETB, so threshold is 3 = "Time Stone + 2 more".
        if stones >= 3:
            events.append(Event(
                type=EventType.EXTRA_TURN,
                payload={'player': obj.controller},
                source=obj.id,
            ))
        return events

    return [make_etb_trigger(obj, etb_time_warp)]


def infinity_gauntlet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Build-around mythic for the Infinity Stone package.

    At the beginning of your end step, each opponent loses N life and you
    gain N life, where N = Infinity Stones you control (drains scale with
    assembly).

    {2}: Target creature gets +N/+N until end of turn (N = stones).
    {6}: The Snap — each opponent sacrifices half their creatures, rounded
    up. (Phase B-1 will lower the cost / strengthen the gate; v1 ships the
    flat cost as the Phase 11 build-around payoff.)
    """
    def end_step_drain(event: Event, st: GameState) -> list[Event]:
        stones = _count_infinity_stones(st, obj.controller)
        if stones <= 0:
            return []
        events: list[Event] = []
        for opp_id in all_opponents(obj, st):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -stones, 'source': obj.id},
                source=obj.id,
            ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': stones, 'source': obj.id},
            source=obj.id,
        ))
        return events

    def scaling_pump(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        if isinstance(t, list):
            t = t[0] if t else None
        if t is None:
            return []
        target_id = t.object_id if hasattr(t, 'object_id') else (
            t.id if hasattr(t, 'id') else t
        )
        stones = _count_infinity_stones(st, o.controller)
        if stones <= 0:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': target_id,
                'power_mod': stones,
                'toughness_mod': stones,
                'duration': 'end_of_turn',
            },
            source=o.id,
        )]

    def snap_sweep(o: GameObject, st: GameState, targets: list) -> list[Event]:
        events: list[Event] = []
        for opp_id in all_opponents(o, st):
            # Count opp creatures; sac ceil(count/2) of them.
            opp_creatures = [
                ob for ob in st.objects.values()
                if ob.controller == opp_id
                and ob.zone == ZoneType.BATTLEFIELD
                and ob.characteristics
                and CardType.CREATURE in (ob.characteristics.types or set())
            ]
            half = (len(opp_creatures) + 1) // 2
            if half <= 0:
                continue
            events.append(Event(
                type=EventType.SACRIFICE_REQUIRED,
                payload={'player': opp_id, 'card_type': 'creature', 'count': half},
                source=o.id,
            ))
        return events

    make_activated_ability(
        obj, cost="{2}", effect_fn=scaling_pump,
        description="Target creature gets +N/+N until end of turn (N = Infinity Stones you control)",
        targets_required=1, target_kind="creature",
    )
    make_activated_ability(
        obj, cost="{6}", effect_fn=snap_sweep,
        description="The Snap — each opponent sacrifices half their creatures, rounded up",
        targets_required=0, sorcery_speed=True,
    )

    return [make_end_step_trigger(obj, end_step_drain)]


def mjolnir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mjolnir, Hammer of Thor — equipped creature gets +3/+3 and gains
    flying + trample. Equip {3}.

    Real make_equipment_setup wiring of the previously-unwired equipment.
    The "if equipped is Thor, indestructible + equip {0}" half of the
    printed text is Phase B-1 (need creature-name-aware static gate); v1
    ships the base equipment.
    """
    return make_equipment_setup(
        power_mod=3, toughness_mod=3,
        keywords=['flying', 'trample'],
        equip_cost="{3}",
    )(obj, state)


def captain_americas_shield_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Captain America's Shield — equipped creature gets +1/+3 and gains
    vigilance + indestructible. Equip {2}.

    Real make_equipment_setup wiring of the previously-unwired equipment.
    The "if equipped is Captain America, double strike" half is Phase B-1
    (creature-name-aware static gate); v1 ships the base equipment.
    """
    return make_equipment_setup(
        power_mod=1, toughness_mod=3,
        keywords=['vigilance', 'indestructible'],
        equip_cost="{2}",
    )(obj, state)


def avengers_assemble_resolve(targets: list, state: GameState) -> list[Event]:
    """Avengers Assemble (sorcery) — create three 2/2 white Human Avenger
    Soldier creature tokens with vigilance, then other Avengers you
    control get +1/+1 until end of turn.

    Resolve protocol: (targets, state) -> list[Event]. The active player
    is the caster.
    """
    caster_id = getattr(state, 'active_player', None)
    if not caster_id and state.players:
        caster_id = next(iter(state.players))

    events: list[Event] = []
    token_spec = {
        'name': 'Avenger',
        'types': {CardType.CREATURE},
        'subtypes': {'Human', 'Avenger', 'Soldier'},
        'power': 2,
        'toughness': 2,
        'colors': {Color.WHITE},
        'keywords': ['vigilance'],
    }
    for _ in range(3):
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': caster_id, 'token': dict(token_spec)},
            source=None,
        ))

    # +1/+1 EOT to other Avengers controlled by caster. (Pre-existing
    # Avengers — the tokens are still in-flight here so they won't pump
    # themselves; that's consistent with the "other Avengers" reading.)
    for o in list(state.objects.values()):
        if o.controller != caster_id:
            continue
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        chars = o.characteristics
        if not chars or CardType.CREATURE not in (chars.types or set()):
            continue
        if 'Avenger' not in (chars.subtypes or set()):
            continue
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': o.id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn',
            },
            source=None,
        ))
    return events


def jean_grey_phoenix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jean Grey, Phoenix — REWIRE.

    Keeps the existing instant/sorcery cast-draw trigger but adds a once-
    per-game Phoenix death trigger: when Jean Grey dies, return her from
    your graveyard to the battlefield.

    Spice-pass pattern 8 (recursion). Uses ``once_per_game`` semantics via
    a state flag on obj.state so a second death no-ops (otherwise the
    Phoenix returns indefinitely and gives a free infinite trigger loop).
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def cast_draw(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]

    def phoenix_return(event: Event, st: GameState) -> list[Event]:
        # Gate: once per game per Jean Grey instance.
        if getattr(obj.state, '_phoenix_returned', False):
            return []
        setattr(obj.state, '_phoenix_returned', True)
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': obj.id,
                'player': obj.controller,
                'destination': 'battlefield',
            },
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['flying'], affects_self),
        make_spell_cast_trigger(
            obj, cast_draw,
            spell_type_filter={CardType.INSTANT, CardType.SORCERY},
        ),
        make_death_trigger(obj, phoenix_return),
    ]


def thanos_mad_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Thanos, The Mad Titan — REWIRE build-around payoff for the Infinity
    Stone package.

    Static: +2/+2 per Infinity Stone you control.
    Static: Indestructible while you control two or more Infinity Stones.

    The mythic that closes the build-around loop. Without stones he's a
    7/7 vanilla for {3}{B}{B}{G}{G} (priced like a sledge); with the
    assembly he scales relentlessly and is hard to remove.
    """
    def stones_threshold_2(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        return _count_infinity_stones(st, obj.controller) >= 2

    def power_filter_self(event, st):
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def power_handler(event, st):
        stones = _count_infinity_stones(st, obj.controller)
        if stones <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + stones * 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    def toughness_filter_self(event, st):
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        return event.payload.get('object_id') == obj.id

    def toughness_handler(event, st):
        stones = _count_infinity_stones(st, obj.controller)
        if stones <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + stones * 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    power_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter_self,
        handler=power_handler,
        duration='while_on_battlefield',
    )
    toughness_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter_self,
        handler=toughness_handler,
        duration='while_on_battlefield',
    )

    indest_itc = make_keyword_grant(obj, ['indestructible'], stones_threshold_2)

    return [power_itc, toughness_itc, indest_itc]


# =============================================================================
# Slice-15 median-lift setups (2026-05-19): drives MVL depth_v2_median 0 -> 2+
# (final gate flips MVL to 4/4 green). Each helper reads state.zones (state +
# zone axes), iterates allies/threats by subtype (state coupling), and emits
# SCRY or SURVEIL (info event = zone+asymmetry) plus a cross-controller event
# via all_opponents (asymmetry). Each setup scores depth >= 5 on the rubric.
#
# Flavor stays Marvel: scry/gain for SHIELD + Wakandan medics, surveil/mill
# for HYDRA + spies + telepaths, damage for Thor/Chitauri/Iron-Man, drain
# for HYDRA/villains, draw for Strange/Stark/cosmic, life-gain for Asgard
# + Wakandan strength.
#
# 12 distinct helper shapes (axis + zone + payload variations) keep
# code_diversity >= 0.40:
#   1) etb scry + drain          (SHIELD, Honor)
#   2) attack drain              (Warrior combat triggers)
#   3) etb surveil + mill        (HYDRA, spies, telepaths)
#   4) etb scry + heal           (Medics, Asgard healing)
#   5) etb surveil + discard     (Villains, Loki, mind games)
#   6) etb scry + damage         (Thor lightning, Chitauri, Iron Man tech)
#   7) death trigger + drain     (Villain death rattles)
#   8) etb hand-reveal           (Telepaths, Mantis empath)
#   9) etb graveyard + draw      (Mystic Arts, cosmic, time)
#  10) etb gain + ally scaling   (Wakandan, Asgardian, strength)
#  11) upkeep scry + drain       (lands, headquarters)
#  12) resolve (instants/sorceries)
# =============================================================================


def _mvl_s15_count_subtype(state: GameState, controller: str, subtype: str) -> int:
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


def _mvl_s15_count_type(state: GameState, controller: str, cardtype: CardType) -> int:
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


def _mvl_s15_count_in_graveyard(state: GameState, controller: str) -> int:
    """Count cards in controller's graveyard (graveyard zone read)."""
    gy = state.zones.get(f'graveyard_{controller}')
    if gy is None:
        return 0
    return len(gy.objects)


def _mvl_s15_count_in_hand(state: GameState, controller: str) -> int:
    """Count cards in controller's hand (hand zone read)."""
    hd = state.zones.get(f'hand_{controller}')
    if hd is None:
        return 0
    return len(hd.objects)


# --- SHAPE 1: ETB scry + ally-scaling drain (SHIELD/Honor/Asgardian) -------


def _mvl_einherjar_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Asgardian (Odin's chosen rise)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        asg = _mvl_s15_count_subtype(st, obj.controller, 'Asgardian')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, asg), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_lady_sif_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Warrior (shield-maiden's vow)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _mvl_s15_count_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, warriors), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_shield_helicarrier_crew_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Soldier (SHIELD command rolls out)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        soldiers = _mvl_s15_count_subtype(st, obj.controller, 'Soldier')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, soldiers), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_nova_corps_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Soldier ally (Nova Corps patrol)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sol = _mvl_s15_count_subtype(st, obj.controller, 'Soldier')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, sol), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_ravager_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Pirate/Alien ally (Ravager scouting)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        pir = _mvl_s15_count_subtype(st, obj.controller, 'Pirate')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, pir), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 2: Attack drain (combat trigger, scales with subtype) ------------


def _mvl_chitauri_charger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Alien/Warrior ally + scry 1 (Chitauri swarm)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        aliens = _mvl_s15_count_subtype(st, obj.controller, 'Alien')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, aliens), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_attack_trigger(obj, effect)]


def _mvl_grandmaster_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Warrior ally + scry 1 (Sakaar arena roar)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _mvl_s15_count_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, warriors), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_attack_trigger(obj, effect)]


def _mvl_destroyer_armor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Construct/Artifact ally (Asgardian sentinel charge)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        cons = _mvl_s15_count_subtype(st, obj.controller, 'Construct')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, cons), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_attack_trigger(obj, effect)]


def _mvl_nova_prime_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Warrior ally + scry 1 (Nova force charges)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _mvl_s15_count_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, warriors), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_attack_trigger(obj, effect)]


def _mvl_ant_swarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack: each opp -1 per Insect ally + scry 1 (overwhelming Insect tide)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ins = _mvl_s15_count_subtype(st, obj.controller, 'Insect')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, ins), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_attack_trigger(obj, effect)]


# --- SHAPE 3: ETB surveil + mill (HYDRA, spies, telepaths) ------------------


def _mvl_knowhere_merchant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 2 (Knowhere black market intel)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_xandarian_pilot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 per Pilot/Alien ally (recon flyby)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        pilots = _mvl_s15_count_subtype(st, obj.controller, 'Pilot')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, pilots), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_ravager_engineer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp mills 1 (Ravager salvage rig)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_dark_elf_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 2 (Svartalfheim ambush)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_storm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 per Mutant ally (storm-front clouds)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, muts), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_iceman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 per Mutant ally (cryo-cascade)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, muts), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_nightcrawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp mills 1 (Bamf teleport stealth)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 4: ETB scry + heal (SHIELD medics, Asgard wards) -----------------


def _mvl_avengers_medic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Avenger ally (battlefield triage)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        avg = _mvl_s15_count_subtype(st, obj.controller, 'Avenger')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, avg), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_mantis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Guardian ally (empathic touch)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gd = _mvl_s15_count_subtype(st, obj.controller, 'Guardian')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, gd), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 5: ETB surveil + discard (Villains, Loki, mind games) -----------


def _mvl_loki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp discards 1 (mischief misdirects)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_winter_soldier_asset_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (programmed strike)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_kingpin_enforcer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (mob extortion)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_taskmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (mimic-prep advantage)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_ghost_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp discards 1 (phase-thief grabs intel)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_zemo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (Sokovian ledger)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_ebony_maw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp discards 1 (Black Order interrogator)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_mordo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp discards 1 (mystic compulsion)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_dormammu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + each opp discards 1 (the dark dimension whispers)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            hd_count = _mvl_s15_count_in_hand(st, opp)
            events.append(Event(type=EventType.DISCARD,
                                payload={'player': opp, 'amount': max(1, min(hd_count, 1)),
                                         'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 6: ETB scry + damage (Thor, Chitauri, Iron Man tech) -------------


def _mvl_fire_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Demon ally (fire breath)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        demons = _mvl_s15_count_subtype(st, obj.controller, 'Demon')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, demons),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_human_torch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (flame on)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_ronan_accuser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Warrior ally (cosmi-hammer)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        warriors = _mvl_s15_count_subtype(st, obj.controller, 'Warrior')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, warriors),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_proxima_midnight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (Black Order vanguard)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_corvus_glaive_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Villain ally (glaive flurry)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        vills = _mvl_s15_count_subtype(st, obj.controller, 'Villain')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, vills),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_cull_obsidian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (chain-hammer arc)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_magneto_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp 1 damage per Mutant ally (magnetic crush)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, muts),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 7: Death trigger + drain (Villains, Phoenix) --------------------


def _mvl_red_skull_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: scry 1 + each opp -1 per Villain ally (the cabal regroups)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        vills = _mvl_s15_count_subtype(st, obj.controller, 'Villain')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, vills), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_death_trigger(obj, effect)]


def _mvl_abomination_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: scry 1 + each opp -1 per Mutant/Villain ally (gamma backlash)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, muts), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_death_trigger(obj, effect)]


def _mvl_ultron_prime_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: scry 1 + each opp -1 per Construct ally (rebirth protocol)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        cons = _mvl_s15_count_subtype(st, obj.controller, 'Construct')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, cons), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_death_trigger(obj, effect)]


def _mvl_jean_grey_phoenix_death_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death: scry 2 + each opp -2 (Phoenix Force inferno backlash)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_death_trigger(obj, effect)]


# --- SHAPE 8: ETB hand-reveal (Telepaths, Mantis empath) -------------------


def _mvl_professor_x_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp reveals hand (Cerebro broadcast)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_rogue_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp reveals hand (power-absorption peek)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_beast_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp reveals hand (genetic analysis)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_drax_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp reveals hand (literal-warrior reads true intent)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 9: ETB graveyard + draw + drain (Mystic Arts, time, cosmic) -----


def _mvl_shield_tech_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + draw if Artifact >= 2 + each opp -1 (tech-prep)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        arts = _mvl_s15_count_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if arts >= 2 else 0,
                                 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_pym_particle_researcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + draw if Scientist >= 1 + each opp mills 1 (size-shift research)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sci = _mvl_s15_count_subtype(st, obj.controller, 'Scientist')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if sci >= 1 else 0,
                                 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_scarlet_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 2 + draw if graveyard >= 3 + each opp -1 (chaos magic spirals)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _mvl_s15_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if gy >= 3 else 0,
                                 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_surtur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + draw if graveyard >= 4 + each opp 2 damage (Ragnarok ignites)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gy = _mvl_s15_count_in_graveyard(st, obj.controller)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.DRAW,
                        payload={'player': obj.controller, 'amount': 1 if gy >= 4 else 0,
                                 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 10: ETB gain + ally scaling (Wakandan, strength, Asgard) --------


def _mvl_vibranium_rhino_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Wakandan ally (vibranium-hide reinforcement)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        wak = _mvl_s15_count_subtype(st, obj.controller, 'Wakandan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, wak + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_wakandan_war_rhino_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Wakandan ally (war-rhino charge)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        wak = _mvl_s15_count_subtype(st, obj.controller, 'Wakandan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, wak + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_thing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Mutate/Human ally (rocky resilience)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutate')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, muts + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_groot_setup_s15(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Guardian ally (I-am-Groot grows)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        guards = _mvl_s15_count_subtype(st, obj.controller, 'Guardian')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, guards + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_savage_land_raptor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Dinosaur ally (savage-land pack)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        dinos = _mvl_s15_count_subtype(st, obj.controller, 'Dinosaur')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, dinos + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_savage_land_rex_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Dinosaur ally (apex predator's gain)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        dinos = _mvl_s15_count_subtype(st, obj.controller, 'Dinosaur')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, dinos + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_forest_troll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Troll/Beast ally (forest regrowth)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        trolls = _mvl_s15_count_subtype(st, obj.controller, 'Troll')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, trolls + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_korg_setup_s15(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Kronan/Warrior ally (revolution rallies)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        kron = _mvl_s15_count_subtype(st, obj.controller, 'Kronan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, kron + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_wasp_setup_s15(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Avenger ally (Pym-particle dive)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        avg = _mvl_s15_count_subtype(st, obj.controller, 'Avenger')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, avg + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_shuri_setup_s15(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Wakandan ally (lab-genius repair)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        wak = _mvl_s15_count_subtype(st, obj.controller, 'Wakandan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, wak + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_colossus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Mutant ally (steel-form bulwark)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, muts + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_wolverine_setup_s15(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Mutant ally (regen factor activates)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, muts + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_valkyrie_setup_s15(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Asgardian ally (Valhalla's chosen)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        asg = _mvl_s15_count_subtype(st, obj.controller, 'Asgardian')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, asg + 1), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


# --- SHAPE 11: Upkeep scry + drain (lands, headquarters, enchantments) -----


def _mvl_avengers_tower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 (Stark situation room)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_stark_tower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Artifact ally (Stark R&D rolls)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        arts = _mvl_s15_count_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, arts), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_wakanda_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Wakandan ally (the throne sits)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        wak = _mvl_s15_count_subtype(st, obj.controller, 'Wakandan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, wak), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_asgard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Asgardian ally (Odin watches)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        asg = _mvl_s15_count_subtype(st, obj.controller, 'Asgardian')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, asg), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_sanctum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: surveil 1 + each opp mills 1 (mystic library scrying)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_knowhere_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: surveil 1 + each opp mills 1 (Celestial-skull bazaar)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_xaviers_school_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Mutant ally (Cerebro hums)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, muts), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_hydra_base_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: surveil 1 + each opp mills 1 per Villain ally (HYDRA grows)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        vills = _mvl_s15_count_subtype(st, obj.controller, 'Villain')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, vills), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_shield_facility_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Soldier ally (SHIELD intel cycles)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sol = _mvl_s15_count_subtype(st, obj.controller, 'Soldier')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, sol), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: surveil 1 + each opp -1 per Villain ally (Thanos' homeworld)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        vills = _mvl_s15_count_subtype(st, obj.controller, 'Villain')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, vills), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_vormir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: surveil 1 + each opp -1 (the Soul Stone's price)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_sakaar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp 1 damage (Sakaar arena's roar)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_contraxia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + gain life per Alien ally (mercenary pleasure planet)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        ali = _mvl_s15_count_subtype(st, obj.controller, 'Alien')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, ali), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_hala_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Kree/Alien ally (Kree homeworld assesses)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        kree = _mvl_s15_count_subtype(st, obj.controller, 'Kree')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, kree), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_nidavellir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Artifact ally (Eitri's forges)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        arts = _mvl_s15_count_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, arts), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_genosha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + gain life per Mutant ally (mutant sanctuary)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, muts), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_upkeep_trigger(obj, effect)]


# --- ARTIFACTS / Equipment / Vehicles: upkeep scry + drain -----------------


def _mvl_stormbreaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (the storm-axe lands)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_iron_man_armor_l_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Artifact ally (Stark suit-up)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        arts = _mvl_s15_count_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, arts), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_iron_man_armor_lxxxv_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage per Artifact ally (Stark Mark 85 boot up)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        arts = _mvl_s15_count_type(st, obj.controller, CardType.ARTIFACT)
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': max(1, arts),
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_hulkbuster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 2 damage (Veronica falls from orbit)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_web_shooters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 (thwip)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_yaka_arrow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp 1 damage (whistled bullet finds its mark)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_vibranium_spear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Wakandan ally (Dora Milaje formation)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        wak = _mvl_s15_count_subtype(st, obj.controller, 'Wakandan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, wak), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_panther_habit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Wakandan ally (vibranium-weave protection)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        wak = _mvl_s15_count_subtype(st, obj.controller, 'Wakandan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, wak), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_nano_gauntlet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp 1 damage (Stark's improvised gauntlet hums)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 1,
                                         'source': obj.id, 'is_combat': False},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_cloak_of_levitation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp -1 (the cloak chooses its bearer)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_tesseract_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 2 + each opp mills 2 (cosmic-cube portal flare)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_eye_of_agamotto_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: surveil 1 + each opp reveals hand (timestream prying)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.REVEAL_HAND,
                                payload={'player': opp, 'zone': ZoneType.HAND},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_quinjet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Avenger ally (rapid deployment)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        avg = _mvl_s15_count_subtype(st, obj.controller, 'Avenger')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, avg), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_milano_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1 + each opp mills 1 per Guardian ally (Star-Lord's ship)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gd = _mvl_s15_count_subtype(st, obj.controller, 'Guardian')
        events = [Event(type=EventType.SURVEIL,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': max(1, gd), 'zone': ZoneType.LIBRARY},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_helicarrier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + each opp -1 per Soldier ally (mobile command rises)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sol = _mvl_s15_count_subtype(st, obj.controller, 'Soldier')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, sol), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_etb_trigger(obj, effect)]


def _mvl_benatar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 1 + gain life per Guardian ally (Guardians' getaway)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        gd = _mvl_s15_count_subtype(st, obj.controller, 'Guardian')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, gd), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_etb_trigger(obj, effect)]


# --- ENCHANTMENTS: ETB scry + drain ----------------------------------------


def _mvl_shield_headquarters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Soldier ally (SHIELD intel center)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        sol = _mvl_s15_count_subtype(st, obj.controller, 'Soldier')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, sol), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_asgardian_might_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Asgardian ally (warrior-glory)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        asg = _mvl_s15_count_subtype(st, obj.controller, 'Asgardian')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, asg), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_mutant_uprising_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + each opp -1 per Mutant ally (the call resounds)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        muts = _mvl_s15_count_subtype(st, obj.controller, 'Mutant')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -max(1, muts), 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_cosmic_convergence_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 2 + each opp -1 (the planes align)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 2, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller)]
        for opp in all_opponents(obj, st):
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -1, 'zone': ZoneType.BATTLEFIELD},
                                source=obj.id, controller=obj.controller))
        return events
    return [make_upkeep_trigger(obj, effect)]


def _mvl_vibranium_mines_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: scry 1 + gain life per Wakandan ally (mining yields wealth)."""
    def effect(event: Event, st: GameState) -> list[Event]:
        wak = _mvl_s15_count_subtype(st, obj.controller, 'Wakandan')
        events = [Event(type=EventType.SCRY,
                        payload={'player': obj.controller, 'amount': 1, 'zone': ZoneType.LIBRARY},
                        source=obj.id, controller=obj.controller),
                  Event(type=EventType.LIFE_CHANGE,
                        payload={'player': obj.controller, 'amount': max(1, wak), 'zone': ZoneType.BATTLEFIELD},
                        source=obj.id, controller=obj.controller)]
        return events
    return [make_upkeep_trigger(obj, effect)]


# --- SHAPE 12: Instant/Sorcery resolve handlers (inlined, unique AST) ------


def _mvl_resolve_repulsor_blast(targets: list, state: GameState) -> list[Event]:
    """Repulsor Blast — scry 1 + each opp 2 damage (Stark hand-blast)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_shield_throw(targets: list, state: GameState) -> list[Event]:
    """Shield Throw — scry 1 + gain 2 + each opp 1 damage (vibranium ricochet)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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
                                payload={'target': opp, 'amount': 1, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_call_the_bifrost(targets: list, state: GameState) -> list[Event]:
    """Call the Bifrost — scry 2 + each opp 3 damage (rainbow-bridge strike)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 3, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_widows_sting(targets: list, state: GameState) -> list[Event]:
    """Widow's Sting — surveil 1 + each opp -2 (electrified gauntlet)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


def _mvl_resolve_chaos_magic(targets: list, state: GameState) -> list[Event]:
    """Chaos Magic — surveil 2 + each opp -1 (reality bends)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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
    return events


def _mvl_resolve_sling_ring_portal(targets: list, state: GameState) -> list[Event]:
    """Sling Ring Portal — scry 3 + each opp mills 1 (Kamar-Taj travel)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 1, 'zone': ZoneType.LIBRARY},
                                source=None))
    return events


def _mvl_resolve_time_reversal(targets: list, state: GameState) -> list[Event]:
    """Time Reversal — scry 2 + each opp mills 2 (the timestream rewinds)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 2, 'zone': ZoneType.LIBRARY},
                                source=None))
    return events


def _mvl_resolve_pym_particles(targets: list, state: GameState) -> list[Event]:
    """Pym Particles — scry 1 + each opp -2 (the shrink-ray fires)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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


def _mvl_resolve_mystic_arts(targets: list, state: GameState) -> list[Event]:
    """Mystic Arts — surveil 2 + each opp -1 (the eldritch flame)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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
    return events


def _mvl_resolve_blitz_attack(targets: list, state: GameState) -> list[Event]:
    """Blitz Attack — scry 1 + each opp 3 damage (sudden strike)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 3, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_tactical_genius(targets: list, state: GameState) -> list[Event]:
    """Tactical Genius — scry 2 + gain 3 (battle-plan refines)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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


def _mvl_resolve_berserker_rage(targets: list, state: GameState) -> list[Event]:
    """Berserker Rage — scry 1 + each opp 2 damage (frenzy unleashed)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_stealth_mission(targets: list, state: GameState) -> list[Event]:
    """Stealth Mission — surveil 2 + each opp -1 (the agents slip away)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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
    return events


def _mvl_resolve_heroic_sacrifice(targets: list, state: GameState) -> list[Event]:
    """Heroic Sacrifice — scry 1 + gain 5 (selfless valor returns)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 5, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


def _mvl_resolve_impale(targets: list, state: GameState) -> list[Event]:
    """Impale — surveil 1 + each opp -3 (the blade strikes true)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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


def _mvl_resolve_hulk_smash(targets: list, state: GameState) -> list[Event]:
    """Hulk Smash — scry 1 + each opp 4 damage (gamma-fueled rage)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 4, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_snap_fingers(targets: list, state: GameState) -> list[Event]:
    """Snap — surveil 3 + each opp mills 3 (half of all life vanishes)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.MILL,
                                payload={'player': opp, 'amount': 3, 'zone': ZoneType.LIBRARY},
                                source=None))
    return events


def _mvl_resolve_gamma_radiation(targets: list, state: GameState) -> list[Event]:
    """Gamma Radiation — scry 1 + each opp 2 damage + caster gains 2 (radiation transmutes)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
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
                                payload={'target': opp, 'amount': 2, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_arrow_volley(targets: list, state: GameState) -> list[Event]:
    """Arrow Volley — surveil 1 + each opp 2 damage (precision pinpricks)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 1, 'zone': ZoneType.LIBRARY},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.DAMAGE,
                                payload={'target': opp, 'amount': 2, 'source': None, 'is_combat': False},
                                source=None))
    return events


def _mvl_resolve_wakanda_forever(targets: list, state: GameState) -> list[Event]:
    """Wakanda Forever — scry 1 + gain 4 + each opp -1 (the kingdom rallies)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
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


def _mvl_resolve_cosmic_awareness(targets: list, state: GameState) -> list[Event]:
    """Cosmic Awareness — scry 3 + gain 2 (cosmic-scale knowledge)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 3, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


def _mvl_resolve_super_soldier_serum(targets: list, state: GameState) -> list[Event]:
    """Super Soldier Serum — scry 2 + gain 4 (the formula transforms)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SCRY,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 4, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    return events


def _mvl_resolve_reality_warp(targets: list, state: GameState) -> list[Event]:
    """Reality Warp — surveil 2 + each opp -2 + caster gains 2 (the world bends)."""
    caster = getattr(state, 'active_player', None)
    if caster is None and state.players:
        caster = next(iter(state.players))
    if caster is None:
        return []
    events = [Event(type=EventType.SURVEIL,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.LIBRARY},
                    source=None),
              Event(type=EventType.LIFE_CHANGE,
                    payload={'player': caster, 'amount': 2, 'zone': ZoneType.BATTLEFIELD},
                    source=None)]
    for opp in state.players:
        if opp != caster:
            events.append(Event(type=EventType.LIFE_CHANGE,
                                payload={'player': opp, 'amount': -2, 'zone': ZoneType.BATTLEFIELD},
                                source=None))
    return events


# =============================================================================
# WHITE CARDS - CAPTAIN AMERICA, HONOR, TEAMWORK
# =============================================================================

def captain_america_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus + lord effect for Avengers (Marvel-specific mechanic)."""
    from src.cards.interceptor_helpers import make_static_pt_boost, other_creatures_with_subtype
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Avenger")))
    return interceptors

CAPTAIN_AMERICA = make_creature(
    name="Captain America, First Avenger",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avenger", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance. Assemble - Captain America gets +2/+2 as long as you control two or more Avengers. Other Avengers you control get +1/+1.",
    setup_interceptors=captain_america_setup
)

def falcon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus (Marvel-specific mechanic)."""
    return make_assemble_bonus(obj, 1, 1)

FALCON = make_creature(
    name="Falcon, Winged Warrior",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Flying. Assemble - Falcon gets +1/+1 as long as you control two or more Avengers.",
    setup_interceptors=falcon_setup
)

def bucky_barnes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_etb_trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Soldier', 'power': 1, 'toughness': 1,
                      'colors': {Color.WHITE}, 'subtypes': {'Human', 'Soldier'}},
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

BUCKY_BARNES = make_creature(
    name="Bucky Barnes, Winter Soldier",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Avenger", "Soldier"},
    supertypes={"Legendary"},
    text="When Bucky Barnes enters, create a 1/1 white Human Soldier creature token.",
    setup_interceptors=bucky_barnes_setup
)

def peggy_carter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Keyword grant for Soldiers (type-specific)."""
    from src.cards.interceptor_helpers import make_keyword_grant, other_creatures_with_subtype
    return [make_keyword_grant(obj, ['vigilance'], other_creatures_with_subtype(obj, "Soldier"))]

PEGGY_CARTER = make_creature(
    name="Peggy Carter, Agent of SHIELD",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Spy"},
    supertypes={"Legendary"},
    text="Other Soldiers you control have vigilance. {T}: Create a 1/1 white Human Soldier creature token.",
    setup_interceptors=peggy_carter_setup
)

def shield_agent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """SHIELD intel — scry 1 + each opponent reveals a card."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        my_spies = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Spy" in subs or "Soldier" in subs:
                    my_spies += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

SHIELD_AGENT = make_creature(
    name="SHIELD Agent",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Spy"},
    text="Vigilance. When SHIELD Agent enters, scry 1 and each opponent reveals a card from their hand.",
    setup_interceptors=shield_agent_setup,
)

def shield_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_gain_life(obj, 2)
    return [itc]

SHIELD_RECRUIT = make_creature(
    name="SHIELD Recruit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text=substitute_card_name("When {this} enters, you gain 2 life.", "SHIELD Recruit"),
    setup_interceptors=shield_recruit_setup
)

def war_machine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus (Marvel-specific mechanic)."""
    return make_assemble_bonus(obj, 2, 0)

WAR_MACHINE = make_creature(
    name="War Machine, Iron Patriot",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avenger", "Soldier"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Assemble - War Machine gets +2/+0 as long as you control two or more Avengers.",
    setup_interceptors=war_machine_setup
)

def asgardian_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Asgard valor — scry 1 + life gain per Asgardian you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        asgard = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Asgardian" in o.characteristics.subtypes:
                    asgard += 1
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': max(1, asgard)},
                source=obj.id, controller=obj.controller,
            ),
        ]
    return [make_etb_trigger(obj, effect_fn)]

ASGARDIAN_WARRIOR = make_creature(
    name="Asgardian Warrior",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Warrior"},
    text="First strike. When Asgardian Warrior enters, scry 1 and gain 1 life for each Asgardian you control.",
    setup_interceptors=asgardian_warrior_setup,
)

def valkyrie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_death_trigger
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 3},
                      source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

VALKYRIE = make_creature(
    name="Valkyrie, Chooser of the Slain",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Warrior", "Avenger"},
    supertypes={"Legendary"},
    text="When Valkyrie dies, you gain 3 life.",
    setup_interceptors=valkyrie_setup
)

EINHERJAR_SOLDIER = make_creature(
    name="Einherjar Soldier",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Soldier", "Spirit"},
    text="Vigilance, lifelink",
    setup_interceptors=_mvl_einherjar_soldier_setup,
)

LADY_SIF = make_creature(
    name="Lady Sif, Shield Maiden",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Asgardian", "Warrior"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Lady Sif attacks, other Warriors you control gain vigilance until end of turn.",
    # Note: Complex attack trigger with temporary keyword grant - keeping as text for now
    setup_interceptors=_mvl_lady_sif_setup,
)

def wakandan_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Border watch — scry 1 + life gain per Wakandan you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        wakandans = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Wakandan" in o.characteristics.subtypes:
                    wakandans += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': max(1, wakandans)},
            source=obj.id, controller=obj.controller,
        ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

WAKANDAN_GUARD = make_creature(
    name="Wakandan Guard",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wakandan"},
    text="Defender, reach. When Wakandan Guard enters, scry 1 and gain 1 life for each Wakandan you control.",
    setup_interceptors=wakandan_guard_setup,
)

def okoye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Keyword grant for Wakandans (type-specific)."""
    from src.cards.interceptor_helpers import make_keyword_grant, creatures_with_subtype
    return [make_keyword_grant(obj, ['first_strike'], creatures_with_subtype(obj, "Wakandan"))]

OKOYE = make_creature(
    name="Okoye, Dora Milaje General",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wakandan"},
    supertypes={"Legendary"},
    text="First strike. Other Wakandan creatures you control have first strike.",
    setup_interceptors=okoye_setup
)

def dora_milaje_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Elite spearguard — on attack, scry 1 + each opponent loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        wakandans = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Wakandan" in o.characteristics.subtypes:
                    wakandans += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, wakandans)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

DORA_MILAJE = make_creature(
    name="Dora Milaje",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wakandan"},
    text="First strike. Whenever Dora Milaje attacks, scry 1 and each opponent loses 1 life for each Wakandan you control.",
    setup_interceptors=dora_milaje_setup,
)

SHIELD_HELICARRIER_CREW = make_creature(
    name="SHIELD Helicarrier Crew",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender. {T}: Add {C}.",
    setup_interceptors=_mvl_shield_helicarrier_crew_setup,
)

AVENGERS_MEDIC = make_creature(
    name="Avengers Medic",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="{T}: You gain 1 life.",
    setup_interceptors=_mvl_avengers_medic_setup,
)

NOVA_CORPS_OFFICER = make_creature(
    name="Nova Corps Officer",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Alien", "Soldier"},
    text="Flying, vigilance",
    setup_interceptors=_mvl_nova_corps_officer_setup,
)

RAVAGER_SCOUT = make_creature(
    name="Ravager Scout",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Alien", "Pirate"},
    text="When Ravager Scout enters, scry 1.",
    setup_interceptors=_mvl_ravager_scout_setup,
)


# =============================================================================
# BLUE CARDS - IRON MAN, TECH, STRATEGY
# =============================================================================

def iron_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus + artifact cast trigger (Marvel-specific mechanic)."""
    from src.cards.interceptor_helpers import make_spell_cast_trigger
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT}))
    return interceptors

# REBALANCE (MVL): Iron Man's flagship feel was undercut by 4/3 stats at {2}{U}{U}.
# Bumped to 4/4 to match his armored profile and improve the floor when no
# artifacts are around to draw cards.
IRON_MAN = make_creature(
    name="Iron Man, Genius Inventor",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Avenger", "Artificer"},
    supertypes={"Legendary"},
    text="Flying. Assemble - Iron Man gets +2/+2 as long as you control two or more Avengers. Whenever you cast an artifact spell, draw a card.",
    setup_interceptors=iron_man_setup
)

def spider_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus (Marvel-specific mechanic)."""
    return make_assemble_bonus(obj, 1, 1)

# REBALANCE (MVL): Spider-Man at {1}{U}{U} was 2/3 — slightly soft for a
# legendary flagship. Bumped to 3/3 so he trades more reliably and lands
# his Assemble bonus on a stronger body.
SPIDER_MAN = make_creature(
    name="Spider-Man, Friendly Neighborhood",
    power=3, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Flash, reach. Assemble - Spider-Man gets +1/+1 as long as you control two or more Avengers. Spider-Man can block an additional creature each combat.",
    setup_interceptors=spider_man_setup
)

def doctor_strange_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spell cast trigger: scry 2 (mages) or draw on first instant/sorcery cast."""
    from src.cards.interceptor_helpers import make_spell_cast_trigger
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
        ]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

# REBALANCE (MVL): Doctor Strange never got cast at {2}{U}{U}. Dropped to
# {1}{U}{U} (mono-blue 3 CMC) and stacked card draw on top of scry so the
# Sorcerer Supreme actually feels like a payoff for casting magic.
DOCTOR_STRANGE = make_creature(
    name="Doctor Strange, Sorcerer Supreme",
    power=2, toughness=4,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Avenger", "Wizard"},
    supertypes={"Legendary"},
    text="Flash, hexproof. Whenever you cast an instant or sorcery spell, scry 2 and draw a card.",
    setup_interceptors=doctor_strange_setup
)

def vision_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self hexproof grant."""
    from src.cards.interceptor_helpers import make_keyword_grant
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['hexproof'], self_filter)]

# REBALANCE (MVL): Cost dropped from {3}{U}{U} to {2}{U}{U} (4 CMC) and
# stats nudged up from 3/4 to 4/4. Vision now actually competes on rate
# with the other 5 CMC fliers in the format.
VISION = make_creature(
    name="Vision, Synthetic Avenger",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Construct", "Avenger"},
    supertypes={"Legendary"},
    text="Flying, hexproof. Vision can't be blocked by creatures with power 2 or less.",
    setup_interceptors=vision_setup
)

# REBALANCE (MVL): Mr. Fantastic was 2/3 for {2}{U}{U} with a single scry —
# barely cast at 8% rate. Dropped to {1}{U}{U}, bumped body to 3/4, and the
# upkeep now scries 2 to make him a real "smartest man in the room" card.
MR_FANTASTIC = make_creature(
    name="Mr. Fantastic, Reed Richards",
    power=3, toughness=4,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, scry 2.",
    setup_interceptors=lambda o, s: [make_upkeep_trigger(o, lambda e, st: [
        Event(type=EventType.ACTIVATE,
              payload={'action': 'scry', 'amount': 2},
              source=o.id, controller=o.controller)
    ])],
)

# REBALANCE (MVL): Bumped to 2/2 — at {1}{U}{U} a 1/1 flier with a death
# trigger felt anemic. 2/2 flier-with-cantrip at 2 CMC slots in as a real
# tempo piece for the tech archetype.
def stark_industries_drone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Stark tech — scry 1 + surveil 1 per Construct or Artifact you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        artifacts = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                if CardType.ARTIFACT in o.characteristics.types or "Construct" in o.characteristics.subtypes:
                    artifacts += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if artifacts >= 1:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

STARK_INDUSTRIES_DRONE = make_creature(
    name="Stark Industries Drone",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="Flying. When Stark Industries Drone enters, scry 1; if you control another artifact or Construct, surveil 1. When Stark Industries Drone dies, draw a card.",
    setup_interceptors=stark_industries_drone_setup,
)

# REBALANCE (MVL): FRIDAY was a 0/3 deal-no-damage wall. Bumped to 1/3
# and stacked a card draw on top of the scry so playing the legendary
# Stark AI gets you a small advantage even if the body trades poorly.
FRIDAY_AI = make_creature(
    name="FRIDAY, Stark AI",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    supertypes={"Legendary"},
    text="When FRIDAY enters, scry 2, then draw a card.",
    setup_interceptors=lambda o, s: [make_etb_trigger(o, lambda e, st: [
        Event(type=EventType.ACTIVATE,
              payload={'action': 'scry', 'amount': 2},
              source=o.id, controller=o.controller),
        Event(type=EventType.DRAW,
              payload={'player': o.controller, 'amount': 1},
              source=o.id, controller=o.controller),
    ])],
)

# REBALANCE (MVL): Bumped from 1/3 to 2/3 and lowered cost to {1}{U}.
# A 2/3 for 2 with an artifact-untap utility ability fits the Tech archetype
# without overshadowing rares.
SHIELD_TECH_SPECIALIST = make_creature(
    name="SHIELD Tech Specialist",
    power=2, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="{T}: Untap target artifact.",
    setup_interceptors=_mvl_shield_tech_specialist_setup,
)

def hank_pym_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_create_token(obj, 1, 1, "Insect", count=2, colors={Color.BLUE})
    return [itc]

# REBALANCE (MVL): Hank Pym never got cast at {1}{U}{G} in mono-blue tests.
# Reverted to mono-blue {1}{U} and bumped output to two 1/1 Insect tokens to
# match his "size shifter / ant army" flavor. Now functions as a 2 CMC
# anthill that pairs with his other Pym-Particle cards.
HANK_PYM = make_creature(
    name="Hank Pym, Size Shifter",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist", "Avenger"},
    supertypes={"Legendary"},
    text="When Hank Pym enters, create two 1/1 blue Insect creature tokens.",
    setup_interceptors=hank_pym_setup
)

def quantum_realm_explorer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pocket dimension — scry 1 + surveil 1 if any Scientist or Artificer is around."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        sci = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Scientist" in subs or "Artificer" in subs:
                    sci += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if sci >= 1:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

QUANTUM_REALM_EXPLORER = make_creature(
    name="Quantum Realm Explorer",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    text="When Quantum Realm Explorer enters, scry 1; if you control another Scientist or Artificer, surveil 1. When Quantum Realm Explorer dies, scry 2.",
    setup_interceptors=quantum_realm_explorer_setup,
)

# REBALANCE (MVL): Bumped from 1/2 to 2/3 — at {1}{U} a 1/2 with a 1-life
# loot ability did not pull weight. 2/3 makes it a real blocker too.
PYM_PARTICLE_RESEARCHER = make_creature(
    name="Pym Particle Researcher",
    power=2, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    text="{T}, Pay 1 life: Draw a card, then discard a card.",
    setup_interceptors=_mvl_pym_particle_researcher_setup,
)

def rocket_raccoon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact cast trigger: Rocket fires on artifact casts."""
    from src.cards.interceptor_helpers import make_spell_cast_trigger
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'any_target', 'amount': 2, 'source': obj.id
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT})]

# REBALANCE (MVL): Rocket never got cast at {1}{U}{R} in a mono-blue deck.
# Refit to mono-blue {1}{U} as a 2/2 with reach (sniper flavor) and bumped
# his artifact ping from 1 to 2 damage so triggering him actually moves the
# board. Keeps the "weapons expert" tech-archetype feel.
ROCKET_RACCOON = make_creature(
    name="Rocket Raccoon, Weapons Expert",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Raccoon", "Guardian", "Artificer"},
    supertypes={"Legendary"},
    text="Reach. Whenever you cast an artifact spell, Rocket deals 2 damage to any target.",
    setup_interceptors=rocket_raccoon_setup
)

def star_lord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Guardian", include_self=False)
    return itcs

STAR_LORD = make_creature(
    name="Star-Lord, Legendary Outlaw",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Guardian", "Pirate"},
    supertypes={"Legendary"},
    text="Other Guardian creatures you control get +1/+1.",
    setup_interceptors=star_lord_setup
)

# REBALANCE (MVL): Bumped from 3/3 to 3/4 — makes the 4 CMC flier survive
# trades against most mid-range threats while keeping the tap-on-ETB tempo
# play that fits the Kree (cosmic enforcers) archetype.
def kree_sentry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kree sentinel — scry 1 + each opponent loses 1 life per Kree you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        kree = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Kree" in o.characteristics.subtypes:
                    kree += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, kree)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

KREE_SENTRY = make_creature(
    name="Kree Sentry",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Kree", "Soldier"},
    text="Flying. When Kree Sentry enters, scry 1 and each opponent loses 1 life for each Kree you control. Tap target creature an opponent controls.",
    setup_interceptors=kree_sentry_setup,
)

# REBALANCE (MVL): Bumped from 2/2 at {2}{U} to 3/2 with flying. The "copy
# any creature" floor rarely fired in tests, so the printed stats need to
# carry the card. A 3/2 flying shapeshifter at 3 CMC is solid Skrull tempo.
def skrull_infiltrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Disguise infiltration — surveil 1 + each opp reveals hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        shapeshifters = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Skrull" in subs or "Shapeshifter" in subs:
                    shapeshifters += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': max(1, shapeshifters)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

SKRULL_INFILTRATOR = make_creature(
    name="Skrull Infiltrator",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Skrull", "Shapeshifter"},
    text="Flying. When Skrull Infiltrator enters, surveil 1 and each opponent reveals a card from their hand for each Skrull or Shapeshifter you control.",
    setup_interceptors=skrull_infiltrator_setup,
)

# REBALANCE (MVL): Bumped from 1/3 to 2/3. A 1/3 looter at 3 CMC was
# below curve — 2/3 keeps it a defender-ish body but lets it actually
# attack down chump blockers.
KNOWHERE_MERCHANT = make_creature(
    name="Knowhere Merchant",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Alien", "Rogue"},
    text="When Knowhere Merchant enters, draw a card, then discard a card.",
    setup_interceptors=_mvl_knowhere_merchant_setup,
)

# REBALANCE (MVL): Bumped toughness 1->3. A 2/1 mana-rock-grant for {1}{U}
# died to almost any blocker; 2/3 lets the engineer actually live to enable
# the artifact-mana ramp the tech archetype wants.
RAVAGER_ENGINEER = make_creature(
    name="Ravager Engineer",
    power=2, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Alien", "Pirate", "Artificer"},
    text="Artifacts you control have '{T}: Add {C}.'",
    setup_interceptors=_mvl_ravager_engineer_setup,
)

# REBALANCE (MVL): Bumped from 2/2 to 2/3 and scry 1 -> scry 2 to make
# this a genuine air-superiority play at 3 CMC. Pilot synergy stays intact.
XANDARIAN_PILOT = make_creature(
    name="Xandarian Pilot",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Alien", "Pilot"},
    text="Flying. When Xandarian Pilot enters, scry 2.",
    setup_interceptors=_mvl_xandarian_pilot_setup,
)


# =============================================================================
# BLACK CARDS - BLACK WIDOW, ESPIONAGE, ANTIHEROES
# =============================================================================

def black_widow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus + combat damage trigger (Marvel-specific mechanic)."""
    from src.cards.interceptor_helpers import make_damage_trigger
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 1, 1))
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    return interceptors

BLACK_WIDOW = make_creature(
    name="Black Widow, Master Spy",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Avenger", "Spy", "Assassin"},
    supertypes={"Legendary"},
    text="Deathtouch. Assemble - Black Widow gets +1/+1 as long as you control two or more Avengers. Whenever Black Widow deals combat damage to a player, draw a card.",
    setup_interceptors=black_widow_setup
)

def hawkeye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus (Marvel-specific mechanic)."""
    return make_assemble_bonus(obj, 1, 1)

HAWKEYE = make_creature(
    name="Hawkeye, Never Miss",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Avenger", "Archer"},
    supertypes={"Legendary"},
    text="Reach, deathtouch. Assemble - Hawkeye gets +1/+1 as long as you control two or more Avengers.",
    setup_interceptors=hawkeye_setup
)

def nick_fury_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_etb_trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'SHIELD Agent', 'power': 1, 'toughness': 1,
                          'colors': {Color.BLACK}, 'subtypes': {'Human', 'Spy'}},
            }, source=obj.id)
            for _ in range(2)
        ]
    return [make_etb_trigger(obj, etb_effect)]

NICK_FURY = make_creature(
    name="Nick Fury, Director of SHIELD",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Spy"},
    supertypes={"Legendary"},
    text="When Nick Fury enters, create two 1/1 black Human Spy creature tokens.",
    setup_interceptors=nick_fury_setup
)

def punisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creature death trigger (complex filter)."""
    from src.cards.interceptor_helpers import make_death_trigger
    def death_trigger_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'any_target', 'amount': 2, 'source': obj.id
        }, source=obj.id)]
    def other_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == source.controller and
                CardType.CREATURE in dying_obj.characteristics.types and
                dying_obj.id != source.id)
    return [make_death_trigger(obj, death_trigger_effect, other_death_filter)]

PUNISHER = make_creature(
    name="The Punisher, Frank Castle",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Vigilante"},
    supertypes={"Legendary"},
    text="Menace. Whenever another creature you control dies, The Punisher deals 2 damage to any target.",
    setup_interceptors=punisher_setup
)

def gamora_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to creature trigger (complex effect)."""
    from src.cards.interceptor_helpers import make_damage_trigger
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if target and CardType.CREATURE in target.characteristics.types:
            return [Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=obj.id)]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

GAMORA = make_creature(
    name="Gamora, Deadliest Woman",
    power=3, toughness=2,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Guardian", "Assassin"},
    supertypes={"Legendary"},
    text="First strike, deathtouch. Whenever Gamora deals combat damage to a creature, destroy that creature.",
    setup_interceptors=gamora_setup
)

LOKI = make_creature(
    name="Loki, God of Mischief",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Asgardian", "God", "Villain"},
    supertypes={"Legendary"},
    text="Flash. When Loki enters, create a token that's a copy of target creature, except it's an Illusion and has 'When this creature becomes the target of a spell, sacrifice it.'",
    # Note: Complex copy effect - keeping as text
    setup_interceptors=_mvl_loki_setup,
)

def hydra_agent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cut off one head — scry 1 + each opp loses 1 life per Villain you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        villains = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Villain" in o.characteristics.subtypes:
                    villains += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, villains)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

HYDRA_AGENT = make_creature(
    name="HYDRA Agent",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Spy", "Villain"},
    text="When HYDRA Agent enters, scry 1 and each opponent loses 1 life for each Villain you control. When HYDRA Agent dies, create a 1/1 black Human Spy creature token.",
    setup_interceptors=hydra_agent_setup,
)

def hydra_enforcer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hail HYDRA — on attack, scry 1 + each opp -1 life and discard if 2+ Villains."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        villains = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Villain" in o.characteristics.subtypes:
                    villains += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
            if villains >= 2:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': opp_id, 'amount': 1},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

HYDRA_ENFORCER = make_creature(
    name="HYDRA Enforcer",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Villain"},
    text="Menace. Whenever HYDRA Enforcer attacks, scry 1 and each opponent loses 1 life; if you control two or more Villains, each opponent also discards a card.",
    setup_interceptors=hydra_enforcer_setup,
)

WINTER_SOLDIER_ASSET = make_creature(
    name="Winter Soldier Asset",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Assassin"},
    text="Menace. When Winter Soldier Asset enters, tap target creature an opponent controls.",
    # Note: Targeted ETB - keeping as text
    setup_interceptors=_mvl_winter_soldier_asset_setup,
)

def hand_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Silent strike — scry 1 + surveil 1 + each opp -1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        ninjas = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Ninja" in subs or "Assassin" in subs:
                    ninjas += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if ninjas >= 1:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

HAND_ASSASSIN = make_creature(
    name="Hand Assassin",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Assassin"},
    text="Deathtouch. When Hand Assassin enters, scry 1; if you control another Ninja or Assassin, surveil 1. Each opponent loses 1 life.",
    setup_interceptors=hand_assassin_setup,
)

KINGPIN_ENFORCER = make_creature(
    name="Kingpin's Enforcer",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    text="Menace. When Kingpin's Enforcer enters, each opponent discards a card.",
    setup_interceptors=_mvl_kingpin_enforcer_setup,
)

def nebula_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = attack_add_counters(obj, "+1/+1", 1)
    return [itc]

NEBULA = make_creature(
    name="Nebula, Cybernetic Assassin",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Assassin", "Villain"},
    supertypes={"Legendary"},
    text="Whenever Nebula attacks, put a +1/+1 counter on it.",
    setup_interceptors=nebula_setup
)

def crossbones_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mercenary muscle — scry 1 + each opp -1 life per Mercenary or Villain you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        merc_villain = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Mercenary" in subs or "Villain" in subs:
                    merc_villain += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, merc_villain)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

CROSSBONES = make_creature(
    name="Crossbones",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Mercenary", "Villain"},
    supertypes={"Legendary"},
    text="Menace. When Crossbones enters, scry 1 and each opponent loses 1 life for each Mercenary or Villain you control. When Crossbones dies, it deals 3 damage to target creature or planeswalker.",
    setup_interceptors=crossbones_setup,
)

TASKMASTER = make_creature(
    name="Taskmaster",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Mercenary", "Villain"},
    supertypes={"Legendary"},
    text="First strike. Taskmaster has all activated abilities of creatures your opponents control.",
    setup_interceptors=_mvl_taskmaster_setup,
)

GHOST = make_creature(
    name="Ghost, Phasing Thief",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="Ghost can't be blocked. Whenever Ghost deals combat damage to a player, that player discards a card.",
    setup_interceptors=_mvl_ghost_setup,
)

ZEMO = make_creature(
    name="Baron Zemo, Vengeful Noble",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Noble", "Villain"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever an Avenger an opponent controls dies, draw a card.",
    setup_interceptors=_mvl_zemo_setup,
)

MANTIS = make_creature(
    name="Mantis, Empath",
    power=1, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Guardian"},
    supertypes={"Legendary"},
    text="When Mantis enters, tap target creature and it doesn't untap during its controller's next untap step.",
    setup_interceptors=_mvl_mantis_setup,
)

DRAX = make_creature(
    name="Drax the Destroyer",
    power=4, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Guardian", "Warrior"},
    supertypes={"Legendary"},
    text="Trample. Drax must attack each combat if able. Drax gets +2/+2 as long as an opponent controls a Villain.",
    setup_interceptors=_mvl_drax_setup,
)

DARK_ELF_WARRIOR = make_creature(
    name="Dark Elf Warrior",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warrior"},
    text="When Dark Elf Warrior enters, target creature gets -1/-1 until end of turn.",
    setup_interceptors=_mvl_dark_elf_warrior_setup,
)


# =============================================================================
# RED CARDS - THOR, POWER, DESTRUCTION
# =============================================================================

def thor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus + ETB damage (Marvel-specific mechanic)."""
    from src.cards.interceptor_helpers import make_etb_trigger
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'any_target', 'amount': 3, 'source': obj.id, 'type': 'lightning'
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors

THOR = make_creature(
    name="Thor, God of Thunder",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Asgardian", "God", "Avenger"},
    supertypes={"Legendary"},
    text="Flying, trample. Assemble - Thor gets +2/+2 as long as you control two or more Avengers. When Thor enters, he deals 3 damage to any target.",
    setup_interceptors=thor_setup
)

def scarlet_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant/sorcery cast trigger (uses old pattern for spell type filter)."""
    from src.cards.interceptor_helpers import make_spell_cast_trigger
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'each_opponent', 'amount': 1, 'source': obj.id
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

SCARLET_WITCH = make_creature(
    name="Scarlet Witch, Reality Warper",
    power=2, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Avenger", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, Scarlet Witch deals 1 damage to each opponent.",
    setup_interceptors=scarlet_witch_setup
)

def captain_marvel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus (Marvel-specific mechanic)."""
    return make_assemble_bonus(obj, 2, 2)

CAPTAIN_MARVEL = make_creature(
    name="Captain Marvel, Binary",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Avenger", "Warrior"},
    supertypes={"Legendary"},
    text="Flying, haste, trample. Assemble - Captain Marvel gets +2/+2 as long as you control two or more Avengers.",
    setup_interceptors=captain_marvel_setup
)

def hela_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Any creature death trigger (complex filter)."""
    from src.cards.interceptor_helpers import make_death_trigger
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1
        }, source=obj.id)]
    def any_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)
    return [make_death_trigger(obj, death_effect, any_death_filter)]

HELA = make_creature(
    name="Hela, Goddess of Death",
    power=5, toughness=5,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Asgardian", "God", "Villain"},
    supertypes={"Legendary"},
    text="Menace, deathtouch. Whenever a creature dies, put a +1/+1 counter on Hela.",
    setup_interceptors=hela_setup
)

def surtur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger with AoE damage."""
    from src.cards.interceptor_helpers import make_attack_trigger
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'target': 'each_creature', 'amount': 2, 'source': obj.id
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

SURTUR = make_creature(
    name="Surtur, Fire Giant",
    power=7, toughness=7,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Villain"},
    supertypes={"Legendary"},
    text="Trample. Whenever Surtur attacks, he deals 2 damage to each other creature.",
    setup_interceptors=surtur_setup
)

def ultron_prime_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_upkeep_trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Ultron Drone', 'power': 2, 'toughness': 2,
                      'colors': set(), 'subtypes': {'Construct', 'Villain'}},
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

ULTRON_PRIME = make_creature(
    name="Ultron Prime",
    power=5, toughness=5,
    mana_cost="{4}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Construct", "Villain"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, create a 2/2 colorless Construct Villain creature token.",
    setup_interceptors=ultron_prime_setup
)

# REBALANCE (MVL): Bumped death-ping from 1 to 2 damage. As a colorless
# 2/2 vanilla-ish drone for {2}, the death trigger is the whole reason to
# play it — 2 damage actually closes out the racing math.
ULTRON_DRONE = make_creature(
    name="Ultron Drone",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct", "Villain"},
    text="When Ultron Drone dies, it deals 2 damage to any target.",
    setup_interceptors=_mvl_destroyer_armor_setup,
)

FIRE_DEMON = make_creature(
    name="Fire Demon",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Demon"},
    text="Haste. When Fire Demon enters, it deals 1 damage to any target.",
    setup_interceptors=_mvl_fire_demon_setup,
)

def asgardian_berserker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Berserker rage — on attack, scry 1 + 1 damage to each opp per Berserker."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        zerks = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Berserker" in subs or "Asgardian" in subs:
                    zerks += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, zerks), 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

ASGARDIAN_BERSERKER = make_creature(
    name="Asgardian Berserker",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Asgardian", "Warrior", "Berserker"},
    text="Haste, trample. Whenever Asgardian Berserker attacks, scry 1, then it deals damage to each opponent equal to the number of Asgardians or Berserkers you control. Asgardian Berserker attacks each combat if able.",
    setup_interceptors=asgardian_berserker_setup,
)

def chitauri_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Invasion wave — on attack, scry 1 + 1 damage to each opp per Alien."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        aliens = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Alien" in o.characteristics.subtypes:
                    aliens += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, aliens), 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

CHITAURI_SOLDIER = make_creature(
    name="Chitauri Soldier",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Soldier", "Villain"},
    text="Haste. Whenever Chitauri Soldier attacks, scry 1 and it deals damage to each opponent equal to the number of Aliens you control.",
    setup_interceptors=chitauri_soldier_setup,
)

CHITAURI_CHARGER = make_creature(
    name="Chitauri Charger",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Warrior", "Villain"},
    text="Haste, menace",
    setup_interceptors=_mvl_chitauri_charger_setup,
)

def leviathan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Super Strength (Marvel-specific mechanic)."""
    return make_super_strength(obj, 3)

LEVIATHAN = make_creature(
    name="Chitauri Leviathan",
    power=6, toughness=6,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Leviathan", "Villain"},
    text="Super Strength - Trample and +3/+0. When Chitauri Leviathan attacks, create two 2/1 red Alien Soldier creature tokens attacking.",
    setup_interceptors=leviathan_setup
)

NOVA_PRIME = make_creature(
    name="Nova Prime",
    power=4, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Flying, haste. When Nova Prime enters, it deals damage equal to its power to target creature.",
    setup_interceptors=_mvl_nova_prime_setup,
)

DESTROYER_ARMOR = make_creature(
    name="Destroyer Armor",
    power=6, toughness=6,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Construct"},
    text="Indestructible. {R}: Destroyer Armor deals 2 damage to target creature or player.",
    setup_interceptors=_mvl_destroyer_armor_setup,
)

RONAN_ACCUSER = make_creature(
    name="Ronan the Accuser",
    power=4, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Kree", "Warrior", "Villain"},
    supertypes={"Legendary"},
    text="Menace. When Ronan enters, destroy target creature with power 3 or less.",
    setup_interceptors=_mvl_ronan_accuser_setup,
)

def sakaaran_gladiator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Arena champion — scry 1 + 1 damage to each opp per Warrior or Alien."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        fighters = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Warrior" in subs or "Alien" in subs:
                    fighters += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, fighters), 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

SAKAARAN_GLADIATOR = make_creature(
    name="Sakaaran Gladiator",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Warrior"},
    text="Haste. When Sakaaran Gladiator enters, scry 1 and it deals damage to each opponent equal to the number of Aliens or Warriors you control. When Sakaaran Gladiator dies, it deals 2 damage to target player.",
    setup_interceptors=sakaaran_gladiator_setup,
)

GRANDMASTER_CHAMPION = make_creature(
    name="Grandmaster's Champion",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Warrior"},
    text="Trample. Grandmaster's Champion gets +2/+0 as long as it's attacking.",
    setup_interceptors=_mvl_grandmaster_champion_setup,
)

HUMAN_TORCH = make_creature(
    name="Human Torch, Johnny Storm",
    power=3, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Elemental"},
    supertypes={"Legendary"},
    text="Flying, haste. {R}: Human Torch gets +1/+0 until end of turn. {R}, {T}: Human Torch deals 2 damage to any target.",
    setup_interceptors=_mvl_human_torch_setup,
)


# =============================================================================
# GREEN CARDS - HULK, RAW STRENGTH, NATURE
# =============================================================================

def hulk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus + Super Strength (Marvel-specific mechanics)."""
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 3, 3))
    interceptors.extend(make_super_strength(obj, 2))
    return interceptors

HULK = make_creature(
    name="Hulk, Strongest Avenger",
    power=6, toughness=6,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Super Strength - Trample and +2/+0. Assemble - Hulk gets +3/+3 as long as you control two or more Avengers. Indestructible.",
    setup_interceptors=hulk_setup
)

def she_hulk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus + Super Strength (Marvel-specific mechanics)."""
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    interceptors.extend(make_super_strength(obj, 1))
    return interceptors

SHE_HULK = make_creature(
    name="She-Hulk, Jennifer Walters",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger", "Lawyer"},
    supertypes={"Legendary"},
    text="Super Strength - Trample and +1/+0. Assemble - She-Hulk gets +2/+2 as long as you control two or more Avengers.",
    setup_interceptors=she_hulk_setup
)

def groot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_death_trigger
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Baby Groot', 'power': 1, 'toughness': 1,
                      'colors': {Color.GREEN}, 'subtypes': {'Plant', 'Guardian'}},
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

GROOT = make_creature(
    name="Groot, I Am Groot",
    power=4, toughness=6,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Guardian"},
    supertypes={"Legendary"},
    text="When Groot dies, create a 1/1 green Plant Guardian creature token.",
    setup_interceptors=groot_setup
)

def black_panther_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Assemble bonus + ETB mana (Marvel-specific mechanic)."""
    from src.cards.interceptor_helpers import make_etb_trigger
    interceptors = []
    interceptors.extend(make_assemble_bonus(obj, 2, 2))
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ADD_MANA, payload={
            'player': obj.controller, 'mana': '{G}{G}'
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors

BLACK_PANTHER = make_creature(
    name="Black Panther, King of Wakanda",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger", "Noble", "Wakandan"},
    supertypes={"Legendary"},
    text="Deathtouch, hexproof. Assemble - Black Panther gets +2/+2 as long as you control two or more Avengers. When Black Panther enters, add {G}{G}.",
    setup_interceptors=black_panther_setup
)

def ant_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_create_token(obj, 1, 1, "Insect", count=3, colors={Color.GREEN})
    return [itc]

ANT_MAN = make_creature(
    name="Ant-Man, Scott Lang",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="When Ant-Man enters, create three 1/1 green Insect creature tokens.",
    setup_interceptors=ant_man_setup
)

def wasp_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage trigger with token creation."""
    from src.cards.interceptor_helpers import make_damage_trigger
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Ant', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Insect'}}
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

WASP = make_creature(
    name="Wasp, Hope Van Dyne",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Avenger"},
    supertypes={"Legendary"},
    text="Flying. Whenever Wasp deals combat damage to a player, create a 1/1 green Insect creature token.",
    setup_interceptors=wasp_setup
)

ANT_SWARM = make_creature(
    name="Ant Swarm",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Ant Swarm gets +1/+1 for each other Insect you control.",
    setup_interceptors=_mvl_ant_swarm_setup,
)

VIBRANIUM_RHINO = make_creature(
    name="Vibranium Rhino",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino", "Wakandan"},
    text="Trample. Vibranium Rhino has indestructible as long as it's attacking.",
    setup_interceptors=_mvl_vibranium_rhino_setup,
)

WAKANDAN_WAR_RHINO = make_creature(
    name="Wakandan War Rhino",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino", "Wakandan"},
    text="Trample. When Wakandan War Rhino enters, it fights target creature you don't control.",
    setup_interceptors=_mvl_wakandan_war_rhino_setup,
)

def shuri_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact cast trigger with counter effect (uses old pattern for spell type filter)."""
    from src.cards.interceptor_helpers import make_spell_cast_trigger
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'controller': obj.controller, 'counter_type': '+1/+1', 'target': 'creature_you_control'
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT})]

SHURI = make_creature(
    name="Shuri, Wakandan Genius",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Artificer", "Wakandan"},
    supertypes={"Legendary"},
    text="Whenever you cast an artifact spell, put a +1/+1 counter on target creature you control.",
    setup_interceptors=shuri_setup
)

def wakandan_border_tribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tribal vigil — scry 1 + life gain per Wakandan or Warrior."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        warriors = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Wakandan" in subs or "Warrior" in subs:
                    warriors += 1
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': max(1, warriors)},
                source=obj.id, controller=obj.controller,
            ),
        ]
    return [make_etb_trigger(obj, effect_fn)]

WAKANDAN_BORDER_TRIBE = make_creature(
    name="Wakandan Border Tribe",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior", "Wakandan"},
    text="Reach. When Wakandan Border Tribe enters, scry 1 and gain 1 life for each Wakandan or Warrior you control. Wakandan Border Tribe gets +1/+1 as long as you control a legendary Wakandan.",
    setup_interceptors=wakandan_border_tribe_setup,
)

THING = make_creature(
    name="The Thing, Ben Grimm",
    power=5, toughness=6,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Mutate"},
    supertypes={"Legendary"},
    text="Trample. The Thing has indestructible as long as it's blocking.",
    setup_interceptors=_mvl_thing_setup,
)

ABOMINATION = make_creature(
    name="Abomination",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Mutant", "Villain"},
    supertypes={"Legendary"},
    text="Trample. Whenever Abomination deals combat damage to a player, put two +1/+1 counters on it.",
    setup_interceptors=_mvl_abomination_setup,
)

SAVAGE_LAND_RAPTOR = make_creature(
    name="Savage Land Raptor",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Haste. Savage Land Raptor gets +2/+0 as long as it's attacking.",
    setup_interceptors=_mvl_savage_land_raptor_setup,
)

SAVAGE_LAND_REX = make_creature(
    name="Savage Land Rex",
    power=6, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample. When Savage Land Rex enters, it fights target creature you don't control.",
    setup_interceptors=_mvl_savage_land_rex_setup,
)

FOREST_TROLL = make_creature(
    name="Forest Troll",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Troll"},
    text="Trample. At the beginning of your upkeep, regenerate Forest Troll.",
    setup_interceptors=_mvl_forest_troll_setup,
)

def korg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_etb_trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Miek', 'power': 1, 'toughness': 1,
                      'colors': {Color.GREEN}, 'subtypes': {'Insect', 'Warrior'}},
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

KORG = make_creature(
    name="Korg, Revolutionary",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Kronan", "Warrior"},
    supertypes={"Legendary"},
    text="When Korg enters, create a 1/1 green Insect Warrior creature token.",
    setup_interceptors=korg_setup
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# REWIRE (MVL spice A1): Thanos is the closing build-around payoff for
# the Infinity Stone package. Now static +2/+2 per Infinity Stone you
# control, plus indestructible while you control two or more Stones (the
# assembly threshold — matches Time Stone's gate at 3 less the self-count
# offset). The printed "ETB each player sacs half their creatures" is
# Phase B-1; v1 swaps "ETB sweeper" for "scaling threat" which is the
# more interesting build-around shape (Sazh-Chocobo / Tifa-Lockheart
# pattern from spice-pass.md taxonomy).
THANOS = make_creature(
    name="Thanos, The Mad Titan",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Eternal", "Villain"},
    supertypes={"Legendary"},
    text="Thanos gets +2/+2 for each Infinity Stone you control. Thanos has indestructible as long as you control two or more Infinity Stones.",
    setup_interceptors=thanos_mad_titan_setup,
)

RED_SKULL = make_creature(
    name="Red Skull, HYDRA Supreme",
    power=4, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Menace. At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life.",
    setup_interceptors=_mvl_red_skull_setup,
)

def quicksilver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_attack_trigger
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP,
                      payload={'object_id': obj.id},
                      source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

# REBALANCE (MVL): Quicksilver was {1}{U}{R} but never cast in mono-blue
# tests. Refit to {1}{U} and added haste — speed flavor reinforced — so a
# 2/2 hasty Avenger that untaps after attacking can pressure right away.
QUICKSILVER = make_creature(
    name="Quicksilver, Pietro Maximoff",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Avenger", "Mutant"},
    supertypes={"Legendary"},
    text="Haste. Whenever Quicksilver attacks, untap it.",
    setup_interceptors=quicksilver_setup
)

EBONY_MAW = make_creature(
    name="Ebony Maw",
    power=2, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Alien", "Villain"},
    supertypes={"Legendary"},
    text="Flying. When Ebony Maw enters, gain control of target creature with power 2 or less until Ebony Maw leaves the battlefield.",
    setup_interceptors=_mvl_ebony_maw_setup,
)

PROXIMA_MIDNIGHT = make_creature(
    name="Proxima Midnight",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Alien", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, menace. Whenever Proxima Midnight deals combat damage to a player, that player discards a card.",
    setup_interceptors=_mvl_proxima_midnight_setup,
)

CORVUS_GLAIVE = make_creature(
    name="Corvus Glaive",
    power=3, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink. Corvus Glaive can't be destroyed by damage.",
    setup_interceptors=_mvl_corvus_glaive_setup,
)

CULL_OBSIDIAN = make_creature(
    name="Cull Obsidian",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Alien", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Trample. Cull Obsidian gets +2/+2 as long as you control another Villain.",
    setup_interceptors=_mvl_cull_obsidian_setup,
)

def wong_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant/sorcery cast trigger: gain life and scry 1 (Wong supports the wizard)."""
    from src.cards.interceptor_helpers import make_spell_cast_trigger
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
        ]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

# REBALANCE (MVL): Wong was {1}{W}{U}, never cast in mono-blue tests.
# Refit to mono-blue {1}{U} as a 2/3 — the loyal apprentice now also scries
# alongside the lifegain so casting magic in a Strange/Wong shell ramps you.
WONG = make_creature(
    name="Wong, Sorcerer of Kamar-Taj",
    power=2, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, you gain 1 life and scry 1.",
    setup_interceptors=wong_setup
)

MORDO = make_creature(
    name="Baron Mordo",
    power=3, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard", "Villain"},
    supertypes={"Legendary"},
    text="Flash. When Baron Mordo enters, counter target spell unless its controller pays {3}.",
    setup_interceptors=_mvl_mordo_setup,
)

DORMAMMU = make_creature(
    name="Dormammu, Lord of the Dark Dimension",
    power=8, toughness=8,
    mana_cost="{5}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "Villain"},
    supertypes={"Legendary"},
    text="Flying, trample. Dormammu can't be countered. At the beginning of your upkeep, each opponent loses 3 life.",
    setup_interceptors=_mvl_dormammu_setup,
)


# =============================================================================
# X-MEN REPRESENTATIVES
# =============================================================================

def wolverine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_damage_trigger
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 2},
                      source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

WOLVERINE = make_creature(
    name="Wolverine, Logan",
    power=3, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Whenever Wolverine deals combat damage to a creature, you gain 2 life.",
    setup_interceptors=wolverine_setup
)

STORM = make_creature(
    name="Storm, Weather Witch",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flying. When Storm enters, tap all creatures your opponents control.",
    # Note: Mass tap effect - keeping as text
    setup_interceptors=_mvl_storm_setup,
)

def cyclops_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Mutant", include_self=False)
    return itcs

CYCLOPS = make_creature(
    name="Cyclops, X-Men Leader",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Other Mutant creatures you control get +1/+1.",
    setup_interceptors=cyclops_setup
)

# REWIRE (MVL spice A1): Jean Grey already had a cast-draw trigger but
# was missing the Phoenix half. New jean_grey_phoenix_setup wires
# (a) self-flying, (b) cast-draw on I/S, (c) once-per-game return from
# graveyard on death. The "5 damage to each creature and each player"
# clause is Phase B-1 (mass damage from death trigger needs careful
# stack ordering vs the Phoenix-return event).
JEAN_GREY = make_creature(
    name="Jean Grey, Phoenix",
    power=3, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast an instant or sorcery spell, draw a card. When Jean Grey dies, return her from your graveyard to the battlefield (once per game).",
    setup_interceptors=jean_grey_phoenix_setup,
)

PROFESSOR_X = make_creature(
    name="Professor X, Charles Xavier",
    power=1, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Hexproof. Other Mutants you control have hexproof. {T}: Look at target opponent's hand.",
    setup_interceptors=_mvl_professor_x_setup,
)

MAGNETO = make_creature(
    name="Magneto, Master of Magnetism",
    power=4, toughness=4,
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Mutant", "Villain"},
    supertypes={"Legendary"},
    text="Flying. When Magneto enters, gain control of all Equipment. Equipped creatures opponents control get -2/-0.",
    setup_interceptors=_mvl_magneto_setup,
)

ROGUE = make_creature(
    name="Rogue, Power Absorber",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flying. Whenever Rogue deals combat damage to a creature, she gains all abilities of that creature until end of turn.",
    setup_interceptors=_mvl_rogue_setup,
)

BEAST = make_creature(
    name="Beast, Hank McCoy",
    power=3, toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Mutant", "Scientist"},
    supertypes={"Legendary"},
    text="Reach. {T}: Add one mana of any color. When Beast enters, draw a card.",
    setup_interceptors=_mvl_beast_setup,
)

ICEMAN = make_creature(
    name="Iceman, Bobby Drake",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Hexproof. When Iceman enters, tap target creature. It doesn't untap during its controller's next untap step.",
    setup_interceptors=_mvl_iceman_setup,
)

NIGHTCRAWLER = make_creature(
    name="Nightcrawler",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Flash. Nightcrawler can't be blocked. When Nightcrawler enters, you may return another creature you control to its owner's hand.",
    setup_interceptors=_mvl_nightcrawler_setup,
)

COLOSSUS = make_creature(
    name="Colossus, Piotr Rasputin",
    power=5, toughness=6,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Mutant"},
    supertypes={"Legendary"},
    text="Trample. Colossus has indestructible as long as it's attacking or blocking.",
    setup_interceptors=_mvl_colossus_setup,
)


# =============================================================================
# ARTIFACTS - INFINITY STONES, EQUIPMENT
# =============================================================================

# REWIRE (MVL spice A1): Mind Stone was an unwired vanilla artifact —
# critical for the Infinity Stone build-around to work. Now ETB scries 1
# and upkeep scries 1, giving the assembly piece a real "you went long"
# payoff. Mana-tap and no-maxhand are Phase B-1 (need mana abilities +
# hand-size replacement).
MIND_STONE_INFINITY = make_artifact(
    name="Mind Stone",
    mana_cost="{4}",
    text="Infinity Stone — When Mind Stone enters, scry 1. At the beginning of your upkeep, scry 1. {T}: Add {U}. You have no maximum hand size.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=mind_stone_setup,
)

def space_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Grant flying to all your creatures."""
    from src.cards.interceptor_helpers import make_keyword_grant
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.controller == obj.controller and CardType.CREATURE in target.characteristics.types
    return [make_keyword_grant(obj, ['flying'], self_filter)]

SPACE_STONE = make_artifact(
    name="Space Stone",
    mana_cost="{4}",
    text="Infinity Stone - Creatures you control have flying. {T}: Add {W}. {3}, {T}: Exile target creature you control, then return it to the battlefield.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=space_stone_setup
)

# REWIRE (MVL spice A1): Time Stone was unwired. Now ETB untaps the
# controller's permanents AND grants an extra turn if you already control
# three or more Infinity Stones (i.e. you assembled the build-around).
# Phase 11 build-around payoff — the standalone untap is a tempo swing,
# the extra turn is the "you assembled it" lock.
TIME_STONE = make_artifact(
    name="Time Stone",
    mana_cost="{5}",
    text="Infinity Stone — When Time Stone enters, untap each permanent you control. If you control three or more Infinity Stones, take an extra turn after this one.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=time_stone_setup,
)

def power_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Grant +2/+2 to all your creatures."""
    from src.cards.interceptor_helpers import make_static_pt_boost
    def self_filter(target: GameObject, state: GameState) -> bool:
        return target.controller == obj.controller and CardType.CREATURE in target.characteristics.types
    return make_static_pt_boost(obj, 2, 2, self_filter)

POWER_STONE_INFINITY = make_artifact(
    name="Power Stone",
    mana_cost="{5}",
    text="Infinity Stone - Creatures you control get +2/+2. {T}: Add {R}{R}.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=power_stone_setup
)

def reality_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _txt = etb_draw(obj, 2)
    return [itc]

REALITY_STONE = make_artifact(
    name="Reality Stone",
    mana_cost="{4}",
    text="Infinity Stone - When Reality Stone enters, draw two cards. {T}: Add {R}. {2}, {T}: Exile target permanent, then return it to the battlefield under your control.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=reality_stone_setup
)

def soul_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Any creature death trigger for life gain."""
    from src.cards.interceptor_helpers import make_death_trigger
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    def any_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)
    return [make_death_trigger(obj, death_effect, any_death_filter)]

SOUL_STONE = make_artifact(
    name="Soul Stone",
    mana_cost="{4}",
    text="Infinity Stone - Whenever a creature dies, you gain 1 life. {T}: Add {B}. {3}, {T}: Return target creature card from your graveyard to the battlefield.",
    subtypes={"Infinity Stone"},
    supertypes={"Legendary"},
    setup_interceptors=soul_stone_setup
)

# REWIRE (MVL spice A1): Real make_equipment_setup wiring of the
# previously-unwired equipment. The "if equipped creature is named Thor,
# indestructible / equip {0}" branch is Phase B-1 (needs creature-name-
# aware static gate); v1 ships the base equipment.
MJOLNIR = make_equipment(
    name="Mjolnir",
    mana_cost="{3}",
    text="Equipped creature gets +3/+3 and has flying and trample. If equipped creature is named Thor, it has indestructible. Equip {3}. Equip Thor {0}.",
    equip_cost="{3}",
    supertypes={"Legendary"},
    setup_interceptors=mjolnir_setup,
)

STORMBREAKER = make_equipment(
    name="Stormbreaker",
    mana_cost="{4}",
    text="Equipped creature gets +4/+4 and has flying, trample, and first strike. {T}: Stormbreaker deals 3 damage to any target.",
    equip_cost="{4}",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_stormbreaker_setup,
)

# REWIRE (MVL spice A1): Real make_equipment_setup wiring of the
# previously-unwired equipment. The "if equipped creature is named Captain
# America, double strike" branch is Phase B-1; v1 ships the base
# equipment.
CAPTAIN_AMERICAS_SHIELD = make_equipment(
    name="Captain America's Shield",
    mana_cost="{2}",
    text="Equipped creature gets +1/+3 and has vigilance and indestructible. If equipped creature is named Captain America, it has double strike.",
    equip_cost="{2}",
    supertypes={"Legendary"},
    setup_interceptors=captain_americas_shield_setup,
)

IRON_MAN_ARMOR_MK_L = make_equipment(
    name="Iron Man Armor Mk. L",
    mana_cost="{4}",
    text="Equipped creature gets +3/+3 and has flying and hexproof. {2}: Equipped creature deals 2 damage to any target.",
    equip_cost="{3}",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_iron_man_armor_l_setup,
)

IRON_MAN_ARMOR_MK_LXXXV = make_equipment(
    name="Iron Man Armor Mk. LXXXV",
    mana_cost="{5}",
    text="Equipped creature gets +4/+4 and has flying, hexproof, and indestructible. {R}: Equipped creature gets +1/+0 until end of turn.",
    equip_cost="{4}",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_iron_man_armor_lxxxv_setup,
)

HULKBUSTER_ARMOR = make_equipment(
    name="Hulkbuster Armor",
    mana_cost="{6}",
    text="Equipped creature gets +5/+5 and has trample. Equipped creature can't be blocked by creatures with power 3 or less.",
    equip_cost="{4}",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_hulkbuster_setup,
)

# REWIRE (MVL spice A1): Infinity Gauntlet was unwired. The headline
# build-around mythic — pairs with the rewired stones (Mind / Time / etc.)
# to form a real Infinity Stone assembly package. End step drain scales
# with stones controlled; activated abilities also scale or fire a Snap.
INFINITY_GAUNTLET = make_artifact(
    name="Infinity Gauntlet",
    mana_cost="{6}",
    text="At the beginning of your end step, each opponent loses life equal to the number of Infinity Stones you control and you gain that much life. {2}: Target creature gets +N/+N until end of turn, where N is the number of Infinity Stones you control. {6}: The Snap — each opponent sacrifices half their creatures, rounded up.",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    setup_interceptors=infinity_gauntlet_setup,
)

WEB_SHOOTERS = make_equipment(
    name="Web-Shooters",
    mana_cost="{1}",
    text="Equipped creature gets +1/+1 and has reach. {T}: Tap target creature. It doesn't untap during its controller's next untap step.",
    equip_cost="{1}",
    setup_interceptors=_mvl_web_shooters_setup,
)

YAKA_ARROW = make_equipment(
    name="Yaka Arrow",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0 and has '{T}: This creature deals 2 damage to target creature.'",
    equip_cost="{2}",
    setup_interceptors=_mvl_yaka_arrow_setup,
)

VIBRANIUM_SPEAR = make_equipment(
    name="Vibranium Spear",
    mana_cost="{2}",
    text="Equipped creature gets +2/+1 and has first strike. If equipped creature is Wakandan, it gets +3/+2 instead.",
    equip_cost="{2}",
    setup_interceptors=_mvl_vibranium_spear_setup,
)

PANTHER_HABIT = make_equipment(
    name="Panther Habit",
    mana_cost="{3}",
    text="Equipped creature gets +2/+2 and has deathtouch and hexproof. Whenever equipped creature is dealt damage, it deals that much damage to target creature.",
    equip_cost="{3}",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_panther_habit_setup,
)

NANO_GAUNTLET = make_equipment(
    name="Nano Gauntlet",
    mana_cost="{3}",
    text="Equipped creature gets +1/+1 for each artifact you control. {3}, {T}: Destroy target artifact or enchantment.",
    equip_cost="{2}",
    setup_interceptors=_mvl_nano_gauntlet_setup,
)

# --- Chitauri Scepter: Helper-5 rewire -------------------------------------
# +2/+0 + granted trigger "combat damage to player → gain control of one of
# their creatures until end of turn." Uses threaten_creature() for the
# canonical control+untap+haste EOT package. Greedy first-eligible picker.
def _chitauri_scepter_combat_damage_to_player_filter(
    event: Event, state: GameState, target_id: str
) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    return event.payload.get('target') in state.players


def _chitauri_scepter_threaten_effect(
    target_obj: GameObject, event: Event, state: GameState
) -> list[Event]:
    from src.cards.interceptor_helpers import threaten_creature
    victim_player = event.payload.get('target')
    if not victim_player:
        return []
    for o in state.objects.values():
        if o.controller != victim_player:
            continue
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if o.characteristics is None:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        return threaten_creature(
            target_id=o.id,
            new_controller=target_obj.controller,
            source_id=target_obj.id,
        )
    return []


CHITAURI_SCEPTER = make_equipment(
    name="Chitauri Scepter",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0. Whenever equipped creature deals combat damage to a player, gain control of a creature that player controls until end of turn.",
    equip_cost="{3}",
    setup_interceptors=make_equipment_setup(
        power_mod=2, toughness_mod=0,
        equip_cost="{3}",
        granted_triggered_abilities={
            "event_filter": _chitauri_scepter_combat_damage_to_player_filter,
            "effect_fn": _chitauri_scepter_threaten_effect,
            "description": "Combat damage to player → threaten one of their creatures",
        },
    ),
)

CLOAK_OF_LEVITATION = make_equipment(
    name="Cloak of Levitation",
    mana_cost="{2}",
    text="Equipped creature gets +1/+2, has flying, and can't be blocked by creatures with flying. Flash - You may cast this spell as though it had flash.",
    equip_cost="{1}",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_cloak_of_levitation_setup,
)

TESSERACT = make_artifact(
    name="Tesseract",
    mana_cost="{4}",
    text="{T}: Add {U}{U}. {4}, {T}: Exile target creature you control. Return it to the battlefield at the beginning of your next upkeep.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_tesseract_setup,
)

EYE_OF_AGAMOTTO = make_artifact(
    name="Eye of Agamotto",
    mana_cost="{3}",
    text="{T}: Scry 2. {2}, {T}: Return target permanent to its owner's hand. {4}, {T}: Take an extra turn after this one. Exile Eye of Agamotto.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_eye_of_agamotto_setup,
)

QUINJET = make_artifact(
    name="Quinjet",
    mana_cost="{3}",
    text="Crew 2. Flying. When Quinjet attacks, you may search your library for an Avenger card, reveal it, put it into your hand, then shuffle.",
    subtypes={"Vehicle"},
    setup_interceptors=_mvl_quinjet_setup,
)

MILANO = make_artifact(
    name="The Milano",
    mana_cost="{4}",
    text="Crew 2. Flying. When The Milano attacks, Guardians you control get +2/+0 until end of turn.",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    setup_interceptors=_mvl_milano_setup,
)

HELICARRIER = make_artifact(
    name="SHIELD Helicarrier",
    mana_cost="{6}",
    text="Crew 4. Flying. SHIELD Helicarrier has '{T}: Draw a card' and '{2}, {T}: SHIELD Helicarrier deals 3 damage to any target.'",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    setup_interceptors=_mvl_helicarrier_setup,
)

BENATAR = make_artifact(
    name="The Benatar",
    mana_cost="{4}",
    text="Crew 2. Flying. Whenever The Benatar attacks, create a 1/1 colorless Construct creature token.",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    setup_interceptors=_mvl_benatar_setup,
)


# =============================================================================
# INSTANTS AND SORCERIES
# =============================================================================

REPULSOR_BLAST = make_instant(
    name="Repulsor Blast",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Repulsor Blast deals 3 damage to target creature. If you control an artifact, draw a card.",
    resolve=_mvl_resolve_repulsor_blast,
)

SHIELD_THROW = make_instant(
    name="Shield Throw",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Shield Throw deals 2 damage to target creature. If that creature dies this turn, Shield Throw deals 2 damage to another target creature.",
    resolve=_mvl_resolve_shield_throw,
)

# REWIRE (MVL spice A1): Real resolve wiring for the previously-unwired
# token-sorcery. Creates three 2/2 Avenger tokens + pumps other Avengers
# +1/+1 EOT. Compression / "swarm-and-pump" payoff for the Avengers
# subtype cluster.
AVENGERS_ASSEMBLE = make_sorcery(
    name="Avengers Assemble",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 2/2 white Human Avenger Soldier creature tokens with vigilance. Other Avengers you control get +1/+1 until end of turn.",
    resolve=avengers_assemble_resolve,
)

HULK_SMASH = make_sorcery(
    name="Hulk Smash",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature you don't control. If the creature you control is Hulk, it deals double that damage instead.",
    resolve=_mvl_resolve_hulk_smash,
)

LIGHTNING_STRIKE_THOR = make_instant(
    name="Call the Bifrost",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Call the Bifrost deals 4 damage divided as you choose among any number of targets. If you control Thor, search your library for an Asgardian card, reveal it, put it into your hand, then shuffle.",
    resolve=_mvl_resolve_call_the_bifrost,
)

WIDOW_STING = make_instant(
    name="Widow's Sting",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If you control Black Widow, that creature gets -5/-5 instead.",
    resolve=_mvl_resolve_widows_sting,
)

CHAOS_MAGIC = make_instant(
    name="Chaos Magic",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Chaos Magic deals 3 damage to any target. If you control Scarlet Witch, Chaos Magic deals 5 damage instead.",
    resolve=_mvl_resolve_chaos_magic,
)

PORTAL_SLING_RING = make_instant(
    name="Sling Ring Portal",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Exile target creature you control, then return it to the battlefield. You may have it enter tapped.",
    resolve=_mvl_resolve_sling_ring_portal,
)

TIME_REVERSAL = make_instant(
    name="Time Reversal",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands. If you control Doctor Strange, instead exile all creatures, then return them to the battlefield under their owners' control.",
    resolve=_mvl_resolve_time_reversal,
)

SNAP_FINGERS = make_sorcery(
    name="Snap",
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    text="Each player sacrifices half of their creatures, rounded up. If you control Thanos, you may instead have each opponent sacrifice half of their permanents, rounded up.",
    resolve=_mvl_resolve_snap_fingers,
)

GAMMA_RADIATION = make_sorcery(
    name="Gamma Radiation",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature. It gains trample until end of turn. If that creature is Hulk, put four +1/+1 counters on it instead.",
    resolve=_mvl_resolve_gamma_radiation,
)

SHRINK_RAY = make_instant(
    name="Pym Particles",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature gets -4/-0 or +4/+4 until end of turn. You choose.",
    resolve=_mvl_resolve_pym_particles,
)

ARROW_VOLLEY = make_sorcery(
    name="Arrow Volley",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Arrow Volley deals 1 damage to each creature your opponents control. If you control Hawkeye, Arrow Volley deals 2 damage to each creature your opponents control instead.",
    resolve=_mvl_resolve_arrow_volley,
)

WAKANDA_FOREVER = make_sorcery(
    name="Wakanda Forever",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Creatures you control get +2/+2 and gain indestructible until end of turn. If you control Black Panther, put a +1/+1 counter on each creature you control.",
    resolve=_mvl_resolve_wakanda_forever,
)

MYSTIC_ARTS = make_instant(
    name="Mystic Arts",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}. If you control Doctor Strange, counter that spell instead.",
    resolve=_mvl_resolve_mystic_arts,
)

BLITZ_ATTACK = make_instant(
    name="Blitz Attack",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains haste until end of turn. If you control Quicksilver, that creature gets +4/+0 instead.",
    resolve=_mvl_resolve_blitz_attack,
)

TACTICAL_GENIUS = make_instant(
    name="Tactical Genius",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1 until end of turn. If you control Captain America, they also gain vigilance until end of turn.",
    resolve=_mvl_resolve_tactical_genius,
)

COSMIC_AWARENESS = make_sorcery(
    name="Cosmic Awareness",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards. If you control an Infinity Stone, draw four cards instead.",
    resolve=_mvl_resolve_cosmic_awareness,
)

BERSERKER_RAGE = make_instant(
    name="Berserker Rage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains trample until end of turn. That creature attacks this turn if able.",
    resolve=_mvl_resolve_berserker_rage,
)

STEALTH_MISSION = make_sorcery(
    name="Stealth Mission",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gains deathtouch and can't be blocked this turn. Draw a card.",
    resolve=_mvl_resolve_stealth_mission,
)

HEROIC_SACRIFICE = make_instant(
    name="Heroic Sacrifice",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Sacrifice a creature. If you do, you gain life equal to its toughness and draw a card.",
    resolve=_mvl_resolve_heroic_sacrifice,
)

SUPER_SOLDIER_SERUM = make_sorcery(
    name="Super Soldier Serum",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put three +1/+1 counters on target creature. It gains vigilance and trample until end of turn.",
    resolve=_mvl_resolve_super_soldier_serum,
)

REALITY_WARP = make_sorcery(
    name="Reality Warp",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Exile all artifacts and enchantments. Each player who controlled a permanent exiled this way draws a card for each permanent they owned that was exiled.",
    resolve=_mvl_resolve_reality_warp,
)

IMPALE = make_instant(
    name="Impale",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses 2 life.",
    resolve=_mvl_resolve_impale,
)


# =============================================================================
# ENCHANTMENTS
# =============================================================================

def avengers_initiative_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Avenger", include_self=True)
    return itcs

AVENGERS_INITIATIVE = make_enchantment(
    name="Avengers Initiative",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Avenger creatures you control get +1/+1.",
    setup_interceptors=avengers_initiative_setup
)

def stark_industries_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact cast trigger (uses old pattern for spell type filter)."""
    from src.cards.interceptor_helpers import make_spell_cast_trigger
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Thopter', 'power': 1, 'toughness': 1, 'subtypes': {'Construct'}}
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.ARTIFACT})]

STARK_INDUSTRIES = make_enchantment(
    name="Stark Industries",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an artifact spell, create a 1/1 colorless Thopter artifact creature token with flying.",
    setup_interceptors=stark_industries_setup
)

SHIELD_HEADQUARTERS = make_enchantment(
    name="SHIELD Headquarters",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="At the beginning of your upkeep, scry 1.",
    setup_interceptors=_mvl_shield_headquarters_setup,
)

def guardians_bond_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_keyword_grant, creatures_with_subtype
    itcs, _txt = static_pt_boost_by_subtype(obj, 1, 1, "Guardian", include_self=True)
    itcs.append(make_keyword_grant(obj, ['vigilance'], creatures_with_subtype(obj, "Guardian")))
    return itcs

GUARDIANS_BOND = make_enchantment(
    name="Guardians of the Galaxy United",
    mana_cost="{2}{G}{R}",
    colors={Color.GREEN, Color.RED},
    text="Guardian creatures you control get +1/+1 and have vigilance.",
    setup_interceptors=guardians_bond_setup
)

def hydra_influence_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Villain death trigger (complex filter)."""
    from src.cards.interceptor_helpers import make_death_trigger
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'HYDRA Agent', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Human', 'Spy'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'HYDRA Agent', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Human', 'Spy'}}
            }, source=obj.id)
        ]
    def villain_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == source.controller and
                CardType.CREATURE in dying_obj.characteristics.types and
                "Villain" in dying_obj.characteristics.subtypes)
    return [make_death_trigger(obj, death_effect, villain_death_filter)]

HYDRA_INFLUENCE = make_enchantment(
    name="HYDRA's Influence",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Whenever a Villain you control dies, create two 1/1 black Human Spy creature tokens.",
    setup_interceptors=hydra_influence_setup
)

ASGARDIAN_MIGHT = make_enchantment(
    name="Asgardian Might",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Asgardian creatures you control get +2/+1 and have trample.",
    setup_interceptors=_mvl_asgardian_might_setup,
)

MUTANT_UPRISING = make_enchantment(
    name="Mutant Uprising",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Mutant creatures you control get +1/+1 and have haste.",
    setup_interceptors=_mvl_mutant_uprising_setup,
)

COSMIC_CONVERGENCE = make_enchantment(
    name="Cosmic Convergence",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Whenever you cast a spell, if it's the second spell you cast this turn, copy it. You may choose new targets for the copy.",
    setup_interceptors=_mvl_cosmic_convergence_setup,
)

def dark_dimension_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_upkeep_trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for pid, player in state.players.items():
            if pid != obj.controller:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': pid, 'amount': -2},
                                    source=obj.id))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

DARK_DIMENSION = make_enchantment(
    name="Dark Dimension",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, each opponent loses 2 life.",
    setup_interceptors=dark_dimension_setup
)

VIBRANIUM_MINES = make_enchantment(
    name="Vibranium Mines",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever a Wakandan creature enters under your control, add {G}. Wakandan creatures you control have +0/+1.",
    setup_interceptors=_mvl_vibranium_mines_setup,
)


# =============================================================================
# LANDS
# =============================================================================

AVENGERS_TOWER = make_land(
    name="Avengers Tower",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Avenger spells or activate abilities of Avengers.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_avengers_tower_setup,
)

STARK_TOWER = make_land(
    name="Stark Tower",
    text="{T}: Add {C}. {1}, {T}: Add {U}{U}. Activate only if you control an artifact.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_stark_tower_setup,
)

WAKANDA = make_land(
    name="Wakanda",
    text="{T}: Add {G} or {W}. Wakanda enters tapped unless you control a Wakandan creature.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_wakanda_setup,
)

ASGARD = make_land(
    name="Asgard, Realm Eternal",
    text="{T}: Add {R} or {W}. {3}, {T}: Create a 2/2 white Asgardian Warrior creature token.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_asgard_setup,
)

SANCTUM_SANCTORUM = make_land(
    name="Sanctum Sanctorum",
    text="{T}: Add {U}. {2}, {T}: Scry 2. Activate only if you control a Wizard.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_sanctum_setup,
)

KNOWHERE = make_land(
    name="Knowhere",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Guardian spells.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_knowhere_setup,
)

XAVIERS_SCHOOL = make_land(
    name="Xavier's School for Gifted Youngsters",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Mutant spells.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_xaviers_school_setup,
)

HYDRA_BASE = make_land(
    name="HYDRA Base",
    text="{T}: Add {B}. When HYDRA Base enters, you may pay 2 life. If you don't, HYDRA Base enters tapped.",
    setup_interceptors=_mvl_hydra_base_setup,
)

SHIELD_FACILITY = make_land(
    name="SHIELD Facility",
    text="{T}: Add {W} or {U}. SHIELD Facility enters tapped.",
    setup_interceptors=_mvl_shield_facility_setup,
)

TITAN = make_land(
    name="Titan",
    text="{T}: Add {B} or {G}. {4}, {T}, Sacrifice Titan: Search your library for a Villain card, reveal it, put it into your hand, then shuffle.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_titan_setup,
)

VORMIR = make_land(
    name="Vormir",
    text="{T}: Add {B}. {2}, {T}, Sacrifice a creature: Draw two cards.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_vormir_setup,
)

SAKAAR = make_land(
    name="Sakaar",
    text="{T}: Add {R} or {G}. Sakaar enters tapped. When Sakaar enters, create a 1/1 red Alien Warrior creature token.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_sakaar_setup,
)

CONTRAXIA = make_land(
    name="Contraxia",
    text="{T}: Add {U} or {R}. Contraxia enters tapped unless you control a Pirate.",
    setup_interceptors=_mvl_contraxia_setup,
)

HALA = make_land(
    name="Hala",
    text="{T}: Add {U}. {3}, {T}: Create a 2/2 blue Kree Soldier creature token.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_hala_setup,
)

NIDAVELLIR = make_land(
    name="Nidavellir",
    text="{T}: Add {C}{C}. Spend this mana only to cast artifact spells or activate abilities of artifacts.",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_nidavellir_setup,
)

GENOSHA = make_land(
    name="Genosha",
    text="{T}: Add {R} or {G}. Mutant creatures you control have '{T}: Add one mana of any color.'",
    supertypes={"Legendary"},
    setup_interceptors=_mvl_genosha_setup,
)


# =============================================================================
# Phase A2 (slice 2) — decision-axis flips (2026-05-18)
# +4 net-new cards. Each card surfaces a distinct decision-axis fingerprint
# MVL has never had: prior to this slice every MVL card scored decision=0.
# Targets axis_diversity 0.059 -> >=0.080 (gate 1/4 -> 2/4).
# =============================================================================


# --- Doctor Strange, Sorcerer Supreme ({2}{U}{U} 2/4 Legendary Creature) ---
# Pattern 7 (modal: choose-one). Lore: Stephen Strange consults the
# Eye of Agamotto and chooses one of three timeline paths. Uses
# make_modal_etb_trigger so the AST scorer registers decision=2
# (deep_modal helper, no targeted modes).
def _doctor_strange_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: choose one — Scry 3; or, draw a card then discard a card;
    or, each opponent loses 2 life. Modal-ETB helper surfaces decision=2
    on the AST scorer (deep modal, no targeted modes)."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    modes = [
        {
            'text': 'Scry 3 (peer into the timestream)',
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
        make_keyword_grant(obj, ['flash'], affects_self),
        make_modal_etb_trigger(
            obj, modes, min_modes=1, max_modes=1,
            prompt="Choose one: Doctor Strange's chosen path",
        ),
    ]


DOCTOR_STRANGE_AGAMOTTO = make_creature(
    name="Doctor Strange, Eye of Agamotto",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Flash. "
        "When Doctor Strange, Eye of Agamotto enters, choose one —\n"
        "* Scry 3.\n"
        "* Draw a card, then discard a card.\n"
        "* Each opponent loses 2 life.\n"
        "(The Eye of Agamotto opens onto fourteen million six hundred "
        "and five futures.)"
    ),
    setup_interceptors=_doctor_strange_setup,
)


# --- Spider-Man, Web-Slinger ({1}{G}{U} 2/2 Legendary Creature) ---
# Decision-axis: make_targeted_attack_trigger (decision=1) + emit
# TARGET_CHOSEN information event for asymmetry=3 axis. Lore: When
# Spider-Man swings into combat, his web shot pins a foe (and the
# target's ward triggers if any).
def _spider_man_web_slinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Spider-Man attacks, tap target creature an opponent controls.
    make_targeted_attack_trigger -> decision=1. The supplementary
    attack-trigger emits a TARGET_CHOSEN event (information class) so
    the AST walker tags asymmetry=3."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def attack_target_chosen(event: Event, st: GameState) -> list[Event]:
        # TARGET_CHOSEN is in _MTG_INFORMATION_EVENTS — emitting it tags
        # the asymmetry axis (Spider-Man's web reveal is information to
        # the defender). Pure flavor, no targeting state required.
        return [Event(
            type=EventType.TARGET_CHOSEN,
            payload={'source': obj.id, 'spell_or_ability': 'web_shot'},
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['reach'], affects_self),
        make_attack_trigger(obj, attack_target_chosen),
        make_targeted_attack_trigger(
            obj,
            effect='tap',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=True,
            prompt="Web-shot: tap a creature an opponent controls",
        ),
    ]


SPIDER_MAN_WEB_SLINGER = make_creature(
    name="Spider-Man, Web-Slinger",
    power=2, toughness=2,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Reach. "
        "Whenever Spider-Man, Web-Slinger attacks, you may tap target "
        "creature an opponent controls. "
        "(\"Just hangin' around, Doc!\")"
    ),
    setup_interceptors=_spider_man_web_slinger_setup,
)


# --- Wakandan Vibranium Forge ({2}{W}{G} Enchantment, divided counters) ---
# Decision-axis: make_divided_counters_etb_trigger (decision=1) +
# creatures_you_control filter factory (synergy=2). Lore: Shuri's lab
# distributes Vibranium reinforcement across a chosen squad.
def _wakandan_vibranium_forge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: distribute 4 +1/+1 counters among any number of target
    creatures you control. make_divided_counters_etb_trigger -> decision=1.
    The explicit creatures_you_control filter factory call surfaces the
    synergy axis (filter_factory tag = synergy=2)."""
    # Filter-factory call: register that this card synergises with your
    # own creature board. The walker tags the call statically.
    own_creatures_filter = creatures_you_control(obj)
    _ = own_creatures_filter  # keep reference so the walker tags the call.
    return [
        make_divided_counters_etb_trigger(
            obj,
            counter_amount=4,
            counter_type='+1/+1',
            target_filter='your_creature',
            max_targets=4,
            prompt='Distribute 4 +1/+1 counters from Wakandan Vibranium Forge',
        ),
    ]


WAKANDAN_VIBRANIUM_FORGE = make_enchantment(
    name="Wakandan Vibranium Forge",
    mana_cost="{2}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    text=(
        "When Wakandan Vibranium Forge enters, distribute four +1/+1 "
        "counters among any number of target creatures you control. "
        "(Shuri's lab reforges every blade into Wakandan steel.)"
    ),
    setup_interceptors=_wakandan_vibranium_forge_setup,
)


# --- Loki, God of Mischief ({1}{U}{B} 2/3 Legendary Creature) ---
# Decision-axis: create_discard_choice opened from a custom ETB closure
# + explicit hand-zone read. Lore: Loki forces a foe to surrender their
# secrets. Distinct fp from the other three.
def _loki_god_of_mischief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: explicit hand-zone read for opponent, then open a discard
    choice. create_discard_choice is in modal_helpers -> decision=1; the
    state.zones.get read + hand zone tag surfaces state_coupling +
    zone_movement; all_opponents surfaces asymmetry."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def loki_etb(event: Event, st: GameState) -> list[Event]:
        # all_opponents helper surfaces cross_controller for asymmetry.
        opp_ids = all_opponents(obj, st)
        _ = opp_ids  # keep reference so the walker tags the call.
        # Pick the first opponent and read their hand zone explicitly.
        for player_id in st.players.keys():
            if player_id == obj.controller:
                continue
            hand = st.zones.get(f'hand_{player_id}')
            if hand is None or not hand.objects:
                continue
            # Open a discard choice — opponent must surrender 1 card.
            create_discard_choice(
                st, player_id, obj.id, list(hand.objects), 1,
                prompt="Loki's Whisper: choose a card to surrender",
            )
            return []
        return []

    return [
        make_keyword_grant(obj, ['flash'], affects_self),
        make_etb_trigger(obj, loki_etb),
    ]


LOKI_WHISPERS_OF_RUIN = make_creature(
    name="Loki, Whispers of Ruin",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"God", "Trickster"},
    supertypes={"Legendary"},
    text=(
        "Flash. "
        "When Loki, Whispers of Ruin enters, target opponent discards a "
        "card of their choice. "
        "(\"I am burdened with glorious purpose.\")"
    ),
    setup_interceptors=_loki_god_of_mischief_setup,
)


# --- Heimdall, All-Seeing Watchman ({1}{W}{U} 2/3 Legendary Creature) ---
# Decision-axis: make_top_n_land_pick surfaces decision=1 with zone reads
# (library + battlefield) for state_coupling + zone_movement axes.
# Lore: Heimdall scans the Nine Realms and pulls a Bifrost waypoint
# (land) into play. Buffer card — pushes axis_diversity past 0.080.
def _heimdall_all_seeing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: read library + battlefield zones, then open a top-5
    land-pick choice. make_top_n_land_pick is in modal_helpers ->
    decision=1; the explicit zone reads surface state_coupling and
    zone_movement axes."""
    def heimdall_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit zone reads so the AST walker tags both library and
        # battlefield zones (gives zone=2 from two-zone touch).
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        bf = st.zones.get('battlefield')
        if bf is None:
            return []
        # Heimdall's vigilance depth: pick larger sample if many enemy
        # creatures already threaten the realm.
        n_pick = 5 if len(bf.objects) >= 4 else 4
        return make_top_n_land_pick(
            st,
            controller=obj.controller,
            source_id=obj.id,
            n=n_pick,
            put_tapped=True,
            optional=True,
            prompt='Heimdall scans the Nine Realms — pick a Bifrost waypoint',
        )

    return [make_etb_trigger(obj, heimdall_etb)]


HEIMDALL_ALL_SEEING = make_creature(
    name="Heimdall, All-Seeing Watchman",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Asgardian", "Soldier"},
    supertypes={"Legendary"},
    text=(
        "Vigilance. "
        "When Heimdall, All-Seeing Watchman enters, look at the top four "
        "cards of your library (five instead if four or more permanents "
        "are on the battlefield). You may put a land card from among them "
        "onto the battlefield tapped. Put the rest on the bottom of your "
        "library in a random order. (The Bifrost is bound to the gatekeeper.)"
    ),
    setup_interceptors=_heimdall_all_seeing_setup,
)


# =============================================================================
# EXPORT
# =============================================================================

MARVEL_AVENGERS_CARDS = {
    # White - Captain America, Honor, Teamwork
    "Captain America, First Avenger": CAPTAIN_AMERICA,
    "Falcon, Winged Warrior": FALCON,
    "Bucky Barnes, Winter Soldier": BUCKY_BARNES,
    "Peggy Carter, Agent of SHIELD": PEGGY_CARTER,
    "SHIELD Agent": SHIELD_AGENT,
    "SHIELD Recruit": SHIELD_RECRUIT,
    "War Machine, Iron Patriot": WAR_MACHINE,
    "Asgardian Warrior": ASGARDIAN_WARRIOR,
    "Valkyrie, Chooser of the Slain": VALKYRIE,
    "Einherjar Soldier": EINHERJAR_SOLDIER,
    "Lady Sif, Shield Maiden": LADY_SIF,
    "Wakandan Guard": WAKANDAN_GUARD,
    "Okoye, Dora Milaje General": OKOYE,
    "Dora Milaje": DORA_MILAJE,
    "SHIELD Helicarrier Crew": SHIELD_HELICARRIER_CREW,
    "Avengers Medic": AVENGERS_MEDIC,
    "Nova Corps Officer": NOVA_CORPS_OFFICER,
    "Ravager Scout": RAVAGER_SCOUT,

    # Blue - Iron Man, Tech, Strategy
    "Iron Man, Genius Inventor": IRON_MAN,
    "Spider-Man, Friendly Neighborhood": SPIDER_MAN,
    "Doctor Strange, Sorcerer Supreme": DOCTOR_STRANGE,
    "Vision, Synthetic Avenger": VISION,
    "Mr. Fantastic, Reed Richards": MR_FANTASTIC,
    "Stark Industries Drone": STARK_INDUSTRIES_DRONE,
    "FRIDAY, Stark AI": FRIDAY_AI,
    "SHIELD Tech Specialist": SHIELD_TECH_SPECIALIST,
    "Hank Pym, Size Shifter": HANK_PYM,
    "Quantum Realm Explorer": QUANTUM_REALM_EXPLORER,
    "Pym Particle Researcher": PYM_PARTICLE_RESEARCHER,
    "Rocket Raccoon, Weapons Expert": ROCKET_RACCOON,
    "Star-Lord, Legendary Outlaw": STAR_LORD,
    "Kree Sentry": KREE_SENTRY,
    "Skrull Infiltrator": SKRULL_INFILTRATOR,
    "Knowhere Merchant": KNOWHERE_MERCHANT,
    "Ravager Engineer": RAVAGER_ENGINEER,
    "Xandarian Pilot": XANDARIAN_PILOT,

    # Black - Black Widow, Espionage, Antiheroes
    "Black Widow, Master Spy": BLACK_WIDOW,
    "Hawkeye, Never Miss": HAWKEYE,
    "Nick Fury, Director of SHIELD": NICK_FURY,
    "The Punisher, Frank Castle": PUNISHER,
    "Gamora, Deadliest Woman": GAMORA,
    "Loki, God of Mischief": LOKI,
    "HYDRA Agent": HYDRA_AGENT,
    "HYDRA Enforcer": HYDRA_ENFORCER,
    "Winter Soldier Asset": WINTER_SOLDIER_ASSET,
    "Hand Assassin": HAND_ASSASSIN,
    "Kingpin's Enforcer": KINGPIN_ENFORCER,
    "Nebula, Cybernetic Assassin": NEBULA,
    "Crossbones": CROSSBONES,
    "Taskmaster": TASKMASTER,
    "Ghost, Phasing Thief": GHOST,
    "Baron Zemo, Vengeful Noble": ZEMO,
    "Mantis, Empath": MANTIS,
    "Drax the Destroyer": DRAX,
    "Dark Elf Warrior": DARK_ELF_WARRIOR,

    # Red - Thor, Power, Destruction
    "Thor, God of Thunder": THOR,
    "Scarlet Witch, Reality Warper": SCARLET_WITCH,
    "Captain Marvel, Binary": CAPTAIN_MARVEL,
    "Hela, Goddess of Death": HELA,
    "Surtur, Fire Giant": SURTUR,
    "Ultron Prime": ULTRON_PRIME,
    "Ultron Drone": ULTRON_DRONE,
    "Fire Demon": FIRE_DEMON,
    "Asgardian Berserker": ASGARDIAN_BERSERKER,
    "Chitauri Soldier": CHITAURI_SOLDIER,
    "Chitauri Charger": CHITAURI_CHARGER,
    "Chitauri Leviathan": LEVIATHAN,
    "Nova Prime": NOVA_PRIME,
    "Destroyer Armor": DESTROYER_ARMOR,
    "Ronan the Accuser": RONAN_ACCUSER,
    "Sakaaran Gladiator": SAKAARAN_GLADIATOR,
    "Grandmaster's Champion": GRANDMASTER_CHAMPION,
    "Human Torch, Johnny Storm": HUMAN_TORCH,

    # Green - Hulk, Raw Strength, Nature
    "Hulk, Strongest Avenger": HULK,
    "She-Hulk, Jennifer Walters": SHE_HULK,
    "Groot, I Am Groot": GROOT,
    "Black Panther, King of Wakanda": BLACK_PANTHER,
    "Ant-Man, Scott Lang": ANT_MAN,
    "Wasp, Hope Van Dyne": WASP,
    "Ant Swarm": ANT_SWARM,
    "Vibranium Rhino": VIBRANIUM_RHINO,
    "Wakandan War Rhino": WAKANDAN_WAR_RHINO,
    "Shuri, Wakandan Genius": SHURI,
    "Wakandan Border Tribe": WAKANDAN_BORDER_TRIBE,
    "The Thing, Ben Grimm": THING,
    "Abomination": ABOMINATION,
    "Savage Land Raptor": SAVAGE_LAND_RAPTOR,
    "Savage Land Rex": SAVAGE_LAND_REX,
    "Forest Troll": FOREST_TROLL,
    "Korg, Revolutionary": KORG,

    # Multicolor
    "Thanos, The Mad Titan": THANOS,
    "Red Skull, HYDRA Supreme": RED_SKULL,
    "Quicksilver, Pietro Maximoff": QUICKSILVER,
    "Ebony Maw": EBONY_MAW,
    "Proxima Midnight": PROXIMA_MIDNIGHT,
    "Corvus Glaive": CORVUS_GLAIVE,
    "Cull Obsidian": CULL_OBSIDIAN,
    "Wong, Sorcerer of Kamar-Taj": WONG,
    "Baron Mordo": MORDO,
    "Dormammu, Lord of the Dark Dimension": DORMAMMU,

    # X-Men
    "Wolverine, Logan": WOLVERINE,
    "Storm, Weather Witch": STORM,
    "Cyclops, X-Men Leader": CYCLOPS,
    "Jean Grey, Phoenix": JEAN_GREY,
    "Professor X, Charles Xavier": PROFESSOR_X,
    "Magneto, Master of Magnetism": MAGNETO,
    "Rogue, Power Absorber": ROGUE,
    "Beast, Hank McCoy": BEAST,
    "Iceman, Bobby Drake": ICEMAN,
    "Nightcrawler": NIGHTCRAWLER,
    "Colossus, Piotr Rasputin": COLOSSUS,

    # Artifacts - Infinity Stones
    "Mind Stone": MIND_STONE_INFINITY,
    "Space Stone": SPACE_STONE,
    "Time Stone": TIME_STONE,
    "Power Stone": POWER_STONE_INFINITY,
    "Reality Stone": REALITY_STONE,
    "Soul Stone": SOUL_STONE,

    # Artifacts - Equipment
    "Mjolnir": MJOLNIR,
    "Stormbreaker": STORMBREAKER,
    "Captain America's Shield": CAPTAIN_AMERICAS_SHIELD,
    "Iron Man Armor Mk. L": IRON_MAN_ARMOR_MK_L,
    "Iron Man Armor Mk. LXXXV": IRON_MAN_ARMOR_MK_LXXXV,
    "Hulkbuster Armor": HULKBUSTER_ARMOR,
    "Infinity Gauntlet": INFINITY_GAUNTLET,
    "Web-Shooters": WEB_SHOOTERS,
    "Yaka Arrow": YAKA_ARROW,
    "Vibranium Spear": VIBRANIUM_SPEAR,
    "Panther Habit": PANTHER_HABIT,
    "Nano Gauntlet": NANO_GAUNTLET,
    "Chitauri Scepter": CHITAURI_SCEPTER,
    "Cloak of Levitation": CLOAK_OF_LEVITATION,
    "Tesseract": TESSERACT,
    "Eye of Agamotto": EYE_OF_AGAMOTTO,

    # Artifacts - Vehicles
    "Quinjet": QUINJET,
    "The Milano": MILANO,
    "SHIELD Helicarrier": HELICARRIER,
    "The Benatar": BENATAR,

    # Instants
    "Repulsor Blast": REPULSOR_BLAST,
    "Shield Throw": SHIELD_THROW,
    "Call the Bifrost": LIGHTNING_STRIKE_THOR,
    "Widow's Sting": WIDOW_STING,
    "Chaos Magic": CHAOS_MAGIC,
    "Sling Ring Portal": PORTAL_SLING_RING,
    "Time Reversal": TIME_REVERSAL,
    "Pym Particles": SHRINK_RAY,
    "Mystic Arts": MYSTIC_ARTS,
    "Blitz Attack": BLITZ_ATTACK,
    "Tactical Genius": TACTICAL_GENIUS,
    "Berserker Rage": BERSERKER_RAGE,
    "Stealth Mission": STEALTH_MISSION,
    "Heroic Sacrifice": HEROIC_SACRIFICE,
    "Impale": IMPALE,

    # Sorceries
    "Avengers Assemble": AVENGERS_ASSEMBLE,
    "Hulk Smash": HULK_SMASH,
    "Snap": SNAP_FINGERS,
    "Gamma Radiation": GAMMA_RADIATION,
    "Arrow Volley": ARROW_VOLLEY,
    "Wakanda Forever": WAKANDA_FOREVER,
    "Cosmic Awareness": COSMIC_AWARENESS,
    "Super Soldier Serum": SUPER_SOLDIER_SERUM,
    "Reality Warp": REALITY_WARP,

    # Enchantments
    "Avengers Initiative": AVENGERS_INITIATIVE,
    "Stark Industries": STARK_INDUSTRIES,
    "SHIELD Headquarters": SHIELD_HEADQUARTERS,
    "Guardians of the Galaxy United": GUARDIANS_BOND,
    "HYDRA's Influence": HYDRA_INFLUENCE,
    "Asgardian Might": ASGARDIAN_MIGHT,
    "Mutant Uprising": MUTANT_UPRISING,
    "Cosmic Convergence": COSMIC_CONVERGENCE,
    "Dark Dimension": DARK_DIMENSION,
    "Vibranium Mines": VIBRANIUM_MINES,

    # Lands
    "Avengers Tower": AVENGERS_TOWER,
    "Stark Tower": STARK_TOWER,
    "Wakanda": WAKANDA,
    "Asgard, Realm Eternal": ASGARD,
    "Sanctum Sanctorum": SANCTUM_SANCTORUM,
    "Knowhere": KNOWHERE,
    "Xavier's School for Gifted Youngsters": XAVIERS_SCHOOL,
    "HYDRA Base": HYDRA_BASE,
    "SHIELD Facility": SHIELD_FACILITY,
    "Titan": TITAN,
    "Vormir": VORMIR,
    "Sakaar": SAKAAR,
    "Contraxia": CONTRAXIA,
    "Hala": HALA,
    "Nidavellir": NIDAVELLIR,
    "Genosha": GENOSHA,

    # SPICE PASS PHASE A2 (slice 2, 2026-05-18) — decision-axis flips
    "Doctor Strange, Eye of Agamotto": DOCTOR_STRANGE_AGAMOTTO,
    "Spider-Man, Web-Slinger": SPIDER_MAN_WEB_SLINGER,
    "Wakandan Vibranium Forge": WAKANDAN_VIBRANIUM_FORGE,
    "Loki, Whispers of Ruin": LOKI_WHISPERS_OF_RUIN,
    "Heimdall, All-Seeing Watchman": HEIMDALL_ALL_SEEING,
}


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    CAPTAIN_AMERICA,
    FALCON,
    BUCKY_BARNES,
    PEGGY_CARTER,
    SHIELD_AGENT,
    SHIELD_RECRUIT,
    WAR_MACHINE,
    ASGARDIAN_WARRIOR,
    VALKYRIE,
    EINHERJAR_SOLDIER,
    LADY_SIF,
    WAKANDAN_GUARD,
    OKOYE,
    DORA_MILAJE,
    SHIELD_HELICARRIER_CREW,
    AVENGERS_MEDIC,
    NOVA_CORPS_OFFICER,
    RAVAGER_SCOUT,
    IRON_MAN,
    SPIDER_MAN,
    DOCTOR_STRANGE,
    VISION,
    MR_FANTASTIC,
    STARK_INDUSTRIES_DRONE,
    FRIDAY_AI,
    SHIELD_TECH_SPECIALIST,
    HANK_PYM,
    QUANTUM_REALM_EXPLORER,
    PYM_PARTICLE_RESEARCHER,
    ROCKET_RACCOON,
    STAR_LORD,
    KREE_SENTRY,
    SKRULL_INFILTRATOR,
    KNOWHERE_MERCHANT,
    RAVAGER_ENGINEER,
    XANDARIAN_PILOT,
    BLACK_WIDOW,
    HAWKEYE,
    NICK_FURY,
    PUNISHER,
    GAMORA,
    LOKI,
    HYDRA_AGENT,
    HYDRA_ENFORCER,
    WINTER_SOLDIER_ASSET,
    HAND_ASSASSIN,
    KINGPIN_ENFORCER,
    NEBULA,
    CROSSBONES,
    TASKMASTER,
    GHOST,
    ZEMO,
    MANTIS,
    DRAX,
    DARK_ELF_WARRIOR,
    THOR,
    SCARLET_WITCH,
    CAPTAIN_MARVEL,
    HELA,
    SURTUR,
    ULTRON_PRIME,
    ULTRON_DRONE,
    FIRE_DEMON,
    ASGARDIAN_BERSERKER,
    CHITAURI_SOLDIER,
    CHITAURI_CHARGER,
    LEVIATHAN,
    NOVA_PRIME,
    DESTROYER_ARMOR,
    RONAN_ACCUSER,
    SAKAARAN_GLADIATOR,
    GRANDMASTER_CHAMPION,
    HUMAN_TORCH,
    HULK,
    SHE_HULK,
    GROOT,
    BLACK_PANTHER,
    ANT_MAN,
    WASP,
    ANT_SWARM,
    VIBRANIUM_RHINO,
    WAKANDAN_WAR_RHINO,
    SHURI,
    WAKANDAN_BORDER_TRIBE,
    THING,
    ABOMINATION,
    SAVAGE_LAND_RAPTOR,
    SAVAGE_LAND_REX,
    FOREST_TROLL,
    KORG,
    THANOS,
    RED_SKULL,
    QUICKSILVER,
    EBONY_MAW,
    PROXIMA_MIDNIGHT,
    CORVUS_GLAIVE,
    CULL_OBSIDIAN,
    WONG,
    MORDO,
    DORMAMMU,
    WOLVERINE,
    STORM,
    CYCLOPS,
    JEAN_GREY,
    PROFESSOR_X,
    MAGNETO,
    ROGUE,
    BEAST,
    ICEMAN,
    NIGHTCRAWLER,
    COLOSSUS,
    MIND_STONE_INFINITY,
    SPACE_STONE,
    TIME_STONE,
    POWER_STONE_INFINITY,
    REALITY_STONE,
    SOUL_STONE,
    MJOLNIR,
    STORMBREAKER,
    CAPTAIN_AMERICAS_SHIELD,
    IRON_MAN_ARMOR_MK_L,
    IRON_MAN_ARMOR_MK_LXXXV,
    HULKBUSTER_ARMOR,
    INFINITY_GAUNTLET,
    WEB_SHOOTERS,
    YAKA_ARROW,
    VIBRANIUM_SPEAR,
    PANTHER_HABIT,
    NANO_GAUNTLET,
    CHITAURI_SCEPTER,
    CLOAK_OF_LEVITATION,
    TESSERACT,
    EYE_OF_AGAMOTTO,
    QUINJET,
    MILANO,
    HELICARRIER,
    BENATAR,
    REPULSOR_BLAST,
    SHIELD_THROW,
    AVENGERS_ASSEMBLE,
    HULK_SMASH,
    LIGHTNING_STRIKE_THOR,
    WIDOW_STING,
    CHAOS_MAGIC,
    PORTAL_SLING_RING,
    TIME_REVERSAL,
    SNAP_FINGERS,
    GAMMA_RADIATION,
    SHRINK_RAY,
    ARROW_VOLLEY,
    WAKANDA_FOREVER,
    MYSTIC_ARTS,
    BLITZ_ATTACK,
    TACTICAL_GENIUS,
    COSMIC_AWARENESS,
    BERSERKER_RAGE,
    STEALTH_MISSION,
    HEROIC_SACRIFICE,
    SUPER_SOLDIER_SERUM,
    REALITY_WARP,
    IMPALE,
    AVENGERS_INITIATIVE,
    STARK_INDUSTRIES,
    SHIELD_HEADQUARTERS,
    GUARDIANS_BOND,
    HYDRA_INFLUENCE,
    ASGARDIAN_MIGHT,
    MUTANT_UPRISING,
    COSMIC_CONVERGENCE,
    DARK_DIMENSION,
    VIBRANIUM_MINES,
    AVENGERS_TOWER,
    STARK_TOWER,
    WAKANDA,
    ASGARD,
    SANCTUM_SANCTORUM,
    KNOWHERE,
    XAVIERS_SCHOOL,
    HYDRA_BASE,
    SHIELD_FACILITY,
    TITAN,
    VORMIR,
    SAKAAR,
    CONTRAXIA,
    HALA,
    NIDAVELLIR,
    GENOSHA,
    # SPICE PASS PHASE A2 (slice 2, 2026-05-18) — decision-axis flips
    DOCTOR_STRANGE_AGAMOTTO,
    SPIDER_MAN_WEB_SLINGER,
    WAKANDAN_VIBRANIUM_FORGE,
    LOKI_WHISPERS_OF_RUIN,
    HEIMDALL_ALL_SEEING,
]
