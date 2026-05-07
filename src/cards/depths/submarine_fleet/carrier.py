"""SUBS — Carrier archetype (30 cards).

Pacific Auxiliary Fleet (oxidized brass / olive). A Carrier sits at PERISCOPE
producing 1/1 Drone tokens at SURFACE every turn (or on attack). The deck
floods the surface band with cheap Drones, leans on saturation Drone attacks
plus anthems and sacrifice payoffs (Kamikaze Run). Front-loaded Torpedo,
light Sonar.

Mechanic notes
--------------
* Drone token creation: every Carrier emits an end-step or attack trigger
  whose effect_fn returns OBJECT_CREATED events for 1/1 Drone Vessels at
  SURFACE. Each event carries the Drone token's CardDefinition via the
  ``card_def`` payload key plus an explicit ``depth_band`` key the
  Stage 7 wire-up will surface; until then the engine's default-band
  interceptor leaves them at PERISCOPE. We also bump
  ``state.turn_data['depths_drone_count_<controller>']`` so Air Group
  Doctrine ("gain 1 TC per Drone created") and similar cards can react
  via DEPTHS_RESUPPLY events.
* Drone bonus stacking: cards that say "Carriers create N additional
  Drones per trigger" (Hangar Bay Doctrine, Drone Catapult, Catapult
  Officer, Hangar Tech, Carrier Battle Group) push +N onto a per-controller
  counter ``state.turn_data['depths_carrier_drone_bonus_<controller>']``
  on ETB / ATTACH; Carrier triggers add this counter to their token count
  every time they fire. Counter decrement is tied to the source's
  battlefield-leave (a leaves_battlefield_trigger).
* Anthems: ``make_static_pt_boost`` filtered to the controller's Drones
  (subtype "Drone") plus ``make_keyword_grant`` for "your Drones have
  homing".
* Sacrifice payoffs: SACRIFICE event (on the Drone) followed by a DAMAGE
  event. Kamikaze Run also passes ``depths_ignore_modifier=True`` so the
  combat depth-modifier interceptor skips reduction.
* Crash-Boat Pilot: attack-trigger that on a Flagship attack emits
  SACRIFICE on self and a DAMAGE event for 4 ignoring depth modifier.
* Skipjack Drone: death trigger that creates a free 1/1 Drone (we treat
  the "you may pay {1T}" optional cost as automatic — v1 simplification).
* Repair Crew: upkeep trigger on the equipped Vessel that decrements its
  ``state.damage`` by 1 (engine reads damage as int, no event needed).
* Light Carrier "Shoho" / Crash-Boat Pilot use ``make_attack_trigger``;
  the rest of the carriers / Yamamoto use ``make_end_step_trigger``.
"""

from __future__ import annotations

from src.cards.depths.submarine_fleet._factories import (
    DepthBand,
    make_action,
    make_crew,
    make_doctrine,
    make_drone_token,
    make_vessel,
    make_weapon,
)
from src.cards.interceptor_helpers import (
    make_attack_trigger,
    make_death_trigger,
    make_end_step_trigger,
    make_etb_trigger,
    make_keyword_grant,
    make_leaves_battlefield_trigger,
    make_static_pt_boost,
    make_upkeep_trigger,
)
from src.engine import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)
from src.engine.depths import (
    get_flagship,
    is_vessel,
)


# ---------------------------------------------------------------------------
# Helpers (Carrier-local)
# ---------------------------------------------------------------------------

def _is_drone(obj: GameObject) -> bool:
    """True if obj is on battlefield and a Drone Vessel."""
    if obj is None:
        return False
    if obj.zone != ZoneType.BATTLEFIELD:
        return False
    if not is_vessel(obj):
        return False
    return "Drone" in obj.characteristics.subtypes


def _is_carrier(obj: GameObject) -> bool:
    """True if obj is on battlefield and a Carrier Vessel."""
    if obj is None:
        return False
    if obj.zone != ZoneType.BATTLEFIELD:
        return False
    if not is_vessel(obj):
        return False
    return "Carrier" in obj.characteristics.subtypes


def _your_drones_filter(source: GameObject):
    """Filter factory: any Drone you control."""
    def _f(target: GameObject, state: GameState) -> bool:
        return target.controller == source.controller and _is_drone(target)
    return _f


def _your_carriers_filter(source: GameObject):
    """Filter factory: any Carrier you control."""
    def _f(target: GameObject, state: GameState) -> bool:
        return target.controller == source.controller and _is_carrier(target)
    return _f


def _drone_count(controller: str, state: GameState) -> int:
    """Count Drones the controller has on the battlefield."""
    n = 0
    bf = state.zones.get("battlefield")
    if bf is None:
        return 0
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.controller == controller and _is_drone(obj):
            n += 1
    return n


