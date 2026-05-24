"""CLAN — ETHOS-7 archetype (Cycle Subroutines / control).

~36 cards: 2 Cores (ETHOS-7, SUBROUTINE-α), 8 Chassis, 8 Weapons, 9 Add-Ons,
6 Transients, 3 Structures. Control wants lots of Transients, card draw, and
scrap-heap recursion. Few chassis but they stay alive a long time.

Notes on engine plumbing used here:
- Cost-reduction for "first Transient costs 1 less" is a TRANSFORM interceptor
  on CLANKERS_COMPUTE_SPEND filtered by source-card type. The interceptor
  reduces the actual amount deducted; the affordability check in
  play_card_from_hand uses the printed cost (engine limitation noted in
  contract).
- Scrap heap zone key: ``clankers_scrap_heap_<player_id>``.
- Per-turn tokens (e.g. SUBROUTINE-α scrap-once-per-turn, Heuristic Layer
  once-per-turn) live on flat ``state.clankers_clan_ethos_*`` dicts keyed
  by player_id; reset by REACT interceptor on CLANKERS_TURN_START.
- "When a Transient you control resolves" triggers off
  EventType.CLANKERS_COMPUTE_SPEND with a ``transient_id`` in the payload
  (the synthetic event _play_transient emits). Other COMPUTE_SPEND events
  don't carry that key, so the filter is unambiguous.
"""

from __future__ import annotations

from typing import Optional

from src.engine import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    new_id,
)
from src.engine.types import CardType, ZoneType
from src.engine.clankers import (
    _gain_scrap,
    _is_transient,
    _is_weapon,
    make_add_on,
    make_add_on_static_integrity,
    make_add_on_static_power,
    make_armor,
    make_chassis,
    make_chassis_etb_trigger,
    make_core,
    make_core_passive,
    make_part_on_attach,
    make_part_on_host_attack,
    make_part_on_self_destroyed,
    make_structure,
    make_structure_global,
    make_transient,
    make_weapon,
    make_weapon_activated,
)


# =============================================================================
# Local helpers / per-turn state
# =============================================================================

def _ensure_ethos_state(state: GameState) -> None:
    """Initialise the per-turn flags we use across this file. Idempotent."""
    if not hasattr(state, "clankers_clan_ethos_first_transient_used"):
        state.clankers_clan_ethos_first_transient_used = {}  # type: ignore[attr-defined]
    if not hasattr(state, "clankers_clan_ethos_transients_this_turn"):
        state.clankers_clan_ethos_transients_this_turn = {}  # type: ignore[attr-defined]
    if not hasattr(state, "clankers_clan_ethos_heuristic_layer_used"):
        state.clankers_clan_ethos_heuristic_layer_used = {}  # type: ignore[attr-defined]
    if not hasattr(state, "clankers_clan_ethos_subroutine_alpha_used"):
        state.clankers_clan_ethos_subroutine_alpha_used = {}  # type: ignore[attr-defined]
    if not hasattr(state, "clankers_clan_ethos_cascade_uses"):
        state.clankers_clan_ethos_cascade_uses = {}  # type: ignore[attr-defined]


def _scrap_heap_objs(state: GameState, player_id: str) -> list[GameObject]:
    """Return the GameObjects currently in player_id's scrap heap."""
    zone_key = f"clankers_scrap_heap_{player_id}"
    zone = state.zones.get(zone_key)
    if zone is None:
        return []
    out: list[GameObject] = []
    for oid in zone.objects:
        obj = state.objects.get(oid)
        if obj is not None:
            out.append(obj)
    return out


def _count_transients_in_scrap(state: GameState, player_id: str) -> int:
    return sum(
        1 for obj in _scrap_heap_objs(state, player_id)
        if obj.card_def is not None and _is_transient(obj.card_def)
    )


def _first_transient_in_scrap(state: GameState, player_id: str) -> Optional[GameObject]:
    for obj in _scrap_heap_objs(state, player_id):
        if obj.card_def is not None and _is_transient(obj.card_def):
            return obj
    return None


def _is_transient_resolution_event(event: Event) -> bool:
    """Detect the synthetic event emitted by _play_transient.

    _play_transient reuses CLANKERS_COMPUTE_SPEND but carries ``transient_id``
    in payload; the normal compute-spend event has ``source_card_id`` only.
    """
    if event.type != EventType.CLANKERS_COMPUTE_SPEND:
        return False
    return event.payload.get("transient_id") is not None


def _return_to_hand(state: GameState, obj: GameObject) -> list[Event]:
    """Move ``obj`` from scrap heap back to its owner's hand. Emits ZONE_CHANGE."""
    owner = obj.controller
    src_key = f"clankers_scrap_heap_{owner}"
    src_zone = state.zones.get(src_key)
    if src_zone is not None and obj.id in src_zone.objects:
        src_zone.objects.remove(obj.id)
    hand_key = f"hand_{owner}"
    hand_zone = state.zones.get(hand_key)
    if hand_zone is not None and obj.id not in hand_zone.objects:
        hand_zone.objects.append(obj.id)
    obj.zone = ZoneType.HAND
    obj.entered_zone_at = state.next_timestamp()
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "to_zone": ZoneType.HAND.name,
            "from_zone": ZoneType.CLANKERS_SCRAP_HEAP.name,
            "controller": owner,
            "reason": "clan_ethos_recursion",
        },
        source=obj.id,
        controller=owner,
    )]


def _pt_boost_eot(obj: GameObject, *, power: int = 0, integrity: int = 0) -> list[Event]:
    """Emit a generic PT_MODIFICATION event valid through end-of-turn."""
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={
            "object_id": obj.id,
            "power_mod": int(power),
            "toughness_mod": int(integrity),
            "duration": "end_of_turn",
        },
        source=obj.id,
        controller=obj.controller,
    )]


# =============================================================================
# Cores
# =============================================================================

