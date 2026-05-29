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
        # FBN (Foundations Beyond) site slots. ``archives_list`` is the
        # CardDefinition append-only log used by Dragon Hoard's ``_active_bonus``
        # walk. ``rift_window`` is the Planar Rift exile shelf consumed by
        # ``play_from_rift_window``. The three counters
        # (``compleation_swaps`` / ``phylactery_audits`` / ``wurms_tamed``) feed
        # the matching FBN alt-wins in ``check_scp_victory``.
        "archives_list": [],
        "rift_window": [],
        "compleation_swaps": 0,
        "phylactery_audits": 0,
        "phylactery_audits_this_game": 0,
        "wurms_tamed": 0,
        "spark_drawn_this_turn": False,
        "leyline_saturation_delta": {},
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
    # FBN Cluster 6: Dragon Hoard. Each archived CardDefinition with subtype
    # "Dragon" AND ``scp_dragon_hoard = X`` adds X to the running total, capped
    # at +6 contribution per test (engine guardrail to keep the design ceiling
    # of +4 in line with the +6 sanity cap). The archive walk reads
    # ``state.scp_sites[player_id]["archives_list"]`` — a list of CardDefinition
    # objects appended by ``record_archived_card`` whenever ``gain_archives``
    # fires for an anomaly source.
    archives_list = state.scp_sites[player_id].get("archives_list", []) or []
    dragon_bonus = 0
    for archived in archives_list:
        if archived is None:
            continue
        hoard = int(getattr(archived, "scp_dragon_hoard", 0) or 0)
        if hoard <= 0:
            continue
        characteristics = getattr(archived, "characteristics", None)
        subtypes = set(getattr(characteristics, "subtypes", set()) or set()) if characteristics else set()
        if "Dragon" not in subtypes:
            continue
        dragon_bonus += hoard
    total += min(6, dragon_bonus)
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


def _fire_card_hook(game, obj: GameObject, hook_name: str, state: GameState = None) -> list[Event]:
    """Fire a single ``scp_on_<name>`` hook bound to ``obj.card_def``.

    Centralizes the established pattern: read the callable, accept either
    ``(obj, state)`` or ``(obj, state, game)`` signature, emit produced
    events through ``game.emit``. Returns the emitted events. No-op when
    the hook is missing or not callable.

    Hooks that emit events expected to fire through the pipeline must use
    ``game.emit`` here so interceptors run; hooks that return pre-emitted
    events (carrying ``timestamp`` or already in ``state.event_log``) are
    passed through unchanged.
    """
    if obj is None or obj.card_def is None:
        return []
    hook = getattr(obj.card_def, hook_name, None)
    if not callable(hook):
        return []
    if state is None:
        state = game.state
    try:
        produced = hook(obj, state, game)
    except TypeError:
        produced = hook(obj, state)
    out: list[Event] = []
    for event in produced or []:
        if getattr(event, "timestamp", 0) or event in state.event_log:
            out.append(event)
        else:
            out.extend(game.emit(event))
    return out


def _fire_static_trigger(
    game,
    hook_name: str,
    player_id: str,
    *,
    state: GameState = None,
    excluded_object_id: Optional[str] = None,
) -> list[Event]:
    """Fire ``hook_name`` on every battlefield card ``player_id`` controls.

    Use for cross-card static triggers ("when ANY anomaly enters, do X"
    on cards that watch that event). ``excluded_object_id`` skips the
    triggering card itself when a static trigger shouldn't self-fire.

    Walks every zone the SCP engine tracks: scp_anomalies, scp_personnel,
    scp_facilities, scp_contained, scp_mandates. Cards that don't carry
    the hook are silently skipped.
    """
    if state is None:
        state = game.state
    events: list[Event] = []
    for bucket in (
        state.scp_anomalies, state.scp_personnel, state.scp_facilities,
        state.scp_contained, state.scp_mandates,
    ):
        for oid in list(bucket.get(player_id, [])):
            if excluded_object_id is not None and oid == excluded_object_id:
                continue
            other = state.objects.get(oid)
            if other is None or other.zone != ZoneType.BATTLEFIELD:
                continue
            events.extend(_fire_card_hook(game, other, hook_name, state))
    return events


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
        # scp_on_play fires *before* the procedure moves to the graveyard
        # so the hook still sees the card on battlefield. For Procedures,
        # scp_on_play is often used in place of scp_effect (the eldrazi_apex
        # and phyrexian_strain Procedures attach scp_on_play directly).
        events.extend(_fire_card_hook(game, obj, "scp_on_play", state))
        _deindex_card(state, obj)
        _move(game, obj, ZoneType.GRAVEYARD, source=obj.id)
    else:
        # Non-anomaly, non-procedure card types still fire scp_on_play as a
        # generic post-activation trigger when set.
        events.extend(_fire_card_hook(game, obj, "scp_on_play", state))

    # scp_on_play for Anomalies fires AFTER scp_on_reveal so on-reveal logic
    # (mood / status changes) has already settled.
    if CardType.SCP_ANOMALY in types:
        events.extend(_fire_card_hook(game, obj, "scp_on_play", state))
        # Cross-card static trigger: when an Anomaly enters play, every
        # other card the controller owns whose scp_on_anomaly_enter hook is
        # set fires. Skip the triggering card itself.
        events.extend(_fire_static_trigger(
            game, "scp_on_anomaly_enter", obj.controller,
            state=state, excluded_object_id=obj.id,
        ))

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
    # scp_on_open_dossier fires after the dossier transitions to battlefield,
    # whether it lands sealed / pending / active. Sealed dossiers have skipped
    # the reveal path, so this is the only hook they fire.
    events.extend(_fire_card_hook(game, obj, "scp_on_open_dossier", state))
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
        # scp_on_dragon_contain is a Dragon-archetype subtype-filtered
        # variant — fires only when a Dragon-subtype anomaly is contained.
        # The Dragon Conclave archetype attaches it on Containment Hangar
        # facilities that pay off when dragons specifically get contained.
        subtypes = getattr(anomaly.card_def, "subtypes", set()) or set()
        if "Dragon" in subtypes:
            events.extend(_fire_static_trigger(
                game, "scp_on_dragon_contain", player_id, state=state,
            ))
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
    breaching_anomalies: list[GameObject] = []
    for anomaly_id in list(state.scp_anomalies.get(player_id, [])):
        anomaly = state.objects.get(anomaly_id)
        if not anomaly or anomaly.zone != ZoneType.BATTLEFIELD or anomaly.state.scp_status != "active":
            continue
        total += _effective_hazard(anomaly)
        anomaly.state.scp_suppressed = 0
        breaching_anomalies.append(anomaly)
    if site(state, player_id)["ethics_debt"] >= 5:
        total += 1
    site(state, player_id)["breach"] += total
    events = game.emit(Event(
        type=EventType.SCP_BREACH_TICK,
        payload={"player": player_id, "amount": total, "breach": site(state, player_id)["breach"]},
        source="SCP_SYSTEM",
        controller=player_id,
    ))
    # scp_on_breach fires per-anomaly that contributed hazard to this tick.
    # The hook sees the anomaly object plus state, and is the natural fire
    # point for "when this anomaly breaches, do X" effects (boltgun-style
    # passive damage, secondary-effect breach payoffs, …).
    for anomaly in breaching_anomalies:
        events.extend(_fire_card_hook(game, anomaly, "scp_on_breach", state))
    if total > 0:
        events.extend(incident_tick(game, player_id))
    # apply_annihilation_wave is gated on SCP_BREACH_TICK per its docstring;
    # call it here so Cluster 7 / Eldrazi Apex anomalies actually fire. Was
    # an engine gap separate from the trigger orphans.
    events.extend(apply_annihilation_wave(game, player_id, breach_amount=total))
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
    events = _activate_dossier(game, obj, auto_seal_default=seal_default)
    # scp_on_activate is the explicit-activation hook: cards that want a
    # different trigger semantics than the implicit "on play" / "on reveal"
    # paths use this for ability-activation effects.
    events.extend(_fire_card_hook(game, obj, "scp_on_activate", game.state))
    return events


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
    # scp_on_memory_hole fires on the card being memory-holed, before the
    # phylactery audit decides whether to pull it back to hand. This lets
    # antimeme / cognitive-rewrite cards react to their own redaction.
    events.extend(_fire_card_hook(game, obj, "scp_on_memory_hole", state))
    # FBN Cluster 2: Phylactery Audit. If the card carries
    # ``scp_phylactery_audit = X``, the audit fires now — on accept the card
    # is yanked back to hand (reversing the exile) and the audit counter
    # bumps; on reject the card is appended to ``scp_forgotten`` and stays
    # in EXILE. Both branches emit ``SCP_PHYLACTERY_AUDIT_OFFER``.
    events.extend(apply_phylactery_audit(state, game, obj))
    events.extend(check_scp_victory(game, source=source))
    return True, "Memory-holed", events


