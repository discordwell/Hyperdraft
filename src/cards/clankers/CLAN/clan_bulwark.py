"""CLAN — BULWARK-9 archetype (Containment Doctrine / artillery) + neutrals.

~37 cards: 1 Core (BULWARK-9), 10 Chassis (9 artillery + 1 neutral),
12 Weapons (8 artillery + 4 neutral), 8 Add-Ons, 4 Transients (3 artillery
+ 1 neutral), 3 Structures. Artillery wants armor stacking, exhausted-add-on
payoffs, and deathclock-acceleration to win the long game.
"""

from __future__ import annotations

from src.engine import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    CardType,
    ZoneType,
    new_id,
)
from src.engine.clankers import (
    CLANKERS_STARTING_WORKSHOP_INTEGRITY,
    _ensure_zone,
    _gain_scrap,
    _is_add_on,
    _is_chassis,
    _is_weapon,
    attach_part,
    compute_effective_power,
    make_add_on,
    make_add_on_static_power,
    make_armor,
    make_chassis,
    make_chassis_etb_trigger,
    make_core,
    make_core_passive,
    make_part_on_attach,
    make_part_on_host_attack,
    make_part_on_host_destroyed,
    make_part_on_self_destroyed,
    make_structure,
    make_structure_global,
    make_transient,
    make_weapon,
    make_weapon_activated,
)


# =============================================================================
# Constants
# =============================================================================

BULWARK_9_MAX_INTEGRITY = 27
ARTILLERY = "artillery"
NEUTRAL = "neutral"


# =============================================================================
# Local helper closures (BULWARK-flavoured)
# =============================================================================

def _opponent_id(state: GameState, player_id: str) -> str | None:
    """Return the id of the other player, or None if not found."""
    for pid in state.players.keys():
        if pid != player_id:
            return pid
    return None


def _count_exhausted_add_ons(state: GameState, player_id: str) -> int:
    """Count add-ons on the Assembly Floor controlled by player_id that are tapped."""
    count = 0
    for obj in state.objects.values():
        if obj.card_def is None:
            continue
        if not _is_add_on(obj.card_def):
            continue
        if obj.controller != player_id:
            continue
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            continue
        if obj.state.tapped:
            count += 1
    return count


def _heal_workshop(state: GameState, player_id: str, amount: int) -> None:
    """Add ``amount`` to workshop_integrity, capped at BULWARK_9_MAX_INTEGRITY."""
    cur = int(state.clankers_workshop_integrity.get(player_id, 0))
    state.clankers_workshop_integrity[player_id] = min(
        BULWARK_9_MAX_INTEGRITY, cur + int(amount)
    )


def _spend_scrap(state: GameState, player_id: str, amount: int) -> bool:
    """Spend ``amount`` scrap; return True on success, False if insufficient."""
    cur = int(state.clankers_scrap_pool.get(player_id, 0))
    if cur < amount:
        return False
    state.clankers_scrap_pool[player_id] = cur - amount
    return True


def _on_turn_end_trigger(
    obj: GameObject,
    react_fn,
    *,
    description: str = "",
):
    """REACT-priority CLANKERS_TURN_END trigger filtered by controller."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_TURN_END:
            return False
        # Payload key is 'player' per types.py:662
        return ev.payload.get("player") == obj.controller

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        try:
            new_events = react_fn(ev, st) or []
        except Exception:
            new_events = []
        return InterceptorResult(
            action=InterceptorAction.REACT if new_events else InterceptorAction.PASS,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On turn end",
        duration="forever" if obj.card_def is not None and CardType.CLANKERS_CORE in obj.characteristics.types else "while_on_battlefield",
    )


def _on_turn_start_trigger(
    obj: GameObject,
    react_fn,
    *,
    description: str = "",
):
    """REACT-priority CLANKERS_TURN_START trigger filtered by controller."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_TURN_START:
            return False
        return ev.payload.get("player") == obj.controller

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        try:
            new_events = react_fn(ev, st) or []
        except Exception:
            new_events = []
        return InterceptorResult(
            action=InterceptorAction.REACT if new_events else InterceptorAction.PASS,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On turn start",
        duration="while_on_battlefield",
    )


def _on_chassis_destroyed_trigger(
    obj: GameObject,
    react_fn,
    *,
    own_controller_only: bool = True,
    self_excluded: bool = False,
    description: str = "",
):
    """REACT trigger for CLANKERS_CHASSIS_DESTROYED. By default fires when any
    chassis the controller owns is destroyed; set own_controller_only=False to
    fire for any chassis."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_CHASSIS_DESTROYED:
            return False
        if own_controller_only and ev.payload.get("controller") != obj.controller:
            return False
        if self_excluded and ev.payload.get("chassis_id") == obj.id:
            return False
        return True

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        try:
            new_events = react_fn(ev, st) or []
        except Exception:
            new_events = []
        return InterceptorResult(
            action=InterceptorAction.REACT if new_events else InterceptorAction.PASS,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On chassis destroyed",
        duration="while_on_battlefield",
    )


def _on_host_blocks_trigger(
    obj: GameObject,
    react_fn,
    *,
    description: str = "",
):
    """REACT trigger for CLANKERS_BLOCK_DECLARE when this part's host is the
    blocker."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_BLOCK_DECLARE:
            return False
        return ev.payload.get("blocker_id") == obj.state.attached_to

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        try:
            new_events = react_fn(ev, st) or []
        except Exception:
            new_events = []
        return InterceptorResult(
            action=InterceptorAction.REACT if new_events else InterceptorAction.PASS,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description=description or "On host blocks",
        duration="while_on_battlefield",
    )


# =============================================================================
# Core: BULWARK-9
# =============================================================================

def _bulwark_9_passive_setup(obj: GameObject, state: GameState):
    """At end of your turn, if you control 3+ exhausted add-ons,
    gain 1 scrap and gain 1 workshop integrity (max 27)."""

    def react(ev: Event, st: GameState):
        controller = obj.controller
        if _count_exhausted_add_ons(st, controller) < 3:
            return []
        # Gain 1 scrap (emits CLANKERS_SCRAP_GAIN), then bump workshop integrity.
        events = list(_gain_scrap(st, controller, 1, obj.id))
        before = int(st.clankers_workshop_integrity.get(controller, 0))
        _heal_workshop(st, controller, 1)
        after = int(st.clankers_workshop_integrity.get(controller, 0))
        if after != before:
            events.append(Event(
                type=EventType.CLANKERS_CORE_PASSIVE,
                payload={
                    "player_id": controller,
                    "source_id": obj.id,
                    "reason": "bulwark_9_armor_cycle",
                    "scrap_gain": 1,
                    "workshop_integrity_gain": after - before,
                    "new_integrity": after,
                },
                source=obj.id,
                controller=controller,
            ))
        return events

    return [_on_turn_end_trigger(obj, react, description="BULWARK-9 armor-cycle payoff")]


BULWARK_9 = make_core(
    name="BULWARK-9",
    workshop_integrity=27,
    passive_setup=_bulwark_9_passive_setup,
    text=("At end of your turn, if you control 3+ exhausted add-ons, "
          "gain 1 scrap and gain 1 workshop integrity (max 27)."),
    flavor=("Cobalt-bordered server rack, visibly armored — the racks are "
            "reinforced with steel girders. The containment doctrine is "
            "non-negotiable."),
)


# =============================================================================
# Chassis (9 artillery + 1 neutral)
# =============================================================================