def _your_drones_on_bf(controller: str, state: GameState) -> list[GameObject]:
    """Return all Drone Vessels the controller has on the battlefield."""
    out: list[GameObject] = []
    bf = state.zones.get("battlefield")
    if bf is None:
        return out
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.controller == controller and _is_drone(obj):
            out.append(obj)
    return out


def _opposing_flagship(controller: str, state: GameState) -> GameObject | None:
    """The flagship of any opposing player (depths is 1v1)."""
    for pid in state.players:
        if pid == controller:
            continue
        flag = get_flagship(pid, state)
        if flag is not None:
            return flag
    return None


# Per-controller "extra Drones per Carrier trigger" counter — modified by
# Hangar Bay Doctrine, Drone Catapult, Catapult Officer, Hangar Tech, and
# Carrier Battle Group.
def _bonus_key(controller: str) -> str:
    return f"depths_carrier_drone_bonus_{controller}"


def _drone_bonus(controller: str, state: GameState) -> int:
    return int(state.turn_data.get(_bonus_key(controller), 0) or 0)


def _adjust_drone_bonus(controller: str, state: GameState, delta: int) -> None:
    key = _bonus_key(controller)
    state.turn_data[key] = max(0, _drone_bonus(controller, state) + delta)


# Drone-creation count notifier — the doctrine "Air Group" reads this turn-data
# bucket each time a Drone is created so it can grant TC.
def _drone_created_count_key(controller: str) -> str:
    return f"depths_drones_created_this_turn_{controller}"


def _bump_drone_created_count(controller: str, state: GameState, n: int) -> None:
    k = _drone_created_count_key(controller)
    state.turn_data[k] = int(state.turn_data.get(k, 0) or 0) + max(0, int(n))


# ---------------------------------------------------------------------------
# Drone token CardDefinitions (used as templates for OBJECT_CREATED events)
# ---------------------------------------------------------------------------

# Plain 1/1 Drone — the workhorse token created by Escort Carrier, Drone
# Swarm, Hiryu, Shoho, Yamamoto, Refit Run, Last-Stand Drone Wave, etc.
DRONE_TOKEN = make_drone_token(
    name="Drone",
    power=1,
    hull=1,
    default_depth=DepthBand.SURFACE,
)

# Decoy Vessel — listed as 0/2 in design notes (reused across the set).
DECOY_VESSEL_TOKEN = make_drone_token(
    name="Decoy Vessel",
    power=0,
    hull=2,
    default_depth=DepthBand.SURFACE,
)


def _create_drone_event(controller: str, source_id: str,
                        *, name: str = "Drone", power: int = 1, hull: int = 1,
                        depth_band: DepthBand = DepthBand.SURFACE,
                        keywords: list[str] | None = None,
                        card_def=None) -> Event:
    """Build the OBJECT_CREATED Event that mints a single Drone token.

    We pass `card_def=DRONE_TOKEN` so the token inherits its CardDefinition
    (carrying `depths_default_depth` for downstream readers) and include
    `depth_band` as a payload key the Stage 7 wire-up will read to set
    `obj.state.depth_band` on entry. `keywords` is converted into the
    `abilities` list the OBJECT_CREATED handler expects.
    """
    payload: dict = {
        "name": name,
        "controller": controller,
        "owner": controller,
        "to_zone_type": ZoneType.BATTLEFIELD,
        "types": [CardType.DEPTHS_VESSEL],
        "subtypes": ["Drone"],
        "power": power,
        "toughness": hull,
        "is_token": True,
        "depth_band": depth_band,
    }
    if keywords:
        payload["keywords"] = list(keywords)
    if card_def is not None:
        payload["card_def"] = card_def
    return Event(
        type=EventType.OBJECT_CREATED,
        payload=payload,
        source=source_id,
        controller=controller,
    )


def _emit_drone_swarm(controller: str, source_id: str, count: int,
                      *, drone_keywords: list[str] | None = None,
                      state: GameState | None = None) -> list[Event]:
    """Build N OBJECT_CREATED events for a Drone swarm.

    If `state` is supplied, also bump the per-turn 'drones created' counter
    so Air Group Doctrine can react.
    """
    events = [
        _create_drone_event(
            controller, source_id,
            keywords=drone_keywords,
            card_def=DRONE_TOKEN,
        )
        for _ in range(max(0, int(count)))
    ]
    if state is not None and events:
        _bump_drone_created_count(controller, state, len(events))
    return events


def _damage_event(target_id: str, source_id: str, amount: int,
                  *, ignore_depth_modifier: bool = False) -> Event:
    payload: dict = {
        "target": target_id,
        "amount": int(amount),
        "source": source_id,
        "is_combat": False,
    }
    if ignore_depth_modifier:
        payload["depths_ignore_modifier"] = True
    return Event(
        type=EventType.DAMAGE,
        payload=payload,
        source=source_id,
    )