def sacrifice_dossier(game, player_id: str, object_id: str, *, source: Optional[str] = None) -> tuple[bool, str, list[Event]]:
    """Sacrifice a dossier ``player_id`` controls, firing ``scp_on_sacrifice``.

    Distinct from ``memory_hole`` (which is a *voluntary* redaction for a
    secrecy gain at archive cost) and from procedure resolution (which
    auto-moves the procedure to graveyard). Sacrifice is the explicit
    "this card pays itself as a cost" path that Procedure effects can call
    against their own pending/active anomalies (Eldrazi Apex "sacrifice N
    Anomalies for briefing" pattern).

    The card's ``scp_on_sacrifice`` hook fires *before* the move to
    graveyard so the hook still sees the card on battlefield. After the
    hook, ``_move`` puts the card in GRAVEYARD and ``_deindex_card``
    updates the SCP zone indices.
    """
    state = game.state
    obj = state.objects.get(object_id)
    if obj is None or obj.controller != player_id:
        return False, "Object not found", []
    if obj.zone != ZoneType.BATTLEFIELD:
        return False, "Only on-battlefield cards can be sacrificed", []
    events = game.emit(Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": player_id,
            "reason": "sacrifice",
            "object_id": obj.id,
        },
        source=source,
        controller=player_id,
    ))
    events.extend(_fire_card_hook(game, obj, "scp_on_sacrifice", state))
    _deindex_card(state, obj)
    events.extend(_move(game, obj, ZoneType.GRAVEYARD, source=source))
    return True, "Sacrificed", events


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
    # FBN Cluster 6 wiring: if the ``source`` resolves to an anomaly GameObject
    # whose card_def is a Dragon Hoard tag, append its CardDefinition to the
    # site's ``archives_list`` so ``_active_bonus`` can read it. Non-anomaly
    # sources are skipped — Dragon Hoard is by definition an anomaly mechanic.
    if source:
        source_obj = state.objects.get(source)
        if source_obj and source_obj.card_def is not None:
            record_archived_card(state, player_id, source_obj.card_def)
    events = game.emit(Event(
        type=EventType.SCP_ARCHIVE_GAINED,
        payload={"player": player_id, "amount": amount, "archives": site(state, player_id)["archives"]},
        source=source,
        controller=player_id,
    ))
    # scp_on_archive fires on the source card whose containment / activation
    # produced the archive gain. scp_on_archive_stub is a variant the Spirit
    # Archive archetype uses on stub-bearing cards (per-card flavor; same
    # semantic fire point).
    if source:
        source_obj = state.objects.get(source)
        if source_obj is not None:
            events.extend(_fire_card_hook(game, source_obj, "scp_on_archive", state))
            events.extend(_fire_card_hook(game, source_obj, "scp_on_archive_stub", state))
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
            # Secrecy 8 -> 7: archetype-trace audit (May 2026) found ETH's
            # secrecy ceiling is median 6-7 across vs SCR and vs ACW; the 8
            # threshold meant ethics_audit alt-win never fired in 10 games.
            # Dropping to 7 puts the win condition in reach of the deck's
            # actual secrecy generation while keeping it above the loss
            # threshold (secrecy <= 0).
            if alt_win == "ethics_audit" and s["archives"] >= 4 and s["secrecy"] >= 7:
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
            # MNR alt-win: 3+ forgotten anomalies (across ALL players) +
            # secrecy >= 8. ``scp_forgotten`` is the MNR-only zone populated
            # by ``forget_anomaly``. Originally counted opposing-only forgets,
            # but only MNR runs Antimeme anomalies, so the opposing-only
            # variant was effectively mirror-match-only. The new formula
            # sums across every player's scp_forgotten zone — thematically
            # MNR is the "memory is collective loss" archetype, and the
            # deck's own Antimeme decays now feed its win con. Thaumiel
            # branch above counts ``scp_contained`` only, which
            # ``forget_anomaly`` explicitly removes from — so a forgotten
            # anomaly never double-counts for both win conditions.
            # Secrecy 10 -> 8: archetype-trace audit (May 2026) reported
            # MNR's secrecy ceiling is median 7 across 40 games. At 10
            # the win was mechanically unreachable. At 8, the deck's two
            # explicit secrecy-pumps (Class-A Amnestic Broadcast +3,
            # Witness Relocation +2) plus normal +1s push through.
            if alt_win == "memory_hole":
                total_forgotten = sum(
                    len(state.scp_forgotten.get(pid, [])) for pid in state.players
                )
                if total_forgotten >= 3 and s["secrecy"] >= 8:
                    events.extend(_declare_site_win(game, player_id, "memory_hole", source=mandate.id))
            # MNR alt-win: 4 active Mnestic personnel (printed mnestic OR
            # Wake-gained) and 4+ archives. Active-only excludes
            # contained/forgotten personnel. The original rider also
            # demanded "unexhausted", but Mnestic personnel get exhausted
            # in tests/contain/suppress — the engine's core action loop
            # — so maintaining 5 unexhausted Mnestic simultaneously
            # fought against actually playing the game. Threshold lowered
            # from 5 -> 4 to fit the deck's 6-8 Mnestic personnel after
            # a few attritioned out across a 16-turn game.
            if alt_win == "mnestic_saturation":
                mnestic_count = 0
                for pid in state.scp_personnel.get(player_id, []):
                    person = state.objects.get(pid)
                    if not person or person.state.scp_status != "active":
                        continue
                    if (getattr(person.card_def, "scp_mnestic", False)
                            or person.state.scp_mnestic_gained):
                        mnestic_count += 1
                if mnestic_count >= 4 and s["archives"] >= 4:
                    events.extend(_declare_site_win(game, player_id, "mnestic_saturation", source=mandate.id))
            # FBN Cluster 1: Phyrexian Strain compleation overrun. Three
            # successful Compleation Vector control-flips while a Phyrexian
            # Strain mandate is active locks the win.
            if alt_win == "compleation_overrun" and int(s.get("compleation_swaps", 0) or 0) >= 3:
                events.extend(_declare_site_win(game, player_id, "compleation_overrun", source=mandate.id))
            # FBN Cluster 2: Lich Phylactery chain. Four Phylactery Audit
            # returns-from-forgotten over the course of the game with an
            # active Lich Phylactery mandate wins.
            if alt_win == "phylactery_chain" and int(s.get("phylactery_audits", 0) or 0) >= 4:
                events.extend(_declare_site_win(game, player_id, "phylactery_chain", source=mandate.id))
            # FBN Cluster 7: Wurm Apex tamed. Three successful Wurm Devourer
            # taming events with an active Wurm Apex mandate wins.
            if alt_win == "wurm_apex_tamed" and int(s.get("wurms_tamed", 0) or 0) >= 3:
                events.extend(_declare_site_win(game, player_id, "wurm_apex_tamed", source=mandate.id))
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


