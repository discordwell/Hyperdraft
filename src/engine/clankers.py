"""Clankers — multi-part robot assembly battler engine core.

See ``docs/games/clankers.md`` for the design and
``docs/games/clankers_contract.md`` for the Stage-1 interface contract.

State convention: this engine uses **flat attribute-attached state on GameState**
(the same pattern Cats / Depths use):

    state.clankers_workshop_integrity: dict[str, int]
    state.clankers_compute_pool: dict[str, int]
    state.clankers_compute_cap: dict[str, int]
    state.clankers_scrap_pool: dict[str, int]
    state.clankers_refill_used: dict[str, bool]
    state.clankers_cores: dict[str, str]
    state.clankers_containment_failure: bool
    state.clankers_containment_turn: int
    state.clankers_structures: dict[str, list[str]]
    state.clankers_assemblies: dict[str, list[str]]   # chassis ids on the floor
    state.clankers_loser: Optional[str]
    state.clankers_first_turn: bool

Card-def numerics (compute_cost, power_bonus, etc.) live as **dynamic attrs**
on the standard CardDefinition (cats pattern). Factories do
``card_def.compute_cost = N`` etc., and readers use
``getattr(card_def, "compute_cost", 0)`` defensively.

Public API: see §4 of the contract. Consumed by ``clankers_combat.py``,
``clankers_turn.py``, ``clankers_adapter.py``, and Stage-4 card sets.
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Callable, Optional

from src.engine.types import (
    CardDefinition,
    CardType,
    Characteristics,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
    Zone,
    ZoneType,
    new_id,
)


# =============================================================================
# Constants (see contract §4)
# =============================================================================

CLANKERS_HAND_FLOOR = 7
CLANKERS_DECK_SIZE = 60
CLANKERS_STARTING_WORKSHOP_INTEGRITY = 25
CLANKERS_COMPUTE_POOL_BASE = 3
CLANKERS_COMPUTE_CAP = 10
CLANKERS_SCRAP_CAP = 10
CLANKERS_MAX_STRUCTURES = 3
CLANKERS_DEATHCLOCK_BASE = 2
CLANKERS_DEATHCLOCK_MULTIPLIER = 2
CLANKERS_DEFAULT_CHASSIS_WEAPON_SLOTS = 2
CLANKERS_DEFAULT_CHASSIS_ADDON_SLOTS = 2
CLANKERS_SOLO_PART_POWER = 1
CLANKERS_SOLO_PART_INTEGRITY = 1


# Part type predicates (engine-internal helpers)
_PART_TYPES = (CardType.CLANKERS_WEAPON, CardType.CLANKERS_ADD_ON)


def _card_types(card_def: Optional[CardDefinition]) -> set:
    if card_def is None or card_def.characteristics is None:
        return set()
    return getattr(card_def.characteristics, "types", set()) or set()


def _is_chassis(card_def: Optional[CardDefinition]) -> bool:
    return CardType.CLANKERS_CHASSIS in _card_types(card_def)


def _is_weapon(card_def: Optional[CardDefinition]) -> bool:
    return CardType.CLANKERS_WEAPON in _card_types(card_def)


def _is_add_on(card_def: Optional[CardDefinition]) -> bool:
    return CardType.CLANKERS_ADD_ON in _card_types(card_def)


def _is_part(card_def: Optional[CardDefinition]) -> bool:
    return _is_weapon(card_def) or _is_add_on(card_def)


def _is_transient(card_def: Optional[CardDefinition]) -> bool:
    return CardType.CLANKERS_TRANSIENT in _card_types(card_def)


def _is_structure(card_def: Optional[CardDefinition]) -> bool:
    return CardType.CLANKERS_STRUCTURE in _card_types(card_def)


def _is_core(card_def: Optional[CardDefinition]) -> bool:
    return CardType.CLANKERS_CORE in _card_types(card_def)


# =============================================================================
# Object / zone plumbing
# =============================================================================

def _make_object_from_def(
    state: GameState,
    card_def: CardDefinition,
    owner: str,
    zone: ZoneType,
) -> GameObject:
    """Create a GameObject from a CardDefinition. Mirrors how the engine builds objects.

    Used for deck construction and Core placement (cats pattern).
    """
    chars = deepcopy(card_def.characteristics)
    obj = GameObject(
        id=new_id(),
        name=card_def.name,
        owner=owner,
        controller=owner,
        zone=zone,
        characteristics=chars,
        card_def=card_def,
    )
    obj._state_ref = state
    obj.created_at = state.next_timestamp()
    obj.entered_zone_at = obj.created_at
    state.objects[obj.id] = obj
    return obj


def _ensure_zone(state: GameState, zone_type: ZoneType, owner: Optional[str]) -> Zone:
    """Get-or-create a zone keyed by (type, owner).

    Matches the canonical key convention used by ``Game._create_player_zones``
    and every peer engine (depths, minecraft, hearthstone): per-player zones
    use ``f"{zone_type.name.lower()}_{player_id}"``; shared zones use just
    ``zone_type.name.lower()``.
    """
    if owner is None:
        zone_key = zone_type.name.lower()
    else:
        zone_key = f"{zone_type.name.lower()}_{owner}"
    z = state.zones.get(zone_key)
    if z is None:
        z = Zone(type=zone_type, owner=owner)
        state.zones[zone_key] = z
    return z


def _zone_objects(state: GameState, zone_type: ZoneType, owner: Optional[str]) -> list[str]:
    """Convenience reader for a zone's object id list."""
    return _ensure_zone(state, zone_type, owner).objects


def _init_clankers_state(state: GameState) -> None:
    """Initialize all state.clankers_* fields if missing. Idempotent."""
    if not hasattr(state, "clankers_workshop_integrity"):
        state.clankers_workshop_integrity = {}
    if not hasattr(state, "clankers_compute_pool"):
        state.clankers_compute_pool = {}
    if not hasattr(state, "clankers_compute_cap"):
        state.clankers_compute_cap = {}
    if not hasattr(state, "clankers_scrap_pool"):
        state.clankers_scrap_pool = {}
    if not hasattr(state, "clankers_refill_used"):
        state.clankers_refill_used = {}
    if not hasattr(state, "clankers_cores"):
        state.clankers_cores = {}
    if not hasattr(state, "clankers_containment_failure"):
        state.clankers_containment_failure = False
    if not hasattr(state, "clankers_containment_turn"):
        state.clankers_containment_turn = 0
    if not hasattr(state, "clankers_structures"):
        state.clankers_structures = {}
    if not hasattr(state, "clankers_assemblies"):
        state.clankers_assemblies = {}
    if not hasattr(state, "clankers_loser"):
        state.clankers_loser = None
    if not hasattr(state, "clankers_first_turn"):
        state.clankers_first_turn = True


# =============================================================================
# Lightweight interceptor dispatcher (synthetic queries)
# =============================================================================

def _dispatch_interceptors(
    state: GameState,
    event: Event,
    priorities: tuple[InterceptorPriority, ...] = (
        InterceptorPriority.TRANSFORM,
        InterceptorPriority.REACT,
    ),
) -> tuple[Event, list[Event]]:
    """Walk state.interceptors, apply matching ones in priority order.

    Returns (possibly-transformed event, list of REACT follow-ups). Mirrors
    the cats.py helper — small enough to dodge the full pipeline for the
    CLANKERS_QUERY_POWER / CLANKERS_QUERY_INTEGRITY / CLANKERS_HAND_REFILL_QUERY
    synthetic queries that don't go through the priority stack.
    """
    new_events: list[Event] = []
    current = event
    for priority in priorities:
        for ic in list(state.interceptors.values()):
            if ic.priority != priority:
                continue
            try:
                if not ic.filter(current, state):
                    continue
            except Exception:
                continue
            try:
                result = ic.handler(current, state)
            except Exception:
                continue
            if not isinstance(result, InterceptorResult):
                if isinstance(result, list):
                    new_events.extend(result)
                continue
            if result.action == InterceptorAction.TRANSFORM and result.transformed_event is not None:
                current = result.transformed_event
            elif result.action == InterceptorAction.REPLACE and result.transformed_event is not None:
                current = result.transformed_event
            elif result.action == InterceptorAction.REACT:
                new_events.extend(result.new_events)
            elif result.action == InterceptorAction.PREVENT:
                return current, new_events
    return current, new_events


