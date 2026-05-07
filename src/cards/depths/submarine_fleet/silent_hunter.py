"""
SUBS — Silent Hunter (Coastal Defense Force) archetype card definitions.

Theme: slow Submarines with SILENT_RUNNING sit at DEEP/MID where detection
costs 3-4 Sonar each. Crew that punish failed pings, Doctrines that turn
undetected threats into per-turn Flagship damage. Even split, slight
Sonar lean.

The 30 cards in this module match the Silent Hunter table in
``docs/sets/SUBS.md`` exactly. Every card is built from the shared
factories in ``_factories.py`` (``make_vessel``, ``make_crew``,
``make_weapon``, ``make_mine``, ``make_action``, ``make_doctrine``) so
the card-shape contract stays consistent across the parallel archetype
agents.

Engine gaps flagged with ``# TODO:`` comments inline:
    * Detection-cost-mod cards (Sonar Jammer, Thermocline Cloak's SH
      cousin, Cold-Cathode Periscope's static detect-mod variant)
      depend on a ``QUERY_DETECTION_COST`` event the engine doesn't
      yet expose. The card text stays accurate; the effect_fn stubs
      to ``[]`` until the query event ships.
    * Counter-detection (``Failed Ping``) requires a stack/dispatch
      hook that the depths engine doesn't have yet — the action
      stubs to a Sonar-drain proxy.
    * "Look at top card of opponent's library" (Hydrophone Operator)
      requires a SCRY/PEEK primitive that the depths engine doesn't
      surface — left as a stub.

These are deliberate stubs so the module imports and the cards are
visible in the deck builder. When the engine adds the missing query
events, the stubs get real bodies.
"""

from __future__ import annotations

from typing import Optional

from src.cards.interceptor_helpers import (
    make_etb_trigger,
    make_attack_trigger,
    make_static_pt_boost,
    make_dynamic_pt_boost,
    make_keyword_grant,
)
from src.engine.depths import (
    DepthBand,
    is_vessel,
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
    make_vessel,
    make_crew,
    make_weapon,
    make_mine,
    make_action,
    make_doctrine,
    make_depths_end_phase_trigger,
    make_depths_dive_phase_trigger,
)


# ---------------------------------------------------------------------------
# Internal helpers — small adapters bridging Silent Hunter cards to the
# (still-evolving) depths event surface.
# ---------------------------------------------------------------------------

def _opposing_undetected_vessels(state: GameState, controller_id: str) -> list[GameObject]:
    """Battlefield Vessels NOT controlled by ``controller_id`` and not detected
    (also excludes Flagship; the Flagship is always considered detected per
    setup)."""
    out: list[GameObject] = []
    bf = state.zones.get("battlefield")
    if not bf:
        return out
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if not obj or not is_vessel(obj):
            continue
        if obj.controller == controller_id:
            continue
        if "Flagship" in obj.characteristics.subtypes:
            continue
        if getattr(obj.state, "detected", False):
            continue
        out.append(obj)
    return out


def _undetected_vessels_you_control(state: GameState, controller_id: str) -> list[GameObject]:
    """Your battlefield Vessels with ``state.detected == False``. Excludes
    Flagship (always detected)."""
    out: list[GameObject] = []
    bf = state.zones.get("battlefield")
    if not bf:
        return out
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if not obj or not is_vessel(obj):
            continue
        if obj.controller != controller_id:
            continue
        if "Flagship" in obj.characteristics.subtypes:
            continue
        if getattr(obj.state, "detected", False):
            continue
        out.append(obj)
    return out


def _make_become_undetected_event(target_id: str, source_id: str, controller: str) -> Event:
    """Emit a marker event the deck-storage / log layer can show.

    The actual flip of ``state.detected = False`` happens inline in the
    effect handler that emits this event (engine has no
    ``DEPTHS_BECOME_UNDETECTED`` event yet — we surface the change as a
    PRIORITY_PASS marker so observers can hook it without a new enum
    member).
    """
    return Event(
        type=EventType.PRIORITY_PASS,
        payload={
            "reason": "depths_become_undetected",
            "target_id": target_id,
            "source": source_id,
            "controller": controller,
        },
        source=source_id,
        controller=controller,
    )


def _flip_undetected(state: GameState, target_id: str) -> None:
    """Mutate the target Vessel's ``state.detected`` flag to False, clearing
    any persistence marker."""
    obj = state.objects.get(target_id)
    if obj is None or not is_vessel(obj):
        return
    obj.state.detected = False
    obj.state.detected_until = None
    # Drop any duration list set up by mark_detected.
    if hasattr(obj.state, "detected_durations"):
        try:
            obj.state.detected_durations = []
        except Exception:
            pass


