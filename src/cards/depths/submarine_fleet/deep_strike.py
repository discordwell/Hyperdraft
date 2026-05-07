"""
SUBS — Deep-Strike archetype (DS).

Combo / control. Stalls 4-5 turns with Mines and chump-blockers, hoarding
Sonar. Then a single huge Vessel (Black Demon X-7, Triton-Class) dives
from SURFACE to CRUSH in one turn and detonates.

Mechanics emphasised here:
  - Crush-Dive triggers (DEPTHS_DIVE / DEPTHS_SURFACE_VESSEL filtered by
    ``payload.get("object_id") == obj.id``)
  - Charge-Swap doctrines (activated abilities emitting DEPTHS_RESUPPLY)
  - Hybrid ``{X(T/S)}`` costs (Contingency Plan, Final Surge)
  - Sacrifice-into-damage (Implosion Strike)
  - "First dive each turn is free" (Deep Vector Doctrine — needs
    QUERY_COST plumbing the engine doesn't yet expose; stubbed)
  - "dives cost 0" (Bathyscaphe Pilot — also QUERY_COST; stubbed)
  - "each Crush-Dive trigger fires twice" (Cold-Water Engineer — needs
    a trigger-doubler shim the engine doesn't yet expose; stubbed)

Each card matches the SUBS doc's Deep-Strike table (30 entries).
"""

from __future__ import annotations

from typing import Optional

from src.cards.interceptor_helpers import make_activated_ability
from src.engine.depths import (
    DepthBand,
    get_flagship,
    is_vessel,
    vessels_at_depth,
)
from src.engine.types import (
    CardDefinition,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)

from ._factories import (
    make_action,
    make_crew,
    make_doctrine,
    make_mine,
    make_vessel,
    make_weapon,
)


# ---------------------------------------------------------------------------
# Crush-Dive trigger helper
# ---------------------------------------------------------------------------

def _make_crush_dive_trigger(
    obj: GameObject,
    effect_fn,
    *,
    description: str = "Crush-Dive trigger",
) -> Interceptor:
    """Custom interceptor: fires when ``obj`` itself dives or surfaces.

    Listens on both ``DEPTHS_DIVE`` and ``DEPTHS_SURFACE_VESSEL`` events
    whose payload's ``object_id`` matches ``obj.id``. ``effect_fn`` is
    called as ``(event, state) -> list[Event]`` and the returned events
    are queued via ``InterceptorResult.REACT`` (same shape as the
    standard make_etb_trigger flow).
    """

    src_id = obj.id

    def _filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.DEPTHS_DIVE, EventType.DEPTHS_SURFACE_VESSEL):
            return False
        if event.payload.get("object_id") != src_id:
            return False
        # Source must still exist and be on the battlefield (Crush-Dive
        # triggers from sacrificed/sunk vessels don't fire).
        src = state.objects.get(src_id)
        if src is None:
            return False
        return src.zone == ZoneType.BATTLEFIELD

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state) or []
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(new_events),
        )

    return Interceptor(
        id=new_id(),
        source=src_id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )


# ---------------------------------------------------------------------------
# Common event builders
# ---------------------------------------------------------------------------

def _gain_charges_event(
    source: GameObject,
    *,
    tc: int = 0,
    sc: int = 0,
) -> Event:
    """Emit a DEPTHS_RESUPPLY with explicit pool gains (no per-turn cap math)."""
    return Event(
        type=EventType.DEPTHS_RESUPPLY,
        payload={
            "player": source.controller,
            "tc_gained": tc,
            "sc_gained": sc,
            "reason": "card_effect",
        },
        source=source.id,
        controller=source.controller,
    )


def _draw_event(source: GameObject, *, count: int = 1) -> Event:
    return Event(
        type=EventType.DRAW,
        payload={"player": source.controller, "count": count},
        source=source.id,
        controller=source.controller,
    )


def _damage_event(source: GameObject, target_id: str, amount: int, *, reason: str = "ability") -> Event:
    return Event(
        type=EventType.DAMAGE,
        payload={
            "target": target_id,
            "amount": amount,
            "source": source.id,
            "is_combat": False,
            "reason": reason,
        },
        source=source.id,
        controller=source.controller,
    )