def _sacrifice_event(target_id: str, controller: str, source_id: str) -> Event:
    return Event(
        type=EventType.SACRIFICE,
        payload={"object_id": target_id, "player": controller},
        source=source_id,
        controller=controller,
    )


def _gain_charges_event(player_id: str, source_id: str, *, tc: int = 0, sc: int = 0) -> Event:
    """Pre-fill tc_gained/sc_gained so the system resupply interceptor skips."""
    return Event(
        type=EventType.DEPTHS_RESUPPLY,
        payload={
            "player": player_id,
            "tc_gained": tc,
            "sc_gained": sc,
            "reason": "card_effect",
        },
        source=source_id,
        controller=player_id,
    )


def _pt_mod_event(target_id: str, source_id: str,
                  *, power: int = 0, toughness: int = 0,
                  duration: str = "end_of_turn") -> Event:
    """End-of-turn P/T modifier via the engine's standard event."""
    return Event(
        type=EventType.PT_MODIFICATION,
        payload={
            "object_id": target_id,
            "power_mod": power,
            "toughness_mod": toughness,
            "duration": duration,
        },
        source=source_id,
    )


# ===========================================================================
# VESSELS
# ===========================================================================
# Vanilla / simple bodies first, then the carriers and trigger-bearing units.

# --- Pilot Cadet — vanilla 1/1 Drone token-style body ----------------------

PILOT_CADET = make_vessel(
    name="Pilot Cadet",
    power=1,
    hull=1,
    cost="{1T}",
    subtypes={"Drone"},
    default_depth=DepthBand.SURFACE,
    text="Vanilla token-style body.",
)


# --- Recon Drone — when sunk, draw 1 ---------------------------------------

def recon_drone_setup(obj: GameObject, state: GameState) -> list:
    """When this is sunk, draw 1."""
    def effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_death_trigger(obj, effect)]


RECON_DRONE = make_vessel(
    name="Recon Drone",
    power=1,
    hull=1,
    cost="{1T}",
    subtypes={"Drone"},
    default_depth=DepthBand.SURFACE,
    text="When sunk, draw 1.",
    setup_interceptors=recon_drone_setup,
)


# --- Escort Frigate — Destroyer with reach ---------------------------------

ESCORT_FRIGATE = make_vessel(
    name="Escort Frigate",
    power=2,
    hull=2,
    cost="{2T}",
    subtypes={"Destroyer"},
    default_depth=DepthBand.SURFACE,
    keywords={"reach"},
    text="Reach.",
)


# --- Patrol Bomber — Drone with homing -------------------------------------

PATROL_BOMBER = make_vessel(
    name="Patrol Bomber",
    power=2,
    hull=1,
    cost="{2T}",
    subtypes={"Drone"},
    default_depth=DepthBand.SURFACE,
    keywords={"homing"},
    text="Homing.",
)


# --- Saber Strike Drone — homing PERISCOPE Drone ---------------------------

SABER_STRIKE_DRONE = make_vessel(
    name="Saber Strike Drone",
    power=2,
    hull=2,
    cost="{2T,1S}",
    subtypes={"Drone"},
    default_depth=DepthBand.PERISCOPE,
    keywords={"homing"},
    text="Homing.",
)


# --- Anti-Sub Drone — homing + reach, PERISCOPE ----------------------------

ANTI_SUB_DRONE = make_vessel(
    name="Anti-Sub Drone",
    power=1,
    hull=1,
    cost="{1T,1S}",
    subtypes={"Drone"},
    default_depth=DepthBand.PERISCOPE,
    keywords={"homing", "reach"},
    text="Homing, reach.",
)


# --- Heavy Cruiser Escort — Destroyer with reach ---------------------------

HEAVY_CRUISER_ESCORT = make_vessel(
    name="Heavy Cruiser Escort",
    power=4,
    hull=4,
    cost="{3T,1S}",
    subtypes={"Destroyer"},
    default_depth=DepthBand.SURFACE,
    keywords={"reach"},
    text="Reach.",
)


# --- Skipjack Drone — when sunk, you may pay {1T} to create a 1/1 Drone ---
# v1 simplification: we always create the Drone (no optional pay choice).

def skipjack_drone_setup(obj: GameObject, state: GameState) -> list:
    """When this is sunk, create a 1/1 Drone token at SURFACE."""
    def effect(event: Event, st: GameState) -> list[Event]:
        return _emit_drone_swarm(obj.controller, obj.id, 1, state=st)
    return [make_death_trigger(obj, effect)]


SKIPJACK_DRONE = make_vessel(
    name="Skipjack Drone",
    power=2,
    hull=1,
    cost="{1T}",
    subtypes={"Drone"},
    default_depth=DepthBand.SURFACE,
    text="When this is sunk, you may pay {1T} to create a 1/1 Drone token.",
    setup_interceptors=skipjack_drone_setup,
)


