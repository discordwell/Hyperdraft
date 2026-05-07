"""SUBS — Wolfpack archetype (30 cards).

Steel grey-blue Kriegsmarine swarm: cheap Submarines flood SURFACE/PERISCOPE
turns 1-3, then saturate-attack the Flagship while WOLFPACK N triggers scale
every attacker. Heavy Torpedo, light Sonar.

Mechanic notes
--------------
* WOLFPACK N: counts other attacking allied Submarines via
  ``obj.state.attacking == True`` at trigger time. If count >= N, fire.
* Sink-on-attack riders: ``make_death_trigger`` (sinking == OBJECT_DESTROYED).
* Lord effects on Submarines: filter on
  ``CardType.DEPTHS_VESSEL`` + ``"Submarine"`` subtype + same controller.
* "+X power EOT" / "+X/+Y EOT": emit ``EventType.PT_MODIFICATION`` with
  ``duration='end_of_turn'`` so the engine's existing temp-mod track fires
  on cleanup. Hull damage persists across turns in the depths engine.
* Charge gain (Torpedo / Sonar): emit ``EventType.DEPTHS_RESUPPLY`` with
  the explicit ``tc_gained``/``sc_gained`` keys so the resupply system
  interceptor leaves them intact (the system handler skips when those
  keys are pre-populated).
* Untap: emit ``EventType.UNTAP`` with ``object_id``.
* Card draw: ``EventType.DRAW`` with ``player`` + ``count``.
* Damage to Flagship: ``EventType.DAMAGE`` against the opposing flagship
  via ``get_flagship`` lookup.
"""

from __future__ import annotations