def _register_interceptors_for(obj: GameObject, state: GameState) -> None:
    """Run obj.card_def.setup_interceptors and register the returned interceptors."""
    if obj is None or obj.card_def is None:
        return
    fn = obj.card_def.setup_interceptors
    if fn is None:
        return
    try:
        new_interceptors = fn(obj, state) or []
    except Exception:
        return
    for ic in new_interceptors:
        if ic.id in state.interceptors:
            continue
        state.interceptors[ic.id] = ic
        if ic.id not in obj.interceptor_ids:
            obj.interceptor_ids.append(ic.id)


# =============================================================================
# Setup
# =============================================================================

def setup_clankers_player(
    state: GameState,
    player_id: str,
    deck: list[CardDefinition],
    core_card_def: CardDefinition,
) -> None:
    """Initialize a Clankers player: shuffle deck into library, draw opening 7,
    place Core in COMMAND zone, init all clankers_* state.

    Idempotent on the per-player state slots (won't overwrite an existing core).
    """
    _init_clankers_state(state)
    if player_id not in state.players:
        state.players[player_id] = Player(id=player_id, name=player_id)

    if state.rng_seed is not None:
        rng = random.Random(state.rng_seed + hash(player_id) % 10_000)
    else:
        rng = random
    deck_copy = list(deck)
    rng.shuffle(deck_copy)

    library = _ensure_zone(state, ZoneType.LIBRARY, player_id)
    library.objects.clear()
    for cd in deck_copy:
        obj = _make_object_from_def(state, cd, player_id, ZoneType.LIBRARY)
        library.objects.append(obj.id)

    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    hand.objects.clear()
    for _ in range(CLANKERS_HAND_FLOOR):
        if not library.objects:
            break
        obj_id = library.objects.pop(0)
        obj = state.objects[obj_id]
        obj.zone = ZoneType.HAND
        obj.entered_zone_at = state.next_timestamp()
        hand.objects.append(obj_id)

    # Pre-create the Assembly Floor and Scrap Heap zones so subsequent
    # play_card_from_hand / death_cascade calls find them.
    _ensure_zone(state, ZoneType.CLANKERS_ASSEMBLY_FLOOR, player_id)
    _ensure_zone(state, ZoneType.CLANKERS_SCRAP_HEAP, player_id)
    _ensure_zone(state, ZoneType.COMMAND, player_id)

    # Per-player state slots.
    state.clankers_workshop_integrity.setdefault(
        player_id,
        int(getattr(core_card_def, "workshop_integrity", CLANKERS_STARTING_WORKSHOP_INTEGRITY)),
    )
    state.clankers_compute_pool.setdefault(player_id, 0)
    state.clankers_compute_cap.setdefault(player_id, CLANKERS_COMPUTE_CAP)
    state.clankers_scrap_pool.setdefault(player_id, 0)
    state.clankers_refill_used.setdefault(player_id, False)
    state.clankers_structures.setdefault(player_id, [])
    state.clankers_assemblies.setdefault(player_id, [])

    # Place Core in COMMAND. Re-running setup for the same player won't double
    # the core; the existing entry wins.
    if player_id not in state.clankers_cores:
        core_obj = _make_object_from_def(state, core_card_def, player_id, ZoneType.COMMAND)
        cmd_zone = _ensure_zone(state, ZoneType.COMMAND, player_id)
        cmd_zone.objects.append(core_obj.id)
        state.clankers_cores[player_id] = core_obj.id
        # Run the Core's passive setup if one was attached via the factory.
        passive = getattr(core_card_def, "clankers_core_passive_setup", None)
        if callable(passive):
            try:
                interceptors = passive(core_obj, state) or []
                for ic in interceptors:
                    state.interceptors[ic.id] = ic
                    if ic.id not in core_obj.interceptor_ids:
                        core_obj.interceptor_ids.append(ic.id)
            except Exception:
                pass
        # Also honour standard setup_interceptors on cores (cats compat).
        _register_interceptors_for(core_obj, state)


# =============================================================================
# Compute / scrap / hand helpers
# =============================================================================

def _draw_one(state: GameState, player_id: str) -> Optional[str]:
    """Move the top card of player_id's library to their hand. Returns the obj id."""
    library = _ensure_zone(state, ZoneType.LIBRARY, player_id)
    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    if not library.objects:
        return None
    cid = library.objects.pop(0)
    obj = state.objects.get(cid)
    if obj is not None:
        obj.zone = ZoneType.HAND
        obj.entered_zone_at = state.next_timestamp()
    hand.objects.append(cid)
    return cid


def _spend_compute(state: GameState, player_id: str, amount: int, source_card_id: Optional[str]) -> list[Event]:
    """Emit a CLANKERS_COMPUTE_SPEND, decrement the pool, return the event list.

    Cost-reduction interceptors may TRANSFORM the payload amount before we
    apply it to the pool.
    """
    _init_clankers_state(state)
    if amount <= 0:
        return []
    event = Event(
        type=EventType.CLANKERS_COMPUTE_SPEND,
        payload={
            "player_id": player_id,
            "amount": int(amount),
            "source_card_id": source_card_id,
        },
        source=source_card_id,
        controller=player_id,
    )
    transformed, reactions = _dispatch_interceptors(
        state, event,
        priorities=(InterceptorPriority.TRANSFORM, InterceptorPriority.REACT),
    )
    actual = int(transformed.payload.get("amount", amount))
    if actual < 0:
        actual = 0
    pool = int(state.clankers_compute_pool.get(player_id, 0))
    state.clankers_compute_pool[player_id] = max(0, pool - actual)
    return [transformed, *reactions]


def _gain_scrap(state: GameState, player_id: str, amount: int, source_card_id: Optional[str]) -> list[Event]:
    """Add scrap (capped at CLANKERS_SCRAP_CAP), emit CLANKERS_SCRAP_GAIN."""
    _init_clankers_state(state)
    if amount <= 0:
        return []
    cur = int(state.clankers_scrap_pool.get(player_id, 0))
    state.clankers_scrap_pool[player_id] = min(CLANKERS_SCRAP_CAP, cur + int(amount))
    return [Event(
        type=EventType.CLANKERS_SCRAP_GAIN,
        payload={"player_id": player_id, "amount": int(amount), "new_total": state.clankers_scrap_pool[player_id]},
        source=source_card_id,
        controller=player_id,
    )]


# =============================================================================
# Public API: attach / detach
# =============================================================================

def _open_slots(state: GameState, chassis: GameObject, slot_type: str) -> int:
    """Return open slot count for ``slot_type`` ('weapon' or 'add_on') on a chassis.

    Accounts for multi-slot weapons via ``weapon_slot_cost`` on each attached
    weapon's card_def.
    """
    if chassis is None or chassis.card_def is None:
        return 0
    if slot_type == "weapon":
        cap = int(getattr(chassis.card_def, "weapon_slots", CLANKERS_DEFAULT_CHASSIS_WEAPON_SLOTS))
        used = 0
        for part_id in chassis.state.attachments:
            p = state.objects.get(part_id)
            if p is None or p.card_def is None:
                continue
            if _is_weapon(p.card_def):
                used += int(getattr(p.card_def, "weapon_slot_cost", 1))
        return max(0, cap - used)
    elif slot_type == "add_on":
        cap = int(getattr(chassis.card_def, "add_on_slots", CLANKERS_DEFAULT_CHASSIS_ADDON_SLOTS))
        used = sum(
            1 for part_id in chassis.state.attachments
            if (state.objects.get(part_id) is not None
                and _is_add_on(state.objects[part_id].card_def))
        )
        return max(0, cap - used)
    return 0


