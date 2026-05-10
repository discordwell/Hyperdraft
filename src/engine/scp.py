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
BREACH_LIMIT = 10
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
    for registry in (
        state.scp_anomalies,
        state.scp_contained,
        state.scp_personnel,
        state.scp_facilities,
        state.scp_mandates,
    ):
        for ids in registry.values():
            while obj.id in ids:
                ids.remove(obj.id)


def _activate_dossier(game, obj: GameObject) -> list[Event]:
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
        events.extend(_activate_dossier(game, obj))
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
            events.extend(_activate_dossier(game, obj))
    return events


def reset_staff(game, player_id: str) -> None:
    state = game.state
    ensure_scp_state(state, player_id)
    for staff_id in list(state.scp_personnel.get(player_id, [])):
        staff = state.objects.get(staff_id)
        if staff and staff.zone == ZoneType.BATTLEFIELD:
            staff.state.scp_exhausted = False


def _staff_total(state: GameState, player_id: str, staff_ids: list[str], task: str) -> tuple[int, list[str]]:
    ensure_scp_state(state, player_id)
    total = _active_bonus(state, player_id, task)
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
        total += int(skills.get(task, 0) or 0)
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
    success = total >= target
    events = game.emit(Event(
        type=EventType.SCP_ASSIGN_STAFF,
        payload={"player": player_id, "task": "contain", "staff_ids": used, "anomaly_id": anomaly_id},
        source=anomaly.id,
        controller=player_id,
    ))
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
    anomaly.state.scp_suppressed += total
    events = game.emit(Event(
        type=EventType.SCP_ASSIGN_STAFF,
        payload={"player": player_id, "task": "suppress", "staff_ids": used, "anomaly_id": anomaly_id, "total": total},
        source=anomaly.id,
        controller=player_id,
    ))
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
    accidentally advance the whole queue.
    """
    if obj.zone != ZoneType.BATTLEFIELD or obj.state.scp_status != "pending":
        return []
    obj.state.scp_paperwork = 0
    return _activate_dossier(game, obj)


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
            if alt_win == "thaumiel" and len(state.scp_contained.get(player_id, [])) >= 4 and s["breach"] == 0:
                events.extend(_declare_site_win(game, player_id, "thaumiel_containment", source=mandate.id))
            if alt_win == "veil_lockdown" and s["archives"] >= 3 and s["breach"] == 0:
                events.extend(_declare_site_win(game, player_id, "veil_lockdown", source=mandate.id))
            if alt_win == "ethics_audit" and s["archives"] >= 4 and s["secrecy"] >= 8 and s["ethics_debt"] <= 2:
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
    rarity: str | None = None,
    on_reveal=None,
    on_contain=None,
    on_test=None,
    effect=None,
) -> CardDefinition:
    """Factory shared by the SCP card pool."""
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
    card.scp_on_reveal = on_reveal
    card.scp_on_contain = on_contain
    card.scp_on_test = on_test
    card.scp_effect = effect
    card.scp_alt_win = None
    return card