from src.cards.depths.submarine_fleet._factories import (
    DepthBand,
    make_action,
    make_crew,
    make_doctrine,
    make_vessel,
    make_weapon,
)
from src.cards.interceptor_helpers import (
    make_attack_trigger,
    make_death_trigger,
    make_etb_trigger,
    make_keyword_grant,
    make_static_pt_boost,
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
# Helpers (Wolfpack-local; we keep these tiny and obvious)
# ---------------------------------------------------------------------------

def _is_submarine(obj: GameObject) -> bool:
    """True if obj is on battlefield and a Submarine Vessel."""
    if obj is None:
        return False
    if obj.zone != ZoneType.BATTLEFIELD:
        return False
    if not is_vessel(obj):
        return False
    return "Submarine" in obj.characteristics.subtypes


def _your_submarines_filter(source: GameObject):
    """Filter factory: any Submarine you control (including source).

    Used by lord effects ("your Submarines get +1/+0").
    """
    def _f(target: GameObject, state: GameState) -> bool:
        return (
            target.controller == source.controller
            and _is_submarine(target)
        )
    return _f


def _your_drones_filter(source: GameObject):
    """Filter factory: any Drone you control."""
    def _f(target: GameObject, state: GameState) -> bool:
        return (
            target.controller == source.controller
            and is_vessel(target)
            and target.zone == ZoneType.BATTLEFIELD
            and "Drone" in target.characteristics.subtypes
        )
    return _f


def _attacking_allied_submarines(source: GameObject, state: GameState) -> list[GameObject]:
    """Other attacking Submarines you control (excludes source itself)."""
    out: list[GameObject] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return out
    for oid in battlefield.objects:
        obj = state.objects.get(oid)
        if obj is None or obj.id == source.id:
            continue
        if not _is_submarine(obj):
            continue
        if obj.controller != source.controller:
            continue
        if not getattr(obj.state, "attacking", False):
            continue
        out.append(obj)
    return out


def _attacking_submarines_inclusive(controller: str, state: GameState) -> list[GameObject]:
    """All attacking Submarines a player controls (inclusive)."""
    out: list[GameObject] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return out
    for oid in battlefield.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if not _is_submarine(obj):
            continue
        if obj.controller != controller:
            continue
        if not getattr(obj.state, "attacking", False):
            continue
        out.append(obj)
    return out


def _opposing_flagship(controller: str, state: GameState) -> GameObject | None:
    """The flagship of any opposing player (depths is 1v1)."""
    for pid in state.players:
        if pid == controller:
            continue
        flagship = get_flagship(pid, state)
        if flagship is not None:
            return flagship
    return None


def _pt_mod_event(target_id: str, source_id: str, *, power: int = 0, toughness: int = 0) -> Event:
    """End-of-turn P/T modifier via the engine's standard event."""
    return Event(
        type=EventType.PT_MODIFICATION,
        payload={
            "object_id": target_id,
            "power_mod": power,
            "toughness_mod": toughness,
            "duration": "end_of_turn",
        },
        source=source_id,
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


def _draw_event(player_id: str, source_id: str, count: int = 1) -> Event:
    return Event(
        type=EventType.DRAW,
        payload={"player": player_id, "count": count},
        source=source_id,
        controller=player_id,
    )


def _damage_event(target_id: str, source_id: str, amount: int) -> Event:
    return Event(
        type=EventType.DAMAGE,
        payload={
            "target": target_id,
            "amount": int(amount),
            "source": source_id,
            "is_combat": False,
        },
        source=source_id,
    )


def _untap_event(target_id: str, source_id: str) -> Event:
    return Event(
        type=EventType.UNTAP,
        payload={"object_id": target_id},
        source=source_id,
    )


# ===========================================================================
# VESSELS
# ===========================================================================
# Vanilla bodies first, then triggered/lord vessels.

# --- Vanilla SURFACE bodies -------------------------------------------------

U_BOAT_WOLF_CUB = make_vessel(
    name="U-Boat Wolf-cub",
    power=2,
    hull=1,
    cost="{1T}",
    default_depth=DepthBand.SURFACE,
    text="Cheap pack body.",
)

COASTAL_RAIDER = make_vessel(
    name="Coastal Raider",
    power=3,
    hull=1,
    cost="{2T}",
    default_depth=DepthBand.SURFACE,
    text="",
)

SURFACE_SKIRMISHER = make_vessel(
    name="Surface Skirmisher",
    power=3,
    hull=2,
    cost="{2T}",
    default_depth=DepthBand.SURFACE,
    text="Vanilla aggressor.",
)


# --- Sea Wolf Scout: draw on coordinated attack -----------------------------

def sea_wolf_scout_setup(obj: GameObject, state: GameState) -> list:
    """When this attacks alongside another attacking Submarine, draw 1."""
    def effect(event: Event, st: GameState) -> list[Event]:
        if not _attacking_allied_submarines(obj, st):
            return []
        return [_draw_event(obj.controller, obj.id, count=1)]
    return [make_attack_trigger(obj, effect)]


SEA_WOLF_SCOUT = make_vessel(
    name="Sea Wolf Scout",
    power=1,
    hull=2,
    cost="{1T}",
    default_depth=DepthBand.SURFACE,
    text="When this attacks alongside another attacking Submarine, draw 1.",
    setup_interceptors=sea_wolf_scout_setup,
)


# --- Pack Runner: WOLFPACK 1 → +1 power EOT (self) --------------------------

def pack_runner_setup(obj: GameObject, state: GameState) -> list:
    def effect(event: Event, st: GameState) -> list[Event]:
        if len(_attacking_allied_submarines(obj, st)) < 1:
            return []
        return [_pt_mod_event(obj.id, obj.id, power=1)]
    return [make_attack_trigger(obj, effect)]


PACK_RUNNER = make_vessel(
    name="Pack Runner",
    power=2,
    hull=2,
    cost="{2T}",
    default_depth=DepthBand.SURFACE,
    text="Wolfpack 1: +1 power EOT.",
    setup_interceptors=pack_runner_setup,
)


# --- Pack Leader U-99: WOLFPACK 2 → all your attacking Submarines +1 power --

def pack_leader_u99_setup(obj: GameObject, state: GameState) -> list:
    def effect(event: Event, st: GameState) -> list[Event]:
        if len(_attacking_allied_submarines(obj, st)) < 2:
            return []
        events: list[Event] = []
        for sub in _attacking_submarines_inclusive(obj.controller, st):
            events.append(_pt_mod_event(sub.id, obj.id, power=1))
        return events
    return [make_attack_trigger(obj, effect)]


PACK_LEADER_U99 = make_vessel(
    name="Pack Leader U-99",
    power=3,
    hull=3,
    cost="{3T}",
    default_depth=DepthBand.SURFACE,
    text="Wolfpack 2: your attacking Submarines get +1 power EOT.",
    setup_interceptors=pack_leader_u99_setup,
)


# --- Type-VII Veteran: gain 1 TC on attack ----------------------------------

def type_vii_veteran_setup(obj: GameObject, state: GameState) -> list:
    def effect(event: Event, st: GameState) -> list[Event]:
        return [_gain_charges_event(obj.controller, obj.id, tc=1)]
    return [make_attack_trigger(obj, effect)]


TYPE_VII_VETERAN = make_vessel(
    name="Type-VII Veteran",
    power=3,
    hull=3,
    cost="{3T}",
    default_depth=DepthBand.PERISCOPE,
    text="Whenever this attacks, gain 1 Torpedo Charge.",
    setup_interceptors=type_vii_veteran_setup,
)


# --- Echo Repeater: grant homing to one ally on combined attack -------------

def echo_repeater_setup(obj: GameObject, state: GameState) -> list:
    """When this attacks alongside another attacking Submarine, grant homing
    to one such ally EOT.

    Target picking is deliberately deterministic (first allied attacker
    found) to avoid pending-choice plumbing in v1 — Wolfpack saturation
    means there's almost always one trivially-eligible ally.
    """
    def effect(event: Event, st: GameState) -> list[Event]:
        allies = _attacking_allied_submarines(obj, st)
        if not allies:
            return []
        ally = allies[0]
        # Stash a temporary keyword on the ally; combat manager reads
        # depths_keywords and the standard QUERY_ABILITIES surface.
        if ally.card_def is not None:
            existing = set(getattr(ally.card_def, "depths_keywords", None) or set())
            if "homing" not in existing:
                # Mark via state so EOT cleanup hooks could revoke it.
                setattr(ally.state, "_temp_keywords_eot",
                        set(getattr(ally.state, "_temp_keywords_eot", set())) | {"homing"})
        return []
    return [make_attack_trigger(obj, effect)]


ECHO_REPEATER = make_vessel(
    name="Echo Repeater",
    power=2,
    hull=3,
    cost="{2T,1S}",
    default_depth=DepthBand.PERISCOPE,
    text="When this attacks alongside another attacking Submarine, that other Submarine gets homing EOT.",
    setup_interceptors=echo_repeater_setup,
)


# --- Kapitanleutnant Kretschmer: WOLFPACK 1 → opp loses 1 SC ----------------

def kretschmer_setup(obj: GameObject, state: GameState) -> list:
    def effect(event: Event, st: GameState) -> list[Event]:
        if len(_attacking_allied_submarines(obj, st)) < 1:
            return []
        events: list[Event] = []
        for pid, player in st.players.items():
            if pid == obj.controller:
                continue
            # Drain via a negative-resupply marker; the resupply handler
            # respects pre-set tc_gained/sc_gained and we mutate the pool
            # directly here for fidelity.
            old = int(getattr(player, "sc", 0) or 0)
            player.sc = max(0, old - 1)
            events.append(Event(
                type=EventType.DEPTHS_RESUPPLY,
                payload={
                    "player": pid,
                    "tc_gained": 0,
                    "sc_gained": -(old - player.sc),
                    "reason": "kretschmer_drain",
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect)]


KAPITANLEUTNANT_KRETSCHMER = make_vessel(
    name="Kapitänleutnant Kretschmer",
    power=4,
    hull=3,
    cost="{3T,1S}",
    default_depth=DepthBand.PERISCOPE,
    text="Wolfpack 1: opponent loses 1 Sonar.",
    setup_interceptors=kretschmer_setup,
)


# --- Convoy Hunter: draw 1 on damaging Flagship -----------------------------

def convoy_hunter_setup(obj: GameObject, state: GameState) -> list:
    def filter_fn(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get("source") != src.id:
            return False
        target_id = event.payload.get("target")
        target = st.objects.get(target_id) if target_id else None
        if target is None:
            return False
        return "Flagship" in target.characteristics.subtypes

    def effect(event: Event, st: GameState) -> list[Event]:
        return [_draw_event(obj.controller, obj.id, count=1)]

    # Build the trigger directly so the filter sees the DAMAGE event.
    from src.cards.interceptor_helpers import make_damage_trigger
    return [make_damage_trigger(obj, effect, filter_fn=filter_fn)]


CONVOY_HUNTER = make_vessel(
    name="Convoy Hunter",
    power=4,
    hull=2,
    cost="{3T}",
    default_depth=DepthBand.SURFACE,
    text="Whenever this deals damage to a Flagship, draw 1.",
    setup_interceptors=convoy_hunter_setup,
)


# --- Iron Coffin Veteran: deal 1 to opp Flagship when sunk ------------------

def iron_coffin_veteran_setup(obj: GameObject, state: GameState) -> list:
    def effect(event: Event, st: GameState) -> list[Event]:
        flag = _opposing_flagship(obj.controller, st)
        if flag is None:
            return []
        return [_damage_event(flag.id, obj.id, 1)]
    return [make_death_trigger(obj, effect)]


IRON_COFFIN_VETERAN = make_vessel(
    name="Iron Coffin Veteran",
    power=2,
    hull=3,
    cost="{2T}",
    default_depth=DepthBand.PERISCOPE,
    text="When sunk, deal 1 to opposing Flagship.",
    setup_interceptors=iron_coffin_veteran_setup,
)


# --- Hammerhead U-505: WOLFPACK 3 → double damage EOT (self) ----------------

def hammerhead_u505_setup(obj: GameObject, state: GameState) -> list:
    """WOLFPACK 3: deals double damage EOT.

    Implementation: we can't mutate the damage-dealing rule per-card without
    a TRANSFORM interceptor on DAMAGE. v1 approximation — instead of a true
    'double damage' we add +power equal to current power EOT (so a 5-power
    sub becomes 10-power for the rest of turn). This is the same in-combat
    outcome as 'double damage' for a single attack against a single target,
    which is the intended Saturation-Strike use case.
    """
    def effect(event: Event, st: GameState) -> list[Event]:
        if len(_attacking_allied_submarines(obj, st)) < 3:
            return []
        # Current base power (5). Add +5 EOT for "double damage"-equivalent.
        cur_power = int(obj.characteristics.power or 0)
        return [_pt_mod_event(obj.id, obj.id, power=cur_power)]
    return [make_attack_trigger(obj, effect)]


HAMMERHEAD_U505 = make_vessel(
    name="Hammerhead U-505",
    power=5,
    hull=3,
    cost="{4T}",
    default_depth=DepthBand.PERISCOPE,
    text="Wolfpack 3: deals double damage EOT.",
    setup_interceptors=hammerhead_u505_setup,
)


# --- Type-IX Long Hunter: WOLFPACK 2 → gain 2 TC ----------------------------

def type_ix_long_hunter_setup(obj: GameObject, state: GameState) -> list:
    def effect(event: Event, st: GameState) -> list[Event]:
        if len(_attacking_allied_submarines(obj, st)) < 2:
            return []
        return [_gain_charges_event(obj.controller, obj.id, tc=2)]
    return [make_attack_trigger(obj, effect)]


TYPE_IX_LONG_HUNTER = make_vessel(
    name="Type-IX Long Hunter",
    power=4,
    hull=5,
    cost="{4T,1S}",
    default_depth=DepthBand.MID,
    text="Wolfpack 2: gain 2 Torpedo.",
    setup_interceptors=type_ix_long_hunter_setup,
)


# --- Admiral Donitz (Legendary): 3+ pack → all attackers +2 damage EOT ------

def admiral_donitz_setup(obj: GameObject, state: GameState) -> list:
    """When this attacks alongside 3+ Submarines, your attacking Submarines
    deal +2 damage EOT.

    +2 damage is implemented as +2 power EOT — same outcome for a single
    swing against a single target, which is the intended saturation-strike
    finisher use case.
    """
    def effect(event: Event, st: GameState) -> list[Event]:
        if len(_attacking_allied_submarines(obj, st)) < 3:
            return []
        events: list[Event] = []
        for sub in _attacking_submarines_inclusive(obj.controller, st):
            events.append(_pt_mod_event(sub.id, obj.id, power=2))
        return events
    return [make_attack_trigger(obj, effect)]


ADMIRAL_DONITZ = make_vessel(
    name="Admiral Dönitz",
    power=6,
    hull=6,
    cost="{5T,1S}",
    default_depth=DepthBand.PERISCOPE,
    text="When this attacks alongside 3+ Submarines, your attacking Submarines deal +2 damage EOT.",
    is_legendary=True,
    setup_interceptors=admiral_donitz_setup,
)


# ===========================================================================
# CREW
# ===========================================================================

FRENZIED_TORPEDO_MATE = make_crew(
    name="Frenzied Torpedo Mate",
    cost="{1T}",
    power_mod=1,
    toughness_mod=0,
    text="Equipped Submarine gets +1/+0.",
)

BRASS_CONDUIT_MATE = make_crew(
    name="Brass Conduit Mate",
    cost="{1T}",
    power_mod=0,
    toughness_mod=1,
    keywords_to_grant=["silent_running"],
    text="Equipped Submarine gets +0/+1 and silent_running.",
)


# Iron Bow Crew: +2/+0 and "Whenever it attacks, gain 1 TC."
# We stack the static P/T boost with a granted activated/passive — the
# attack-trigger rider needs custom setup since make_equipment_setup's
# granted_activated_abilities path is for activated, not triggered.

def iron_bow_crew_setup(obj: GameObject, state: GameState) -> list:
    """+2/+0 stat boost AND attack-trigger on equipped Submarine."""
    from src.cards.interceptor_helpers import make_equipment_setup
    base = make_equipment_setup(power_mod=2, toughness_mod=0)
    interceptors = base(obj, state)

    # Attach an attack-trigger to whatever the crew is equipped to. We
    # listen for ATTACH events and wire the trigger onto the host then.
    def attach_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACH:
            return False
        return event.payload.get("object_id") == obj.id

    def attach_handler(event: Event, st: GameState):
        from src.engine import Interceptor, InterceptorAction, InterceptorPriority, InterceptorResult, new_id
        target_id = event.payload.get("target_id")
        host = st.objects.get(target_id) if target_id else None
        if host is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        def trig_filter(ev: Event, _st: GameState) -> bool:
            if ev.type != EventType.ATTACK_DECLARED:
                return False
            return ev.payload.get("attacker_id") == host.id

        def trig_handler(ev: Event, _st: GameState):
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[_gain_charges_event(host.controller, obj.id, tc=1)],
            )

        rider = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=trig_filter,
            handler=trig_handler,
            duration="while_on_battlefield",
        )
        st._game.register_interceptor(rider) if hasattr(st, "_game") else None
        return InterceptorResult(action=InterceptorAction.PASS)

    from src.engine import Interceptor, InterceptorPriority, new_id
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attach_filter,
        handler=attach_handler,
        duration="while_on_battlefield",
    ))
    return interceptors