# Vault Chassis — vanilla wall
# BALANCE CYCLE 1: compute_cost 5 → 4. BULWARK's whole deck plan depends on
# landing Vault Chassis early enough to stack 2-3 armor add-ons on it. At 5
# Compute it arrived on T5 and the deck typically lost combat before the
# armor stack was online (winrate 12.7% — by far the bottom). Dropping to
# 4 puts the wall on the table a turn earlier, which is the entire deck's
# rate-limiting step.
VAULT_CHASSIS = make_chassis(
    name="Vault Chassis",
    power=2, integrity=7,
    weapon_slots=1, add_on_slots=4,
    compute_cost=4,
    clankers_archetype=ARTILLERY,
    text="Vanilla wall.",
)


# Bastion Frame — pay 1 scrap to prevent an add-on exhaustion on this chassis
def _bastion_frame_setup(obj: GameObject, state: GameState):
    """If an add-on attached to Bastion Frame would be exhausted (tapped via
    armor absorption), the controller may pay 1 scrap to keep it ready.

    Implemented as a TRANSFORM-priority interceptor on the damage events
    armor would normally absorb — we run *before* the armor interceptor's
    fixed priority by paying with scrap; on success the armor interceptor
    sees obj.state.tapped already False and won't exhaust (the armor helper
    sets tapped=True itself, so we revert it post-handler via a REACT).
    """

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type not in (
            EventType.DAMAGE,
            EventType.CLANKERS_COMBAT_DAMAGE,
            EventType.CLANKERS_WORKSHOP_DAMAGE,
        ):
            return False
        target = ev.payload.get("target") or ev.payload.get("defender_id")
        if target != obj.id:
            return False
        # Only fire if the controller has scrap to spend.
        return int(st.clankers_scrap_pool.get(obj.controller, 0)) >= 1

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        """After armor absorbs damage on Bastion Frame, refund the exhaustion
        by spending 1 scrap and re-readying the most-recently-tapped add-on.
        We run at REACT so the armor TRANSFORM has already set tapped=True
        on its add-on. The hook to find which add-on tapped: pick the first
        add-on attached to obj whose state.tapped is True AND was not
        tapped before this event — best-effort via the simple "most-recent
        attached add-on currently tapped" heuristic.
        """
        # Find a tapped add-on attached to this chassis to re-ready.
        candidate_id = None
        for pid in list(obj.state.attachments):
            p = st.objects.get(pid)
            if p is None or p.card_def is None:
                continue
            if not _is_add_on(p.card_def):
                continue
            if p.state.tapped:
                candidate_id = pid
                break
        if candidate_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not _spend_scrap(st, obj.controller, 1):
            return InterceptorResult(action=InterceptorAction.PASS)
        # Re-ready.
        target = st.objects.get(candidate_id)
        if target is not None:
            target.state.tapped = False
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CLANKERS_SCRAP_SPEND,
                payload={
                    "player_id": obj.controller,
                    "amount": 1,
                    "source_card_id": obj.id,
                    "reason": "bastion_frame_no_exhaust",
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Bastion Frame: pay 1 scrap to keep an add-on ready",
        duration="while_on_battlefield",
    )]


BASTION_FRAME = make_chassis(
    name="Bastion Frame",
    power=1, integrity=6,
    weapon_slots=1, add_on_slots=4,
    compute_cost=4,
    clankers_archetype=ARTILLERY,
    text=("If an add-on attached to Bastion Frame would be exhausted, "
          "you may pay 1 scrap; if you do, don't exhaust it."),
    setup_interceptors=_bastion_frame_setup,
)


# Sentinel Crane — vanilla high-end wall
SENTINEL_CRANE = make_chassis(
    name="Sentinel Crane",
    power=3, integrity=8,
    weapon_slots=1, add_on_slots=4,
    compute_cost=6,
    clankers_archetype=ARTILLERY,
    text="Vanilla high-end wall.",
)


# Embankment — cannot equip weapons (printed: 0 weapon slots)
EMBANKMENT = make_chassis(
    name="Embankment",
    power=1, integrity=5,
    weapon_slots=0, add_on_slots=4,
    compute_cost=3,
    clankers_archetype=ARTILLERY,
    text="Vanilla; cannot equip weapons.",
)


