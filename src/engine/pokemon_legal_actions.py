"""Legal-action packets for Codex-supported Pokemon mirror playtests.

This module is deterministic and model-free. Codex player agents receive only
the hidden-information-safe packet produced here, choose an action id, and the
referee validates that id against a fresh legal-action list before applying it.
"""

from __future__ import annotations

from typing import Any

from src.engine.pokemon_combat import PokemonCombatManager
from src.engine.pokemon_energy import PokemonEnergySystem
from src.engine.pokemon_status import can_retreat
from src.engine.types import CardType, GameObject, PokemonType, ZoneType


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


def _supertype(obj: GameObject) -> str:
    types = _card_types(obj)
    if CardType.POKEMON in types:
        return "Pokemon"
    if CardType.ENERGY in types:
        return "Energy"
    if CardType.SUPPORTER in types:
        return "Supporter"
    if CardType.STADIUM in types:
        return "Stadium"
    if CardType.ITEM in types:
        return "Item"
    if CardType.POKEMON_TOOL in types:
        return "Tool"
    if CardType.TRAINER in types:
        return "Trainer"
    return "Card"


def _attached_energy(game, obj: GameObject) -> list[dict[str, Any]]:
    attached = []
    for energy_id in list(getattr(obj.state, "attached_energy", []) or []):
        energy = game.state.objects.get(energy_id)
        if not energy:
            continue
        attached.append({
            "id": energy.id,
            "name": energy.name,
            "energy_type": getattr(energy.card_def, "energy_type", None),
        })
    return attached


def _attack_public(attack: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": attack.get("name", "Attack"),
        "cost": list(attack.get("cost", [])),
        "damage": attack.get("damage", 0),
        "text": attack.get("text", ""),
    }


def _public_card(game, obj: GameObject) -> dict[str, Any]:
    card_def = obj.card_def
    data: dict[str, Any] = {
        "id": obj.id,
        "name": obj.name,
        "supertype": _supertype(obj),
        "zone": obj.zone.name,
    }
    if not card_def:
        return data

    if CardType.POKEMON in _card_types(obj):
        hp = getattr(card_def, "hp", 0) or 0
        damage_counters = int(getattr(obj.state, "damage_counters", 0) or 0)
        data.update({
            "hp": hp,
            "remaining_hp": max(0, hp - damage_counters * 10),
            "damage_counters": damage_counters,
            "pokemon_type": getattr(card_def, "pokemon_type", None),
            "evolution_stage": getattr(card_def, "evolution_stage", None),
            "evolves_from": getattr(card_def, "evolves_from", None),
            "retreat_cost": getattr(card_def, "retreat_cost", 0) or 0,
            "prize_count": getattr(card_def, "prize_count", 1) or 1,
            "is_ex": bool(getattr(card_def, "is_ex", False)),
            "status_conditions": sorted(getattr(obj.state, "status_conditions", set()) or []),
            "attached_energy": _attached_energy(game, obj),
            "attacks": [_attack_public(attack) for attack in getattr(card_def, "attacks", [])],
        })
        ability = getattr(card_def, "ability", None)
        if ability:
            data["ability"] = {
                "name": ability.get("name", "Ability"),
                "text": ability.get("text", ""),
            }
    elif CardType.ENERGY in _card_types(obj):
        data["energy_type"] = getattr(card_def, "energy_type", None)
    else:
        data["text"] = getattr(card_def, "text", "")
    return data


def _private_hand_card(game, obj: GameObject) -> dict[str, Any]:
    return _public_card(game, obj)


def _own_pokemon(game, player_id: str) -> list[GameObject]:
    out: list[GameObject] = []
    for key in (f"active_spot_{player_id}", f"bench_{player_id}"):
        out.extend(_zone_objects(game, key))
    return [
        obj for obj in out
        if CardType.POKEMON in _card_types(obj)
    ]