def _grant_charges(state: GameState, player_id: str, *, tc: int = 0, sc: int = 0) -> None:
    """Best-effort charge grant. Mutates the player object directly. Caps
    at MAX_CHARGE_CAP via the charge system if available."""
    player = state.players.get(player_id)
    if player is None:
        return
    try:
        from src.engine.depths import DepthsChargeSystem, MAX_CHARGE_CAP
        cs = DepthsChargeSystem(state)
        cs.add_charges(player_id, tc=tc, sc=sc)
    except Exception:
        # Direct fallback if the charge system can't be constructed.
        if tc:
            player.tc = min(10, getattr(player, "tc", 0) + int(tc))
        if sc:
            player.sc = min(10, getattr(player, "sc", 0) + int(sc))


def _drain_opponent_charges(state: GameState, controller_id: str, *, tc: int = 0, sc: int = 0) -> None:
    """Drain charges from the opposing player(s)."""
    for pid, player in state.players.items():
        if pid == controller_id:
            continue
        if tc:
            player.tc = max(0, getattr(player, "tc", 0) - int(tc))
        if sc:
            player.sc = max(0, getattr(player, "sc", 0) - int(sc))


# ---------------------------------------------------------------------------
# 1. Periscope Recon — vanilla SR scout
# ---------------------------------------------------------------------------

PERISCOPE_RECON = make_vessel(
    name="Periscope Recon",
    cost="{1T}",
    power=1, hull=2,
    default_depth=DepthBand.PERISCOPE,
    keywords=["silent_running"],
    text="Silent Running.",
)


# ---------------------------------------------------------------------------
# 2. Listening Post — defender wall
# ---------------------------------------------------------------------------

LISTENING_POST = make_vessel(
    name="Listening Post",
    cost="{1S}",
    power=0, hull=3,
    default_depth=DepthBand.MID,
    keywords=["defender", "silent_running"],
    text="Defender. Silent Running.",
)


# ---------------------------------------------------------------------------
# 3. Diesel Whisper — failed-ping draw engine on self
# ---------------------------------------------------------------------------

def _diesel_whisper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """REACT to DEPTHS_DETECTION_FAIL where the failed attempt targeted us."""
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DEPTHS_DETECTION_FAIL:
            return False
        return event.payload.get("attacker_id") == src_id

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": controller, "count": 1},
                source=src_id,
                controller=controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


DIESEL_WHISPER = make_vessel(
    name="Diesel Whisper",
    cost="{2T,1S}",
    power=2, hull=3,
    default_depth=DepthBand.MID,
    keywords=["silent_running"],
    setup_interceptors=_diesel_whisper_setup,
    text="Silent Running. Whenever an opposing detection attempt against this fails, draw 1.",
)


# ---------------------------------------------------------------------------
# 4. Echo Chamber Mate — equipped failed-ping draw
# ---------------------------------------------------------------------------

def _echo_chamber_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crew: grant silent_running and trigger draw on attached's failed-ping."""
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DEPTHS_DETECTION_FAIL:
            return False
        source = st.objects.get(src_id)
        if source is None:
            return False
        attached_to = source.state.attached_to
        if not attached_to:
            return False
        return event.payload.get("attacker_id") == attached_to

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": controller, "count": 1},
                source=src_id,
                controller=controller,
            )],
        )

    # Stack with the Equipment-style attach setup so we get silent_running too.
    from src.cards.interceptor_helpers import make_equipment_setup
    base_setup = make_equipment_setup(keywords=["silent_running"])
    base_interceptors = base_setup(obj, state) or []
    base_interceptors.append(Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    ))
    return base_interceptors


ECHO_CHAMBER_MATE = make_crew(
    name="Echo Chamber Mate",
    cost="{2S}",
    setup_interceptors=_echo_chamber_setup,
    text="Equipped Vessel has silent_running; whenever a detection attempt against equipped fails, draw 1.",
)


# ---------------------------------------------------------------------------
# 5. Cold Hull Engineer — +0/+1 silent-running grant
# ---------------------------------------------------------------------------

COLD_HULL_ENGINEER = make_crew(
    name="Cold Hull Engineer",
    cost="{1S}",
    toughness_mod=1,
    keywords_to_grant=["silent_running"],
    text="Equipped Vessel has silent_running and +0/+1.",
)


# ---------------------------------------------------------------------------
# 6. Stalker Sub — Crush-Dive: gain 1 Sonar
# ---------------------------------------------------------------------------

