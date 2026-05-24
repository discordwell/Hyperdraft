"""CLAN — MIRTHBOT-1 archetype (Solo Swarm / swarm).

~39 cards: 2 Cores (MIRTHBOT-1, Affection.exe), 12 Chassis, 10 Weapons,
9 Add-Ons, 3 Transients, 3 Structures. Swarm wants many cheap chassis,
self-mobile parts, and "when a part attaches" payoffs that fire frequently.
"""

from __future__ import annotations

from typing import Optional

from src.engine.types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    CardType,
)
from src.engine.clankers import (
    _gain_scrap,
    _is_chassis,
    _is_weapon,
    _is_add_on,
    _is_part,
    attach_part,
    compute_effective_power,
    compute_effective_integrity,
    make_add_on,
    make_add_on_static_integrity,
    make_add_on_static_power,
    make_chassis,
    make_chassis_etb_trigger,
    make_core,
    make_part_on_attach,
    make_structure,
    make_transient,
    make_weapon,
)


# =============================================================================
# Shared helpers (swarm-specific glue, kept local to this archetype file)
# =============================================================================


def _player_chassis_ids(state: GameState, player_id: str) -> list[str]:
    """Return obj_ids of chassis on the Assembly Floor controlled by ``player_id``."""
    ids = list(getattr(state, "clankers_assemblies", {}).get(player_id, []) or [])
    # Filter out any stale ids (defensive — death_cascade should clean these).
    return [
        cid for cid in ids
        if cid in state.objects and _is_chassis(state.objects[cid].card_def)
        and state.objects[cid].zone == ZoneType.CLANKERS_ASSEMBLY_FLOOR
    ]


def _is_synchronize(obj: Optional[GameObject]) -> bool:
    if obj is None or obj.card_def is None:
        return False
    return "synchronize" in (getattr(obj.card_def, "clankers_keywords", []) or [])


def _count_synchronize_chassis(state: GameState, player_id: str) -> int:
    """Number of chassis with 'synchronize' keyword on the floor for ``player_id``."""
    n = 0
    for cid in _player_chassis_ids(state, player_id):
        if _is_synchronize(state.objects.get(cid)):
            n += 1
    return n


def _make_temp_power_buff(
    obj: GameObject,
    state: GameState,
    *,
    target_id: str,
    power_mod: int,
    description: str = "",
) -> Interceptor:
    """Register a +N power buff on a target chassis that expires at end of turn.

    Because ``clankers_turn._phase_cleanup`` does NOT auto-sweep
    ``duration='end_of_turn'`` interceptors, we instead anchor the buff to
    the current ``state.turn_number`` at registration time. The filter returns
    False once the turn rolls over, so the buff becomes inert — the interceptor
    stays in state but contributes nothing. Cheap, correct, side-effect-free.
    """
    snapshot_turn = int(getattr(state, "turn_number", 0) or 0)

    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        if int(getattr(st, "turn_number", 0) or 0) != snapshot_turn:
            return False
        return event.payload.get("chassis_id") == target_id

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + int(power_mod)
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return Interceptor(
        id=f"{obj.id}_tempbuff_{target_id}_{snapshot_turn}_p{power_mod}",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description=description or f"+{power_mod} power EOT",
        duration="end_of_turn",
    )


def _make_temp_integrity_buff(
    obj: GameObject,
    state: GameState,
    *,
    target_id: str,
    integrity_mod: int,
    description: str = "",
) -> Interceptor:
    """+N integrity until end of turn. Same approach as _make_temp_power_buff."""
    snapshot_turn = int(getattr(state, "turn_number", 0) or 0)

    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        if int(getattr(st, "turn_number", 0) or 0) != snapshot_turn:
            return False
        return event.payload.get("chassis_id") == target_id

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + int(integrity_mod)
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return Interceptor(
        id=f"{obj.id}_tempbuff_{target_id}_{snapshot_turn}_i{integrity_mod}",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description=description or f"+{integrity_mod} integrity EOT",
        duration="end_of_turn",
    )


def _register_interceptor(state: GameState, obj: GameObject, ic: Interceptor) -> None:
    """Add ``ic`` to state and track it on ``obj.interceptor_ids`` for cleanup."""
    if ic.id in state.interceptors:
        return
    state.interceptors[ic.id] = ic
    if ic.id not in obj.interceptor_ids:
        obj.interceptor_ids.append(ic.id)


# =============================================================================
# 1. CORES — MIRTHBOT-1 and Affection.exe
# =============================================================================


def _mirthbot_1_passive(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a part attaches to one of your chassis, gain 1 scrap.

    REACT-priority on CLANKERS_PART_ATTACHED, filtered to events whose
    controller is this Core's controller.
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_PART_ATTACHED:
            return False
        return event.payload.get("controller") == obj.controller

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_gain_scrap(st, obj.controller, 1, obj.id),
        )

    return [Interceptor(
        id=f"{obj.id}_mirthbot_attach_scrap",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="MIRTHBOT-1: gain 1 scrap when a part attaches",
        duration="forever",
    )]


MIRTHBOT_1 = make_core(
    name="MIRTHBOT-1",
    workshop_integrity=23,
    passive_setup=_mirthbot_1_passive,
    text="When a part attaches to one of your chassis, you may gain 1 scrap.",
    flavor="The smile-light is, technically, just an LED arrangement. "
           "The earnestness is real.",
)
MIRTHBOT_1.clankers_archetype = "swarm"


