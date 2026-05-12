"""Deterministic referee for Codex-supported MTG mirror playtests.

This script contains no model calls. It can run a fallback-only smoke match and
can initialize/step a pickled referee state for a parent Codex agent that is
orchestrating player subagents outside the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.combat import AttackDeclaration, BlockDeclaration
from src.engine.game import Game
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase, Step
from src.engine.types import CardDefinition, CardType, Event, EventType
from src.engine.mtg_legal_actions import (
    legal_mtg_actions,
    validate_mtg_action,
    visible_mtg_packet,
)

try:  # cloudpickle handles local card hooks registered as interceptors.
    import cloudpickle as _pickle
except ImportError:  # pragma: no cover - standard pickle works for simple smoke tests.
    import pickle as _pickle


@dataclass
class CodexMTGRefereeState:
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
    return len(zone.objects) if zone else 0


def _save_state(referee: CodexMTGRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pickle.dumps(referee))


def _load_state(path: Path) -> CodexMTGRefereeState:
    return _pickle.loads(path.read_bytes())


def _emit(game: Game, event_type: EventType, payload: dict[str, Any], *, source: str = "MTG_CODEX") -> list[Event]:
    return game.emit(Event(type=event_type, payload=payload, source=source, controller=payload.get("player")))


def _winner(referee: CodexMTGRefereeState) -> str | None:
    return referee.game.get_winner()


def _game_over(referee: CodexMTGRefereeState) -> bool:
    return referee.game.is_game_over()


def _deck_from_custom_set(set_code: str, focal: str | None, *, synergy: bool) -> tuple[list[CardDefinition], str]:
    from src.cards.custom import CUSTOM_SETS
    from scripts.play.capability_test import _load_synergy_registry, build_synergy_deck
    from scripts.play.custom_set_tournament import build_set_deck

    set_code = set_code.upper()
    if set_code not in CUSTOM_SETS:
        raise ValueError(f"Unknown custom set '{set_code}'. Available: {sorted(CUSTOM_SETS)}")
    cards = CUSTOM_SETS[set_code]
    if synergy:
        if not focal:
            raise ValueError("A focal card is required for a synergy deck")
        registry = _load_synergy_registry(set_code)
        if focal not in registry:
            raise ValueError(f"Focal {focal!r} missing from {set_code} synergy registry")
        return build_synergy_deck(focal, registry[focal], cards), f"{set_code}:synergy:{focal}"
    deck, _info = build_set_deck(set_code, cards)
    return deck, f"{set_code}:baseline"


async def initialize_referee_from_decks(
    *,
    p1_deck: list[CardDefinition],
    p2_deck: list[CardDefinition],
    p1_deck_id: str,
    p2_deck_id: str,
    seed: int,
    match_id: str = "mtg-codex",
) -> CodexMTGRefereeState:
    random.seed(seed)
    game = Game()
    p1 = game.add_player("Codex-P1")
    p2 = game.add_player("Codex-P2")
    for card_def in p1_deck:
        game.add_card_to_library(p1.id, card_def)
    for card_def in p2_deck:
        game.add_card_to_library(p2.id, card_def)
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)
    game.set_mulligan_handler(lambda _pid, _hand, _count: True)
    await game.start_game()
    turn_order = list(getattr(game.turn_manager, "turn_order", []) or [p1.id, p2.id])
    game.state.active_player = None
    game.state.priority_player = None
    return CodexMTGRefereeState(
        game=game,
        player_ids=turn_order,
        deck_ids={p1.id: p1_deck_id, p2.id: p2_deck_id},
        seed=seed,
        match_id=match_id,
    )


async def initialize_referee(
    *,
    set_code: str,
    focal: str,
    seed: int,
    match_id: str = "mtg-codex",
) -> CodexMTGRefereeState:
    p1_deck, p1_id = _deck_from_custom_set(set_code, focal, synergy=True)
    p2_deck, p2_id = _deck_from_custom_set(set_code, focal, synergy=False)
    return await initialize_referee_from_decks(
        p1_deck=p1_deck,
        p2_deck=p2_deck,
        p1_deck_id=p1_id,
        p2_deck_id=p2_id,
        seed=seed,
        match_id=match_id,
    )


def _auto_choice_fallback(game: Game) -> list[Event]:
    events: list[Event] = []
    guard = 0
    while game.state.pending_choice is not None and guard < 20:
        guard += 1
        choice = game.state.pending_choice
        selected: list[Any] = []
        min_choices = max(1, choice.min_choices or 1)
        for opt in (choice.options or [])[:min_choices]:
            if isinstance(opt, dict):
                if opt.get("id") is not None:
                    selected.append(opt["id"])
                elif opt.get("index") is not None:
                    selected.append(opt["index"])
                else:
                    selected.append(opt)
            else:
                selected.append(opt)
        ok, _message, produced = game.submit_choice(choice.id, choice.player, selected)
        if not ok:
            game.state.pending_choice = None
            break
        events.extend(produced)
    return events


def begin_turn_if_needed(referee: CodexMTGRefereeState) -> None:
    if referee.phase == "action" or _game_over(referee):
        return
    game = referee.game
    turn_mgr = game.turn_manager
    active = referee.player_ids[referee.active_index]
    turn_mgr.turn_state.active_player_id = active
    turn_mgr.current_player_index = referee.active_index
    turn_mgr.turn_state.turn_number += 1
    game.state.turn_number = turn_mgr.turn_state.turn_number
    turn_mgr._reset_turn_state()
    game.state.active_player = active
    game.state.priority_player = active
    turn_mgr.turn_state.phase = Phase.PRECOMBAT_MAIN
    turn_mgr.turn_state.step = Step.MAIN
    _emit(game, EventType.TURN_START, {
        "player": active,
        "turn_number": game.state.turn_number,
    })
    skip_first_player_draw = (
        not getattr(game.state, "first_player_draws", False)
        and game.state.turn_number == 1
        and referee.active_index == 0
    )
    if not skip_first_player_draw:
        game.draw_cards(active, 1)
    _emit(game, EventType.PHASE_START, {
        "phase": "precombat_main",
        "step": "main",
        "active_player": active,
        "turn_number": game.state.turn_number,
    })
    game.priority_system.priority_player = active
    game.priority_system.passed_players.clear()
    referee.phase = "action"


async def end_turn(referee: CodexMTGRefereeState) -> list[Event]:
    game = referee.game
    player_id = referee.player_ids[referee.active_index]
    events: list[Event] = []
    if not _game_over(referee):
        events.extend(await game.turn_manager._do_cleanup_step())
        events.extend(_emit(game, EventType.TURN_END, {
            "player": player_id,
            "turn_number": game.state.turn_number,
        }))
    referee.active_index = (referee.active_index + 1) % len(referee.player_ids)
    referee.phase = "need_turn_start"
    game.state.priority_player = None
    game.priority_system.priority_player = None
    game.priority_system.passed_players.clear()
    return events


def current_packet(referee: CodexMTGRefereeState) -> dict[str, Any]:
    begin_turn_if_needed(referee)
    _auto_choice_fallback(referee.game)
    if _game_over(referee):
        return {
            "match_id": referee.match_id,
            "seed": referee.seed,
            "game_over": True,
            "winner": _winner(referee),
            "legal_actions": [],
        }
    player_id = referee.game.priority_system.priority_player or referee.player_ids[referee.active_index]
    legal = legal_mtg_actions(referee.game, player_id)
    return visible_mtg_packet(
        referee.game,
        player_id,
        legal,
        match_id=referee.match_id,
        seed=referee.seed,
    )


def public_summary(referee: CodexMTGRefereeState) -> dict[str, Any]:
    game = referee.game
    players = {}
    for pid in referee.player_ids:
        player = game.state.players[pid]
        players[pid] = {
            "deck": referee.deck_ids[pid],
            "life": player.life,
            "hand_count": _zone_count(game, f"hand_{pid}"),
            "library_count": _zone_count(game, f"library_{pid}"),
            "graveyard_count": _zone_count(game, f"graveyard_{pid}"),
            "lost": bool(player.has_lost),
        }
    return {
        "turn": game.state.turn_number,
        "active_player": game.state.active_player,
        "priority_player": game.priority_system.priority_player,
        "players": players,
        "winner": _winner(referee),
        "game_over": _game_over(referee),
        "stack_size": len(getattr(game.stack, "items", []) or []),
        "battlefield_count": _zone_count(game, "battlefield"),
    }


def _player_action_from_payload(player_id: str, payload: dict[str, Any]) -> PlayerAction:
    action_type = ActionType[payload["action_type"]]
    return PlayerAction(
        type=action_type,
        player_id=player_id,
        card_id=payload.get("card_id"),
        ability_id=payload.get("ability_id"),
        source_id=payload.get("source_id"),
        x_value=int(payload.get("x_value", 0) or 0),
        modes=list(payload.get("modes", []) or []),
        targets=list(payload.get("targets", []) or []),
        data={"crew_with": list(payload.get("crew_with", []) or [])},
    )


async def _apply_pass(referee: CodexMTGRefereeState, player_id: str) -> list[Event]:
    game = referee.game
    priority = game.priority_system
    priority.passed_players.add(player_id)
    if len(priority.passed_players) < len(referee.player_ids):
        current_index = referee.player_ids.index(player_id)
        next_player = referee.player_ids[(current_index + 1) % len(referee.player_ids)]
        priority.priority_player = next_player
        game.state.priority_player = next_player
        return []

    priority.passed_players.clear()
    if game.stack and not game.stack.is_empty():
        events = game.stack.resolve_top()
        processed: list[Event] = []
        for event in events:
            processed.extend(game.emit(event))
        active = referee.player_ids[referee.active_index]
        priority.priority_player = active
        game.state.priority_player = active
        return processed
    return await end_turn(referee)


async def apply_action_id(
    referee: CodexMTGRefereeState,
    action_id: str,
    *,
    rationale: str = "",
    source: str = "fallback",
) -> dict[str, Any]:
    begin_turn_if_needed(referee)
    game = referee.game
    if _game_over(referee):
        raise RuntimeError("Cannot apply an action to a completed MTG Codex match")

    player_id = game.priority_system.priority_player or referee.player_ids[referee.active_index]
    legal = legal_mtg_actions(game, player_id)
    packet = visible_mtg_packet(game, player_id, legal, match_id=referee.match_id, seed=referee.seed)
    validation = validate_mtg_action(game, player_id, action_id)
    entry: dict[str, Any] = {
        "index": referee.action_index,
        "turn": game.state.turn_number,
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
        fallback = next((action for action in legal if action["type"] == "MTG_PASS"), legal[-1])
        entry["fallback_action_id"] = fallback["id"]
        validation = {"ok": True, "action": fallback, "error": None}

    action = validation["action"]
    events: list[Event] = []
    if action["type"] == "MTG_PASS":
        events.extend(await _apply_pass(referee, player_id))
    else:
        player_action = _player_action_from_payload(player_id, action["payload"])
        events.extend(await game.priority_system._execute_action(player_action))
        events.extend(_auto_choice_fallback(game))
        game.check_state_based_actions()
        game.priority_system.passed_players.clear()
        game.priority_system.priority_player = player_id
        game.state.priority_player = player_id

    entry["action"] = {
        "id": action["id"],
        "type": action["type"],
        "label": action["label"],
        "tags": list(action.get("tags", [])),
    }
    entry["engine_ok"] = action["type"] == "MTG_PASS" or bool(events)
    entry["events"] = [event.type.name for event in events]
    entry["public_summary"] = public_summary(referee)
    referee.transcript.append(entry)
    referee.action_index += 1
    return entry


def choose_fallback_action(packet: dict[str, Any]) -> str:
    """Deterministic fallback that prefers progress over passing."""
    legal = packet["legal_actions"]
    for tag in ("lethal", "resource", "threat", "tempo", "interaction", "card_advantage", "value"):
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


async def run_fallback_match_from_decks(
    *,
    p1_deck: list[CardDefinition],
    p2_deck: list[CardDefinition],
    p1_deck_id: str,
    p2_deck_id: str,
    seed: int,
    max_actions: int,
    match_id: str = "mtg-codex-smoke",
) -> CodexMTGRefereeState:
    referee = await initialize_referee_from_decks(
        p1_deck=p1_deck,
        p2_deck=p2_deck,
        p1_deck_id=p1_deck_id,
        p2_deck_id=p2_deck_id,
        seed=seed,
        match_id=match_id,
    )
    for _ in range(max_actions):
        if _game_over(referee):
            break
        packet = current_packet(referee)
        if not packet.get("legal_actions"):
            break
        await apply_action_id(referee, choose_fallback_action(packet), rationale="deterministic fallback", source="fallback")
    return referee


async def run_fallback_match(
    *,
    set_code: str,
    focal: str,
    seed: int,
    max_actions: int,
    match_id: str = "mtg-codex-smoke",
) -> CodexMTGRefereeState:
    referee = await initialize_referee(set_code=set_code, focal=focal, seed=seed, match_id=match_id)
    for _ in range(max_actions):
        if _game_over(referee):
            break
        packet = current_packet(referee)
        if not packet.get("legal_actions"):
            break
        await apply_action_id(referee, choose_fallback_action(packet), rationale="deterministic fallback", source="fallback")
    return referee


def _write_transcript(referee: CodexMTGRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "hyperdraft.mtg_codex_match.v1",
        "match_id": referee.match_id,
        "seed": referee.seed,
        "decks": referee.deck_ids,
        "validation_mode": "deterministic_fallback",
        "live_subagents_used": False,
        "fallback_actions": len(referee.transcript),
        "summary": public_summary(referee),
        "transcript": referee.transcript,
    }, indent=2), encoding="utf-8")


def write_transcript(referee: CodexMTGRefereeState, path: Path) -> None:
    """Public wrapper used by spice-loop orchestration."""
    _write_transcript(referee, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MTG Codex mirror referee; no model/API calls.")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="Run deterministic fallback smoke match")
    smoke.add_argument("--set", default="PKH")
    smoke.add_argument("--focal", default="Pikachu, Thunder Champion")
    smoke.add_argument("--seed", type=int, default=20260510)
    smoke.add_argument("--max-actions", type=int, default=12)
    smoke.add_argument("--out", default="logs/mtg_codex_smoke.json")

    init = sub.add_parser("init", help="Initialize a persisted referee state")
    init.add_argument("--set", default="PKH")
    init.add_argument("--focal", default="Pikachu, Thunder Champion")
    init.add_argument("--seed", type=int, default=20260510)
    init.add_argument("--state", required=True)
    init.add_argument("--match-id", default="mtg-codex-live")

    packet = sub.add_parser("packet", help="Print hidden-info-safe packet for current priority seat")
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
            set_code=args.set,
            focal=args.focal,
            seed=args.seed,
            max_actions=args.max_actions,
        )
        _write_transcript(referee, Path(args.out))
        print(json.dumps({"summary": public_summary(referee), "transcript": args.out}, indent=2))
        return
    if args.command == "init":
        referee = await initialize_referee(set_code=args.set, focal=args.focal, seed=args.seed, match_id=args.match_id)
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
    raise ValueError(f"Unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(_main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