def ethos_7_passive_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETHOS-7: the first Transient you play each turn costs 1 less Compute (min 0).

    Implemented as a TRANSFORM-priority interceptor on CLANKERS_COMPUTE_SPEND
    that filters on (a) controller matches the core's owner, and (b) the
    source card is a Transient. The first matching spend per turn deducts
    one from ``payload['amount']``; subsequent spends pass through.

    Also installs a REACT interceptor on CLANKERS_TURN_START that resets the
    per-player flag.
    """
    _ensure_ethos_state(state)

    def discount_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_COMPUTE_SPEND:
            return False
        if event.payload.get("player_id") != obj.controller:
            return False
        src_id = event.payload.get("source_card_id")
        if src_id is None:
            return False
        src_obj = st.objects.get(src_id)
        if src_obj is None or src_obj.card_def is None:
            return False
        if not _is_transient(src_obj.card_def):
            return False
        used_map = getattr(st, "clankers_clan_ethos_first_transient_used", {}) or {}
        return not used_map.get(obj.controller, False)

    def discount_handler(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        new_payload = dict(event.payload)
        amt = int(new_payload.get("amount", 0))
        new_amt = max(0, amt - 1)
        new_payload["amount"] = new_amt
        new_payload["ethos_discount_applied"] = 1
        st.clankers_clan_ethos_first_transient_used[obj.controller] = True  # type: ignore[attr-defined]
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

    discount_ic = Interceptor(
        id=f"{obj.id}_ethos7_discount",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=discount_filter,
        handler=discount_handler,
        description="ETHOS-7: first Transient costs 1 less",
        duration="forever",
    )

    def reset_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_TURN_START:
            return False
        return event.payload.get("player") == obj.controller

    def reset_handler(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        st.clankers_clan_ethos_first_transient_used[obj.controller] = False  # type: ignore[attr-defined]
        return InterceptorResult(action=InterceptorAction.PASS)

    reset_ic = Interceptor(
        id=f"{obj.id}_ethos7_reset",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=reset_filter,
        handler=reset_handler,
        description="ETHOS-7: reset first-Transient flag at turn start",
        duration="forever",
    )

    return [discount_ic, reset_ic]


ETHOS_7 = make_core(
    name="ETHOS-7",
    workshop_integrity=22,
    passive_setup=ethos_7_passive_setup,
    text="The first Transient you play each turn costs 1 less Compute (min 0).",
    flavor=(
        "ETHOS-7 reads the manual cover-to-cover before doing anything else, "
        "then quietly underlines the most efficient subroutine."
    ),
)
ETHOS_7.clankers_archetype = "control"


def subroutine_alpha_passive_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """SUBROUTINE-α: at the start of your Reassemble phase, you may scrap a
    card from your hand. If you do, gain 2 Compute this turn only.

    Filter on PHASE_START with phase == 'reassemble' and player == controller.
    For Stage-1 we always auto-take the discount when there is a card to scrap
    (no UI affordance for the optional decline yet). We pick the first card
    in hand — the heuristic AI doesn't have a "which card to scrap" choice
    function yet; future tuning can prefer dead Transients.
    """
    _ensure_ethos_state(state)

    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get("phase") != "reassemble":
            return False
        if event.payload.get("player") != obj.controller:
            return False
        used_map = getattr(st, "clankers_clan_ethos_subroutine_alpha_used", {}) or {}
        return not used_map.get(obj.controller, False)

    def hand(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        owner = obj.controller
        hand_zone = st.zones.get(f"hand_{owner}")
        if hand_zone is None or not hand_zone.objects:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Scrap the first card in hand (oldest / drawn-earliest).
        scrap_id = hand_zone.objects[0]
        scrap_obj = st.objects.get(scrap_id)
        if scrap_obj is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        hand_zone.objects.remove(scrap_id)
        scrap_zone_key = f"clankers_scrap_heap_{owner}"
        scrap_zone = st.zones.get(scrap_zone_key)
        if scrap_zone is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        scrap_zone.objects.append(scrap_id)
        scrap_obj.zone = ZoneType.CLANKERS_SCRAP_HEAP
        scrap_obj.entered_zone_at = st.next_timestamp()

        # Mark the per-turn token used (cleared at TURN_START).
        st.clankers_clan_ethos_subroutine_alpha_used[owner] = True  # type: ignore[attr-defined]

        # Grant +2 Compute this turn only (above-cap, won't bank).
        pool = getattr(st, "clankers_compute_pool", {}) or {}
        cur = int(pool.get(owner, 0))
        pool[owner] = cur + 2
        st.clankers_compute_pool = pool  # type: ignore[attr-defined]

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        "object_id": scrap_id,
                        "to_zone": ZoneType.CLANKERS_SCRAP_HEAP.name,
                        "from_zone": ZoneType.HAND.name,
                        "controller": owner,
                        "reason": "subroutine_alpha_scrap",
                    },
                    source=obj.id,
                    controller=owner,
                ),
                Event(
                    type=EventType.CLANKERS_COMPUTE_GAIN,
                    payload={
                        "player_id": owner,
                        "amount": 2,
                        "reason": "subroutine_alpha",
                    },
                    source=obj.id,
                    controller=owner,
                ),
                Event(
                    type=EventType.CLANKERS_CORE_PASSIVE,
                    payload={"core_id": obj.id, "name": "SUBROUTINE-α"},
                    source=obj.id,
                    controller=owner,
                ),
            ],
        )

    burst_ic = Interceptor(
        id=f"{obj.id}_subalpha_burst",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=hand,
        description="SUBROUTINE-α: scrap hand card → +2 Compute this Reassemble",
        duration="forever",
    )

    def reset_filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_TURN_START:
            return False
        return event.payload.get("player") == obj.controller

    def reset_handler(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        st.clankers_clan_ethos_subroutine_alpha_used[obj.controller] = False  # type: ignore[attr-defined]
        return InterceptorResult(action=InterceptorAction.PASS)

    reset_ic = Interceptor(
        id=f"{obj.id}_subalpha_reset",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=reset_filt,
        handler=reset_handler,
        description="SUBROUTINE-α: reset per-turn token",
        duration="forever",
    )

    return [burst_ic, reset_ic]


SUBROUTINE_ALPHA = make_core(
    name="SUBROUTINE-α",
    workshop_integrity=24,
    passive_setup=subroutine_alpha_passive_setup,
    text=(
        "At the start of your Reassemble phase, you may scrap a card from "
        "your hand. If you do, gain 2 Compute this turn only."
    ),
    flavor=(
        "SUBROUTINE-α edits its own source code in real time. Half the "
        "panels are open at any given moment."
    ),
)
SUBROUTINE_ALPHA.clankers_archetype = "control"


# =============================================================================
# Chassis (8)
# =============================================================================

# BALANCE CYCLE 1: integrity 5 → 6. As ETHOS's only real tank (printed at
# 4x and most-cast control chassis at 88 casts), Bulwark Frame on integrity 5
# was getting one-shot by MIRTH's Synchronize-Crawler-with-attached-weapon
# pressure before the Containment Lattice add-ons could stack. Bumping to
# 6 lets it actually live through one combat without immediate add-on
# investment — directly addresses ETHOS's "tank can't hold" complaint.
BULWARK_FRAME = make_chassis(
    name="Bulwark Frame",
    power=3, integrity=6,
    weapon_slots=1, add_on_slots=4,
    compute_cost=4,
    text="A patient tank with deep add-on stacking.",
    rarity="common",
    clankers_archetype="control",
)


def subroutine_core_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Subroutine Core: when you play a Transient, this gets +1 power until EOT."""
    def filt(event: Event, st: GameState) -> bool:
        if not _is_transient_resolution_event(event):
            return False
        return event.payload.get("controller") == obj.controller

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_pt_boost_eot(obj, power=1),
        )

    return [Interceptor(
        id=f"{obj.id}_subroutine_core_trans",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Subroutine Core: +1 power on Transient cast (EOT)",
    )]


SUBROUTINE_CORE = make_chassis(
    name="Subroutine Core",
    power=2, integrity=4,
    weapon_slots=1, add_on_slots=3,
    compute_cost=3,
    text="When you play a Transient, this gets +1 power until end of turn.",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=subroutine_core_setup,
)