def _pt_mod_event(source: GameObject, *, target_id: Optional[str] = None,
                  power_mod: int = 0, toughness_mod: int = 0,
                  duration: str = "end_of_turn") -> Event:
    return Event(
        type=EventType.PT_MODIFICATION,
        payload={
            "object_id": target_id or source.id,
            "power_mod": power_mod,
            "toughness_mod": toughness_mod,
            "duration": duration,
        },
        source=source.id,
        controller=source.controller,
    )


def _dive_event(vessel: GameObject) -> Event:
    """Synthetic DEPTHS_DIVE event (no cost paid)."""
    current = vessel.state.depth_band or DepthBand.SURFACE
    if current is DepthBand.CRUSH:
        # Stay put; emit a no-op-ish dive that engine can ignore.
        new_band = current
    else:
        new_band = DepthBand(int(current.value) + 1)
    # Mutate the band immediately so any same-frame triggers see the new band.
    vessel.state.depth_band = new_band
    return Event(
        type=EventType.DEPTHS_DIVE,
        payload={
            "object_id": vessel.id,
            "from_band": current,
            "to_band": new_band,
            "controller": vessel.controller,
            "reason": "card_effect",
        },
        source=vessel.id,
        controller=vessel.controller,
    )


def _opposing_flagship(state: GameState, my_player_id: str) -> Optional[GameObject]:
    for pid in state.players:
        if pid == my_player_id:
            continue
        fs = get_flagship(pid, state)
        if fs is not None:
            return fs
    return None


def _opposing_vessels(state: GameState, my_player_id: str) -> list[GameObject]:
    out: list[GameObject] = []
    bf = state.zones.get("battlefield")
    if not bf:
        return out
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None or not is_vessel(obj):
            continue
        if obj.controller == my_player_id:
            continue
        out.append(obj)
    return out


def _my_vessels(state: GameState, my_player_id: str, *, include_flagship: bool = False) -> list[GameObject]:
    out: list[GameObject] = []
    bf = state.zones.get("battlefield")
    if not bf:
        return out
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None or not is_vessel(obj):
            continue
        if obj.controller != my_player_id:
            continue
        if not include_flagship and "Flagship" in obj.characteristics.subtypes:
            continue
        out.append(obj)
    return out


# ---------------------------------------------------------------------------
# Per-card setup functions
# ---------------------------------------------------------------------------

# --- Pressure Probe: Crush-Dive — gain 1 SC ---------------------------------

def _pressure_probe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(event: Event, st: GameState) -> list[Event]:
        return [_gain_charges_event(obj, sc=1)]
    return [_make_crush_dive_trigger(obj, _effect, description="Crush-Dive: gain 1 SC")]


# --- Pressure Hull Veteran: Crush-Dive — draw 1 -----------------------------

def _pressure_hull_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(event: Event, st: GameState) -> list[Event]:
        return [_draw_event(obj, count=1)]
    return [_make_crush_dive_trigger(obj, _effect, description="Crush-Dive: draw 1")]


# --- Deep-Lurker: Crush-Dive — gain +1/+0 EOT --------------------------------

def _deep_lurker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(event: Event, st: GameState) -> list[Event]:
        return [_pt_mod_event(obj, target_id=obj.id, power_mod=1, toughness_mod=0)]
    return [_make_crush_dive_trigger(obj, _effect, description="Crush-Dive: +1/+0 EOT")]


# --- Bathysphere Veteran: Crush-Dive — +0/+2 EOT -----------------------------

def _bathysphere_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(event: Event, st: GameState) -> list[Event]:
        return [_pt_mod_event(obj, target_id=obj.id, power_mod=0, toughness_mod=2)]
    return [_make_crush_dive_trigger(obj, _effect, description="Crush-Dive: +0/+2 EOT")]


# --- Black Demon X-7: Crush-Dive — deal 4 damage ----------------------------

def _black_demon_x7_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(event: Event, st: GameState) -> list[Event]:
        # AI/UI picks a target via the targeting system normally; for now
        # default to opposing flagship so the trigger always lands.
        target = _opposing_flagship(st, obj.controller)
        if target is None:
            return []
        return [_damage_event(obj, target.id, 4, reason="crush_dive")]
    return [_make_crush_dive_trigger(obj, _effect, description="Crush-Dive: deal 4 damage to a Vessel")]


# --- Triton-Class: Whenever this dives, gain 2 TC ---------------------------