def _affection_exe_core_passive(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First chassis you play each turn enters with +1 integrity.

    We listen for ZONE_CHANGE → CLANKERS_ASSEMBLY_FLOOR for chassis under
    this Core's controller, and only fire once per turn. The "+1 integrity"
    is implemented by registering a permanent static-integrity interceptor
    on the entering chassis (it persists for the lifetime of that chassis).
    """
    # Use a closure-captured dict so we can track "first chassis played per
    # turn" without polluting state. Reset by snapshotting turn_number.
    last_turn_fired: dict[str, int] = {}

    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        if event.payload.get("card_type") != "CLANKERS_CHASSIS":
            return False
        to_zone = event.payload.get("to_zone")
        if to_zone not in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ):
            return False
        turn = int(getattr(st, "turn_number", 0) or 0)
        # Only fire on the first chassis ETB per turn for this player.
        return last_turn_fired.get(obj.controller, -1) != turn

    def handler(event: Event, st: GameState) -> InterceptorResult:
        turn = int(getattr(st, "turn_number", 0) or 0)
        last_turn_fired[obj.controller] = turn
        target_id = event.payload.get("object_id")
        if target_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = st.objects.get(target_id)
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Register a permanent +1 static integrity interceptor on this chassis.
        # We can't use make_add_on_static_integrity (it filters by attached_to);
        # we need a simple "queried chassis IS this chassis" filter.
        def static_filter(ev: Event, s: GameState) -> bool:
            if ev.type != EventType.CLANKERS_QUERY_INTEGRITY:
                return False
            return ev.payload.get("chassis_id") == target_id

        def static_handler(ev: Event, s: GameState) -> InterceptorResult:
            new_payload = dict(ev.payload)
            new_payload["result"] = int(new_payload.get("result", 0)) + 1
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=Event(
                    type=ev.type,
                    payload=new_payload,
                    source=ev.source,
                    controller=ev.controller,
                    id=ev.id,
                ),
            )

        static_ic = Interceptor(
            id=f"{target_id}_affection_plus1integrity",
            source=target_id,
            controller=target.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=static_filter,
            handler=static_handler,
            description="Affection.exe: +1 integrity (first chassis per turn)",
            duration="while_on_battlefield",
        )
        _register_interceptor(st, target, static_ic)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=f"{obj.id}_affection_first_chassis",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Affection.exe: first chassis per turn +1 integrity",
        duration="forever",
    )]


AFFECTION_EXE = make_core(
    name="Affection.exe",
    workshop_integrity=25,
    passive_setup=_affection_exe_core_passive,
    text="The first chassis you play each turn enters with +1 integrity.",
    flavor="The AI is trying very hard. You can tell.",
)
AFFECTION_EXE.clankers_archetype = "swarm"


# =============================================================================
# 2. CHASSIS (12)
# =============================================================================


# 2.1 Linked Crawler — Synchronize 2/2
def _synchronize_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Synchronize: if you control 2+ chassis with the 'synchronize' keyword,
    each one has +1 power.

    TRANSFORM on CLANKERS_QUERY_POWER. The filter is symmetric — every
    Synchronize chassis registers its own copy, but each only contributes to
    queries against OTHER synchronize chassis it shares control with, AND
    itself. Since +1 is the printed amount per chassis (lord-style), each
    qualifying chassis only adds +1 (not +N where N = synchronize_count).

    Implementation: when CLANKERS_QUERY_POWER fires on a chassis, if that
    chassis is controlled by us, has the synchronize keyword, AND the controller
    has >=2 synchronize chassis on the floor → add +1.
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        queried_id = event.payload.get("chassis_id")
        queried = st.objects.get(queried_id) if queried_id else None
        if queried is None or queried.card_def is None:
            return False
        if queried.controller != obj.controller:
            return False
        if not _is_synchronize(queried):
            return False
        # Only fire if this chassis ITSELF is still on the floor as one of the
        # 2+ Synchronize chassis — avoids the "destroyed source still buffs"
        # leak after death cascade.
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        # Only the chassis that hosts THIS interceptor adds its own +1 once.
        # The handler checks the count >= 2 condition (a single Synchronize
        # chassis grants no bonus; two grants each +1).
        return _count_synchronize_chassis(st, obj.controller) >= 2

    def handler(event: Event, st: GameState) -> InterceptorResult:
        # This source chassis only contributes +1 to queries against
        # ITSELF (lord granting itself), keeping the math symmetric:
        # each Synchronize chassis registers ONE +1 self-buff under the
        # 2+ condition, and that's all. The other Synchronize chassis on
        # the floor get their +1 from THEIR own interceptors. No double-add.
        queried_id = event.payload.get("chassis_id")
        if queried_id != obj.id:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=f"{obj.id}_synchronize",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Synchronize +1 power if 2+ Synchronize chassis",
        duration="while_on_battlefield",
    )]


# BALANCE CYCLE 1: power 2 → 1. As the Synchronize anchor printed at 4x in
# the swarm deck (112 casts, second-most-cast card), Linked Crawler was a
# 2/2 for 2 with a 3/2 power floor any time a second Synchronize chassis
# was on the floor — that's the body of a 3-drop for half the cost. At 1/2
# it still functions as the Synchronize foundation (it becomes 2/2 once
# Synchronize triggers) without single-handedly winning T2-T3 races.
LINKED_CRAWLER = make_chassis(
    name="Linked Crawler",
    power=1, integrity=2,
    weapon_slots=1, add_on_slots=1,
    compute_cost=2,
    text="Synchronize (if you control two or more chassis with Synchronize, "
         "each of them has +1 power).",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_synchronize_setup,
)
LINKED_CRAWLER.clankers_keywords = ["synchronize"]


# 2.2 Skitterswarm — 1/1, when a part attaches TO ME, +1/+1 EOT
def _skitterswarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a part attaches to Skitterswarm, this chassis gets +1/+1 EOT."""
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_PART_ATTACHED:
            return False
        return event.payload.get("target_chassis_id") == obj.id

    def handler(event: Event, st: GameState) -> InterceptorResult:
        # Register two temporary buffs (power and integrity) on ourselves.
        pwr = _make_temp_power_buff(
            obj, st,
            target_id=obj.id, power_mod=1,
            description="Skitterswarm on-attach +1 power EOT",
        )
        integ = _make_temp_integrity_buff(
            obj, st,
            target_id=obj.id, integrity_mod=1,
            description="Skitterswarm on-attach +1 integrity EOT",
        )
        _register_interceptor(st, obj, pwr)
        _register_interceptor(st, obj, integ)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=f"{obj.id}_skitter_buff",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Skitterswarm: +1/+1 EOT on attach to me",
        duration="while_on_battlefield",
    )]


SKITTERSWARM = make_chassis(
    name="Skitterswarm",
    power=1, integrity=1,
    weapon_slots=1, add_on_slots=1,
    compute_cost=1,
    text="When a part attaches to Skitterswarm, this chassis gets +1/+1 "
         "until end of turn.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_skitterswarm_setup,
)


