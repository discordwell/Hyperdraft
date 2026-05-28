"""
Neutral cards for the SUBS (Submarine Fleet) set.

The Neutral archetype is the "tutorial floor" of the depth engine — mostly
vanilla Vessels, vanilla Crew, plain Mines, and one-shot Actions that
don't lean into any of the four archetypal mechanics (Wolfpack swarm,
Silent Hunter stealth, Carrier drones, Deep-Strike combo). Most cards are
implementable as a single factory call; the half-dozen that need
interceptors use the standard ``interceptor_helpers`` patterns.

Design references:
  - Card list:          docs/sets/SUBS.md (section 4 — "Neutral — 30 cards")
  - Engine doc:         docs/games/depths.md
  - Shared factories:   src/cards/depths/submarine_fleet/_factories.py
  - Helpers:            src/cards/interceptor_helpers.py

Open implementation questions (see ``# TODO:`` markers below):
  - Brace for Impact: needs a damage-prevention shield primitive.
  - Helm Officer:     firing_depth_band override needs a Crew → AttackerSpec
    bridge that ``depths_combat`` doesn't yet expose.
"""

from __future__ import annotations

from typing import Optional

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

from src.cards.depths.submarine_fleet._factories import (
    DepthBand,
    make_action,
    make_crew,
    make_doctrine,
    make_mine,
    make_vessel,
    make_weapon,
    make_drone_token,
    make_depths_dive_phase_trigger,
)
from src.engine.depths import is_vessel


# =============================================================================
# Vanilla Vessels (3)
# =============================================================================

DIESEL_ELECTRIC_SUB = make_vessel(
    name="Diesel-Electric Sub",
    cost="{2T}",
    power=2,
    hull=2,
    default_depth=DepthBand.SURFACE,
    subtypes={"Submarine"},
    text="Vanilla generic body.",
)

COASTAL_PATROL_BOAT = make_vessel(
    name="Coastal Patrol Boat",
    cost="{1T}",
    power=1,
    hull=2,
    default_depth=DepthBand.SURFACE,
    subtypes={"Submarine"},
    text="Vanilla.",
)

STEAM_PINNACE = make_vessel(
    name="Steam Pinnace",
    cost="{1T}",
    power=2,
    hull=1,
    default_depth=DepthBand.SURFACE,
    subtypes={"Submarine"},
    text="Vanilla.",
)


# =============================================================================
# Destroyers w/ reach (2)
# =============================================================================
# Destroyers are surface ships with the `reach` keyword so they can
# intercept across two depth bands (per docs/games/depths.md §7).

LIGHT_CRUISER = make_vessel(
    name="Light Cruiser",
    cost="{3T}",
    power=3,
    hull=3,
    default_depth=DepthBand.SURFACE,
    subtypes={"Destroyer"},
    keywords=["reach"],
    text="Reach.",
)

COASTGUARD_CUTTER = make_vessel(
    name="Coastguard Cutter",
    cost="{2T}",
    power=2,
    hull=3,
    default_depth=DepthBand.SURFACE,
    subtypes={"Destroyer"},
    keywords=["reach"],
    text="Reach.",
)


# =============================================================================
# Vanilla Crew with stat boosts (3)
# =============================================================================

RESERVE_ENGINEER = make_crew(
    name="Reserve Engineer",
    cost="{1T}",
    power_mod=1,
    toughness_mod=1,
    text="Equipped Vessel gets +1/+1.",
)

REAR_TUBE_LOADER = make_crew(
    name="Rear-Tube Loader",
    cost="{1T}",
    power_mod=0,
    toughness_mod=2,
    text="Equipped Vessel gets +0/+2.",
)

STOKER_MATE = make_crew(
    name="Stoker Mate",
    cost="{1T}",
    power_mod=1,
    toughness_mod=0,
    text="Equipped Vessel gets +1/+0.",
)


# =============================================================================
# Crew with keyword grants (1)
# =============================================================================

SONAR_TECH = make_crew(
    name="Sonar Tech",
    cost="{1S}",
    keywords_to_grant=["silent_running"],
    text="Equipped Vessel has silent_running.",
)