def attach_part(
    state: GameState,
    part_obj_id: str,
    target_chassis_id: str,
) -> list[Event]:
    """Validate slot availability + emit CLANKERS_ATTACH_PART + CLANKERS_PART_ATTACHED.

    Validation:
      1. Part and chassis both exist and live on the Assembly Floor.
      2. They share a controller.
      3. The chassis has an open slot of the correct type
         (weapon_slot_cost is honoured for weapons).
      4. Part is not already attached.

    On success: mutates part.state.attached_to and appends to chassis.state.attachments;
    runs the part's setup_interceptors so on_attach triggers + static add-on
    bonuses register; returns [CLANKERS_ATTACH_PART, CLANKERS_PART_ATTACHED, ...react].
    On failure: returns [].
    """
    _init_clankers_state(state)
    part = state.objects.get(part_obj_id)
    chassis = state.objects.get(target_chassis_id)
    if part is None or chassis is None:
        return []
    if part.card_def is None or chassis.card_def is None:
        return []
    if not _is_part(part.card_def):
        return []
    if not _is_chassis(chassis.card_def):
        return []
    if part.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR or chassis.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
        return []
    if part.controller != chassis.controller:
        return []
    if part.state.attached_to is not None:
        return []  # already attached somewhere
    slot_kind = "weapon" if _is_weapon(part.card_def) else "add_on"
    if _open_slots(state, chassis, slot_kind) < (
        int(getattr(part.card_def, "weapon_slot_cost", 1)) if slot_kind == "weapon" else 1
    ):
        return []

    # Perform the attach (the real event for triggers happens via the marker).
    attach_event = Event(
        type=EventType.CLANKERS_ATTACH_PART,
        payload={
            "part_id": part_obj_id,
            "target_chassis_id": target_chassis_id,
            "controller": part.controller,
        },
        source=part_obj_id,
        controller=part.controller,
    )
    part.state.attached_to = target_chassis_id
    if part_obj_id not in chassis.state.attachments:
        chassis.state.attachments.append(part_obj_id)

    # Register the part's own setup_interceptors (on_attach triggers, statics).
    _register_interceptors_for(part, state)

    marker = Event(
        type=EventType.CLANKERS_PART_ATTACHED,
        payload={
            "part_id": part_obj_id,
            "target_chassis_id": target_chassis_id,
            "controller": part.controller,
            "slot_kind": slot_kind,
        },
        source=part_obj_id,
        controller=part.controller,
    )
    _, reactions = _dispatch_interceptors(
        state, marker, priorities=(InterceptorPriority.REACT,),
    )
    return [attach_event, marker, *reactions]


def detach_part(state: GameState, part_obj_id: str) -> list[Event]:
    """Reverse of attach_part. Part stays on the floor as a solo part.

    Emits CLANKERS_DETACH_PART + CLANKERS_PART_DETACHED marker.
    """
    _init_clankers_state(state)
    part = state.objects.get(part_obj_id)
    if part is None or part.state.attached_to is None:
        return []
    former_host_id = part.state.attached_to
    chassis = state.objects.get(former_host_id)
    if chassis is not None and part_obj_id in chassis.state.attachments:
        chassis.state.attachments.remove(part_obj_id)
    part.state.attached_to = None

    detach_event = Event(
        type=EventType.CLANKERS_DETACH_PART,
        payload={"part_id": part_obj_id, "former_host_id": former_host_id},
        source=part_obj_id,
        controller=part.controller,
    )
    marker = Event(
        type=EventType.CLANKERS_PART_DETACHED,
        payload={"part_id": part_obj_id, "former_host_id": former_host_id},
        source=part_obj_id,
        controller=part.controller,
    )
    _, reactions = _dispatch_interceptors(
        state, marker, priorities=(InterceptorPriority.REACT,),
    )
    return [detach_event, marker, *reactions]


# =============================================================================
# Public API: effective power / integrity queries
# =============================================================================

def _base_power(chassis: GameObject) -> int:
    """Chassis printed power + sum of attached parts' power_bonus.

    Per contract clarification: we read attached parts directly here rather
    than requiring each attached part to register a TRANSFORM interceptor.
    Equivalent semantics, simpler control flow, fewer cards needing extra
    boilerplate. Card-level static effects (e.g. Structure global "+1 power")
    still come in via TRANSFORM interceptors on CLANKERS_QUERY_POWER, which
    the public function below applies on top of this base.
    """
    cd = chassis.card_def
    base = int(getattr(cd, "power", 0) or 0)
    if chassis._state_ref is None:
        return base
    state = chassis._state_ref
    for pid in chassis.state.attachments:
        p = state.objects.get(pid)
        if p is None or p.card_def is None:
            continue
        # Exhausted add-ons (tapped) don't contribute their static power.
        if p.state.tapped and _is_add_on(p.card_def):
            continue
        base += int(getattr(p.card_def, "power_bonus", 0) or 0)
    return base


def _base_integrity(chassis: GameObject) -> int:
    """Chassis printed integrity + sum of attached add-ons' integrity_bonus.

    Weapons contribute 0 integrity (per design §5).
    """
    cd = chassis.card_def
    base = int(getattr(cd, "integrity", 0) or 0)
    if chassis._state_ref is None:
        return base
    state = chassis._state_ref
    for pid in chassis.state.attachments:
        p = state.objects.get(pid)
        if p is None or p.card_def is None:
            continue
        if not _is_add_on(p.card_def):
            continue
        if p.state.tapped:
            # Exhausted add-on doesn't contribute its integrity_bonus (design §5)
            continue
        base += int(getattr(p.card_def, "integrity_bonus", 0) or 0)
    return base


def compute_effective_power(state: GameState, chassis_obj_id: str) -> int:
    """Emit CLANKERS_QUERY_POWER and let TRANSFORM-priority interceptors modify the result.

    Base = chassis.power + sum(attached parts' power_bonus). Interceptors
    (Structures, Core passives, etc.) can adjust ``payload['result']``.

    For solo parts, the base value is ``CLANKERS_SOLO_PART_POWER`` (== 1);
    we still dispatch interceptors so self-mobile / static-power interceptors
    that target the solo part's own id can apply their bonus.
    """
    chassis = state.objects.get(chassis_obj_id)
    if chassis is None or chassis.card_def is None:
        return 0
    if _is_chassis(chassis.card_def):
        base = _base_power(chassis)
    elif _is_part(chassis.card_def):
        # Solo part path — baseline 1, but still dispatch interceptors so
        # self-mobile bonuses (registered as CLANKERS_QUERY_POWER TRANSFORMs)
        # can apply. The combat manager has its own keyword-derived shortcut
        # for self-mobile, but any other caller (AI evaluators, card effects)
        # uses this path and expects the interceptor pipeline.
        base = CLANKERS_SOLO_PART_POWER
    else:
        return 0
    query = Event(
        type=EventType.CLANKERS_QUERY_POWER,
        payload={"chassis_id": chassis_obj_id, "base_value": base, "result": base},
        source=chassis_obj_id,
        controller=chassis.controller,
    )
    transformed, _ = _dispatch_interceptors(
        state, query, priorities=(InterceptorPriority.TRANSFORM,),
    )
    try:
        return int(transformed.payload.get("result", base))
    except (TypeError, ValueError):
        return base


def compute_effective_integrity(state: GameState, chassis_obj_id: str) -> int:
    """Emit CLANKERS_QUERY_INTEGRITY and let TRANSFORM interceptors modify the result.

    Solo parts dispatch with baseline ``CLANKERS_SOLO_PART_INTEGRITY`` (== 1)
    so self-mobile interceptors can adjust the result.
    """
    chassis = state.objects.get(chassis_obj_id)
    if chassis is None or chassis.card_def is None:
        return 0
    if _is_chassis(chassis.card_def):
        base = _base_integrity(chassis)
    elif _is_part(chassis.card_def):
        base = CLANKERS_SOLO_PART_INTEGRITY
    else:
        return 0
    query = Event(
        type=EventType.CLANKERS_QUERY_INTEGRITY,
        payload={"chassis_id": chassis_obj_id, "base_value": base, "result": base},
        source=chassis_obj_id,
        controller=chassis.controller,
    )
    transformed, _ = _dispatch_interceptors(
        state, query, priorities=(InterceptorPriority.TRANSFORM,),
    )
    try:
        return int(transformed.payload.get("result", base))
    except (TypeError, ValueError):
        return base


