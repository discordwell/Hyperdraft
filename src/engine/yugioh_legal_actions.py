"""Legal-action packets for Codex-supported Yu-Gi-Oh! mirror playtests.

This module is deterministic and model-free. Codex player agents receive only
the hidden-information-safe packet produced here, choose an action id, and the
referee validates that id against a fresh legal-action list before applying it.
"""

from __future__ import annotations

from typing import Any

from src.engine.types import CardType, GameObject, ZoneType
from src.engine.yugioh_types import YGOPhase


def _zone_objects(game, key: str) -> list[GameObject]:
    zone = game.state.zones.get(key)
    if not zone:
        return []
    return [
        game.state.objects[obj_id]
        for obj_id in list(zone.objects)
        if obj_id and obj_id in game.state.objects
    ]


def _card_types(obj: GameObject) -> set[CardType]:
    return set(obj.characteristics.types or set())


def _is_monster(obj: GameObject) -> bool:
    return CardType.YGO_MONSTER in _card_types(obj)


def _is_spell(obj: GameObject) -> bool:
    return CardType.YGO_SPELL in _card_types(obj)


def _is_trap(obj: GameObject) -> bool:
    return CardType.YGO_TRAP in _card_types(obj)


def _card_kind(obj: GameObject) -> str:
    if _is_monster(obj):
        return "Monster"
    if _is_spell(obj):
        return "Spell"
    if _is_trap(obj):
        return "Trap"
    return "Card"


def _opponent_id(game, player_id: str) -> str | None:
    return next((pid for pid in game.state.players if pid != player_id), None)


def _public_card(game, obj: GameObject, *, viewer: str, owner_view: bool) -> dict[str, Any]:
    del game, viewer
    face_down = bool(getattr(obj.state, "face_down", False))
    hidden = face_down and not owner_view
    if hidden and obj.zone == ZoneType.MONSTER_ZONE:
        return {
            "id": obj.id,
            "name": "Face-down Monster",
            "kind": "Monster",
            "zone": obj.zone.name,
            "position": getattr(obj.state, "ygo_position", "face_down_def"),
            "face_down": True,
        }
    if hidden:
        return {
            "id": obj.id,
            "name": "Set Spell/Trap",
            "kind": "Spell/Trap",
            "zone": obj.zone.name,
            "face_down": True,
        }

    card_def = obj.card_def
    data: dict[str, Any] = {
        "id": obj.id,
        "name": obj.name,
        "kind": _card_kind(obj),
        "zone": obj.zone.name,
        "face_down": face_down,
    }
    if not card_def:
        return data
    if _is_monster(obj):
        data.update({
            "atk": getattr(card_def, "atk", 0) or 0,
            "def": getattr(card_def, "def_val", 0) or 0,
            "level": getattr(card_def, "level", 0) or 0,
            "attribute": getattr(card_def, "attribute", None),
            "monster_type": getattr(card_def, "ygo_monster_type", None),
            "position": getattr(obj.state, "ygo_position", None),
            "text": getattr(card_def, "text", ""),
        })
    elif _is_spell(obj):
        data.update({
            "spell_type": getattr(card_def, "ygo_spell_type", None),
            "text": getattr(card_def, "text", ""),
        })
    elif _is_trap(obj):
        data.update({
            "trap_type": getattr(card_def, "ygo_trap_type", None),
            "text": getattr(card_def, "text", ""),
        })
    return data


def _private_hand_card(game, obj: GameObject, player_id: str) -> dict[str, Any]:
    return _public_card(game, obj, viewer=player_id, owner_view=True)


def _monsters(game, player_id: str) -> list[GameObject]:
    return [obj for obj in _zone_objects(game, f"monster_zone_{player_id}") if _is_monster(obj)]


def _spell_traps(game, player_id: str) -> list[GameObject]:
    return [
        obj
        for obj in _zone_objects(game, f"spell_trap_zone_{player_id}")
        if _is_spell(obj) or _is_trap(obj)
    ]


def _graveyard_monsters(game, player_id: str) -> list[GameObject]:
    return [obj for obj in _zone_objects(game, f"graveyard_{player_id}") if _is_monster(obj)]


def _visible_monsters(monsters: list[GameObject]) -> list[GameObject]:
    return [obj for obj in monsters if not getattr(obj.state, "face_down", False)]


def _card_text(obj: GameObject) -> str:
    return f"{obj.name} {getattr(obj.card_def, 'text', '') or ''}".lower()


