"""SCP Containment TCG core helpers.

This mode is intentionally not another combat/mana game. Each player is a
Foundation Site. Cards move through a paperwork queue, anomalies create breach
pressure, personnel are assigned to containment/research/suppression checks,
and players win by building classified Archives before their Site collapses.
"""

from __future__ import annotations

from typing import Optional

from .types import (
    CardDefinition,
    CardType,
    Characteristics,
    Event,
    EventType,
    GameObject,
    GameState,
    Player,
    ZoneType,
)


STARTING_SECRECY = 10
ARCHIVES_TO_WIN = 7
BREACH_LIMIT = 12
ETHICS_LIMIT = 8

TASKS = ("contain", "research", "suppress")
MOOD_MODS = {
    "docile": {"hazard": -1, "containment": 0, "curiosity": 0},
    "agitated": {"hazard": 1, "containment": 1, "curiosity": 0},
    "cryptic": {"hazard": 0, "containment": 0, "curiosity": 2},
    "cooperative": {"hazard": -1, "containment": -1, "curiosity": -1},
}
PROTOCOL_MODS = {
    "mirror_box": {"hazard": 0, "containment": -1, "curiosity": 1},
    "no_eye_contact": {"hazard": -1, "containment": 1, "curiosity": 0},
    "feed_it_lies": {"hazard": 1, "containment": 0, "curiosity": -2},
    "ritual_diagram": {"hazard": 0, "containment": -2, "curiosity": 2},
}


def _site_defaults() -> dict:
    return {
        "secrecy": STARTING_SECRECY,
        "breach": 0,
        "archives": 0,
        "ethics_debt": 0,
        "clearance": 2,
        "briefing": 0,
        "assignment_slots": 2,
        "assignments_used": 0,
    }


def ensure_scp_state(state: GameState, player_id: str) -> None:
    state.scp_sites.setdefault(player_id, _site_defaults())
    for key, value in _site_defaults().items():
        state.scp_sites[player_id].setdefault(key, value)
    state.scp_anomalies.setdefault(player_id, [])
    state.scp_contained.setdefault(player_id, [])
    state.scp_personnel.setdefault(player_id, [])
    state.scp_facilities.setdefault(player_id, [])
    state.scp_mandates.setdefault(player_id, [])
    state.scp_incidents.setdefault(player_id, [])
    # MNR: forgotten zone for antimeme decay (per-player list of object IDs).
    if not hasattr(state, "scp_forgotten"):
        state.scp_forgotten = {}
    state.scp_forgotten.setdefault(player_id, [])


def setup_scp_player(game, player: Player) -> None:
    """Initialise a player as a Site. Life is not a loss condition here."""
    player.life = 0
    player.max_life = 0
    player.has_lost = False
    ensure_scp_state(game.state, player.id)


def site(state: GameState, player_id: str) -> dict:
    ensure_scp_state(state, player_id)
    return state.scp_sites[player_id]


def _zone_key(zone_type: ZoneType, owner_id: Optional[str]) -> Optional[str]:
    if zone_type in {ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD}:
        return f"{zone_type.name.lower()}_{owner_id}" if owner_id else None
    if zone_type in {ZoneType.BATTLEFIELD, ZoneType.STACK, ZoneType.EXILE, ZoneType.COMMAND}:
        return zone_type.name.lower()
    return None


def _move(game, obj: GameObject, to_zone: ZoneType, *, source: Optional[str] = None) -> list[Event]:
    event = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone_type": obj.zone,
            "to_zone_type": to_zone,
            "from_zone": _zone_key(obj.zone, obj.owner),
            "to_zone": _zone_key(to_zone, obj.owner),
        },
        source=source,
        controller=obj.controller,
    )
    return game.emit(event)


def _active_bonus(state: GameState, player_id: str, task: str) -> int:
    """Sum static task bonuses contributed by facilities, mandates, and contained anomalies.

    Reads three attribute conventions:
      - ``scp_bonus`` on active facilities / mandates (existing).
      - ``scp_contained_bonus`` on contained anomalies — a dict shaped the same
        as ``scp_bonus`` (e.g. ``{"research": 1, "contain": 1}``). This lets a
        contained anomaly act as an "aura" reward for keeping it locked away.
        Cards that omit the attribute are no-ops via ``getattr`` default.
    """
    ensure_scp_state(state, player_id)
    total = 0
    for facility_id in list(state.scp_facilities.get(player_id, [])):
        facility = state.objects.get(facility_id)
        if not facility or facility.zone != ZoneType.BATTLEFIELD or facility.state.scp_status != "active":
            continue
        bonuses = getattr(facility.card_def, "scp_bonus", {}) if facility.card_def else {}
        total += int(bonuses.get(task, 0) or 0)
    for mandate_id in list(state.scp_mandates.get(player_id, [])):
        mandate = state.objects.get(mandate_id)
        if not mandate or mandate.zone != ZoneType.BATTLEFIELD or mandate.state.scp_status != "active":
            continue
        bonuses = getattr(mandate.card_def, "scp_bonus", {}) if mandate.card_def else {}
        total += int(bonuses.get(task, 0) or 0)
    for contained_id in list(state.scp_contained.get(player_id, [])):
        contained = state.objects.get(contained_id)
        if not contained or contained.zone != ZoneType.BATTLEFIELD or contained.state.scp_status != "contained":
            continue
        bonuses = getattr(contained.card_def, "scp_contained_bonus", {}) if contained.card_def else {}
        total += int((bonuses or {}).get(task, 0) or 0)
    return total


def _has_active_mandate(state: GameState, player_id: str, *, alt_win: Optional[str] = None) -> bool:
    ensure_scp_state(state, player_id)
    for mandate_id in list(state.scp_mandates.get(player_id, [])):
        mandate = state.objects.get(mandate_id)
        if not mandate or mandate.zone != ZoneType.BATTLEFIELD or mandate.state.scp_status != "active":
            continue
        if alt_win is None or getattr(mandate.card_def, "scp_alt_win", None) == alt_win:
            return True
    return False


def _card_types(obj: GameObject) -> set[CardType]:
    return set(obj.characteristics.types or set())


def _index_active_card(state: GameState, obj: GameObject) -> None:
    controller = obj.controller
    ensure_scp_state(state, controller)
    types = _card_types(obj)
    if CardType.SCP_ANOMALY in types:
        if obj.id not in state.scp_anomalies[controller]:
            state.scp_anomalies[controller].append(obj.id)
    elif CardType.SCP_PERSONNEL in types:
        if obj.id not in state.scp_personnel[controller]:
            state.scp_personnel[controller].append(obj.id)
    elif CardType.SCP_FACILITY in types:
        if obj.id not in state.scp_facilities[controller]:
            state.scp_facilities[controller].append(obj.id)
    elif CardType.SCP_MANDATE in types:
        if obj.id not in state.scp_mandates[controller]:
            state.scp_mandates[controller].append(obj.id)


def _deindex_card(state: GameState, obj: GameObject) -> None:
    registries = [
        state.scp_anomalies,
        state.scp_contained,
        state.scp_personnel,
        state.scp_facilities,
        state.scp_mandates,
    ]
    # MNR: also scrub forgotten zone so a doubly-routed move can't leave
    # stale references. (Forgotten anomalies are never expected to be
    # touched by other systems, but keep the bookkeeping symmetric.)
    forgotten = getattr(state, "scp_forgotten", None)
    if forgotten is not None:
        registries.append(forgotten)
    for registry in registries:
        for ids in registry.values():
            while obj.id in ids:
                ids.remove(obj.id)