# =============================================================================
# Public API: refill / deathclock
# =============================================================================

def emit_refill_query(
    state: GameState,
    player_id: str,
    take: bool = True,
) -> list[Event]:
    """Allocate-phase refill. Emit CLANKERS_HAND_REFILL_QUERY + default-draws-to-7.

    Per contract: the turn manager asks the AI ``choose_refill(state, player_id)``
    and passes the resulting bool in as ``take``. We honour the may-decision
    by either drawing to 7 or emitting the CLANKERS_REFILL_DECLINED marker.

    ``state.clankers_refill_used[player_id]`` is set True either way to
    prevent re-firing within the same turn. The turn manager clears it at
    Cleanup.
    """
    _init_clankers_state(state)
    if state.clankers_refill_used.get(player_id, False):
        return []

    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    library = _ensure_zone(state, ZoneType.LIBRARY, player_id)
    current_hand_size = len(hand.objects)
    target = CLANKERS_HAND_FLOOR

    query = Event(
        type=EventType.CLANKERS_HAND_REFILL_QUERY,
        payload={
            "player_id": player_id,
            "current_hand_size": current_hand_size,
            "target_hand_size": target,
            "may": True,
        },
        source=None,
        controller=player_id,
    )
    transformed, reactions = _dispatch_interceptors(
        state, query,
        priorities=(InterceptorPriority.TRANSFORM, InterceptorPriority.REACT),
    )

    events: list[Event] = [transformed]
    events.extend(reactions)

    state.clankers_refill_used[player_id] = True

    if not take:
        events.append(Event(
            type=EventType.CLANKERS_REFILL_DECLINED,
            payload={"player_id": player_id, "current_hand_size": current_hand_size},
            source=None,
            controller=player_id,
        ))
        return events

    new_target = int(transformed.payload.get("target_hand_size", target))
    draw_count = max(0, new_target - current_hand_size)
    # Cap by library availability — we never auto-draw more than the library
    # holds. Empty-library handling is the deathclock's job, not this query's.
    draw_count = min(draw_count, len(library.objects))

    drawn_ids: list[str] = []
    for _ in range(draw_count):
        cid = _draw_one(state, player_id)
        if cid is None:
            break
        drawn_ids.append(cid)

    events.append(Event(
        type=EventType.CLANKERS_REFILL_TAKEN,
        payload={
            "player_id": player_id,
            "drew": len(drawn_ids),
            "card_ids": drawn_ids,
            "new_hand_size": len(_ensure_zone(state, ZoneType.HAND, player_id).objects),
        },
        source=None,
        controller=player_id,
    ))
    return events


def activate_deathclock_if_needed(state: GameState) -> list[Event]:
    """Containment Failure (deathclock) check.

    First call when both libraries are empty: set
    ``state.clankers_containment_failure = True``, ``containment_turn = 0``,
    no damage yet (the tick fires on the NEXT trigger).

    Subsequent calls (containment_failure already set): increment turn,
    compute damage = CLANKERS_DEATHCLOCK_BASE * (CLANKERS_DEATHCLOCK_MULTIPLIER ** turn),
    emit CLANKERS_CONTAINMENT_FAILURE_TICK + a DAMAGE event on each player's
    Core.

    Idempotent within a turn — the contract is "called at the end of each
    turn"; calling twice in the same Cleanup will tick twice. The turn
    manager must call exactly once per turn end.
    """
    _init_clankers_state(state)
    pids = list(state.players.keys())
    if not pids:
        return []

    if not state.clankers_containment_failure:
        # Activation requires BOTH libraries empty.
        all_empty = all(
            not _ensure_zone(state, ZoneType.LIBRARY, pid).objects
            for pid in pids
        )
        if not all_empty:
            return []
        state.clankers_containment_failure = True
        state.clankers_containment_turn = 0
        # Activation event (no damage on the first tick — sets up the clock).
        return [Event(
            type=EventType.CLANKERS_CONTAINMENT_FAILURE_TICK,
            payload={"turn": 0, "damage": 0, "activated": True},
            source=None,
        )]

    # Already activated — tick.
    turn = int(state.clankers_containment_turn) + 1
    state.clankers_containment_turn = turn
    damage = int(CLANKERS_DEATHCLOCK_BASE) * (int(CLANKERS_DEATHCLOCK_MULTIPLIER) ** (turn - 1))

    events: list[Event] = [Event(
        type=EventType.CLANKERS_CONTAINMENT_FAILURE_TICK,
        payload={"turn": turn, "damage": damage, "activated": False},
        source=None,
    )]
    for pid in pids:
        core_id = state.clankers_cores.get(pid)
        if core_id is None:
            continue
        # Direct workshop-integrity drain (the engine doesn't need a full
        # DAMAGE pipeline for the deathclock — apply the subtraction here so
        # smoke tests / non-pipeline drivers see the same outcome).
        current = int(state.clankers_workshop_integrity.get(pid, 0))
        state.clankers_workshop_integrity[pid] = max(0, current - damage)
        events.append(Event(
            type=EventType.CLANKERS_WORKSHOP_DAMAGE,
            payload={
                "target": core_id,
                "player_id": pid,
                "amount": damage,
                "reason": "containment_failure",
                "new_integrity": state.clankers_workshop_integrity[pid],
            },
            source=core_id,
            controller=pid,
        ))
    return events


def check_workshop_breached(state: GameState) -> Optional[str]:
    """Return the player_id of any player whose workshop_integrity <= 0, else None.

    If both players hit 0 in the same step (simultaneous breach), returns the
    first one we encounter — the design says simultaneous is a draw, but
    the turn manager can re-check and route to a draw event explicitly. For
    Stage 1 we just report a single loser; the turn manager owns the
    draw-detection logic if it needs it.
    """
    _init_clankers_state(state)
    for pid, integrity in state.clankers_workshop_integrity.items():
        if int(integrity) <= 0:
            state.clankers_loser = pid
            return pid
    return None


# =============================================================================
# Public API: death cascade
# =============================================================================