def _has_empty_monster_slot(game, player_id: str) -> bool:
    zone = game.state.zones.get(f"monster_zone_{player_id}")
    return bool(zone and any(i >= len(zone.objects) or zone.objects[i] is None for i in range(5)))


def _has_empty_spell_trap_slot(game, player_id: str) -> bool:
    zone = game.state.zones.get(f"spell_trap_zone_{player_id}")
    return bool(zone and any(i >= len(zone.objects) or zone.objects[i] is None for i in range(5)))


def _tribute_ids(monsters: list[GameObject], count: int) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for monster in monsters:
        if not monster.card_def:
            continue
        atk = getattr(monster.card_def, "atk", 0) or 0
        defense = getattr(monster.card_def, "def_val", 0) or 0
        ranked.append((max(atk, defense), monster.id))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [mid for _score, mid in ranked[:count]]


def _tributes_needed(obj: GameObject) -> int:
    level = getattr(obj.card_def, "level", 0) or 0
    if level >= 7:
        return 2
    if level >= 5:
        return 1
    return 0


def _can_normal_place(game, player_id: str, obj: GameObject, monsters: list[GameObject]) -> tuple[bool, list[str]]:
    needed = _tributes_needed(obj)
    if needed and len(monsters) >= needed:
        return True, _tribute_ids(monsters, needed)
    if needed:
        return False, []
    return _has_empty_monster_slot(game, player_id), []


def _action(
    action_id: str,
    action_type: str,
    payload: dict[str, Any],
    label: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "type": action_type,
        "payload": dict(payload),
        "label": label,
        "tags": tags or [],
    }


def _spell_actions(game, player_id: str, spell: GameObject, add) -> None:
    opponent_id = _opponent_id(game, player_id)
    own_monsters = sorted(_visible_monsters(_monsters(game, player_id)), key=lambda o: (o.name, o.id))
    opp_monsters = sorted(_monsters(game, opponent_id), key=lambda o: (o.name, o.id)) if opponent_id else []
    visible_opp_monsters = sorted(_visible_monsters(opp_monsters), key=lambda o: (o.name, o.id))
    text = _card_text(spell)
    spell_type = getattr(spell.card_def, "ygo_spell_type", "Normal") if spell.card_def else "Normal"
    base = {"action_type": "activate_spell", "card_id": spell.id}
    tags = ["value"] if any(term in text for term in ("draw", "search", "add 1")) else ["tempo"]

    if spell_type == "Equip":
        for target in own_monsters:
            add(
                "YGO_ACTIVATE_SPELL",
                {**base, "targets": [target.id]},
                f"Equip {spell.name} to {target.name}",
                ["tempo", "resource"],
            )
        return

    if spell.name in {"Monster Reborn", "Premature Burial"} or "special summon 1 monster from your gy" in text:
        candidates = _graveyard_monsters(game, player_id)
        if spell.name == "Monster Reborn" and opponent_id:
            candidates += _graveyard_monsters(game, opponent_id)
        if not _has_empty_monster_slot(game, player_id):
            return
        for target in sorted(candidates, key=lambda o: (-(getattr(o.card_def, "atk", 0) or 0), o.name, o.id))[:3]:
            add(
                "YGO_ACTIVATE_SPELL",
                {**base, "targets": [target.id]},
                f"Activate {spell.name}; revive {target.name}",
                ["tempo", "recursion"],
            )
        return

    if spell.name in {"Mystical Space Typhoon", "Stamping Destruction"}:
        if opponent_id:
            targets = _spell_traps(game, opponent_id)
            targets += _zone_objects(game, f"field_spell_zone_{opponent_id}")
            for target in sorted(targets, key=lambda o: (o.name, o.id))[:3]:
                label_name = target.name if not getattr(target.state, "face_down", False) else "set Spell/Trap"
                add(
                    "YGO_ACTIVATE_SPELL",
                    {**base, "targets": [target.id]},
                    f"Activate {spell.name}; target {label_name}",
                    ["tempo", "removal"],
                )
        return

    if spell.name == "Nobleman of Crossout":
        for target in [m for m in opp_monsters if getattr(m.state, "face_down", False)]:
            add(
                "YGO_ACTIVATE_SPELL",
                {**base, "targets": [target.id]},
                f"Activate {spell.name}; banish a face-down monster",
                ["tempo", "removal"],
            )
        return

    if (
        spell.name in {"Book of Moon", "Path to Exile", "Swords to Plowshares", "Doom Blade"}
        or any(term in text for term in ("destroy 1", "banish 1", "return 1 monster", "return 1 face-up", "bounce"))
    ):
        for target in sorted(visible_opp_monsters, key=lambda o: (-(getattr(o.card_def, "atk", 0) or 0), o.name, o.id))[:3]:
            add(
                "YGO_ACTIVATE_SPELL",
                {**base, "targets": [target.id]},
                f"Activate {spell.name}; target {target.name}",
                ["tempo", "removal"],
            )
        return

    if spell.name == "Lightning Bolt":
        for target in sorted(
            [m for m in visible_opp_monsters if (getattr(m.card_def, "atk", 0) or 0) <= 1500],
            key=lambda o: (-(getattr(o.card_def, "atk", 0) or 0), o.name, o.id),
        )[:2]:
            add(
                "YGO_ACTIVATE_SPELL",
                {**base, "targets": [target.id]},
                f"Activate {spell.name}; target {target.name}",
                ["tempo", "removal"],
            )
        add("YGO_ACTIVATE_SPELL", base, f"Activate {spell.name} at opponent", ["burn", "lethal"])
        return

    add("YGO_ACTIVATE_SPELL", base, f"Activate {spell.name}", tags)