# =============================================================================
# Crew with custom interceptors (3)
# =============================================================================

def _periscope_watch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At your upkeep, gain 1 SC. Only fires while attached to a Vessel."""
    def _gain_sc(event: Event, st: GameState) -> list[Event]:
        target_id = getattr(obj.state, "_attached_to", None) or getattr(
            obj.state, "_equipped_to", None
        )
        target = st.objects.get(target_id) if target_id else None
        if target is None or target.zone != ZoneType.BATTLEFIELD:
            return []
        # The DEPTHS_RESUPPLY event with player+sc_gained=1 is read by the
        # system resupply interceptor. We grant directly via the charge
        # system to bypass the cap-on-resupply path (this is a card effect,
        # not the per-turn resupply ramp).
        from src.engine.depths import DepthsChargeSystem
        game = getattr(st, "_game", None)
        if game is None:
            return []
        cs = getattr(game, "mana_system", None)
        if not isinstance(cs, DepthsChargeSystem):
            cs = DepthsChargeSystem(st)
        cs.add_charges(obj.controller, sc=1)
        return []
    return [make_depths_dive_phase_trigger(obj, _gain_sc)]


PERISCOPE_WATCH = make_crew(
    name="Periscope Watch",
    cost="{1S}",
    setup_interceptors=_periscope_watch_setup,
    text="Equipped Vessel: at your upkeep, gain 1 SC.",
)


def _compass_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped Vessel: dives cost 0 the first time each turn.

    We can't easily intercept the dive cost from a Crew (the
    ``dive_vessel`` action handler in ``src.engine.depths`` reads the
    cost as a hardcoded ``{1S}``), so we refund 1 SC after the first
    DEPTHS_DIVE event each turn for the equipped Vessel.
    """
    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DEPTHS_DIVE:
            return False
        target_id = getattr(obj.state, "_attached_to", None) or getattr(
            obj.state, "_equipped_to", None
        )
        if not target_id:
            return False
        if event.payload.get("object_id") != target_id:
            return False
        # Once-per-turn gate: store last refund turn on the Crew object.
        last_turn = getattr(obj.state, "_compass_refund_turn", None)
        if last_turn == st.turn_number:
            return False
        return True

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        from src.engine.depths import DepthsChargeSystem
        game = getattr(st, "_game", None)
        if game is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        cs = getattr(game, "mana_system", None)
        if not isinstance(cs, DepthsChargeSystem):
            cs = DepthsChargeSystem(st)
        cs.add_charges(obj.controller, sc=1)
        obj.state._compass_refund_turn = st.turn_number
        return InterceptorResult(action=InterceptorAction.PASS)

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )
    return [interceptor]


COMPASS_OFFICER = make_crew(
    name="Compass Officer",
    cost="{1T}",
    setup_interceptors=_compass_officer_setup,
    text="Equipped Vessel: dives cost 0 the first time each turn.",
)


# TODO: Helm Officer — "fire one band shallower" requires a Crew → combat
# bridge that lets the Crew override AttackerSpec.firing_depth_band when
# the equipped Vessel attacks. ``depths_combat`` doesn't currently expose
# that hook; the parameter is set at attack-declare time inside
# DepthsCombatManager and isn't queried per-vessel through an interceptor.
# Stubbed as a no-op Crew with the printed text so the card exists in the
# pool and can be wired once the combat module grows the hook.
def _helm_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []


HELM_OFFICER = make_crew(
    name="Helm Officer",
    cost="{1T}",
    setup_interceptors=_helm_officer_setup,
    text="Equipped Vessel can fire from one band shallower than its actual depth.",
)


# =============================================================================
# Weapons (2)
# =============================================================================

HULL_PLATE = make_weapon(
    name="Hull Plate",
    cost="{1T}",
    power_mod=0,
    toughness_mod=2,
    text="Equipped Vessel gets +0/+2.",
)