def activate_ability(
    game,
    player_id: str,
    object_id: Optional[str],
    ability_index: int,
    *,
    mode: Optional[int] = None,
) -> tuple[bool, str, list[Event]]:
    """Activate an SCP-native activated / modal ability registered on an object.

    Synchronous: the cost is validated + paid here and the effect resolves
    immediately, so both the human action loop and the AI's direct-call path
    use the same code. Modal abilities require a valid ``mode`` index (the
    legal-action surface enumerates one action per mode, so the caller — human
    or AI — has already chosen). We deliberately do NOT wrap ``effect_fn`` in a
    blanket ``except`` so card-side bugs surface under ``HYPERDRAFT_STRICT=1``.
    """
    from src.engine.scp_abilities import is_scp_ability
    from src.engine.scp_costs import can_pay_scp_cost, pay_scp_cost

    state = game.state
    obj = state.objects.get(object_id) if object_id else None
    if obj is None:
        return False, "Object not found", []
    if obj.controller != player_id:
        return False, "Not your object", []
    abilities = getattr(obj.state, "activated_abilities", None) or []
    if ability_index < 0 or ability_index >= len(abilities):
        return False, "No such ability", []
    ability = abilities[ability_index]
    if not is_scp_ability(ability):
        return False, "Not an SCP ability", []

    if ability.once_per_game and ability.used_this_game:
        return False, "Ability already used this game", []
    if ability.once_per_turn and ability.activations_this_turn > 0:
        return False, "Ability already used this turn", []
    if ability.precondition_fn and not ability.precondition_fn(obj, state):
        return False, "Ability precondition not met", []

    if ability.is_modal:
        if mode is None or not (0 <= int(mode) < len(ability.modes)):
            return False, "Modal ability requires a valid mode", []
        effect_fn = ability.modes[int(mode)].effect_fn
    else:
        effect_fn = ability.effect_fn

    ok, why = can_pay_scp_cost(obj, state, ability.cost)
    if not ok:
        return False, why, []

    events = pay_scp_cost(game, obj, ability.cost)
    events.extend(game.emit(Event(
        type=EventType.SCP_ABILITY_ACTIVATED,
        payload={
            "player": player_id,
            "object_id": obj.id,
            "ability_index": ability_index,
            "mode": int(mode) if ability.is_modal else None,
            "description": ability.description,
        },
        source=obj.id,
        controller=player_id,
    )))

    # Resolve the effect, emitting its events through the pipeline (mirrors
    # _fire_card_hook so interceptors / reactions run; pre-emitted events pass
    # through unchanged).
    for event in (effect_fn(obj, state) or []):
        if getattr(event, "timestamp", 0) or event in state.event_log:
            events.append(event)
        else:
            events.extend(game.emit(event))

    ability.activations_this_turn += 1
    ability.used_this_game = True

    events.extend(check_scp_victory(game, source=obj.id))
    events.extend(check_scp_loss(game))
    return True, f"Activated: {ability.description}", events


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