def _active_pokemon(game, player_id: str) -> GameObject | None:
    active = _zone_objects(game, f"active_spot_{player_id}")
    return active[0] if active else None


def _bench_pokemon(game, player_id: str) -> list[GameObject]:
    return [
        obj for obj in _zone_objects(game, f"bench_{player_id}")
        if CardType.POKEMON in _card_types(obj)
    ]


def _opponent_id(game, player_id: str) -> str | None:
    return next((pid for pid in game.state.players if pid != player_id), None)


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
        "payload": {"action_type": action_type, **payload},
        "label": label,
        "tags": tags or [],
    }


def _is_first_player_first_turn(game, player_id: str) -> bool:
    turn_state = getattr(game.turn_manager, "pkm_turn_state", None)
    return bool(
        turn_state
        and turn_state.game_turn_count == 1
        and turn_state.first_player_id == player_id
    )


def legal_pokemon_actions(game, player_id: str) -> list[dict[str, Any]]:
    """Return the current legal Pokemon action packet for ``player_id``."""
    actions: list[dict[str, Any]] = []
    turn_mgr = game.turn_manager
    player = game.state.players.get(player_id)
    hand = sorted(_zone_objects(game, f"hand_{player_id}"), key=lambda o: (o.name, o.id))
    bench = _bench_pokemon(game, player_id)
    own_pokemon = sorted(_own_pokemon(game, player_id), key=lambda o: (o.name, o.id))
    energy_system = PokemonEnergySystem(game.state)

    def add(action_type: str, payload: dict[str, Any], label: str, tags: list[str] | None = None) -> None:
        actions.append(_action(f"a{len(actions):03d}", action_type, payload, label, tags))

    if player:
        if len(bench) < 5:
            for obj in hand:
                if (
                    CardType.POKEMON in _card_types(obj)
                    and obj.card_def
                    and obj.card_def.evolution_stage == "Basic"
                ):
                    add(
                        "PKM_PLAY_BASIC",
                        {"card_id": obj.id},
                        f"Bench {obj.name}",
                        ["resource", "setup"],
                    )

        # iter1 fix (pilot A v2-iter1 "Evolve actions lack disambiguation labels"):
        # with 2 Lazlets on field, 4 identical "Evolve Lazlet into Lazander" labels
        # appeared. Mirror the energy-attach disambiguation pattern below: suffix
        # the target name with (Active) / (Bench) / (Bench N) only when the target
        # name collides across zones.
        evo_name_counts: dict[str, int] = {}
        for p in own_pokemon:
            evo_name_counts[p.name] = evo_name_counts.get(p.name, 0) + 1
        evo_active_obj = _active_pokemon(game, player_id)
        evo_active_id = evo_active_obj.id if evo_active_obj else None
        evo_bench_objs = _bench_pokemon(game, player_id)
        evo_bench_ids_by_name: dict[str, list[str]] = {}
        for b in evo_bench_objs:
            evo_bench_ids_by_name.setdefault(b.name, []).append(b.id)
        for evolution in hand:
            if CardType.POKEMON not in _card_types(evolution) or not evolution.card_def:
                continue
            if not getattr(evolution.card_def, "evolves_from", None):
                continue
            for target in own_pokemon:
                ok, _msg = turn_mgr.can_evolve(target.id, evolution.id)
                if ok:
                    label = f"Evolve {target.name} into {evolution.name}"
                    if evo_name_counts.get(target.name, 0) > 1:
                        if target.id == evo_active_id:
                            label += " (Active)"
                        else:
                            same_name_bench = evo_bench_ids_by_name.get(target.name, [])
                            if len(same_name_bench) > 1:
                                idx = same_name_bench.index(target.id) + 1
                                label += f" (Bench {idx})"
                            else:
                                label += " (Bench)"
                    add(
                        "PKM_EVOLVE",
                        {"card_id": evolution.id, "target_id": target.id},
                        label,
                        ["tempo", "value"],
                    )

        if not getattr(player, "energy_attached_this_turn", False):
            energy_cards = [
                obj for obj in hand
                if CardType.ENERGY in _card_types(obj)
            ]
            # Disambiguate when multiple Pokemon share a name across zones.
            # If only one Pokemon has a given name, label stays clean ("Attach X to Y").
            name_counts: dict[str, int] = {}
            for p in own_pokemon:
                name_counts[p.name] = name_counts.get(p.name, 0) + 1
            active_obj = _active_pokemon(game, player_id)
            active_id = active_obj.id if active_obj else None
            bench_objs = _bench_pokemon(game, player_id)
            bench_ids_by_name: dict[str, list[str]] = {}
            for b in bench_objs:
                bench_ids_by_name.setdefault(b.name, []).append(b.id)
            for energy in energy_cards:
                for target in own_pokemon:
                    label = f"Attach {energy.name} to {target.name}"
                    if name_counts.get(target.name, 0) > 1:
                        if target.id == active_id:
                            label += " (Active)"
                        else:
                            same_name_bench = bench_ids_by_name.get(target.name, [])
                            if len(same_name_bench) > 1:
                                idx = same_name_bench.index(target.id) + 1
                                label += f" (Bench {idx})"
                            else:
                                label += " (Bench)"
                    add(
                        "PKM_ATTACH_ENERGY",
                        {"energy_id": energy.id, "target_id": target.id},
                        label,
                        ["resource", "tempo"],
                    )

        for obj in hand:
            types = _card_types(obj)
            if CardType.ITEM in types:
                add(
                    "PKM_PLAY_ITEM",
                    {"card_id": obj.id},
                    f"Play Item {obj.name}",
                    ["tempo"],
                )
            elif CardType.SUPPORTER in types:
                if (
                    not getattr(player, "supporter_played_this_turn", False)
                    and not _is_first_player_first_turn(game, player_id)
                ):
                    add(
                        "PKM_PLAY_SUPPORTER",
                        {"card_id": obj.id},
                        f"Play Supporter {obj.name}",
                        ["value"],
                    )
            elif CardType.STADIUM in types:
                if not getattr(player, "stadium_played_this_turn", False):
                    add(
                        "PKM_PLAY_STADIUM",
                        {"card_id": obj.id},
                        f"Play Stadium {obj.name}",
                        ["resource"],
                    )

        if not getattr(player, "retreated_this_turn", False):
            active = _active_pokemon(game, player_id)
            if active:
                can, _msg = can_retreat(active.id, game.state)
                if can:
                    cost = [{"type": PokemonType.COLORLESS.value, "count": active.card_def.retreat_cost or 0}]
                    if energy_system.can_pay_cost(active.id, cost):
                        for target in bench:
                            add(
                                "PKM_RETREAT",
                                {"bench_pokemon_id": target.id},
                                f"Retreat {active.name}; promote {target.name}",
                                ["stabilize", "tempo"],
                            )

        for pokemon in own_pokemon:
            ability = getattr(pokemon.card_def, "ability", None) if pokemon.card_def else None
            if ability and ability.get("effect_fn") and not getattr(pokemon.state, "ability_used_this_turn", False):
                add(
                    "PKM_USE_ABILITY",
                    {"pokemon_id": pokemon.id},
                    f"Use {pokemon.name}'s {ability.get('name', 'Ability')}",
                    ["value"],
                )

        active = _active_pokemon(game, player_id)
        if active and not _is_first_player_first_turn(game, player_id):
            combat = PokemonCombatManager(game.state)
            for attack in combat.get_available_attacks(active.id):
                tags = ["attack"]
                opponent = _opponent_id(game, player_id)
                opp_active = _active_pokemon(game, opponent) if opponent else None
                if opp_active:
                    final_damage = combat.calculate_damage(active.id, opp_active.id, attack.get("damage", 0))
                    remaining = max(0, (opp_active.card_def.hp or 0) - opp_active.state.damage_counters * 10)
                    if final_damage >= remaining > 0:
                        tags.append("lethal")
                add(
                    "PKM_ATTACK",
                    {"attack_index": attack.get("_index", 0), "targets": []},
                    f"Attack with {active.name}: {attack.get('name', 'Attack')} for {attack.get('damage', 0)}",
                    tags,
                )

    add("PKM_END_TURN", {}, "End turn", ["pass"])
    return actions