IRON_BOW_CREW = make_crew(
    name="Iron Bow Crew",
    cost="{2T}",
    text="Equipped Submarine gets +2/+0 and 'Whenever it attacks, gain 1 TC.'",
    setup_interceptors=iron_bow_crew_setup,
)


# Pack Mind Officer: equipped Sub has WOLFPACK 1: pack +0/+1 EOT.
# The equipped Sub itself gets the trigger; we register an ATTACH listener.

def pack_mind_officer_setup(obj: GameObject, state: GameState) -> list:
    """On attach: register an ATTACK_DECLARED trigger on the host Sub."""
    def attach_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACH:
            return False
        return event.payload.get("object_id") == obj.id

    def attach_handler(event: Event, st: GameState):
        from src.engine import Interceptor, InterceptorAction, InterceptorPriority, InterceptorResult, new_id
        host_id = event.payload.get("target_id")
        host = st.objects.get(host_id) if host_id else None
        if host is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        def trig_filter(ev: Event, _st: GameState) -> bool:
            if ev.type != EventType.ATTACK_DECLARED:
                return False
            return ev.payload.get("attacker_id") == host.id

        def trig_handler(ev: Event, _st: GameState):
            allies = _attacking_allied_submarines(host, _st)
            if len(allies) < 1:
                return InterceptorResult(action=InterceptorAction.PASS)
            evs: list[Event] = []
            for sub in _attacking_submarines_inclusive(host.controller, _st):
                evs.append(_pt_mod_event(sub.id, obj.id, toughness=1))
            return InterceptorResult(action=InterceptorAction.REACT, new_events=evs)

        rider = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=trig_filter,
            handler=trig_handler,
            duration="while_on_battlefield",
        )
        if hasattr(st, "_game"):
            st._game.register_interceptor(rider)
        return InterceptorResult(action=InterceptorAction.PASS)

    from src.engine import Interceptor, InterceptorPriority, new_id
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attach_filter,
        handler=attach_handler,
        duration="while_on_battlefield",
    )]