def _trap_actions(game, player_id: str, trap: GameObject, add) -> None:
    if getattr(trap.state, "face_down", False) and getattr(trap.state, "turns_set", 0) < 1:
        return
    if not trap.card_def or not trap.card_def.resolve:
        return
    opponent_id = _opponent_id(game, player_id)
    opp_monsters = _visible_monsters(_monsters(game, opponent_id)) if opponent_id else []
    text = _card_text(trap)
    base = {"action_type": "activate_trap", "card_id": trap.id}
    if any(term in text for term in ("destroy", "banish", "return", "bounce")) and opp_monsters:
        for target in sorted(opp_monsters, key=lambda o: (-(getattr(o.card_def, "atk", 0) or 0), o.name, o.id))[:3]:
            add(
                "YGO_ACTIVATE_TRAP",
                {**base, "targets": [target.id]},
                f"Activate {trap.name}; target {target.name}",
                ["tempo", "removal"],
            )
        return
    if any(term in text for term in ("draw", "damage", "inflict")):
        add("YGO_ACTIVATE_TRAP", base, f"Activate {trap.name}", ["value"])


def legal_yugioh_actions(game, player_id: str) -> list[dict[str, Any]]:
    """Return the current legal Yu-Gi-Oh! action packet for ``player_id``."""
    actions: list[dict[str, Any]] = []
    turn_mgr = game.turn_manager
    turn_state = getattr(turn_mgr, "ygo_turn_state", None)
    phase = getattr(turn_state, "phase", YGOPhase.MAIN1)
    hand = sorted(_zone_objects(game, f"hand_{player_id}"), key=lambda o: (o.name, o.id))
    own_monsters = sorted(_monsters(game, player_id), key=lambda o: (o.name, o.id))
    opponent_id = _opponent_id(game, player_id)
    opp_monsters = sorted(_monsters(game, opponent_id), key=lambda o: (o.name, o.id)) if opponent_id else []

    def add(action_type: str, payload: dict[str, Any], label: str, tags: list[str] | None = None) -> None:
        actions.append(_action(f"a{len(actions):03d}", action_type, payload, label, tags))

    if phase in {YGOPhase.MAIN1, YGOPhase.MAIN2}:
        if not getattr(turn_state, "normal_summon_used", False):
            for obj in hand:
                if not _is_monster(obj):
                    continue
                ok, tributes = _can_normal_place(game, player_id, obj, own_monsters)
                if ok:
                    payload = {"action_type": "normal_summon", "card_id": obj.id}
                    if tributes:
                        payload["tribute_ids"] = tributes
                    add("YGO_NORMAL_SUMMON", payload, f"Normal Summon {obj.name}", ["tempo", "threat"])

            for obj in hand:
                if not _is_monster(obj):
                    continue
                ok, tributes = _can_normal_place(game, player_id, obj, own_monsters)
                if ok:
                    payload = {"action_type": "set_monster", "card_id": obj.id}
                    if tributes:
                        payload["tribute_ids"] = tributes
                    add("YGO_SET_MONSTER", payload, f"Set {obj.name}", ["setup", "stabilize"])

        for obj in own_monsters:
            if getattr(obj.state, "ygo_position", None) == "face_down_def" and getattr(obj.state, "turns_set", 0) >= 1:
                add("YGO_FLIP_SUMMON", {"action_type": "flip_summon", "card_id": obj.id}, f"Flip Summon {obj.name}", ["tempo", "value"])
            elif (
                not getattr(obj.state, "face_down", False)
                and not getattr(turn_state, "position_changes", {}).get(obj.id)
                and getattr(obj.state, "ygo_position", None) in {"face_up_atk", "face_up_def"}
            ):
                add("YGO_CHANGE_POSITION", {"action_type": "change_position", "card_id": obj.id}, f"Change {obj.name}'s battle position", ["stabilize"])

        for obj in hand:
            if _is_spell(obj):
                _spell_actions(game, player_id, obj, add)

        for obj in _spell_traps(game, player_id):
            if _is_trap(obj):
                _trap_actions(game, player_id, obj, add)

        if _has_empty_spell_trap_slot(game, player_id):
            for obj in hand:
                if _is_spell(obj) or _is_trap(obj):
                    add("YGO_SET_SPELL_TRAP", {"action_type": "set_spell_trap", "card_id": obj.id}, f"Set {obj.name}", ["setup", "resource"])

        first_turn = bool(
            getattr(turn_state, "game_turn_count", 0) == 1
            and getattr(turn_state, "first_player_id", None) == player_id
        )
        can_battle = phase == YGOPhase.MAIN1 and not first_turn and any(
            not getattr(obj.state, "face_down", False)
            and getattr(obj.state, "ygo_position", None) == "face_up_atk"
            and (getattr(obj.card_def, "atk", 0) or 0) > 0
            for obj in own_monsters
        )
        if can_battle:
            add("YGO_ENTER_BATTLE", {"action_type": "enter_battle"}, "Enter Battle Phase", ["attack"])
        add("YGO_END_TURN", {"action_type": "end_turn"}, "End turn", ["pass"])
        return actions

    if phase in {YGOPhase.BATTLE_START, YGOPhase.BATTLE_STEP, YGOPhase.DAMAGE_STEP, YGOPhase.BATTLE_END}:
        attackers = [
            obj for obj in own_monsters
            if not getattr(obj.state, "face_down", False)
            and getattr(obj.state, "ygo_position", None) == "face_up_atk"
            and not getattr(turn_state, "attacks_declared", {}).get(obj.id)
            and (getattr(obj.card_def, "atk", 0) or 0) > 0
        ]
        if not opp_monsters:
            for attacker in sorted(attackers, key=lambda o: (-(getattr(o.card_def, "atk", 0) or 0), o.name, o.id)):
                add(
                    "YGO_DECLARE_ATTACK",
                    {"action_type": "declare_attack", "attacker_id": attacker.id, "target_id": None},
                    f"{attacker.name} attacks directly",
                    ["attack", "tempo"],
                )
        else:
            for attacker in sorted(attackers, key=lambda o: (-(getattr(o.card_def, "atk", 0) or 0), o.name, o.id)):
                for target in sorted(opp_monsters, key=lambda o: (o.name, o.id)):
                    label_name = target.name if not getattr(target.state, "face_down", False) else "face-down monster"
                    tags = ["attack"]
                    atk = getattr(attacker.card_def, "atk", 0) or 0
                    defense = getattr(target.card_def, "def_val", 0) or 0
                    target_atk = getattr(target.card_def, "atk", 0) or 0
                    if (
                        getattr(target.state, "ygo_position", None) == "face_up_atk"
                        and atk > target_atk
                    ) or (
                        getattr(target.state, "ygo_position", None) in {"face_up_def", "face_down_def"}
                        and atk > defense
                    ):
                        tags.append("removal")
                    add(
                        "YGO_DECLARE_ATTACK",
                        {"action_type": "declare_attack", "attacker_id": attacker.id, "target_id": target.id},
                        f"{attacker.name} attacks {label_name}",
                        tags,
                    )
        add("YGO_END_PHASE", {"action_type": "end_phase"}, "Move to Main Phase 2", ["pass"])
        add("YGO_END_TURN", {"action_type": "end_turn"}, "End turn", ["pass"])
        return actions

    add("YGO_END_TURN", {"action_type": "end_turn"}, "End turn", ["pass"])
    return actions