def _iter_active_personnel(state: GameState, player_id: str):
    """Yield active battlefield personnel objects for ``player_id`` with card_def set."""
    for staff_id in list(state.scp_personnel.get(player_id, [])):
        staff = state.objects.get(staff_id)
        if not staff or staff.zone != ZoneType.BATTLEFIELD:
            continue
        if staff.state.scp_status != "active":
            continue
        if not staff.card_def:
            continue
        yield staff


def has_active_subtype(state: GameState, player_id: str, subtype: str) -> bool:
    """True if ``player_id`` has at least one active personnel with ``subtype``.

    Reads ``card_def.characteristics.subtypes`` — set when the card was
    minted. Compare with ``has_mnestic`` (which is a printed attribute on
    the card_def itself, not a subtype string).
    """
    for staff in _iter_active_personnel(state, player_id):
        subtypes = getattr(staff.card_def.characteristics, "subtypes", set()) or set()
        if subtype in subtypes:
            return True
    return False


def count_active_subtype(state: GameState, player_id: str, subtype: str) -> int:
    """Count active personnel with ``subtype``."""
    total = 0
    for staff in _iter_active_personnel(state, player_id):
        subtypes = getattr(staff.card_def.characteristics, "subtypes", set()) or set()
        if subtype in subtypes:
            total += 1
    return total


def first_active_subtype(state: GameState, player_id: str, subtype: str) -> Optional[GameObject]:
    """Return the first active personnel with ``subtype``, or None."""
    for staff in _iter_active_personnel(state, player_id):
        subtypes = getattr(staff.card_def.characteristics, "subtypes", set()) or set()
        if subtype in subtypes:
            return staff
    return None


def _first_opposing_player(state: GameState, player_id: str) -> Optional[str]:
    """Return the first non-eliminated opponent of ``player_id``, or None.

    Public-facing thin wrapper used by reset/bump/recover helpers. Distinct
    from ``_opposing_players`` (which returns the full list).
    """
    for pid, player in state.players.items():
        if pid == player_id:
            continue
        if getattr(player, "has_lost", False):
            continue
        return pid
    return None


def reset_forget_counters(
    state: GameState,
    player_id: str,
    limit: Optional[int] = None,
) -> int:
    """Zero out ``scp_forget_counters`` on (at most ``limit``) anomalies.

    Acts on both active and contained anomalies. Returns the count reset.
    If ``limit`` is None, resets all. Picks the highest counter first
    (most-decayed anomaly is the most valuable to refresh).

    Honors the ``mnr_no_reset_this_turn`` site flag: if set on the
    player's own site, the reset short-circuits to 0 (the flag is cleared
    by the SCP turn manager at end-of-turn).
    """
    ensure_scp_state(state, player_id)
    if site(state, player_id).get("mnr_no_reset_this_turn"):
        return 0
    candidates: list[tuple[int, GameObject]] = []
    pool: list[str] = []
    pool.extend(list(state.scp_anomalies.get(player_id, [])))
    pool.extend(list(state.scp_contained.get(player_id, [])))
    for aid in pool:
        an = state.objects.get(aid)
        if not an or an.zone != ZoneType.BATTLEFIELD:
            continue
        counter = int(getattr(an.state, "scp_forget_counters", 0) or 0)
        if counter > 0:
            candidates.append((counter, an))
    # Highest counters first (most urgent to reset).
    candidates.sort(key=lambda c: -c[0])
    if limit is not None:
        candidates = candidates[:limit]
    for _, an in candidates:
        an.state.scp_forget_counters = 0
    return len(candidates)


def bump_opposing_antimeme_counters(
    state: GameState,
    player_id: str,
    amount: int = 1,
    limit: Optional[int] = None,
) -> list[GameObject]:
    """Add ``amount`` to ``scp_forget_counters`` on opposing antimeme anomalies.

    Picks the LOWEST current counter first (so the bump is most likely to
    advance multiple anomalies toward their forget threshold). If ``limit``
    is None, hits all qualifying anomalies. Returns the bumped objects.
    """
    opp_id = _first_opposing_player(state, player_id)
    if opp_id is None:
        return []
    bumped: list[GameObject] = []
    pool: list[str] = []
    pool.extend(list(state.scp_anomalies.get(opp_id, [])))
    pool.extend(list(state.scp_contained.get(opp_id, [])))
    candidates: list[GameObject] = []
    for aid in pool:
        an = state.objects.get(aid)
        if not an or an.zone != ZoneType.BATTLEFIELD:
            continue
        threshold = int(getattr(an.card_def, "scp_antimeme", 0) or 0)
        if threshold <= 0:
            continue
        candidates.append(an)
    # Lowest current counter first.
    candidates.sort(key=lambda a: int(getattr(a.state, "scp_forget_counters", 0) or 0))
    if limit is not None:
        candidates = candidates[:limit]
    for an in candidates:
        prior = int(getattr(an.state, "scp_forget_counters", 0) or 0)
        an.state.scp_forget_counters = prior + amount
        bumped.append(an)
    return bumped


def recover_forgotten(
    state: GameState,
    player_id: str,
    limit: int = 1,
) -> list[GameObject]:
    """Move up to ``limit`` anomalies from ``scp_forgotten`` back to ``scp_anomalies``.

    Requires a Mnestic personnel on board (the case files only resurface
    when somebody can remember). Returns the recovered anomaly objects.
    Sets ``scp_status = "active"`` and resets forget counters to 0.
    """
    if limit <= 0:
        return []
    if not has_mnestic(state, player_id):
        return []
    forgotten = state.scp_forgotten.get(player_id, [])
    if not forgotten:
        return []
    recovered: list[GameObject] = []
    # Take from the tail (most-recently forgotten first — feels right
    # narratively, and matches list.pop() semantics).
    while forgotten and len(recovered) < limit:
        aid = forgotten.pop()
        an = state.objects.get(aid)
        if an is None:
            continue
        an.state.scp_status = "active"
        an.state.scp_forget_counters = 0
        active = state.scp_anomalies.setdefault(player_id, [])
        if an.id not in active:
            active.append(an.id)
        recovered.append(an)
    return recovered