def death_cascade(state: GameState, chassis_obj_id: str) -> list[Event]:
    """Destroy a chassis and scatter all its attached parts to scrap simultaneously.

    Emits, in order:
      1. CLANKERS_CHASSIS_DESTROYED marker (for the chassis itself)
      2. CLANKERS_DEATH_CASCADE marker (one, with the full list of cascaded ids)
      3. For each cascaded part: CLANKERS_WEAPON_DESTROYED or
         CLANKERS_ADD_ON_DESTROYED marker (plus OBJECT_DESTROYED for pipeline
         observability).
      4. REACT-priority reactions from any of the above.

    All parts move to the chassis owner's CLANKERS_SCRAP_HEAP zone. The
    chassis itself also moves to the scrap heap (parts came from cards in
    the same workshop).
    """
    _init_clankers_state(state)
    chassis = state.objects.get(chassis_obj_id)
    if chassis is None:
        return []
    if chassis.card_def is None or not _is_chassis(chassis.card_def):
        return []

    controller = chassis.controller
    cascaded_part_ids: list[str] = list(chassis.state.attachments)

    events: list[Event] = []

    # 1. Chassis destruction marker.
    events.append(Event(
        type=EventType.CLANKERS_CHASSIS_DESTROYED,
        payload={
            "chassis_id": chassis_obj_id,
            "controller": controller,
            "cascaded_part_ids": list(cascaded_part_ids),
        },
        source=chassis_obj_id,
        controller=controller,
    ))

    # 2. Cascade marker (single event with the bundle of ids — triggers key on
    # this one to know "this damage just produced a 3-for-1").
    events.append(Event(
        type=EventType.CLANKERS_DEATH_CASCADE,
        payload={
            "chassis_id": chassis_obj_id,
            "cascaded_part_ids": list(cascaded_part_ids),
            "controller": controller,
        },
        source=chassis_obj_id,
        controller=controller,
    ))

    # 3. Move the chassis itself to the scrap heap.
    floor = _ensure_zone(state, ZoneType.CLANKERS_ASSEMBLY_FLOOR, controller)
    if chassis_obj_id in floor.objects:
        floor.objects.remove(chassis_obj_id)
    scrap = _ensure_zone(state, ZoneType.CLANKERS_SCRAP_HEAP, controller)
    scrap.objects.append(chassis_obj_id)
    chassis.zone = ZoneType.CLANKERS_SCRAP_HEAP
    chassis.entered_zone_at = state.next_timestamp()
    # Detach all parts (state-level) — they no longer have a host.
    chassis.state.attachments = []
    # Remove the chassis from per-player assembly list.
    state.clankers_assemblies.setdefault(controller, [])
    if chassis_obj_id in state.clankers_assemblies[controller]:
        state.clankers_assemblies[controller].remove(chassis_obj_id)

    # 4. Scatter each part. Specific markers per-type fire so triggers can
    # filter on weapon-death vs add-on-death.
    for part_id in cascaded_part_ids:
        part = state.objects.get(part_id)
        if part is None:
            continue
        part_controller = part.controller
        # Move to scrap heap.
        owner_floor = _ensure_zone(state, ZoneType.CLANKERS_ASSEMBLY_FLOOR, part_controller)
        if part_id in owner_floor.objects:
            owner_floor.objects.remove(part_id)
        owner_scrap = _ensure_zone(state, ZoneType.CLANKERS_SCRAP_HEAP, part_controller)
        owner_scrap.objects.append(part_id)
        part.zone = ZoneType.CLANKERS_SCRAP_HEAP
        part.entered_zone_at = state.next_timestamp()
        part.state.attached_to = None

        if _is_weapon(part.card_def):
            events.append(Event(
                type=EventType.CLANKERS_WEAPON_DESTROYED,
                payload={
                    "part_id": part_id,
                    "former_host_id": chassis_obj_id,
                    "controller": part_controller,
                    "cascade_from": chassis_obj_id,
                },
                source=part_id,
                controller=part_controller,
            ))
        elif _is_add_on(part.card_def):
            events.append(Event(
                type=EventType.CLANKERS_ADD_ON_DESTROYED,
                payload={
                    "part_id": part_id,
                    "former_host_id": chassis_obj_id,
                    "controller": part_controller,
                    "cascade_from": chassis_obj_id,
                },
                source=part_id,
                controller=part_controller,
            ))

        # OBJECT_DESTROYED so generic graveyard / leaves-battlefield observers
        # also fire. This is what the pipeline-level death-cascade hook keys
        # on per the contract §10.
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={
                "object_id": part_id,
                "reason": "death_cascade",
                "cascade_from": chassis_obj_id,
            },
            source=chassis_obj_id,
            controller=part_controller,
        ))

    # OBJECT_DESTROYED for the chassis itself (the pipeline-level death cascade
    # is usually triggered FROM an OBJECT_DESTROYED — but in case death_cascade
    # was invoked directly by combat-resolution code, emit it for downstream
    # observers).
    events.append(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": chassis_obj_id, "reason": "chassis_destroyed"},
        source=chassis_obj_id,
        controller=controller,
    ))

    # Run REACT-priority interceptors on every emitted event so on_self_destroyed
    # / on_host_destroyed triggers can fire.
    follow_ups: list[Event] = []
    for ev in list(events):
        _, reactions = _dispatch_interceptors(
            state, ev, priorities=(InterceptorPriority.REACT,),
        )
        follow_ups.extend(reactions)
    events.extend(follow_ups)
    return events


# =============================================================================
# Public API: top-level play dispatcher
# =============================================================================

def _move_card_to_floor(state: GameState, player_id: str, obj: GameObject) -> None:
    """Move ``obj`` from HAND to CLANKERS_ASSEMBLY_FLOOR + book-keep zones."""
    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    if obj.id in hand.objects:
        hand.objects.remove(obj.id)
    floor = _ensure_zone(state, ZoneType.CLANKERS_ASSEMBLY_FLOOR, player_id)
    if obj.id not in floor.objects:
        floor.objects.append(obj.id)
    obj.zone = ZoneType.CLANKERS_ASSEMBLY_FLOOR
    obj.entered_zone_at = state.next_timestamp()
    obj.controller = player_id


def _move_card_to_scrap(state: GameState, player_id: str, obj: GameObject) -> None:
    """Send a card from HAND (or anywhere) into the player's SCRAP_HEAP."""
    hand = _ensure_zone(state, ZoneType.HAND, player_id)
    if obj.id in hand.objects:
        hand.objects.remove(obj.id)
    scrap = _ensure_zone(state, ZoneType.CLANKERS_SCRAP_HEAP, player_id)
    if obj.id not in scrap.objects:
        scrap.objects.append(obj.id)
    obj.zone = ZoneType.CLANKERS_SCRAP_HEAP
    obj.entered_zone_at = state.next_timestamp()
    obj.controller = player_id


def play_card_from_hand(
    state: GameState,
    player_id: str,
    card_obj_id: str,
    **kwargs: Any,
) -> list[Event]:
    """Top-level dispatcher: route by CardType to the per-type play path.

    kwargs honoured per CardType:
      - CLANKERS_WEAPON / CLANKERS_ADD_ON: ``target_chassis_id: Optional[str]``
        (None = play solo).
      - CLANKERS_TRANSIENT: ``targets: list[str]`` is passed into the
        card's resolve_fn via the synthetic event payload.

    Pays compute_cost first, then performs the action. Returns the event list
    in dispatch order: COMPUTE_SPEND → type-specific events.
    """
    _init_clankers_state(state)
    obj = state.objects.get(card_obj_id)
    if obj is None or obj.card_def is None:
        return []

    cd = obj.card_def
    compute_cost = int(getattr(cd, "compute_cost", 0) or 0)

    # Validate affordability before doing anything irreversible.
    available = int(state.clankers_compute_pool.get(player_id, 0))
    if compute_cost > available:
        return []

    events: list[Event] = []
    events.extend(_spend_compute(state, player_id, compute_cost, card_obj_id))

    if _is_chassis(cd):
        events.extend(_play_chassis(state, player_id, obj))
    elif _is_weapon(cd):
        target = kwargs.get("target_chassis_id")
        events.extend(_play_part(state, player_id, obj, target))
    elif _is_add_on(cd):
        target = kwargs.get("target_chassis_id")
        events.extend(_play_part(state, player_id, obj, target))
    elif _is_transient(cd):
        targets = list(kwargs.get("targets") or [])
        events.extend(_play_transient(state, player_id, obj, targets))
    elif _is_structure(cd):
        events.extend(_play_structure(state, player_id, obj))
    else:
        # Unknown card type for clankers — silently no-op so future card types
        # don't crash the dispatcher; return the compute-spend so the caller
        # sees the cost was paid (defensive).
        pass

    return events


def _play_chassis(state: GameState, player_id: str, obj: GameObject) -> list[Event]:
    """Play a chassis from hand to the Assembly Floor."""
    _move_card_to_floor(state, player_id, obj)
    state.clankers_assemblies.setdefault(player_id, [])
    if obj.id not in state.clankers_assemblies[player_id]:
        state.clankers_assemblies[player_id].append(obj.id)
    _register_interceptors_for(obj, state)
    events: list[Event] = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": player_id,
            "card_type": "CLANKERS_CHASSIS",
        },
        source=obj.id,
        controller=player_id,
    )]
    return events


