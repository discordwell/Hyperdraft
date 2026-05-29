"""Legal-action packets for Codex-supported SCP mirror playtests.

This module is deliberately deterministic and model-free. Codex player agents
receive the packet produced here, choose an action id, and the referee validates
that id against a fresh legal-action list before applying it.
"""

from __future__ import annotations

from typing import Any

from src.engine.types import CardType, GameObject, ZoneType
from src.engine import scp


def _zone_objects(game, key: str) -> list[GameObject]:
    zone = game.state.zones.get(key)
    if not zone:
        return []
    return [game.state.objects[obj_id] for obj_id in list(zone.objects) if obj_id in game.state.objects]


def _card_types(obj: GameObject) -> set[CardType]:
    return set(obj.characteristics.types or set())


def _type_label(obj: GameObject) -> str:
    types = _card_types(obj)
    for card_type, label in (
        (CardType.SCP_ANOMALY, "Anomaly"),
        (CardType.SCP_PERSONNEL, "Personnel"),
        (CardType.SCP_FACILITY, "Facility"),
        (CardType.SCP_PROCEDURE, "Procedure"),
        (CardType.SCP_MANDATE, "Mandate"),
    ):
        if card_type in types:
            return label
    return "Card"


def _public_card(obj: GameObject) -> dict[str, Any]:
    card_def = obj.card_def
    data: dict[str, Any] = {
        "id": obj.id,
        "name": obj.name,
        "type": _type_label(obj),
        "status": obj.state.scp_status,
        "paperwork": obj.state.scp_paperwork,
        "exhausted": obj.state.scp_exhausted,
        "subtypes": sorted(str(s) for s in (obj.characteristics.subtypes or [])),
    }
    if card_def:
        for attr, key in (
            ("scp_containment", "containment"),
            ("scp_curiosity", "curiosity"),
            ("scp_hazard", "hazard"),
            ("scp_red_tape", "red_tape"),
            ("scp_clearance", "clearance"),
        ):
            value = getattr(card_def, attr, None)
            if value is not None:
                data[key] = value
        if getattr(card_def, "scp_skills", None):
            data["skills"] = dict(card_def.scp_skills)
        if getattr(card_def, "scp_bonus", None):
            data["bonus"] = dict(card_def.scp_bonus)
        if getattr(card_def, "scp_keywords", None):
            data["keywords"] = list(card_def.scp_keywords)
        if getattr(card_def, "scp_alt_win", None):
            data["alt_win"] = card_def.scp_alt_win
    return data


def _private_hand_card(obj: GameObject) -> dict[str, Any]:
    data = _public_card(obj)
    data["text"] = obj.card_def.text if obj.card_def else ""
    return data


def _available_staff(game, player_id: str) -> list[GameObject]:
    out: list[GameObject] = []
    for obj_id in list(game.state.scp_personnel.get(player_id, [])):
        obj = game.state.objects.get(obj_id)
        if (
            obj
            and obj.zone == ZoneType.BATTLEFIELD
            and obj.state.scp_status == "active"
            and not obj.state.scp_exhausted
        ):
            out.append(obj)
    return sorted(out, key=lambda o: (o.name, o.id))


def _active_anomalies(game, player_id: str) -> list[GameObject]:
    out: list[GameObject] = []
    for obj_id in list(game.state.scp_anomalies.get(player_id, [])):
        obj = game.state.objects.get(obj_id)
        if obj and obj.zone == ZoneType.BATTLEFIELD and obj.state.scp_status == "active":
            out.append(obj)
    return sorted(out, key=lambda o: (o.name, o.id))


def _contained_anomalies(game, player_id: str) -> list[GameObject]:
    out: list[GameObject] = []
    for obj_id in list(game.state.scp_contained.get(player_id, [])):
        obj = game.state.objects.get(obj_id)
        if obj and obj.zone == ZoneType.BATTLEFIELD and obj.state.scp_status == "contained":
            out.append(obj)
    return sorted(out, key=lambda o: (o.name, o.id))


def _action(action_id: str, action_type: str, payload: dict[str, Any], label: str, tags: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": action_id,
        "type": action_type,
        "payload": {"action_type": action_type, **payload},
        "label": label,
        "tags": tags or [],
    }