def _stalker_sub_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type not in (EventType.DEPTHS_DIVE, EventType.DEPTHS_SURFACE_VESSEL):
            return False
        return event.payload.get("object_id") == src_id

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        # Crush-dive triggers grant 1 Sonar Charge to controller.
        _grant_charges(st, controller, sc=1)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


STALKER_SUB = make_vessel(
    name="Stalker Sub",
    cost="{2T}",
    power=2, hull=2,
    default_depth=DepthBand.PERISCOPE,
    keywords=["silent_running"],
    setup_interceptors=_stalker_sub_setup,
    text="Silent Running. Crush-Dive: gain 1 Sonar.",
)


# ---------------------------------------------------------------------------
# 7. Bottom-Crawler Probe — DEEP defender-style
# ---------------------------------------------------------------------------

BOTTOM_CRAWLER_PROBE = make_vessel(
    name="Bottom-Crawler Probe",
    cost="{2S}",
    power=1, hull=4,
    default_depth=DepthBand.DEEP,
    keywords=["bottom_crawler", "silent_running"],
    text="Bottom-crawler. Silent Running.",
)


# ---------------------------------------------------------------------------
# 8. Acoustic Decoy — Mine
# ---------------------------------------------------------------------------

ACOUSTIC_DECOY = make_mine(
    name="Acoustic Decoy",
    cost="{1S}",
    damage=2,
    default_depth=DepthBand.PERISCOPE,
    detect_triggering_vessel=True,
    text="When triggered, the triggering Vessel becomes detected and takes 2.",
)


# ---------------------------------------------------------------------------
# 9. Sonar Jammer — opponent's detection costs +1 EOT
# ---------------------------------------------------------------------------

def _sonar_jammer_cast(obj: GameObject, state: GameState) -> list[Event]:
    # TODO: detection-cost mod requires QUERY_DETECTION_COST event in engine.
    #       Until then, drain 1 Sonar Charge from each opponent as a proxy
    #       so the card has *some* tempo impact.
    _drain_opponent_charges(state, obj.controller, sc=1)
    return []


SONAR_JAMMER = make_action(
    name="Sonar Jammer",
    cost="{1S}",
    text="Opponent's detection attempts cost +1 Sonar EOT.",
    cast_effect_fn=_sonar_jammer_cast,
)


# ---------------------------------------------------------------------------
# 10. Failed Ping — counter detection attempt; opp loses 2 SC
# ---------------------------------------------------------------------------

def _failed_ping_cast(obj: GameObject, state: GameState) -> list[Event]:
    # TODO: counter-detection requires the engine to surface a stackable
    #       DEPTHS_DETECT pending check. For now apply the Sonar-drain
    #       portion of the effect — the counter portion is a no-op.
    _drain_opponent_charges(state, obj.controller, sc=2)
    return []


FAILED_PING = make_action(
    name="Failed Ping",
    cost="{2S}",
    text="Counter target detection attempt; opponent loses 2 Sonar.",
    cast_effect_fn=_failed_ping_cast,
)


# ---------------------------------------------------------------------------
# 11. U-Class Stalker — vanilla SR midband body
# ---------------------------------------------------------------------------

U_CLASS_STALKER = make_vessel(
    name="U-Class Stalker",
    cost="{2T,1S}",
    power=2, hull=3,
    default_depth=DepthBand.MID,
    keywords=["silent_running"],
    text="Silent Running.",
)


# ---------------------------------------------------------------------------
# 12. Cold-Cathode Periscope — Weapon: SR static + {1S} pump
# ---------------------------------------------------------------------------