def _activate_dossier(game, obj: GameObject, *, auto_seal_default: bool = False) -> list[Event]:
    """Transition a dossier from pending/just-opened into the active state.

    ``auto_seal_default``: when True and the underlying anomaly card_def carries
    ``scp_seal_default = True``, the dossier runs its on-reveal hook (so mood
    seeding, secrecy/breach hits, and other W1 reveal effects still fire) and
    is then immediately converted to the ``sealed`` state, deindexed from the
    active-anomaly registry, and an ``SCP_SEAL_DOSSIER`` event is emitted.
    This is the open-time path; ``reveal_dossier`` always passes
    ``auto_seal_default=False`` so an explicit reveal does not re-seal.
    """
    state = game.state
    obj.state.scp_status = "active"
    obj.state.scp_paperwork = 0
    _index_active_card(state, obj)
    events = game.emit(Event(
        type=EventType.SCP_ACTIVATE_DOSSIER,
        payload={"object_id": obj.id, "controller": obj.controller},
        source=obj.id,
        controller=obj.controller,
    ))

    types = _card_types(obj)
    if CardType.SCP_ANOMALY in types:
        events.extend(game.emit(Event(
            type=EventType.SCP_ANOMALY_REVEALED,
            payload={
                "object_id": obj.id,
                "controller": obj.controller,
                "hazard": getattr(obj.card_def, "scp_hazard", 0),
            },
            source=obj.id,
            controller=obj.controller,
        )))
        hook = getattr(obj.card_def, "scp_on_reveal", None)
        if callable(hook):
            for event in hook(obj, state) or []:
                events.extend(game.emit(event))
        # After the reveal hook has fired, convert the anomaly to sealed when
        # its card_def declares ``scp_seal_default = True`` and the caller
        # requested auto-seal. The mood / secrecy / breach effects of the
        # reveal hook are intentionally preserved; only the public status flips.
        if auto_seal_default and getattr(obj.card_def, "scp_seal_default", False):
            obj.state.scp_status = "sealed"
            # Remove from the active-anomaly registry (sealed dossiers are not
            # exposed as active anomalies for hazard / test / aura purposes).
            anomaly_list = state.scp_anomalies.get(obj.controller, [])
            while obj.id in anomaly_list:
                anomaly_list.remove(obj.id)
            events.extend(game.emit(Event(
                type=EventType.SCP_SEAL_DOSSIER,
                payload={
                    "player": obj.controller,
                    "object_id": obj.id,
                    "reason": "seal_default",
                },
                source=obj.id,
                controller=obj.controller,
            )))
    elif CardType.SCP_PROCEDURE in types:
        hook = getattr(obj.card_def, "scp_effect", None)
        if callable(hook):
            try:
                produced = hook(obj, state, game)
            except TypeError:
                produced = hook(obj, state)
            for event in produced or []:
                if getattr(event, "timestamp", 0) or event in state.event_log:
                    events.append(event)
                else:
                    events.extend(game.emit(event))
        _deindex_card(state, obj)
        _move(game, obj, ZoneType.GRAVEYARD, source=obj.id)
    return events


def open_dossier(
    game,
    player_id: str,
    card_id: str,
    *,
    fast_track: bool = False,
    sealed: bool = False,
) -> tuple[bool, str, list[Event]]:
    """Play a card by opening its dossier.

    Red tape is not a resource cost. It is a delay. Fast-tracking bypasses the
    delay but reduces secrecy, making speed a public-exposure risk.
    """
    state = game.state
    ensure_scp_state(state, player_id)
    obj = state.objects.get(card_id)
    if not obj or obj.owner != player_id:
        return False, "Card not found", []
    if obj.zone != ZoneType.HAND:
        return False, "Card is not in hand", []
    if not obj.card_def:
        return False, "Card has no definition", []

    clearance = int(getattr(obj.card_def, "scp_clearance", 0) or 0)
    if site(state, player_id)["clearance"] < clearance:
        return False, "Insufficient clearance", []

    if sealed and CardType.SCP_ANOMALY not in _card_types(obj):
        return False, "Only anomalies can be sealed", []

    red_tape = max(0, int(getattr(obj.card_def, "scp_red_tape", 0) or 0))
    events: list[Event] = []
    if fast_track and red_tape > 0:
        site(state, player_id)["secrecy"] -= red_tape
        events.extend(game.emit(Event(
            type=EventType.SCP_FAST_TRACK,
            payload={"player": player_id, "object_id": obj.id, "exposure": red_tape},
            source=obj.id,
            controller=player_id,
        )))
        red_tape = 0

    # ``scp_seal_default`` on an anomaly card_def means "open into sealed by
    # default after running the reveal hook." It only applies when the caller
    # did not already request an explicit sealed open (which uses the
    # no-reveal-hook semantics inherited from SZB cards).
    seal_default = (
        not sealed
        and CardType.SCP_ANOMALY in _card_types(obj)
        and bool(getattr(obj.card_def, "scp_seal_default", False))
    )

    events.extend(_move(game, obj, ZoneType.BATTLEFIELD, source=obj.id))
    obj.state.scp_status = "sealed" if sealed else ("pending" if red_tape else "active")
    obj.state.scp_paperwork = red_tape
    events.extend(game.emit(Event(
        type=EventType.SCP_OPEN_DOSSIER,
        payload={
            "player": player_id,
            "object_id": obj.id,
            "paperwork": red_tape,
            "fast_track": fast_track,
            "sealed": sealed,
        },
        source=obj.id,
        controller=player_id,
    )))
    if sealed:
        events.extend(game.emit(Event(
            type=EventType.SCP_SEAL_DOSSIER,
            payload={"player": player_id, "object_id": obj.id},
            source=obj.id,
            controller=player_id,
        )))
    elif red_tape == 0:
        events.extend(_activate_dossier(game, obj, auto_seal_default=seal_default))
    # For pending dossiers (red_tape > 0), the auto-seal still applies when
    # paperwork ticks down: ``process_paperwork`` and ``activate_dossier_now``
    # re-read ``scp_seal_default`` off the card_def, so no per-state flag is
    # needed here.
    events.extend(check_scp_loss(game))
    return True, "Dossier opened", events


def reveal_dossier(game, player_id: str, object_id: str) -> tuple[bool, str, list[Event]]:
    state = game.state
    obj = state.objects.get(object_id)
    if not obj or obj.controller != player_id:
        return False, "Dossier not found", []
    if obj.state.scp_status != "sealed":
        return False, "Dossier is not sealed", []
    events = game.emit(Event(
        type=EventType.SCP_REVEAL_DOSSIER,
        payload={"player": player_id, "object_id": obj.id},
        source=obj.id,
        controller=player_id,
    ))
    events.extend(_activate_dossier(game, obj))
    events.extend(check_scp_loss(game))
    return True, "Dossier revealed", events


def process_paperwork(game, player_id: str, amount: int = 1) -> list[Event]:
    """Advance every pending dossier for a Site."""
    state = game.state
    ensure_scp_state(state, player_id)
    events: list[Event] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return events
    for obj_id in list(battlefield.objects):
        obj = state.objects.get(obj_id)
        if not obj or obj.controller != player_id or obj.state.scp_status != "pending":
            continue
        before = obj.state.scp_paperwork
        obj.state.scp_paperwork = max(0, before - amount)
        events.extend(game.emit(Event(
            type=EventType.SCP_PAPERWORK_TICK,
            payload={"object_id": obj.id, "from": before, "to": obj.state.scp_paperwork},
            source=obj.id,
            controller=player_id,
        )))
        if obj.state.scp_paperwork == 0:
            # When a pending anomaly with ``scp_seal_default = True`` finally
            # activates via the paperwork queue, route through the auto-seal
            # path so the reveal hook fires and the dossier still ends sealed.
            seal_default = (
                CardType.SCP_ANOMALY in _card_types(obj)
                and bool(getattr(obj.card_def, "scp_seal_default", False))
            )
            events.extend(_activate_dossier(game, obj, auto_seal_default=seal_default))
    return events


def reset_staff(game, player_id: str) -> None:
    state = game.state
    ensure_scp_state(state, player_id)
    for staff_id in list(state.scp_personnel.get(player_id, [])):
        staff = state.objects.get(staff_id)
        if staff and staff.zone == ZoneType.BATTLEFIELD:
            staff.state.scp_exhausted = False
            # Per-turn assignment counter used by scp_on_assign hooks (e.g.
            # Sleep-Deprived Intern's "first assignment per turn is free"
            # quirk). Stored as a dynamic attr because GameObjectState's
            # SCP slot is otherwise full of anomaly-shaped fields.
            setattr(staff.state, "scp_assigns_this_turn", 0)


def _fire_on_assign(
    state: GameState,
    player_id: str,
    staff_ids: list[str],
    action: str,
) -> tuple[int, list[Event]]:
    """Fire ``scp_on_assign`` hooks for every staff actually used in an assignment.

    Fired AFTER ``_staff_total`` (so the staff are marked exhausted and ``used``
    is finalized) but BEFORE the test's success/fail resolution. Hooks may:

      * Mutate site state (briefing, secrecy, breach, ethics_debt, etc.).
      * Return events whose ``payload["task_bonus"]`` adds to THIS test's total.
      * Toggle ``personnel.state.scp_exhausted = False`` to veto exhaustion
        (used by Sleep-Deprived Intern's "always available" quirk).

    Hook signature: ``(personnel_obj, state, action: str) -> list[Event]``.
    The ``action`` arg is one of ``"research"``, ``"contain"``, ``"suppress"``.

    Returns ``(task_bonus, events)`` where ``task_bonus`` is summed across all
    hook-emitted events that carry a ``task_bonus`` payload key.
    """
    events: list[Event] = []
    bonus = 0
    for staff_id in staff_ids:
        staff = state.objects.get(staff_id)
        if not staff or staff.controller != player_id:
            continue
        hook = getattr(staff.card_def, "scp_on_assign", None) if staff.card_def else None
        if not callable(hook):
            continue
        # Bump per-turn assignment counter BEFORE invoking the hook so the
        # hook can read it (e.g. "first assignment per turn is free").
        prior = int(getattr(staff.state, "scp_assigns_this_turn", 0) or 0)
        setattr(staff.state, "scp_assigns_this_turn", prior + 1)
        produced = hook(staff, state, action) or []
        for event in produced:
            payload = getattr(event, "payload", None) or {}
            if isinstance(payload, dict):
                bonus += int(payload.get("task_bonus", 0) or 0)
            events.append(event)
    return bonus, events


