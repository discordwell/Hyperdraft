"""Deterministic referee for Codex-supported Yu-Gi-Oh! mirror playtests.

This script contains no model calls. It can run a fallback-only smoke match and
can initialize/step a pickled referee state for a parent Codex agent that is
orchestrating player subagents outside the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.engine.game import Game
from src.engine.types import Event, EventType
from src.engine.yugioh_legal_actions import (
    legal_yugioh_actions,
    validate_yugioh_action,
    visible_yugioh_packet,
)
from src.engine.yugioh_types import YGOPhase

with contextlib.redirect_stdout(sys.stderr):
    from src.cards.yugioh.deck_builder import (
        build_ygo_optimized_deck,
        list_ygo_optimized_decks,
    )
    from src.cards.yugioh.ygo_classic import (
        KAIBA_DECK,
        KAIBA_EXTRA_DECK,
        YUGI_DECK,
        YUGI_EXTRA_DECK,
    )
    from src.cards.yugioh.ygo_starter import (
        SPELLCASTER_DECK,
        SPELLCASTER_EXTRA_DECK,
        WARRIOR_DECK,
        WARRIOR_EXTRA_DECK,
    )
    from src.cards.yugioh.beyond.kamigawa import (
        build_kamigawa_deck,
        list_kamigawa_archetypes,
    )

try:  # cloudpickle handles local card hooks registered as interceptors.
    import cloudpickle as _pickle
except ImportError:  # pragma: no cover - standard pickle works for simple smoke tests.
    import pickle as _pickle


@dataclass
class CodexYugiohRefereeState:
    game: Game
    player_ids: list[str]
    deck_ids: dict[str, str]
    seed: int
    match_id: str
    active_index: int = 0
    phase: str = "need_turn_start"
    action_index: int = 0
    transcript: list[dict[str, Any]] = field(default_factory=list)


def _json_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _zone_count(game: Game, zone_key: str) -> int:
    zone = game.state.zones.get(zone_key)
    return len([obj_id for obj_id in zone.objects if obj_id]) if zone else 0


def _resolve_deck(deck_id: str) -> tuple[list, list]:
    name = deck_id.strip()
    key = name.lower()
    fixed = {
        "starter:warrior": (WARRIOR_DECK, WARRIOR_EXTRA_DECK),
        "starter:spellcaster": (SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK),
        "classic:yugi": (YUGI_DECK, YUGI_EXTRA_DECK),
        "classic:kaiba": (KAIBA_DECK, KAIBA_EXTRA_DECK),
    }
    if key in fixed:
        main, extra = fixed[key]
        return list(main), list(extra)

    optimized = set(list_ygo_optimized_decks())
    if name in optimized:
        main, extra, _strategy = build_ygo_optimized_deck(name, enforce_quality=False)
        return main, extra

    kamigawa = set(list_kamigawa_archetypes())
    archetype = key.split(":", 1)[1] if key.startswith("kamigawa:") else key
    if archetype in kamigawa:
        return build_kamigawa_deck(archetype, enforce_balance=False)

    available = (
        sorted(fixed)
        + sorted(optimized)
        + [f"kamigawa:{archetype}" for archetype in sorted(kamigawa)]
    )
    raise ValueError(f"Unknown Yu-Gi-Oh! deck id: {deck_id!r}. Available: {available}")


async def initialize_referee(
    *,
    p1_deck: str,
    p2_deck: str,
    seed: int,
    match_id: str = "yugioh-codex",
) -> CodexYugiohRefereeState:
    random.seed(seed)
    game = Game(mode="yugioh")
    p1 = game.add_player("Codex-P1")
    p2 = game.add_player("Codex-P2")
    main_a, extra_a = _resolve_deck(p1_deck)
    main_b, extra_b = _resolve_deck(p2_deck)
    game.setup_yugioh_player(p1, main_a, extra_a)
    game.setup_yugioh_player(p2, main_b, extra_b)

    await game.turn_manager.setup_game()
    turn_order = list(getattr(game.turn_manager, "_turn_order", []) or [p1.id, p2.id])
    active = game.turn_manager.ygo_turn_state.active_player_id
    active_index = turn_order.index(active) if active in turn_order else 0
    game.state.priority_player = None
    return CodexYugiohRefereeState(
        game=game,
        player_ids=turn_order,
        deck_ids={p1.id: p1_deck, p2.id: p2_deck},
        seed=seed,
        match_id=match_id,
        active_index=active_index,
    )


def _save_state(referee: CodexYugiohRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pickle.dumps(referee))


def _load_state(path: Path) -> CodexYugiohRefereeState:
    return _pickle.loads(path.read_bytes())


def _emit(game: Game, event_type: EventType, payload: dict[str, Any], *, source: str = "YGO_CODEX") -> list[Event]:
    return game.emit(Event(type=event_type, payload=payload, source=source, controller=payload.get("player")))


def _sync_losses(referee: CodexYugiohRefereeState) -> None:
    for player in referee.game.state.players.values():
        if getattr(player, "lp", getattr(player, "life", 0)) <= 0:
            player.has_lost = True


def _winner(referee: CodexYugiohRefereeState) -> str | None:
    _sync_losses(referee)
    return referee.game.get_winner()


def _game_over(referee: CodexYugiohRefereeState) -> bool:
    _sync_losses(referee)
    return referee.game.is_game_over()


def _loss_reason(game: Game, player_id: str) -> str:
    player = game.state.players[player_id]
    if getattr(player, "lp", getattr(player, "life", 0)) <= 0:
        return "lp_zero"
    if not getattr(player, "has_lost", False):
        return "not_lost"
    library = game.state.zones.get(f"library_{player_id}")
    if library is not None and not library.objects:
        return "deck_out"
    return "unknown_loss"


def begin_turn_if_needed(referee: CodexYugiohRefereeState) -> list[Event]:
    if referee.phase == "action" or _game_over(referee):
        return []
    game = referee.game
    turn_mgr = game.turn_manager
    turn_state = turn_mgr.ygo_turn_state
    active = referee.player_ids[referee.active_index]
    events: list[Event] = []

    turn_state.active_player_id = active
    turn_mgr.turn_state.active_player_id = active
    game.state.active_player = active
    game.state.priority_player = active
    turn_state.turn_number += 1
    turn_state.game_turn_count += 1
    game.state.turn_number = turn_state.turn_number
    turn_mgr.turn_state.turn_number = turn_state.turn_number
    turn_mgr._end_turn_requested = False
    turn_state.normal_summon_used = False
    turn_state.battle_phase_entered = False
    turn_state.position_changes.clear()
    turn_state.attacks_declared.clear()

    player = game.state.players.get(active)
    if player:
        player.normal_summon_used = False

    turn_mgr._increment_set_turns()
    events.extend(_emit(game, EventType.TURN_START, {"player": active, "turn": turn_state.turn_number}))

    is_very_first_turn = turn_state.game_turn_count == 1
    if not is_very_first_turn:
        turn_state.phase = YGOPhase.DRAW
        turn_mgr._draw_cards(active, 1)
        events.append(Event(type=EventType.YGO_DRAW, payload={"player": active}))

    if not _game_over(referee):
        turn_state.phase = YGOPhase.MAIN1
        events.append(Event(type=EventType.PHASE_START, payload={"phase": "main1", "player": active}))
        referee.phase = "action"
    return events


def end_turn(referee: CodexYugiohRefereeState) -> list[Event]:
    game = referee.game
    turn_mgr = game.turn_manager
    player_id = referee.player_ids[referee.active_index]
    turn_mgr.ygo_turn_state.phase = YGOPhase.END
    events = turn_mgr._run_end_phase(player_id)
    events.extend(_emit(game, EventType.TURN_END, {"player": player_id}))
    referee.active_index = (referee.active_index + 1) % len(referee.player_ids)
    next_player = referee.player_ids[referee.active_index]
    turn_mgr.ygo_turn_state.active_player_id = next_player
    game.state.active_player = next_player
    turn_mgr.turn_state.active_player_id = next_player
    game.state.priority_player = None
    referee.phase = "need_turn_start"
    return events


def current_packet(referee: CodexYugiohRefereeState) -> dict[str, Any]:
    begin_turn_if_needed(referee)
    if _game_over(referee):
        return {
            "match_id": referee.match_id,
            "seed": referee.seed,
            "game_over": True,
            "winner": _winner(referee),
            "legal_actions": [],
        }
    player_id = referee.player_ids[referee.active_index]
    legal = legal_yugioh_actions(referee.game, player_id)
    return visible_yugioh_packet(
        referee.game,
        player_id,
        legal,
        match_id=referee.match_id,
        seed=referee.seed,
    )


def public_summary(referee: CodexYugiohRefereeState) -> dict[str, Any]:
    game = referee.game
    _sync_losses(referee)
    players = {}
    for pid in referee.player_ids:
        player = game.state.players[pid]
        players[pid] = {
            "deck": referee.deck_ids[pid],
            "lp": getattr(player, "lp", getattr(player, "life", 0)),
            "hand_count": _zone_count(game, f"hand_{pid}"),
            "library_count": _zone_count(game, f"library_{pid}"),
            "monster_count": _zone_count(game, f"monster_zone_{pid}"),
            "spell_trap_count": _zone_count(game, f"spell_trap_zone_{pid}"),
            "graveyard_count": _zone_count(game, f"graveyard_{pid}"),
            "lost": bool(getattr(player, "has_lost", False)),
            "loss_reason": _loss_reason(game, pid),
        }
    return {
        "turn": game.state.turn_number,
        "phase": getattr(game.turn_manager.ygo_turn_state.phase, "value", None),
        "active_player": game.state.active_player,
        "players": players,
        "winner": _winner(referee),
        "game_over": _game_over(referee),
    }


async def apply_action_id(
    referee: CodexYugiohRefereeState,
    action_id: str,
    *,
    rationale: str = "",
    source: str = "fallback",
) -> dict[str, Any]:
    begin_turn_if_needed(referee)
    if _game_over(referee):
        raise RuntimeError("Cannot apply an action to a completed Yu-Gi-Oh! Codex match")

    game = referee.game
    turn_mgr = game.turn_manager
    player_id = referee.player_ids[referee.active_index]
    legal = legal_yugioh_actions(game, player_id)
    packet = visible_yugioh_packet(game, player_id, legal, match_id=referee.match_id, seed=referee.seed)
    validation = validate_yugioh_action(game, player_id, action_id)
    entry: dict[str, Any] = {
        "index": referee.action_index,
        "turn": game.state.turn_number,
        "phase": getattr(turn_mgr.ygo_turn_state.phase, "value", None),
        "player": player_id,
        "deck": referee.deck_ids[player_id],
        "packet_hash": _json_hash(packet),
        "selected_action_id": action_id,
        "source": source,
        "rationale": rationale,
        "validation": validation["ok"],
        "error": validation["error"],
    }
    if not validation["ok"]:
        fallback = next((action for action in legal if action["type"] == "YGO_END_TURN"), legal[-1])
        entry["fallback_action_id"] = fallback["id"]
        validation = {"ok": True, "action": fallback, "error": None}

    action = validation["action"]
    payload = dict(action["payload"])
    action_type = action["type"]
    events: list[Event] = []

    if action_type == "YGO_END_TURN":
        events.extend(end_turn(referee))
    elif action_type == "YGO_ENTER_BATTLE":
        turn_mgr.ygo_turn_state.battle_phase_entered = True
        turn_mgr.ygo_turn_state.phase = YGOPhase.BATTLE_STEP
        events.append(Event(type=EventType.PHASE_START, payload={"phase": "battle_step", "player": player_id}))
    elif action_type == "YGO_END_PHASE":
        turn_mgr.ygo_turn_state.phase = YGOPhase.MAIN2
        events.append(Event(type=EventType.PHASE_START, payload={"phase": "main2", "player": player_id}))
    elif action_type == "YGO_DECLARE_ATTACK":
        opponent_id = next(pid for pid in referee.player_ids if pid != player_id)
        events.extend(turn_mgr._resolve_attack(
            player_id,
            payload["attacker_id"],
            payload.get("target_id"),
            opponent_id,
        ))
    elif action_type in {
        "YGO_NORMAL_SUMMON",
        "YGO_SET_MONSTER",
        "YGO_FLIP_SUMMON",
        "YGO_CHANGE_POSITION",
        "YGO_ACTIVATE_SPELL",
        "YGO_ACTIVATE_TRAP",
        "YGO_SET_SPELL_TRAP",
        "YGO_ACTIVATE_MONSTER_EFFECT",
    }:
        events.extend(turn_mgr._execute_action(player_id, payload))
    else:  # pragma: no cover - legal generator controls action types.
        raise ValueError(f"Unsupported Yu-Gi-Oh! Codex action type: {action_type}")

    _sync_losses(referee)
    entry["action"] = {
        "id": action["id"],
        "type": action["type"],
        "label": action["label"],
        "tags": list(action.get("tags", [])),
    }
    entry["engine_ok"] = action_type in {"YGO_END_TURN", "YGO_ENTER_BATTLE", "YGO_END_PHASE"} or bool(events)
    entry["events"] = [event.type.name for event in events]
    entry["public_summary"] = public_summary(referee)
    referee.transcript.append(entry)
    referee.action_index += 1
    return entry


def choose_fallback_action(packet: dict[str, Any]) -> str:
    """Deterministic fallback that prefers progress over passing."""
    legal = packet["legal_actions"]
    for tag in ("lethal", "attack", "removal", "tempo", "value", "threat", "setup"):
        for action in legal:
            if tag in action.get("tags", []):
                return action["id"]
    return legal[-1]["id"]


def parse_player_json(raw: str, legal_actions: list[dict[str, Any]]) -> tuple[str | None, str, str | None]:
    """Parse a player response. Return (action_id, rationale, error)."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, "", f"Invalid JSON: {exc}"
    action_id = payload.get("action_id")
    if not isinstance(action_id, str):
        return None, str(payload.get("rationale", "")), "Missing string action_id"
    if action_id not in {action["id"] for action in legal_actions}:
        return action_id, str(payload.get("rationale", "")), f"Illegal action_id: {action_id}"
    return action_id, str(payload.get("rationale", "")), None