def _triton_class_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DEPTHS_DIVE:
            return False
        if event.payload.get("object_id") != src_id:
            return False
        src = st.objects.get(src_id)
        if src is None:
            return False
        return src.zone == ZoneType.BATTLEFIELD

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_gain_charges_event(obj, tc=2)],
        )

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


# --- Shadow-Vector: Crush-Dive — deal 2 to opposing Flagship ----------------

def _shadow_vector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _effect(event: Event, st: GameState) -> list[Event]:
        target = _opposing_flagship(st, obj.controller)
        if target is None:
            return []
        return [_damage_event(obj, target.id, 2, reason="crush_dive")]
    return [_make_crush_dive_trigger(obj, _effect, description="Crush-Dive: deal 2 to opposing Flagship")]


# --- Salvage Diver: {2S}: dive 1 band ---------------------------------------

def _salvage_diver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _dive_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [_dive_event(o)]
    make_activated_ability(
        obj, cost="{2S}", effect_fn=_dive_effect,
        description="{2S}: dive 1 band",
    )
    return []


# --- Frogman Squad: {1S}: tap target Vessel ---------------------------------

def _frogman_squad_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _tap_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        first = targets[0]
        target_id = (
            getattr(first, "object_id", None)
            or getattr(first, "id", None)
            or first
        )
        return [Event(
            type=EventType.TAP_TARGET,
            payload={"object_id": target_id, "target_id": target_id},
            source=o.id, controller=o.controller,
        )]
    make_activated_ability(
        obj, cost="{1S}", effect_fn=_tap_effect,
        description="{1S}: tap target Vessel",
        targets_required=1, target_kind="any",
    )
    return []


# --- Battery Reroute (Doctrine): {2T} → 1 SC; {2S} → 1 TC, each once/turn ---

def _battery_reroute_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _t_to_s(o: GameObject, st: GameState, targets) -> list[Event]:
        return [_gain_charges_event(o, sc=1)]
    def _s_to_t(o: GameObject, st: GameState, targets) -> list[Event]:
        return [_gain_charges_event(o, tc=1)]
    make_activated_ability(
        obj, cost="{2T}", effect_fn=_t_to_s,
        description="{2T}: gain 1 SC", once_per_turn=True,
    )
    make_activated_ability(
        obj, cost="{2S}", effect_fn=_s_to_t,
        description="{2S}: gain 1 TC", once_per_turn=True,
    )
    return []


# --- Crush-Depth Doctrine: 2+ band changes/turn → 1 to opposing Flagship ----

def _crush_depth_doctrine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tracks per-vessel band changes per turn. On the 2nd change, fires once."""
    src_id = obj.id

    def _filter(event: Event, st: GameState) -> bool:
        if event.type not in (EventType.DEPTHS_DIVE, EventType.DEPTHS_SURFACE_VESSEL):
            return False
        # Must be a vessel we control
        oid = event.payload.get("object_id")
        if not oid:
            return False
        vessel = st.objects.get(oid)
        if vessel is None or not is_vessel(vessel):
            return False
        if vessel.controller != obj.controller:
            return False
        src = st.objects.get(src_id)
        return src is not None and src.zone == ZoneType.BATTLEFIELD

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        td = getattr(st, "turn_data", None)
        if td is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        bucket = td.setdefault(f"_crush_depth_changes_{src_id}", {})
        oid = event.payload.get("object_id")
        bucket[oid] = int(bucket.get(oid, 0)) + 1
        # Fire on the 2nd change (and exactly once: only the transition
        # from 1 -> 2 emits the damage event).
        if bucket[oid] != 2:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = _opposing_flagship(st, obj.controller)
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_damage_event(obj, target.id, 1, reason="crush_depth_doctrine")],
        )

    # Reset the per-turn tracker on TURN_END so it doesn't carry over.
    def _reset_filter(event: Event, st: GameState) -> bool:
        return event.type == EventType.TURN_END

    def _reset_handler(event: Event, st: GameState) -> InterceptorResult:
        td = getattr(st, "turn_data", None)
        if td is not None:
            td.pop(f"_crush_depth_changes_{src_id}", None)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=src_id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_filter,
            handler=_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=src_id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_reset_filter,
            handler=_reset_handler,
            duration="while_on_battlefield",
        ),
    ]


# --- Sonar Hoard Doctrine: at end step, if SC >= 6, draw 1 ------------------

def _sonar_hoard_doctrine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get("phase") != "end_step":
            return False
        if st.active_player != obj.controller:
            return False
        src = st.objects.get(src_id)
        return src is not None and src.zone == ZoneType.BATTLEFIELD

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        player = st.players.get(obj.controller)
        if player is None or int(getattr(player, "sc", 0)) < 6:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_draw_event(obj, count=1)],
        )

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


# --- Deep Vector Doctrine: first dive each turn for each Vessel is free ----

def _deep_vector_doctrine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    TODO: requires QUERY_COST hook for dive cost. The depths engine pays
    {1S} for dive directly inside ``dive_vessel`` rather than emitting a
    cost-query event, so we cannot intercept the cost transparently from
    a card. As a stub the doctrine registers no interceptors today —
    future engine work would add a DEPTHS_QUERY_DIVE_COST event for cards
    like this and Bathyscaphe Pilot to listen on.

    Track shape if/when wired:
        state.turn_data['_dives_used_<vessel_id>'] = int  # reset on TURN_END
    """
    return []