# Containment Sergeant — at end of turn, if 2+ exhausted add-ons, +1 integrity
def _containment_sergeant_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        if _count_exhausted_add_ons(st, obj.controller) < 2:
            return []
        before = int(st.clankers_workshop_integrity.get(obj.controller, 0))
        _heal_workshop(st, obj.controller, 1)
        after = int(st.clankers_workshop_integrity.get(obj.controller, 0))
        if after == before:
            return []
        return [Event(
            type=EventType.CLANKERS_WORKSHOP_DAMAGE,
            payload={
                "target": st.clankers_cores.get(obj.controller),
                "player_id": obj.controller,
                "amount": -1,
                "reason": "containment_sergeant_heal",
                "new_integrity": after,
                "source_card_id": obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [_on_turn_end_trigger(obj, react, description="Containment Sergeant heal")]


CONTAINMENT_SERGEANT = make_chassis(
    name="Containment Sergeant",
    power=2, integrity=5,
    weapon_slots=1, add_on_slots=3,
    compute_cost=4,
    clankers_archetype=ARTILLERY,
    text=("At end of your turn, if you control 2+ exhausted add-ons, "
          "gain 1 workshop integrity (max 27)."),
    setup_interceptors=_containment_sergeant_setup,
)


# Ready-Up Engineer — at Boot phase, ready an additional exhausted add-on
def _ready_one_exhausted_add_on(state: GameState, player_id: str, source_id: str):
    """Find one exhausted add-on the player controls and ready it. Returns the
    obj id (or None)."""
    for obj in state.objects.values():
        if obj.card_def is None:
            continue
        if not _is_add_on(obj.card_def):
            continue
        if obj.controller != player_id:
            continue
        if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
            continue
        if obj.state.tapped:
            obj.state.tapped = False
            return obj.id
    return None


def _ready_up_engineer_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        readied = _ready_one_exhausted_add_on(st, obj.controller, obj.id)
        if readied is None:
            return []
        return [Event(
            type=EventType.CLANKERS_CORE_PASSIVE,
            payload={
                "player_id": obj.controller,
                "source_id": obj.id,
                "reason": "ready_up_engineer_extra_ready",
                "readied_part_id": readied,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [_on_turn_start_trigger(obj, react, description="Ready-Up Engineer: extra add-on ready")]


READY_UP_ENGINEER = make_chassis(
    name="Ready-Up Engineer",
    power=2, integrity=4,
    weapon_slots=1, add_on_slots=3,
    compute_cost=3,
    clankers_archetype=ARTILLERY,
    text=("At the start of your Boot phase, ready an additional exhausted "
          "add-on you control."),
    setup_interceptors=_ready_up_engineer_setup,
)


# Counterweight Walker — when another chassis is destroyed, +2 permanent integrity
def _counterweight_walker_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        # Mutate the host's card_def integrity (permanent). To avoid leaking
        # state across game instances we mutate the per-object characteristics
        # toughness AND ALSO bump a per-obj attr 'cw_integrity_buff'.
        bump = int(getattr(obj, "cw_integrity_buff", 0)) + 2
        obj.cw_integrity_buff = bump
        # The buff lives in a TRANSFORM interceptor on QUERY_INTEGRITY for self.
        return []

    def integrity_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        return ev.payload.get("chassis_id") == obj.id

    def integrity_handler(ev: Event, st: GameState) -> InterceptorResult:
        bump = int(getattr(obj, "cw_integrity_buff", 0))
        if bump <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_payload = dict(ev.payload)
        new_payload["result"] = int(new_payload.get("result", 0)) + bump
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

    integrity_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=integrity_filter,
        handler=integrity_handler,
        description="Counterweight Walker permanent integrity buff",
        duration="while_on_battlefield",
    )

    return [
        _on_chassis_destroyed_trigger(
            obj, react, own_controller_only=True, self_excluded=True,
            description="Counterweight Walker grows on ally death",
        ),
        integrity_ic,
    ]


COUNTERWEIGHT_WALKER = make_chassis(
    name="Counterweight Walker",
    power=3, integrity=6,
    weapon_slots=1, add_on_slots=3,
    compute_cost=5,
    clankers_archetype=ARTILLERY,
    text=("When a chassis you control is destroyed, this gets +2 integrity "
          "(permanent)."),
    setup_interceptors=_counterweight_walker_setup,
)


# Mortar Lieutenant — when attacks unblocked, +1 workshop damage
def _mortar_lieutenant_setup(obj: GameObject, state: GameState):
    """+1 extra workshop damage when this attacks unblocked."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_WORKSHOP_DAMAGE:
            return False
        return ev.source == obj.id

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(ev.payload)
        amount = int(new_payload.get("amount", 0))
        new_payload["amount"] = amount + 1
        new_payload["mortar_bonus"] = 1
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

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Mortar Lieutenant +1 workshop damage",
        duration="while_on_battlefield",
    )]


MORTAR_LIEUTENANT = make_chassis(
    name="Mortar Lieutenant",
    power=4, integrity=4,
    weapon_slots=2, add_on_slots=2,
    compute_cost=4,
    clankers_archetype=ARTILLERY,
    text=("When this attacks unblocked, deal 1 additional workshop damage "
          "to defending Core."),
    setup_interceptors=_mortar_lieutenant_setup,
)


# Foreman's Watch — at end of turn, if 3+ exhausted add-ons, draw a card
def _foremans_watch_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        if _count_exhausted_add_ons(st, obj.controller) < 3:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1, "reason": "foremans_watch"},
            source=obj.id,
            controller=obj.controller,
        )]

    return [_on_turn_end_trigger(obj, react, description="Foreman's Watch end-of-turn draw")]


FOREMANS_WATCH = make_chassis(
    name="Foreman's Watch",
    power=4, integrity=6,
    weapon_slots=1, add_on_slots=4,
    compute_cost=6,
    clankers_archetype=ARTILLERY,
    text="At end of your turn, if you control 3+ exhausted add-ons, draw a card.",
    setup_interceptors=_foremans_watch_setup,
)


# Workshop Prototype (neutral)
WORKSHOP_PROTOTYPE = make_chassis(
    name="Workshop Prototype",
    power=2, integrity=3,
    weapon_slots=1, add_on_slots=2,
    compute_cost=2,
    clankers_archetype=NEUTRAL,
    text="Vanilla 2-drop usable in any deck.",
)


# =============================================================================
# Weapons (8 artillery + 4 neutral)
# =============================================================================

# Riot Baton — when host blocks, +1 power EoT
def _riot_baton_setup(obj: GameObject, state: GameState):
    """While host is the blocker, gain +1 power. Implemented as a TRANSFORM
    on QUERY_POWER conditioned on the chassis being assigned as a blocker
    (we proxy via a flag on the part itself set during BLOCK_DECLARE)."""

    def block_react(ev: Event, st: GameState):
        obj.riot_baton_blocking = True
        return []

    def turn_end_clear(ev: Event, st: GameState):
        obj.riot_baton_blocking = False
        return []

    def power_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_QUERY_POWER:
            return False
        host = obj.state.attached_to
        if host is None:
            return False
        if not getattr(obj, "riot_baton_blocking", False):
            return False
        return ev.payload.get("chassis_id") == host

    def power_handler(ev: Event, st: GameState) -> InterceptorResult:
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

    power_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=power_filter,
        handler=power_handler,
        description="Riot Baton +1 power while blocking",
        duration="while_on_battlefield",
    )

    return [
        _on_host_blocks_trigger(obj, block_react, description="Riot Baton: enter block mode"),
        _on_turn_end_trigger(obj, turn_end_clear, description="Riot Baton: clear block mode"),
        power_ic,
    ]


RIOT_BATON = make_weapon(
    name="Riot Baton",
    power_bonus=2,
    compute_cost=2,
    clankers_archetype=ARTILLERY,
    text="When host blocks, this gets +1 power until end of turn.",
    setup_interceptors=_riot_baton_setup,
)


# Containment Whip — when host attacks, may exhaust an add-on for +1 damage
def _containment_whip_setup(obj: GameObject, state: GameState):
    """On host attack, exhaust a ready add-on attached to host to add +1 to
    damage. Implemented as a REACT-priority on CLANKERS_COMBAT_DAMAGE whose
    source matches host."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_COMBAT_DAMAGE:
            return False
        host = obj.state.attached_to
        if host is None:
            return False
        return ev.payload.get("attacker_id") == host

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        host_id = obj.state.attached_to
        host = st.objects.get(host_id) if host_id else None
        if host is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Find a ready (non-tapped) add-on attached to host besides ourselves.
        target = None
        for pid in list(host.state.attachments):
            if pid == obj.id:
                continue
            p = st.objects.get(pid)
            if p is None or p.card_def is None:
                continue
            if _is_add_on(p.card_def) and not p.state.tapped:
                target = p
                break
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        target.state.tapped = True
        new_payload = dict(ev.payload)
        new_payload["amount"] = int(new_payload.get("amount", 0)) + 1
        new_payload["containment_whip_bonus"] = 1
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

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Containment Whip: exhaust an add-on for +1 damage",
        duration="while_on_battlefield",
    )]


CONTAINMENT_WHIP = make_weapon(
    name="Containment Whip",
    power_bonus=2,
    compute_cost=3,
    clankers_archetype=ARTILLERY,
    text=("When host attacks, you may exhaust an add-on you control; "
          "if you do, deal 1 extra damage."),
    setup_interceptors=_containment_whip_setup,
)


# Riot Mortar — when attacks unblocked, deal 2 workshop damage instead of effective power
def _riot_mortar_setup(obj: GameObject, state: GameState):
    """Override workshop damage from host to a flat 2."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_WORKSHOP_DAMAGE:
            return False
        host = obj.state.attached_to
        if host is None:
            return False
        return ev.source == host

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(ev.payload)
        new_payload["amount"] = 2
        new_payload["riot_mortar_override"] = True
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

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Riot Mortar: flat 2 workshop damage",
        duration="while_on_battlefield",
    )]


RIOT_MORTAR = make_weapon(
    name="Riot Mortar",
    power_bonus=3,
    compute_cost=4,
    clankers_archetype=ARTILLERY,
    text=("When host attacks unblocked, deal 2 workshop damage instead "
          "of host's effective power."),
    setup_interceptors=_riot_mortar_setup,
)


# Stunner Arm — activated: pay 1 compute, exhaust host: target opp's chassis can't attack next turn
def _stunner_arm_setup(obj: GameObject, state: GameState):
    def effect_fn(ev: Event, st: GameState):
        # Targets supplied via activation payload.
        targets = ev.payload.get("targets") or []
        events: list[Event] = []
        for tid in targets:
            target = st.objects.get(tid)
            if target is None or target.card_def is None:
                continue
            if not _is_chassis(target.card_def):
                continue
            if target.controller == obj.controller:
                continue
            # Set a per-object flag the combat manager (or AI legal-actions)
            # would consult on the next turn.
            target.cannot_attack_until_turn = int(st.turn_number or 0) + 2
            events.append(Event(
                type=EventType.CLANKERS_CORE_PASSIVE,
                payload={
                    "player_id": obj.controller,
                    "source_id": obj.id,
                    "reason": "stunner_arm_disable",
                    "target_id": tid,
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return [make_weapon_activated(
        obj,
        compute_cost=1,
        exhaust_self=True,
        effect_fn=effect_fn,
        description="Stunner Arm: target opp chassis can't attack next turn",
    )]


STUNNER_ARM = make_weapon(
    name="Stunner Arm",
    power_bonus=1,
    compute_cost=2,
    clankers_archetype=ARTILLERY,
    text=("Pay 1 Compute, exhaust host: target opponent's chassis cannot "
          "attack next turn."),
    setup_interceptors=_stunner_arm_setup,
)


# Sentinel Cannon — when host destroys a chassis, gain 1 workshop integrity
def _sentinel_cannon_setup(obj: GameObject, state: GameState):
    """On CHASSIS_DESTROYED whose attacker (via combat-damage trail) is host,
    heal 1 to the controller's workshop. Simple approximation: any chassis
    destruction event whose controller != ours fires the heal — refine if/when
    a combat-attribution payload field is added."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_CHASSIS_DESTROYED:
            return False
        # Only fire if the destroyed chassis belongs to the OPPONENT.
        if ev.payload.get("controller") == obj.controller:
            return False
        # And only if this weapon is currently attached to a chassis controlled
        # by us (we're "live" combat-active).
        host = obj.state.attached_to
        if host is None:
            return False
        return True

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        before = int(st.clankers_workshop_integrity.get(obj.controller, 0))
        _heal_workshop(st, obj.controller, 1)
        after = int(st.clankers_workshop_integrity.get(obj.controller, 0))
        if after == before:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CLANKERS_CORE_PASSIVE,
                payload={
                    "player_id": obj.controller,
                    "source_id": obj.id,
                    "reason": "sentinel_cannon_heal",
                    "new_integrity": after,
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Sentinel Cannon: gain 1 workshop integrity on kill",
        duration="while_on_battlefield",
    )]


SENTINEL_CANNON = make_weapon(
    name="Sentinel Cannon",
    power_bonus=3,
    compute_cost=3,
    clankers_archetype=ARTILLERY,
    text="When host destroys a chassis, gain 1 workshop integrity (max 27).",
    setup_interceptors=_sentinel_cannon_setup,
)


# Heavy Watchpost — host cannot attack; when blocks, host has armor 2
def _heavy_watchpost_setup(obj: GameObject, state: GameState):
    """Two interceptors:
      1. Prevent the host from attacking (block CLANKERS_ATTACK_DECLARE when
         attacker_id == host).
      2. When the host is a blocker (host_block trigger), grant armor 2 for
         this combat by reducing incoming damage by 2 once.
    """

    def attack_prevent_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_ATTACK_DECLARE:
            return False
        return ev.payload.get("attacker_id") == obj.state.attached_to

    def attack_prevent_handler(ev: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    attack_prevent_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_prevent_filter,
        handler=attack_prevent_handler,
        description="Heavy Watchpost: host cannot attack",
        duration="while_on_battlefield",
    )

    def damage_filter(ev: Event, st: GameState) -> bool:
        if ev.type not in (EventType.DAMAGE, EventType.CLANKERS_COMBAT_DAMAGE):
            return False
        host = obj.state.attached_to
        if host is None:
            return False
        if getattr(obj, "watchpost_used_this_combat", False):
            return False
        target = ev.payload.get("target") or ev.payload.get("defender_id")
        return target == host

    def damage_handler(ev: Event, st: GameState) -> InterceptorResult:
        new_payload = dict(ev.payload)
        amount_key = "amount" if "amount" in new_payload else "damage"
        amount = int(new_payload.get(amount_key, 0))
        absorbed = min(2, amount)
        new_payload[amount_key] = amount - absorbed
        new_payload["watchpost_absorbed"] = absorbed
        obj.watchpost_used_this_combat = True
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

    damage_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=damage_filter,
        handler=damage_handler,
        description="Heavy Watchpost: armor 2 while blocking",
        duration="while_on_battlefield",
    )

    def turn_end_clear(ev: Event, st: GameState):
        obj.watchpost_used_this_combat = False
        return []

    return [
        attack_prevent_ic,
        damage_ic,
        _on_turn_end_trigger(obj, turn_end_clear, description="Heavy Watchpost: clear used flag"),
    ]


HEAVY_WATCHPOST = make_weapon(
    name="Heavy Watchpost",
    power_bonus=2,
    compute_cost=4,
    clankers_archetype=ARTILLERY,
    text=("Host cannot attack. When host blocks, host has armor 2 for "
          "that combat."),
    setup_interceptors=_heavy_watchpost_setup,
)


# Burnout Cannon — when host attacks unblocked, defender mills 1
def _burnout_cannon_setup(obj: GameObject, state: GameState):
    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_WORKSHOP_DAMAGE:
            return False
        host = obj.state.attached_to
        return host is not None and ev.source == host

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        defender = ev.payload.get("player_id")
        if defender is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        library = _ensure_zone(st, ZoneType.LIBRARY, defender)
        if not library.objects:
            return InterceptorResult(action=InterceptorAction.PASS)
        cid = library.objects.pop(0)
        scrap = _ensure_zone(st, ZoneType.CLANKERS_SCRAP_HEAP, defender)
        scrap.objects.append(cid)
        moved = st.objects.get(cid)
        if moved is not None:
            moved.zone = ZoneType.CLANKERS_SCRAP_HEAP
            moved.entered_zone_at = st.next_timestamp()
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": cid,
                    "to_zone": ZoneType.CLANKERS_SCRAP_HEAP.name,
                    "controller": defender,
                    "reason": "burnout_cannon_mill",
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Burnout Cannon: defender mills 1 on unblocked hit",
        duration="while_on_battlefield",
    )]