def _cold_cathode_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment: grant silent_running, register a {1S}: +1/+0 EOT activated
    ability on the host."""
    from src.cards.interceptor_helpers import make_equipment_setup, make_activated_ability

    base_setup = make_equipment_setup(keywords=["silent_running"])
    base_interceptors = base_setup(obj, state) or []

    # Register the {1S} pump on the equipped Vessel via the granted-abilities
    # listener pattern. We piggyback on the same listener by passing
    # granted_activated_abilities to a second equipment_setup pass — but
    # since the vessel is the host, the cleanest path is to wire the
    # ability inline at attach time.
    src_id = obj.id
    controller = obj.controller

    def _attach_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACH:
            return False
        return event.payload.get("object_id") == src_id

    def _attach_handler(event: Event, st: GameState) -> InterceptorResult:
        target_id = event.payload.get("target_id") or event.payload.get("target")
        target = st.objects.get(target_id) if target_id else None
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        def _pump_effect(o: GameObject, gs: GameState, targets) -> list[Event]:
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": o.id,
                    "power_mod": 1,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                },
                source=o.id,
                controller=o.controller,
            )]

        try:
            make_activated_ability(
                target,
                cost="{1S}",
                effect_fn=_pump_effect,
                description="Equipped Vessel gains +1/+0 until end of turn",
            )
        except Exception:
            pass
        return InterceptorResult(action=InterceptorAction.PASS)

    base_interceptors.append(Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_attach_filter,
        handler=_attach_handler,
        duration="while_on_battlefield",
    ))
    return base_interceptors


COLD_CATHODE_PERISCOPE = make_weapon(
    name="Cold-Cathode Periscope",
    cost="{1S}",
    setup_interceptors=_cold_cathode_setup,
    text='Equipped Vessel has silent_running. {1S}: that Vessel gains +1/+0 EOT.',
)


# ---------------------------------------------------------------------------
# 13. Iron Discipline — Doctrine: your Vessels at DEEP can't be detected
# ---------------------------------------------------------------------------

def _iron_discipline_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """PREVENT-priority interceptor: vetoes DEPTHS_DETECT against your DEEP
    vessels."""
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DEPTHS_DETECT:
            return False
        target_id = event.payload.get("attacker_id") or event.payload.get("target_id")
        if not target_id:
            return False
        target = st.objects.get(target_id)
        if target is None or not is_vessel(target):
            return False
        if target.controller != controller:
            return False
        return target.state.depth_band == DepthBand.DEEP

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.PREVENT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


IRON_DISCIPLINE = make_doctrine(
    name="Iron Discipline",
    cost="{3S}",
    text="Your Vessels at DEEP cannot be detected.",
    setup_interceptors=_iron_discipline_setup,
)


# ---------------------------------------------------------------------------
# 14. Type-XXI Phantom — premium SR+homing DEEP threat
# ---------------------------------------------------------------------------

TYPE_XXI_PHANTOM = make_vessel(
    name="Type-XXI Phantom",
    cost="{4T,2S}",
    power=5, hull=4,
    default_depth=DepthBand.DEEP,
    keywords=["silent_running", "homing"],
    text="Silent Running. Homing.",
)


# ---------------------------------------------------------------------------
# 15. Sonar Decoy Crew — failed-ping drains opp 1 SC
# ---------------------------------------------------------------------------

def _sonar_decoy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.DEPTHS_DETECTION_FAIL:
            return False
        source = st.objects.get(src_id)
        if source is None:
            return False
        attached_to = source.state.attached_to
        if not attached_to:
            return False
        return event.payload.get("attacker_id") == attached_to

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        _drain_opponent_charges(st, controller, sc=1)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


SONAR_DECOY_CREW = make_crew(
    name="Sonar Decoy Crew",
    cost="{1T,1S}",
    setup_interceptors=_sonar_decoy_setup,
    text="Equipped Vessel: when an opposing detection attempt against it fails, opponent loses 1 SC.",
)


# ---------------------------------------------------------------------------
# 16. Hydrophone Operator — peek at opponent's library
# ---------------------------------------------------------------------------

def _hydrophone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crew: at your upkeep, look at top card of opponent's library.
    TODO: PEEK_LIBRARY primitive missing — emit a marker event for now.
    """
    src_id = obj.id
    controller = obj.controller

    def _effect(event: Event, st: GameState) -> list[Event]:
        # TODO: requires a PEEK_LIBRARY primitive in the engine.
        # Surface a benign marker so logs / observers see the trigger.
        return [Event(
            type=EventType.PRIORITY_PASS,
            payload={
                "reason": "depths_peek_library",
                "source": src_id,
                "controller": controller,
            },
            source=src_id,
            controller=controller,
        )]

    return [make_depths_dive_phase_trigger(obj, _effect, controller_only=True)]


HYDROPHONE_OPERATOR = make_crew(
    name="Hydrophone Operator",
    cost="{1S}",
    setup_interceptors=_hydrophone_setup,
    text="Equipped Vessel: at your upkeep, look at top card of opponent's library.",
)


# ---------------------------------------------------------------------------
# 17. Dive Master — equipped Vessel's dives cost 0
# ---------------------------------------------------------------------------