def _play_part(
    state: GameState,
    player_id: str,
    obj: GameObject,
    target_chassis_id: Optional[str],
) -> list[Event]:
    """Play a weapon/add-on from hand. Optionally attach to a chassis immediately.

    If ``target_chassis_id`` is None, the part lands solo on the floor.
    If attach fails (invalid target / no slot), the part still lands on the
    floor as solo — design §4 "solo parts" is the explicit fallback.
    """
    _move_card_to_floor(state, player_id, obj)
    events: list[Event] = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": player_id,
            "card_type": (
                "CLANKERS_WEAPON" if _is_weapon(obj.card_def) else "CLANKERS_ADD_ON"
            ),
        },
        source=obj.id,
        controller=player_id,
    )]
    if target_chassis_id is not None:
        attach_events = attach_part(state, obj.id, target_chassis_id)
        if attach_events:
            events.extend(attach_events)
        else:
            # Attach failed (no slot, wrong controller, etc.) — register the
            # part's setup_interceptors anyway so solo-part triggers can still
            # fire.
            _register_interceptors_for(obj, state)
    else:
        # Solo part — still register setup_interceptors so triggers like
        # on_self_destroyed work.
        _register_interceptors_for(obj, state)
    return events


def _play_transient(
    state: GameState,
    player_id: str,
    obj: GameObject,
    targets: list[str],
) -> list[Event]:
    """Resolve a Transient and send the card to the scrap heap.

    The card's resolve_fn (stored at ``card_def.clankers_resolve``) is invoked
    with a synthetic CLANKERS_TURN_START-ish event carrying the player and
    targets. If no resolve_fn is registered, the card just goes to scrap (
    no-op effect — useful for placeholder cards in scaffolding tests).
    """
    resolve_fn = getattr(obj.card_def, "clankers_resolve", None)
    events: list[Event] = []
    if callable(resolve_fn):
        synth = Event(
            type=EventType.CLANKERS_COMPUTE_SPEND,  # repurposed as the "resolve trigger"
            payload={
                "transient_id": obj.id,
                "controller": player_id,
                "targets": list(targets),
            },
            source=obj.id,
            controller=player_id,
        )
        try:
            new_events = resolve_fn(synth, state) or []
        except Exception:
            new_events = []
        events.extend(new_events)
    _move_card_to_scrap(state, player_id, obj)
    return events


def _play_structure(state: GameState, player_id: str, obj: GameObject) -> list[Event]:
    """Play a Structure to the Assembly Floor; enforce the 3-cap.

    If the cap is exceeded, the 4th Structure replaces the oldest one (FIFO).
    Card-author-visible behaviour: the design says "player chooses which to
    scrap" — but Stage 1 just FIFO-evicts. The turn manager can implement a
    choose-which-to-scrap UI in a later pass if needed.
    """
    state.clankers_structures.setdefault(player_id, [])
    structures = state.clankers_structures[player_id]

    if len(structures) >= CLANKERS_MAX_STRUCTURES:
        oldest_id = structures.pop(0)
        oldest_obj = state.objects.get(oldest_id)
        if oldest_obj is not None:
            _move_card_to_scrap(state, player_id, oldest_obj)

    _move_card_to_floor(state, player_id, obj)
    structures.append(obj.id)
    _register_interceptors_for(obj, state)
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": player_id,
            "card_type": "CLANKERS_STRUCTURE",
        },
        source=obj.id,
        controller=player_id,
    )]


# =============================================================================
# Card factories (see contract §4)
# =============================================================================

def make_chassis(
    name: str,
    *,
    power: int,
    integrity: int,
    weapon_slots: int = CLANKERS_DEFAULT_CHASSIS_WEAPON_SLOTS,
    add_on_slots: int = CLANKERS_DEFAULT_CHASSIS_ADDON_SLOTS,
    compute_cost: int = 2,
    text: str = "",
    rarity: str = "common",
    clankers_archetype: Optional[str] = None,
    setup_interceptors: Optional[Callable] = None,
) -> CardDefinition:
    """Build a chassis card. Power/integrity are stored on card_def directly
    (not on characteristics) so the engine reads them via getattr."""
    chars = Characteristics(
        types={CardType.CLANKERS_CHASSIS},
        subtypes={"Chassis"},
        power=power,
        toughness=integrity,
    )
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain="CLANKERS",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.compute_cost = int(compute_cost)
    card_def.power = int(power)
    card_def.integrity = int(integrity)
    card_def.weapon_slots = int(weapon_slots)
    card_def.add_on_slots = int(add_on_slots)
    card_def.clankers_archetype = clankers_archetype
    card_def.clankers_keywords = []
    return card_def


def make_weapon(
    name: str,
    *,
    power_bonus: int,
    compute_cost: int = 1,
    weapon_slot_cost: int = 1,
    integrity_bonus: int = 0,
    clankers_keywords: Optional[list[str]] = None,
    text: str = "",
    rarity: str = "common",
    clankers_archetype: Optional[str] = None,
    setup_interceptors: Optional[Callable] = None,
) -> CardDefinition:
    """Build a weapon card. Adds power_bonus when attached.

    weapon_slot_cost defaults to 1; massive weapons can cost 2 slots.
    integrity_bonus is supported (defaults 0) for the rare "barbed armor"-type
    weapon that grants integrity too.
    """
    chars = Characteristics(
        types={CardType.CLANKERS_WEAPON},
        subtypes={"Weapon"},
        power=CLANKERS_SOLO_PART_POWER,
        toughness=CLANKERS_SOLO_PART_INTEGRITY,
    )
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain="CLANKERS",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.compute_cost = int(compute_cost)
    card_def.power_bonus = int(power_bonus)
    card_def.integrity_bonus = int(integrity_bonus)
    card_def.weapon_slot_cost = int(weapon_slot_cost)
    card_def.clankers_keywords = list(clankers_keywords or [])
    card_def.clankers_archetype = clankers_archetype
    return card_def


def make_add_on(
    name: str,
    *,
    integrity_bonus: int = 0,
    power_bonus: int = 0,
    compute_cost: int = 1,
    armor_value: Optional[int] = None,
    clankers_keywords: Optional[list[str]] = None,
    text: str = "",
    rarity: str = "common",
    clankers_archetype: Optional[str] = None,
    setup_interceptors: Optional[Callable] = None,
) -> CardDefinition:
    """Build an add-on card. Adds integrity_bonus (and optionally power_bonus)
    when attached. armor_value (with the 'armor' keyword) enables damage
    absorption via a TRANSFORM interceptor (registered by the card's
    setup_interceptors, usually via ``make_armor``).
    """
    chars = Characteristics(
        types={CardType.CLANKERS_ADD_ON},
        subtypes={"Add-On"},
        power=CLANKERS_SOLO_PART_POWER,
        toughness=CLANKERS_SOLO_PART_INTEGRITY,
    )
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain="CLANKERS",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.compute_cost = int(compute_cost)
    card_def.power_bonus = int(power_bonus)
    card_def.integrity_bonus = int(integrity_bonus)
    card_def.armor_value = armor_value
    keywords = list(clankers_keywords or [])
    if armor_value is not None and "armor" not in keywords:
        keywords.append("armor")
    card_def.clankers_keywords = keywords
    card_def.clankers_archetype = clankers_archetype
    return card_def


def make_transient(
    name: str,
    *,
    compute_cost: int,
    resolve_fn: Callable[[Event, GameState], list[Event]],
    text: str = "",
    rarity: str = "common",
    clankers_archetype: Optional[str] = None,
) -> CardDefinition:
    """Build a Transient (one-shot subroutine). resolve_fn is invoked on play."""
    chars = Characteristics(
        types={CardType.CLANKERS_TRANSIENT},
        subtypes={"Transient"},
        power=0,
        toughness=0,
    )
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain="CLANKERS",
        text=text,
        rarity=rarity,
    )
    card_def.compute_cost = int(compute_cost)
    card_def.clankers_resolve = resolve_fn
    card_def.clankers_archetype = clankers_archetype
    card_def.clankers_keywords = []
    return card_def