def clear_mnr_no_reset_flag(state: GameState, player_id: str) -> bool:
    """Clear the ``mnr_no_reset_this_turn`` site flag for ``player_id``.

    Returns True if the flag was set (and is now cleared), False otherwise.
    Called by the SCP turn manager at end-of-turn so the marker only
    persists for the duration of the active player's turn.
    """
    s = site(state, player_id)
    if s.get("mnr_no_reset_this_turn"):
        s["mnr_no_reset_this_turn"] = False
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


def has_unexhausted_mnestic(state: GameState, player_id: str) -> bool:
    """Variant of ``has_mnestic`` that requires the Mnestic personnel to be
    unexhausted. Used by ``tick_antimeme_counters`` (May 2026 audit fix) so the
    decay clock advances on turns where every Mnestic personnel has been
    tapped out by assignments. Distinct from ``has_mnestic`` so the
    ``mnestic_saturation`` alt-win still counts active-but-exhausted personnel
    (designers explicitly rejected the unexhausted rider for that count).
    """
    ensure_scp_state(state, player_id)
    for staff_id in list(state.scp_personnel.get(player_id, [])):
        staff = state.objects.get(staff_id)
        if not staff or staff.zone != ZoneType.BATTLEFIELD:
            continue
        if staff.state.scp_status != "active":
            continue
        if getattr(staff.state, "scp_exhausted", False):
            continue
        if bool(getattr(staff.card_def, "scp_mnestic", False)):
            return True
        if bool(getattr(staff.state, "scp_mnestic_gained", False)):
            return True
    return False


def tick_antimeme_counters(game, player_id: str) -> list[Event]:
    """End-of-turn hook for ``player_id``. Advance every antimeme anomaly.

    For each anomaly P that ``player_id`` controls (active OR contained):
      - If P.card_def declares ``scp_antimeme = N`` (N>=1)
      - AND no UNEXHAUSTED Mnestic personnel is active for ``player_id``
      - Then P.state.scp_forget_counters += 1
      - If the new counter >= N, call ``forget_anomaly(game, P.id)``.

    Mnestic blocks decay only when the personnel are actually paying
    attention — exhausted-from-action Mnestic personnel let the antimeme
    slip through. This is by design (May 2026 audit): with the previous
    "any active Mnestic" gate, MNR decks that committed to keeping Mnestic
    on board could never produce ``scp_forgotten`` cards, blocking the
    memory_hole alt-win. The exhaust gate honors the design rationale
    ("the antimeme is silently chewing through the dossier even when a
    researcher temporarily remembers it") — researchers who just spent
    the turn doing something else aren't remembering anything.

    Anomalies covered by an unexhausted Mnestic personnel do NOT
    accumulate, but they also do NOT reset — once a counter is on, the
    only way to clear it is to forget the card (or future bespoke MNR
    cards).
    """
    state = game.state
    ensure_scp_state(state, player_id)
    if has_unexhausted_mnestic(state, player_id):
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


# ---------------------------------------------------------------------------
# FBN (Foundations Beyond) engine extensions
#
# Seven mechanic clusters layered atop the SCP core. Each cluster is read off a
# card-def attribute stamped by ``src/cards/scp/foundations_beyond/helpers.py``
# (``scp_compleation_vector``, ``scp_phylactery_audit``, ``scp_spark_containment``,
# ``scp_leyline_saturation``, ``scp_planar_rift``, ``scp_dragon_hoard``,
# ``scp_annihilation_wave``, ``scp_wurm_devourer``). The Dragon Hoard cluster
# is implemented inline in ``_active_bonus`` above; the rest are public
# functions invoked from card hooks, the turn manager, and the FBN-aware
# memory_hole / gain_archives integrations.
# ---------------------------------------------------------------------------


def record_archived_card(state: GameState, player_id: str, card_def) -> None:
    """Append ``card_def`` to ``state.scp_sites[player_id]["archives_list"]``.

    Called from ``gain_archives`` whenever a player gains archives from a card
    source. Dragon Hoard's ``_active_bonus`` walk reads this list to sum +X
    per archived Dragon. Non-Dragon entries are no-ops at read time so this
    helper is safe to call for every archive event.
    """
    if card_def is None:
        return
    ensure_scp_state(state, player_id)
    archives_list = state.scp_sites[player_id].setdefault("archives_list", [])
    archives_list.append(card_def)


# ---------------------------------------------------------------------------
# Cluster 1: Compleation Vector
# ---------------------------------------------------------------------------


def _compleation_swap(state: GameState, personnel_obj: GameObject) -> Optional[str]:
    """Flip ``personnel_obj``'s controller to the first opposing player.

    Returns the new controller ID on a successful swap, ``None`` if no
    opposing player is available (e.g. all opponents eliminated). The
    personnel is removed from the previous controller's ``scp_personnel``
    registry and appended to the new controller's. The swap counter on the
    new controller's site bumps by 1.
    """
    old_controller = personnel_obj.controller
    new_controller = _first_opposing_player(state, old_controller)
    if new_controller is None:
        return None
    ensure_scp_state(state, old_controller)
    ensure_scp_state(state, new_controller)
    old_list = state.scp_personnel.get(old_controller, [])
    while personnel_obj.id in old_list:
        old_list.remove(personnel_obj.id)
    new_list = state.scp_personnel.setdefault(new_controller, [])
    if personnel_obj.id not in new_list:
        new_list.append(personnel_obj.id)
    personnel_obj.controller = new_controller
    site(state, new_controller)["compleation_swaps"] = int(
        site(state, new_controller).get("compleation_swaps", 0) or 0,
    ) + 1
    return new_controller