def loop_engine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Loop Engine: at start of your Reassemble phase, if you played a
    Transient this turn, draw a card.
    """
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get("phase") != "reassemble":
            return False
        if event.payload.get("player") != obj.controller:
            return False
        counters = getattr(st, "clankers_clan_ethos_transients_this_turn", {}) or {}
        return int(counters.get(obj.controller, 0)) > 0

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "loop_engine"},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=f"{obj.id}_loop_engine",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Loop Engine: Reassemble-phase draw if Transient played",
    )]


LOOP_ENGINE = make_chassis(
    name="Loop Engine",
    power=4, integrity=5,
    weapon_slots=1, add_on_slots=3,
    compute_cost=5,
    text=(
        "At the start of your Reassemble phase, if you played a Transient "
        "this turn, draw a card."
    ),
    rarity="rare",
    clankers_archetype="control",
    setup_interceptors=loop_engine_setup,
)


def heuristic_sentry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enters the floor, you may scrap a card from your hand to draw a card.

    Stage-1 implementation: always take the trade if hand has at least one
    non-self card. Picks the first eligible hand card (mirrors the
    SUBROUTINE-α "scrap first card" heuristic).
    """
    def etb(event: Event, st: GameState) -> list[Event]:
        owner = obj.controller
        hand_zone = st.zones.get(f"hand_{owner}")
        if hand_zone is None:
            return []
        # Skip self in the lookup just in case ETB fires before the zone
        # move; defensively pick the first OTHER card.
        candidates = [oid for oid in hand_zone.objects if oid != obj.id]
        if not candidates:
            return []
        scrap_id = candidates[0]
        scrap_obj = st.objects.get(scrap_id)
        if scrap_obj is None:
            return []
        hand_zone.objects.remove(scrap_id)
        scrap_zone = st.zones.get(f"clankers_scrap_heap_{owner}")
        if scrap_zone is None:
            return []
        scrap_zone.objects.append(scrap_id)
        scrap_obj.zone = ZoneType.CLANKERS_SCRAP_HEAP
        scrap_obj.entered_zone_at = st.next_timestamp()
        return [
            Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": scrap_id,
                    "to_zone": ZoneType.CLANKERS_SCRAP_HEAP.name,
                    "from_zone": ZoneType.HAND.name,
                    "controller": owner,
                    "reason": "heuristic_sentry_etb",
                },
                source=obj.id,
                controller=owner,
            ),
            Event(
                type=EventType.DRAW,
                payload={"player": owner, "count": 1, "reason": "heuristic_sentry"},
                source=obj.id,
                controller=owner,
            ),
        ]
    return [make_chassis_etb_trigger(obj, etb, description="Heuristic Sentry ETB")]


HEURISTIC_SENTRY = make_chassis(
    name="Heuristic Sentry",
    power=1, integrity=3,
    weapon_slots=1, add_on_slots=2,
    compute_cost=2,
    text="When this enters the floor, you may scrap a card from your hand to draw a card.",
    rarity="common",
    clankers_archetype="control",
    setup_interceptors=heuristic_sentry_setup,
)


def long_memory_husk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reclaim 2 — when this chassis is destroyed, gain 2 scrap.

    Chassis-style reclaim: filter on CLANKERS_CHASSIS_DESTROYED matching self.
    """
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_CHASSIS_DESTROYED:
            return False
        return event.payload.get("chassis_id") == obj.id

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_gain_scrap(st, obj.controller, 2, obj.id),
        )

    return [Interceptor(
        id=f"{obj.id}_long_memory_husk_reclaim",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Long-Memory Husk: Reclaim 2",
    )]


LONG_MEMORY_HUSK = make_chassis(
    name="Long-Memory Husk",
    power=2, integrity=6,
    weapon_slots=1, add_on_slots=4,
    compute_cost=4,
    text="Reclaim 2 (when this is destroyed, gain 2 scrap).",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=long_memory_husk_setup,
)


def recursive_sentinel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Recursive Sentinel: when a Transient you control resolves, +1 power EOT."""
    def filt(event: Event, st: GameState) -> bool:
        if not _is_transient_resolution_event(event):
            return False
        return event.payload.get("controller") == obj.controller

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_pt_boost_eot(obj, power=1),
        )

    return [Interceptor(
        id=f"{obj.id}_recursive_sentinel_trans",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Recursive Sentinel: +1 power on Transient resolve (EOT)",
    )]


RECURSIVE_SENTINEL = make_chassis(
    name="Recursive Sentinel",
    power=3, integrity=5,
    weapon_slots=2, add_on_slots=3,
    compute_cost=5,
    text="When a Transient you control resolves, Recursive Sentinel gets +1 power until end of turn.",
    rarity="rare",
    clankers_archetype="control",
    setup_interceptors=recursive_sentinel_setup,
)


def containment_scribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Containment Scribe: when you play a Transient, scry 1."""
    def filt(event: Event, st: GameState) -> bool:
        if not _is_transient_resolution_event(event):
            return False
        return event.payload.get("controller") == obj.controller

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.SCRY,
                payload={"player": obj.controller, "amount": 1, "reason": "containment_scribe"},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=f"{obj.id}_containment_scribe",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Containment Scribe: scry 1 on Transient",
    )]


CONTAINMENT_SCRIBE = make_chassis(
    name="Containment Scribe",
    power=2, integrity=4,
    weapon_slots=1, add_on_slots=3,
    compute_cost=3,
    text="When you play a Transient, scry 1 (look at the top card of your library; you may scrap it).",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=containment_scribe_setup,
)


ENDURANCE_FRAME = make_chassis(
    name="Endurance Frame",
    power=4, integrity=7,
    weapon_slots=1, add_on_slots=4,
    compute_cost=6,
    text="A patient bulk-tank for the late game.",
    rarity="rare",
    clankers_archetype="control",
)


# =============================================================================
# Weapons (8)
# =============================================================================

def logic_lance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Logic Lance: when this attaches, scry 1."""
    def on_attach(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={"player": obj.controller, "amount": 1, "reason": "logic_lance"},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_part_on_attach(obj, on_attach, description="Logic Lance: scry 1 on attach")]


LOGIC_LANCE = make_weapon(
    name="Logic Lance",
    power_bonus=2,
    compute_cost=2,
    weapon_slot_cost=1,
    text="When this attaches, scry 1.",
    rarity="common",
    clankers_archetype="control",
    setup_interceptors=logic_lance_setup,
)


def memory_blade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Memory Blade: when host attacks, scrap the top card of your library;
    if it was a Transient, draw a card."""
    def on_attack(event: Event, st: GameState) -> list[Event]:
        owner = obj.controller
        lib_zone = st.zones.get(f"library_{owner}")
        if lib_zone is None or not lib_zone.objects:
            return []
        top_id = lib_zone.objects[0]
        top_obj = st.objects.get(top_id)
        if top_obj is None or top_obj.card_def is None:
            return []
        # Move top of library to scrap.
        lib_zone.objects.pop(0)
        scrap_zone = st.zones.get(f"clankers_scrap_heap_{owner}")
        if scrap_zone is None:
            return []
        scrap_zone.objects.append(top_id)
        top_obj.zone = ZoneType.CLANKERS_SCRAP_HEAP
        top_obj.entered_zone_at = st.next_timestamp()
        events: list[Event] = [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": top_id,
                "to_zone": ZoneType.CLANKERS_SCRAP_HEAP.name,
                "from_zone": ZoneType.LIBRARY.name,
                "controller": owner,
                "reason": "memory_blade_mill",
            },
            source=obj.id,
            controller=owner,
        )]
        if _is_transient(top_obj.card_def):
            events.append(Event(
                type=EventType.DRAW,
                payload={"player": owner, "count": 1, "reason": "memory_blade"},
                source=obj.id,
                controller=owner,
            ))
        return events

    return [make_part_on_host_attack(obj, on_attack, description="Memory Blade: mill 1, draw on Transient")]


MEMORY_BLADE = make_weapon(
    name="Memory Blade",
    power_bonus=3,
    compute_cost=3,
    weapon_slot_cost=1,
    text=(
        "When host attacks, you may scrap the top card of your library; "
        "if it was a Transient, draw a card."
    ),
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=memory_blade_setup,
)


def recursion_hook_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Recursion Hook: when this is destroyed, return a Transient from scrap heap to hand."""
    def on_destroy(event: Event, st: GameState) -> list[Event]:
        tgt = _first_transient_in_scrap(st, obj.controller)
        if tgt is None:
            return []
        return _return_to_hand(st, tgt)
    return [make_part_on_self_destroyed(obj, on_destroy, description="Recursion Hook: recurse a Transient")]