def _dive_master_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment: tag the host Vessel so the engine's dive-cost path can
    see the discount.
    TODO: dive cost is hardcoded to {1S} in deps.dive_vessel; a
    QUERY_DIVE_COST or per-vessel discount flag is needed for this card
    to work at runtime. Stub the static effect via a state flag the
    runtime can grow into.
    """
    src_id = obj.id
    controller = obj.controller

    def _attach_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACH:
            return False
        return event.payload.get("object_id") == src_id

    def _attach_handler(event: Event, st: GameState) -> InterceptorResult:
        target_id = event.payload.get("target_id") or event.payload.get("target")
        target = st.objects.get(target_id) if target_id else None
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Set a state flag the engine can consult.
        try:
            target.state.depths_dive_cost_zero = True
        except Exception:
            pass
        return InterceptorResult(action=InterceptorAction.PASS)

    def _detach_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.UNATTACH:
            return False
        return event.payload.get("object_id") == src_id

    def _detach_handler(event: Event, st: GameState) -> InterceptorResult:
        target_id = event.payload.get("target_id") or event.payload.get("target")
        target = st.objects.get(target_id) if target_id else None
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        try:
            target.state.depths_dive_cost_zero = False
        except Exception:
            pass
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=src_id,
            controller=controller,
            priority=InterceptorPriority.REACT,
            filter=_attach_filter,
            handler=_attach_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=src_id,
            controller=controller,
            priority=InterceptorPriority.REACT,
            filter=_detach_filter,
            handler=_detach_handler,
            duration="while_on_battlefield",
        ),
    ]


DIVE_MASTER = make_crew(
    name="Dive Master",
    cost="{2S}",
    setup_interceptors=_dive_master_setup,
    text="Equipped Vessel's dives cost 0.",
)


# ---------------------------------------------------------------------------
# 18. Whisper Below — undetect + dive 1
# ---------------------------------------------------------------------------

def _whisper_below_cast(obj: GameObject, state: GameState) -> list[Event]:
    # Card targets a Vessel; in the absence of full target dispatch we read
    # ``obj.state.cast_target_ids`` if present, else target the controller's
    # first eligible Vessel (best-effort).
    target_id: Optional[str] = None
    targets = getattr(obj.state, "cast_target_ids", None) or []
    if targets:
        target_id = targets[0]
    else:
        # Pick any Vessel controller owns that isn't the Flagship.
        bf = state.zones.get("battlefield")
        if bf:
            for oid in bf.objects:
                cand = state.objects.get(oid)
                if (cand and is_vessel(cand)
                        and cand.controller == obj.controller
                        and "Flagship" not in cand.characteristics.subtypes):
                    target_id = oid
                    break

    events: list[Event] = []
    if target_id:
        target = state.objects.get(target_id)
        _flip_undetected(state, target_id)
        events.append(_make_become_undetected_event(target_id, obj.id, obj.controller))
        # Dive 1 band if not already at CRUSH and not Flagship.
        if (target is not None and is_vessel(target)
                and "Flagship" not in target.characteristics.subtypes):
            current = target.state.depth_band or DepthBand.SURFACE
            if current is not DepthBand.CRUSH:
                new_band = DepthBand(int(current.value) + 1)
                target.state.depth_band = new_band
                events.append(Event(
                    type=EventType.DEPTHS_DIVE,
                    payload={
                        "object_id": target_id,
                        "from_band": current,
                        "to_band": new_band,
                        "controller": obj.controller,
                    },
                    source=obj.id,
                    controller=obj.controller,
                ))
    return events


WHISPER_BELOW = make_action(
    name="Whisper Below",
    cost="{2S}",
    text="Target Vessel becomes undetected and dives 1 band.",
    cast_effect_fn=_whisper_below_cast,
)


# ---------------------------------------------------------------------------
# 19. Silent Service Doctrine — undetect → +1 SC trigger
# ---------------------------------------------------------------------------

def _silent_service_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Vessel you control becomes undetected, gain 1 SC.

    We watch the marker event ``PRIORITY_PASS`` with reason
    ``depths_become_undetected`` (emitted by all of our
    'become-undetected' helpers in this module), filtered to our own
    vessels. Once the engine grows a real ``DEPTHS_BECOME_UNDETECTED``
    type, swap the watcher.
    """
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PRIORITY_PASS:
            return False
        if event.payload.get("reason") != "depths_become_undetected":
            return False
        target_id = event.payload.get("target_id")
        target = st.objects.get(target_id) if target_id else None
        if target is None or not is_vessel(target):
            return False
        return target.controller == controller

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        _grant_charges(st, controller, sc=1)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


SILENT_SERVICE_DOCTRINE = make_doctrine(
    name="Silent Service Doctrine",
    cost="{2S}",
    text="Whenever a Vessel you control becomes undetected, gain 1 SC.",
    setup_interceptors=_silent_service_setup,
)


# ---------------------------------------------------------------------------
# 20. Dead-Stop Maneuver — undetect + grant SR EOT
# ---------------------------------------------------------------------------