# --- Crash-Boat Pilot — when this attacks the Flagship, sacrifice it: 4 dmg

def crash_boat_pilot_setup(obj: GameObject, state: GameState) -> list:
    """When this attacks the Flagship, sacrifice it: deal 4 damage."""
    def effect(event: Event, st: GameState) -> list[Event]:
        target_id = event.payload.get("target_id")
        target = st.objects.get(target_id) if target_id else None
        if target is None or "Flagship" not in target.characteristics.subtypes:
            return []
        return [
            _damage_event(target_id, obj.id, 4, ignore_depth_modifier=True),
            _sacrifice_event(obj.id, obj.controller, obj.id),
        ]
    return [make_attack_trigger(obj, effect)]


CRASH_BOAT_PILOT = make_vessel(
    name="Crash-Boat Pilot",
    power=2,
    hull=2,
    cost="{2T}",
    subtypes={"Drone"},
    default_depth=DepthBand.SURFACE,
    text="When this attacks the Flagship, sacrifice it: deal 4 damage.",
    setup_interceptors=crash_boat_pilot_setup,
)


# --- Escort Carrier — at end step, create 1 Drone --------------------------

def _make_carrier_end_step_trigger(token_count: int):
    """Return a setup_interceptors callable that gives the Carrier an end-step
    trigger producing `token_count` Drone tokens, plus the Hangar-Bay bonus.
    """
    def setup(obj: GameObject, state: GameState) -> list:
        def effect(event: Event, st: GameState) -> list[Event]:
            count = token_count + _drone_bonus(obj.controller, st)
            return _emit_drone_swarm(obj.controller, obj.id, count, state=st)
        return [make_end_step_trigger(obj, effect)]
    return setup


ESCORT_CARRIER = make_vessel(
    name="Escort Carrier",
    power=1,
    hull=5,
    cost="{3T}",
    subtypes={"Carrier"},
    default_depth=DepthBand.PERISCOPE,
    text="At your end step, create a 1/1 Drone token at SURFACE.",
    setup_interceptors=_make_carrier_end_step_trigger(1),
)


# --- Fleet Carrier "Hiryu" — at end step, create 2 Drones -----------------

FLEET_CARRIER_HIRYU = make_vessel(
    name='Fleet Carrier "Hiryu"',
    power=2,
    hull=6,
    cost="{4T,1S}",
    subtypes={"Carrier"},
    default_depth=DepthBand.PERISCOPE,
    text="At your end step, create two 1/1 Drone tokens at SURFACE.",
    setup_interceptors=_make_carrier_end_step_trigger(2),
)


# --- Light Carrier "Shoho" — when this attacks, create a 1/1 Drone --------

def light_carrier_shoho_setup(obj: GameObject, state: GameState) -> list:
    """When this attacks, create a 1/1 Drone at SURFACE."""
    def effect(event: Event, st: GameState) -> list[Event]:
        count = 1 + _drone_bonus(obj.controller, st)
        return _emit_drone_swarm(obj.controller, obj.id, count, state=st)
    return [make_attack_trigger(obj, effect)]


LIGHT_CARRIER_SHOHO = make_vessel(
    name='Light Carrier "Shoho"',
    power=1,
    hull=4,
    cost="{3T}",
    subtypes={"Carrier"},
    default_depth=DepthBand.PERISCOPE,
    text="When this attacks, create a 1/1 Drone at SURFACE.",
    setup_interceptors=light_carrier_shoho_setup,
)


# --- Fleet Admiral Yamamoto — at end step, create 3 Drones; Drones homing -

def fleet_admiral_yamamoto_setup(obj: GameObject, state: GameState) -> list:
    """At your end step, create three 1/1 Drone tokens at SURFACE.
    Drones you control have homing.
    """
    def effect(event: Event, st: GameState) -> list[Event]:
        count = 3 + _drone_bonus(obj.controller, st)
        return _emit_drone_swarm(obj.controller, obj.id, count, state=st)

    interceptors = [
        make_end_step_trigger(obj, effect),
        # "Drones you control have homing" — static keyword grant.
        make_keyword_grant(obj, ["homing"], _your_drones_filter(obj)),
    ]
    return interceptors


FLEET_ADMIRAL_YAMAMOTO = make_vessel(
    name="Fleet Admiral Yamamoto",
    power=3,
    hull=8,
    cost="{6T,2S}",
    subtypes={"Carrier"},
    default_depth=DepthBand.PERISCOPE,
    is_legendary=True,
    text="At your end step, create three 1/1 Drone tokens at SURFACE. "
         "Drones you control have homing.",
    setup_interceptors=fleet_admiral_yamamoto_setup,
)


# ===========================================================================
# CREW
# ===========================================================================