PACK_MIND_OFFICER = make_crew(
    name="Pack Mind Officer",
    cost="{2S}",
    text="Equipped Submarine has Wolfpack 1: pack gains +0/+1 EOT.",
    setup_interceptors=pack_mind_officer_setup,
)


GUNNERY_OFFICER = make_crew(
    name="Gunnery Officer",
    cost="{1T,1S}",
    keywords_to_grant=["homing"],
    text="Equipped Submarine has homing.",
)


# ===========================================================================
# WEAPONS
# ===========================================================================

# Forward Torpedo Tube: equipped {1T}: 1 dmg to target Vessel. 3 charges.
def _weapon_damage_effect(amount: int):
    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        events = [_damage_event(target_id, o.id, amount)]
        # Decrement weapon charges; when 0, sink the weapon. The weapon is
        # the *attached* card, but since granted_activated_abilities live
        # on the host, we look up the weapon via host's attachments.
        host = o
        equipment_id = None
        for attach_id in getattr(host.state, "attachments", []) or []:
            attach = state.objects.get(attach_id)
            if attach is None or attach.card_def is None:
                continue
            charges_left = getattr(attach.card_def, "depths_weapon_charges", None)
            if charges_left is None:
                continue
            equipment_id = attach.id
            new_charges = max(0, int(charges_left) - 1)
            attach.card_def.depths_weapon_charges = new_charges
            if new_charges == 0:
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": equipment_id, "reason": "weapon_depleted"},
                    source=o.id,
                ))
            break
        return events
    return _effect