def _staff_total(state: GameState, player_id: str, staff_ids: list[str], task: str) -> tuple[int, list[str]]:
    """Sum personnel skill contributions plus static / aura bonuses for ``task``.

    Two attribute conventions on personnel cards augment the base ``scp_skills``:
      - ``scp_aura`` on a personnel's ``card_def``. Dict keyed by selector,
        whose value is a per-task delta dict::

            {"subtype:Memetics": {"research": 1}, "any": {"contain": 1}}

        Selectors supported:
          * ``"subtype:X"`` — applies when the target personnel's subtypes
            include ``X``.
          * ``"any"`` — applies to every friendly personnel on the battlefield.

        The aura source IS counted (a "Memetics +1" lord buffs itself when its
        own subtypes match — flatly disallowing self would mean the aura's
        Memetics tag doesn't apply to itself, which the design treats as a bug
        not a feature). Auras only apply when the target personnel is active
        and assigned (i.e. while building this task's total).
      - The existing ``scp_skills`` per-task base.
    """
    ensure_scp_state(state, player_id)
    total = _active_bonus(state, player_id, task)

    # Pre-compute friendly personnel auras once.
    aura_sources: list[tuple[GameObject, dict]] = []
    for source_id in list(state.scp_personnel.get(player_id, [])):
        source = state.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD or source.state.scp_status != "active":
            continue
        aura = getattr(source.card_def, "scp_aura", None) if source.card_def else None
        if not aura:
            continue
        aura_sources.append((source, aura))

    used: list[str] = []
    for staff_id in staff_ids:
        staff = state.objects.get(staff_id)
        if not staff or staff.controller != player_id:
            continue
        if staff.zone != ZoneType.BATTLEFIELD or staff.state.scp_status != "active":
            continue
        if staff.state.scp_exhausted:
            continue
        if CardType.SCP_PERSONNEL not in _card_types(staff):
            continue
        skills = getattr(staff.card_def, "scp_skills", {}) if staff.card_def else {}
        contribution = int(skills.get(task, 0) or 0)
        staff_subtypes = set(staff.characteristics.subtypes or set()) if staff.characteristics else set()
        for _source, aura in aura_sources:
            for selector, deltas in aura.items():
                if not deltas:
                    continue
                if selector == "any":
                    contribution += int((deltas or {}).get(task, 0) or 0)
                elif isinstance(selector, str) and selector.startswith("subtype:"):
                    needed = selector.split(":", 1)[1]
                    if needed in staff_subtypes:
                        contribution += int((deltas or {}).get(task, 0) or 0)
        total += contribution
        staff.state.scp_exhausted = True
        used.append(staff.id)
    return total, used


def _consume_assignment_slot(state: GameState, player_id: str, *, emergency: bool = False) -> tuple[bool, str]:
    s = site(state, player_id)
    if emergency:
        s["ethics_debt"] += 1
        s["secrecy"] -= 1
        return True, "Emergency assignment"
    if s["assignments_used"] >= s["assignment_slots"]:
        return False, "No assignment slots remaining"
    s["assignments_used"] += 1
    return True, "Assignment slot used"


def reset_assignment_slots(state: GameState, player_id: str) -> None:
    site(state, player_id)["assignments_used"] = 0


def _effective_hazard(obj: GameObject) -> int:
    base = int(getattr(obj.card_def, "scp_hazard", 0) or 0)
    suppressed = int(getattr(obj.state, "scp_suppressed", 0) or 0)
    mood = MOOD_MODS.get(obj.state.scp_mood or "", {})
    protocol_delta = sum(int(PROTOCOL_MODS.get(p, {}).get("hazard", 0) or 0) for p in obj.state.scp_protocols)
    bound_dampening = 0
    if obj.state.scp_bound_to and obj._state_ref:
        bound = obj._state_ref.objects.get(obj.state.scp_bound_to)
        if bound and bound.zone == ZoneType.BATTLEFIELD and bound.state.scp_status == "contained":
            bound_dampening = max(1, int(getattr(bound.card_def, "scp_hazard", 0) or 0))
        else:
            obj.state.scp_bound_to = None
    return max(0, base + int(mood.get("hazard", 0) or 0) + protocol_delta - suppressed - bound_dampening)


def _effective_curiosity(obj: GameObject) -> int:
    base = int(getattr(obj.card_def, "scp_curiosity", 0) or 0)
    mood = MOOD_MODS.get(obj.state.scp_mood or "", {})
    protocol_delta = sum(int(PROTOCOL_MODS.get(p, {}).get("curiosity", 0) or 0) for p in obj.state.scp_protocols)
    return max(0, base + int(mood.get("curiosity", 0) or 0) + protocol_delta)


def _effective_containment(obj: GameObject) -> int:
    base = int(getattr(obj.card_def, "scp_containment", 0) or 0)
    mood = MOOD_MODS.get(obj.state.scp_mood or "", {})
    protocol_delta = sum(int(PROTOCOL_MODS.get(p, {}).get("containment", 0) or 0) for p in obj.state.scp_protocols)
    return max(0, base + int(mood.get("containment", 0) or 0) + protocol_delta)


def run_test(game, player_id: str, anomaly_id: str, staff_ids: list[str], *, emergency: bool = False) -> tuple[bool, str, list[Event]]:
    """Research an active anomaly. Success gains Archives; failure leaks."""
    state = game.state
    anomaly = state.objects.get(anomaly_id)
    if not anomaly or anomaly.controller != player_id or CardType.SCP_ANOMALY not in _card_types(anomaly):
        return False, "Anomaly not found", []
    if anomaly.state.scp_status != "active":
        return False, "Anomaly is not active", []
    ok_slot, slot_message = _consume_assignment_slot(state, player_id, emergency=emergency)
    if not ok_slot:
        return False, slot_message, []

    total, used = _staff_total(state, player_id, staff_ids, "research")
    target = _effective_curiosity(anomaly)
    events = game.emit(Event(
        type=EventType.SCP_ASSIGN_STAFF,
        payload={"player": player_id, "task": "research", "staff_ids": used, "anomaly_id": anomaly_id},
        source=anomaly.id,
        controller=player_id,
    ))
    # AGENT C: scp_on_assign hook (personnel-side, fires per used staff,
    # action="research"). Hooks fire AFTER _staff_total has marked staff
    # exhausted so they can veto exhaustion or grant a task_bonus delta.
    assign_bonus, assign_events = _fire_on_assign(state, player_id, used, "research")
    for event in assign_events:
        events.extend(game.emit(event))
    total += assign_bonus
    success = total >= target
    events.extend(game.emit(Event(
        type=EventType.SCP_TEST_RUN,
        payload={"player": player_id, "anomaly_id": anomaly_id, "total": total, "target": target, "success": success},
        source=anomaly.id,
        controller=player_id,
    )))
    if success:
        anomaly.state.scp_researched += 1
        events.extend(gain_archives(game, player_id, 1, source=anomaly.id))
        hook = getattr(anomaly.card_def, "scp_on_test", None)
        if callable(hook):
            for event in hook(anomaly, state) or []:
                events.extend(game.emit(event))
    else:
        leak = max(1, _effective_hazard(anomaly) - total)
        site(state, player_id)["secrecy"] -= 1
        site(state, player_id)["breach"] += leak
        # scp_on_test_fail mirrors scp_on_test for the failure branch. Hook
        # signature: (obj, state) -> list[Event]. Mechanic agents may use this
        # for "test-time exhaustion" effects that fire on miss.
        fail_hook = getattr(anomaly.card_def, "scp_on_test_fail", None)
        if callable(fail_hook):
            for event in fail_hook(anomaly, state) or []:
                events.extend(game.emit(event))
    events.extend(check_scp_loss(game))
    return True, "Test complete", events