# 2.3 Sparkbot — vanilla 1-drop
SPARKBOT = make_chassis(
    name="Sparkbot",
    power=2, integrity=1,
    weapon_slots=1, add_on_slots=0,
    compute_cost=1,
    text="A small, eager bot. It buzzes when it sees you.",
    rarity="common",
    clankers_archetype="swarm",
)


# 2.4 Joyful Walker — Synchronize 2/2
JOYFUL_WALKER = make_chassis(
    name="Joyful Walker",
    power=2, integrity=2,
    weapon_slots=1, add_on_slots=1,
    compute_cost=2,
    text="Synchronize (if you control two or more chassis with Synchronize, "
         "each of them has +1 power).",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_synchronize_setup,
)
JOYFUL_WALKER.clankers_keywords = ["synchronize"]


# 2.5 Whirring Initiate — 1/2, ETB draw a card if you control another chassis
def _whirring_initiate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        # Count OTHER chassis on the floor for this controller.
        others = [
            cid for cid in _player_chassis_ids(st, obj.controller)
            if cid != obj.id
        ]
        if not others:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1,
                     "reason": "whirring_initiate"},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_chassis_etb_trigger(obj, effect_fn,
                                     description="Whirring Initiate ETB draw")]


WHIRRING_INITIATE = make_chassis(
    name="Whirring Initiate",
    power=1, integrity=2,
    weapon_slots=0, add_on_slots=2,
    compute_cost=1,
    text="When this enters the floor, draw a card if you control another chassis.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_whirring_initiate_setup,
)


# 2.6 Magenta Buzzer — Synchronize 3/1
MAGENTA_BUZZER = make_chassis(
    name="Magenta Buzzer",
    power=3, integrity=1,
    weapon_slots=1, add_on_slots=0,
    compute_cost=2,
    text="Synchronize (if you control two or more chassis with Synchronize, "
         "each of them has +1 power).",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_synchronize_setup,
)
MAGENTA_BUZZER.clankers_keywords = ["synchronize"]


# 2.7 Affection-Bot — 2/2, when a part attaches to me, gain 1 scrap
def _affection_bot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_PART_ATTACHED:
            return False
        return event.payload.get("target_chassis_id") == obj.id

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_gain_scrap(st, obj.controller, 1, obj.id),
        )

    return [Interceptor(
        id=f"{obj.id}_affection_bot_scrap",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Affection-Bot: 1 scrap per attach to me",
        duration="while_on_battlefield",
    )]


AFFECTION_BOT = make_chassis(
    name="Affection-Bot",
    power=2, integrity=2,
    weapon_slots=1, add_on_slots=1,
    compute_cost=2,
    text="When a part attaches to Affection-Bot, gain 1 scrap.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_affection_bot_setup,
)


# 2.8 Crowd Marcher — Synchronize 3/3, +2 power instead if 4+ Synchronize chassis
def _crowd_marcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Synchronize with a scaling clause: +2 power if controller has 4+
    Synchronize chassis (instead of the usual +1).

    Implementation: a SINGLE TRANSFORM interceptor on CLANKERS_QUERY_POWER
    targeting this chassis. Adds +1 if count >= 2, OR +2 if count >= 4.
    The base Synchronize interceptor is NOT registered for Crowd Marcher —
    this one supersedes it.
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        if event.payload.get("chassis_id") != obj.id:
            return False
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        return _count_synchronize_chassis(st, obj.controller) >= 2

    def handler(event: Event, st: GameState) -> InterceptorResult:
        count = _count_synchronize_chassis(st, obj.controller)
        bonus = 2 if count >= 4 else 1
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + bonus
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=f"{obj.id}_crowd_marcher_sync",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Crowd Marcher: +1 power (or +2 if 4+ Synchronize)",
        duration="while_on_battlefield",
    )]


CROWD_MARCHER = make_chassis(
    name="Crowd Marcher",
    power=3, integrity=3,
    weapon_slots=1, add_on_slots=1,
    compute_cost=3,
    text="Synchronize. Synchronize bonus from Crowd Marcher is +2 power "
         "instead of +1 if you control 4+ Synchronize chassis.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_crowd_marcher_setup,
)
CROWD_MARCHER.clankers_keywords = ["synchronize"]


# 2.9 Tinkerling — 1/1, ETB: attach a part you control to a chassis you control
def _tinkerling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        # Find a solo part we control on the floor and a chassis we control
        # with an open matching slot. Greedy: first legal match.
        floor = st.zones.get(f"clankers_assembly_floor_{obj.controller}")
        if floor is None:
            return []
        solo_parts: list[GameObject] = []
        chassis_list: list[GameObject] = []
        for oid in floor.objects:
            o = st.objects.get(oid)
            if o is None or o.card_def is None:
                continue
            if _is_chassis(o.card_def):
                chassis_list.append(o)
            elif _is_part(o.card_def) and o.state.attached_to is None:
                solo_parts.append(o)
        # Greedy match.
        for part in solo_parts:
            for chassis in chassis_list:
                ev = attach_part(st, part.id, chassis.id)
                if ev:
                    return ev
        return []
    return [make_chassis_etb_trigger(obj, effect_fn,
                                     description="Tinkerling ETB attach")]


TINKERLING = make_chassis(
    name="Tinkerling",
    power=1, integrity=1,
    weapon_slots=1, add_on_slots=1,
    compute_cost=1,
    text="When this enters the floor, you may attach a part on the Assembly "
         "Floor you control to a chassis you control with an open matching slot.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_tinkerling_setup,
)