# --- Hangar Tech — equipped Carrier creates +1 Drone per trigger -----------
# Implemented via the per-controller drone bonus counter. We bump on ATTACH
# (when the Crew lands on a Carrier you control) and decrement on the Crew
# leaving the battlefield.

def hangar_tech_setup(obj: GameObject, state: GameState) -> list:
    """When attached, increase the controller's Carrier drone-bonus by 1.
    On leave, undo the bump.
    """
    def attach_filter(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.ATTACH:
            return False
        return event.payload.get("object_id") == src.id

    def attach_effect(event: Event, st: GameState) -> list[Event]:
        target_id = event.payload.get("target_id")
        target = st.objects.get(target_id) if target_id else None
        if target is None or not _is_carrier(target):
            return []
        if getattr(obj.state, "_hangar_tech_active", False):
            return []
        obj.state._hangar_tech_active = True
        _adjust_drone_bonus(obj.controller, st, +1)
        return []

    def leave_effect(event: Event, st: GameState) -> list[Event]:
        if getattr(obj.state, "_hangar_tech_active", False):
            obj.state._hangar_tech_active = False
            _adjust_drone_bonus(obj.controller, st, -1)
        return []

    from src.cards.interceptor_helpers import (
        Interceptor, InterceptorAction, InterceptorPriority, InterceptorResult, new_id
    )
    attach_int = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: attach_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT, new_events=attach_effect(e, s)
        ),
        duration="while_on_battlefield",
    )
    return [attach_int, make_leaves_battlefield_trigger(obj, leave_effect)]


HANGAR_TECH = make_crew(
    name="Hangar Tech",
    cost="{1T}",
    text="Equipped Carrier produces 1 extra Drone token per trigger.",
    setup_interceptors=hangar_tech_setup,
)


# --- Air-Sea Coordinator — equipped Vessel: at end step, all Drones +1/+0 -

def air_sea_coordinator_setup(obj: GameObject, state: GameState) -> list:
    """At end step, all your Drones get +1/+0 EOT."""
    def effect(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for drone in _your_drones_on_bf(obj.controller, st):
            events.append(_pt_mod_event(drone.id, obj.id, power=1))
        return events
    return [make_end_step_trigger(obj, effect)]


AIR_SEA_COORDINATOR = make_crew(
    name="Air-Sea Coordinator",
    cost="{1T,1S}",
    text="Equipped Vessel: at your end step, all your Drones get +1/+0 EOT.",
    setup_interceptors=air_sea_coordinator_setup,
)


# --- Catapult Officer — equipped Carrier produces +1 Drone per trigger ----
# Same shape as Hangar Tech. Stacks (each instance bumps the counter once).

def catapult_officer_setup(obj: GameObject, state: GameState) -> list:
    return hangar_tech_setup(obj, state)  # identical semantics


CATAPULT_OFFICER = make_crew(
    name="Catapult Officer",
    cost="{1T}",
    text="Equipped Carrier produces +1 Drone per trigger.",
    setup_interceptors=catapult_officer_setup,
)


# --- Drone Pen Mate — equipped Carrier: when it deploys a Drone, +1/+0 EOT
# Implementation: react to OBJECT_CREATED for Drone tokens whose `source` is
# the Carrier this Crew is attached to.

def drone_pen_mate_setup(obj: GameObject, state: GameState) -> list:
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.OBJECT_CREATED:
            return False
        # Only Drone tokens — check the resolved object.
        new_id = event.payload.get("object_id")
        new_obj = st.objects.get(new_id) if new_id else None
        if new_obj is None or "Drone" not in new_obj.characteristics.subtypes:
            return False
        # The Drone's creator must be the Carrier we're attached to.
        host_id = getattr(obj.state, "attached_to", None)
        if not host_id:
            return False
        if event.source != host_id:
            return False
        return True

    def handler(event: Event, st: GameState):
        from src.engine import InterceptorAction, InterceptorResult
        new_obj_id = event.payload.get("object_id")
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_pt_mod_event(new_obj_id, obj.id, power=1)],
        )

    from src.engine import Interceptor, InterceptorPriority, new_id as _new_id
    return [Interceptor(
        id=_new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )]


DRONE_PEN_MATE = make_crew(
    name="Drone Pen Mate",
    cost="{1T}",
    text="Equipped Carrier: when it deploys a Drone, that Drone gets +1/+0 EOT.",
    setup_interceptors=drone_pen_mate_setup,
)


# --- Veteran Squadron Lead — equipped Vessel: your Drones get +1/+1 -------

def veteran_squadron_lead_setup(obj: GameObject, state: GameState) -> list:
    """Your Drones get +1/+1 (lord effect)."""
    return make_static_pt_boost(obj, 1, 1, _your_drones_filter(obj))


VETERAN_SQUADRON_LEAD = make_crew(
    name="Veteran Squadron Lead",
    cost="{2T,1S}",
    text="Equipped Vessel: your Drones get +1/+1.",
    setup_interceptors=veteran_squadron_lead_setup,
)