BURNOUT_CANNON = make_weapon(
    name="Burnout Cannon",
    power_bonus=4,
    compute_cost=5,
    clankers_archetype=ARTILLERY,
    text=("When host attacks unblocked, the defending player loses 1 from "
          "their library (mill 1)."),
    setup_interceptors=_burnout_cannon_setup,
)


# Containment Pike — Reclaim 2
def _reclaim_setup(amount: int):
    """Factory: build a setup_interceptors that emits Reclaim N (gain N scrap
    when this part is destroyed)."""

    def setup(obj: GameObject, state: GameState):
        def react(ev: Event, st: GameState):
            return _gain_scrap(st, obj.controller, amount, obj.id)
        return [make_part_on_self_destroyed(
            obj, react, description=f"Reclaim {amount}"
        )]

    return setup


CONTAINMENT_PIKE = make_weapon(
    name="Containment Pike",
    power_bonus=3,
    compute_cost=3,
    clankers_archetype=ARTILLERY,
    text="Reclaim 2 (when this is destroyed, gain 2 scrap).",
    setup_interceptors=_reclaim_setup(2),
)


# Neutral weapons (4)
STANDARD_ISSUE_BLASTER = make_weapon(
    name="Standard Issue Blaster",
    power_bonus=1,
    compute_cost=1,
    clankers_archetype=NEUTRAL,
    text="Vanilla.",
)