RECURSION_HOOK = make_weapon(
    name="Recursion Hook",
    power_bonus=3,
    compute_cost=4,
    weapon_slot_cost=1,
    text="When this is destroyed, return a Transient from your scrap heap to your hand.",
    rarity="rare",
    clankers_archetype="control",
    setup_interceptors=recursion_hook_setup,
)


def subroutine_driver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reclaim 1: when destroyed, gain 1 scrap."""
    def on_destroy(event: Event, st: GameState) -> list[Event]:
        return _gain_scrap(st, obj.controller, 1, obj.id)
    return [make_part_on_self_destroyed(obj, on_destroy, description="Subroutine Driver: Reclaim 1")]


SUBROUTINE_DRIVER = make_weapon(
    name="Subroutine Driver",
    power_bonus=2,
    compute_cost=2,
    weapon_slot_cost=1,
    clankers_keywords=["reclaim_1"],
    text="Reclaim 1 (when this is destroyed, gain 1 scrap).",
    rarity="common",
    clankers_archetype="control",
    setup_interceptors=subroutine_driver_setup,
)


def heuristic_lance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When you play a Transient, this gets +1 power until end of turn."""
    def filt(event: Event, st: GameState) -> bool:
        if not _is_transient_resolution_event(event):
            return False
        return event.payload.get("controller") == obj.controller

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_pt_boost_eot(obj, power=1),
        )

    return [Interceptor(
        id=f"{obj.id}_heuristic_lance_trans",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Heuristic Lance: +1 power on Transient (EOT)",
    )]


HEURISTIC_LANCE = make_weapon(
    name="Heuristic Lance",
    power_bonus=3,
    compute_cost=3,
    weapon_slot_cost=1,
    text="When you play a Transient, this gets +1 power until end of turn.",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=heuristic_lance_setup,
)


def decoder_spike_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Decoder Spike: when you play your first Transient each turn, draw a card.

    Reads the per-turn counter we maintain on state — fires only when the
    counter transitions from 0 to 1 on a CLANKERS_COMPUTE_SPEND-Transient
    event by this controller. We track this via the counter increment in
    the interceptor itself (counter increments are wired in the file
    bootstrap below via _register_global_state_hooks, but the per-card
    interceptor reads the counter as the authoritative source).
    """
    def filt(event: Event, st: GameState) -> bool:
        if not _is_transient_resolution_event(event):
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        _ensure_ethos_state(st)
        counters = getattr(st, "clankers_clan_ethos_transients_this_turn", {}) or {}
        # The global ETHOS counter hook (install_ethos_counter_hooks) is
        # registered BEFORE this interceptor and increments first in REACT
        # dispatch order, so by the time we run the counter is already 1
        # for the first Transient of the turn. We fire when counter == 1
        # (transition 0→1, "first Transient this turn").
        return int(counters.get(obj.controller, 0)) == 1

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "decoder_spike"},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=f"{obj.id}_decoder_spike",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Decoder Spike: draw on first Transient",
    )]


DECODER_SPIKE = make_weapon(
    name="Decoder Spike",
    power_bonus=1,
    compute_cost=1,
    weapon_slot_cost=1,
    text="When you play your first Transient each turn, draw a card.",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=decoder_spike_setup,
)


def cipher_rotor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self-Mobile: a 1/1 solo part gains +power_bonus/+integrity_bonus when
    standing alone on the floor (i.e. ``state.attached_to is None``).

    Implementation: TRANSFORM on CLANKERS_QUERY_POWER / CLANKERS_QUERY_INTEGRITY
    filtered to (chassis_id == self.id) AND (attached_to is None).
    """
    def power_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        if event.payload.get("chassis_id") != obj.id:
            return False
        return obj.state.attached_to is None

    def power_handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + int(
            getattr(obj.card_def, "power_bonus", 0) or 0
        )
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

    def integ_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        if event.payload.get("chassis_id") != obj.id:
            return False
        return obj.state.attached_to is None

    def integ_handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + int(
            getattr(obj.card_def, "integrity_bonus", 0) or 0
        )
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

    return [
        Interceptor(
            id=f"{obj.id}_cipher_rotor_power",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=power_filter,
            handler=power_handler,
            description="Cipher Rotor: Self-Mobile power",
        ),
        Interceptor(
            id=f"{obj.id}_cipher_rotor_integ",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=integ_filter,
            handler=integ_handler,
            description="Cipher Rotor: Self-Mobile integrity",
        ),
    ]


CIPHER_ROTOR = make_weapon(
    name="Cipher Rotor",
    power_bonus=3,
    compute_cost=4,
    weapon_slot_cost=1,
    clankers_keywords=["self_mobile"],
    text="Self-Mobile. While unattached, Cipher Rotor is a 4/1 instead of a 1/1.",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=cipher_rotor_setup,
)


def containment_lance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Containment Lance: when host attacks, the defender cannot ready
    exhausted parts next Boot.

    Sets ``state.clankers_clan_ethos_skip_ready_next_boot[defender_id] = True``.
    The Clankers turn manager's ``_phase_boot`` reads this flag and skips
    the untap pass (consuming the flag) when set, implementing the lockout.
    """
    def on_attack(event: Event, st: GameState) -> list[Event]:
        attacker_id = event.payload.get("attacker_id")
        attacker = st.objects.get(attacker_id) if attacker_id else None
        if attacker is None:
            return []
        # The defender is the other player. Look up via state.players.
        defender_id = None
        for pid in st.players.keys():
            if pid != attacker.controller:
                defender_id = pid
                break
        if defender_id is None:
            return []
        if not hasattr(st, "clankers_clan_ethos_skip_ready_next_boot"):
            st.clankers_clan_ethos_skip_ready_next_boot = {}  # type: ignore[attr-defined]
        st.clankers_clan_ethos_skip_ready_next_boot[defender_id] = True  # type: ignore[attr-defined]
        return [Event(
            type=EventType.CLANKERS_CORE_PASSIVE,
            payload={
                "name": "Containment Lance",
                "effect": "skip_ready_next_boot",
                "target_player": defender_id,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_part_on_host_attack(obj, on_attack, description="Containment Lance: lockout opp ready")]


CONTAINMENT_LANCE = make_weapon(
    name="Containment Lance",
    power_bonus=5,
    compute_cost=5,
    weapon_slot_cost=1,
    text="When host attacks, the defender cannot ready exhausted add-ons next Boot.",
    rarity="rare",
    clankers_archetype="control",
    setup_interceptors=containment_lance_setup,
)


# =============================================================================
# Add-Ons (9)
# =============================================================================

def containment_lattice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Armor 2."""
    return [make_armor(obj, 2)]


CONTAINMENT_LATTICE = make_add_on(
    name="Containment Lattice",
    integrity_bonus=2,
    compute_cost=2,
    armor_value=2,
    text="Armor 2 (exhaust to absorb up to 2 damage to host).",
    rarity="common",
    clankers_archetype="control",
    setup_interceptors=containment_lattice_setup,
)