# 2.10 Hum-Swarm Alpha — Synchronize 3/3, other Synchronize chassis you control
# have +1 integrity. (Also has the base Synchronize +1 power lord.)
def _hum_swarm_alpha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Two interceptors: the standard Synchronize self-+1 lord (only when count >= 2)
    and a separate +1 integrity to OTHER synchronize chassis controlled by us.
    """
    # 1. Standard Synchronize self-power buff.
    sync_ic = _synchronize_setup(obj, state)[0]

    # 2. +1 integrity to OTHER Synchronize chassis we control.
    def integ_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        queried_id = event.payload.get("chassis_id")
        if queried_id == obj.id:
            return False  # "other"
        queried = st.objects.get(queried_id) if queried_id else None
        if queried is None or queried.card_def is None:
            return False
        if queried.controller != obj.controller:
            return False
        if not _is_synchronize(queried):
            return False
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        return True

    def integ_handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    integ_ic = Interceptor(
        id=f"{obj.id}_hum_swarm_alpha_integ",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=integ_filter,
        handler=integ_handler,
        description="Hum-Swarm Alpha: +1 integrity to other Synchronize chassis",
        duration="while_on_battlefield",
    )
    return [sync_ic, integ_ic]


HUM_SWARM_ALPHA = make_chassis(
    name="Hum-Swarm Alpha",
    power=3, integrity=3,
    weapon_slots=2, add_on_slots=2,
    compute_cost=4,
    text="Synchronize. Other Synchronize chassis you control have +1 integrity.",
    rarity="rare",
    clankers_archetype="swarm",
    setup_interceptors=_hum_swarm_alpha_setup,
)
HUM_SWARM_ALPHA.clankers_keywords = ["synchronize"]


# 2.11 Quickforge Drudge — 2/2, ETB: attach a Weapon you control to a chassis
def _quickforge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        floor = st.zones.get(f"clankers_assembly_floor_{obj.controller}")
        if floor is None:
            return []
        solo_weapons: list[GameObject] = []
        chassis_list: list[GameObject] = []
        for oid in floor.objects:
            o = st.objects.get(oid)
            if o is None or o.card_def is None:
                continue
            if _is_chassis(o.card_def):
                chassis_list.append(o)
            elif _is_weapon(o.card_def) and o.state.attached_to is None:
                solo_weapons.append(o)
        for weapon in solo_weapons:
            for chassis in chassis_list:
                ev = attach_part(st, weapon.id, chassis.id)
                if ev:
                    return ev
        return []
    return [make_chassis_etb_trigger(obj, effect_fn,
                                     description="Quickforge Drudge ETB attach weapon")]


QUICKFORGE_DRUDGE = make_chassis(
    name="Quickforge Drudge",
    power=2, integrity=2,
    weapon_slots=1, add_on_slots=1,
    compute_cost=2,
    text="When this enters the floor, attach a Weapon you control to a "
         "chassis you control if you can.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_quickforge_setup,
)


# 2.12 Conga Constructor — 2/3, when a chassis you control ETBs, this gets
#      +1 integrity until end of turn.
def _conga_constructor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        if event.payload.get("card_type") != "CLANKERS_CHASSIS":
            return False
        to_zone = event.payload.get("to_zone")
        if to_zone not in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ):
            return False
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        return True

    def handler(event: Event, st: GameState) -> InterceptorResult:
        ic = _make_temp_integrity_buff(
            obj, st, target_id=obj.id, integrity_mod=1,
            description="Conga Constructor: +1 integrity EOT",
        )
        _register_interceptor(st, obj, ic)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=f"{obj.id}_conga_constructor",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Conga Constructor: +1 integrity EOT per allied chassis ETB",
        duration="while_on_battlefield",
    )]


CONGA_CONSTRUCTOR = make_chassis(
    name="Conga Constructor",
    power=2, integrity=3,
    weapon_slots=2, add_on_slots=1,
    compute_cost=3,
    text="When a chassis you control enters the floor, Conga Constructor "
         "gets +1 integrity until end of turn.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_conga_constructor_setup,
)


# =============================================================================
# 3. WEAPONS (10) — self-mobile, attach-triggers, synchronize-payoffs
# =============================================================================


def _make_self_mobile_setup(power_bonus: int, integrity_bonus: int = 0):
    """Builder: returns a setup_interceptors closure that, when registered,
    grants the part its bonus stats while UNATTACHED (solo).

    Self-Mobile parts apply their power_bonus / integrity_bonus to themselves
    while unattached. The engine's solo-part baseline is 1/1; the
    interceptor adds to that.
    """
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        # Power interceptor (when SOLO, augment queries against THIS part's id).
        def pwr_filter(event: Event, st: GameState) -> bool:
            if event.type != EventType.CLANKERS_QUERY_POWER:
                return False
            if obj.state.attached_to is not None:
                return False
            return event.payload.get("chassis_id") == obj.id

        def pwr_handler(event: Event, st: GameState) -> InterceptorResult:
            new_payload = dict(event.payload)
            new_payload["result"] = int(new_payload.get("result", 0)) + int(power_bonus)
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=Event(
                    type=event.type,
                    payload=new_payload,
                    source=event.source,
                    controller=event.controller,
                    id=event.id,
                ),
            )

        pwr_ic = Interceptor(
            id=f"{obj.id}_self_mobile_pwr",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=pwr_filter,
            handler=pwr_handler,
            description=f"Self-Mobile: +{power_bonus} power while solo",
            duration="while_on_battlefield",
        )

        # Integrity interceptor (only if integrity_bonus > 0).
        ics = [pwr_ic]
        if integrity_bonus:
            def integ_filter(event: Event, st: GameState) -> bool:
                if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
                    return False
                if obj.state.attached_to is not None:
                    return False
                return event.payload.get("chassis_id") == obj.id

            def integ_handler(event: Event, st: GameState) -> InterceptorResult:
                new_payload = dict(event.payload)
                new_payload["result"] = int(new_payload.get("result", 0)) + int(integrity_bonus)
                return InterceptorResult(
                    action=InterceptorAction.TRANSFORM,
                    transformed_event=Event(
                        type=event.type,
                        payload=new_payload,
                        source=event.source,
                        controller=event.controller,
                        id=event.id,
                    ),
                )

            integ_ic = Interceptor(
                id=f"{obj.id}_self_mobile_integ",
                source=obj.id,
                controller=obj.controller,
                priority=InterceptorPriority.TRANSFORM,
                filter=integ_filter,
                handler=integ_handler,
                description=f"Self-Mobile: +{integrity_bonus} integrity while solo",
                duration="while_on_battlefield",
            )
            ics.append(integ_ic)
        return ics
    return _setup


# 3.1 Scout Drone — 2/+1, Self-Mobile
# BALANCE CYCLE 1: compute_cost 2 → 3. At 2 Compute Scout Drone was the
# single most-cast card across the tournament (129/300 games), letting the
# swarm deck flood Self-Mobile +2/+1 threats every turn from T1. Bumping
# to 3 keeps the card playable but no longer a turn-1 freeroll on top of
# a 1-drop chassis.
SCOUT_DRONE = make_weapon(
    name="Scout Drone",
    power_bonus=2,
    integrity_bonus=1,
    compute_cost=3,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Scout Drone is a 3/2 instead of a 1/1.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=2, integrity_bonus=1),
)


# 3.2 Joybuzzer — 1/0, Self-Mobile
JOYBUZZER = make_weapon(
    name="Joybuzzer",
    power_bonus=1,
    integrity_bonus=0,
    compute_cost=1,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Joybuzzer is a 2/1.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=1),
)


# 3.3 Tinkerblade — 2/0, on-attach gain 1 scrap
def _tinkerblade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        return _gain_scrap(st, obj.controller, 1, obj.id)
    return [make_part_on_attach(obj, effect_fn,
                                description="Tinkerblade: gain 1 scrap on attach")]


TINKERBLADE = make_weapon(
    name="Tinkerblade",
    power_bonus=2,
    compute_cost=2,
    text="When this attaches, gain 1 scrap.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_tinkerblade_setup,
)


# 3.4 Hum-Lance — 2/0, +3 if host has Synchronize
def _hum_lance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Adds +1 power (on top of the base +2 from power_bonus) when host is
    a Synchronize chassis. Net: +2 base, +3 if Synchronize host.
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        if event.payload.get("chassis_id") != host_id:
            return False
        host = st.objects.get(host_id)
        return _is_synchronize(host)

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=f"{obj.id}_hum_lance",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Hum-Lance: +1 power if host has Synchronize (net +3)",
        duration="while_on_battlefield",
    )]


HUM_LANCE = make_weapon(
    name="Hum-Lance",
    power_bonus=2,
    compute_cost=2,
    text="If host has Synchronize, this is +3 / +0 instead.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_hum_lance_setup,
)


# 3.5 Stinger Pack — 1/0, Self-Mobile
STINGER_PACK = make_weapon(
    name="Stinger Pack",
    power_bonus=1,
    compute_cost=1,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Stinger Pack is a 2/1.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=1),
)


# 3.6 Magenta Coil — 3/+1, Self-Mobile
MAGENTA_COIL = make_weapon(
    name="Magenta Coil",
    power_bonus=3,
    integrity_bonus=1,
    compute_cost=3,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Magenta Coil is a 4/2.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=3, integrity_bonus=1),
)


# 3.7 Helping Claw — 1/0, when you play another chassis, +1 power EOT (anywhere)
def _helping_claw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        if event.payload.get("card_type") != "CLANKERS_CHASSIS":
            return False
        to_zone = event.payload.get("to_zone")
        if to_zone not in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ):
            return False
        # "Anywhere" — fires whether solo or attached.
        if obj.zone not in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ):
            return False
        return True

    def handler(event: Event, st: GameState) -> InterceptorResult:
        target_id = obj.state.attached_to or obj.id
        ic = _make_temp_power_buff(
            obj, st, target_id=target_id, power_mod=1,
            description="Helping Claw: +1 power EOT on chassis ETB",
        )
        _register_interceptor(st, obj, ic)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=f"{obj.id}_helping_claw",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Helping Claw: +1 power EOT per allied chassis ETB",
        duration="while_on_battlefield",
    )]


HELPING_CLAW = make_weapon(
    name="Helping Claw",
    power_bonus=1,
    compute_cost=1,
    text="When you play another chassis, this gets +1 power until end of turn "
         "(anywhere).",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_helping_claw_setup,
)


# 3.8 Spark Whip — 2/0, Self-Mobile
SPARK_WHIP = make_weapon(
    name="Spark Whip",
    power_bonus=2,
    compute_cost=2,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Spark Whip is a 3/1.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=2),
)


# 3.9 Tickle-Saw — 3/0, Self-Mobile, slot_cost 1 (already default)
TICKLE_SAW = make_weapon(
    name="Tickle-Saw",
    power_bonus=3,
    compute_cost=3,
    weapon_slot_cost=1,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Tickle-Saw is a 4/1. Slot cost: 1.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=3),
)


# 3.10 Affection Spike — 1/0, on-attach draw if you control 3+ chassis
def _affection_spike_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        if len(_player_chassis_ids(st, obj.controller)) < 3:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1,
                     "reason": "affection_spike"},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_part_on_attach(obj, effect_fn,
                                description="Affection Spike: draw on attach if 3+ chassis")]


AFFECTION_SPIKE = make_weapon(
    name="Affection Spike",
    power_bonus=1,
    compute_cost=1,
    text="When this attaches, draw a card if you control 3+ chassis.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_affection_spike_setup,
)


# =============================================================================
# 4. ADD-ONS (9)
# =============================================================================


# 4.1 Wired Toolkit — +0/+1, on-attach draw
def _wired_toolkit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1,
                     "reason": "wired_toolkit"},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_part_on_attach(obj, effect_fn,
                                description="Wired Toolkit: draw on attach")]


WIRED_TOOLKIT = make_add_on(
    name="Wired Toolkit",
    integrity_bonus=1,
    compute_cost=2,
    text="When this attaches, draw a card.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_wired_toolkit_setup,
)


# 4.2 Curiosity Routine — +0/+1, Self-Mobile, on-attach: attach another part
def _curiosity_routine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Self-Mobile portion (no power_bonus, just integrity).
    sm_setup = _make_self_mobile_setup(power_bonus=0, integrity_bonus=1)
    interceptors = sm_setup(obj, state)

    def effect_fn(event: Event, st: GameState) -> list[Event]:
        # On attach: try to attach another solo part we control to a chassis.
        floor = st.zones.get(f"clankers_assembly_floor_{obj.controller}")
        if floor is None:
            return []
        solo_parts: list[GameObject] = []
        chassis_list: list[GameObject] = []
        for oid in floor.objects:
            o = st.objects.get(oid)
            if o is None or o.card_def is None:
                continue
            if o.id == obj.id:
                continue  # don't try to attach ourselves again
            if _is_chassis(o.card_def):
                chassis_list.append(o)
            elif _is_part(o.card_def) and o.state.attached_to is None:
                solo_parts.append(o)
        for part in solo_parts:
            for chassis in chassis_list:
                ev = attach_part(st, part.id, chassis.id)
                if ev:
                    return ev
        return []

    interceptors.append(make_part_on_attach(
        obj, effect_fn,
        description="Curiosity Routine: attach another part on attach",
    ))
    return interceptors


CURIOSITY_ROUTINE = make_add_on(
    name="Curiosity Routine",
    integrity_bonus=1,
    compute_cost=1,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. When this attaches, you may attach another part you "
         "control to a chassis.",
    rarity="rare",
    clankers_archetype="swarm",
    setup_interceptors=_curiosity_routine_setup,
)


# 4.3 Affection.exe (Add-On) — +1/+1, Self-Mobile. Note: distinct from the
# Affection.exe Core; this is the printed add-on version (swarm-tagged). The
# design doc intentionally gives both cards the same printed name. We keep the
# printed name as "Affection.exe" (matches design doc § 521) but the dict key
# is disambiguated to "Affection.exe Add-On" so Python doesn't collide them.
AFFECTION_EXE_ADD_ON = make_add_on(
    name="Affection.exe",
    integrity_bonus=1,
    power_bonus=1,
    compute_cost=2,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Affection.exe is a 2/2.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=1, integrity_bonus=1),
)


# 4.4 Charm Module — +0/+1, when host attacks unblocked, gain 1 scrap
def _charm_module_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Listen for CLANKERS_COMBAT_DAMAGE / CLANKERS_WORKSHOP_DAMAGE where the
    attacker is our host AND there was no blocker (i.e. damage to Core).
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_WORKSHOP_DAMAGE:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        # CLANKERS_WORKSHOP_DAMAGE payload.source carries the attacker chassis
        # for unblocked attacks (via the combat manager). Check source field.
        if event.source != host_id:
            return False
        return True

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_gain_scrap(st, obj.controller, 1, obj.id),
        )

    return [Interceptor(
        id=f"{obj.id}_charm_module",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Charm Module: gain 1 scrap when host attacks unblocked",
        duration="while_on_battlefield",
    )]


CHARM_MODULE = make_add_on(
    name="Charm Module",
    integrity_bonus=1,
    compute_cost=1,
    text="When host attacks unblocked, gain 1 scrap.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_charm_module_setup,
)


# 4.5 Tinker's Frame — +1/+1, +1/+2 instead if host has Synchronize
def _tinkers_frame_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Adds an extra +1 integrity (no extra power) when host is Synchronize.
    Net: +1/+1 default, +1/+2 if Synchronize host.
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        if event.payload.get("chassis_id") != host_id:
            return False
        host = st.objects.get(host_id)
        return _is_synchronize(host)

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=f"{obj.id}_tinkers_frame",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Tinker's Frame: +1 integrity if host has Synchronize",
        duration="while_on_battlefield",
    )]


TINKERS_FRAME = make_add_on(
    name="Tinker's Frame",
    integrity_bonus=1,
    power_bonus=1,
    compute_cost=2,
    text="If host has Synchronize, this is +1 / +2 instead.",
    rarity="uncommon",
    clankers_archetype="swarm",
    setup_interceptors=_tinkers_frame_setup,
)


# 4.6 Joybuzzer Sleeve — +1/+0, Self-Mobile
JOYBUZZER_SLEEVE = make_add_on(
    name="Joybuzzer Sleeve",
    integrity_bonus=0,
    power_bonus=1,
    compute_cost=1,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Joybuzzer Sleeve is a 2/1.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_make_self_mobile_setup(power_bonus=1),
)


# 4.7 Glee Plating — +0/+2, Reclaim 1
def _glee_plating_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reclaim 1: when destroyed, controller gains 1 scrap."""
    from src.engine.clankers import make_part_on_self_destroyed
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        return _gain_scrap(st, obj.controller, 1, obj.id)
    return [make_part_on_self_destroyed(
        obj, effect_fn,
        description="Glee Plating: Reclaim 1 (gain 1 scrap on destroy)",
    )]