def make_structure(
    name: str,
    *,
    compute_cost: int = 2,
    setup_interceptors: Callable[[GameObject, GameState], list[Interceptor]],
    text: str = "",
    rarity: str = "rare",
    clankers_archetype: Optional[str] = None,
) -> CardDefinition:
    """Build a Structure (workshop fixture). setup_interceptors registers the
    global passive when the structure enters the floor."""
    chars = Characteristics(
        types={CardType.CLANKERS_STRUCTURE},
        subtypes={"Structure"},
        power=0,
        toughness=0,
    )
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain="CLANKERS",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    card_def.compute_cost = int(compute_cost)
    card_def.clankers_archetype = clankers_archetype
    card_def.clankers_keywords = []
    return card_def


def make_core(
    name: str,
    *,
    workshop_integrity: int = CLANKERS_STARTING_WORKSHOP_INTEGRITY,
    passive_setup: Optional[Callable[[GameObject, GameState], list[Interceptor]]] = None,
    text: str = "",
    flavor: str = "",
) -> CardDefinition:
    """Build a Core Processor (commander-equivalent). passive_setup, if given,
    is called on game setup to register the Core's always-on passive
    interceptors with ``duration='forever'``."""
    chars = Characteristics(
        types={CardType.CLANKERS_CORE},
        subtypes={"Core"},
        power=0,
        toughness=workshop_integrity,
    )
    card_def = CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=chars,
        domain="CLANKERS",
        text=text,
        rarity="mythic",
    )
    card_def.workshop_integrity = int(workshop_integrity)
    card_def.clankers_core_passive_setup = passive_setup
    card_def.clankers_flavor = flavor
    card_def.clankers_keywords = []
    return card_def


# =============================================================================
# Helper interceptor builders (for card scripts)
# =============================================================================

def make_chassis_etb_trigger(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    description: str = "",
) -> Interceptor:
    """REACT-priority trigger that fires when this chassis enters the floor.

    Filters on ZONE_CHANGE with object_id == obj.id and to_zone =
    CLANKERS_ASSEMBLY_FLOOR.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("object_id") != obj.id:
            return False
        return event.payload.get("to_zone") in (
            ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        )

    def handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=f"{obj.id}_chassis_etb",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "Chassis ETB",
    )


def make_part_on_attach(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    description: str = "",
) -> Interceptor:
    """Fires when this part attaches to a host chassis."""
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_PART_ATTACHED:
            return False
        return event.payload.get("part_id") == obj.id

    def handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=f"{obj.id}_on_attach",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On attach",
    )


def make_part_on_host_attack(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    description: str = "",
) -> Interceptor:
    """Fires on CLANKERS_ATTACK_DECLARE when the attacker is this part's host."""
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_ATTACK_DECLARE:
            return False
        return event.payload.get("attacker_id") == obj.state.attached_to

    def handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=f"{obj.id}_on_host_attack",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On host attack",
    )


def make_part_on_host_destroyed(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    description: str = "",
) -> Interceptor:
    """Fires when this part's host chassis is destroyed (death cascade)."""
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_CHASSIS_DESTROYED:
            return False
        # The host id may have already been cleared from obj.state.attached_to
        # by the time death_cascade emits OBJECT_DESTROYED for the part. To
        # cover both orderings, check the cascade list.
        chassis_id = event.payload.get("chassis_id")
        if obj.state.attached_to == chassis_id:
            return True
        cascaded = event.payload.get("cascaded_part_ids", []) or []
        return obj.id in cascaded

    def handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=f"{obj.id}_on_host_destroyed",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On host destroyed",
    )


def make_part_on_self_destroyed(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    description: str = "",
) -> Interceptor:
    """Fires when this part itself is destroyed (cascade or direct).

    The destroyed-part-id is carried under either ``part_id`` (death_cascade
    helper) or ``object_id`` (combat manager's direct-destroy path). Accept
    both so the trigger fires regardless of which path destroyed the part.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type not in (
            EventType.CLANKERS_WEAPON_DESTROYED,
            EventType.CLANKERS_ADD_ON_DESTROYED,
        ):
            return False
        pid = event.payload.get("part_id") or event.payload.get("object_id")
        return pid == obj.id

    def handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=f"{obj.id}_on_self_destroyed",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On self destroyed",
    )


def make_weapon_activated(
    obj: GameObject,
    *,
    compute_cost: int = 0,
    exhaust_self: bool = False,
    effect_fn: Callable[[Event, GameState], list[Event]],
    description: str = "",
) -> Interceptor:
    """Register a weapon's activated ability. Stored on obj.state.activated_abilities
    (reused descriptor list — same shape as MTG Phase-4 activated abilities) so
    the legal-actions enumerator can surface it.

    Returns a sentinel interceptor whose lifecycle tracks the ability — it
    doesn't fire on any event (filter returns False), but its presence in
    obj.interceptor_ids lets the standard cleanup path remove the ability if
    the weapon leaves the battlefield.
    """
    descriptor = {
        "kind": "clankers_activated",
        "source_id": obj.id,
        "compute_cost": int(compute_cost),
        "exhaust_self": bool(exhaust_self),
        "effect_fn": effect_fn,
        "description": description,
    }
    # Reuse the existing list; many objects may have multiple activated abilities.
    obj.state.activated_abilities.append(descriptor)

    def _never(event: Event, state: GameState) -> bool:
        return False

    def _noop(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PASS)

    return Interceptor(
        id=f"{obj.id}_activated_{len(obj.state.activated_abilities)}",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_never,
        handler=_noop,
        description=description or "Activated ability descriptor",
    )


def activate_ability(
    state: GameState,
    player_id: str,
    source_obj_id: str,
    *,
    ability_index: int = 0,
    targets: Optional[list[str]] = None,
) -> list[Event]:
    """Dispatch an activated ability on a source object.

    Resolves the descriptor stored at
    ``state.objects[source_obj_id].state.activated_abilities[ability_index]``
    (written by ``make_weapon_activated``), validates ownership + cost
    payability, mutates state to pay the cost (compute pool decrement and/or
    self-exhaust), and invokes ``effect_fn(synth_event, state)``.

    Returns a list of events: ``[CLANKERS_ACTIVATE marker, *cost_events,
    *effect_events]``. Returns ``[]`` (no state mutation) on any of:
      - missing source object
      - controller mismatch
      - missing/invalid ability_index
      - insufficient compute
      - already-tapped source when ``exhaust_self=True``

    NB: descriptors may write their own scrap/secondary costs inside
    ``effect_fn`` (returning ``[]`` if they can't pay). The function-level
    cost paid here is the ``compute_cost``/``exhaust_self`` declared on the
    descriptor itself.
    """
    _init_clankers_state(state)
    source = state.objects.get(source_obj_id) if source_obj_id else None
    if source is None:
        return []
    if getattr(source, "controller", None) != player_id:
        return []
    abilities = getattr(getattr(source, "state", None), "activated_abilities", None) or []
    if not isinstance(ability_index, int) or ability_index < 0 or ability_index >= len(abilities):
        return []
    descriptor = abilities[ability_index]
    # Descriptors are dicts written by make_weapon_activated, but tolerate
    # either dict access or attribute access for future flexibility.
    def _read(key: str, default=None):
        if isinstance(descriptor, dict):
            return descriptor.get(key, default)
        return getattr(descriptor, key, default)

    compute_cost = int(_read("compute_cost", 0) or 0)
    exhaust_self = bool(_read("exhaust_self", False))
    effect_fn = _read("effect_fn")
    if effect_fn is None:
        return []

    # Cost-pay phase: validate everything BEFORE mutating state.
    pool = int(state.clankers_compute_pool.get(player_id, 0))
    if compute_cost > 0 and pool < compute_cost:
        return []
    if exhaust_self and bool(getattr(source.state, "tapped", False)):
        return []

    events: list[Event] = []

    # 1. Pay compute (routes through _spend_compute so cost-reduction
    #    interceptors can TRANSFORM the amount).
    if compute_cost > 0:
        events.extend(_spend_compute(state, player_id, compute_cost, source_obj_id))

    # 2. Pay exhaust.
    if exhaust_self:
        source.state.tapped = True

    # 3. Emit the activation marker (placed before effect events so observers
    #    see the activation in order).
    activate_marker = Event(
        type=EventType.CLANKERS_ACTIVATE,
        payload={
            "player_id": player_id,
            "source_id": source_obj_id,
            "ability_index": int(ability_index),
            "targets": list(targets or []),
            "compute_paid": compute_cost,
            "exhausted_self": exhaust_self,
            "description": _read("description", ""),
        },
        source=source_obj_id,
        controller=player_id,
    )
    events.append(activate_marker)

    # 4. Build synthetic activation event and dispatch effect.
    synth = Event(
        type=EventType.CLANKERS_ACTIVATE,
        payload={
            "source": source_obj_id,
            "ability_index": int(ability_index),
            "targets": list(targets or []),
            "controller": player_id,
        },
        source=source_obj_id,
        controller=player_id,
    )
    try:
        effect_events = effect_fn(synth, state) or []
    except Exception:
        effect_events = []
    events.extend(effect_events)
    return events


def make_add_on_static_power(obj: GameObject, power_mod: int) -> Interceptor:
    """TRANSFORM-priority interceptor on CLANKERS_QUERY_POWER for the host.

    Adds ``power_mod`` to ``payload['result']`` when the queried chassis is
    this add-on's host. The base power addition from ``power_bonus`` is read
    directly by _base_power, so this is for non-trivial static effects beyond
    flat bonuses (e.g. conditional bonuses based on board state).
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_POWER:
            return False
        host_id = obj.state.attached_to
        return host_id is not None and event.payload.get("chassis_id") == host_id

    def handler(event: Event, state: GameState) -> InterceptorResult:
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
        id=f"{obj.id}_static_power",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description=f"+{power_mod} static power to host",
    )