FORWARD_TORPEDO_TUBE = make_weapon(
    name="Forward Torpedo Tube",
    cost="{1T}",
    charges=3,
    granted_activated_abilities=[{
        "cost": "{1T}",
        "effect_fn": _weapon_damage_effect(1),
        "description": "{1T}: deal 1 damage to a target Vessel",
        "targets_required": 1,
        "target_kind": "vessel",
    }],
    text="Equipped: {1T}: deal 1 to a target Vessel. 3 charge counters; sinks at 0.",
)


# Wire-Guided Spread: {1T}: deal 2 to target within 2 bands. 3 charges.
def _wire_guided_effect(o: GameObject, state: GameState, targets) -> list[Event]:
    if not targets:
        return []
    t = targets[0]
    target_id = getattr(t, "object_id", None) or t
    target_obj = state.objects.get(target_id) if isinstance(target_id, str) else None
    # Range gate: 2 bands. If we can't compute, pass-through (engine target
    # filter already constrained the legal pick).
    if target_obj is not None:
        from src.engine.depths import depth_difference
        own_band = getattr(o.state, "depth_band", None)
        tgt_band = getattr(target_obj.state, "depth_band", None)
        if own_band is not None and tgt_band is not None:
            if depth_difference(own_band, tgt_band) > 2:
                return []
    events = [_damage_event(target_id, o.id, 2)]
    # Decrement weapon charges (mirrors _weapon_damage_effect logic).
    for attach_id in getattr(o.state, "attachments", []) or []:
        attach = state.objects.get(attach_id)
        if attach is None or attach.card_def is None:
            continue
        charges_left = getattr(attach.card_def, "depths_weapon_charges", None)
        if charges_left is None:
            continue
        new_charges = max(0, int(charges_left) - 1)
        attach.card_def.depths_weapon_charges = new_charges
        if new_charges == 0:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": attach.id, "reason": "weapon_depleted"},
                source=o.id,
            ))
        break
    return events