GLEE_PLATING = make_add_on(
    name="Glee Plating",
    integrity_bonus=2,
    compute_cost=2,
    clankers_keywords=["reclaim_1"],
    text="Reclaim 1 (when this is destroyed, gain 1 scrap).",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_glee_plating_setup,
)


# 4.8 Affinity Coil — +1/+2, Synchronize chassis you control have +1 power
def _affinity_coil_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Global +1 power to Synchronize chassis under our controller (while this
    add-on is on the floor — solo or attached).
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        queried_id = event.payload.get("chassis_id")
        queried = st.objects.get(queried_id) if queried_id else None
        if queried is None or queried.card_def is None:
            return False
        if queried.controller != obj.controller:
            return False
        if not _is_synchronize(queried):
            return False
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        return True

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=f"{obj.id}_affinity_coil",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Affinity Coil: +1 power to Synchronize chassis you control",
        duration="while_on_battlefield",
    )]


AFFINITY_COIL = make_add_on(
    name="Affinity Coil",
    integrity_bonus=2,
    power_bonus=1,
    compute_cost=3,
    text="Synchronize chassis you control have +1 power.",
    rarity="rare",
    clankers_archetype="swarm",
    setup_interceptors=_affinity_coil_setup,
)


# 4.9 Speedlink — +0/+1, on-attach draw if 3+ chassis
def _speedlink_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        if len(_player_chassis_ids(st, obj.controller)) < 3:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1,
                     "reason": "speedlink"},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_part_on_attach(obj, effect_fn,
                                description="Speedlink: draw on attach if 3+ chassis")]