def contain_anomaly(game, player_id: str, anomaly_id: str, staff_ids: list[str], *, emergency: bool = False) -> tuple[bool, str, list[Event]]:
    """Contain an active anomaly. Contained anomalies stop breach ticking."""
    state = game.state
    anomaly = state.objects.get(anomaly_id)
    if not anomaly or anomaly.controller != player_id or CardType.SCP_ANOMALY not in _card_types(anomaly):
        return False, "Anomaly not found", []
    if anomaly.state.scp_status != "active":
        return False, "Anomaly is not active", []
    ok_slot, slot_message = _consume_assignment_slot(state, player_id, emergency=emergency)
    if not ok_slot:
        return False, slot_message, []

    total, used = _staff_total(state, player_id, staff_ids, "contain")
    target = _effective_containment(anomaly)
    events = game.emit(Event(
        type=EventType.SCP_ASSIGN_STAFF,
        payload={"player": player_id, "task": "contain", "staff_ids": used, "anomaly_id": anomaly_id},
        source=anomaly.id,
        controller=player_id,
    ))
    # AGENT C: scp_on_assign hook (personnel-side, fires per used staff,
    # action="contain"). Same pattern as run_test — hooks fire BEFORE the
    # contain/fail decision so they can grant a task_bonus.
    assign_bonus, assign_events = _fire_on_assign(state, player_id, used, "contain")
    for event in assign_events:
        events.extend(game.emit(event))
    total += assign_bonus
    success = total >= target
    events.extend(game.emit(Event(
        type=EventType.SCP_CONTAINMENT_ATTEMPT,
        payload={"player": player_id, "anomaly_id": anomaly_id, "total": total, "target": target, "success": success},
        source=anomaly.id,
        controller=player_id,
    )))
    if success:
        anomaly.state.scp_status = "contained"
        if anomaly.id in state.scp_anomalies[player_id]:
            state.scp_anomalies[player_id].remove(anomaly.id)
        if anomaly.id not in state.scp_contained[player_id]:
            state.scp_contained[player_id].append(anomaly.id)
        events.extend(game.emit(Event(
            type=EventType.SCP_CONTAINED,
            payload={"player": player_id, "anomaly_id": anomaly.id},
            source=anomaly.id,
            controller=player_id,
        )))
        events.extend(gain_archives(game, player_id, 2, source=anomaly.id))
        hook = getattr(anomaly.card_def, "scp_on_contain", None)
        if callable(hook):
            for event in hook(anomaly, state) or []:
                events.extend(game.emit(event))
    else:
        site(state, player_id)["breach"] += max(1, _effective_hazard(anomaly))
        site(state, player_id)["secrecy"] -= 1
    events.extend(check_scp_loss(game))
    return True, "Containment complete", events


def suppress_anomaly(game, player_id: str, anomaly_id: str, staff_ids: list[str], *, emergency: bool = False) -> tuple[bool, str, list[Event]]:
    """Suppress an anomaly's next breach tick."""
    state = game.state
    anomaly = state.objects.get(anomaly_id)
    if not anomaly or anomaly.controller != player_id or CardType.SCP_ANOMALY not in _card_types(anomaly):
        return False, "Anomaly not found", []
    if anomaly.state.scp_status != "active":
        return False, "Anomaly is not active", []
    ok_slot, slot_message = _consume_assignment_slot(state, player_id, emergency=emergency)
    if not ok_slot:
        return False, slot_message, []
    hazard_before = _effective_hazard(anomaly)
    total, used = _staff_total(state, player_id, staff_ids, "suppress")
    # AGENT C: scp_on_assign hook (personnel-side, fires per used staff,
    # action="suppress"). Same pattern as run_test — hooks fire BEFORE the
    # suppression total is applied so they can grant a task_bonus. The
    # task_bonus contributes BEFORE anomaly.state.scp_suppressed is bumped.
    assign_bonus, assign_events = _fire_on_assign(state, player_id, used, "suppress")
    total += assign_bonus
    anomaly.state.scp_suppressed += total
    events = game.emit(Event(
        type=EventType.SCP_ASSIGN_STAFF,
        payload={"player": player_id, "task": "suppress", "staff_ids": used, "anomaly_id": anomaly_id, "total": total},
        source=anomaly.id,
        controller=player_id,
    ))
    for event in assign_events:
        events.extend(game.emit(event))
    redaction_target = max(hazard_before, _effective_containment(anomaly))
    if used and hazard_before > 0 and total >= redaction_target and _has_active_mandate(state, player_id, alt_win="veil_lockdown"):
        anomaly.state.scp_status = "contained"
        if anomaly.id in state.scp_anomalies[player_id]:
            state.scp_anomalies[player_id].remove(anomaly.id)
        if anomaly.id not in state.scp_contained[player_id]:
            state.scp_contained[player_id].append(anomaly.id)
        events.extend(game.emit(Event(
            type=EventType.SCP_CONTAINED,
            payload={"player": player_id, "anomaly_id": anomaly.id, "reason": "veil_lockdown"},
            source=anomaly.id,
            controller=player_id,
        )))
        events.extend(gain_archives(game, player_id, 2, source=anomaly.id))
    return True, "Suppressed", events


def breach_tick(game, player_id: str) -> list[Event]:
    """Apply breach pressure from active, uncontained anomalies."""
    state = game.state
    ensure_scp_state(state, player_id)
    total = 0
    for anomaly_id in list(state.scp_anomalies.get(player_id, [])):
        anomaly = state.objects.get(anomaly_id)
        if not anomaly or anomaly.zone != ZoneType.BATTLEFIELD or anomaly.state.scp_status != "active":
            continue
        total += _effective_hazard(anomaly)
        anomaly.state.scp_suppressed = 0
    if site(state, player_id)["ethics_debt"] >= 5:
        total += 1
    site(state, player_id)["breach"] += total
    events = game.emit(Event(
        type=EventType.SCP_BREACH_TICK,
        payload={"player": player_id, "amount": total, "breach": site(state, player_id)["breach"]},
        source="SCP_SYSTEM",
        controller=player_id,
    ))
    if total > 0:
        events.extend(incident_tick(game, player_id))
    events.extend(check_scp_loss(game))
    events.extend(check_scp_victory(game))
    return events


def activate_dossier_now(game, obj: GameObject, *, source: Optional[str] = None) -> list[Event]:
    """Activate exactly one pending dossier.

    Card effects use this instead of a huge paperwork tick so they do not
    accidentally advance the whole queue. Honors ``scp_seal_default`` like
    ``process_paperwork`` does, so a card that yanks a sealed-by-default
    anomaly off the pending queue still ends up sealed after its reveal hook.
    """
    if obj.zone != ZoneType.BATTLEFIELD or obj.state.scp_status != "pending":
        return []
    obj.state.scp_paperwork = 0
    seal_default = (
        CardType.SCP_ANOMALY in _card_types(obj)
        and bool(getattr(obj.card_def, "scp_seal_default", False))
    )
    return _activate_dossier(game, obj, auto_seal_default=seal_default)


def shift_mood(
    game,
    player_id: str,
    anomaly_id: str,
    mood: str,
    *,
    source: Optional[str] = None,
) -> tuple[bool, str, list[Event]]:
    if mood not in MOOD_MODS:
        return False, "Unknown anomaly mood", []
    anomaly = game.state.objects.get(anomaly_id)
    if not anomaly or anomaly.controller != player_id or CardType.SCP_ANOMALY not in _card_types(anomaly):
        return False, "Anomaly not found", []
    if anomaly.state.scp_status not in {"active", "sealed", "contained"}:
        return False, "Mood shift requires an opened anomaly", []
    if source is None:
        s = site(game.state, player_id)
        if s["briefing"] <= 0:
            return False, "Mood shift requires a briefing token", []
        s["briefing"] -= 1
    old = anomaly.state.scp_mood
    anomaly.state.scp_mood = mood
    events = game.emit(Event(
        type=EventType.SCP_MOOD_SHIFT,
        payload={"object_id": anomaly.id, "from": old, "to": mood},
        source=source or anomaly.id,
        controller=player_id,
    ))
    return True, "Mood shifted", events


def incident_tick(game, player_id: str) -> list[Event]:
    """Deterministic incident table keyed off current breach pressure."""
    state = game.state
    ensure_scp_state(state, player_id)
    s = site(state, player_id)
    active = [
        state.objects[aid]
        for aid in state.scp_anomalies.get(player_id, [])
        if aid in state.objects and state.objects[aid].state.scp_status == "active"
    ]
    roll = (state.turn_number + s["breach"] + len(active)) % 4
    incident = ("false_alarm", "paperwork_storm", "sympathy_leak", "hostility_spike")[roll]
    payload = {"player": player_id, "incident": incident}
    if incident == "false_alarm":
        s["secrecy"] -= 1
    elif incident == "paperwork_storm":
        for obj in state.objects.values():
            if obj.controller == player_id and obj.state.scp_status == "pending":
                obj.state.scp_paperwork += 1
        payload["pending_taxed"] = True
    elif incident == "sympathy_leak":
        s["ethics_debt"] = max(0, s["ethics_debt"] - 1)
        s["secrecy"] -= 1
    elif active:
        active[0].state.scp_mood = "agitated"
        payload["mood_shifted"] = active[0].id
    state.scp_incidents[player_id].append({
        "name": incident,
        "turn": state.turn_number,
        "breach": s["breach"],
    })
    return game.emit(Event(
        type=EventType.SCP_INCIDENT,
        payload=payload,
        source="SCP_SYSTEM",
        controller=player_id,
    ))