# --- Cold-Water Engineer (Crew): each Crush-Dive trigger fires twice -------

def _cold_water_engineer_attach_effect(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    TODO: requires a trigger-doubler hook the engine doesn't yet expose.
    The cleanest path would be a per-target marker
    ``equipped.state._crush_dive_doubler = True`` that crush-dive triggers
    consult, but that requires every Crush-Dive helper to read a flag —
    out of scope for this archetype file. Stubbed: the equipment still
    attaches and grants nothing.
    """
    # We still want to emit the standard equipment attach interceptor so
    # the Crew physically attaches; the +0/+0 mod is a no-op.
    from src.cards.interceptor_helpers import make_equipment_setup
    return make_equipment_setup()(obj, state)


# --- Crush Capacitor (Weapon): when equipped changes depth, deal 1 to Flag --

def _crush_capacitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Track the equipped target via the standard attach hook. On any DEPTHS_DIVE
    or DEPTHS_SURFACE_VESSEL whose object_id matches the equipped target,
    deal 1 to the opposing Flagship.
    """
    src_id = obj.id

    def _filter(event: Event, st: GameState) -> bool:
        if event.type not in (EventType.DEPTHS_DIVE, EventType.DEPTHS_SURFACE_VESSEL):
            return False
        src = st.objects.get(src_id)
        if src is None or src.zone != ZoneType.BATTLEFIELD:
            return False
        attached_to = src.state.attached_to
        if attached_to is None:
            return False
        return event.payload.get("object_id") == attached_to

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        target = _opposing_flagship(st, obj.controller)
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_damage_event(obj, target.id, 1, reason="crush_capacitor")],
        )

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


# --- Scuba Saboteur: on sink, may put a Mine from hand free at any depth ---

def _scuba_saboteur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    TODO: requires hand-zone search + free-cast plumbing. We register a
    death trigger that emits a marker event so an AI/UI hook can pick a
    Mine from hand and lay it for free; until that surface exists, the
    trigger fires but produces no game-state change.
    """
    src_id = obj.id

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get("object_id") == src_id

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        # Marker event — picked up by the future "may-lay-mine" handler.
        marker = Event(
            type=EventType.MAY_SACRIFICE,  # reusing MAY_* as marker scaffold
            payload={
                "player": obj.controller,
                "reason": "scuba_saboteur_lay_mine",
                "source": obj.id,
            },
            source=obj.id, controller=obj.controller,
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[marker])

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="until_leaves",
    )]


# ---------------------------------------------------------------------------
# Cast-effect functions for Action cards
# ---------------------------------------------------------------------------

def _crush_depth_charges_cast(obj: GameObject, state: GameState) -> list[Event]:
    """
    Deal 4 damage to target Vessel ignoring depth modifier.

    Targeting flow: tries first chosen_target; falls back to any opposing
    vessel with the highest hull. The "ignore depth modifier" flag lives
    on the DAMAGE payload as ``ignore_depth_modifier`` — combat-side
    transformer will respect it.
    """
    targets = list(getattr(obj.state, "chosen_targets", []) or [])
    target_id: Optional[str] = targets[0] if targets else None
    if target_id is None:
        opp = sorted(
            _opposing_vessels(state, obj.controller),
            key=lambda o: int(o.characteristics.toughness or 0),
            reverse=True,
        )
        if opp:
            target_id = opp[0].id
    if target_id is None:
        return []
    ev = _damage_event(obj, target_id, 4, reason="crush_depth_charges")
    ev.payload["ignore_depth_modifier"] = True
    return [ev]


def _pressure_wave_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Each my Vessel dives 1; each opposing Vessel takes 1."""
    events: list[Event] = []
    for v in _my_vessels(state, obj.controller, include_flagship=False):
        if v.state.depth_band is None or v.state.depth_band is DepthBand.CRUSH:
            continue
        events.append(_dive_event(v))
    for opp in _opposing_vessels(state, obj.controller):
        events.append(_damage_event(obj, opp.id, 1, reason="pressure_wave"))
    return events