def apply_compleation_vector(game, player_id: str) -> list[Event]:
    """End-of-turn hook for ``player_id``. Opposing Compleation Vector
    anomalies place counters on ``player_id``'s strongest non-Mnestic
    personnel.

    For each opposing player O, each active anomaly O controls with
    ``scp_compleation_vector = N`` picks the highest-skill non-Mnestic
    personnel under ``player_id``'s control and places N ``scp_compleation``
    counters on them. When a personnel's counter reaches >=3 the personnel's
    controller flips via ``_compleation_swap`` and ``SCP_CONTROL_SWAP`` fires.

    Mnestic personnel (printed or Mnestic-Wake-gained) are skipped — Mnestic
    suppresses the cognitive rewrite half of Compleation Vector.
    """
    state = game.state
    ensure_scp_state(state, player_id)
    events: list[Event] = []
    for opp_id in _opposing_players(state, player_id):
        for anomaly_id in list(state.scp_anomalies.get(opp_id, [])):
            anomaly = state.objects.get(anomaly_id)
            if not anomaly or anomaly.zone != ZoneType.BATTLEFIELD:
                continue
            if anomaly.state.scp_status != "active":
                continue
            n = int(getattr(anomaly.card_def, "scp_compleation_vector", 0) or 0)
            if n <= 0:
                continue
            candidates: list[tuple[int, GameObject]] = []
            for staff_id in list(state.scp_personnel.get(player_id, [])):
                staff = state.objects.get(staff_id)
                if not staff or staff.zone != ZoneType.BATTLEFIELD:
                    continue
                if staff.state.scp_status != "active":
                    continue
                if bool(getattr(staff.card_def, "scp_mnestic", False)):
                    continue
                if bool(getattr(staff.state, "scp_mnestic_gained", False)):
                    continue
                skills = getattr(staff.card_def, "scp_skills", {}) if staff.card_def else {}
                total_skill = sum(int(v or 0) for v in (skills or {}).values())
                candidates.append((total_skill, staff))
            if not candidates:
                continue
            candidates.sort(
                key=lambda c: (-c[0], c[1].card_def.name if c[1].card_def else c[1].name),
            )
            target = candidates[0][1]
            target.state.scp_compleation = int(
                getattr(target.state, "scp_compleation", 0) or 0,
            ) + n
            if target.state.scp_compleation >= 3:
                old_controller = target.controller
                new_controller = _compleation_swap(state, target)
                if new_controller is not None:
                    events.extend(game.emit(Event(
                        type=EventType.SCP_CONTROL_SWAP,
                        payload={
                            "object_id": target.id,
                            "from_controller": old_controller,
                            "to_controller": new_controller,
                            "reason": "compleation_vector",
                            "source_anomaly": anomaly.id,
                        },
                        source=anomaly.id,
                        controller=new_controller,
                    )))
                    # Compleation triggers fan out as static triggers on
                    # both sides of the swap. scp_on_any_compleated fires on
                    # cards owned by either player (universal observer);
                    # scp_on_opponent_compleated fires on cards owned by the
                    # player who *lost* the personnel (their opponent just
                    # compleated one of theirs); scp_on_you_compleated fires
                    # on cards owned by the player whose personnel switched.
                    for observer in (old_controller, new_controller):
                        events.extend(_fire_static_trigger(
                            game, "scp_on_any_compleated", observer, state=state,
                        ))
                    events.extend(_fire_static_trigger(
                        game, "scp_on_opponent_compleated", old_controller,
                        state=state,
                    ))
                    events.extend(_fire_static_trigger(
                        game, "scp_on_you_compleated", new_controller,
                        state=state,
                    ))
    events.extend(check_scp_victory(game))
    return events


# ---------------------------------------------------------------------------
# Cluster 2: Phylactery Audit
# ---------------------------------------------------------------------------


def apply_phylactery_audit(state: GameState, game, card_obj: GameObject) -> list[Event]:
    """Audit hook fired during ``memory_hole`` when ``card_obj`` carries
    ``scp_phylactery_audit = X``.

    Auto-accept when ``ethics_debt + X <= 8``: the card is yanked from EXILE
    back to HAND, ``ethics_debt += X``, and ``phylactery_audits`` bumps by 1.
    Otherwise the card is appended to ``state.scp_forgotten`` and stays in
    EXILE. Both branches emit ``SCP_PHYLACTERY_AUDIT_OFFER`` so analytics /
    frontend hooks can observe the decision.
    """
    if card_obj is None or card_obj.card_def is None:
        return []
    x = int(getattr(card_obj.card_def, "scp_phylactery_audit", 0) or 0)
    if x <= 0:
        return []
    controller = card_obj.controller
    ensure_scp_state(state, controller)
    s = site(state, controller)
    current_debt = int(s.get("ethics_debt", 0) or 0)
    accepted = (current_debt + x) <= 8
    if accepted:
        exile = state.zones.get("exile")
        hand = state.zones.get(f"hand_{controller}")
        if exile is not None and card_obj.id in exile.objects:
            exile.objects.remove(card_obj.id)
        if hand is not None and card_obj.id not in hand.objects:
            hand.objects.append(card_obj.id)
        card_obj.zone = ZoneType.HAND
        card_obj.state.scp_status = None
        card_obj.state.scp_paperwork = 0
        s["ethics_debt"] = current_debt + x
        s["phylactery_audits"] = int(s.get("phylactery_audits", 0) or 0) + 1
        s["phylactery_audits_this_game"] = int(
            s.get("phylactery_audits_this_game", 0) or 0,
        ) + 1
    else:
        if not hasattr(state, "scp_forgotten"):
            state.scp_forgotten = {}
        forgotten = state.scp_forgotten.setdefault(controller, [])
        if card_obj.id not in forgotten:
            forgotten.append(card_obj.id)
    events = game.emit(Event(
        type=EventType.SCP_PHYLACTERY_AUDIT_OFFER,
        payload={
            "player": controller,
            "object_id": card_obj.id,
            "audit": x,
            "ethics_debt_before": current_debt,
            "accepted": accepted,
        },
        source=card_obj.id,
        controller=controller,
    ))
    # scp_on_audit_return fires only on the accept branch — the card has
    # actually returned to hand. On reject the card stays in EXILE / is
    # appended to scp_forgotten and no return happens.
    if accepted:
        events.extend(_fire_card_hook(game, card_obj, "scp_on_audit_return", state))
    return events


# ---------------------------------------------------------------------------
# Cluster 3: Spark Containment
# ---------------------------------------------------------------------------