def resolve_incident(game, player_id: str, index: int = 0) -> tuple[bool, str, list[Event]]:
    state = game.state
    ensure_scp_state(state, player_id)
    incidents = state.scp_incidents[player_id]
    if index < 0 or index >= len(incidents):
        return False, "Incident not found", []
    incident = incidents.pop(index)
    site(state, player_id)["briefing"] += 1
    if incident.get("name") == "paperwork_storm":
        site(state, player_id)["secrecy"] += 1
    elif incident.get("name") == "hostility_spike":
        site(state, player_id)["breach"] = max(0, site(state, player_id)["breach"] - 1)
    events = game.emit(Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={"player": player_id, "incident": incident},
        source="SCP_SYSTEM",
        controller=player_id,
    ))
    return True, "Incident resolved", events


def apply_protocol(
    game,
    player_id: str,
    anomaly_id: str,
    protocol: str,
    *,
    source: Optional[str] = None,
) -> tuple[bool, str, list[Event]]:
    state = game.state
    anomaly = state.objects.get(anomaly_id)
    if protocol not in PROTOCOL_MODS:
        return False, "Unknown protocol", []
    if not anomaly or anomaly.controller != player_id or CardType.SCP_ANOMALY not in _card_types(anomaly):
        return False, "Anomaly not found", []
    if anomaly.state.scp_status not in {"active", "sealed", "contained"}:
        return False, "Protocol requires a known anomaly", []
    contradiction = bool(anomaly.state.scp_protocols and protocol not in anomaly.state.scp_protocols)
    if protocol not in anomaly.state.scp_protocols:
        anomaly.state.scp_protocols.append(protocol)
    if contradiction:
        site(state, player_id)["ethics_debt"] += 1
    events = game.emit(Event(
        type=EventType.SCP_PROTOCOL_APPLIED,
        payload={
            "player": player_id,
            "anomaly_id": anomaly.id,
            "protocol": protocol,
            "contradiction": contradiction,
        },
        source=source or anomaly.id,
        controller=player_id,
    ))
    events.extend(check_scp_loss(game))
    return True, "Protocol applied", events


def goi_raid(
    game,
    target_id: str,
    *,
    faction: str = "Chaos Insurgency",
    source: Optional[str] = None,
) -> list[Event]:
    """External pressure that is neither player combat nor spell targeting."""
    state = game.state
    ensure_scp_state(state, target_id)
    active = [
        state.objects[aid]
        for aid in state.scp_anomalies.get(target_id, [])
        if aid in state.objects and state.objects[aid].state.scp_status == "active"
    ]
    pending = [
        obj for obj in state.objects.values()
        if obj.controller == target_id and obj.state.scp_status == "pending"
    ]
    payload = {"target": target_id, "faction": faction}
    if active:
        target = max(active, key=_effective_hazard)
        target.state.scp_mood = "agitated"
        site(state, target_id)["breach"] += 1
        payload["anomaly_id"] = target.id
        payload["effect"] = "agitated_active_anomaly"
    elif pending:
        pending[0].state.scp_paperwork += 2
        payload["object_id"] = pending[0].id
        payload["effect"] = "paperwork_sabotage"
    else:
        site(state, target_id)["secrecy"] -= 1
        payload["effect"] = "public_leak"
    events = game.emit(Event(
        type=EventType.SCP_GOI_RAID,
        payload=payload,
        source=source or "GOI",
        controller=target_id,
    ))
    events.extend(check_scp_loss(game))
    return events


def cross_contain(
    game,
    player_id: str,
    contained_id: str,
    active_id: str,
    *,
    source: Optional[str] = None,
) -> tuple[bool, str, list[Event]]:
    """Use one contained anomaly as a bespoke countermeasure for another."""
    state = game.state
    contained = state.objects.get(contained_id)
    active = state.objects.get(active_id)
    if not contained or contained.controller != player_id or contained.state.scp_status != "contained":
        return False, "Contained anomaly not available", []
    if not active or active.controller != player_id or active.state.scp_status != "active":
        return False, "Active anomaly not available", []
    if CardType.SCP_ANOMALY not in _card_types(contained) or CardType.SCP_ANOMALY not in _card_types(active):
        return False, "Both objects must be anomalies", []
    dampening = max(1, int(getattr(contained.card_def, "scp_hazard", 0) or 0))
    active.state.scp_bound_to = contained.id
    events = game.emit(Event(
        type=EventType.SCP_CROSS_CONTAINMENT,
        payload={"player": player_id, "contained_id": contained.id, "active_id": active.id, "dampening": dampening},
        source=source or contained.id,
        controller=player_id,
    ))
    return True, "Cross-containment established", events


def memory_hole(game, player_id: str, object_id: str, *, source: Optional[str] = None) -> tuple[bool, str, list[Event]]:
    """Redact a non-active dossier into exile, gaining secrecy at archive cost."""
    state = game.state
    obj = state.objects.get(object_id)
    if not obj or obj.controller != player_id:
        return False, "Object not found", []
    if obj.zone != ZoneType.BATTLEFIELD:
        return False, "Only opened dossiers can be memory-holed", []
    if obj.state.scp_status == "active":
        return False, "Active anomalies cannot be memory-holed safely", []
    _deindex_card(state, obj)
    site(state, player_id)["secrecy"] += 1
    site(state, player_id)["archives"] = max(0, site(state, player_id)["archives"] - 1)
    events = game.emit(Event(
        type=EventType.SCP_MEMORY_HOLE,
        payload={"player": player_id, "object_id": obj.id},
        source=source,
        controller=player_id,
    ))
    events.extend(_move(game, obj, ZoneType.EXILE, source=source))
    events.extend(check_scp_victory(game, source=source))
    return True, "Memory-holed", events


def effective_hazard_for_ai(obj: GameObject) -> int:
    return _effective_hazard(obj)


def effective_curiosity_for_ai(obj: GameObject) -> int:
    return _effective_curiosity(obj)


def effective_containment_for_ai(obj: GameObject) -> int:
    return _effective_containment(obj)


def gain_archives(game, player_id: str, amount: int, *, source: Optional[str] = None) -> list[Event]:
    state = game.state
    ensure_scp_state(state, player_id)
    site(state, player_id)["archives"] += max(0, amount)
    events = game.emit(Event(
        type=EventType.SCP_ARCHIVE_GAINED,
        payload={"player": player_id, "amount": amount, "archives": site(state, player_id)["archives"]},
        source=source,
        controller=player_id,
    ))
    events.extend(check_scp_victory(game, source=source))
    return events


def _declare_site_win(game, player_id: str, reason: str, *, source: Optional[str] = None) -> list[Event]:
    events: list[Event] = []
    for opponent_id, opponent in game.state.players.items():
        if opponent_id != player_id and not opponent.has_lost:
            opponent.has_lost = True
            events.extend(game.emit(Event(
                type=EventType.PLAYER_LOSES,
                payload={"player": opponent_id, "reason": reason, "winner": player_id},
                source=source,
                controller=player_id,
            )))
    return events


def redaction_alt_win_met(card_def, site_values: dict) -> bool:
    """Return whether a redaction mandate meets its printed alternate-win condition."""
    threshold = getattr(card_def, "scp_redaction_win", None)
    archives_required = 3
    secrecy_required = 12
    max_breach = None
    if isinstance(threshold, dict):
        archives_required = int(threshold.get("archives", archives_required) or archives_required)
        secrecy_required = int(threshold.get("secrecy", secrecy_required) or secrecy_required)
        if threshold.get("max_breach") is not None:
            max_breach = int(threshold["max_breach"])

    if site_values.get("archives", 0) < archives_required:
        return False
    if site_values.get("secrecy", 0) < secrecy_required:
        return False
    if max_breach is not None and site_values.get("breach", 0) > max_breach:
        return False
    return True