def heuristic_layer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When you play a Transient, draw a card. (Once per turn.)"""
    def filt(event: Event, st: GameState) -> bool:
        if not _is_transient_resolution_event(event):
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        _ensure_ethos_state(st)
        used_map = getattr(st, "clankers_clan_ethos_heuristic_layer_used", {}) or {}
        # Key by the layer's own id so multiple copies don't collide.
        return not used_map.get(obj.id, False)

    def handler(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        st.clankers_clan_ethos_heuristic_layer_used[obj.id] = True  # type: ignore[attr-defined]
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "heuristic_layer"},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    def reset_filt(event: Event, st: GameState) -> bool:
        return event.type == EventType.CLANKERS_TURN_START

    def reset_handler(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        if obj.id in st.clankers_clan_ethos_heuristic_layer_used:  # type: ignore[attr-defined]
            st.clankers_clan_ethos_heuristic_layer_used[obj.id] = False  # type: ignore[attr-defined]
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=f"{obj.id}_heuristic_layer",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            description="Heuristic Layer: draw on Transient (1/turn)",
        ),
        Interceptor(
            id=f"{obj.id}_heuristic_layer_reset",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=reset_filt,
            handler=reset_handler,
            description="Heuristic Layer: reset",
        ),
    ]


HEURISTIC_LAYER = make_add_on(
    name="Heuristic Layer",
    integrity_bonus=1,
    compute_cost=2,
    text="When you play a Transient, draw a card. (Once per turn.)",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=heuristic_layer_setup,
)


def logic_buffer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Armor 3."""
    return [make_armor(obj, 3)]


LOGIC_BUFFER = make_add_on(
    name="Logic Buffer",
    integrity_bonus=3,
    compute_cost=3,
    armor_value=3,
    text="Armor 3.",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=logic_buffer_setup,
)


def subroutine_dampener_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a Transient you control resolves, host gets +1 integrity EOT."""
    def filt(event: Event, st: GameState) -> bool:
        if not _is_transient_resolution_event(event):
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        return obj.state.attached_to is not None

    def handler(event: Event, st: GameState) -> InterceptorResult:
        host_id = obj.state.attached_to
        if host_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        host = st.objects.get(host_id)
        if host is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_pt_boost_eot(host, integrity=1),
        )

    return [Interceptor(
        id=f"{obj.id}_subroutine_dampener",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Subroutine Dampener: host +1 integrity on Transient",
    )]


SUBROUTINE_DAMPENER = make_add_on(
    name="Subroutine Dampener",
    integrity_bonus=1,
    compute_cost=1,
    text="When a Transient you control resolves, host gets +1 integrity until end of turn.",
    rarity="common",
    clankers_archetype="control",
    setup_interceptors=subroutine_dampener_setup,
)


def recursive_tape_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this is destroyed, draw 2 cards."""
    def on_destroy(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 2, "reason": "recursive_tape"},
            source=obj.id,
            controller=obj.controller,
        )]
    return [make_part_on_self_destroyed(obj, on_destroy, description="Recursive Tape: draw 2 on death")]


RECURSIVE_TAPE = make_add_on(
    name="Recursive Tape",
    integrity_bonus=3,
    power_bonus=1,
    compute_cost=4,
    text="When this is destroyed, draw 2 cards.",
    rarity="rare",
    clankers_archetype="control",
    setup_interceptors=recursive_tape_setup,
)


def soft_cycle_ridge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Armor 2. When this absorbs damage, draw a card.

    We install a custom armor-with-draw interceptor instead of make_armor,
    because we need to fire a follow-up DRAW after the damage absorption.
    """
    def filt(event: Event, st: GameState) -> bool:
        if event.type not in (
            EventType.DAMAGE,
            EventType.CLANKERS_COMBAT_DAMAGE,
            EventType.CLANKERS_WORKSHOP_DAMAGE,
        ):
            return False
        if obj.state.tapped:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        target = event.payload.get("target") or event.payload.get("defender_id")
        return target == host_id

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        amount_key = "amount" if "amount" in new_payload else "damage"
        amount = int(new_payload.get(amount_key, 0))
        absorbed = min(2, amount)
        new_payload[amount_key] = amount - absorbed
        new_payload["armor_absorbed"] = absorbed
        obj.state.tapped = True
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=Event(
                type=event.type,
                payload=new_payload,
                source=event.source,
                controller=event.controller,
                id=event.id,
            ),
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "soft_cycle_ridge"},
                source=obj.id,
                controller=obj.controller,
            )] if absorbed > 0 else [],
        )

    return [Interceptor(
        id=f"{obj.id}_soft_cycle_ridge",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filt,
        handler=handler,
        description="Soft-Cycle Ridge: Armor 2 + draw on absorb",
    )]


SOFT_CYCLE_RIDGE = make_add_on(
    name="Soft-Cycle Ridge",
    integrity_bonus=2,
    compute_cost=3,
    armor_value=2,
    text="Armor 2. When this absorbs damage, draw a card.",
    rarity="rare",
    clankers_archetype="control",
    setup_interceptors=soft_cycle_ridge_setup,
)


def cooldown_harness_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the start of your Boot phase, ready an additional exhausted add-on
    you control.

    Implemented as a REACT on PHASE_START phase=='boot'. Picks the first
    exhausted add-on (other than self) on the floor and clears its
    state.tapped.
    """
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get("phase") != "boot":
            return False
        return event.payload.get("player") == obj.controller

    def handler(event: Event, st: GameState) -> InterceptorResult:
        owner = obj.controller
        floor_key = f"clankers_assembly_floor_{owner}"
        floor = st.zones.get(floor_key)
        if floor is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Walk attached add-ons on owner's chassis.
        for chassis_id in list(floor.objects):
            chassis = st.objects.get(chassis_id)
            if chassis is None or chassis.card_def is None:
                continue
            if CardType.CLANKERS_CHASSIS not in (
                getattr(chassis.card_def.characteristics, "types", set()) or set()
            ):
                continue
            for part_id in list(chassis.state.attachments):
                part = st.objects.get(part_id)
                if part is None or part.card_def is None:
                    continue
                if CardType.CLANKERS_ADD_ON not in (
                    getattr(part.card_def.characteristics, "types", set()) or set()
                ):
                    continue
                if part.id == obj.id:
                    continue
                if not part.state.tapped:
                    continue
                part.state.tapped = False
                return InterceptorResult(
                    action=InterceptorAction.REACT,
                    new_events=[Event(
                        type=EventType.CLANKERS_CORE_PASSIVE,
                        payload={
                            "name": "Cooldown Harness",
                            "ready_part_id": part.id,
                        },
                        source=obj.id,
                        controller=owner,
                    )],
                )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=f"{obj.id}_cooldown_harness",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Cooldown Harness: extra ready at Boot",
    )]


COOLDOWN_HARNESS = make_add_on(
    name="Cooldown Harness",
    integrity_bonus=2,
    compute_cost=2,
    text="At the start of your Boot phase, ready an additional exhausted add-on you control.",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=cooldown_harness_setup,
)


def patient_frame_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """While host has 4+ damage marked, host has +2 power.

    Conditional TRANSFORM on CLANKERS_QUERY_POWER. The filter checks host's
    damage_marked >= 4.
    """
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        if event.payload.get("chassis_id") != host_id:
            return False
        host = st.objects.get(host_id)
        if host is None:
            return False
        damage = int(getattr(host.state, "damage_marked", 0) or 0)
        return damage >= 4

    def handler(event: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + 2
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
        id=f"{obj.id}_patient_frame",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filt,
        handler=handler,
        description="Patient Frame: +2 power when host has 4+ damage",
    )]