def _public_player_state(game, player_id: str | None) -> dict[str, Any]:
    if not player_id:
        return {}
    player = game.state.players.get(player_id)
    return {
        "player_id": player_id,
        "prizes_remaining": getattr(player, "prizes_remaining", 6) if player else 6,
        "hand_count": len(_zone_objects(game, f"hand_{player_id}")),
        "library_count": len(_zone_objects(game, f"library_{player_id}")),
        "discard_count": len(_zone_objects(game, f"graveyard_{player_id}")),
        "prize_count": len(_zone_objects(game, f"prize_cards_{player_id}")),
        "active": [
            _public_card(game, obj)
            for obj in _zone_objects(game, f"active_spot_{player_id}")
        ],
        "bench": [
            _public_card(game, obj)
            for obj in sorted(_bench_pokemon(game, player_id), key=lambda o: (o.name, o.id))
        ],
    }


def visible_pokemon_packet(
    game,
    player_id: str,
    legal_actions: list[dict[str, Any]],
    *,
    match_id: str = "pokemon-codex",
    seed: int | None = None,
) -> dict[str, Any]:
    """Return a hidden-information-safe packet for one Pokemon player."""
    opponents = [pid for pid in game.state.players if pid != player_id]
    opponent_id = opponents[0] if opponents else None
    turn_state = getattr(game.turn_manager, "pkm_turn_state", None)
    return {
        "match_id": match_id,
        "seed": seed,
        "turn": int(game.state.turn_number),
        "active_player": game.state.active_player,
        "seat": player_id,
        "phase": getattr(getattr(turn_state, "phase", None), "name", "MAIN"),
        "objective": "Take all prize cards, deck the opponent, or leave the opponent with no Pokemon in play.",
        "loss_conditions": {
            "prizes": "Lose when the opponent takes their final prize card.",
            "deck_out": "Lose when you must draw from an empty deck.",
            "no_pokemon": "Lose when you have no Active or Benched Pokemon in play.",
        },
        "rules_reminders": [
            "You may attach only one Energy per turn.",
            "You may play only one Supporter per turn.",
            "The player going first cannot attack or play a Supporter on their first turn.",
            "Attacking ends the turn.",
        ],
        "you": {
            **_public_player_state(game, player_id),
            "hand": [
                _private_hand_card(game, obj)
                for obj in sorted(_zone_objects(game, f"hand_{player_id}"), key=lambda o: (o.name, o.id))
            ],
        },
        "opponent": _public_player_state(game, opponent_id),
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


def validate_pokemon_action(game, player_id: str, action_id_or_payload: str | dict[str, Any]) -> dict[str, Any]:
    """Validate an action id or exact payload against the current legal list."""
    legal = legal_pokemon_actions(game, player_id)
    if isinstance(action_id_or_payload, str):
        for action in legal:
            if action["id"] == action_id_or_payload:
                return {"ok": True, "action": action, "error": None}
        return {"ok": False, "action": None, "error": f"Unknown action id: {action_id_or_payload}"}

    action_id = action_id_or_payload.get("id") or action_id_or_payload.get("action_id")
    if action_id:
        return validate_pokemon_action(game, player_id, str(action_id))
    payload = action_id_or_payload.get("payload", action_id_or_payload)
    for action in legal:
        if action["payload"] == payload:
            return {"ok": True, "action": action, "error": None}
    return {"ok": False, "action": None, "error": "Payload is not legal in the current state"}