def check_scp_victory(game, *, source: Optional[str] = None) -> list[Event]:
    events: list[Event] = []
    state = game.state
    for player_id in list(state.players):
        ensure_scp_state(state, player_id)
        s = site(state, player_id)
        if s["archives"] >= ARCHIVES_TO_WIN:
            events.extend(_declare_site_win(game, player_id, "scp_archives_completed", source=source))
            continue
        for mandate_id in list(state.scp_mandates.get(player_id, [])):
            mandate = state.objects.get(mandate_id)
            if not mandate or mandate.state.scp_status != "active" or not mandate.card_def:
                continue
            alt_win = getattr(mandate.card_def, "scp_alt_win", None)
            if alt_win == "redaction" and redaction_alt_win_met(mandate.card_def, s):
                events.extend(_declare_site_win(game, player_id, "total_redaction", source=mandate.id))
            # Thaumiel: 3 contained (was 4) + 0 breach. The contained-zone
            # accumulation is slow enough that 4 almost never lands in 18-turn
            # games; 3 is achievable while still expressing the archetype.
            if alt_win == "thaumiel" and len(state.scp_contained.get(player_id, [])) >= 3 and s["breach"] == 0:
                events.extend(_declare_site_win(game, player_id, "thaumiel_containment", source=mandate.id))
            if alt_win == "veil_lockdown" and s["archives"] >= 3 and s["breach"] == 0:
                events.extend(_declare_site_win(game, player_id, "veil_lockdown", source=mandate.id))
            # Ethics audit: dropped the ethics_debt <= 2 requirement. The ETH
            # archetype's own anomalies seed ethics_debt on reveal, so the
            # old requirement directly fought its win condition. Now just
            # archives + secrecy, matching public_panic's complexity.
            if alt_win == "ethics_audit" and s["archives"] >= 4 and s["secrecy"] >= 8:
                events.extend(_declare_site_win(game, player_id, "ethics_audit", source=mandate.id))
            if alt_win == "public_panic" and s["archives"] >= 4:
                exposed_opponent = any(
                    opponent_id != player_id
                    and not state.players[opponent_id].has_lost
                    and site(state, opponent_id)["secrecy"] <= 6
                    for opponent_id in state.players
                )
                if exposed_opponent:
                    events.extend(_declare_site_win(game, player_id, "public_panic", source=mandate.id))
            # MNR alt-win: forget 3+ opposing anomalies + secrecy >= 10.
            # ``scp_forgotten`` is the MNR-only zone populated by
            # ``forget_anomaly``. Thaumiel branch above counts
            # ``scp_contained`` only, which forget_anomaly explicitly removes
            # from — so a forgotten anomaly never double-counts for both
            # win conditions. (Card-design agents: the threshold is
            # cumulative across BOTH opponents in multiplayer.)
            if alt_win == "memory_hole":
                forgotten_opp = 0
                for opp_id in state.players:
                    if opp_id == player_id:
                        continue
                    forgotten_opp += len(state.scp_forgotten.get(opp_id, []))
                if forgotten_opp >= 3 and s["secrecy"] >= 10:
                    events.extend(_declare_site_win(game, player_id, "memory_hole", source=mandate.id))
    return events


def adjust_site(
    game,
    player_id: str,
    *,
    secrecy: int = 0,
    breach: int = 0,
    archives: int = 0,
    ethics_debt: int = 0,
    clearance: int = 0,
    source: Optional[str] = None,
) -> list[Event]:
    state = game.state
    s = site(state, player_id)
    s["secrecy"] += secrecy
    s["breach"] = max(0, s["breach"] + breach)
    s["ethics_debt"] = max(0, s["ethics_debt"] + ethics_debt)
    s["clearance"] = max(0, s["clearance"] + clearance)
    events: list[Event] = []
    if archives:
        events.extend(gain_archives(game, player_id, archives, source=source))
    events.extend(check_scp_victory(game, source=source))
    events.extend(check_scp_loss(game))
    return events


def force_audit(game, actor_id: str, target_id: str, *, intensity: int = 1, source: Optional[str] = None) -> list[Event]:
    """Cross-site interference: audit a rival Site instead of attacking it."""
    state = game.state
    ensure_scp_state(state, target_id)
    pending = sum(
        1
        for obj in state.objects.values()
        if obj.controller == target_id and obj.zone == ZoneType.BATTLEFIELD and obj.state.scp_status == "pending"
    )
    active_anomalies = len(state.scp_anomalies.get(target_id, []))
    pressure = max(0, intensity + pending + active_anomalies)
    site(state, target_id)["secrecy"] -= pressure
    site(state, actor_id)["ethics_debt"] += max(0, intensity - 1)
    events = game.emit(Event(
        type=EventType.SCP_AUDIT,
        payload={
            "actor": actor_id,
            "target": target_id,
            "intensity": intensity,
            "exposure": pressure,
            "pending": pending,
            "active_anomalies": active_anomalies,
        },
        source=source,
        controller=actor_id,
    ))
    events.extend(check_scp_loss(game))
    return events


def misfile_dossier(game, actor_id: str, target_object_id: str, *, amount: int = 1, source: Optional[str] = None) -> tuple[bool, str, list[Event]]:
    """Cross-site interference: add paperwork to an opponent's pending card."""
    state = game.state
    obj = state.objects.get(target_object_id)
    if not obj:
        return False, "Dossier not found", []
    if obj.controller == actor_id:
        return False, "Cannot misfile your own dossier", []
    if obj.state.scp_status != "pending":
        return False, "Only pending dossiers can be misfiled", []
    obj.state.scp_paperwork += max(1, amount)
    events = game.emit(Event(
        type=EventType.SCP_AUDIT,
        payload={"actor": actor_id, "target": obj.controller, "object_id": obj.id, "paperwork_added": amount},
        source=source,
        controller=actor_id,
    ))
    return True, "Dossier misfiled", events


def spend_ethics(game, player_id: str, amount: int, *, mode: str, source: Optional[str] = None) -> tuple[bool, str, list[Event]]:
    """Use ethics debt as a resource. Powerful, but the loss clock remains."""
    state = game.state
    if mode not in {"erase_breach", "buy_clearance", "bury_exposure"}:
        return False, "Unknown ethics spend mode", []
    s = site(state, player_id)
    if s["ethics_debt"] < amount:
        return False, "Not enough ethics debt", []
    s["ethics_debt"] -= amount
    events = game.emit(Event(
        type=EventType.SCP_ETHICS_SPENT,
        payload={"player": player_id, "amount": amount, "mode": mode},
        source=source,
        controller=player_id,
    ))
    if mode == "erase_breach":
        s["breach"] = max(0, s["breach"] - amount * 2)
    elif mode == "buy_clearance":
        s["clearance"] += amount
    else:
        s["secrecy"] += amount
    events.extend(check_scp_victory(game, source=source))
    events.extend(check_scp_loss(game))
    return True, "Ethics spent", events


def check_scp_loss(game) -> list[Event]:
    events: list[Event] = []
    state = game.state
    for player_id, player in state.players.items():
        ensure_scp_state(state, player_id)
        s = state.scp_sites[player_id]
        if player.has_lost:
            continue
        reason = None
        if s["breach"] >= BREACH_LIMIT:
            reason = "breach"
        elif s["secrecy"] <= 0:
            reason = "veil_exposure"
        elif s["ethics_debt"] >= ETHICS_LIMIT:
            reason = "ethics_collapse"
        if reason:
            player.has_lost = True
            events.extend(game.emit(Event(
                type=EventType.SCP_SITE_LOST,
                payload={"player": player_id, "reason": reason},
                source="SCP_SYSTEM",
                controller=player_id,
            )))
            events.extend(game.emit(Event(
                type=EventType.PLAYER_LOSES,
                payload={"player": player_id, "reason": reason},
                source="SCP_SYSTEM",
                controller=player_id,
            )))
    events.extend(check_scp_victory(game))
    return events


def make_scp_card(
    name: str,
    card_type: CardType,
    *,
    text: str,
    subtypes: set[str] | None = None,
    red_tape: int = 0,
    clearance: int = 0,
    containment: int = 0,
    curiosity: int = 0,
    hazard: int = 0,
    skills: dict[str, int] | None = None,
    bonus: dict[str, int] | None = None,
    contained_bonus: dict[str, int] | None = None,
    aura: dict[str, dict[str, int]] | None = None,
    rarity: str | None = None,
    on_reveal=None,
    on_contain=None,
    on_test=None,
    on_test_fail=None,
    effect=None,
) -> CardDefinition:
    """Factory shared by the SCP card pool.

    Extension attributes (read by engine helpers):
      - ``scp_contained_bonus`` — dict ``{task: int}`` applied while this
        anomaly is contained. See ``_active_bonus``.
      - ``scp_aura`` — dict ``{selector: {task: int}}`` for personnel-side
        lord effects. See ``_staff_total``.
      - ``scp_on_test_fail`` — hook ``(obj, state) -> list[Event]`` invoked
        when a research test against this anomaly fails.
      - ``scp_on_assign`` — hook
        ``(personnel_obj, state, action: str) -> list[Event]`` invoked when
        a personnel is committed to a research/contain/suppress assignment.
        See ``_fire_on_assign``. Events whose ``payload["task_bonus"]`` is
        set contribute to the assignment's total before the success check.
    """
    card = CardDefinition(
        name=name,
        mana_cost=None,
        domain="SCP",
        text=text,
        rarity=rarity,
        characteristics=Characteristics(
            types={card_type},
            subtypes=set(subtypes or set()),
            power=containment if card_type == CardType.SCP_ANOMALY else None,
            toughness=hazard if card_type == CardType.SCP_ANOMALY else None,
        ),
    )
    card.scp_red_tape = red_tape
    card.scp_clearance = clearance
    card.scp_containment = containment
    card.scp_curiosity = curiosity
    card.scp_hazard = hazard
    card.scp_skills = dict(skills or {})
    card.scp_bonus = dict(bonus or {})
    card.scp_contained_bonus = dict(contained_bonus or {})
    card.scp_aura = dict(aura or {})
    card.scp_on_reveal = on_reveal
    card.scp_on_contain = on_contain
    card.scp_on_test = on_test
    card.scp_on_test_fail = on_test_fail
    card.scp_effect = effect
    card.scp_alt_win = None
    return card