def _contingency_plan_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Gain X charges in either pool (X chosen at cast time)."""
    x = int(getattr(obj.state, "x_value", 0) or 0)
    if x <= 0:
        return []
    # Default: split as even as possible, leaning Sonar (the constrained pool).
    sc = (x + 1) // 2
    tc = x - sc
    return [_gain_charges_event(obj, tc=tc, sc=sc)]


def _final_surge_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Target Vessel you control gains +X/+0 EOT and homing."""
    x = int(getattr(obj.state, "x_value", 0) or 0)
    targets = list(getattr(obj.state, "chosen_targets", []) or [])
    target_id: Optional[str] = targets[0] if targets else None
    if target_id is None:
        # Fall back: pick our highest-power Vessel.
        mine = sorted(
            _my_vessels(state, obj.controller, include_flagship=False),
            key=lambda o: int(o.characteristics.power or 0),
            reverse=True,
        )
        if mine:
            target_id = mine[0].id
    if target_id is None or x <= 0:
        return []
    return [
        _pt_mod_event(obj, target_id=target_id, power_mod=x, toughness_mod=0),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                "object_id": target_id,
                "keyword": "homing",
                "duration": "end_of_turn",
            },
            source=obj.id, controller=obj.controller,
        ),
    ]


def _deep_pulse_bomb_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 to each Vessel and the opposing Flagship; ignore depth modifier."""
    events: list[Event] = []
    bf = state.zones.get("battlefield")
    if not bf:
        return events
    for oid in bf.objects:
        v = state.objects.get(oid)
        if v is None or not is_vessel(v):
            continue
        ev = _damage_event(obj, v.id, 2, reason="deep_pulse_bomb")
        ev.payload["ignore_depth_modifier"] = True
        events.append(ev)
    # Also explicitly hit opposing flagship (already in iteration above, but
    # listed in flavor text — guard for the case where the flagship sits in
    # a separate sub-zone the iteration missed).
    opp = _opposing_flagship(state, obj.controller)
    if opp is not None and not any(
        e.payload.get("target") == opp.id for e in events
    ):
        ev = _damage_event(obj, opp.id, 2, reason="deep_pulse_bomb")
        ev.payload["ignore_depth_modifier"] = True
        events.append(ev)
    return events


def _battery_drain_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Opponent loses up to 3 SC. Direct mutation (no negative-charge event)."""
    events: list[Event] = []
    for pid, player in state.players.items():
        if pid == obj.controller:
            continue
        loss = min(3, int(getattr(player, "sc", 0) or 0))
        if loss <= 0:
            continue
        player.sc -= loss
        events.append(Event(
            type=EventType.DEPTHS_RESUPPLY,
            payload={
                "player": pid,
                "tc_gained": 0,
                "sc_gained": -loss,
                "reason": "battery_drain",
            },
            source=obj.id, controller=obj.controller,
        ))
    return events


def _implosion_strike_cast(obj: GameObject, state: GameState) -> list[Event]:
    """
    Sacrifice a Vessel at DEEP, deal damage equal to its hull to target
    Vessel or Flagship.

    Picks the deepest sacrificeable Vessel (highest hull at DEEP) so the
    AI default is "use the biggest hammer."
    """
    deep_mine = [
        v for v in _my_vessels(state, obj.controller, include_flagship=False)
        if v.state.depth_band is DepthBand.DEEP
    ]
    if not deep_mine:
        return []
    sacrificed = max(deep_mine, key=lambda v: int(v.characteristics.toughness or 0))
    hull = int(sacrificed.characteristics.toughness or 0)
    if hull <= 0:
        return []

    targets = list(getattr(obj.state, "chosen_targets", []) or [])
    target_id: Optional[str] = targets[0] if targets else None
    if target_id is None:
        opp_fs = _opposing_flagship(state, obj.controller)
        if opp_fs is not None:
            target_id = opp_fs.id
    if target_id is None:
        return []

    sac = Event(
        type=EventType.SACRIFICE,
        payload={"object_id": sacrificed.id},
        source=obj.id, controller=obj.controller,
    )
    dmg = _damage_event(obj, target_id, hull, reason="implosion_strike")
    dmg.payload["ignore_depth_modifier"] = True
    return [sac, dmg]