def _workshop_wrench_setup(obj: GameObject, state: GameState):
    """Activated: pay 1 compute, exhaust host: ready one exhausted add-on."""

    def effect_fn(ev: Event, st: GameState):
        readied = _ready_one_exhausted_add_on(st, obj.controller, obj.id)
        if readied is None:
            return []
        return [Event(
            type=EventType.CLANKERS_CORE_PASSIVE,
            payload={
                "player_id": obj.controller,
                "source_id": obj.id,
                "reason": "workshop_wrench_ready",
                "readied_part_id": readied,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [make_weapon_activated(
        obj,
        compute_cost=1,
        exhaust_self=True,
        effect_fn=effect_fn,
        description="Workshop Wrench: ready an exhausted add-on",
    )]


WORKSHOP_WRENCH = make_weapon(
    name="Workshop Wrench",
    power_bonus=1,
    compute_cost=1,
    clankers_archetype=NEUTRAL,
    text=("Pay 1 Compute, exhaust host: ready one exhausted add-on "
          "you control."),
    setup_interceptors=_workshop_wrench_setup,
)


RIVETER_MK_I = make_weapon(
    name="Riveter Mk-I",
    power_bonus=2,
    compute_cost=2,
    clankers_archetype=NEUTRAL,
    text="Vanilla.",
)


SPARE_COILGUN = make_weapon(
    name="Spare Coilgun",
    power_bonus=3,
    compute_cost=3,
    clankers_archetype=NEUTRAL,
    text="Vanilla.",
)


# =============================================================================
# Add-Ons (8 artillery)
# =============================================================================

def _armor_setup(armor_value: int):
    """Factory: setup_interceptors that registers a single make_armor."""
    def setup(obj: GameObject, state: GameState):
        return [make_armor(obj, armor_value)]
    return setup


# BALANCE CYCLE 1: integrity_bonus 1 → 2. BULWARK's keystone armor add-on
# printed at 4x in the deck. Even with Armor 3 absorption, +1 integrity
# wasn't enough to keep the Vault Chassis alive past one combat phase
# when MIRTH's swarm chained attacks. Bumping the integrity_bonus from
# 1 to 2 makes a Vault Chassis stacked with two Reactive Shieldings a
# real 2/11 instead of a 2/9, which is the size of wall the armor-grinder
# plan actually needs to compete.
REACTIVE_SHIELDING = make_add_on(
    name="Reactive Shielding",
    integrity_bonus=2,
    compute_cost=3,
    armor_value=3,
    clankers_archetype=ARTILLERY,
    text="Armor 3 (exhaust to absorb up to 3 damage to host).",
    setup_interceptors=_armor_setup(3),
)


VAULT_BRACER = make_add_on(
    name="Vault Bracer",
    integrity_bonus=3,
    compute_cost=2,
    clankers_archetype=ARTILLERY,
    text="Vanilla.",
)


# Riot Plating — armor 2 + when absorbs damage, deal 1 to the attacker
def _riot_plating_setup(obj: GameObject, state: GameState):
    """We compose the standard make_armor with a REACT-priority observer that
    looks for armor_absorbed > 0 on damage events targeting the host, then
    deals 1 damage back to the attacker.
    """

    armor_ic = make_armor(obj, 2)

    def reactor_filter(ev: Event, st: GameState) -> bool:
        if ev.type not in (
            EventType.DAMAGE,
            EventType.CLANKERS_COMBAT_DAMAGE,
        ):
            return False
        target = ev.payload.get("target") or ev.payload.get("defender_id")
        if target != obj.state.attached_to:
            return False
        return int(ev.payload.get("armor_absorbed", 0)) > 0

    def reactor_handler(ev: Event, st: GameState) -> InterceptorResult:
        attacker_id = ev.payload.get("source") or ev.payload.get("attacker_id") or ev.source
        if attacker_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Mark damage on the attacker if it's a chassis.
        attacker = st.objects.get(attacker_id)
        if attacker is not None and attacker.card_def is not None and _is_chassis(attacker.card_def):
            attacker.state.damage_marked = int(getattr(attacker.state, "damage_marked", 0)) + 1
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DAMAGE,
                payload={
                    "target": attacker_id,
                    "amount": 1,
                    "source": obj.id,
                    "reason": "riot_plating_thorn",
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    reactor_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=reactor_filter,
        handler=reactor_handler,
        description="Riot Plating: thorn 1 on absorb",
        duration="while_on_battlefield",
    )

    return [armor_ic, reactor_ic]


RIOT_PLATING = make_add_on(
    name="Riot Plating",
    integrity_bonus=2,
    compute_cost=3,
    armor_value=2,
    clankers_archetype=ARTILLERY,
    text="Armor 2. When this absorbs damage, deal 1 damage to the attacker.",
    setup_interceptors=_riot_plating_setup,
)


BUNKER_CRADLE = make_add_on(
    name="Bunker Cradle",
    integrity_bonus=4,
    compute_cost=4,
    armor_value=4,
    clankers_archetype=ARTILLERY,
    text="Armor 4 (exhaust to absorb up to 4 damage to host).",
    setup_interceptors=_armor_setup(4),
)


# Counterweight Sleeve — when host blocks, +1 integrity until end of combat
def _counterweight_sleeve_setup(obj: GameObject, state: GameState):
    """+1 integrity to host while blocking. We use a flag toggled by the
    block-declare trigger; we clear at turn end."""

    def block_react(ev: Event, st: GameState):
        obj.counterweight_blocking = True
        return []

    def turn_end_clear(ev: Event, st: GameState):
        obj.counterweight_blocking = False
        return []

    def integrity_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_QUERY_INTEGRITY:
            return False
        host = obj.state.attached_to
        if host is None:
            return False
        if not getattr(obj, "counterweight_blocking", False):
            return False
        return ev.payload.get("chassis_id") == host

    def integrity_handler(ev: Event, st: GameState) -> InterceptorResult:
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

    integrity_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=integrity_filter,
        handler=integrity_handler,
        description="Counterweight Sleeve +1 integrity while blocking",
        duration="while_on_battlefield",
    )

    return [
        _on_host_blocks_trigger(obj, block_react, description="Counterweight Sleeve: enter block mode"),
        _on_turn_end_trigger(obj, turn_end_clear, description="Counterweight Sleeve: clear block mode"),
        integrity_ic,
    ]


COUNTERWEIGHT_SLEEVE = make_add_on(
    name="Counterweight Sleeve",
    integrity_bonus=2,
    compute_cost=2,
    clankers_archetype=ARTILLERY,
    text="When host blocks, this gets +1 integrity until end of combat.",
    setup_interceptors=_counterweight_sleeve_setup,
)


# Coolant Cradle — activated: pay 1 scrap, Reassemble: ready this add-on
def _coolant_cradle_setup(obj: GameObject, state: GameState):
    """Custom activated descriptor. Cost: 1 scrap. Effect: ready self."""

    def effect_fn(ev: Event, st: GameState):
        # Cost-check + spend.
        if not _spend_scrap(st, obj.controller, 1):
            return []
        obj.state.tapped = False
        return [Event(
            type=EventType.CLANKERS_SCRAP_SPEND,
            payload={
                "player_id": obj.controller,
                "amount": 1,
                "source_card_id": obj.id,
                "reason": "coolant_cradle_ready_self",
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [make_weapon_activated(
        obj,
        compute_cost=0,
        exhaust_self=False,
        effect_fn=effect_fn,
        description="Coolant Cradle: pay 1 scrap to ready self",
    )]


COOLANT_CRADLE = make_add_on(
    name="Coolant Cradle",
    integrity_bonus=1,
    compute_cost=1,
    clankers_archetype=ARTILLERY,
    text="Pay 1 scrap, Reassemble: ready this add-on.",
    setup_interceptors=_coolant_cradle_setup,
)


# Containment Lining — armor 2 + while 3+ attached add-ons are exhausted, host +1 power
def _containment_lining_setup(obj: GameObject, state: GameState):
    armor_ic = make_armor(obj, 2)

    def power_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_QUERY_POWER:
            return False
        host_id = obj.state.attached_to
        if host_id is None:
            return False
        if ev.payload.get("chassis_id") != host_id:
            return False
        host = st.objects.get(host_id)
        if host is None:
            return False
        # Count exhausted add-ons attached to host.
        exhausted = 0
        for pid in host.state.attachments:
            p = st.objects.get(pid)
            if p is None or p.card_def is None:
                continue
            if _is_add_on(p.card_def) and p.state.tapped:
                exhausted += 1
        return exhausted >= 3

    def power_handler(ev: Event, st: GameState) -> InterceptorResult:
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

    power_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=power_filter,
        handler=power_handler,
        description="Containment Lining: +1 power if 3+ exhausted add-ons",
        duration="while_on_battlefield",
    )

    return [armor_ic, power_ic]


CONTAINMENT_LINING = make_add_on(
    name="Containment Lining",
    integrity_bonus=3,
    compute_cost=3,
    armor_value=2,
    clankers_archetype=ARTILLERY,
    text=("Armor 2. While 3+ add-ons attached to host are exhausted, "
          "host has +1 power."),
    setup_interceptors=_containment_lining_setup,
)


# Spotter Rig — when host blocks, draw a card
def _spotter_rig_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        return [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1, "reason": "spotter_rig"},
            source=obj.id,
            controller=obj.controller,
        )]

    return [_on_host_blocks_trigger(obj, react, description="Spotter Rig draw on block")]


SPOTTER_RIG = make_add_on(
    name="Spotter Rig",
    integrity_bonus=2,
    compute_cost=2,
    clankers_archetype=ARTILLERY,
    text="When host blocks, draw a card.",
    setup_interceptors=_spotter_rig_setup,
)


# =============================================================================
# Transients (3 artillery + 1 neutral)
# =============================================================================

# Burnout Protocol — double opponent's containment-failure damage this turn
def _burnout_protocol_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if controller is None:
        return []
    if not state.clankers_containment_failure:
        # If deathclock isn't active yet, the effect is wasted (the card text
        # is gated on "if deathclock active").
        return []
    opponent = _opponent_id(state, controller)
    if opponent is None:
        return []

    # Register a one-shot REPLACE interceptor on CONTAINMENT_FAILURE_TICK that
    # doubles damage to opponent on the next tick this turn cleanup, then
    # de-registers itself.
    triggered = {"fired": False}

    def filter_fn(ev: Event, st: GameState) -> bool:
        if triggered["fired"]:
            return False
        if ev.type != EventType.CLANKERS_CONTAINMENT_FAILURE_TICK:
            return False
        # Don't trigger on the "activated" marker (damage=0).
        if int(ev.payload.get("damage", 0)) <= 0:
            return False
        return True

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        triggered["fired"] = True
        # The tick already applied damage; we issue an extra WORKSHOP_DAMAGE to
        # the opponent equalling the tick's damage (i.e. doubling).
        damage = int(ev.payload.get("damage", 0))
        core_id = st.clankers_cores.get(opponent)
        if core_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        before = int(st.clankers_workshop_integrity.get(opponent, 0))
        st.clankers_workshop_integrity[opponent] = max(0, before - damage)
        # Clean up — set duration so it self-cleans.
        ic_obj = None
        for ic in list(st.interceptors.values()):
            if ic.description == "Burnout Protocol: double opp deathclock":
                ic_obj = ic
                break
        if ic_obj is not None:
            st.interceptors.pop(ic_obj.id, None)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CLANKERS_WORKSHOP_DAMAGE,
                payload={
                    "target": core_id,
                    "player_id": opponent,
                    "amount": damage,
                    "reason": "burnout_protocol_double",
                    "new_integrity": st.clankers_workshop_integrity[opponent],
                },
                source=None,
                controller=controller,
            )],
        )

    interceptor = Interceptor(
        id=new_id(),
        source=event.payload.get("transient_id"),
        controller=controller,
        priority=InterceptorPriority.REPLACE,
        filter=filter_fn,
        handler=handler,
        description="Burnout Protocol: double opp deathclock",
        duration="end_of_turn",
    )
    state.interceptors[interceptor.id] = interceptor
    return []