def _public_player_state(game, player_id: str | None, *, viewer: str) -> dict[str, Any]:
    if not player_id:
        return {}
    player = game.state.players.get(player_id)
    owner_view = player_id == viewer
    field_spell = _zone_objects(game, f"field_spell_zone_{player_id}")
    return {
        "player_id": player_id,
        "lp": getattr(player, "lp", getattr(player, "life", 0)) if player else 0,
        "hand_count": len(_zone_objects(game, f"hand_{player_id}")),
        "library_count": len(_zone_objects(game, f"library_{player_id}")),
        "graveyard": [
            _public_card(game, obj, viewer=viewer, owner_view=True)
            for obj in sorted(_zone_objects(game, f"graveyard_{player_id}"), key=lambda o: (o.name, o.id))
        ],
        "graveyard_count": len(_zone_objects(game, f"graveyard_{player_id}")),
        "banished_count": len(_zone_objects(game, f"banished_{player_id}")),
        "extra_deck_count": len(_zone_objects(game, f"extra_deck_{player_id}")),
        "monster_zone": [
            _public_card(game, obj, viewer=viewer, owner_view=owner_view)
            for obj in sorted(_monsters(game, player_id), key=lambda o: (o.name if owner_view or not getattr(o.state, "face_down", False) else "", o.id))
        ],
        "spell_trap_zone": [
            _public_card(game, obj, viewer=viewer, owner_view=owner_view)
            for obj in sorted(_spell_traps(game, player_id), key=lambda o: (o.name if owner_view or not getattr(o.state, "face_down", False) else "", o.id))
        ],
        "field_spell_zone": [
            _public_card(game, obj, viewer=viewer, owner_view=owner_view)
            for obj in field_spell
        ],
        "lost": bool(getattr(player, "has_lost", False)) if player else False,
    }