# ---------------------------------------------------------------------------
# CARD DEFINITIONS
# ---------------------------------------------------------------------------

# Vessels --------------------------------------------------------------------

BATHYSCAPHE_MITE = make_vessel(
    name="Bathyscaphe Mite",
    cost="{1S}",
    power=0, hull=2,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler", "defender"],
    text="Bottom-crawler. Defender.",
)

PRESSURE_PROBE = make_vessel(
    name="Pressure Probe",
    cost="{1T}",
    power=1, hull=1,
    subtypes={"Drone"},
    default_depth=DepthBand.DEEP,
    text="Crush-Dive: gain 1 SC.",
    setup_interceptors=_pressure_probe_setup,
)

SALVAGE_DIVER = make_vessel(
    name="Salvage Diver",
    cost="{2S}",
    power=1, hull=3,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler"],
    text="Bottom-crawler. {2S}: dive 1 band.",
    setup_interceptors=_salvage_diver_setup,
)

PRESSURE_HULL_VETERAN = make_vessel(
    name="Pressure Hull Veteran",
    cost="{3T,1S}",
    power=3, hull=4,
    default_depth=DepthBand.MID,
    text="Crush-Dive: draw 1.",
    setup_interceptors=_pressure_hull_veteran_setup,
)

DEEP_LURKER = make_vessel(
    name="Deep-Lurker",
    cost="{2T,1S}",
    power=2, hull=3,
    default_depth=DepthBand.MID,
    keywords=["bottom_crawler"],
    text="Bottom-crawler. Crush-Dive: this gets +1/+0 EOT.",
    setup_interceptors=_deep_lurker_setup,
)

BLACK_DEMON_X7 = make_vessel(
    name="Black Demon X-7",
    cost="{4T,4S}",
    power=6, hull=4,
    default_depth=DepthBand.SURFACE,
    keywords=["homing"],
    is_legendary=True,
    text="Crush-Dive: deal 4 damage to target Vessel. Homing.",
    setup_interceptors=_black_demon_x7_setup,
)

TRITON_CLASS = make_vessel(
    name="Triton-Class",
    cost="{6T,2S}",
    power=8, hull=8,
    default_depth=DepthBand.SURFACE,
    keywords=["homing"],
    is_legendary=True,
    text="Homing. Whenever this dives, gain 2 TC.",
    setup_interceptors=_triton_class_setup,
)

SCUBA_SABOTEUR = make_vessel(
    name="Scuba Saboteur",
    cost="{2T,1S}",
    power=2, hull=2,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler"],
    text=("Bottom-crawler. When this is sunk, you may put a Mine card from "
          "your hand on the battlefield free at any depth."),
    setup_interceptors=_scuba_saboteur_setup,
)

COELACANTH_CLASS = make_vessel(
    name="Coelacanth Class",
    cost="{3T,2S}",
    power=4, hull=4,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler", "homing"],
    text="Bottom-crawler. Homing.",
)

BATHYSPHERE_VETERAN = make_vessel(
    name="Bathysphere Veteran",
    cost="{3T,1S}",
    power=3, hull=5,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler"],
    text="Bottom-crawler. Crush-Dive: this gets +0/+2 EOT.",
    setup_interceptors=_bathysphere_veteran_setup,
)

FROGMAN_SQUAD = make_vessel(
    name="Frogman Squad",
    cost="{2S}",
    power=2, hull=2,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler"],
    text="Bottom-crawler. {1S}: tap target Vessel.",
    setup_interceptors=_frogman_squad_setup,
)

SHADOW_VECTOR = make_vessel(
    name="Shadow-Vector",
    cost="{4T,1S}",
    power=4, hull=4,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler"],
    text="Crush-Dive: deal 2 to opposing Flagship. Bottom-crawler.",
    setup_interceptors=_shadow_vector_setup,
)