def _dead_stop_cast(obj: GameObject, state: GameState) -> list[Event]:
    target_id: Optional[str] = None
    targets = getattr(obj.state, "cast_target_ids", None) or []
    if targets:
        target_id = targets[0]
    else:
        bf = state.zones.get("battlefield")
        if bf:
            for oid in bf.objects:
                cand = state.objects.get(oid)
                if (cand and is_vessel(cand)
                        and cand.controller == obj.controller
                        and "Flagship" not in cand.characteristics.subtypes):
                    target_id = oid
                    break

    events: list[Event] = []
    if target_id:
        _flip_undetected(state, target_id)
        events.append(_make_become_undetected_event(target_id, obj.id, obj.controller))
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                "object_id": target_id,
                "keyword": "silent_running",
                "duration": "end_of_turn",
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return events


DEAD_STOP_MANEUVER = make_action(
    name="Dead-Stop Maneuver",
    cost="{1S}",
    text="Target Vessel you control becomes undetected and gains silent_running EOT.",
    cast_effect_fn=_dead_stop_cast,
)


# ---------------------------------------------------------------------------
# 21. Snorkel Stalker — attack-while-undetected pump
# ---------------------------------------------------------------------------

def _snorkel_stalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id
    controller = obj.controller

    def _attack_filter(event: Event, st: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get("attacker_id") != source_obj.id:
            return False
        # Only fire when the source is currently undetected.
        return not getattr(source_obj.state, "detected", False)

    def _effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                "object_id": src_id,
                "power_mod": 1,
                "toughness_mod": 0,
                "duration": "end_of_turn",
            },
            source=src_id,
            controller=controller,
        )]

    return [make_attack_trigger(obj, _effect, filter_fn=_attack_filter)]


# Balance pass 2026-05-06 (rounds 2-5): Snorkel Stalker has been the runaway
# Silent_Hunter carry across every tournament round (100% winrate-in-play,
# 705 dmg / 60 casts in round 5). Iterative nerfs (trigger +2→+1, removed
# silent_running, fixed EOT pump-stacking bug) didn't tame it because it
# spawns at PERISCOPE for free, can't easily be intercepted (no Wolfpack
# vessel reaches PERISCOPE turn 1), and still does 3-4 dmg/turn unintercepted.
# Round-5 nerf: hull 2 → 1. Now any 1+ damage chip from Wolfpack sinks it.
SNORKEL_STALKER = make_vessel(
    name="Snorkel Stalker",
    cost="{2T}",
    power=3, hull=1,
    default_depth=DepthBand.PERISCOPE,
    setup_interceptors=_snorkel_stalker_setup,
    text="Whenever this attacks while undetected, +1 power EOT.",
)


# ---------------------------------------------------------------------------
# 22. Threat Board Analyst — Shadow-Count P/0 on equipped
# ---------------------------------------------------------------------------

def _threat_board_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crew: equipped gets +1/+0 per opposing undetected Vessel."""
    from src.cards.interceptor_helpers import make_attached_dynamic_pt_boost

    def _mod(source: GameObject, target: GameObject, st: GameState) -> tuple[int, int]:
        count = len(_opposing_undetected_vessels(st, source.controller))
        return (count, 0)

    return list(make_attached_dynamic_pt_boost(obj, _mod))


THREAT_BOARD_ANALYST = make_crew(
    name="Threat Board Analyst",
    cost="{1S}",
    setup_interceptors=_threat_board_setup,
    text="Equipped Vessel gets +1/+0 for each opposing undetected Vessel (Shadow-Count).",
)


# ---------------------------------------------------------------------------
# 23. Wolf at the Door — homing while undetected
# ---------------------------------------------------------------------------

def _wolf_at_the_door_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Conditional homing: grant ``homing`` while ``state.detected == False``."""
    src_id = obj.id
    controller = obj.controller

    def _affects_filter(target: GameObject, st: GameState) -> bool:
        if target.id != src_id:
            return False
        return not getattr(target.state, "detected", False)

    return [make_keyword_grant(obj, ["homing"], _affects_filter)]


WOLF_AT_THE_DOOR = make_vessel(
    name="Wolf at the Door",
    cost="{3T,1S}",
    power=3, hull=4,
    default_depth=DepthBand.DEEP,
    keywords=["silent_running"],
    setup_interceptors=_wolf_at_the_door_setup,
    text="Silent Running. While undetected, has homing.",
)


# ---------------------------------------------------------------------------
# 24. Black Sea Veteran — Crush-Dive: free detect on opposing Vessel
# ---------------------------------------------------------------------------