def visible_yugioh_packet(
    game,
    player_id: str,
    legal_actions: list[dict[str, Any]],
    *,
    match_id: str = "yugioh-codex",
    seed: int | None = None,
) -> dict[str, Any]:
    """Return a hidden-information-safe packet for one Yu-Gi-Oh! player."""
    opponents = [pid for pid in game.state.players if pid != player_id]
    opponent_id = opponents[0] if opponents else None
    turn_state = getattr(game.turn_manager, "ygo_turn_state", None)
    phase = getattr(getattr(turn_state, "phase", None), "value", "main1")
    return {
        "match_id": match_id,
        "seed": seed,
        "turn": int(game.state.turn_number),
        "active_player": game.state.active_player,
        "seat": player_id,
        "phase": phase,
        "objective": "Reduce the opponent's LP to 0 or make the opponent lose by drawing from an empty deck.",
        "loss_conditions": {
            "lp": "Lose when your LP reaches 0.",
            "deck_out": "Lose when you must draw from an empty deck.",
        },
        "rules_reminders": [
            "You may Normal Summon or Set one monster per turn.",
            "The first player cannot draw or enter the Battle Phase on the first turn.",
            "Face-down opponent monsters and set Spell/Trap cards are hidden information.",
            "Choose only an id from legal_actions; the referee validates and applies it.",
        ],
        "you": {
            **_public_player_state(game, player_id, viewer=player_id),
            "hand": [
                _private_hand_card(game, obj, player_id)
                for obj in sorted(_zone_objects(game, f"hand_{player_id}"), key=lambda o: (o.name, o.id))
            ],
        },
        "opponent": _public_player_state(game, opponent_id, viewer=player_id),
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


def validate_yugioh_action(game, player_id: str, action_id_or_payload: str | dict[str, Any]) -> dict[str, Any]:
    """Validate an action id or exact payload against the current legal list."""
    legal = legal_yugioh_actions(game, player_id)
    if isinstance(action_id_or_payload, str):
        for action in legal:
            if action["id"] == action_id_or_payload:
                return {"ok": True, "action": action, "error": None}
        return {"ok": False, "action": None, "error": f"Unknown action id: {action_id_or_payload}"}

    action_id = action_id_or_payload.get("id") or action_id_or_payload.get("action_id")
    if action_id:
        return validate_yugioh_action(game, player_id, str(action_id))
    payload = action_id_or_payload.get("payload", action_id_or_payload)
    for action in legal:
        if action["payload"] == payload:
            return {"ok": True, "action": action, "error": None}
    return {"ok": False, "action": None, "error": "Payload is not legal in the current state"}
