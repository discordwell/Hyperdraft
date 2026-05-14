"""Hidden-info-safe legal actions for Hearthstone Codex mirror playtests."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from src.engine.queries import get_power, get_toughness, has_ability
from src.engine.types import CardType, Event, EventType, EventStatus, ZoneType


def legal_hearthstone_actions(game, player_id: str) -> list[dict]:
    """Return stable legal action choices for the active Hearthstone player."""
    state = game.state
    player = state.players.get(player_id)
    if not player or player.has_lost:
        return []
    if state.active_player != player_id:
        return []

    actions: list[dict] = []
    actions.extend(_legal_attune_actions(game, player_id))
    actions.extend(_legal_play_card_actions(game, player_id))
    actions.extend(_legal_hero_power_actions(game, player_id))
    actions.extend(_legal_attack_actions(game, player_id))
    actions.append(
        {
            "id": "end_turn",
            "type": "HS_END_TURN",
            "payload": {"action_type": "HS_END_TURN"},
            "label": "End turn",
            "tags": ["pass"],
            "score_hint": -100,
        }
    )
    return _assign_packet_ids(actions)


def visible_hearthstone_packet(game, player_id: str, legal_actions: list[dict] | None = None) -> dict:
    """Build a packet containing only public state plus the seat's own hand."""
    state = game.state
    player = state.players[player_id]
    opponent_id = _opponent_id(state, player_id)
    opponent = state.players.get(opponent_id) if opponent_id else None
    legal_actions = legal_actions if legal_actions is not None else legal_hearthstone_actions(game, player_id)

    packet = {
        "match_id": getattr(game, "codex_match_id", "hearthstone-codex-match"),
        "seed": getattr(game, "codex_seed", None),
        "turn": state.turn_number,
        "active_player": _seat_for_player(game, state.active_player),
        "seat": _seat_for_player(game, player_id),
        "objective": "Reduce the opposing hero to 0 life while preserving your own hero.",
        "win_loss": {
            "win": "Opponent hero/player has lost.",
            "loss": "Your hero/player has lost.",
            "draw": "Turn/action cap expires with equal adjudication score.",
        },
        "rules_reminders": [
            "Choose exactly one action_id from legal_actions.",
            "Hearthstone mana crystals refill at the start of your turn.",
            "Minions with Taunt must be attacked before non-Taunt enemies.",
            "Only public battlefield, graveyard counts, and your own hand are visible.",
        ],
        "you": _player_private_view(game, player_id),
        "opponent": _opponent_public_view(game, opponent.id) if opponent else None,
        "battlefield": _battlefield_view(game),
        "public_graveyards": {
            _seat_for_player(game, pid): _public_zone_card_names(game, f"graveyard_{pid}")
            for pid in state.players
        },
        "legal_actions": [_packet_action(action) for action in legal_actions],
    }
    return packet


def validate_hearthstone_action(game, player_id: str, action_id_or_payload: Any) -> dict:
    """Validate a chosen action id against the current legal action list."""
    action_id = _extract_action_id(action_id_or_payload)
    legal_actions = legal_hearthstone_actions(game, player_id)
    if not action_id:
        return {
            "ok": False,
            "error": "Missing action_id",
            "fallback_action": deterministic_hearthstone_fallback(game, player_id, legal_actions),
        }
    for action in legal_actions:
        if action["id"] == action_id:
            return {"ok": True, "action": action, "error": None}
    return {
        "ok": False,
        "error": f"Illegal action_id {action_id!r}",
        "fallback_action": deterministic_hearthstone_fallback(game, player_id, legal_actions),
    }


def deterministic_hearthstone_fallback(game, player_id: str, legal_actions: list[dict] | None = None) -> dict:
    """Pick a deterministic legal action when a Codex player output is invalid."""
    actions = legal_actions if legal_actions is not None else legal_hearthstone_actions(game, player_id)
    if not actions:
        return {
            "id": "end_turn",
            "type": "HS_END_TURN",
            "payload": {"action_type": "HS_END_TURN"},
            "label": "End turn",
            "tags": ["pass"],
            "score_hint": -100,
        }
    return max(actions, key=lambda action: (int(action.get("score_hint", 0)), action["id"]))