WIRE_GUIDED_SPREAD = make_weapon(
    name="Wire-Guided Spread",
    cost="{2T}",
    charges=3,
    granted_activated_abilities=[{
        "cost": "{1T}",
        "effect_fn": _wire_guided_effect,
        "description": "{1T}: deal 2 to target Vessel within 2 bands",
        "targets_required": 1,
        "target_kind": "vessel",
    }],
    text="Equipped: {1T}: deal 2 to target Vessel within 2 bands.",
)


# ===========================================================================
# ACTIONS (sorcery-speed effects)
# ===========================================================================

# Saturation Strike: your attacking Submarines get +2/+0 EOT.
def saturation_strike_effect(obj: GameObject, state: GameState) -> list[Event]:
    events: list[Event] = []
    for sub in _attacking_submarines_inclusive(obj.controller, state):
        events.append(_pt_mod_event(sub.id, obj.id, power=2))
    return events


SATURATION_STRIKE = make_action(
    name="Saturation Strike",
    cost="{2T}",
    text="Your attacking Submarines get +2/+0 EOT.",
    cast_effect_fn=saturation_strike_effect,
)


# Donitz's Recall: untap up to 2 attacking Submarines you control.
def donitz_recall_effect(obj: GameObject, state: GameState) -> list[Event]:
    attackers = _attacking_submarines_inclusive(obj.controller, state)
    events: list[Event] = []
    for sub in attackers[:2]:
        sub.state.tapped = False
        sub.state.attacking = False
        events.append(_untap_event(sub.id, obj.id))
    return events


DONITZ_RECALL = make_action(
    name="Dönitz's Recall",
    cost="{1T,1S}",
    text="Untap up to 2 attacking Submarines you control.",
    cast_effect_fn=donitz_recall_effect,
)


# Loaded Tubes: target Submarine gets +3/+0 and homing EOT.
# v1: target dispatch isn't fully wired through Action targeting yet — we
# pick the player's first untapped Submarine to keep the code self-contained.
def loaded_tubes_effect(obj: GameObject, state: GameState) -> list[Event]:
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    for oid in battlefield.objects:
        o = state.objects.get(oid)
        if o is None or o.controller != obj.controller or not _is_submarine(o):
            continue
        # Stash homing EOT.
        setattr(o.state, "_temp_keywords_eot",
                set(getattr(o.state, "_temp_keywords_eot", set())) | {"homing"})
        return [_pt_mod_event(o.id, obj.id, power=3)]
    return []