def apply_spark_containment(game, player_id: str, contained_event: Optional[Event] = None) -> list[Event]:
    """Spark Containment hook. Sums each active Spark personnel's N into
    clearance; the first crossing of clearance >= 6 each turn fires one extra
    paperwork tick on a pending dossier the controller owns.

    ``contained_event`` is accepted (and ignored) for callers wiring this
    behind an ``SCP_CONTAINED`` event filter — the actual computation is a
    flat sum, not per-event.
    """
    state = game.state
    ensure_scp_state(state, player_id)
    s = site(state, player_id)
    total_bump = 0
    for staff_id in list(state.scp_personnel.get(player_id, [])):
        staff = state.objects.get(staff_id)
        if not staff or staff.zone != ZoneType.BATTLEFIELD:
            continue
        if staff.state.scp_status != "active":
            continue
        n = int(getattr(staff.card_def, "scp_spark_containment", 0) or 0)
        if n <= 0:
            continue
        total_bump += n
    if total_bump <= 0:
        return []
    before = int(s.get("clearance", 0) or 0)
    after = before + total_bump
    s["clearance"] = after
    events: list[Event] = []
    if after >= 6 and not bool(s.get("spark_drawn_this_turn", False)):
        s["spark_drawn_this_turn"] = True
        for obj_id in list(state.objects):
            obj = state.objects.get(obj_id)
            if obj is None or obj.controller != player_id:
                continue
            if obj.zone != ZoneType.BATTLEFIELD or obj.state.scp_status != "pending":
                continue
            if obj.state.scp_paperwork <= 0:
                continue
            prior = obj.state.scp_paperwork
            obj.state.scp_paperwork = max(0, prior - 1)
            events.append(Event(
                type=EventType.SCP_PAPERWORK_TICK,
                payload={
                    "object_id": obj.id,
                    "from": prior,
                    "to": obj.state.scp_paperwork,
                    "reason": "spark_containment",
                },
                source=obj.id,
                controller=player_id,
            ))
            break
    return events


# ---------------------------------------------------------------------------
# Cluster 4: Leyline Saturation
# ---------------------------------------------------------------------------


def apply_leyline_saturation(game, opener_id: str, opened_obj: GameObject) -> list[Event]:
    """Hook on opposing ``SCP_OPEN_DOSSIER``. When ``opened_obj`` is a
    Procedure/Facility/Mandate (NOT an anomaly), each opposing player's
    active anomalies tagged with ``scp_leyline_saturation = N`` drop
    ``scp_suppressed`` by N (negative suppression = bonus hazard).

    The reverse-bookkeeping needed for ``clear_leyline_saturation`` is stored
    on the saturating player's site under ``leyline_saturation_delta`` —
    keyed by anomaly_id so the cleanup hook can restore exactly what was
    applied without trampling unrelated ``scp_suppressed`` adjustments.
    """
    if opened_obj is None or opened_obj.card_def is None:
        return []
    types = _card_types(opened_obj)
    if CardType.SCP_ANOMALY in types:
        return []
    if (
        CardType.SCP_PROCEDURE not in types
        and CardType.SCP_FACILITY not in types
        and CardType.SCP_MANDATE not in types
    ):
        return []
    state = game.state
    for saturator_id in _opposing_players(state, opener_id):
        ensure_scp_state(state, saturator_id)
        delta_map = site(state, saturator_id).setdefault("leyline_saturation_delta", {})
        for anomaly_id in list(state.scp_anomalies.get(saturator_id, [])):
            anomaly = state.objects.get(anomaly_id)
            if not anomaly or anomaly.zone != ZoneType.BATTLEFIELD:
                continue
            if anomaly.state.scp_status != "active":
                continue
            n = int(getattr(anomaly.card_def, "scp_leyline_saturation", 0) or 0)
            if n <= 0:
                continue
            anomaly.state.scp_suppressed = int(
                getattr(anomaly.state, "scp_suppressed", 0) or 0,
            ) - n
            delta_map[anomaly_id] = int(delta_map.get(anomaly_id, 0) or 0) + n
    return []


def clear_leyline_saturation(state: GameState, player_id: str) -> None:
    """End-of-turn cleanup. Restores every ``scp_suppressed`` delta booked into
    ``leyline_saturation_delta`` for ``player_id`` and zeroes the bookkeeping.
    """
    ensure_scp_state(state, player_id)
    s = site(state, player_id)
    delta_map = s.get("leyline_saturation_delta", {}) or {}
    for anomaly_id, delta in list(delta_map.items()):
        anomaly = state.objects.get(anomaly_id)
        if not anomaly:
            continue
        anomaly.state.scp_suppressed = int(
            getattr(anomaly.state, "scp_suppressed", 0) or 0,
        ) + int(delta or 0)
    s["leyline_saturation_delta"] = {}


# ---------------------------------------------------------------------------
# Cluster 5: Planar Rift
# ---------------------------------------------------------------------------


def apply_planar_rift(game, player_id: str, rift_obj: GameObject) -> list[Event]:
    """Hook on ``SCP_CONTAINED`` for rift_obj when ``scp_planar_rift = X`` is
    set. Exiles the top X of ``player_id``'s library into the rift_window
    shelf.

    Top-of-library is the tail of ``state.zones["library_{pid}"].objects``.
    The exiled object IDs are appended to ``site["rift_window"]`` so
    ``play_from_rift_window`` can consume them.
    """
    if rift_obj is None or rift_obj.card_def is None:
        return []
    x = int(getattr(rift_obj.card_def, "scp_planar_rift", 0) or 0)
    if x <= 0:
        return []
    state = game.state
    ensure_scp_state(state, player_id)
    library = state.zones.get(f"library_{player_id}")
    exile = state.zones.get("exile")
    window = site(state, player_id).setdefault("rift_window", [])
    if library is None:
        return []
    moved = 0
    while moved < x and library.objects:
        obj_id = library.objects.pop()
        obj = state.objects.get(obj_id)
        if obj is None:
            continue
        obj.zone = ZoneType.EXILE
        if exile is not None and obj.id not in exile.objects:
            exile.objects.append(obj.id)
        window.append(obj.id)
        moved += 1
    return []