async def apply_hearthstone_action(game, player_id: str, action: dict) -> list[Event]:
    """Apply a previously validated Hearthstone legal action."""
    action_type = action.get("type")
    payload = action.get("payload", {})
    events: list[Event] = []

    if action_type == "HS_END_TURN":
        return await game.turn_manager.end_turn()

    if action_type == "HS_ATTUNE_CARD":
        ok = await game.attune_card(player_id, payload.get("card_id"))
        if ok and hasattr(game.turn_manager, "_check_state_based_actions"):
            await game.turn_manager._check_state_based_actions()
        return events

    if action_type == "HS_PLAY_CARD":
        events.extend(await _execute_card_play(game, player_id, payload.get("card_id"), payload.get("targets", [])))
    elif action_type == "HS_HERO_POWER":
        ok = await game.use_hero_power(player_id, payload.get("target_id"))
        if ok:
            events.append(
                Event(
                    type=EventType.HERO_POWER_ACTIVATE,
                    payload={"player": player_id, "hero_power_id": game.state.players[player_id].hero_power_id},
                    source=game.state.players[player_id].hero_power_id,
                )
            )
    elif action_type == "HS_ATTACK":
        combat = getattr(game, "combat_manager", None)
        if combat:
            events.extend(await combat.declare_attack(payload.get("attacker_id"), payload.get("target_id")))

    if hasattr(game.turn_manager, "_check_state_based_actions"):
        await game.turn_manager._check_state_based_actions()
    return events


def public_hearthstone_summary(game) -> dict:
    """Compact public state summary for transcript entries."""
    state = game.state
    return {
        "turn": state.turn_number,
        "active_player": _seat_for_player(game, state.active_player),
        "players": {
            _seat_for_player(game, pid): _opponent_public_view(game, pid)
            for pid in state.players
        },
        "battlefield": _battlefield_view(game),
        "winner": _seat_for_player(game, game.get_winner()) if game.is_game_over() else None,
    }