PATIENT_FRAME = make_add_on(
    name="Patient Frame",
    integrity_bonus=4,
    compute_cost=3,
    text="While host has 4+ damage marked, it has +2 power.",
    rarity="rare",
    clankers_archetype="control",
    setup_interceptors=patient_frame_setup,
)


def memory_buffer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pay 2 Compute, exhaust this: return a Transient from your scrap heap to your hand.

    Registered via make_weapon_activated (reuses the same activated-ability
    descriptor list — works for both weapons and add-ons by convention).
    """
    def effect(event: Event, st: GameState) -> list[Event]:
        tgt = _first_transient_in_scrap(st, obj.controller)
        if tgt is None:
            return []
        return _return_to_hand(st, tgt)

    return [make_weapon_activated(
        obj,
        compute_cost=2,
        exhaust_self=True,
        effect_fn=effect,
        description="Memory Buffer: recurse a Transient",
    )]


MEMORY_BUFFER = make_add_on(
    name="Memory Buffer",
    integrity_bonus=2,
    compute_cost=2,
    text="Pay 2 Compute, exhaust this: return a Transient from your scrap heap to your hand.",
    rarity="uncommon",
    clankers_archetype="control",
    setup_interceptors=memory_buffer_setup,
)


# =============================================================================
# Transients (6)
# =============================================================================

def _heuristic_loop_resolve(event: Event, state: GameState) -> list[Event]:
    """Draw 2; if 3+ Transients in scrap heap, draw 1 more."""
    controller = event.payload.get("controller") or event.controller
    if not isinstance(controller, str):
        return []
    count = _count_transients_in_scrap(state, controller)
    n_draw = 2 + (1 if count >= 3 else 0)
    return [Event(
        type=EventType.DRAW,
        payload={"player": controller, "count": n_draw, "reason": "heuristic_loop"},
        source=event.payload.get("transient_id") or event.source,
        controller=controller,
    )]


HEURISTIC_LOOP = make_transient(
    name="Heuristic Loop",
    compute_cost=2,
    resolve_fn=_heuristic_loop_resolve,
    text="Draw 2 cards. If 3+ Transients are in your scrap heap, draw 1 more.",
    rarity="uncommon",
    clankers_archetype="control",
)


def _reroute_power_resolve(event: Event, state: GameState) -> list[Event]:
    """Target chassis deals damage = its attached-weapon-count to chassis or Core.

    Targets payload: [source_chassis_id, target_id]. If no targets are
    provided the resolver picks the controller's first chassis with attached
    weapons as source and the opponent's Core as target (sensible default
    so the AI can fire-and-forget).
    """
    controller = event.payload.get("controller") or event.controller
    if not isinstance(controller, str):
        return []
    targets = list(event.payload.get("targets") or [])
    source_chassis_id: Optional[str] = targets[0] if len(targets) > 0 else None
    target_id: Optional[str] = targets[1] if len(targets) > 1 else None

    # Default-target heuristics: pick first own chassis with weapons, then
    # opponent's Core.
    if source_chassis_id is None:
        floor = state.zones.get(f"clankers_assembly_floor_{controller}")
        if floor is not None:
            for cid in floor.objects:
                c = state.objects.get(cid)
                if c is None or c.card_def is None:
                    continue
                if CardType.CLANKERS_CHASSIS not in (
                    getattr(c.card_def.characteristics, "types", set()) or set()
                ):
                    continue
                w_count = sum(
                    1 for pid in c.state.attachments
                    if state.objects.get(pid) is not None
                    and _is_weapon(state.objects[pid].card_def)
                )
                if w_count > 0:
                    source_chassis_id = cid
                    break
    if target_id is None:
        for pid in state.players.keys():
            if pid != controller:
                target_id = state.clankers_cores.get(pid)  # type: ignore[attr-defined]
                break

    if source_chassis_id is None or target_id is None:
        return []
    source_obj = state.objects.get(source_chassis_id)
    if source_obj is None:
        return []
    weapon_count = sum(
        1 for pid in source_obj.state.attachments
        if state.objects.get(pid) is not None
        and state.objects[pid].card_def is not None
        and _is_weapon(state.objects[pid].card_def)
    )
    if weapon_count <= 0:
        return []

    # Pick the right damage event type: workshop damage if target is a Core,
    # otherwise generic DAMAGE.
    target_obj = state.objects.get(target_id)
    is_core = (
        target_obj is not None
        and target_obj.card_def is not None
        and CardType.CLANKERS_CORE in (
            getattr(target_obj.card_def.characteristics, "types", set()) or set()
        )
    )
    if is_core:
        target_player = target_obj.controller
        cur = int(state.clankers_workshop_integrity.get(target_player, 0))  # type: ignore[attr-defined]
        state.clankers_workshop_integrity[target_player] = max(0, cur - weapon_count)  # type: ignore[attr-defined]
        return [Event(
            type=EventType.CLANKERS_WORKSHOP_DAMAGE,
            payload={
                "target": target_id,
                "player_id": target_player,
                "amount": weapon_count,
                "reason": "reroute_power",
                "new_integrity": state.clankers_workshop_integrity[target_player],  # type: ignore[attr-defined]
            },
            source=source_chassis_id,
            controller=controller,
        )]
    return [Event(
        type=EventType.DAMAGE,
        payload={
            "target": target_id,
            "amount": weapon_count,
            "source": source_chassis_id,
            "reason": "reroute_power",
        },
        source=source_chassis_id,
        controller=controller,
    )]


REROUTE_POWER = make_transient(
    name="Reroute Power",
    compute_cost=1,
    resolve_fn=_reroute_power_resolve,
    text=(
        "Target chassis deals damage equal to its attached-weapon-count to "
        "a chassis or Core."
    ),
    rarity="uncommon",
    clankers_archetype="control",
)


def _garbage_collector_resolve(event: Event, state: GameState) -> list[Event]:
    """Return a Transient from your scrap heap to your hand."""
    controller = event.payload.get("controller") or event.controller
    if not isinstance(controller, str):
        return []
    targets = list(event.payload.get("targets") or [])
    target_obj: Optional[GameObject] = None
    if targets:
        cand = state.objects.get(targets[0])
        if cand is not None and cand.card_def is not None and _is_transient(cand.card_def):
            target_obj = cand
    if target_obj is None:
        target_obj = _first_transient_in_scrap(state, controller)
    if target_obj is None:
        return []
    return _return_to_hand(state, target_obj)


GARBAGE_COLLECTOR = make_transient(
    name="Garbage Collector",
    compute_cost=3,
    resolve_fn=_garbage_collector_resolve,
    text="Return a Transient from your scrap heap to your hand.",
    rarity="uncommon",
    clankers_archetype="control",
)


def _diagnostic_sweep_resolve(event: Event, state: GameState) -> list[Event]:
    """Scry 3 (look at top 3; scrap any; rest on top in any order)."""
    controller = event.payload.get("controller") or event.controller
    if not isinstance(controller, str):
        return []
    return [Event(
        type=EventType.SCRY,
        payload={
            "player": controller,
            "amount": 3,
            "may_scrap": True,
            "reason": "diagnostic_sweep",
        },
        source=event.payload.get("transient_id") or event.source,
        controller=controller,
    )]


DIAGNOSTIC_SWEEP = make_transient(
    name="Diagnostic Sweep",
    compute_cost=2,
    resolve_fn=_diagnostic_sweep_resolve,
    text="Scry 3 (look at top 3, scrap any, rest on top in any order).",
    rarity="common",
    clankers_archetype="control",
)


def _subroutine_cascade_resolve(event: Event, state: GameState) -> list[Event]:
    """Draw 3 cards; the next Transient you play this turn costs 2 less Compute (min 0).

    We register a one-shot TRANSFORM interceptor on CLANKERS_COMPUTE_SPEND
    that reduces the next Transient-spend by this controller by 2, then
    self-destructs (uses_remaining=1). Cleanup at TURN_END defensively in
    case the player never plays another Transient.
    """
    _ensure_ethos_state(state)
    controller = event.payload.get("controller") or event.controller
    if not isinstance(controller, str):
        return []

    cascade_token_id = f"clan_ethos_cascade_{controller}_{state.next_timestamp()}"

    def cascade_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_COMPUTE_SPEND:
            return False
        if ev.payload.get("player_id") != controller:
            return False
        src_id = ev.payload.get("source_card_id")
        if src_id is None:
            return False
        src_obj = st.objects.get(src_id)
        if src_obj is None or src_obj.card_def is None:
            return False
        if not _is_transient(src_obj.card_def):
            return False
        uses = getattr(st, "clankers_clan_ethos_cascade_uses", {}) or {}
        return int(uses.get(cascade_token_id, 0)) > 0

    def cascade_handler(ev: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        uses_map = st.clankers_clan_ethos_cascade_uses  # type: ignore[attr-defined]
        cur = int(uses_map.get(cascade_token_id, 0))
        uses_map[cascade_token_id] = cur - 1
        new_payload = dict(ev.payload)
        amt = int(new_payload.get("amount", 0))
        new_payload["amount"] = max(0, amt - 2)
        new_payload["cascade_discount_applied"] = 2
        # Remove the interceptor from the live dispatch table so the next
        # Transient doesn't double-apply.
        ic_id = f"{cascade_token_id}_ic"
        if ic_id in st.interceptors:
            del st.interceptors[ic_id]
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

    state.clankers_clan_ethos_cascade_uses[cascade_token_id] = 1  # type: ignore[attr-defined]
    cascade_ic = Interceptor(
        id=f"{cascade_token_id}_ic",
        source=event.payload.get("transient_id"),
        controller=controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=cascade_filter,
        handler=cascade_handler,
        description="Subroutine Cascade: next Transient costs 2 less",
        duration="end_of_turn",
    )
    state.interceptors[cascade_ic.id] = cascade_ic

    return [Event(
        type=EventType.DRAW,
        payload={"player": controller, "count": 3, "reason": "subroutine_cascade"},
        source=event.payload.get("transient_id") or event.source,
        controller=controller,
    )]


SUBROUTINE_CASCADE = make_transient(
    name="Subroutine Cascade",
    compute_cost=4,
    resolve_fn=_subroutine_cascade_resolve,
    text=(
        "Draw 3 cards; the next Transient you play this turn costs 2 less "
        "Compute (min 0)."
    ),
    rarity="rare",
    clankers_archetype="control",
)


def _patch_resolve(event: Event, state: GameState) -> list[Event]:
    """Target chassis you control regains all damage marked (heal full).

    Directly clears the chassis's damage_marked counter. We emit a synthetic
    OBJECT_HEAL-style event so observers/UI can see the heal; the engine
    doesn't have a dedicated heal-primitive event type, so we use DAMAGE
    with a negative amount on the target — that's a recognised pattern in
    other engines (Pokemon Patch / Lorwyn Path of Peace).
    """
    controller = event.payload.get("controller") or event.controller
    if not isinstance(controller, str):
        return []
    targets = list(event.payload.get("targets") or [])
    target_id: Optional[str] = targets[0] if targets else None
    target_obj: Optional[GameObject] = None
    if target_id is not None:
        cand = state.objects.get(target_id)
        if (
            cand is not None
            and cand.card_def is not None
            and CardType.CLANKERS_CHASSIS in (
                getattr(cand.card_def.characteristics, "types", set()) or set()
            )
            and cand.controller == controller
        ):
            target_obj = cand

    if target_obj is None:
        # Default: heal the controller's most-damaged chassis.
        floor = state.zones.get(f"clankers_assembly_floor_{controller}")
        if floor is None:
            return []
        best: Optional[GameObject] = None
        best_dmg = -1
        for cid in floor.objects:
            c = state.objects.get(cid)
            if c is None or c.card_def is None:
                continue
            if CardType.CLANKERS_CHASSIS not in (
                getattr(c.card_def.characteristics, "types", set()) or set()
            ):
                continue
            dmg = int(getattr(c.state, "damage_marked", 0) or 0)
            if dmg > best_dmg:
                best = c
                best_dmg = dmg
        target_obj = best

    if target_obj is None:
        return []
    healed = int(getattr(target_obj.state, "damage_marked", 0) or 0)
    target_obj.state.damage_marked = 0
    # Also clear the alternate damage field if set (some engines use both).
    if hasattr(target_obj.state, "damage"):
        target_obj.state.damage = 0
    return [Event(
        type=EventType.DAMAGE,
        payload={
            "target": target_obj.id,
            "amount": -healed,
            "source": event.payload.get("transient_id") or event.source,
            "reason": "patch_heal",
            "healed": healed,
        },
        source=event.payload.get("transient_id") or event.source,
        controller=controller,
    )]


PATCH = make_transient(
    name="Patch",
    compute_cost=1,
    resolve_fn=_patch_resolve,
    text="Target chassis you control regains all damage marked (heal full).",
    rarity="common",
    clankers_archetype="control",
)


# =============================================================================
# Structures (2)
# =============================================================================

def recursive_observatory_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reticulate: at end of turn, if you played no Transients this turn,
    draw a card.

    Reads the per-turn counter on state.clankers_clan_ethos_transients_this_turn.
    """
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.CLANKERS_TURN_END:
            return False
        if event.payload.get("player") != obj.controller:
            return False
        counters = getattr(st, "clankers_clan_ethos_transients_this_turn", {}) or {}
        return int(counters.get(obj.controller, 0)) == 0

    def handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1, "reason": "recursive_observatory"},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=f"{obj.id}_recursive_observatory",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Recursive Observatory: Reticulate EOT draw",
    )]