def play_from_rift_window(game, player_id: str, card_id: str) -> tuple[bool, str, list[Event]]:
    """Play ``card_id`` from the rift_window shelf directly onto the
    battlefield as an active anomaly. Skips the paperwork queue — Planar
    Rift's flavor is "the entity is already here; you just point at it."
    """
    state = game.state
    ensure_scp_state(state, player_id)
    s = site(state, player_id)
    window = s.get("rift_window", []) or []
    if card_id not in window:
        return False, "Card not in rift window", []
    obj = state.objects.get(card_id)
    if obj is None:
        return False, "Object missing", []
    exile = state.zones.get("exile")
    battlefield = state.zones.get("battlefield")
    if exile is not None and obj.id in exile.objects:
        exile.objects.remove(obj.id)
    if battlefield is not None and obj.id not in battlefield.objects:
        battlefield.objects.append(obj.id)
    obj.zone = ZoneType.BATTLEFIELD
    obj.controller = player_id
    while card_id in window:
        window.remove(card_id)
    s["rift_window"] = window
    events = _activate_dossier(game, obj, auto_seal_default=False)
    # scp_on_rift_play fires after the rift-window play resolves. It is the
    # rift-specific entry path; cards that want a different trigger than
    # the generic scp_on_play use this for rift-specific payoffs (Multiverse
    # Rift archetype's Containment Aperture Alpha attaches this).
    events.extend(_fire_card_hook(game, obj, "scp_on_rift_play", state))
    return True, "Played from rift window", events


def cleanup_rift_window(game, player_id: str) -> list[Event]:
    """End-of-turn cleanup. Anything left in the rift_window shelf returns to
    the top of the controller's library.
    """
    state = game.state
    ensure_scp_state(state, player_id)
    s = site(state, player_id)
    window = s.get("rift_window", []) or []
    if not window:
        s["rift_window"] = []
        return []
    library = state.zones.get(f"library_{player_id}")
    exile = state.zones.get("exile")
    for card_id in list(window):
        obj = state.objects.get(card_id)
        if obj is None:
            continue
        if exile is not None and obj.id in exile.objects:
            exile.objects.remove(obj.id)
        if library is not None and obj.id not in library.objects:
            library.objects.append(obj.id)
        obj.zone = ZoneType.LIBRARY
    s["rift_window"] = []
    return []


# ---------------------------------------------------------------------------
# Cluster 7: Annihilation Wave + Wurm Devourer
# ---------------------------------------------------------------------------


def apply_annihilation_wave(game, player_id: str, *, breach_amount: int = 1) -> list[Event]:
    """Hook on ``SCP_BREACH_TICK`` for ``player_id``. For each active anomaly
    ``player_id`` controls tagged ``scp_annihilation_wave = N``, redact N
    opposing dossiers AND bump every opposing player's breach by N.

    ``breach_amount`` is the breach delta currently being processed —
    accepted for callers that want to scale the effect against a real breach
    tick but the test surface treats N as the canonical pump amount.
    """
    state = game.state
    ensure_scp_state(state, player_id)
    events: list[Event] = []
    for anomaly_id in list(state.scp_anomalies.get(player_id, [])):
        anomaly = state.objects.get(anomaly_id)
        if not anomaly or anomaly.zone != ZoneType.BATTLEFIELD:
            continue
        if anomaly.state.scp_status != "active":
            continue
        n = int(getattr(anomaly.card_def, "scp_annihilation_wave", 0) or 0)
        if n <= 0:
            continue
        events.extend(redact_opposing(game, player_id, n, source=anomaly.id))
        for opp_id in _opposing_players(state, player_id):
            site(state, opp_id)["breach"] += n
        # scp_on_annihilation_wave_fire fires on the anomaly that just fired
        # its wave. Used by Eldrazi Apex anomalies that want secondary
        # effects ("when this anomaly's wave fires, also +1 breach to all
        # opponents", "draw a brief", etc.).
        events.extend(_fire_card_hook(game, anomaly, "scp_on_annihilation_wave_fire", state))
    events.extend(check_scp_loss(game))
    return events


def apply_wurm_devourer(game, anomaly_obj: GameObject) -> list[Event]:
    """Hook called when a successful research test fires against a Wurm
    Devourer anomaly. Reverses the curiosity tick (``scp_researched -= 1``)
    that ``run_test`` applied, bumps ``scp_suppressed += 2`` (negative
    suppression doesn't apply here — Wurm Devourer's flavor is "the devourer
    is sated, less hazardous next breach"), and increments the controller's
    ``wurms_tamed`` counter for the alt-win.
    """
    if anomaly_obj is None or anomaly_obj.card_def is None:
        return []
    if not bool(getattr(anomaly_obj.card_def, "scp_wurm_devourer", False)):
        return []
    controller = anomaly_obj.controller
    state = game.state
    ensure_scp_state(state, controller)
    anomaly_obj.state.scp_researched = max(
        0, int(getattr(anomaly_obj.state, "scp_researched", 0) or 0) - 1,
    )
    anomaly_obj.state.scp_suppressed = int(
        getattr(anomaly_obj.state, "scp_suppressed", 0) or 0,
    ) + 2
    site(state, controller)["wurms_tamed"] = int(
        site(state, controller).get("wurms_tamed", 0) or 0,
    ) + 1
    return [Event(
        type=EventType.SCP_INCIDENT_RESOLVED,
        payload={
            "player": controller,
            "object_id": anomaly_obj.id,
            "reason": "wurm_taming",
            "wurms_tamed": site(state, controller)["wurms_tamed"],
        },
        source=anomaly_obj.id,
        controller=controller,
    )]


# ---------------------------------------------------------------------------
# Turn-marker housekeeping
# ---------------------------------------------------------------------------


def reset_fbn_turn_flags(state: GameState, player_id: str) -> None:
    """Turn-start hook. Reset per-turn FBN markers that the previous turn may
    have left set. Currently:

      * ``spark_drawn_this_turn`` — Cluster 3 one-shot guard.

    Note: ``compleation_swaps`` / ``phylactery_audits`` / ``wurms_tamed`` are
    cross-turn counters (alt-win progress) and are NOT reset here.
    """
    ensure_scp_state(state, player_id)
    s = site(state, player_id)
    s["spark_drawn_this_turn"] = False