def packet_hash(packet: dict) -> str:
    data = json.dumps(packet, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def _legal_play_card_actions(game, player_id: str) -> list[dict]:
    state = game.state
    player = state.players.get(player_id)
    hand = state.zones.get(f"hand_{player_id}")
    if not player or not hand:
        return []

    actions = []
    board_full = _minion_count(state, player_id) >= 7
    for card_id in list(hand.objects):
        card = state.objects.get(card_id)
        if not card:
            continue
        if board_full and CardType.MINION in card.characteristics.types:
            continue
        cost = _mana_cost(card, state, player_id)
        if cost > player.mana_crystals_available:
            continue

        targets = _chosen_spell_targets(card, state, player_id)
        if CardType.SPELL in card.characteristics.types and getattr(card.card_def, "requires_target", False):
            if not targets:
                continue

        tags = ["tempo"]
        if CardType.SPELL in card.characteristics.types:
            tags = ["spell"]
        elif CardType.WEAPON in card.characteristics.types:
            tags = ["weapon", "tempo"]
        elif has_ability(card, "taunt", state):
            tags = ["stabilize", "taunt"]
        if "draw" in _card_text(card):
            tags.append("resource")
        if "deal" in _card_text(card) and "damage" in _card_text(card):
            tags.append("damage")

        target_suffix = ""
        if targets:
            target_suffix = ":" + "-".join(targets)
        actions.append(
            {
                "id": f"play:{card_id}{target_suffix}",
                "type": "HS_PLAY_CARD",
                "payload": {"action_type": "HS_PLAY_CARD", "card_id": card_id, "targets": targets},
                "label": f"Play {card.name}" + (_target_label(game, targets) if targets else ""),
                "tags": tags,
                "score_hint": _play_score(card, state, player_id, cost),
            }
        )
    return actions


def _legal_attune_actions(game, player_id: str) -> list[dict]:
    state = game.state
    player = state.players.get(player_id)
    hand = state.zones.get(f"hand_{player_id}")
    if not player or not hand or not getattr(player, "manual_mana_growth", False):
        return []
    if int(getattr(player, "attunements_this_turn", 0) or 0) >= int(getattr(player, "attunements_per_turn", 1) or 1):
        return []

    actions = []
    for card_id in list(hand.objects):
        card = state.objects.get(card_id)
        if not card:
            continue
        actions.append(
            {
                "id": f"attune:{card_id}",
                "type": "HS_ATTUNE_CARD",
                "payload": {"action_type": "HS_ATTUNE_CARD", "card_id": card_id},
                "label": f"Attune {card.name}",
                "tags": ["resource"],
                "score_hint": max(20, _mana_cost(card, state, player_id) * 4),
            }
        )
    return actions


def _legal_hero_power_actions(game, player_id: str) -> list[dict]:
    state = game.state
    player = state.players.get(player_id)
    if not player or not player.hero_power_id or player.hero_power_used:
        return []
    hp_obj = state.objects.get(player.hero_power_id)
    if not hp_obj:
        return []
    cost = _mana_cost(hp_obj, state, player_id) or 2
    if player.mana_crystals_available < cost:
        return []
    if "summon" in _card_text(hp_obj) and _minion_count(state, player_id) >= 7:
        return []

    tags = ["resource"] if "draw" in _card_text(hp_obj) else ["tempo"]
    if "armor" in _card_text(hp_obj) or "restore" in _card_text(hp_obj):
        tags.append("stabilize")
    if "damage" in _card_text(hp_obj):
        tags.append("damage")
    return [
        {
            "id": "hero_power",
            "type": "HS_HERO_POWER",
            "payload": {"action_type": "HS_HERO_POWER"},
            "label": f"Use hero power: {hp_obj.name}",
            "tags": tags,
            "score_hint": 16 if player.mana_crystals_available <= 3 else 10,
        }
    ]


def _legal_attack_actions(game, player_id: str) -> list[dict]:
    combat = getattr(game, "combat_manager", None)
    if not combat:
        return []
    state = game.state
    actions = []
    opponent_id = _opponent_id(state, player_id)
    opponent = state.players.get(opponent_id) if opponent_id else None
    opponent_effective_life = (opponent.life + opponent.armor) if opponent else 999

    for attacker_id in combat._get_legal_attackers(player_id):
        attacker = state.objects.get(attacker_id)
        if not attacker:
            continue
        for target_id in combat._get_legal_targets(player_id):
            target = state.objects.get(target_id)
            if not target:
                continue
            if not combat._check_taunt_requirement(player_id, target_id):
                continue
            if (
                CardType.MINION in attacker.characteristics.types
                and attacker.state.summoning_sickness
                and has_ability(attacker, "rush", state)
                and not has_ability(attacker, "charge", state)
                and CardType.HERO in target.characteristics.types
            ):
                continue

            attacker_power = _attacker_power(state, attacker)
            tags = ["attack"]
            score = attacker_power * 3
            if CardType.HERO in target.characteristics.types:
                tags.append("pressure")
                score += 8
                if attacker_power >= opponent_effective_life:
                    tags.append("lethal")
                    score += 200
            else:
                tags.append("trade")
                target_health = max(0, (get_toughness(target, state) or 0) - target.state.damage)
                if attacker_power >= target_health:
                    tags.append("removal")
                    score += (get_power(target, state) or 0) * 4 + 12
            actions.append(
                {
                    "id": f"attack:{attacker_id}:{target_id}",
                    "type": "HS_ATTACK",
                    "payload": {
                        "action_type": "HS_ATTACK",
                        "attacker_id": attacker_id,
                        "target_id": target_id,
                    },
                    "label": f"Attack {target.name} with {attacker.name}",
                    "tags": tags,
                    "score_hint": score,
                }
            )
    return actions


async def _execute_card_play(game, player_id: str, card_id: str | None, targets: list[str]) -> list[Event]:
    state = game.state
    events: list[Event] = []
    if not card_id:
        return events
    card = state.objects.get(card_id)
    player = state.players.get(player_id)
    hand = state.zones.get(f"hand_{player_id}")
    if not card or not player or not hand or card_id not in hand.objects:
        return events
    cost = _mana_cost(card, state, player_id)
    if player.mana_crystals_available < cost:
        return events
    if CardType.MINION in card.characteristics.types and _minion_count(state, player_id) >= 7:
        return events

    player.mana_crystals_available -= cost
    if (
        CardType.MINION in card.characteristics.types
        or CardType.WEAPON in card.characteristics.types
        or CardType.SECRET in card.characteristics.types
    ):
        # Secrets share battlefield-entry semantics with weapons: their
        # `setup_interceptors` register an interceptor gated
        # ``duration='while_on_battlefield'`` that goes live once the
        # secret's source object moves into BATTLEFIELD. (See audit
        # commit 535b7598 — without this branch the SECRET elif chain
        # silently no-ops: no mana deduction, no hand → battlefield
        # zone move, no interceptor activation.)
        # NOTE: Real Hearthstone forbids casting a duplicate active
        # secret and caps at 5 active secrets per player. The legal-
        # action generator does not enforce that today — TODO follow-on.
        zone_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": card_id,
                "from_zone": f"hand_{player_id}",
                "from_zone_type": ZoneType.HAND,
                "to_zone": "battlefield",
                "to_zone_type": ZoneType.BATTLEFIELD,
            },
            source=card_id,
        )
        if game.pipeline:
            game.pipeline.emit(zone_event)
        events.append(zone_event)
    elif CardType.SPELL in card.characteristics.types:
        spell_event = Event(
            type=EventType.SPELL_CAST,
            payload={"spell_id": card_id, "caster": player_id},
            source=card_id,
        )
        if game.pipeline:
            game.pipeline.emit(spell_event)
        events.append(spell_event)
        card_def = card.card_def
        if card_def and getattr(card_def, "spell_effect", None):
            try:
                if game.pipeline:
                    game.pipeline.sba_deferred = True
                for event in card_def.spell_effect(card, state, targets or []):
                    if game.pipeline:
                        game.pipeline.emit(event)
                    events.append(event)
            finally:
                if game.pipeline:
                    game.pipeline.sba_deferred = False
            if hasattr(game.turn_manager, "_check_state_based_actions"):
                await game.turn_manager._check_state_based_actions()
        zone_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": card_id,
                "from_zone": f"hand_{player_id}",
                "from_zone_type": ZoneType.HAND,
                "to_zone": f"graveyard_{player_id}",
                "to_zone_type": ZoneType.GRAVEYARD,
            },
            source=card_id,
        )
        if game.pipeline:
            game.pipeline.emit(zone_event)
        events.append(zone_event)

    player.cards_played_this_turn += 1
    _consume_cost_modifiers(player, card)
    if hasattr(game.turn_manager, "_check_state_based_actions"):
        await game.turn_manager._check_state_based_actions()
    return events


