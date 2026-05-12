"""Legal-action packets for Codex-supported MTG mirror playtests.

This module is deterministic and model-free. Codex player agents receive only
the hidden-information-safe packet produced here, choose an action id, and the
referee validates that id against a fresh legal-action list before applying it.
"""

from __future__ import annotations

from typing import Any

from src.engine.mana import ManaCost
from src.engine.priority import ActionType, LegalAction
from src.engine.queries import get_power, get_toughness, has_ability, is_creature
from src.engine.types import CardType, GameObject, ZoneType


def _zone_objects(game, key: str) -> list[GameObject]:
    zone = game.state.zones.get(key)
    if not zone:
        return []
    return [
        game.state.objects[obj_id]
        for obj_id in list(zone.objects)
        if obj_id in game.state.objects
    ]


def _card_types(obj: GameObject) -> set[CardType]:
    return set(obj.characteristics.types or set())


def _type_line(obj: GameObject) -> str:
    parts: list[str] = []
    if obj.characteristics.supertypes:
        parts.extend(sorted(obj.characteristics.supertypes))
    parts.extend(t.name.title() for t in sorted(_card_types(obj), key=lambda t: t.name))
    if obj.characteristics.subtypes:
        parts.append("-")
        parts.extend(sorted(obj.characteristics.subtypes))
    return " ".join(parts)


def _mana_value(obj: GameObject) -> int:
    try:
        return ManaCost.parse(obj.characteristics.mana_cost or "").mana_value
    except Exception:
        return 0


def _public_card(game, obj: GameObject) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": obj.id,
        "name": obj.name,
        "zone": obj.zone.name,
        "type_line": _type_line(obj),
        "mana_cost": obj.characteristics.mana_cost or "",
        "colors": sorted(color.value for color in (obj.characteristics.colors or set())),
        "tapped": bool(obj.state.tapped),
        "counters": dict(obj.state.counters or {}),
    }
    if is_creature(obj, game.state):
        data.update({
            "power": get_power(obj, game.state),
            "toughness": get_toughness(obj, game.state),
            "damage": int(obj.state.damage or 0),
            "summoning_sickness": bool(obj.state.summoning_sickness),
            "abilities": sorted(obj.characteristics.keywords),
        })
    if obj.card_def and obj.zone in {ZoneType.BATTLEFIELD, ZoneType.GRAVEYARD, ZoneType.EXILE, ZoneType.STACK}:
        data["text"] = obj.card_def.text or ""
    return data


def _private_hand_card(game, obj: GameObject) -> dict[str, Any]:
    data = _public_card(game, obj)
    if obj.card_def:
        data["text"] = obj.card_def.text or ""
    return data


def _public_player_state(game, player_id: str | None) -> dict[str, Any]:
    if not player_id:
        return {}
    player = game.state.players.get(player_id)
    return {
        "player_id": player_id,
        "life": getattr(player, "life", 20) if player else 20,
        "lost": bool(getattr(player, "has_lost", False)) if player else False,
        "hand_count": len(_zone_objects(game, f"hand_{player_id}")),
        "library_count": len(_zone_objects(game, f"library_{player_id}")),
        "graveyard": [
            _public_card(game, obj)
            for obj in _zone_objects(game, f"graveyard_{player_id}")
        ],
        "exile": [
            _public_card(game, obj)
            for obj in _zone_objects(game, "exile")
            if obj.owner == player_id
        ],
    }


def _stack_state(game) -> list[dict[str, Any]]:
    stack_zone = game.state.zones.get("stack")
    if not stack_zone:
        return []
    return [
        _public_card(game, game.state.objects[obj_id])
        for obj_id in list(stack_zone.objects)
        if obj_id in game.state.objects
    ]


def _battlefield_state(game) -> list[dict[str, Any]]:
    return [
        _public_card(game, obj)
        for obj in _zone_objects(game, "battlefield")
    ]


def _opponent_id(game, player_id: str) -> str | None:
    return next((pid for pid in game.state.players if pid != player_id), None)


def _legal_attackers(game, player_id: str) -> list[dict[str, Any]]:
    combat = getattr(game, "combat_manager", None)
    if not combat or not hasattr(combat, "_get_legal_attackers"):
        return []
    try:
        ids = combat._get_legal_attackers(player_id)
    except Exception:
        ids = []
    out = []
    for obj_id in ids:
        obj = game.state.objects.get(obj_id)
        if obj:
            out.append({
                "id": obj.id,
                "name": obj.name,
                "power": get_power(obj, game.state),
                "toughness": get_toughness(obj, game.state),
                "haste": has_ability(obj, "haste", game.state),
                "flying": has_ability(obj, "flying", game.state),
            })
    return out


def _action_payload(action: LegalAction) -> dict[str, Any]:
    return {
        "action_type": action.type.name,
        "card_id": action.card_id,
        "ability_id": action.ability_id,
        "source_id": action.source_id,
        "x_value": 0,
        "modes": [],
        "targets": [],
        "crew_with": list(action.crew_with or []),
    }