def _black_sea_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type not in (EventType.DEPTHS_DIVE, EventType.DEPTHS_SURFACE_VESSEL):
            return False
        return event.payload.get("object_id") == src_id

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        # Pick a target: first opposing Vessel that is undetected (not Flagship).
        candidates = [v for v in _opposing_undetected_vessels(st, controller)]
        if not candidates:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = candidates[0]
        target.state.detected = True
        target.state.detected_until = "end_of_turn"
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DEPTHS_DETECT,
                payload={
                    "defender": controller,
                    "attacker_id": target.id,
                    "cost_paid": 0,
                    "reason": "black_sea_veteran_free_detect",
                },
                source=src_id,
                controller=controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


BLACK_SEA_VETERAN = make_vessel(
    name="Black Sea Veteran",
    cost="{3T,2S}",
    power=3, hull=3,
    default_depth=DepthBand.DEEP,
    keywords=["silent_running"],
    setup_interceptors=_black_sea_veteran_setup,
    text="Silent Running. Crush-Dive: detect target Vessel an opponent controls (free).",
)


# ---------------------------------------------------------------------------
# 25. Quiet Reload — undetect + 2 TC
# ---------------------------------------------------------------------------

def _quiet_reload_cast(obj: GameObject, state: GameState) -> list[Event]:
    target_id: Optional[str] = None
    targets = getattr(obj.state, "cast_target_ids", None) or []
    if targets:
        target_id = targets[0]
    else:
        bf = state.zones.get("battlefield")
        if bf:
            for oid in bf.objects:
                cand = state.objects.get(oid)
                if (cand and is_vessel(cand)
                        and cand.controller == obj.controller
                        and "Flagship" not in cand.characteristics.subtypes):
                    target_id = oid
                    break

    events: list[Event] = []
    if target_id:
        _flip_undetected(state, target_id)
        events.append(_make_become_undetected_event(target_id, obj.id, obj.controller))
    _grant_charges(state, obj.controller, tc=2)
    return events


QUIET_RELOAD = make_action(
    name="Quiet Reload",
    cost="{2S}",
    text="Target Vessel you control becomes undetected; gain 2 TC.",
    cast_effect_fn=_quiet_reload_cast,
)


# ---------------------------------------------------------------------------
# 26. Acoustic Camouflage — Doctrine: your Vessels ETB silent_running
# ---------------------------------------------------------------------------