def _chosen_spell_targets(card, state, player_id: str) -> list[str]:
    if CardType.SPELL not in card.characteristics.types:
        return []
    if not getattr(card.card_def, "requires_target", False):
        return []
    from src.ai.hearthstone_adapter import HearthstoneAIAdapter

    adapter = HearthstoneAIAdapter(difficulty="hard")
    nested = adapter._choose_spell_targets(card, state, player_id)
    return [target for group in nested for target in group]


def _mana_cost(card, state, player_id: str) -> int:
    cost = 0
    cost_str = getattr(card.characteristics, "mana_cost", None) or ""
    for number in re.findall(r"\{(\d+)\}", cost_str):
        cost += int(number)

    if card.card_def and getattr(card.card_def, "dynamic_cost", None):
        try:
            cost = max(0, int(card.card_def.dynamic_cost(card, state)))
        except Exception:
            pass

    player = state.players.get(player_id)
    if player:
        floor = 0
        for modifier in list(getattr(player, "cost_modifiers", [])):
            mod_type = modifier.get("card_type")
            if mod_type and mod_type in card.characteristics.types:
                cost -= int(modifier.get("amount", 0) or 0)
                floor = max(floor, int(modifier.get("floor", 0) or 0))
        cost = max(floor, cost)
    return max(0, cost)