RECURSIVE_OBSERVATORY = make_structure(
    name="Recursive Observatory",
    compute_cost=3,
    setup_interceptors=recursive_observatory_setup,
    text=(
        "Reticulate (at end of turn, if you played no Transients this turn, "
        "draw a card)."
    ),
    rarity="rare",
    clankers_archetype="control",
)


def compute_trickle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the start of your Boot phase, gain 1 Compute (above your cap, this turn only)."""
    def filt(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get("phase") != "boot":
            return False
        return event.payload.get("player") == obj.controller

    def handler(event: Event, st: GameState) -> InterceptorResult:
        owner = obj.controller
        pool = getattr(st, "clankers_compute_pool", {}) or {}
        cur = int(pool.get(owner, 0))
        pool[owner] = cur + 1
        st.clankers_compute_pool = pool  # type: ignore[attr-defined]
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CLANKERS_COMPUTE_GAIN,
                payload={
                    "player_id": owner,
                    "amount": 1,
                    "reason": "compute_trickle",
                    "above_cap": True,
                },
                source=obj.id,
                controller=owner,
            )],
        )

    return [Interceptor(
        id=f"{obj.id}_compute_trickle",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        description="Compute Trickle: +1 Compute at Boot",
    )]


COMPUTE_TRICKLE = make_structure(
    name="Compute Trickle",
    compute_cost=3,
    setup_interceptors=compute_trickle_setup,
    text="At the start of your Boot phase, gain 1 Compute (above your cap, this turn only).",
    rarity="uncommon",
    clankers_archetype="control",
)


# =============================================================================
# Shared per-game state hook (per-player transient counter)
# =============================================================================
#
# Several cards in this file (Loop Engine, Decoder Spike, Recursive
# Observatory) read state.clankers_clan_ethos_transients_this_turn to know
# whether the controller played any Transients this turn. We need to
# increment that counter on every Transient resolution and reset it at
# turn start. Rather than duplicate the bookkeeping on every card, we
# install a single global REACT pair the first time any ETHOS card is
# constructed.
#
# This hook is installed lazily by ``install_ethos_counter_hooks(state)``,
# which is called by the deck-building / setup code (or test harnesses).
# Calling it twice on the same state is a no-op (idempotent on a flag).


def install_ethos_counter_hooks(state: GameState) -> None:
    """Install the global Transient-counter hooks on ``state``. Idempotent.

    Card setup_interceptors closures call this from within their first
    invocation (see _maybe_install_hooks below) so deck-building harnesses
    don't need to call it explicitly. It's exposed publicly so the test
    harness can also call it from a fixture if it wants pre-game setup.
    """
    if getattr(state, "_clan_ethos_counter_installed", False):
        return
    setattr(state, "_clan_ethos_counter_installed", True)
    _ensure_ethos_state(state)

    def inc_filter(event: Event, st: GameState) -> bool:
        return _is_transient_resolution_event(event)

    def inc_handler(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        controller = event.payload.get("controller") or event.controller
        if not isinstance(controller, str):
            return InterceptorResult(action=InterceptorAction.PASS)
        cur = int(st.clankers_clan_ethos_transients_this_turn.get(controller, 0))  # type: ignore[attr-defined]
        st.clankers_clan_ethos_transients_this_turn[controller] = cur + 1  # type: ignore[attr-defined]
        return InterceptorResult(action=InterceptorAction.PASS)

    def reset_filter(event: Event, st: GameState) -> bool:
        return event.type == EventType.CLANKERS_TURN_START

    def reset_handler(event: Event, st: GameState) -> InterceptorResult:
        _ensure_ethos_state(st)
        player = event.payload.get("player")
        if isinstance(player, str):
            st.clankers_clan_ethos_transients_this_turn[player] = 0  # type: ignore[attr-defined]
        return InterceptorResult(action=InterceptorAction.PASS)

    inc_ic_id = "clan_ethos_global_transient_counter"
    if inc_ic_id not in state.interceptors:
        state.interceptors[inc_ic_id] = Interceptor(
            id=inc_ic_id,
            source=None,
            controller=None,
            priority=InterceptorPriority.REACT,
            filter=inc_filter,
            handler=inc_handler,
            description="ETHOS: global Transient counter increment",
            duration="forever",
        )

    reset_ic_id = "clan_ethos_global_transient_reset"
    if reset_ic_id not in state.interceptors:
        state.interceptors[reset_ic_id] = Interceptor(
            id=reset_ic_id,
            source=None,
            controller=None,
            priority=InterceptorPriority.REACT,
            filter=reset_filter,
            handler=reset_handler,
            description="ETHOS: global Transient counter reset at turn start",
            duration="forever",
        )


# Auto-install the counter hooks the first time any ETHOS chassis or part
# setup_interceptors closure runs on a given state. We achieve this by
# wrapping each setup_interceptors function defined above so its first call
# also installs the hooks. Doing this in-place keeps the deck-loader free
# of bespoke registration code.

def _wrap_with_hook(orig_setup):
    if orig_setup is None:
        return None

    def wrapped(obj, st):
        try:
            install_ethos_counter_hooks(st)
        except Exception:
            pass
        return orig_setup(obj, st)
    return wrapped


# Apply the wrapper to every card def above with a setup_interceptors.
for _cd in (
    ETHOS_7, SUBROUTINE_ALPHA,
    BULWARK_FRAME, SUBROUTINE_CORE, LOOP_ENGINE, HEURISTIC_SENTRY,
    LONG_MEMORY_HUSK, RECURSIVE_SENTINEL, CONTAINMENT_SCRIBE, ENDURANCE_FRAME,
    LOGIC_LANCE, MEMORY_BLADE, RECURSION_HOOK, SUBROUTINE_DRIVER,
    HEURISTIC_LANCE, DECODER_SPIKE, CIPHER_ROTOR, CONTAINMENT_LANCE,
    CONTAINMENT_LATTICE, HEURISTIC_LAYER, LOGIC_BUFFER, SUBROUTINE_DAMPENER,
    RECURSIVE_TAPE, SOFT_CYCLE_RIDGE, COOLDOWN_HARNESS, PATIENT_FRAME,
    MEMORY_BUFFER,
    RECURSIVE_OBSERVATORY, COMPUTE_TRICKLE,
):
    _existing = getattr(_cd, "setup_interceptors", None)
    if _existing is not None:
        _cd.setup_interceptors = _wrap_with_hook(_existing)
    # Cores use clankers_core_passive_setup instead.
    _passive = getattr(_cd, "clankers_core_passive_setup", None)
    if _passive is not None:
        _cd.clankers_core_passive_setup = _wrap_with_hook(_passive)


# =============================================================================
# Aggregate (registry)
# =============================================================================

ETHOS_CARDS = {
    "ETHOS-7": ETHOS_7,
    "SUBROUTINE-α": SUBROUTINE_ALPHA,
    # Chassis
    "Bulwark Frame": BULWARK_FRAME,
    "Subroutine Core": SUBROUTINE_CORE,
    "Loop Engine": LOOP_ENGINE,
    "Heuristic Sentry": HEURISTIC_SENTRY,
    "Long-Memory Husk": LONG_MEMORY_HUSK,
    "Recursive Sentinel": RECURSIVE_SENTINEL,
    "Containment Scribe": CONTAINMENT_SCRIBE,
    "Endurance Frame": ENDURANCE_FRAME,
    # Weapons
    "Logic Lance": LOGIC_LANCE,
    "Memory Blade": MEMORY_BLADE,
    "Recursion Hook": RECURSION_HOOK,
    "Subroutine Driver": SUBROUTINE_DRIVER,
    "Heuristic Lance": HEURISTIC_LANCE,
    "Decoder Spike": DECODER_SPIKE,
    "Cipher Rotor": CIPHER_ROTOR,
    "Containment Lance": CONTAINMENT_LANCE,
    # Add-Ons
    "Containment Lattice": CONTAINMENT_LATTICE,
    "Heuristic Layer": HEURISTIC_LAYER,
    "Logic Buffer": LOGIC_BUFFER,
    "Subroutine Dampener": SUBROUTINE_DAMPENER,
    "Recursive Tape": RECURSIVE_TAPE,
    "Soft-Cycle Ridge": SOFT_CYCLE_RIDGE,
    "Cooldown Harness": COOLDOWN_HARNESS,
    "Patient Frame": PATIENT_FRAME,
    "Memory Buffer": MEMORY_BUFFER,
    # Transients
    "Heuristic Loop": HEURISTIC_LOOP,
    "Reroute Power": REROUTE_POWER,
    "Garbage Collector": GARBAGE_COLLECTOR,
    "Diagnostic Sweep": DIAGNOSTIC_SWEEP,
    "Subroutine Cascade": SUBROUTINE_CASCADE,
    "Patch": PATCH,
    # Structures
    "Recursive Observatory": RECURSIVE_OBSERVATORY,
    "Compute Trickle": COMPUTE_TRICKLE,
}