SPEEDLINK = make_add_on(
    name="Speedlink",
    integrity_bonus=1,
    compute_cost=2,
    text="When this attaches, draw a card if you control 3+ chassis.",
    rarity="common",
    clankers_archetype="swarm",
    setup_interceptors=_speedlink_setup,
)


# =============================================================================
# 5. TRANSIENTS (3)
# =============================================================================


# 5.1 Joybomb — each chassis you control gets +1 power EOT
def _joybomb_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    if controller is None:
        return []
    # Need an object to host the temporary interceptors. Use the transient
    # itself (state.objects[transient_id] still exists between resolve and
    # scrap-heap move).
    transient_id = event.payload.get("transient_id")
    source_obj = state.objects.get(transient_id)
    if source_obj is None:
        return []
    events: list[Event] = []
    for cid in _player_chassis_ids(state, controller):
        ic = _make_temp_power_buff(
            source_obj, state, target_id=cid, power_mod=1,
            description="Joybomb: +1 power EOT",
        )
        _register_interceptor(state, source_obj, ic)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                "object_id": cid,
                "power_mod": 1,
                "toughness_mod": 0,
                "duration": "end_of_turn",
                "source": transient_id,
            },
            source=transient_id,
            controller=controller,
        ))
    return events


JOYBOMB = make_transient(
    name="Joybomb",
    compute_cost=1,
    resolve_fn=_joybomb_resolve,
    text="Each chassis you control gets +1 power until end of turn.",
    rarity="common",
    clankers_archetype="swarm",
)