LOADED_TUBES = make_action(
    name="Loaded Tubes",
    cost="{1T}",
    text="Target Submarine gets +3/+0 and homing EOT.",
    cast_effect_fn=loaded_tubes_effect,
)


# Reload at Dock: untap target Submarine and remove all damage from it.
def reload_at_dock_effect(obj: GameObject, state: GameState) -> list[Event]:
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    # Pick the most-damaged Submarine you control — best deterministic fit
    # for "target Submarine" in the absence of an interactive choice.
    best = None
    best_damage = -1
    for oid in battlefield.objects:
        o = state.objects.get(oid)
        if o is None or o.controller != obj.controller or not _is_submarine(o):
            continue
        dmg = int(getattr(o.state, "damage", 0) or 0)
        if dmg > best_damage:
            best_damage = dmg
            best = o
    if best is None:
        return []
    best.state.damage = 0
    best.state.tapped = False
    best.state.attacking = False
    return [_untap_event(best.id, obj.id)]


RELOAD_AT_DOCK = make_action(
    name="Reload at Dock",
    cost="{1T}",
    text="Untap target Submarine and remove all damage from it.",
    cast_effect_fn=reload_at_dock_effect,
)


# Coordinated Strike: up to 3 target Submarines you control gain WOLFPACK 1 EOT and untap.
# Wolfpack-1 EOT is a nuanced trigger; we implement the concrete benefit
# (untap + the +1 power for the upcoming attack as if WOLFPACK 1 fired).
def coordinated_strike_effect(obj: GameObject, state: GameState) -> list[Event]:
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    picks: list[GameObject] = []
    for oid in battlefield.objects:
        if len(picks) >= 3:
            break
        o = state.objects.get(oid)
        if o is None or o.controller != obj.controller or not _is_submarine(o):
            continue
        picks.append(o)
    events: list[Event] = []
    for sub in picks:
        sub.state.tapped = False
        sub.state.attacking = False
        events.append(_untap_event(sub.id, obj.id))
        # +1 power EOT as the practical "Wolfpack 1: +1 power EOT" effect.
        events.append(_pt_mod_event(sub.id, obj.id, power=1))
    return events


COORDINATED_STRIKE = make_action(
    name="Coordinated Strike",
    cost="{3T}",
    text="Up to 3 target Submarines you control gain Wolfpack 1 EOT and untap.",
    cast_effect_fn=coordinated_strike_effect,
)


# ===========================================================================
# DOCTRINES
# ===========================================================================

def wolfpack_doctrine_setup(obj: GameObject, state: GameState) -> list:
    """Your Submarines get +1/+0."""
    return make_static_pt_boost(obj, 1, 0, _your_submarines_filter(obj))


WOLFPACK_DOCTRINE = make_doctrine(
    name="Wolfpack Doctrine",
    cost="{3T}",
    text="Your Submarines get +1/+0.",
    setup_interceptors=wolfpack_doctrine_setup,
)


def iron_cross_pennant_setup(obj: GameObject, state: GameState) -> list:
    """When 2+ Submarines you control attack, draw 1.

    We listen on ATTACK_DECLARED and check the controller's attacking-Sub
    count *post*-event. To avoid duplicate fires we mark the turn number
    we last fired on.
    """
    def trig_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get("attacker_id")
        attacker = st.objects.get(attacker_id) if attacker_id else None
        if attacker is None or attacker.controller != obj.controller:
            return False
        return _is_submarine(attacker)

    def trig_handler(event: Event, st: GameState):
        from src.engine import InterceptorAction, InterceptorResult
        # Fire only once per turn, on the threshold-crossing attacker.
        last = getattr(obj.state, "_iron_cross_last_turn", None)
        if last == st.turn_number:
            return InterceptorResult(action=InterceptorAction.PASS)
        attackers = _attacking_submarines_inclusive(obj.controller, st)
        if len(attackers) < 2:
            return InterceptorResult(action=InterceptorAction.PASS)
        obj.state._iron_cross_last_turn = st.turn_number
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_draw_event(obj.controller, obj.id, count=1)],
        )

    from src.engine import Interceptor, InterceptorPriority, new_id
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trig_filter,
        handler=trig_handler,
        duration="while_on_battlefield",
    )]


IRON_CROSS_PENNANT = make_doctrine(
    name="Iron Cross Pennant",
    cost="{2T,1S}",
    text="Whenever 2+ Submarines you control attack, draw 1.",
    setup_interceptors=iron_cross_pennant_setup,
)