# ---------------------------------------------------------------------------
# Reveal / mood / paperwork helpers exposed to card-side mechanic modules.
# ---------------------------------------------------------------------------


def _public_reveal(amount: int):
    """Return an ``on_reveal`` hook that drops the controller's secrecy by ``amount``.

    Mirror of ``_hostile_reveal`` (which bumps breach). Emits an ``SCP_AUDIT``
    event tagged with ``reason="public_reveal"`` so audit consumers can react
    without inventing a new event type.
    """

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        s = site(state, obj.controller)
        s["secrecy"] -= amount
        return [Event(
            type=EventType.SCP_AUDIT,
            payload={
                "actor": obj.id,
                "target": obj.controller,
                "exposure": amount,
                "reason": "public_reveal",
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return reveal


def _seeded_mood(mood: str, *, protocol: Optional[str] = None, briefing: int = 0):
    """Return an ``on_reveal`` hook that seeds mood/protocol/briefing for an anomaly.

    Lifted from the SZB ``_quarantine`` pattern. ``mood`` must appear in
    ``MOOD_MODS`` (caller's responsibility to pick from
    {"docile", "agitated", "cryptic", "cooperative"}). ``protocol``, when set,
    must appear in ``PROTOCOL_MODS`` and is appended to the anomaly's protocol
    list (idempotent). ``briefing`` is added to the controller's site briefing
    pool. Emits ``SCP_MOOD_SHIFT``.
    """
    if mood not in MOOD_MODS:
        raise ValueError(f"_seeded_mood: unknown mood {mood!r}")
    if protocol is not None and protocol not in PROTOCOL_MODS:
        raise ValueError(f"_seeded_mood: unknown protocol {protocol!r}")

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        obj.state.scp_mood = mood
        if protocol and protocol not in obj.state.scp_protocols:
            obj.state.scp_protocols.append(protocol)
        s = site(state, obj.controller)
        s["briefing"] += briefing
        return [Event(
            type=EventType.SCP_MOOD_SHIFT,
            payload={
                "object_id": obj.id,
                "to": mood,
                "protocol": protocol,
                "briefing": s["briefing"],
                "seeded": True,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return hook


# ---------------------------------------------------------------------------
# Mnestic Reset (MNR) verbs: mnestic / antimeme / redact / cog hazard.
#
# Five interlocking verbs that read three card_def attributes
# (``scp_mnestic``, ``scp_antimeme``, ``scp_cog_hazard``), two object-state
# fields (``scp_forget_counters``, ``scp_mnestic_gained``), and a new zone
# (``state.scp_forgotten``). The MNR_ block below is grouped together so it
# can be moved / tested as one feature.
# ---------------------------------------------------------------------------


def has_mnestic(state: GameState, player_id: str) -> bool:
    """Return True if ``player_id`` has an active personnel with Mnestic tag.

    Reads both the printed ``scp_mnestic`` card_def attribute AND the
    per-object ``scp_mnestic_gained`` flag (set by Mnestic Wake), so a
    personnel that became Mnestic mid-game still counts.
    """
    ensure_scp_state(state, player_id)
    for staff_id in list(state.scp_personnel.get(player_id, [])):
        staff = state.objects.get(staff_id)
        if not staff or staff.zone != ZoneType.BATTLEFIELD:
            continue
        if staff.state.scp_status != "active":
            continue
        if bool(getattr(staff.card_def, "scp_mnestic", False)):
            return True
        if bool(getattr(staff.state, "scp_mnestic_gained", False)):
            return True
    return False


def forget_anomaly(game, anomaly_id: str, *, source: Optional[str] = None) -> list[Event]:
    """Move an anomaly into ``state.scp_forgotten`` (removed-from-history).

    This is NOT a destroy: leaves-battlefield triggers do NOT fire, and the
    object is intentionally pulled out of ``scp_anomalies`` / ``scp_contained``
    but not routed through ZONE_CHANGE. The card_def's history is effectively
    unwound. Emits a single ``SCP_FORGET`` event for log / AI consumers.
    """
    state = game.state
    obj = state.objects.get(anomaly_id)
    if obj is None or obj.zone != ZoneType.BATTLEFIELD:
        return []
    controller = obj.controller
    ensure_scp_state(state, controller)
    anomalies = state.scp_anomalies.get(controller, [])
    while obj.id in anomalies:
        anomalies.remove(obj.id)
    contained = state.scp_contained.get(controller, [])
    while obj.id in contained:
        contained.remove(obj.id)
    forgotten = state.scp_forgotten.setdefault(controller, [])
    if obj.id not in forgotten:
        forgotten.append(obj.id)
    obj.state.scp_status = "forgotten"
    return game.emit(Event(
        type=EventType.SCP_FORGET,
        payload={
            "player": controller,
            "object_id": obj.id,
            "forget_counters": int(getattr(obj.state, "scp_forget_counters", 0) or 0),
            "antimeme": int(getattr(obj.card_def, "scp_antimeme", 0) or 0),
        },
        source=source or obj.id,
        controller=controller,
    ))


def tick_antimeme_counters(game, player_id: str) -> list[Event]:
    """End-of-turn hook for ``player_id``. Advance every antimeme anomaly.

    For each anomaly P that ``player_id`` controls (active OR contained):
      - If P.card_def declares ``scp_antimeme = N`` (N>=1)
      - AND ``has_mnestic(state, player_id)`` is False
      - Then P.state.scp_forget_counters += 1
      - If the new counter >= N, call ``forget_anomaly(game, P.id)``.

    Anomalies controlled by a Mnestic-covered Site do NOT accumulate, but
    they also do NOT reset — once a counter is on, the only way to clear
    it is to forget the card (or future bespoke MNR cards). This is by
    design: the antimeme is silently chewing through the dossier even
    when a researcher temporarily remembers it.
    """
    state = game.state
    ensure_scp_state(state, player_id)
    if has_mnestic(state, player_id):
        return []
    events: list[Event] = []
    # Both active and contained anomalies can accumulate. The decay clock
    # represents the anomaly chewing through the paperwork, not its
    # physical containment status.
    anomaly_ids: list[str] = []
    anomaly_ids.extend(list(state.scp_anomalies.get(player_id, [])))
    anomaly_ids.extend(list(state.scp_contained.get(player_id, [])))
    for anomaly_id in anomaly_ids:
        anomaly = state.objects.get(anomaly_id)
        if anomaly is None or anomaly.zone != ZoneType.BATTLEFIELD:
            continue
        threshold = int(getattr(anomaly.card_def, "scp_antimeme", 0) or 0)
        if threshold <= 0:
            continue
        prior = int(getattr(anomaly.state, "scp_forget_counters", 0) or 0)
        anomaly.state.scp_forget_counters = prior + 1
        if anomaly.state.scp_forget_counters >= threshold:
            events.extend(forget_anomaly(game, anomaly.id, source=anomaly.id))
    return events


def _opposing_players(state: GameState, player_id: str) -> list[str]:
    """Return the IDs of every other player that hasn't lost yet."""
    out: list[str] = []
    for pid, player in state.players.items():
        if pid == player_id:
            continue
        if getattr(player, "has_lost", False):
            continue
        out.append(pid)
    return out


def _opponent_anomalies_with_cog_hazard(state: GameState, victim_id: str) -> int:
    """Sum scp_cog_hazard across anomalies whose controller is NOT victim_id.

    Only counts anomalies whose controller's opponent (= victim_id) has NO
    active Mnestic personnel. If victim_id is mnestic-protected, the
    cognitive hazard is suppressed and this returns 0.
    """
    if has_mnestic(state, victim_id):
        return 0
    total = 0
    for controller_id, anomalies in state.scp_anomalies.items():
        if controller_id == victim_id:
            continue
        for anomaly_id in list(anomalies):
            anomaly = state.objects.get(anomaly_id)
            if anomaly is None or anomaly.zone != ZoneType.BATTLEFIELD:
                continue
            total += int(getattr(anomaly.card_def, "scp_cog_hazard", 0) or 0)
    # Contained anomalies also project cog hazard. The flavor: the dossier
    # is still chewing on the witness — sealing it doesn't stop the meme.
    for controller_id, contained in state.scp_contained.items():
        if controller_id == victim_id:
            continue
        for anomaly_id in list(contained):
            anomaly = state.objects.get(anomaly_id)
            if anomaly is None or anomaly.zone != ZoneType.BATTLEFIELD:
                continue
            total += int(getattr(anomaly.card_def, "scp_cog_hazard", 0) or 0)
    return total


def _hand_zone_objects(state: GameState, player_id: str) -> list[GameObject]:
    zone = state.zones.get(f"hand_{player_id}")
    if zone is None:
        return []
    out: list[GameObject] = []
    for oid in list(zone.objects):
        obj = state.objects.get(oid)
        if obj is not None:
            out.append(obj)
    return out


def _discard_pick_score(obj: GameObject) -> tuple[int, str]:
    """Score used to pick the "lowest-impact" hand card to discard.

    Sort key: lowest red_tape first, then alphabetical by card name. The
    intuition: low-red-tape cards are usually cheap utility (procedures,
    bench personnel) — losing them stings less than losing a premium
    high-RT anomaly or mandate.
    """
    red_tape = int(getattr(obj.card_def, "scp_red_tape", 0) or 0) if obj.card_def else 0
    name = (obj.card_def.name if obj.card_def else obj.name) or ""
    return (red_tape, name)


def _discard_hand_cards(
    state: GameState,
    player_id: str,
    object_ids: list[str],
    *,
    source: Optional[str] = None,
    reason: str = "mnr_discard",
) -> list[Event]:
    """Move the named objects from ``player_id``'s hand to their graveyard.

    Helper used by both Redact and Cognitive Hazard resolution. Iterates
    through ``object_ids`` (which is the caller's chosen subset; PendingChoice
    or auto-pick selects them upstream) and emits a DISCARD event per card.
    The actual zone move is performed inline because SCP cards don't go
    through the MTG-style DISCARD pipeline handler.
    """
    events: list[Event] = []
    hand = state.zones.get(f"hand_{player_id}")
    gy = state.zones.get(f"graveyard_{player_id}")
    if hand is None:
        return events
    for oid in object_ids:
        obj = state.objects.get(oid)
        if obj is None or obj.zone != ZoneType.HAND or obj.owner != player_id:
            continue
        if oid in hand.objects:
            hand.objects.remove(oid)
        if gy is not None and oid not in gy.objects:
            gy.objects.append(oid)
        obj.zone = ZoneType.GRAVEYARD
        events.append(Event(
            type=EventType.DISCARD,
            payload={
                "player": player_id,
                "object_id": oid,
                "reason": reason,
            },
            source=source,
            controller=player_id,
        ))
    return events


def _choose_lowest_impact_n(state: GameState, player_id: str, n: int) -> list[str]:
    """Return up to ``n`` object IDs from player_id's hand ordered by impact.

    Used as the auto-pick when PendingChoice isn't wired through the SCP
    frontend. Sorts the hand by ``_discard_pick_score`` and returns the
    head. Callers that want a different selection (human play) should
    route through ``PendingChoice`` before falling back here.
    """
    if n <= 0:
        return []
    hand_objs = _hand_zone_objects(state, player_id)
    hand_objs.sort(key=_discard_pick_score)
    return [obj.id for obj in hand_objs[:n]]


def apply_cognitive_hazard_start(game, player_id: str) -> list[Event]:
    """Start-of-turn hook for ``player_id`` — drain hand cards.

    Total cards drained = sum of ``scp_cog_hazard`` across opposing anomalies,
    provided ``player_id`` has no active Mnestic personnel (Mnestic suppresses
    the entire effect). If the total is 0, no event fires.

    Auto-pick: lowest-impact (red_tape, then alphabetical). When the SCP
    frontend wires PendingChoice for cog hazard, callers should swap in a
    real choice prompt; today we pick deterministically.
    """
    state = game.state
    ensure_scp_state(state, player_id)
    total = _opponent_anomalies_with_cog_hazard(state, player_id)
    if total <= 0:
        return []
    picks = _choose_lowest_impact_n(state, player_id, total)
    if not picks:
        # Hand was empty — emit the marker event with discarded=0 anyway so
        # logs / AI can react. (Mnestic-protected players short-circuit at
        # _opponent_anomalies_with_cog_hazard already.)
        return [Event(
            type=EventType.SCP_COG_HAZARD_TICK,
            payload={"player": player_id, "amount": total, "discarded": 0},
            source="SCP_SYSTEM",
            controller=player_id,
        )]
    events: list[Event] = []
    events.append(Event(
        type=EventType.SCP_COG_HAZARD_TICK,
        payload={"player": player_id, "amount": total, "discarded": len(picks)},
        source="SCP_SYSTEM",
        controller=player_id,
    ))
    events.extend(_discard_hand_cards(
        state, player_id, picks,
        source="SCP_SYSTEM", reason="cognitive_hazard",
    ))
    return events


def redact_opposing(
    game,
    player_id: str,
    amount: int,
    *,
    source: Optional[str] = None,
) -> list[Event]:
    """Redact N: opponent discards ``amount`` cards + the last N matching events
    are tagged ``redacted=True``.

    Currently auto-picks the lowest-impact ``amount`` cards from each
    opponent's hand (matches the docstring contract — "human play would
    route through PendingChoice when SCP frontend supports it"). The
    event-history tag is a marker for AI scoring + flavor; full event
    undo is explicitly out of scope.
    """
    state = game.state
    if amount <= 0:
        return []
    events: list[Event] = []
    for opp_id in _opposing_players(state, player_id):
        picks = _choose_lowest_impact_n(state, opp_id, amount)
        # Tag the last ``amount`` events that affected this opponent's
        # site state. We define "affected" as the controller == opp_id.
        # Iterate event_log in reverse so the most-recent are tagged first.
        tagged = 0
        for past_event in reversed(state.event_log):
            if tagged >= amount:
                break
            if past_event.controller != opp_id:
                continue
            if not isinstance(past_event.payload, dict):
                continue
            past_event.payload["redacted"] = True
            tagged += 1
        events.append(Event(
            type=EventType.SCP_REDACT,
            payload={
                "actor": player_id,
                "target": opp_id,
                "amount": amount,
                "events_tagged": tagged,
                "discarded": len(picks),
            },
            source=source,
            controller=player_id,
        ))
        events.extend(_discard_hand_cards(
            state, opp_id, picks,
            source=source, reason="redact",
        ))
    return events


def gain_mnestic(game, personnel_id: str, *, source: Optional[str] = None) -> list[Event]:
    """Personnel becomes permanently Mnestic.

    Sets ``state.scp_mnestic_gained = True`` on the target object so
    ``has_mnestic`` picks it up. Idempotent: re-calling on an already-Mnestic
    personnel still fires the event (lets cards stack "gain mnestic" hooks
    without bookkeeping).
    """
    state = game.state
    obj = state.objects.get(personnel_id)
    if obj is None or obj.zone != ZoneType.BATTLEFIELD:
        return []
    obj.state.scp_mnestic_gained = True
    return game.emit(Event(
        type=EventType.SCP_MNESTIC_ACTIVE,
        payload={
            "player": obj.controller,
            "object_id": obj.id,
            "already_mnestic": bool(getattr(obj.card_def, "scp_mnestic", False)),
        },
        source=source or obj.id,
        controller=obj.controller,
    ))


# ---------------------------------------------------------------------------
# /MNR
# ---------------------------------------------------------------------------


def tax_own_pending(state: GameState, player_id: str, amount: int, source: Optional[str] = None) -> list[Event]:
    """Add paperwork to ALL of ``player_id``'s pending dossiers.

    Inward-pointing mirror of ``misfile_dossier`` (which targets opposing
    cards). Returns the list of ``SCP_PAPERWORK_TICK`` events emitted (note:
    these are constructed here, not pushed through ``game.emit`` — callers
    that need pipeline emission should iterate the list and re-emit, but the
    common use is a card hook that returns them directly).
    """
    ensure_scp_state(state, player_id)
    events: list[Event] = []
    amount = max(1, int(amount or 0))
    for obj in list(state.objects.values()):
        if obj.controller != player_id:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.state.scp_status != "pending":
            continue
        before = obj.state.scp_paperwork
        obj.state.scp_paperwork = before + amount
        events.append(Event(
            type=EventType.SCP_PAPERWORK_TICK,
            payload={
                "object_id": obj.id,
                "from": before,
                "to": obj.state.scp_paperwork,
                "reason": "tax_own_pending",
            },
            source=source,
            controller=player_id,
        ))
    return events