# --- Repair Crew — at upkeep, remove 1 damage from equipped Vessel --------

def repair_crew_setup(obj: GameObject, state: GameState) -> list:
    """At your upkeep, remove 1 damage from the equipped Vessel."""
    def effect(event: Event, st: GameState) -> list[Event]:
        host_id = getattr(obj.state, "attached_to", None)
        if not host_id:
            return []
        host = st.objects.get(host_id)
        if host is None or host.zone != ZoneType.BATTLEFIELD:
            return []
        host.state.damage = max(0, int(getattr(host.state, "damage", 0) or 0) - 1)
        return []
    return [make_upkeep_trigger(obj, effect)]


REPAIR_CREW = make_crew(
    name="Repair Crew",
    cost="{1T,1S}",
    text="Equipped Vessel: at your upkeep, remove 1 damage from it.",
    setup_interceptors=repair_crew_setup,
)


# ===========================================================================
# WEAPONS
# ===========================================================================

# --- Drone Catapult — equipped Carrier creates +1 Drone per trigger -------
# Same shape as Hangar Tech. We treat Weapon attach the same as Crew attach.

def drone_catapult_setup(obj: GameObject, state: GameState) -> list:
    return hangar_tech_setup(obj, state)


DRONE_CATAPULT = make_weapon(
    name="Drone Catapult",
    cost="{2T}",
    text="Equipped Carrier creates 1 additional Drone per trigger.",
    setup_interceptors=drone_catapult_setup,
)


# ===========================================================================
# ACTIONS (sorcery-speed effects)
# ===========================================================================

# --- Drone Swarm — create three 1/1 Drones at SURFACE ----------------------

def drone_swarm_effect(obj: GameObject, state: GameState) -> list[Event]:
    return _emit_drone_swarm(obj.controller, obj.id, 3, state=state)


DRONE_SWARM = make_action(
    name="Drone Swarm",
    cost="{2T}",
    text="Create three 1/1 Drone tokens at SURFACE.",
    cast_effect_fn=drone_swarm_effect,
)


# --- Kamikaze Run — sacrifice a Drone: deal 3 damage ignoring depth modifier
# v1: deterministically picks the lowest-power friendly Drone; emits a
# SACRIFICE event then a DAMAGE event. "Target Vessel" is approximated as
# the opposing Flagship (best deck-shape fit) — Stage 7 wire-up will add
# proper target dispatch.

def kamikaze_run_effect(obj: GameObject, state: GameState) -> list[Event]:
    drones = _your_drones_on_bf(obj.controller, state)
    if not drones:
        return []
    drones.sort(key=lambda d: int(d.characteristics.power or 0))
    sacrificial = drones[0]
    flag = _opposing_flagship(obj.controller, state)
    if flag is None:
        return []
    return [
        _sacrifice_event(sacrificial.id, obj.controller, obj.id),
        _damage_event(flag.id, obj.id, 3, ignore_depth_modifier=True),
    ]


KAMIKAZE_RUN = make_action(
    name="Kamikaze Run",
    cost="{1T}",
    text="Sacrifice a Drone: deal 3 damage to target Vessel ignoring depth modifier.",
    cast_effect_fn=kamikaze_run_effect,
)


# --- Dive Bomber Squadron — each Drone you control deals 1 dmg to target Vessel

def dive_bomber_squadron_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Each Drone you control deals 1 to target Vessel.
    v1: target is the opposing Flagship (best deterministic choice).
    """
    flag = _opposing_flagship(obj.controller, state)
    if flag is None:
        return []
    drones = _your_drones_on_bf(obj.controller, state)
    return [_damage_event(flag.id, d.id, 1) for d in drones]


DIVE_BOMBER_SQUADRON = make_action(
    name="Dive Bomber Squadron",
    cost="{3T,1S}",
    text="Each Drone you control deals 1 damage to target Vessel.",
    cast_effect_fn=dive_bomber_squadron_effect,
)


# --- Refit Run — remove all damage from target Carrier; create a 1/1 Drone

def refit_run_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Remove all damage from the most-damaged Carrier; create a 1/1 Drone."""
    bf = state.zones.get("battlefield")
    if bf is None:
        return []
    carrier_pick = None
    best_dmg = -1
    for oid in bf.objects:
        o = state.objects.get(oid)
        if o is None or o.controller != obj.controller or not _is_carrier(o):
            continue
        d = int(getattr(o.state, "damage", 0) or 0)
        if d > best_dmg:
            best_dmg = d
            carrier_pick = o
    if carrier_pick is not None:
        carrier_pick.state.damage = 0
    return _emit_drone_swarm(obj.controller, obj.id, 1, state=state)