def surface_strike_doctrine_setup(obj: GameObject, state: GameState) -> list:
    """At your end step, if 2+ Subs you control attacked this turn, deal 1
    to opposing Flagship."""
    def trig_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_END:
            return False
        phase = event.payload.get("phase")
        if phase not in {"surface", "depths_surface", "end", "ending", "regroup"}:
            return False
        # Only on the controller's turn.
        return st.turn_state.active_player_id == obj.controller if hasattr(st, "turn_state") else True

    def trig_handler(event: Event, st: GameState):
        from src.engine import InterceptorAction, InterceptorResult
        attackers = [
            sub for sub in st.objects.values()
            if _is_submarine(sub)
            and sub.controller == obj.controller
            and getattr(sub.state, "_attacked_this_turn", False)
        ]
        # Fall back to current attacking flag when _attacked_this_turn isn't tracked.
        if len(attackers) < 2:
            attackers = _attacking_submarines_inclusive(obj.controller, st)
        if len(attackers) < 2:
            return InterceptorResult(action=InterceptorAction.PASS)
        flag = _opposing_flagship(obj.controller, st)
        if flag is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[_damage_event(flag.id, obj.id, 1)],
        )

    from src.engine import Interceptor, InterceptorPriority, new_id
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trig_filter,
        handler=trig_handler,
        duration="while_on_battlefield",
    )]


SURFACE_STRIKE_DOCTRINE = make_doctrine(
    name="Surface Strike Doctrine",
    cost="{3T,1S}",
    text="At your end step, if 2+ Submarines you control attacked this turn, deal 1 to opposing Flagship.",
    setup_interceptors=surface_strike_doctrine_setup,
)


def kriegsmarine_banner_setup(obj: GameObject, state: GameState) -> list:
    """Your Submarines that entered this turn lose summoning sickness.

    Implementation: on every ZONE_CHANGE that lands a Submarine you
    control on the battlefield, clear its summoning_sickness flag.
    """
    def trig_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("to_zone_type") != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get("object_id")
        target = st.objects.get(target_id) if target_id else None
        if target is None or target.controller != obj.controller:
            return False
        return _is_submarine(target)

    def trig_handler(event: Event, st: GameState):
        from src.engine import InterceptorAction, InterceptorResult
        target_id = event.payload.get("object_id")
        target = st.objects.get(target_id) if target_id else None
        if target is not None:
            target.state.summoning_sickness = False
        return InterceptorResult(action=InterceptorAction.PASS)

    from src.engine import Interceptor, InterceptorPriority, new_id
    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trig_filter,
        handler=trig_handler,
        duration="while_on_battlefield",
    )]


KRIEGSMARINE_BANNER = make_doctrine(
    name="Kriegsmarine Banner",
    cost="{2T}",
    text="Your Submarines that entered this turn lose summoning sickness.",
    setup_interceptors=kriegsmarine_banner_setup,
)


# ===========================================================================
# CARD REGISTRY
# ===========================================================================

WOLFPACK_CARDS: dict[str, "object"] = {
    card.name: card for card in [
        # Vessels (12)
        U_BOAT_WOLF_CUB,
        SEA_WOLF_SCOUT,
        PACK_RUNNER,
        COASTAL_RAIDER,
        PACK_LEADER_U99,
        TYPE_VII_VETERAN,
        ECHO_REPEATER,
        KAPITANLEUTNANT_KRETSCHMER,
        SURFACE_SKIRMISHER,
        CONVOY_HUNTER,
        IRON_COFFIN_VETERAN,
        HAMMERHEAD_U505,
        TYPE_IX_LONG_HUNTER,
        ADMIRAL_DONITZ,
        # Crew (5)
        FRENZIED_TORPEDO_MATE,
        BRASS_CONDUIT_MATE,
        IRON_BOW_CREW,
        PACK_MIND_OFFICER,
        GUNNERY_OFFICER,
        # Weapons (2)
        FORWARD_TORPEDO_TUBE,
        WIRE_GUIDED_SPREAD,
        # Actions (5)
        SATURATION_STRIKE,
        DONITZ_RECALL,
        LOADED_TUBES,
        RELOAD_AT_DOCK,
        COORDINATED_STRIKE,
        # Doctrines (4)
        WOLFPACK_DOCTRINE,
        IRON_CROSS_PENNANT,
        SURFACE_STRIKE_DOCTRINE,
        KRIEGSMARINE_BANNER,
    ]
}


__all__ = ["WOLFPACK_CARDS"]
