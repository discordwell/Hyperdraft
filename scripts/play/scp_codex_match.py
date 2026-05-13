"""Deterministic referee for Codex-supported SCP mirror playtests.

This script contains no model calls. It can run a fallback-only smoke match and
can also initialize/step a pickled referee state for a parent Codex agent that
is orchestrating player subagents outside the repository.
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
from src.engine.turn import Phase, Step
from src.engine.types import Event, EventType
from src.engine import scp
from src.engine.scp_legal_actions import (
    legal_scp_actions,
    validate_scp_action,
    visible_scp_packet,
)

with contextlib.redirect_stdout(sys.stderr):
    from src.cards.scp import SCP_STARTER_DECKS

try:  # cloudpickle handles local card hooks registered as interceptors.
    import cloudpickle as _pickle
except ImportError:  # pragma: no cover - standard pickle still works for simple smoke tests.
    import pickle as _pickle


@dataclass
class CodexSCPRefereeState:
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


async def initialize_referee(
    *,
    p1_deck: str,
    p2_deck: str,
    seed: int,
    match_id: str = "scp-codex",
) -> CodexSCPRefereeState:
    random.seed(seed)
    game = Game(mode="scp")
    p1 = game.add_player("Codex-P1")
    p2 = game.add_player("Codex-P2")
    game.setup_scp_player(p1, SCP_STARTER_DECKS[p1_deck]())
    game.setup_scp_player(p2, SCP_STARTER_DECKS[p2_deck]())
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)
    await game.start_game()
    game.state.active_player = None
    game.state.priority_player = None
    return CodexSCPRefereeState(
        game=game,
        player_ids=[p1.id, p2.id],
        deck_ids={p1.id: p1_deck, p2.id: p2_deck},
        seed=seed,
        match_id=match_id,
    )


def _save_state(referee: CodexSCPRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pickle.dumps(referee))


def _load_state(path: Path) -> CodexSCPRefereeState:
    return _pickle.loads(path.read_bytes())


def _append_system_event(referee: CodexSCPRefereeState, event_type: EventType, payload: dict[str, Any], *, source: str = "SCP_CODEX") -> list[Event]:
    return referee.game.emit(Event(type=event_type, payload=payload, source=source, controller=payload.get("player")))


def begin_turn_if_needed(referee: CodexSCPRefereeState) -> None:
    if referee.phase == "action":
        return
    game = referee.game
    active = referee.player_ids[referee.active_index]
    game.turn_manager.turn_state.active_player_id = active
    game.turn_manager.turn_state.turn_number += 1
    game.turn_manager.turn_state.phase = Phase.BEGINNING
    game.turn_manager.turn_state.step = Step.UNTAP
    game.state.active_player = active
    game.state.priority_player = active
    game.state.turn_number = game.turn_manager.turn_state.turn_number
    scp.ensure_scp_state(game.state, active)
    scp.reset_assignment_slots(game.state, active)
    scp.reset_staff(game, active)
    _append_system_event(referee, EventType.TURN_START, {"player": active, "turn_number": game.state.turn_number})
    scp.process_paperwork(game, active)
    game.draw_cards(active, 1)
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    game.turn_manager.turn_state.step = Step.MAIN
    _append_system_event(referee, EventType.PHASE_START, {"player": active, "phase": "scp_assignment"})
    referee.phase = "action"


def current_packet(referee: CodexSCPRefereeState) -> dict[str, Any]:
    begin_turn_if_needed(referee)
    player_id = referee.player_ids[referee.active_index]
    legal = legal_scp_actions(referee.game, player_id)
    return visible_scp_packet(referee.game, player_id, legal, match_id=referee.match_id, seed=referee.seed)


def public_summary(referee: CodexSCPRefereeState) -> dict[str, Any]:
    game = referee.game
    players = {}
    for pid in referee.player_ids:
        players[pid] = {
            "deck": referee.deck_ids[pid],
            "site": dict(game.state.scp_sites.get(pid, {})),
            "hand_count": _zone_count(game, f"hand_{pid}"),
            "library_count": _zone_count(game, f"library_{pid}"),
            "active_anomalies": len(game.state.scp_anomalies.get(pid, [])),
            "contained": len(game.state.scp_contained.get(pid, [])),
        }
    return {
        "turn": game.state.turn_number,
        "active_player": game.state.active_player,
        "players": players,
        "winner": game.get_winner(),
        "game_over": game.is_game_over(),
    }


async def apply_action_id(referee: CodexSCPRefereeState, action_id: str, *, rationale: str = "", source: str = "fallback") -> dict[str, Any]:
    begin_turn_if_needed(referee)
    game = referee.game
    player_id = referee.player_ids[referee.active_index]
    legal = legal_scp_actions(game, player_id)
    packet = visible_scp_packet(game, player_id, legal, match_id=referee.match_id, seed=referee.seed)
    validation = validate_scp_action(game, player_id, action_id)
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
        fallback = next((action for action in legal if action["type"] == "SCP_END_TURN"), legal[-1])
        entry["fallback_action_id"] = fallback["id"]
        validation = {"ok": True, "action": fallback, "error": None}

    action = validation["action"]
    entry["action"] = {
        "id": action["id"],
        "type": action["type"],
        "label": action["label"],
        "tags": list(action.get("tags", [])),
    }
    if action["type"] == "SCP_END_TURN":
        events = scp.breach_tick(game, player_id)
        _append_system_event(referee, EventType.TURN_END, {"player": player_id, "turn_number": game.state.turn_number})
        game.state.priority_player = None
        referee.active_index = (referee.active_index + 1) % len(referee.player_ids)
        referee.phase = "need_turn_start"
    else:
        ok, message, events = await game.turn_manager.execute_action(player_id, dict(action["payload"]))
        entry["engine_ok"] = ok
        entry["engine_message"] = message
    entry["events"] = [event.type.name for event in events]
    entry["public_summary"] = public_summary(referee)
    referee.transcript.append(entry)
    referee.action_index += 1
    return entry


def choose_fallback_action(packet: dict[str, Any]) -> str:
    """Deterministic fallback that prefers value/stabilization over passing."""
    legal = packet["legal_actions"]
    for tag in ("archive", "stabilize", "resource", "tempo"):
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
    match_id: str = "scp-codex-smoke",
) -> CodexSCPRefereeState:
    referee = await initialize_referee(p1_deck=p1_deck, p2_deck=p2_deck, seed=seed, match_id=match_id)
    for _ in range(max_actions):
        if referee.game.is_game_over():
            break
        packet = current_packet(referee)
        await apply_action_id(referee, choose_fallback_action(packet), rationale="deterministic fallback", source="fallback")
    return referee


def _write_transcript(referee: CodexSCPRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "hyperdraft.scp_codex_match.v1",
        "match_id": referee.match_id,
        "seed": referee.seed,
        "decks": referee.deck_ids,
        "summary": public_summary(referee),
        "transcript": referee.transcript,
    }, indent=2), encoding="utf-8")


def _deck(value: str) -> str:
    if value not in SCP_STARTER_DECKS:
        raise argparse.ArgumentTypeError(f"Unknown SCP deck id: {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SCP Codex mirror referee; no model/API calls.")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="Run deterministic fallback smoke match")
    smoke.add_argument("--p1-deck", type=_deck, default="site_zero_redaction_lock")
    smoke.add_argument("--p2-deck", type=_deck, default="site_zero_quarantine")
    smoke.add_argument("--seed", type=int, default=20260510)
    smoke.add_argument("--max-actions", type=int, default=24)
    smoke.add_argument("--out", default="logs/scp_codex_smoke.json")

    init = sub.add_parser("init", help="Initialize a persisted referee state")
    init.add_argument("--p1-deck", type=_deck, default="site_zero_redaction_lock")
    init.add_argument("--p2-deck", type=_deck, default="site_zero_quarantine")
    init.add_argument("--seed", type=int, default=20260510)
    init.add_argument("--state", required=True)
    init.add_argument("--match-id", default="scp-codex-live")

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
    args = build_parser().parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