def _consume_cost_modifiers(player, card) -> None:
    kept = []
    for modifier in list(getattr(player, "cost_modifiers", [])):
        if modifier.get("uses_remaining") is not None:
            mod_type = modifier.get("card_type")
            if mod_type and mod_type in card.characteristics.types:
                modifier["uses_remaining"] -= 1
                if modifier["uses_remaining"] <= 0:
                    continue
        kept.append(modifier)
    player.cost_modifiers = kept


def _play_score(card, state, player_id: str, cost: int) -> int:
    score = cost * 10
    if CardType.MINION in card.characteristics.types:
        score += (get_power(card, state) or 0) * 4
        score += (get_toughness(card, state) or 0) * 3
        if has_ability(card, "charge", state):
            score += 18
        if has_ability(card, "taunt", state):
            score += 12
    elif CardType.SPELL in card.characteristics.types:
        text = _card_text(card)
        if "deal" in text and "damage" in text:
            score += 20
        if "draw" in text:
            score += 12
        if "all enemy" in text or "all minions" in text:
            score += 12
    elif CardType.WEAPON in card.characteristics.types:
        score += (card.characteristics.power or 0) * (card.characteristics.toughness or 0) * 6
    return score


def _packet_action(action: dict) -> dict:
    out = {
        "id": action["id"],
        "type": action["type"],
        "label": action["label"],
        "tags": list(action.get("tags", [])),
    }
    payload = copy.deepcopy(action.get("payload", {}))
    if payload:
        out["payload"] = payload
    return out


def _assign_packet_ids(actions: list[dict]) -> list[dict]:
    """Expose packet-local IDs that reproduce across seeded fresh games."""
    out = []
    for index, action in enumerate(actions):
        copied = dict(action)
        copied["debug_id"] = action["id"]
        copied["id"] = f"a{index:03d}"
        out.append(copied)
    return out


def _player_private_view(game, player_id: str) -> dict:
    state = game.state
    player = state.players[player_id]
    return {
        **_base_player_view(game, player_id),
        "hand": [_private_hand_card_view(game, oid) for oid in state.zones.get(f"hand_{player_id}", []).objects],
        "library_count": len(state.zones.get(f"library_{player_id}").objects) if state.zones.get(f"library_{player_id}") else 0,
    }


def _opponent_public_view(game, player_id: str) -> dict:
    state = game.state
    return {
        **_base_player_view(game, player_id),
        "hand_count": len(state.zones.get(f"hand_{player_id}").objects) if state.zones.get(f"hand_{player_id}") else 0,
        "library_count": len(state.zones.get(f"library_{player_id}").objects) if state.zones.get(f"library_{player_id}") else 0,
    }


def _base_player_view(game, player_id: str) -> dict:
    state = game.state
    player = state.players[player_id]
    hero = state.objects.get(player.hero_id) if player.hero_id else None
    hero_power = state.objects.get(player.hero_power_id) if player.hero_power_id else None
    return {
        "seat": _seat_for_player(game, player_id),
        "life": player.life,
        "armor": player.armor,
        "mana": {
            "available": player.mana_crystals_available,
            "crystals": player.mana_crystals,
        },
        "hero": hero.name if hero else None,
        "hero_power": hero_power.name if hero_power else None,
        "hero_power_used": bool(player.hero_power_used),
        "weapon": {
            "attack": player.weapon_attack,
            "durability": player.weapon_durability,
        },
        "manual_mana_growth": bool(getattr(player, "manual_mana_growth", False)),
        "variant_resources": dict(getattr(player, "variant_resources", {}) or {}),
        "has_lost": bool(player.has_lost),
    }