def _acoustic_camouflage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When your Vessels ETB, set their detected=False and add silent_running
    permanently while this Doctrine is in play."""
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("to_zone_type") != ZoneType.BATTLEFIELD:
            return False
        oid = event.payload.get("object_id")
        target = st.objects.get(oid) if oid else None
        if target is None or not is_vessel(target):
            return False
        if target.controller != controller:
            return False
        # Don't apply to the Doctrine itself or to the Flagship.
        if oid == src_id:
            return False
        if "Flagship" in target.characteristics.subtypes:
            return False
        return True

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        target = st.objects.get(oid) if oid else None
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        target.state.detected = False
        # Best-effort SR keyword grant: append to the abilities list.
        existing = target.characteristics.abilities or []
        if not any(
            (isinstance(a, dict) and a.get("keyword") == "silent_running")
            for a in existing
        ):
            target.characteristics.abilities = list(existing) + [{"keyword": "silent_running"}]
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


ACOUSTIC_CAMOUFLAGE = make_doctrine(
    name="Acoustic Camouflage",
    cost="{2T,2S}",
    text="Your Vessels enter the battlefield with silent_running.",
    setup_interceptors=_acoustic_camouflage_setup,
)


# ---------------------------------------------------------------------------
# 27. Operational Brief — draw 2 (3 if you have undetected)
# ---------------------------------------------------------------------------

def _operational_brief_cast(obj: GameObject, state: GameState) -> list[Event]:
    count = 2
    if _undetected_vessels_you_control(state, obj.controller):
        count = 3
    return [Event(
        type=EventType.DRAW,
        payload={"player": obj.controller, "count": count},
        source=obj.id,
        controller=obj.controller,
    )]


OPERATIONAL_BRIEF = make_action(
    name="Operational Brief",
    cost="{1S}",
    text="Draw 2; if you control an undetected Vessel, draw 3.",
    cast_effect_fn=_operational_brief_cast,
)


# ---------------------------------------------------------------------------
# 28. Periscope Sweep — detect; if cost ≤ 3, also tap
# ---------------------------------------------------------------------------

def _periscope_sweep_cast(obj: GameObject, state: GameState) -> list[Event]:
    target_id: Optional[str] = None
    targets = getattr(obj.state, "cast_target_ids", None) or []
    if targets:
        target_id = targets[0]
    else:
        # Pick any opposing undetected Vessel.
        candidates = _opposing_undetected_vessels(state, obj.controller)
        if candidates:
            target_id = candidates[0].id

    events: list[Event] = []
    if not target_id:
        return events

    target = state.objects.get(target_id)
    if target is None or not is_vessel(target):
        return events

    target.state.detected = True
    target.state.detected_until = "end_of_turn"
    events.append(Event(
        type=EventType.DEPTHS_DETECT,
        payload={
            "defender": obj.controller,
            "attacker_id": target_id,
            "cost_paid": 0,
            "reason": "periscope_sweep",
        },
        source=obj.id,
        controller=obj.controller,
    ))

    # Cost check: parse the printed mana cost as a ChargeCost; total <= 3
    # means tap as well.
    try:
        from src.engine.depths import parse_charge_cost
        cost = parse_charge_cost(target.characteristics.mana_cost)
        total = cost.total_fixed
        if total <= 3:
            target.state.tapped = True
    except Exception:
        pass

    return events


PERISCOPE_SWEEP = make_action(
    name="Periscope Sweep",
    cost="{1S}",
    text="Detect target Vessel; if it has cost 3 or less, also tap it.",
    cast_effect_fn=_periscope_sweep_cast,
)


# ---------------------------------------------------------------------------
# 29. Submersion Veteran — Crush-Dive: +1/+0 EOT
# ---------------------------------------------------------------------------

def _submersion_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    src_id = obj.id
    controller = obj.controller

    def _filter(event: Event, st: GameState) -> bool:
        if event.type not in (EventType.DEPTHS_DIVE, EventType.DEPTHS_SURFACE_VESSEL):
            return False
        return event.payload.get("object_id") == src_id

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": src_id,
                    "power_mod": 1,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                },
                source=src_id,
                controller=controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=src_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]


SUBMERSION_VETERAN = make_vessel(
    name="Submersion Veteran",
    cost="{2T,1S}",
    power=2, hull=4,
    default_depth=DepthBand.MID,
    keywords=["silent_running"],
    setup_interceptors=_submersion_veteran_setup,
    text="Silent Running. Crush-Dive: this gets +1/+0 EOT.",
)


# ---------------------------------------------------------------------------
# 30. Black Sea Doctrine — end step: ping Flagship per undetected vessel
# ---------------------------------------------------------------------------

def _black_sea_doctrine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end of YOUR turn, deal 1 damage to opposing Flagship for each
    undetected Vessel you control."""
    from src.engine.depths import get_flagship

    src_id = obj.id
    controller = obj.controller

    def _effect(event: Event, st: GameState) -> list[Event]:
        undetected = _undetected_vessels_you_control(st, controller)
        if not undetected:
            return []
        events: list[Event] = []
        for opp_pid in [p for p in st.players if p != controller]:
            opp_flagship = get_flagship(opp_pid, st)
            if opp_flagship is None:
                continue
            damage = len(undetected)
            events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    "target": opp_flagship.id,
                    "amount": damage,
                    "source": src_id,
                    "is_combat": False,
                    "reason": "black_sea_doctrine",
                },
                source=src_id,
                controller=controller,
            ))
        return events

    return [make_depths_end_phase_trigger(obj, _effect, controller_only=True)]


BLACK_SEA_DOCTRINE = make_doctrine(
    name="Black Sea Doctrine",
    cost="{3T,3S}",
    text="At your end step, deal 1 to opposing Flagship for each undetected Vessel you control.",
    setup_interceptors=_black_sea_doctrine_setup,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SILENT_HUNTER_CARDS: dict[str, CardDefinition] = {
    card.name: card for card in [
        PERISCOPE_RECON,
        LISTENING_POST,
        DIESEL_WHISPER,
        ECHO_CHAMBER_MATE,
        COLD_HULL_ENGINEER,
        STALKER_SUB,
        BOTTOM_CRAWLER_PROBE,
        ACOUSTIC_DECOY,
        SONAR_JAMMER,
        FAILED_PING,
        U_CLASS_STALKER,
        COLD_CATHODE_PERISCOPE,
        IRON_DISCIPLINE,
        TYPE_XXI_PHANTOM,
        SONAR_DECOY_CREW,
        HYDROPHONE_OPERATOR,
        DIVE_MASTER,
        WHISPER_BELOW,
        SILENT_SERVICE_DOCTRINE,
        DEAD_STOP_MANEUVER,
        SNORKEL_STALKER,
        THREAT_BOARD_ANALYST,
        WOLF_AT_THE_DOOR,
        BLACK_SEA_VETERAN,
        QUIET_RELOAD,
        ACOUSTIC_CAMOUFLAGE,
        OPERATIONAL_BRIEF,
        PERISCOPE_SWEEP,
        SUBMERSION_VETERAN,
        BLACK_SEA_DOCTRINE,
    ]
}


__all__ = ["SILENT_HUNTER_CARDS"]