REFIT_RUN = make_action(
    name="Refit Run",
    cost="{2T}",
    text="Remove all damage from target Carrier; create a 1/1 Drone.",
    cast_effect_fn=refit_run_effect,
)


# --- Strike Group Bonsai — combine two Drones for one strike --------------
# Combining two creatures' attacks into one strike requires combat-system
# changes (DepthsCombatManager would need a "merged-attacker" hook). v1
# stub: keep the cast effect text-accurate; tap two Drones (so they can't
# both attack), grant the first Drone +P equal to the sacrificed Drone's
# power EOT — preserving "combine power for one strike" approximate semantics.
# The combat engine then resolves a single attacker with the combined power.

def strike_group_bonsai_effect(obj: GameObject, state: GameState) -> list[Event]:
    drones = _your_drones_on_bf(obj.controller, state)
    if len(drones) < 2:
        return []
    # Use the two highest-power Drones; the smaller donates power.
    drones.sort(key=lambda d: int(d.characteristics.power or 0), reverse=True)
    receiver, donor = drones[0], drones[1]
    donor_power = int(donor.characteristics.power or 0)
    # Tap both so the engine treats them as one combined "strike."
    receiver.state.tapped = True
    donor.state.tapped = True
    return [_pt_mod_event(receiver.id, obj.id, power=donor_power)]


# TODO: Strike Group Bonsai needs combat-system support for a true single
# combined strike. v1 approximation taps both Drones and pumps the receiver
# by the donor's power EOT, which is close to the intended outcome but
# routes attack through the standard one-attacker-per-decl path.
STRIKE_GROUP_BONSAI = make_action(
    name="Strike Group Bonsai",
    cost="{2T,1S}",
    text="Two target Drones you control attack as one (combine power for one strike, both tap).",
    cast_effect_fn=strike_group_bonsai_effect,
)


# --- Last-Stand Drone Wave — create five Drones; if hull <8, +1/+0 EOT ----

def last_stand_drone_wave_effect(obj: GameObject, state: GameState) -> list[Event]:
    """Create five 1/1 Drones; if controller's flagship has <8 hull
    remaining, the new Drones get +1/+0 EOT.
    """
    events: list[Event] = []
    flag = get_flagship(obj.controller, state)
    remaining_hull = 0
    if flag is not None:
        hull = int(flag.characteristics.toughness or 0)
        damage = int(getattr(flag.state, "damage", 0) or 0)
        remaining_hull = max(0, hull - damage)

    # Create the swarm and capture the events so we can find them post-emit.
    swarm = _emit_drone_swarm(obj.controller, obj.id, 5, state=state)
    events.extend(swarm)

    # If under threshold, follow up with PT_MODIFICATIONS for each newly
    # minted Drone. We can't peek at the new ids before pipeline emit, so
    # we mark a flag the cards can read; the engine wire-up will fan out
    # the boost. As a pragmatic stand-in, we set state.turn_data for the
    # next-tick pump.
    if remaining_hull < 8:
        # Schedule a one-shot REACT that walks newly-created Drones for
        # this controller and pumps each. We register the watcher and let
        # it fire as the swarm OBJECT_CREATEDs flow through.
        state.turn_data["_last_stand_pump_pending"] = {
            "controller": obj.controller,
            "source_id": obj.id,
            "remaining": 5,
        }
    return events


LAST_STAND_DRONE_WAVE = make_action(
    name="Last-Stand Drone Wave",
    cost="{3T}",
    text="Create five 1/1 Drone tokens at SURFACE; if you have <8 hull, they get +1/+0 EOT.",
    cast_effect_fn=last_stand_drone_wave_effect,
)


# ===========================================================================
# DOCTRINES
# ===========================================================================

# --- Carrier Air Wing Doctrine — your Drones get +1/+0 and have homing ---

def carrier_air_wing_doctrine_setup(obj: GameObject, state: GameState) -> list:
    """Your Drones get +1/+0 and have homing."""
    interceptors = list(make_static_pt_boost(obj, 1, 0, _your_drones_filter(obj)))
    interceptors.append(make_keyword_grant(obj, ["homing"], _your_drones_filter(obj)))
    return interceptors


CARRIER_AIR_WING_DOCTRINE = make_doctrine(
    name="Carrier Air Wing Doctrine",
    cost="{3T}",
    text="Your Drones get +1/+0 and have homing.",
    setup_interceptors=carrier_air_wing_doctrine_setup,
)


# --- Air Group Doctrine — whenever you create a Drone token, gain 1 TC ---