def _private_hand_card_view(game, object_id: str) -> dict:
    obj = game.state.objects[object_id]
    return {
        "id": obj.id,
        "name": obj.name,
        "cost": _mana_cost(obj, game.state, obj.controller),
        "types": sorted(t.name for t in obj.characteristics.types),
        "attack": obj.characteristics.power,
        "health": obj.characteristics.toughness,
        "text": obj.card_def.text if obj.card_def else "",
        "keywords": _keywords(obj, game.state),
    }


def _battlefield_view(game) -> list[dict]:
    state = game.state
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    out = []
    for oid in battlefield.objects:
        obj = state.objects.get(oid)
        if not obj or CardType.MINION not in obj.characteristics.types:
            continue
        out.append(
            {
                "id": obj.id,
                "controller": _seat_for_player(game, obj.controller),
                "name": obj.name,
                "attack": get_power(obj, state),
                "health": max(0, (get_toughness(obj, state) or 0) - obj.state.damage),
                "damage": obj.state.damage,
                "keywords": _keywords(obj, state),
                "attacks_this_turn": obj.state.attacks_this_turn,
                "summoning_sickness": bool(obj.state.summoning_sickness),
                "frozen": bool(obj.state.frozen),
            }
        )
    return out


def _public_zone_card_names(game, zone_key: str) -> list[str]:
    zone = game.state.zones.get(zone_key)
    if not zone:
        return []
    return [game.state.objects[oid].name for oid in zone.objects if oid in game.state.objects]


def _keywords(obj, state) -> list[str]:
    kws = set(getattr(obj.characteristics, "keywords", set()) or set())
    for ability in getattr(obj.characteristics, "abilities", []) or []:
        if isinstance(ability, dict) and ability.get("keyword"):
            kws.add(str(ability["keyword"]).lower())
    for attr, keyword in (
        ("divine_shield", "divine_shield"),
        ("stealth", "stealth"),
        ("windfury", "windfury"),
        ("frozen", "frozen"),
    ):
        if getattr(obj.state, attr, False):
            kws.add(keyword)
    for keyword in ("taunt", "charge", "rush", "lifesteal"):
        if has_ability(obj, keyword, state):
            kws.add(keyword)
    return sorted(kws)


def _minion_count(state, player_id: str) -> int:
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return 0
    return sum(
        1
        for oid in battlefield.objects
        if oid in state.objects
        and state.objects[oid].controller == player_id
        and CardType.MINION in state.objects[oid].characteristics.types
    )


def _attacker_power(state, attacker) -> int:
    if CardType.HERO in attacker.characteristics.types:
        player = state.players.get(attacker.owner)
        return int(getattr(player, "weapon_attack", 0) or 0)
    return int(get_power(attacker, state) or 0)


def _card_text(card) -> str:
    return str(card.card_def.text if card.card_def else "").lower()


def _target_label(game, targets: list[str]) -> str:
    names = [game.state.objects[t].name for t in targets if t in game.state.objects]
    return f" targeting {', '.join(names)}" if names else ""


def _opponent_id(state, player_id: str) -> str | None:
    for pid in state.players:
        if pid != player_id:
            return pid
    return None


def _seat_for_player(game, player_id: str | None) -> str | None:
    if player_id is None:
        return None
    seat_map = getattr(game, "codex_seats", None)
    if seat_map and player_id in seat_map:
        return seat_map[player_id]
    players = list(game.state.players)
    if player_id in players:
        return "P1" if players.index(player_id) == 0 else "P2"
    return player_id


def _extract_action_id(action_id_or_payload: Any) -> str | None:
    if isinstance(action_id_or_payload, str):
        return action_id_or_payload
    if isinstance(action_id_or_payload, dict):
        value = action_id_or_payload.get("action_id") or action_id_or_payload.get("id")
        return str(value) if value else None
    return None


def _json_default(value):
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "name"):
        return value.name
    return str(value)