def make_add_on_static_integrity(obj: GameObject, integrity_mod: int) -> Interceptor:
    """TRANSFORM-priority on CLANKERS_QUERY_INTEGRITY for the host."""
    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        host_id = obj.state.attached_to
        return host_id is not None and event.payload.get("chassis_id") == host_id

    def handler(event: Event, state: GameState) -> InterceptorResult:
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
        id=f"{obj.id}_static_integrity",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description=f"+{integrity_mod} static integrity to host",
    )


def make_armor(obj: GameObject, armor_value: int) -> Interceptor:
    """TRANSFORM on DAMAGE / CLANKERS_COMBAT_DAMAGE targeting the host.

    When triggered, decrements the damage amount by up to ``armor_value``
    and exhausts the add-on (sets state.tapped = True). The exhausted add-on
    no longer contributes its integrity_bonus until next Boot.

    Single-use per "ready" cycle — once tapped, the filter returns False so
    the same add-on can't absorb twice in one turn.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
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
        # Both 'target' (DAMAGE) and 'defender_id' (CLANKERS_COMBAT_DAMAGE)
        # payload shapes are honoured.
        target = event.payload.get("target") or event.payload.get("defender_id")
        return target == host_id

    def handler(event: Event, state: GameState) -> InterceptorResult:
        new_payload = dict(event.payload)
        amount_key = "amount" if "amount" in new_payload else "damage"
        amount = int(new_payload.get(amount_key, 0))
        absorbed = min(int(armor_value), amount)
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
        )

    return Interceptor(
        id=f"{obj.id}_armor",
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description=f"Armor {armor_value} (exhaust)",
    )


def make_structure_global(
    obj: GameObject,
    modifier_fn: Callable[[Event, GameState], InterceptorResult],
    *,
    description: str = "",
    priority: InterceptorPriority = InterceptorPriority.TRANSFORM,
) -> Interceptor:
    """Register a Structure's global passive effect.

    ``modifier_fn`` is the full handler — ``(event, state) -> InterceptorResult``
    — because Structure passives vary too widely to have a single shape.
    The Structure card author wires their own filter into modifier_fn via
    a closure if needed; this helper just packages the registration.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        # Permissive filter — modifier_fn is expected to decide. Structures
        # rarely need to be hyper-selective here.
        return obj.zone == ZoneType.CLANKERS_ASSEMBLY_FLOOR

    return Interceptor(
        id=f"{obj.id}_structure_global",
        source=obj.id,
        controller=obj.controller,
        priority=priority,
        filter=filter_fn,
        handler=modifier_fn,
        description=description or "Structure global passive",
        duration="while_on_battlefield",
    )


def make_core_passive(
    obj: GameObject,
    modifier_fn: Callable[[Event, GameState], InterceptorResult],
    *,
    description: str = "",
    priority: InterceptorPriority = InterceptorPriority.REACT,
) -> Interceptor:
    """Register a Core Processor's always-on passive.

    Duration is 'forever' — Cores cannot leave the COMMAND zone, so the
    interceptor never gets cleaned up by the standard cleanup path. ``is_core``
    is marked via the description for downstream silence/disenchant guards;
    we don't (yet) need a dedicated field.
    """
    def filter_fn(event: Event, state: GameState) -> bool:
        # The author's modifier_fn does its own filtering.
        return True

    ic = Interceptor(
        id=f"{obj.id}_core_passive",
        source=obj.id,
        controller=obj.controller,
        priority=priority,
        filter=filter_fn,
        handler=modifier_fn,
        description=description or "Core passive",
        duration="forever",
    )
    return ic


# =============================================================================
# Mode adapter (lazy-built; see cats.py:1233 for pattern)
# =============================================================================

def _clankers_mode_adapter_class():
    """Build the ClankersModeAdapter class lazily to dodge the
    mode_adapter <-> clankers import cycle.
    """
    from src.engine.mode_adapter import GameModeAdapter

    class ClankersModeAdapter(GameModeAdapter):
        """Mode adapter for the Clankers engine.

        Hooks overridden:
          - default_max_hand_size: None (hand size is soft-floored at 7, no cap)
          - create_mana_system: None (Compute is per-player flat state, not a ManaSystem)
          - handle_empty_library_draw: returns containment-failure activation
            events instead of auto-losing the game.
          - setup_starting_hands: setup_clankers_player already drew the
            opening 7, so skip the MTG mulligan flow.

        Damage persists across turns in Clankers (chassis.state.damage_marked
        is intentionally NOT cleared on cleanup) — we rely on
        ``state.clear_damage_on_cleanup = False`` set at setup time.
        """

        mode = "clankers"

        def default_max_hand_size(self):
            # No cap; design §3 specifies the floor is 7 and hand can grow above.
            return None

        def overdraw_burns(self, state) -> bool:
            return False

        def create_mana_system(self, state):
            # Compute lives in state.clankers_compute_pool; no ManaSystem.
            return None

        def handle_empty_library_draw(self, player, state):
            """Empty-library does NOT auto-lose the game; trigger the
            containment-failure check instead. The deathclock is the loss
            condition under deck-out (design §1).
            """
            return activate_deathclock_if_needed(state)

        async def setup_starting_hands(self, game, player_ids):
            """setup_clankers_player has already drawn the opening 7; skip
            the standard MTG mulligan flow."""
            return True

        def create_combat_manager(self, state):
            # ClankersCombatManager accepts either a Game or a GameState.
            # The mode_adapter factory only has ``state``; the manager will
            # resolve the Game back-ref via ``state._game`` when needed.
            from src.engine.clankers_combat import ClankersCombatManager
            return ClankersCombatManager(state)

        def create_turn_manager(self, state):
            from src.engine.clankers_turn import ClankersTurnManager
            return ClankersTurnManager(state)

        def register_ai_player(self, game, player_id):
            if hasattr(game.turn_manager, "set_ai_player"):
                game.turn_manager.set_ai_player(player_id)

        def includes_game_log_in_state(self):
            return True

    return ClankersModeAdapter


def ClankersModeAdapter(*args, **kwargs):
    """Public constructor — produces a ClankersModeAdapter instance via the
    lazy class builder. Mirrors the cats.py:1270 pattern."""
    cls = _clankers_mode_adapter_class()
    return cls(*args, **kwargs)