BURNOUT_PROTOCOL = make_transient(
    name="Burnout Protocol",
    compute_cost=4,
    resolve_fn=_burnout_protocol_resolve,
    clankers_archetype=ARTILLERY,
    text=("If the deathclock is active, the opponent takes double "
          "containment-failure damage at end of turn."),
)


# Repair Subroutine — ready up to 2 exhausted add-ons you control
def _repair_subroutine_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if controller is None:
        return []
    targets = list(event.payload.get("targets") or [])
    events: list[Event] = []
    readied: list[str] = []
    # If specific targets supplied, ready those (up to 2).
    if targets:
        for tid in targets[:2]:
            obj = state.objects.get(tid)
            if obj is None or obj.card_def is None:
                continue
            if not _is_add_on(obj.card_def):
                continue
            if obj.controller != controller:
                continue
            if not obj.state.tapped:
                continue
            obj.state.tapped = False
            readied.append(tid)
    else:
        # Default: ready the first two exhausted add-ons we find.
        for obj in state.objects.values():
            if len(readied) >= 2:
                break
            if obj.card_def is None or not _is_add_on(obj.card_def):
                continue
            if obj.controller != controller:
                continue
            if obj.zone != ZoneType.CLANKERS_ASSEMBLY_FLOOR:
                continue
            if not obj.state.tapped:
                continue
            obj.state.tapped = False
            readied.append(obj.id)
    for tid in readied:
        events.append(Event(
            type=EventType.CLANKERS_CORE_PASSIVE,
            payload={
                "player_id": controller,
                "source_id": event.payload.get("transient_id"),
                "reason": "repair_subroutine_ready",
                "readied_part_id": tid,
            },
            source=event.payload.get("transient_id"),
            controller=controller,
        ))
    return events


REPAIR_SUBROUTINE = make_transient(
    name="Repair Subroutine",
    compute_cost=2,
    resolve_fn=_repair_subroutine_resolve,
    clankers_archetype=ARTILLERY,
    text="Ready up to 2 exhausted add-ons you control.",
)


# Containment Recall — return a destroyed add-on to the Assembly Floor exhausted/unattached
def _containment_recall_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if controller is None:
        return []
    targets = list(event.payload.get("targets") or [])
    scrap = _ensure_zone(state, ZoneType.CLANKERS_SCRAP_HEAP, controller)

    # Determine which add-on to recall.
    recall_id = None
    if targets:
        for tid in targets:
            if tid in scrap.objects:
                obj = state.objects.get(tid)
                if obj is None or obj.card_def is None:
                    continue
                if _is_add_on(obj.card_def):
                    recall_id = tid
                    break
    if recall_id is None:
        # Default: take the most-recently-destroyed add-on (back of list).
        for tid in reversed(scrap.objects):
            obj = state.objects.get(tid)
            if obj is None or obj.card_def is None:
                continue
            if _is_add_on(obj.card_def):
                recall_id = tid
                break
    if recall_id is None:
        return []

    obj = state.objects.get(recall_id)
    if obj is None:
        return []
    # Move scrap -> floor; set tapped=True, attached_to=None.
    if recall_id in scrap.objects:
        scrap.objects.remove(recall_id)
    floor = _ensure_zone(state, ZoneType.CLANKERS_ASSEMBLY_FLOOR, controller)
    if recall_id not in floor.objects:
        floor.objects.append(recall_id)
    obj.zone = ZoneType.CLANKERS_ASSEMBLY_FLOOR
    obj.entered_zone_at = state.next_timestamp()
    obj.state.attached_to = None
    obj.state.tapped = True
    obj.controller = controller

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": recall_id,
            "to_zone": ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
            "controller": controller,
            "reason": "containment_recall",
            "card_type": "CLANKERS_ADD_ON",
        },
        source=event.payload.get("transient_id"),
        controller=controller,
    )]


CONTAINMENT_RECALL = make_transient(
    name="Containment Recall",
    compute_cost=3,
    resolve_fn=_containment_recall_resolve,
    clankers_archetype=ARTILLERY,
    text=("Return a destroyed add-on from your scrap heap to the Assembly "
          "Floor exhausted and unattached."),
)