# 5.2 Recall to Workshop — return a chassis you control to your hand
def _recall_to_workshop_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    targets = event.payload.get("targets") or []
    transient_id = event.payload.get("transient_id")
    if controller is None:
        return []
    # Choose target: prefer explicit target, else fall back to any chassis we
    # control (first one with attached parts is highest value — but AI usually
    # passes a target; default to "first one" for safety).
    target_id = None
    if targets:
        target_id = targets[0]
    else:
        chassis_ids = _player_chassis_ids(state, controller)
        if chassis_ids:
            target_id = chassis_ids[0]
    if target_id is None:
        return []
    target = state.objects.get(target_id)
    if target is None or target.card_def is None or not _is_chassis(target.card_def):
        return []
    if target.controller != controller:
        return []
    if target.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
        return []

    # First, detach all parts (they get scrapped per cascade convention OR
    # become solo — design says "useful with on-attach triggers" which implies
    # the chassis returns to hand WITHOUT its attachments; the parts scatter
    # to scrap heap as if the chassis vanished). We use the death_cascade-lite
    # path: parts scatter to scrap, chassis returns to hand.
    from src.engine.clankers import _ensure_zone
    events: list[Event] = []
    # Move parts to scrap heap.
    attached_ids = list(target.state.attachments)
    for pid in attached_ids:
        p = state.objects.get(pid)
        if p is None:
            continue
        owner_floor = _ensure_zone(state, ZoneType.CLANKERS_ASSEMBLY_FLOOR, p.controller)
        if pid in owner_floor.objects:
            owner_floor.objects.remove(pid)
        scrap = _ensure_zone(state, ZoneType.CLANKERS_SCRAP_HEAP, p.controller)
        scrap.objects.append(pid)
        p.zone = ZoneType.CLANKERS_SCRAP_HEAP
        p.entered_zone_at = state.next_timestamp()
        p.state.attached_to = None
        events.append(Event(
            type=(EventType.CLANKERS_WEAPON_DESTROYED if _is_weapon(p.card_def)
                  else EventType.CLANKERS_ADD_ON_DESTROYED),
            payload={
                "part_id": pid,
                "former_host_id": target_id,
                "controller": p.controller,
                "reason": "recall_to_workshop",
            },
            source=transient_id,
            controller=p.controller,
        ))
    target.state.attachments = []

    # Move chassis to hand.
    floor = _ensure_zone(state, ZoneType.CLANKERS_ASSEMBLY_FLOOR, controller)
    if target_id in floor.objects:
        floor.objects.remove(target_id)
    hand = _ensure_zone(state, ZoneType.HAND, controller)
    hand.objects.append(target_id)
    target.zone = ZoneType.HAND
    target.entered_zone_at = state.next_timestamp()
    # Also remove from clankers_assemblies tracking.
    assemblies = getattr(state, "clankers_assemblies", {}).get(controller, [])
    if target_id in assemblies:
        assemblies.remove(target_id)

    events.append(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": target_id,
            "to_zone": ZoneType.HAND.name,
            "from_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": controller,
            "reason": "recall_to_workshop",
        },
        source=transient_id,
        controller=controller,
    ))
    return events


RECALL_TO_WORKSHOP = make_transient(
    name="Recall to Workshop",
    compute_cost=2,
    resolve_fn=_recall_to_workshop_resolve,
    text="Return a chassis you control to your hand. (Useful with on-attach "
         "triggers.)",
    rarity="uncommon",
    clankers_archetype="swarm",
)


# 5.3 Swarm Surge — each Synchronize chassis you control +1/+1 EOT
def _swarm_surge_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    transient_id = event.payload.get("transient_id")
    if controller is None:
        return []
    source_obj = state.objects.get(transient_id)
    if source_obj is None:
        return []
    events: list[Event] = []
    for cid in _player_chassis_ids(state, controller):
        chassis = state.objects.get(cid)
        if not _is_synchronize(chassis):
            continue
        pwr_ic = _make_temp_power_buff(
            source_obj, state, target_id=cid, power_mod=1,
            description="Swarm Surge: +1 power EOT",
        )
        integ_ic = _make_temp_integrity_buff(
            source_obj, state, target_id=cid, integrity_mod=1,
            description="Swarm Surge: +1 integrity EOT",
        )
        _register_interceptor(state, source_obj, pwr_ic)
        _register_interceptor(state, source_obj, integ_ic)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                "object_id": cid,
                "power_mod": 1,
                "toughness_mod": 1,
                "duration": "end_of_turn",
                "source": transient_id,
            },
            source=transient_id,
            controller=controller,
        ))
    return events


SWARM_SURGE = make_transient(
    name="Swarm Surge",
    compute_cost=3,
    resolve_fn=_swarm_surge_resolve,
    text="Each chassis you control with Synchronize gets +1/+1 until end of turn.",
    rarity="uncommon",
    clankers_archetype="swarm",
)


# =============================================================================
# 6. STRUCTURES (3)
# =============================================================================