def _spare_torpedo_damage(obj: GameObject, st: GameState, targets: list) -> list[Event]:
    """{1T}: deal 1 damage to target Vessel. Decrements weapon charges."""
    if not targets:
        return []
    target_id = targets[0]
    if hasattr(target_id, "object_id"):
        target_id = target_id.object_id
    target = st.objects.get(target_id)
    if target is None or not is_vessel(target):
        return []
    # Decrement the weapon's charges; if it falls to 0, sink the weapon.
    current = int(getattr(obj.state, "depths_weapon_charges", 3) or 0)
    obj.state.depths_weapon_charges = max(0, current - 1)
    events: list[Event] = [Event(
        type=EventType.DAMAGE,
        payload={
            "target": target.id,
            "amount": 1,
            "source": obj.id,
            "is_combat": False,
            "reason": "spare_torpedo",
        },
        source=obj.id,
        controller=obj.controller,
    )]
    if obj.state.depths_weapon_charges <= 0:
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={"object_id": obj.id, "reason": "weapon_spent"},
            source=obj.id,
            controller=obj.controller,
        ))
    return events


SPARE_TORPEDO = make_weapon(
    name="Spare Torpedo",
    cost="{1T}",
    charges=3,
    granted_activated_abilities=[{
        "cost": "{1T}",
        "effect_fn": _spare_torpedo_damage,
        "description": "{1T}: deal 1 damage to target Vessel.",
        "targets_required": 1,
        "target_kind": "vessel",
    }],
    text="{1T}: deal 1 damage to target Vessel. (3 charges.)",
)


# =============================================================================
# Mines (4)
# =============================================================================

SONAR_BUOY = make_mine(
    name="Sonar Buoy",
    cost="{1T}",
    damage=2,
    default_depth=DepthBand.SURFACE,
    text="When triggered, deal 2 damage.",
)

MAGNETIC_MINE = make_mine(
    name="Magnetic Mine",
    cost="{1T,1S}",
    damage=3,
    default_depth=DepthBand.PERISCOPE,
    text="When triggered, deal 3 damage.",
)

ACOUSTIC_TRIP = make_mine(
    name="Acoustic Trip",
    cost="{2T,1S}",
    damage=4,
    default_depth=DepthBand.MID,
    text="When triggered, deal 4 damage.",
)

PRESSURE_MINE = make_mine(
    name="Pressure Mine",
    cost="{2T,2S}",
    damage=5,
    default_depth=DepthBand.DEEP,
    detect_triggering_vessel=True,
    text="When triggered, deal 5 damage and detect the triggering Vessel.",
)


# =============================================================================
# Doctrines (2)
# =============================================================================