# Scrap Salvo (neutral) — pay 3 scrap: deal 3 damage to a chassis or Core
def _scrap_salvo_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if controller is None:
        return []
    if not _spend_scrap(state, controller, 3):
        # Insufficient scrap — fizzles (the alternate cost gate failed).
        return []
    targets = list(event.payload.get("targets") or [])
    events: list[Event] = [Event(
        type=EventType.CLANKERS_SCRAP_SPEND,
        payload={
            "player_id": controller,
            "amount": 3,
            "source_card_id": event.payload.get("transient_id"),
            "reason": "scrap_salvo_cost",
        },
        source=event.payload.get("transient_id"),
        controller=controller,
    )]

    target_id = targets[0] if targets else None
    target = state.objects.get(target_id) if target_id else None
    if target is None or target.card_def is None:
        # No legal target — choose the opponent's Core by default.
        opp = _opponent_id(state, controller)
        target_id = state.clankers_cores.get(opp) if opp else None
        target = state.objects.get(target_id) if target_id else None
    if target is None:
        return events

    # If a chassis: mark damage. If a Core: drain workshop integrity.
    if target.card_def is not None and _is_chassis(target.card_def):
        target.state.damage_marked = int(getattr(target.state, "damage_marked", 0)) + 3
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                "target": target_id,
                "amount": 3,
                "source": event.payload.get("transient_id"),
                "reason": "scrap_salvo",
            },
            source=event.payload.get("transient_id"),
            controller=controller,
        ))
    elif target.card_def is not None and CardType.CLANKERS_CORE in target.characteristics.types:
        target_player = target.controller
        before = int(state.clankers_workshop_integrity.get(target_player, 0))
        state.clankers_workshop_integrity[target_player] = max(0, before - 3)
        events.append(Event(
            type=EventType.CLANKERS_WORKSHOP_DAMAGE,
            payload={
                "target": target_id,
                "player_id": target_player,
                "amount": 3,
                "reason": "scrap_salvo",
                "new_integrity": state.clankers_workshop_integrity[target_player],
            },
            source=event.payload.get("transient_id"),
            controller=controller,
        ))
    return events


SCRAP_SALVO = make_transient(
    name="Scrap Salvo",
    compute_cost=2,
    resolve_fn=_scrap_salvo_resolve,
    clankers_archetype=NEUTRAL,
    text="Pay 3 scrap: deal 3 damage to a chassis or Core.",
)


# =============================================================================
# Structures (2 artillery + 3 neutral)
# =============================================================================

# Containment Baffle — opposing chassis with effective power >=4 pay +1 to attack
def _containment_baffle_setup(obj: GameObject, state: GameState):
    """TRANSFORM-priority on CLANKERS_COMPUTE_SPEND: if the source card is a
    "declare attack" for a high-power opposing chassis, +1 to amount.

    Because Combat doesn't explicitly route through COMPUTE_SPEND for attack
    declarations in this engine version, we use a simpler approximation:
    REACT on CLANKERS_ATTACK_DECLARE for opponent's chassis with power>=4 and
    deduct 1 compute. If the opponent can't pay, we'd PREVENT — but since the
    legal-actions layer doesn't surface compute-checked attacks, this becomes
    a soft tax rather than a hard block. Card-text intent preserved.
    """

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_ATTACK_DECLARE:
            return False
        attacker_id = ev.payload.get("attacker_id")
        attacker_controller = ev.payload.get("attacker_controller")
        if attacker_controller == obj.controller:
            return False
        if attacker_id is None:
            return False
        # Only opposing chassis above the power threshold pay.
        try:
            pwr = compute_effective_power(st, attacker_id)
        except Exception:
            pwr = 0
        return pwr >= 4

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        attacker_controller = ev.payload.get("attacker_controller")
        if attacker_controller is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Deduct 1 compute from the opponent (soft tax).
        cur = int(st.clankers_compute_pool.get(attacker_controller, 0))
        st.clankers_compute_pool[attacker_controller] = max(0, cur - 1)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CLANKERS_COMPUTE_SPEND,
                payload={
                    "player_id": attacker_controller,
                    "amount": 1,
                    "source_card_id": obj.id,
                    "reason": "containment_baffle_attack_tax",
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        description="Containment Baffle: +1 compute tax on big attacks",
        duration="while_on_battlefield",
    )]


CONTAINMENT_BAFFLE = make_structure(
    name="Containment Baffle",
    compute_cost=3,
    clankers_archetype=ARTILLERY,
    text=("Opposing chassis with effective power >=4 must pay 1 extra "
          "Compute to attack from the Assembly Floor."),
    setup_interceptors=_containment_baffle_setup,
)