def _tags_for_action(game, player_id: str, action: LegalAction) -> list[str]:
    if action.type == ActionType.PASS:
        return ["pass"]
    if action.type == ActionType.PLAY_LAND:
        return ["resource"]
    if action.type == ActionType.CREW:
        return ["attack", "tempo"]
    if action.type in {ActionType.ACTIVATE_ABILITY, ActionType.CYCLE_CARD}:
        return ["value"]
    if action.type == ActionType.CAST_SPELL and action.card_id:
        obj = game.state.objects.get(action.card_id)
        if not obj:
            return ["spell"]
        tags = ["spell"]
        if CardType.CREATURE in _card_types(obj):
            tags.append("threat")
        if _mana_value(obj) <= 2:
            tags.append("tempo")
        text = (obj.card_def.text if obj.card_def else "") or ""
        lowered = text.lower()
        if "draw" in lowered:
            tags.append("card_advantage")
        if "damage" in lowered or "destroy" in lowered or "exile target" in lowered:
            tags.append("interaction")
        return tags
    return []


def _can_packet_apply(action: LegalAction) -> bool:
    # The Codex harness currently delegates choices/targets to deterministic
    # fallbacks. Avoid exposing target-required actions as direct model choices
    # until target-packet support is added.
    return not bool(action.requires_targets)


def legal_mtg_actions(game, player_id: str) -> list[dict[str, Any]]:
    """Return the current legal MTG action packet for ``player_id``."""
    priority = getattr(game, "priority_system", None)
    raw_actions: list[LegalAction] = []
    if priority is not None:
        try:
            raw_actions = list(priority.get_legal_actions(player_id))
        except Exception:
            raw_actions = []

    actions: list[dict[str, Any]] = []
    for raw in raw_actions:
        if not _can_packet_apply(raw):
            continue
        actions.append({
            "id": f"a{len(actions):03d}",
            "type": f"MTG_{raw.type.name}",
            "payload": _action_payload(raw),
            "label": raw.description or raw.type.name.replace("_", " ").title(),
            "tags": _tags_for_action(game, player_id, raw),
        })

    if not any(action["type"] == "MTG_PASS" for action in actions):
        actions.insert(0, {
            "id": "a000",
            "type": "MTG_PASS",
            "payload": {
                "action_type": "PASS",
                "card_id": None,
                "ability_id": None,
                "source_id": None,
                "x_value": 0,
                "modes": [],
                "targets": [],
                "crew_with": [],
            },
            "label": "Pass priority",
            "tags": ["pass"],
        })
        for index, action in enumerate(actions):
            action["id"] = f"a{index:03d}"
    return actions


def visible_mtg_packet(
    game,
    player_id: str,
    legal_actions: list[dict[str, Any]],
    *,
    match_id: str = "mtg-codex",
    seed: int | None = None,
) -> dict[str, Any]:
    """Return a hidden-information-safe packet for one MTG player."""
    opponent_id = _opponent_id(game, player_id)
    turn = getattr(game, "turn_manager", None)
    turn_state = getattr(turn, "turn_state", None)
    return {
        "match_id": match_id,
        "seed": seed,
        "turn": int(game.state.turn_number),
        "active_player": game.state.active_player,
        "priority_player": player_id,
        "seat": player_id,
        "phase": getattr(getattr(turn_state, "phase", None), "name", "PRECOMBAT_MAIN"),
        "step": getattr(getattr(turn_state, "step", None), "name", "MAIN"),
        "objective": "Reduce the opponent to 0 life or make them lose by normal MTG state-based actions.",
        "loss_conditions": {
            "life": "A player with 0 or less life loses.",
            "deck_out": "A player loses when they must draw from an empty library.",
        },
        "rules_reminders": [
            "Choose exactly one legal action id.",
            "The referee validates the id against a fresh legal-action list.",
            "Passing priority may resolve the stack or end the current abbreviated turn.",
            "The packet hides opponent hand and library contents.",
        ],
        "you": {
            **_public_player_state(game, player_id),
            "hand": [
                _private_hand_card(game, obj)
                for obj in sorted(_zone_objects(game, f"hand_{player_id}"), key=lambda o: (o.name, o.id))
            ],
            "legal_attackers": _legal_attackers(game, player_id),
        },
        "opponent": _public_player_state(game, opponent_id),
        "battlefield": _battlefield_state(game),
        "stack": _stack_state(game),
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


def validate_mtg_action(game, player_id: str, action_id_or_payload: str | dict[str, Any]) -> dict[str, Any]:
    """Validate an action id or exact payload against the current legal list."""
    legal = legal_mtg_actions(game, player_id)
    if isinstance(action_id_or_payload, str):
        for action in legal:
            if action["id"] == action_id_or_payload:
                return {"ok": True, "action": action, "error": None}
        return {"ok": False, "action": None, "error": f"Unknown action id: {action_id_or_payload}"}

    action_id = action_id_or_payload.get("id") or action_id_or_payload.get("action_id")
    if action_id:
        return validate_mtg_action(game, player_id, str(action_id))
    payload = action_id_or_payload.get("payload", action_id_or_payload)
    for action in legal:
        if action["payload"] == payload:
            return {"ok": True, "action": action, "error": None}
    return {"ok": False, "action": None, "error": "Payload is not legal in the current state"}