def _captains_bell_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you deploy a Vessel, gain 1 TC.

    Listens for ZONE_CHANGE → BATTLEFIELD where the moved object is a
    Vessel controlled by the same controller as this Doctrine. Fires
    once per qualifying entry.
    """
    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("to_zone_type") != ZoneType.BATTLEFIELD:
            return False
        # The Doctrine itself enters via ZONE_CHANGE — don't fire on self.
        oid = event.payload.get("object_id")
        if oid == obj.id:
            return False
        moved = st.objects.get(oid) if oid else None
        if moved is None or not is_vessel(moved):
            return False
        if moved.controller != obj.controller:
            return False
        # Skip the Flagship (it ETBs once during setup, before this
        # doctrine is in play; safe defense in depth).
        if "Flagship" in moved.characteristics.subtypes:
            return False
        return True

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        from src.engine.depths import DepthsChargeSystem
        game = getattr(st, "_game", None)
        if game is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        cs = getattr(game, "mana_system", None)
        if not isinstance(cs, DepthsChargeSystem):
            cs = DepthsChargeSystem(st)
        cs.add_charges(obj.controller, tc=1)
        return InterceptorResult(action=InterceptorAction.PASS)

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )
    return [interceptor]


CAPTAINS_BELL = make_doctrine(
    name="Captain's Bell",
    cost="{2T,1S}",
    setup_interceptors=_captains_bell_setup,
    text="Whenever you deploy a Vessel, gain 1 TC.",
)


def _bridge_logbook_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At your upkeep, scry 1."""
    def _scry(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={
                "player": obj.controller,
                "amount": 1,
                "source_id": obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_depths_dive_phase_trigger(obj, _scry)]


BRIDGE_LOGBOOK = make_doctrine(
    name="Bridge Logbook",
    cost="{1S}",
    setup_interceptors=_bridge_logbook_setup,
    text="At your upkeep, scry 1.",
)


# =============================================================================
# Actions (12)
# =============================================================================

def _decoy_buoy_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Create a 0/2 Decoy Vessel token at SURFACE; can intercept once."""
    decoy_def = make_vessel(
        name="Decoy",
        cost=None,
        power=0,
        hull=2,
        default_depth=DepthBand.SURFACE,
        subtypes={"Decoy"},
        is_token=True,
        text="Can intercept once.",
    )
    # Mark the can-intercept-once flag on the token def so the engine /
    # combat module can read it when filtering blockers.
    decoy_def.depths_intercept_once = True
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            "controller": obj.controller,
            "token": decoy_def,
            "count": 1,
            "depth_band": DepthBand.SURFACE,
        },
        source=obj.id,
        controller=obj.controller,
    )]


DECOY_BUOY = make_action(
    name="Decoy Buoy",
    cost="{1T}",
    text="Create a 0/2 Decoy Vessel token at SURFACE; it can intercept once.",
    cast_effect_fn=_decoy_buoy_cast,
)


def _dive_order_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Up to 2 Vessels you control dive 1 band (free).

    With no targeting UI hooked yet, greedily dive the two most-shallow
    non-Flagship Vessels controlled by the caster — this gives the AI
    something useful to do with the card and matches the design intent.
    """
    events: list[Event] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return events
    candidates: list[tuple[int, GameObject]] = []
    for oid in battlefield.objects:
        target = state.objects.get(oid)
        if not target or target.controller != obj.controller:
            continue
        if not is_vessel(target):
            continue
        if "Flagship" in target.characteristics.subtypes:
            continue
        band = target.state.depth_band or DepthBand.SURFACE
        if band is DepthBand.CRUSH:
            continue
        candidates.append((int(band.value), target))
    candidates.sort(key=lambda pair: pair[0])
    for _, target in candidates[:2]:
        current = target.state.depth_band or DepthBand.SURFACE
        new_band = DepthBand(int(current.value) + 1)
        target.state.depth_band = new_band
        events.append(Event(
            type=EventType.DEPTHS_DIVE,
            payload={
                "object_id": target.id,
                "from_band": current,
                "to_band": new_band,
                "controller": obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


DIVE_ORDER = make_action(
    name="Dive Order",
    cost="{1S}",
    text="Up to 2 Vessels you control dive 1 band (free).",
    cast_effect_fn=_dive_order_cast,
)


def _surface_order_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Up to 2 Vessels you control surface 1 band."""
    events: list[Event] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return events
    candidates: list[tuple[int, GameObject]] = []
    for oid in battlefield.objects:
        target = state.objects.get(oid)
        if not target or target.controller != obj.controller:
            continue
        if not is_vessel(target):
            continue
        if "Flagship" in target.characteristics.subtypes:
            continue
        band = target.state.depth_band or DepthBand.SURFACE
        if band is DepthBand.SURFACE:
            continue
        # Sort by deepest-first so we surface the most-buried Vessels.
        candidates.append((-int(band.value), target))
    candidates.sort(key=lambda pair: pair[0])
    for _, target in candidates[:2]:
        current = target.state.depth_band or DepthBand.PERISCOPE
        new_band = DepthBand(int(current.value) - 1)
        target.state.depth_band = new_band
        events.append(Event(
            type=EventType.DEPTHS_SURFACE_VESSEL,
            payload={
                "object_id": target.id,
                "from_band": current,
                "to_band": new_band,
                "controller": obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


SURFACE_ORDER = make_action(
    name="Surface Order",
    cost="{0}",
    text="Up to 2 Vessels you control surface 1 band.",
    cast_effect_fn=_surface_order_cast,
)


def _resupply_run_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Gain 1 TC and 1 SC."""
    return [Event(
        type=EventType.DEPTHS_RESUPPLY,
        payload={
            "player": obj.controller,
            "tc_gained": 1,
            "sc_gained": 1,
            "source": "resupply_run",
        },
        source=obj.id,
        controller=obj.controller,
    )]


RESUPPLY_RUN = make_action(
    name="Resupply Run",
    cost="{1T}",
    text="Gain 1 TC and 1 SC.",
    cast_effect_fn=_resupply_run_cast,
)


def _chart_plot_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Draw 1; gain 1 SC."""
    return [
        Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "amount": 1, "source": obj.id},
            source=obj.id,
            controller=obj.controller,
        ),
        Event(
            type=EventType.DEPTHS_RESUPPLY,
            payload={
                "player": obj.controller,
                "tc_gained": 0,
                "sc_gained": 1,
                "source": "chart_plot",
            },
            source=obj.id,
            controller=obj.controller,
        ),
    ]


CHART_PLOT = make_action(
    name="Chart Plot",
    cost="{1S}",
    text="Draw 1; gain 1 SC.",
    cast_effect_fn=_chart_plot_cast,
)


def _damage_control_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Remove up to 3 damage from target Vessel you control.

    Targeting machinery isn't wired through cast_effect_fn yet, so we
    pick the most-damaged friendly Vessel as a sensible default. We emit
    a ``DAMAGE_REMOVE`` event; the depths system interceptor mutates
    ``state.damage`` (and mirrors onto ``player.life`` for Flagship).
    """
    candidates: list[GameObject] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    for oid in battlefield.objects:
        target = state.objects.get(oid)
        if not target or target.controller != obj.controller:
            continue
        if not is_vessel(target):
            continue
        if (target.state.damage or 0) <= 0:
            continue
        candidates.append(target)
    if not candidates:
        return []
    candidates.sort(key=lambda v: -(v.state.damage or 0))
    pick = candidates[0]
    return [Event(
        type=EventType.DAMAGE_REMOVE,
        payload={"object_id": pick.id, "amount": 3},
        source=obj.id,
        controller=obj.controller,
    )]


DAMAGE_CONTROL = make_action(
    name="Damage Control",
    cost="{1T}",
    text="Remove up to 3 damage from target Vessel you control.",
    cast_effect_fn=_damage_control_cast,
)


# TODO: Brace for Impact — needs a damage-prevention shield primitive
# that sits at PREVENT priority and absorbs up to N damage on a target
# Vessel until end of turn. The ``interceptor_helpers`` module doesn't
# yet expose a ``make_prevention_shield`` (the existing ``make_ward``
# only counters spells, doesn't absorb damage). Below is the intended
# shape: a closure that decrements a per-Vessel "shield" counter on each
# DAMAGE event and PREVENTs the damage when shield > 0. Engine wiring
# is incomplete because (a) cast_effect_fn doesn't currently install
# transient interceptors on the controller's behalf, and (b) the
# ``end_of_turn`` duration cleanup hook doesn't track shield interceptors
# generated by spells. Leaving the cast_effect_fn as a marker that emits
# a no-op so the card still resolves and goes to the graveyard.
def _brace_for_impact_cast(obj: GameObject, state: GameState) -> list[Event]:
    # TODO: install a PREVENT-priority interceptor on DAMAGE for the
    # chosen target, with a 4-damage shield counter that decrements per
    # absorbed point and expires at end of turn.
    return []


BRACE_FOR_IMPACT = make_action(
    name="Brace for Impact",
    cost="{1T,1S}",
    text="Prevent the next 4 damage to target Vessel you control EOT.",
    cast_effect_fn=_brace_for_impact_cast,
)


def _sonar_sweep_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Detect each opposing Vessel at SURFACE/PERISCOPE."""
    events: list[Event] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return events
    for oid in battlefield.objects:
        target = state.objects.get(oid)
        if not target or target.controller == obj.controller:
            continue
        if not is_vessel(target):
            continue
        band = target.state.depth_band
        if band not in (DepthBand.SURFACE, DepthBand.PERISCOPE):
            continue
        if target.state.detected:
            continue
        # Direct flip + DEPTHS_DETECT marker so triggers fire.
        target.state.detected = True
        if not getattr(target.state, "detected_until", None):
            target.state.detected_until = "end_of_turn"
        events.append(Event(
            type=EventType.DEPTHS_DETECT,
            payload={
                "object_id": target.id,
                "controller": obj.controller,
                "source": "sonar_sweep",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


SONAR_SWEEP = make_action(
    name="Sonar Sweep",
    cost="{2S}",
    text="Detect each opposing Vessel at SURFACE/PERISCOPE.",
    cast_effect_fn=_sonar_sweep_cast,
)


def _torpedo_spread_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 2 damage to up to 2 target Vessels.

    No targeting prompt — pick up to 2 highest-toughness opposing
    Vessels as a sensible default for the AI.
    """
    candidates: list[GameObject] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    for oid in battlefield.objects:
        target = state.objects.get(oid)
        if not target or target.controller == obj.controller:
            continue
        if not is_vessel(target):
            continue
        candidates.append(target)
    candidates.sort(key=lambda v: -(v.characteristics.toughness or 0))
    events: list[Event] = []
    for target in candidates[:2]:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                "target": target.id,
                "amount": 2,
                "source": obj.id,
                "is_combat": False,
                "reason": "torpedo_spread",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


TORPEDO_SPREAD = make_action(
    name="Torpedo Spread",
    cost="{2T}",
    text="Deal 2 damage to up to 2 target Vessels.",
    cast_effect_fn=_torpedo_spread_cast,
)


def _deep_charge_cast(obj: GameObject, state: GameState) -> list[Event]:
    """Deal 4 damage to target Vessel at MID, DEEP, or CRUSH.

    Picks the opposing Vessel deepest on the ladder (legal target
    range MID..CRUSH) as a default.
    """
    deep_bands = {DepthBand.MID, DepthBand.DEEP, DepthBand.CRUSH}
    candidates: list[GameObject] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    for oid in battlefield.objects:
        target = state.objects.get(oid)
        if not target or target.controller == obj.controller:
            continue
        if not is_vessel(target):
            continue
        if target.state.depth_band not in deep_bands:
            continue
        candidates.append(target)
    if not candidates:
        return []
    candidates.sort(key=lambda v: -(int(v.state.depth_band.value)))
    pick = candidates[0]
    return [Event(
        type=EventType.DAMAGE,
        payload={
            "target": pick.id,
            "amount": 4,
            "source": obj.id,
            "is_combat": False,
            "reason": "deep_charge",
        },
        source=obj.id,
        controller=obj.controller,
    )]


DEEP_CHARGE = make_action(
    name="Deep Charge",
    cost="{2T,1S}",
    text="Deal 4 damage to target Vessel at MID, DEEP, or CRUSH.",
    cast_effect_fn=_deep_charge_cast,
)


# =============================================================================
# Aggregate
# =============================================================================

NEUTRAL_CARDS: dict[str, CardDefinition] = {
    card.name: card
    for card in [
        # Vanilla Vessels
        DIESEL_ELECTRIC_SUB,
        COASTAL_PATROL_BOAT,
        STEAM_PINNACE,
        # Destroyers w/ reach
        LIGHT_CRUISER,
        COASTGUARD_CUTTER,
        # Vanilla Crew (stat boosts)
        RESERVE_ENGINEER,
        REAR_TUBE_LOADER,
        STOKER_MATE,
        # Crew w/ keyword grant
        SONAR_TECH,
        # Crew w/ custom interceptors
        PERISCOPE_WATCH,
        COMPASS_OFFICER,
        HELM_OFFICER,
        # Weapons
        HULL_PLATE,
        SPARE_TORPEDO,
        # Mines
        SONAR_BUOY,
        MAGNETIC_MINE,
        ACOUSTIC_TRIP,
        PRESSURE_MINE,
        # Doctrines
        CAPTAINS_BELL,
        BRIDGE_LOGBOOK,
        # Actions
        DECOY_BUOY,
        DIVE_ORDER,
        SURFACE_ORDER,
        RESUPPLY_RUN,
        CHART_PLOT,
        DAMAGE_CONTROL,
        BRACE_FOR_IMPACT,
        SONAR_SWEEP,
        TORPEDO_SPREAD,
        DEEP_CHARGE,
    ]
}


__all__ = ["NEUTRAL_CARDS"]