# Crew -----------------------------------------------------------------------

# TODO: Bathyscaphe Pilot — "dives cost 0" needs QUERY_COST plumbing the
#       engine doesn't yet expose. Stubbed: attaches as a vanilla Crew with
#       no stat changes. Future work: register a QUERY_COST interceptor
#       gated on event.payload.get('reason') == 'dive' and source ==
#       equipped target's id.
BATHYSCAPHE_PILOT = make_crew(
    name="Bathyscaphe Pilot",
    cost="{1T,1S}",
    text="Equipped Vessel's dives cost 0.",
)

# Thermocline Cloak — "detection cost +2 while at MID/DEEP/CRUSH" requires
# a detection-cost transform hook on the equipped target. Engine has
# silent_running as a flat +1; +2-with-depth-gate is unmodelled. Stub
# attach with no stats.
# TODO: detection-cost transform on equipped target gated by depth band.
THERMOCLINE_CLOAK = make_crew(
    name="Thermocline Cloak",
    cost="{2S}",
    text="Equipped Vessel: detection cost +2 while at MID/DEEP/CRUSH.",
)

SOUND_CHANNEL_PILOT = make_crew(
    name="Sound-Channel Pilot",
    cost="{2T,2S}",
    keywords_to_grant=["homing", "reach"],
    text="Equipped Vessel has homing and reach.",
)

# TODO: Cold-Water Engineer — needs trigger-doubler hook (no engine shim
# yet for "this trigger fires twice"). Attaches as a vanilla Crew.
COLD_WATER_ENGINEER = make_crew(
    name="Cold-Water Engineer",
    cost="{2T,1S}",
    text="Equipped Vessel: each Crush-Dive trigger fires twice.",
    setup_interceptors=_cold_water_engineer_attach_effect,
)


# Weapons --------------------------------------------------------------------

def _dive_tube_attach(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Equipment that grants the equipped target a {1S}: dive 1 band ability.
    Uses the granted-activated-abilities pathway on attach.
    """
    from src.cards.interceptor_helpers import make_equipment_setup

    def _granted_dive(o: GameObject, st: GameState, targets) -> list[Event]:
        # ``o`` is the equipped target (the granted ability's host), not
        # the weapon.
        return [_dive_event(o)]

    return make_equipment_setup(
        granted_activated_abilities=[{
            "cost": "{1S}",
            "effect_fn": _granted_dive,
            "description": "{1S}: dive 1 band",
        }],
    )(obj, state)

DIVE_TUBE = make_weapon(
    name="Dive Tube",
    cost="{1S}",
    text="Equipped Vessel: {1S}: dive 1 band.",
    setup_interceptors=_dive_tube_attach,
)

CRUSH_CAPACITOR = make_weapon(
    name="Crush Capacitor",
    cost="{2T,1S}",
    text="Equipped Vessel: when it changes depth, deal 1 to opposing Flagship.",
    setup_interceptors=_crush_capacitor_setup,
)


# Doctrines ------------------------------------------------------------------

BATTERY_REROUTE = make_doctrine(
    name="Battery Reroute",
    cost="{1S}",
    text="{2T}: gain 1 SC. {2S}: gain 1 TC. Each once per turn.",
    setup_interceptors=_battery_reroute_setup,
)

CRUSH_DEPTH_DOCTRINE = make_doctrine(
    name="Crush-Depth Doctrine",
    cost="{2T,1S}",
    text=("Whenever a Vessel you control changes depth 2+ bands in a turn, "
          "deal 1 to opposing Flagship."),
    setup_interceptors=_crush_depth_doctrine_setup,
)

SONAR_HOARD_DOCTRINE = make_doctrine(
    name="Sonar Hoard Doctrine",
    cost="{2S}",
    text="At your end step, if you have 6+ SC, draw 1.",
    setup_interceptors=_sonar_hoard_doctrine_setup,
)

DEEP_VECTOR_DOCTRINE = make_doctrine(
    name="Deep Vector Doctrine",
    cost="{3S}",
    text="The first dive each turn for each Vessel you control is free.",
    setup_interceptors=_deep_vector_doctrine_setup,  # TODO: requires QUERY_COST
)


def _abyssal_doctrine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Your Vessels at DEEP/CRUSH have homing and silent_running."""
    src_id = obj.id

    def _ability_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get("object_id")
        target = st.objects.get(target_id)
        if target is None or not is_vessel(target):
            return False
        if target.controller != obj.controller:
            return False
        if target.state.depth_band not in (DepthBand.DEEP, DepthBand.CRUSH):
            return False
        src = st.objects.get(src_id)
        return src is not None and src.zone == ZoneType.BATTLEFIELD

    def _ability_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get("granted", []))
        for kw in ("homing", "silent_running"):
            if kw not in granted:
                granted.append(kw)
        new_event.payload["granted"] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_ability_filter,
        handler=_ability_handler,
        duration="while_on_battlefield",
    )]