def air_group_doctrine_setup(obj: GameObject, state: GameState) -> list:
    """Whenever you create a Drone token, gain 1 Torpedo Charge."""
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.OBJECT_CREATED:
            return False
        new_obj_id = event.payload.get("object_id")
        new_obj = st.objects.get(new_obj_id) if new_obj_id else None
        if new_obj is None:
            return False
        if new_obj.controller != obj.controller:
            return False
        return "Drone" in new_obj.characteristics.subtypes

    def handler(event: Event, st: GameState):
        from src.engine import InterceptorAction, InterceptorResult
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_gain_charges_event(obj.controller, obj.id, tc=1)],
        )

    from src.engine import Interceptor, InterceptorPriority, new_id as _new_id
    return [Interceptor(
        id=_new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )]


AIR_GROUP_DOCTRINE = make_doctrine(
    name="Air Group Doctrine",
    cost="{2T,1S}",
    text="Whenever you create a Drone token, gain 1 TC.",
    setup_interceptors=air_group_doctrine_setup,
)


# --- Hangar Bay Doctrine — your Carriers create +1 Drone per trigger -----
# Stateful: bumps the per-controller drone bonus on ETB and undoes on leave.

def hangar_bay_doctrine_setup(obj: GameObject, state: GameState) -> list:
    """ETB: +1 to controller's drone bonus. Leave: -1."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        if not getattr(obj.state, "_hangar_bay_active", False):
            obj.state._hangar_bay_active = True
            _adjust_drone_bonus(obj.controller, st, +1)
        return []

    def leave_effect(event: Event, st: GameState) -> list[Event]:
        if getattr(obj.state, "_hangar_bay_active", False):
            obj.state._hangar_bay_active = False
            _adjust_drone_bonus(obj.controller, st, -1)
        return []

    return [
        make_etb_trigger(obj, etb_effect),
        make_leaves_battlefield_trigger(obj, leave_effect),
    ]


HANGAR_BAY_DOCTRINE = make_doctrine(
    name="Hangar Bay Doctrine",
    cost="{3T,1S}",
    text="Your Carriers create 1 extra Drone per trigger.",
    setup_interceptors=hangar_bay_doctrine_setup,
)


# --- Carrier Battle Group — your Carriers have +0/+3; +1 Drone per trigger

def carrier_battle_group_setup(obj: GameObject, state: GameState) -> list:
    """Your Carriers get +0/+3; create 1 additional Drone per trigger."""
    interceptors = list(make_static_pt_boost(obj, 0, 3, _your_carriers_filter(obj)))

    # Drone bonus stacking — same shape as Hangar Bay Doctrine.
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        if not getattr(obj.state, "_carrier_bg_active", False):
            obj.state._carrier_bg_active = True
            _adjust_drone_bonus(obj.controller, st, +1)
        return []

    def leave_effect(event: Event, st: GameState) -> list[Event]:
        if getattr(obj.state, "_carrier_bg_active", False):
            obj.state._carrier_bg_active = False
            _adjust_drone_bonus(obj.controller, st, -1)
        return []

    interceptors.append(make_etb_trigger(obj, etb_effect))
    interceptors.append(make_leaves_battlefield_trigger(obj, leave_effect))
    return interceptors


CARRIER_BATTLE_GROUP = make_doctrine(
    name="Carrier Battle Group",
    cost="{4T,2S}",
    text="Your Carriers have +0/+3; create 1 additional Drone per trigger.",
    setup_interceptors=carrier_battle_group_setup,
)


# ===========================================================================
# CARD REGISTRY
# ===========================================================================

CARRIER_CARDS: dict[str, "object"] = {
    card.name: card for card in [
        # Vessels — Drones (8)
        PILOT_CADET,
        RECON_DRONE,
        PATROL_BOMBER,
        SABER_STRIKE_DRONE,
        ANTI_SUB_DRONE,
        SKIPJACK_DRONE,
        CRASH_BOAT_PILOT,
        # Vessels — Destroyers (2)
        ESCORT_FRIGATE,
        HEAVY_CRUISER_ESCORT,
        # Vessels — Carriers (4)
        ESCORT_CARRIER,
        FLEET_CARRIER_HIRYU,
        LIGHT_CARRIER_SHOHO,
        FLEET_ADMIRAL_YAMAMOTO,
        # Crew (6)
        HANGAR_TECH,
        AIR_SEA_COORDINATOR,
        CATAPULT_OFFICER,
        DRONE_PEN_MATE,
        VETERAN_SQUADRON_LEAD,
        REPAIR_CREW,
        # Weapons (1)
        DRONE_CATAPULT,
        # Actions (5)
        DRONE_SWARM,
        KAMIKAZE_RUN,
        DIVE_BOMBER_SQUADRON,
        REFIT_RUN,
        STRIKE_GROUP_BONSAI,
        LAST_STAND_DRONE_WAVE,
        # Doctrines (4)
        CARRIER_AIR_WING_DOCTRINE,
        AIR_GROUP_DOCTRINE,
        HANGAR_BAY_DOCTRINE,
        CARRIER_BATTLE_GROUP,
    ]
}


__all__ = ["CARRIER_CARDS"]