def legal_scp_actions(game, player_id: str) -> list[dict[str, Any]]:
    """Return the current legal SCP action packet for ``player_id``."""
    scp.ensure_scp_state(game.state, player_id)
    site = scp.site(game.state, player_id)
    actions: list[dict[str, Any]] = []

    def add(action_type: str, payload: dict[str, Any], label: str, tags: list[str] | None = None) -> None:
        actions.append(_action(f"a{len(actions):03d}", action_type, payload, label, tags))

    hand = sorted(_zone_objects(game, f"hand_{player_id}"), key=lambda o: (o.name, o.id))
    for obj in hand:
        if not obj.card_def:
            continue
        clearance = int(getattr(obj.card_def, "scp_clearance", 0) or 0)
        if site["clearance"] < clearance:
            continue
        red_tape = max(0, int(getattr(obj.card_def, "scp_red_tape", 0) or 0))
        tags = ["resource"] if CardType.SCP_PERSONNEL in _card_types(obj) else []
        if CardType.SCP_ANOMALY in _card_types(obj):
            tags = ["risky", "threat"]
        add(
            "SCP_OPEN_DOSSIER",
            {"card_id": obj.id, "fast_track": False, "sealed": False},
            f"Open {obj.name} ({_type_label(obj)}, paperwork {red_tape})",
            tags,
        )
        if red_tape > 0 and site["secrecy"] > red_tape:
            add(
                "SCP_OPEN_DOSSIER",
                {"card_id": obj.id, "fast_track": True, "sealed": False},
                f"Fast-track {obj.name} for {red_tape} secrecy",
                ["tempo", "risky"],
            )
        if CardType.SCP_ANOMALY in _card_types(obj):
            add(
                "SCP_OPEN_DOSSIER",
                {"card_id": obj.id, "fast_track": False, "sealed": True},
                f"Seal {obj.name} face-down as a delayed anomaly",
                ["stabilize"],
            )

    battlefield = sorted(_zone_objects(game, "battlefield"), key=lambda o: (o.name, o.id))
    for obj in battlefield:
        if obj.controller == player_id and obj.state.scp_status == "sealed":
            add("SCP_REVEAL_DOSSIER", {"object_id": obj.id}, f"Reveal sealed dossier {obj.name}", ["tempo"])

    staff = _available_staff(game, player_id)
    staff_ids = [obj.id for obj in staff]
    staff_label = ", ".join(obj.name for obj in staff) if staff else "no staff"
    slots_remaining = max(0, int(site.get("assignment_slots", 0) or 0) - int(site.get("assignments_used", 0) or 0))
    if staff and slots_remaining > 0:
        for anomaly in _active_anomalies(game, player_id):
            add(
                "SCP_RESEARCH",
                {"anomaly_id": anomaly.id, "staff_ids": staff_ids},
                f"Research {anomaly.name} with {staff_label}",
                ["archive", "value"],
            )
            add(
                "SCP_CONTAIN",
                {"anomaly_id": anomaly.id, "staff_ids": staff_ids},
                f"Contain {anomaly.name} with {staff_label}",
                ["stabilize", "archive"],
            )
            add(
                "SCP_SUPPRESS",
                {"anomaly_id": anomaly.id, "staff_ids": staff_ids},
                f"Suppress {anomaly.name} with {staff_label}",
                ["stabilize"],
            )

    if site.get("briefing", 0) > 0:
        for anomaly in _active_anomalies(game, player_id):
            for mood in ("docile", "cooperative", "cryptic", "agitated"):
                add("SCP_SHIFT_MOOD", {"anomaly_id": anomaly.id, "mood": mood}, f"Shift {anomaly.name} to {mood}", ["tactical"])
            for protocol in ("mirror_box", "no_eye_contact", "feed_it_lies", "ritual_diagram"):
                add(
                    "SCP_APPLY_PROTOCOL",
                    {"anomaly_id": anomaly.id, "protocol": protocol},
                    f"Apply {protocol.replace('_', ' ')} to {anomaly.name}",
                    ["tactical"],
                )

    # Activated / modal abilities on controlled permanents. One action per
    # modal mode so the chooser (human or AI) picks before dispatch.
    from src.engine.scp_abilities import is_scp_ability
    from src.engine.scp_costs import can_pay_scp_cost, describe_scp_cost
    for obj in battlefield:
        if obj.controller != player_id:
            continue
        for idx, ability in enumerate(getattr(obj.state, "activated_abilities", None) or []):
            if not is_scp_ability(ability):
                continue
            if ability.once_per_game and ability.used_this_game:
                continue
            if ability.once_per_turn and ability.activations_this_turn > 0:
                continue
            if ability.precondition_fn and not ability.precondition_fn(obj, game.state):
                continue
            ok, _why = can_pay_scp_cost(obj, game.state, ability.cost)
            if not ok:
                continue
            cost_label = describe_scp_cost(ability.cost)
            if ability.is_modal:
                for m_idx, mode in enumerate(ability.modes):
                    add(
                        "SCP_ACTIVATE_ABILITY",
                        {"source_id": obj.id, "ability_index": idx, "mode": m_idx},
                        f"{obj.name} — {mode.label} ({cost_label})",
                        ["ability", *mode.tags],
                    )
            else:
                add(
                    "SCP_ACTIVATE_ABILITY",
                    {"source_id": obj.id, "ability_index": idx},
                    f"{obj.name} — {ability.description} ({cost_label})",
                    ["ability"],
                )

    for incident_index, incident in enumerate(list(game.state.scp_incidents.get(player_id, []))):
        add("SCP_RESOLVE_INCIDENT", {"index": incident_index}, f"Resolve incident: {incident.get('name', 'unknown')}", ["stabilize"])

    contained = _contained_anomalies(game, player_id)
    active = _active_anomalies(game, player_id)
    for contained_obj in contained[:3]:
        for active_obj in active[:3]:
            add(
                "SCP_CROSS_CONTAIN",
                {"contained_id": contained_obj.id, "active_id": active_obj.id},
                f"Use contained {contained_obj.name} to dampen {active_obj.name}",
                ["stabilize", "combo"],
            )

    if site.get("archives", 0) > 0:
        for obj in battlefield:
            if obj.controller == player_id and obj.state.scp_status != "active":
                add("SCP_MEMORY_HOLE", {"object_id": obj.id}, f"Memory-hole {obj.name}", ["stabilize"])

    if site.get("ethics_debt", 0) > 0:
        add("SCP_SPEND_ETHICS", {"amount": 1, "mode": "erase_breach"}, "Spend 1 ethics to erase breach", ["stabilize"])
        add("SCP_SPEND_ETHICS", {"amount": 1, "mode": "buy_clearance"}, "Spend 1 ethics to buy clearance", ["resource"])
        add("SCP_SPEND_ETHICS", {"amount": 1, "mode": "bury_exposure"}, "Spend 1 ethics to bury exposure", ["stabilize"])

    add("SCP_END_TURN", {}, "End turn and accept breach audit", ["pass"])
    return actions