async def run_fallback_match(
    *,
    p1_deck: str,
    p2_deck: str,
    seed: int,
    max_actions: int,
    match_id: str = "yugioh-codex-smoke",
) -> CodexYugiohRefereeState:
    referee = await initialize_referee(p1_deck=p1_deck, p2_deck=p2_deck, seed=seed, match_id=match_id)
    for _ in range(max_actions):
        if _game_over(referee):
            break
        packet = current_packet(referee)
        if not packet.get("legal_actions"):
            break
        await apply_action_id(referee, choose_fallback_action(packet), rationale="deterministic fallback", source="fallback")
    return referee


def _write_transcript(referee: CodexYugiohRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "hyperdraft.yugioh_codex_match.v1",
        "match_id": referee.match_id,
        "seed": referee.seed,
        "decks": referee.deck_ids,
        "summary": public_summary(referee),
        "transcript": referee.transcript,
    }, indent=2), encoding="utf-8")


def _deck(value: str) -> str:
    _resolve_deck(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yu-Gi-Oh! Codex mirror referee; no model/API calls.")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="Run deterministic fallback smoke match")
    smoke.add_argument("--p1-deck", type=_deck, default="chain_burn")
    smoke.add_argument("--p2-deck", type=_deck, default="kamigawa:ninja")
    smoke.add_argument("--seed", type=int, default=20260510)
    smoke.add_argument("--max-actions", type=int, default=24)
    smoke.add_argument("--out", default="logs/ygo_codex_smoke.json")

    init = sub.add_parser("init", help="Initialize a persisted referee state")
    init.add_argument("--p1-deck", type=_deck, default="chain_burn")
    init.add_argument("--p2-deck", type=_deck, default="kamigawa:ninja")
    init.add_argument("--seed", type=int, default=20260510)
    init.add_argument("--state", required=True)
    init.add_argument("--match-id", default="yugioh-codex-live")

    packet = sub.add_parser("packet", help="Print hidden-info-safe packet for current active seat")
    packet.add_argument("--state", required=True)

    apply = sub.add_parser("apply", help="Apply a validated action id and update state")
    apply.add_argument("--state", required=True)
    apply.add_argument("--action-id", required=True)
    apply.add_argument("--rationale", default="")
    apply.add_argument("--source", default="codex-agent")
    apply.add_argument("--transcript", default="")

    return parser


async def _main_async(args: argparse.Namespace) -> None:
    if args.command == "smoke":
        referee = await run_fallback_match(
            p1_deck=args.p1_deck,
            p2_deck=args.p2_deck,
            seed=args.seed,
            max_actions=args.max_actions,
        )
        _write_transcript(referee, Path(args.out))
        print(json.dumps({"summary": public_summary(referee), "transcript": args.out}, indent=2))
        return
    if args.command == "init":
        referee = await initialize_referee(p1_deck=args.p1_deck, p2_deck=args.p2_deck, seed=args.seed, match_id=args.match_id)
        _save_state(referee, Path(args.state))
        print(json.dumps(public_summary(referee), indent=2))
        return
    if args.command == "packet":
        referee = _load_state(Path(args.state))
        packet = current_packet(referee)
        _save_state(referee, Path(args.state))
        print(json.dumps(packet, indent=2))
        return
    if args.command == "apply":
        referee = _load_state(Path(args.state))
        entry = await apply_action_id(referee, args.action_id, rationale=args.rationale, source=args.source)
        _save_state(referee, Path(args.state))
        if args.transcript:
            _write_transcript(referee, Path(args.transcript))
        print(json.dumps(entry, indent=2))
        return
    raise AssertionError(args.command)


def main() -> None:
    asyncio.run(_main_async(build_parser().parse_args()))


if __name__ == "__main__":
    main()