# Workshop Sprinkler — at end of turn, ready an additional exhausted add-on
def _workshop_sprinkler_setup(obj: GameObject, state: GameState):
    def react(ev: Event, st: GameState):
        readied = _ready_one_exhausted_add_on(st, obj.controller, obj.id)
        if readied is None:
            return []
        return [Event(
            type=EventType.CLANKERS_CORE_PASSIVE,
            payload={
                "player_id": obj.controller,
                "source_id": obj.id,
                "reason": "workshop_sprinkler_ready",
                "readied_part_id": readied,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [_on_turn_end_trigger(obj, react, description="Workshop Sprinkler: ready add-on")]


WORKSHOP_SPRINKLER = make_structure(
    name="Workshop Sprinkler",
    compute_cost=4,
    clankers_archetype=ARTILLERY,
    text="At end of your turn, ready an additional exhausted add-on you control.",
    setup_interceptors=_workshop_sprinkler_setup,
)


# Shared Bus (neutral) — first part you play each turn costs 1 less
def _shared_bus_setup(obj: GameObject, state: GameState):
    """TRANSFORM on CLANKERS_COMPUTE_SPEND: if the source is a part and the
    controller hasn't played a part this turn yet, subtract 1 (min 0)."""

    def filter_fn(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_COMPUTE_SPEND:
            return False
        if ev.payload.get("player_id") != obj.controller:
            return False
        if getattr(st, "shared_bus_used", {}).get(obj.controller, False):
            return False
        source_id = ev.payload.get("source_card_id")
        if source_id is None:
            return False
        src = st.objects.get(source_id)
        if src is None or src.card_def is None:
            return False
        # Only weapons or add-ons count as "parts".
        if not (_is_weapon(src.card_def) or _is_add_on(src.card_def)):
            return False
        return True

    def handler(ev: Event, st: GameState) -> InterceptorResult:
        # Mark as used.
        if not hasattr(st, "shared_bus_used"):
            st.shared_bus_used = {}
        st.shared_bus_used[obj.controller] = True
        new_payload = dict(ev.payload)
        new_payload["amount"] = max(0, int(new_payload.get("amount", 0)) - 1)
        new_payload["shared_bus_discount"] = 1
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

    discount_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        description="Shared Bus: first part each turn -1 Compute",
        duration="while_on_battlefield",
    )

    # Reset the once-per-turn flag at turn start.
    def reset_fn(ev: Event, st: GameState):
        if hasattr(st, "shared_bus_used"):
            st.shared_bus_used[obj.controller] = False
        return []

    reset_ic = _on_turn_start_trigger(obj, reset_fn, description="Shared Bus: reset once-per-turn")

    return [discount_ic, reset_ic]


SHARED_BUS = make_structure(
    name="Shared Bus",
    compute_cost=2,
    clankers_archetype=NEUTRAL,
    text="The first part you play each turn costs 1 less Compute (min 0).",
    setup_interceptors=_shared_bus_setup,
)


# Public Telemetry (neutral) — at EoT, if 0 Transients played, +1 Compute next turn
def _public_telemetry_setup(obj: GameObject, state: GameState):
    """Track transient plays via a per-turn counter; at end of turn, if 0,
    bump next-turn compute pool. The bump is applied at the next CLANKERS_TURN_START.
    """

    def track_transient_filter(ev: Event, st: GameState) -> bool:
        if ev.type != EventType.CLANKERS_COMPUTE_SPEND:
            return False
        if ev.payload.get("player_id") != obj.controller:
            return False
        source_id = ev.payload.get("source_card_id")
        if source_id is None:
            return False
        src = st.objects.get(source_id)
        if src is None or src.card_def is None:
            return False
        return (CardType.CLANKERS_TRANSIENT in src.characteristics.types)

    def track_handler(ev: Event, st: GameState) -> InterceptorResult:
        st.public_telemetry_transients = getattr(st, "public_telemetry_transients", {})
        st.public_telemetry_transients[obj.controller] = (
            st.public_telemetry_transients.get(obj.controller, 0) + 1
        )
        return InterceptorResult(action=InterceptorAction.PASS)

    track_ic = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=track_transient_filter,
        handler=track_handler,
        description="Public Telemetry: track transient plays",
        duration="while_on_battlefield",
    )

    def end_react(ev: Event, st: GameState):
        # Defensive init: the track_ic above only assigns when a transient
        # is played; if none played this turn the attribute won't exist yet.
        if not hasattr(st, "public_telemetry_transients"):
            st.public_telemetry_transients = {}
        played = st.public_telemetry_transients.get(obj.controller, 0)
        st.public_telemetry_transients[obj.controller] = 0
        if played != 0:
            return []
        # Queue a +1 compute for next turn.
        if not hasattr(st, "public_telemetry_pending"):
            st.public_telemetry_pending = {}
        st.public_telemetry_pending[obj.controller] = (
            st.public_telemetry_pending.get(obj.controller, 0) + 1
        )
        return []

    def start_react(ev: Event, st: GameState):
        if not hasattr(st, "public_telemetry_pending"):
            st.public_telemetry_pending = {}
        pending = st.public_telemetry_pending.get(obj.controller, 0)
        if pending <= 0:
            return []
        st.public_telemetry_pending[obj.controller] = 0
        cur = int(st.clankers_compute_pool.get(obj.controller, 0))
        st.clankers_compute_pool[obj.controller] = cur + pending
        return [Event(
            type=EventType.CLANKERS_COMPUTE_GAIN,
            payload={
                "player_id": obj.controller,
                "amount": pending,
                "reason": "public_telemetry",
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        track_ic,
        _on_turn_end_trigger(obj, end_react, description="Public Telemetry: queue compute"),
        _on_turn_start_trigger(obj, start_react, description="Public Telemetry: apply compute"),
    ]


PUBLIC_TELEMETRY = make_structure(
    name="Public Telemetry",
    compute_cost=3,
    clankers_archetype=NEUTRAL,
    text=("At end of your turn, if you played 0 Transients this turn, "
          "gain 1 Compute next turn (above your cap, that turn only)."),
    setup_interceptors=_public_telemetry_setup,
)


# Auxiliary Bench (neutral) — activated: pay 1 scrap, Reassemble: free attach
def _auxiliary_bench_setup(obj: GameObject, state: GameState):
    """Activated ability: spend 1 scrap to attach one solo part you control
    to a chassis with an open matching slot. Targets supplied via payload."""

    def effect_fn(ev: Event, st: GameState):
        if not _spend_scrap(st, obj.controller, 1):
            return []
        targets = list(ev.payload.get("targets") or [])
        # targets is expected to be [part_id, chassis_id].
        if len(targets) < 2:
            return [Event(
                type=EventType.CLANKERS_SCRAP_SPEND,
                payload={
                    "player_id": obj.controller,
                    "amount": 1,
                    "source_card_id": obj.id,
                    "reason": "auxiliary_bench_no_targets",
                },
                source=obj.id,
                controller=obj.controller,
            )]
        part_id, chassis_id = targets[0], targets[1]
        events = [Event(
            type=EventType.CLANKERS_SCRAP_SPEND,
            payload={
                "player_id": obj.controller,
                "amount": 1,
                "source_card_id": obj.id,
                "reason": "auxiliary_bench_cost",
            },
            source=obj.id,
            controller=obj.controller,
        )]
        events.extend(attach_part(st, part_id, chassis_id))
        return events

    return [make_weapon_activated(
        obj,
        compute_cost=0,
        exhaust_self=False,
        effect_fn=effect_fn,
        description="Auxiliary Bench: pay 1 scrap to free-attach a solo part",
    )]


AUXILIARY_BENCH = make_structure(
    name="Auxiliary Bench",
    compute_cost=1,
    clankers_archetype=NEUTRAL,
    text=("Pay 1 scrap, Reassemble: put a solo Weapon or Add-On you control "
          "onto a chassis you control with an open slot. "
          "(Free Modular for one part.)"),
    setup_interceptors=_auxiliary_bench_setup,
)


# =============================================================================
# Aggregate
# =============================================================================

BULWARK_CARDS = {
    # Core
    "BULWARK-9": BULWARK_9,
    # Chassis (artillery)
    "Vault Chassis": VAULT_CHASSIS,
    "Bastion Frame": BASTION_FRAME,
    "Sentinel Crane": SENTINEL_CRANE,
    "Embankment": EMBANKMENT,
    "Containment Sergeant": CONTAINMENT_SERGEANT,
    "Ready-Up Engineer": READY_UP_ENGINEER,
    "Counterweight Walker": COUNTERWEIGHT_WALKER,
    "Mortar Lieutenant": MORTAR_LIEUTENANT,
    "Foreman's Watch": FOREMANS_WATCH,
    # Chassis (neutral)
    "Workshop Prototype": WORKSHOP_PROTOTYPE,
    # Weapons (artillery)
    "Riot Baton": RIOT_BATON,
    "Containment Whip": CONTAINMENT_WHIP,
    "Riot Mortar": RIOT_MORTAR,
    "Stunner Arm": STUNNER_ARM,
    "Sentinel Cannon": SENTINEL_CANNON,
    "Heavy Watchpost": HEAVY_WATCHPOST,
    "Burnout Cannon": BURNOUT_CANNON,
    "Containment Pike": CONTAINMENT_PIKE,
    # Weapons (neutral)
    "Standard Issue Blaster": STANDARD_ISSUE_BLASTER,
    "Workshop Wrench": WORKSHOP_WRENCH,
    "Riveter Mk-I": RIVETER_MK_I,
    "Spare Coilgun": SPARE_COILGUN,
    # Add-Ons (artillery)
    "Reactive Shielding": REACTIVE_SHIELDING,
    "Vault Bracer": VAULT_BRACER,
    "Riot Plating": RIOT_PLATING,
    "Bunker Cradle": BUNKER_CRADLE,
    "Counterweight Sleeve": COUNTERWEIGHT_SLEEVE,
    "Coolant Cradle": COOLANT_CRADLE,
    "Containment Lining": CONTAINMENT_LINING,
    "Spotter Rig": SPOTTER_RIG,
    # Transients (artillery)
    "Burnout Protocol": BURNOUT_PROTOCOL,
    "Repair Subroutine": REPAIR_SUBROUTINE,
    "Containment Recall": CONTAINMENT_RECALL,
    # Transients (neutral)
    "Scrap Salvo": SCRAP_SALVO,
    # Structures (artillery)
    "Containment Baffle": CONTAINMENT_BAFFLE,
    "Workshop Sprinkler": WORKSHOP_SPRINKLER,
    # Structures (neutral)
    "Shared Bus": SHARED_BUS,
    "Public Telemetry": PUBLIC_TELEMETRY,
    "Auxiliary Bench": AUXILIARY_BENCH,
}