def _public_site(game, player_id: str) -> dict[str, Any]:
    s = dict(scp.site(game.state, player_id))
    s["hand_count"] = len(_zone_objects(game, f"hand_{player_id}"))
    s["library_count"] = len(_zone_objects(game, f"library_{player_id}"))
    s["graveyard_count"] = len(_zone_objects(game, f"graveyard_{player_id}"))
    s["active_anomalies"] = [_public_card(obj) for obj in _active_anomalies(game, player_id)]
    s["contained_anomalies"] = [_public_card(obj) for obj in _contained_anomalies(game, player_id)]
    s["personnel"] = [_public_card(obj) for obj in sorted(
        (game.state.objects[obj_id] for obj_id in game.state.scp_personnel.get(player_id, []) if obj_id in game.state.objects),
        key=lambda o: (o.name, o.id),
    )]
    s["facilities"] = [_public_card(obj) for obj in sorted(
        (game.state.objects[obj_id] for obj_id in game.state.scp_facilities.get(player_id, []) if obj_id in game.state.objects),
        key=lambda o: (o.name, o.id),
    )]
    s["mandates"] = [_public_card(obj) for obj in sorted(
        (game.state.objects[obj_id] for obj_id in game.state.scp_mandates.get(player_id, []) if obj_id in game.state.objects),
        key=lambda o: (o.name, o.id),
    )]
    s["incidents"] = list(game.state.scp_incidents.get(player_id, []))
    return s


def visible_scp_packet(
    game,
    player_id: str,
    legal_actions: list[dict[str, Any]],
    *,
    match_id: str = "scp-codex",
    seed: int | None = None,
) -> dict[str, Any]:
    """Return a hidden-information-safe packet for one SCP player."""
    opponents = [pid for pid in game.state.players if pid != player_id]
    opponent_id = opponents[0] if opponents else None
    return {
        "match_id": match_id,
        "seed": seed,
        "turn": int(game.state.turn_number),
        "active_player": game.state.active_player,
        "seat": player_id,
        "objective": "Gain 7 Archives or satisfy an active mandate alternate win before your Site collapses.",
        "loss_conditions": {
            "breach": "Lose at breach 10+.",
            "exposure": "Lose at secrecy 0 or less.",
            "ethics": "Lose at ethics debt 8+.",
        },
        "rules_reminders": [
            "Red tape is delay, not a spendable cost.",
            "Fast-track skips paperwork but reduces secrecy.",
            "Personnel exhaust when assigned to research, containment, or suppression.",
            "Active anomalies add hazard to breach at end of their controller's turn.",
        ],
        "you": {
            "player_id": player_id,
            "site": _public_site(game, player_id),
            "hand": [_private_hand_card(obj) for obj in sorted(_zone_objects(game, f"hand_{player_id}"), key=lambda o: (o.name, o.id))],
        },
        "opponent": {
            "player_id": opponent_id,
            "site": _public_site(game, opponent_id) if opponent_id else {},
        },
        "legal_actions": [
            {
                "id": action["id"],
                "label": action["label"],
                "type": action["type"],
                "tags": list(action.get("tags", [])),
            }
            for action in legal_actions
        ],
    }


def validate_scp_action(game, player_id: str, action_id_or_payload: str | dict[str, Any]) -> dict[str, Any]:
    """Validate an action id or exact payload against the current legal list."""
    legal = legal_scp_actions(game, player_id)
    if isinstance(action_id_or_payload, str):
        for action in legal:
            if action["id"] == action_id_or_payload:
                return {"ok": True, "action": action, "error": None}
        return {"ok": False, "action": None, "error": f"Unknown action id: {action_id_or_payload}"}

    action_id = action_id_or_payload.get("id") or action_id_or_payload.get("action_id")
    if action_id:
        return validate_scp_action(game, player_id, str(action_id))
    payload = action_id_or_payload.get("payload", action_id_or_payload)
    for action in legal:
        if action["payload"] == payload:
            return {"ok": True, "action": action, "error": None}
    return {"ok": False, "action": None, "error": "Payload is not legal in the current state"}