ABYSSAL_DOCTRINE = make_doctrine(
    name="Abyssal Doctrine",
    cost="{4T,3S}",
    text="Your Vessels at DEEP/CRUSH get homing and silent_running.",
    setup_interceptors=_abyssal_doctrine_setup,
)


# Actions --------------------------------------------------------------------

CRUSH_DEPTH_CHARGES = make_action(
    name="Crush-Depth Charges",
    cost="{2T,2S}",
    text="Deal 4 damage to target Vessel ignoring depth modifier.",
    cast_effect_fn=_crush_depth_charges_cast,
)

PRESSURE_WAVE = make_action(
    name="Pressure Wave",
    cost="{3T,1S}",
    text="Each Vessel you control dives 1 band; each opposing Vessel takes 1 damage.",
    cast_effect_fn=_pressure_wave_cast,
)

CONTINGENCY_PLAN = make_action(
    name="Contingency Plan",
    cost="{X(T/S)}",
    text="Gain X charges in either pool (at most until cap).",
    cast_effect_fn=_contingency_plan_cast,
)

DEEP_PULSE_BOMB = make_action(
    name="Deep Pulse Bomb",
    cost="{2T,2S}",
    text="Deal 2 damage to each Vessel and to the opposing Flagship; ignore depth modifier.",
    cast_effect_fn=_deep_pulse_bomb_cast,
)

FINAL_SURGE = make_action(
    name="Final Surge",
    cost="{X(T/S)}",
    text="Target Vessel you control gains +X/+0 EOT and homing.",
    cast_effect_fn=_final_surge_cast,
)

BATTERY_DRAIN = make_action(
    name="Battery Drain",
    cost="{1T,1S}",
    text="Opponent loses up to 3 SC.",
    cast_effect_fn=_battery_drain_cast,
)

IMPLOSION_STRIKE = make_action(
    name="Implosion Strike",
    cost="{4T,2S}",
    text="Sacrifice a Vessel at DEEP: deal damage equal to its hull to target Vessel or Flagship.",
    cast_effect_fn=_implosion_strike_cast,
)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

DEEP_STRIKE_CARDS: dict[str, CardDefinition] = {
    card.name: card
    for card in [
        # Vessels (12)
        BATHYSCAPHE_MITE,
        PRESSURE_PROBE,
        SALVAGE_DIVER,
        PRESSURE_HULL_VETERAN,
        DEEP_LURKER,
        BLACK_DEMON_X7,
        TRITON_CLASS,
        SCUBA_SABOTEUR,
        COELACANTH_CLASS,
        BATHYSPHERE_VETERAN,
        FROGMAN_SQUAD,
        SHADOW_VECTOR,
        # Crew (4)
        BATHYSCAPHE_PILOT,
        THERMOCLINE_CLOAK,
        SOUND_CHANNEL_PILOT,
        COLD_WATER_ENGINEER,
        # Weapons (2)
        DIVE_TUBE,
        CRUSH_CAPACITOR,
        # Doctrines (5)
        BATTERY_REROUTE,
        CRUSH_DEPTH_DOCTRINE,
        SONAR_HOARD_DOCTRINE,
        DEEP_VECTOR_DOCTRINE,
        ABYSSAL_DOCTRINE,
        # Actions (7)
        CRUSH_DEPTH_CHARGES,
        PRESSURE_WAVE,
        CONTINGENCY_PLAN,
        DEEP_PULSE_BOMB,
        FINAL_SURGE,
        BATTERY_DRAIN,
        IMPLOSION_STRIKE,
    ]
}

assert len(DEEP_STRIKE_CARDS) == 30, (
    f"DEEP_STRIKE_CARDS expected 30, got {len(DEEP_STRIKE_CARDS)}"
)


__all__ = ["DEEP_STRIKE_CARDS"]