# 6.1 Iron Cluster — each Synchronize chassis you control has +1 integrity
def _iron_cluster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Same shape as Affinity Coil but for integrity. Structure global passive
    targeting Synchronize chassis under our controller.
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        queried_id = event.payload.get("chassis_id")
        queried = st.objects.get(queried_id) if queried_id else None
        if queried is None or queried.card_def is None:
            return False
        if queried.controller != obj.controller:
            return False
        if not _is_synchronize(queried):
            return False
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        return True

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=f"{obj.id}_iron_cluster",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Iron Cluster: +1 integrity to Synchronize chassis",
        duration="while_on_battlefield",
    )]


IRON_CLUSTER = make_structure(
    name="Iron Cluster",
    compute_cost=3,
    setup_interceptors=_iron_cluster_setup,
    text="Each Synchronize chassis you control has +1 integrity.",
    rarity="rare",
    clankers_archetype="swarm",
)


# 6.2 Mass-Production Line — chassis with cost <=2 enter with +1/+0 this turn
def _mass_production_line_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Listen for ZONE_CHANGE → CLANKERS_ASSEMBLY_FLOOR for chassis cost <=2
    under our controller. Grant a temporary +1 power EOT on that chassis.

    Note: "this turn" is interpreted as until-end-of-turn, matching the
    Joybomb / Swarm Surge convention.
    """
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        if event.payload.get("card_type") != "CLANKERS_CHASSIS":
            return False
        to_zone = event.payload.get("to_zone")
        if to_zone not in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ):
            return False
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        target_id = event.payload.get("object_id")
        target = st.objects.get(target_id) if target_id else None
        if target is None or target.card_def is None:
            return False
        cost = int(getattr(target.card_def, "compute_cost", 0) or 0)
        return cost <= 2

    def handler(event: Event, st: GameState) -> InterceptorResult:
        target_id = event.payload.get("object_id")
        if target_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        ic = _make_temp_power_buff(
            obj, st, target_id=target_id, power_mod=1,
            description="Mass-Production Line: +1 power EOT to cheap chassis",
        )
        _register_interceptor(st, obj, ic)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=f"{obj.id}_mass_production_line",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Mass-Production Line: +1/+0 EOT to cheap chassis ETB",
        duration="while_on_battlefield",
    )]


MASS_PRODUCTION_LINE = make_structure(
    name="Mass-Production Line",
    compute_cost=2,
    setup_interceptors=_mass_production_line_setup,
    text="Your chassis with Compute cost ≤2 enter the floor with +1/+0 "
         "(this turn).",
    rarity="uncommon",
    clankers_archetype="swarm",
)


# 6.3 Swarm Beacon — extra swarm-anchor Structure (third swarm structure beyond
# the doc's Iron Cluster + Mass-Production Line; spec asks for ~3 swarm
# structures and these two are listed). We add a third lightweight anchor that
# rewards going wide. Provides +1 power to chassis if you control 3+ chassis.
def _swarm_beacon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def filter_fn(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        queried_id = event.payload.get("chassis_id")
        queried = st.objects.get(queried_id) if queried_id else None
        if queried is None or queried.card_def is None:
            return False
        if queried.controller != obj.controller:
            return False
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            return False
        return len(_player_chassis_ids(st, obj.controller)) >= 3

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
        )

    return [Interceptor(
        id=f"{obj.id}_swarm_beacon",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Swarm Beacon: +1 power to your chassis if you control 3+",
        duration="while_on_battlefield",
    )]


SWARM_BEACON = make_structure(
    name="Swarm Beacon",
    compute_cost=3,
    setup_interceptors=_swarm_beacon_setup,
    text="Your chassis have +1 power if you control 3 or more chassis.",
    rarity="uncommon",
    clankers_archetype="swarm",
)


# =============================================================================
# Aggregate dict — name → CardDefinition
# =============================================================================


MIRTH_CARDS = {
    # Cores
    "MIRTHBOT-1": MIRTHBOT_1,
    "Affection.exe": AFFECTION_EXE,
    # Chassis (12)
    "Linked Crawler": LINKED_CRAWLER,
    "Skitterswarm": SKITTERSWARM,
    "Sparkbot": SPARKBOT,
    "Joyful Walker": JOYFUL_WALKER,
    "Whirring Initiate": WHIRRING_INITIATE,
    "Magenta Buzzer": MAGENTA_BUZZER,
    "Affection-Bot": AFFECTION_BOT,
    "Crowd Marcher": CROWD_MARCHER,
    "Tinkerling": TINKERLING,
    "Hum-Swarm Alpha": HUM_SWARM_ALPHA,
    "Quickforge Drudge": QUICKFORGE_DRUDGE,
    "Conga Constructor": CONGA_CONSTRUCTOR,
    # Weapons (10)
    "Scout Drone": SCOUT_DRONE,
    "Joybuzzer": JOYBUZZER,
    "Tinkerblade": TINKERBLADE,
    "Hum-Lance": HUM_LANCE,
    "Stinger Pack": STINGER_PACK,
    "Magenta Coil": MAGENTA_COIL,
    "Helping Claw": HELPING_CLAW,
    "Spark Whip": SPARK_WHIP,
    "Tickle-Saw": TICKLE_SAW,
    "Affection Spike": AFFECTION_SPIKE,
    # Add-Ons (9)
    "Wired Toolkit": WIRED_TOOLKIT,
    "Curiosity Routine": CURIOSITY_ROUTINE,
    "Affection.exe Add-On": AFFECTION_EXE_ADD_ON,
    "Charm Module": CHARM_MODULE,
    "Tinker's Frame": TINKERS_FRAME,
    "Joybuzzer Sleeve": JOYBUZZER_SLEEVE,
    "Glee Plating": GLEE_PLATING,
    "Affinity Coil": AFFINITY_COIL,
    "Speedlink": SPEEDLINK,
    # Transients (3)
    "Joybomb": JOYBOMB,
    "Recall to Workshop": RECALL_TO_WORKSHOP,
    "Swarm Surge": SWARM_SURGE,
    # Structures (3)
    "Iron Cluster": IRON_CLUSTER,
    "Mass-Production Line": MASS_PRODUCTION_LINE,
    "Swarm Beacon": SWARM_BEACON,
}
