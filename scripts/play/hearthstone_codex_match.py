"""Deterministic referee for Codex-supported Hearthstone mirror playtests.

This script contains no model calls. It can run deterministic fallback smoke
matches and can initialize/step a pickled referee state for a parent Codex
agent that is orchestrating live player subagents outside the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engine.game import Game
from src.engine.hearthstone_legal_actions import (
    apply_hearthstone_action,
    deterministic_hearthstone_fallback,
    legal_hearthstone_actions,
    packet_hash,
    public_hearthstone_summary,
    validate_hearthstone_action,
    visible_hearthstone_packet,
)
from src.engine.hearthstone_turn import HearthstonePhase
from src.engine.types import Event, EventType


try:  # cloudpickle handles local card hooks registered as interceptors.
    import cloudpickle as _pickle
except ImportError:  # pragma: no cover - standard pickle works for simple smoke tests.
    import pickle as _pickle


@dataclass
class CodexHearthstoneRefereeState:
    game: Game
    player_ids: list[str]
    deck_ids: dict[str, str]
    seed: int
    match_id: str
    active_index: int = 0
    phase: str = "need_turn_start"
    action_index: int = 0
    transcript: list[dict[str, Any]] = field(default_factory=list)


def _deck_specs() -> dict[str, dict[str, Any]]:
    with contextlib.redirect_stdout(sys.stderr):
        from src.cards.hearthstone.decks import HEARTHSTONE_DECKS
        from src.cards.hearthstone.heroes import HEROES
        from src.cards.hearthstone.hero_powers import HERO_POWERS
        from src.cards.hearthstone.stormrift import (
            STORMRIFT_DECKS,
            STORMRIFT_HEROES,
            STORMRIFT_HERO_POWERS,
            install_stormrift_modifiers,
        )
        from src.cards.hearthstone.frierenrift import (
            FRIERENRIFT_DECKS,
            FRIERENRIFT_HEROES,
            FRIERENRIFT_HERO_POWERS,
            install_frierenrift_modifiers,
        )
        from src.cards.hearthstone.riftclash import (
            RIFTCLASH_DECKS,
            RIFTCLASH_HEROES,
            RIFTCLASH_HERO_POWERS,
            install_riftclash_modifiers,
        )

    specs: dict[str, dict[str, Any]] = {}
    for hero_class, deck in HEARTHSTONE_DECKS.items():
        specs[hero_class.lower()] = {
            "label": hero_class,
            "deck": deck,
            "hero": HEROES[hero_class],
            "hero_power": HERO_POWERS[hero_class],
            "modifier": None,
        }
    specs.update(
        {
            "stormrift_pyromancer": {
                "label": "Stormrift Pyromancer",
                "deck": STORMRIFT_DECKS["Pyromancer"],
                "hero": STORMRIFT_HEROES["Pyromancer"],
                "hero_power": STORMRIFT_HERO_POWERS["Pyromancer"],
                "modifier": install_stormrift_modifiers,
            },
            "stormrift_cryomancer": {
                "label": "Stormrift Cryomancer",
                "deck": STORMRIFT_DECKS["Cryomancer"],
                "hero": STORMRIFT_HEROES["Cryomancer"],
                "hero_power": STORMRIFT_HERO_POWERS["Cryomancer"],
                "modifier": install_stormrift_modifiers,
            },
            "frieren": {
                "label": "Frierenrift Frieren",
                "deck": FRIERENRIFT_DECKS["Frieren"],
                "hero": FRIERENRIFT_HEROES["Frieren"],
                "hero_power": FRIERENRIFT_HERO_POWERS["Frieren"],
                "modifier": install_frierenrift_modifiers,
            },
            "macht": {
                "label": "Frierenrift Macht",
                "deck": FRIERENRIFT_DECKS["Macht"],
                "hero": FRIERENRIFT_HEROES["Macht"],
                "hero_power": FRIERENRIFT_HERO_POWERS["Macht"],
                "modifier": install_frierenrift_modifiers,
            },
            "riftclash_pyromancer": {
                "label": "Riftclash Pyromancer",
                "deck": RIFTCLASH_DECKS["Pyromancer"],
                "hero": RIFTCLASH_HEROES["Pyromancer"],
                "hero_power": RIFTCLASH_HERO_POWERS["Pyromancer"],
                "modifier": install_riftclash_modifiers,
            },
            "riftclash_cryomancer": {
                "label": "Riftclash Cryomancer",
                "deck": RIFTCLASH_DECKS["Cryomancer"],
                "hero": RIFTCLASH_HEROES["Cryomancer"],
                "hero_power": RIFTCLASH_HERO_POWERS["Cryomancer"],
                "modifier": install_riftclash_modifiers,
            },
        }
    )
    return specs


def _resolve_deck(deck_id: str) -> dict[str, Any]:
    aliases = {
        "stormrift_pyro": "stormrift_pyromancer",
        "stormrift_cryo": "stormrift_cryomancer",
        "frierenrift_frieren": "frieren",
        "frierenrift_macht": "macht",
        "riftclash_pyro": "riftclash_pyromancer",
        "riftclash_cryo": "riftclash_cryomancer",
    }
    key = aliases.get(deck_id.strip().lower(), deck_id.strip().lower())
    specs = _deck_specs()
    if key not in specs:
        raise ValueError(f"Unknown Hearthstone deck id: {deck_id!r}. Available: {', '.join(sorted(specs))}")
    return specs[key]


async def initialize_referee(
    *,
    p1_deck: str,
    p2_deck: str,
    seed: int,
    match_id: str = "hearthstone-codex",
) -> CodexHearthstoneRefereeState:
    random.seed(seed)
    game = Game(mode="hearthstone")
    game.codex_seed = seed
    game.codex_match_id = match_id

    p1 = game.add_player("Codex-P1", life=30)
    p2 = game.add_player("Codex-P2", life=30)
    p1_spec = _resolve_deck(p1_deck)
    p2_spec = _resolve_deck(p2_deck)
    game.setup_hearthstone_player(p1, p1_spec["hero"], p1_spec["hero_power"])
    game.setup_hearthstone_player(p2, p2_spec["hero"], p2_spec["hero_power"])
    game.codex_seats = {p1.id: "P1", p2.id: "P2"}

    modifiers = []
    for modifier in (p1_spec.get("modifier"), p2_spec.get("modifier")):
        if modifier and modifier not in modifiers:
            modifiers.append(modifier)
    for modifier in modifiers:
        modifier(game)

    for card_def in p1_spec["deck"]:
        game.add_card_to_library(p1.id, card_def)
    for card_def in p2_spec["deck"]:
        game.add_card_to_library(p2.id, card_def)
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)
    game.get_mulligan_decision = lambda _pid, _hand, _count: True

    await game.start_game()
    turn_order = list(getattr(game.turn_manager, "turn_order", []) or [p1.id, p2.id])
    game.state.active_player = None
    game.state.priority_player = None
    return CodexHearthstoneRefereeState(
        game=game,
        player_ids=turn_order,
        deck_ids={p1.id: p1_deck, p2.id: p2_deck},
        seed=seed,
        match_id=match_id,
    )


def _save_state(referee: CodexHearthstoneRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pickle.dumps(referee))


def _load_state(path: Path) -> CodexHearthstoneRefereeState:
    return _pickle.loads(path.read_bytes())


def _game_over(referee: CodexHearthstoneRefereeState) -> bool:
    game = referee.game
    if hasattr(game.turn_manager, "_check_state_based_actions"):
        # The async check happens after every applied action; this is just a cheap public check.
        pass
    return game.is_game_over() or any(player.life <= 0 for player in game.state.players.values())


async def begin_turn_if_needed(referee: CodexHearthstoneRefereeState) -> None:
    if referee.phase == "action" or _game_over(referee):
        return
    game = referee.game
    turn_manager = game.turn_manager
    active = referee.player_ids[referee.active_index]
    turn_manager.current_player_index = referee.active_index
    turn_manager.hs_turn_state.active_player_id = active
    game.state.active_player = active
    game.state.priority_player = active
    turn_manager.hs_turn_state.turn_number += 1
    game.state.turn_number = turn_manager.hs_turn_state.turn_number
    turn_manager.turn_state.turn_number = turn_manager.hs_turn_state.turn_number

    await turn_manager._emit_turn_start()
    turn_manager.hs_turn_state.phase = HearthstonePhase.DRAW
    await turn_manager._run_draw_phase()
    if _game_over(referee):
        return
    turn_manager.hs_turn_state.phase = HearthstonePhase.MAIN
    await turn_manager._run_main_phase_start()
    referee.phase = "action"


async def current_packet(referee: CodexHearthstoneRefereeState) -> dict[str, Any]:
    await begin_turn_if_needed(referee)
    if _game_over(referee):
        return {
            "match_id": referee.match_id,
            "seed": referee.seed,
            "game_over": True,
            "winner": referee.game.get_winner(),
            "legal_actions": [],
        }
    player_id = referee.player_ids[referee.active_index]
    legal = legal_hearthstone_actions(referee.game, player_id)
    return visible_hearthstone_packet(referee.game, player_id, legal)


def public_summary(referee: CodexHearthstoneRefereeState) -> dict[str, Any]:
    return public_hearthstone_summary(referee.game)


async def apply_action_id(
    referee: CodexHearthstoneRefereeState,
    action_id: str,
    *,
    rationale: str = "",
    source: str = "codex-agent",
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    await begin_turn_if_needed(referee)
    game = referee.game
    if _game_over(referee):
        raise RuntimeError("Cannot apply an action to a completed Hearthstone Codex match")

    player_id = referee.player_ids[referee.active_index]
    legal = legal_hearthstone_actions(game, player_id)
    packet = visible_hearthstone_packet(game, player_id, legal)
    validation = validate_hearthstone_action(game, player_id, action_id)
    entry: dict[str, Any] = {
        "index": referee.action_index,
        "turn": game.state.turn_number,
        "player": game.codex_seats.get(player_id, player_id),
        "deck": referee.deck_ids[player_id],
        "packet_hash": packet_hash(packet),
        "selected_action_id": action_id,
        "source": source,
        "rationale": rationale,
        "validation": validation["ok"],
        "error": validation["error"],
    }
    if not validation["ok"]:
        fallback = validation["fallback_action"]
        entry["fallback_action_id"] = fallback["id"]
        entry["fallback_reason"] = fallback_reason or validation["error"] or "invalid player output"
        entry["source"] = "deterministic_fallback"
        validation = {"ok": True, "action": fallback, "error": None}
    elif fallback_reason:
        entry["fallback_reason"] = fallback_reason

    action = validation["action"]
    events = await apply_hearthstone_action(game, player_id, action)
    if action["type"] == "HS_END_TURN":
        referee.active_index = (referee.active_index + 1) % len(referee.player_ids)
        referee.phase = "need_turn_start"
        game.state.priority_player = None

    entry["action"] = {
        "id": action["id"],
        "type": action["type"],
        "label": action["label"],
        "tags": list(action.get("tags", [])),
    }
    entry["engine_ok"] = action["type"] == "HS_END_TURN" or bool(events) or action["type"] == "HS_ATTUNE_CARD"
    entry["events"] = [event.type.name for event in events]
    entry["public_summary"] = public_summary(referee)
    referee.transcript.append(entry)
    referee.action_index += 1
    return entry


async def apply_player_json(
    referee: CodexHearthstoneRefereeState,
    raw: str,
    *,
    source: str = "live_codex",
) -> dict[str, Any]:
    packet = await current_packet(referee)
    action_id, rationale, error = parse_player_json(raw, packet.get("legal_actions", []))
    if error:
        fallback = choose_fallback_action(packet)
        return await apply_action_id(
            referee,
            fallback,
            rationale=f"fallback after invalid player output: {error}",
            source="deterministic_fallback",
            fallback_reason=error,
        )
    assert action_id is not None
    return await apply_action_id(referee, action_id, rationale=rationale, source=source)


def choose_fallback_action(packet: dict[str, Any]) -> str:
    """Deterministic fallback that prefers lethal and board progress over passing."""
    legal = packet["legal_actions"]
    for tag in ("lethal", "removal", "damage", "tempo", "resource", "stabilize", "attack"):
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
    match_id: str = "hearthstone-codex-smoke",
) -> CodexHearthstoneRefereeState:
    referee = await initialize_referee(p1_deck=p1_deck, p2_deck=p2_deck, seed=seed, match_id=match_id)
    for _ in range(max_actions):
        if _game_over(referee):
            break
        packet = await current_packet(referee)
        if not packet.get("legal_actions"):
            break
        action_id = choose_fallback_action(packet)
        await apply_action_id(
            referee,
            action_id,
            rationale="deterministic fallback smoke",
            source="deterministic_fallback",
        )
    return referee


def _decision_counts(referee: CodexHearthstoneRefereeState) -> dict[str, int]:
    counts = {"live_codex": 0, "deterministic_fallback": 0, "invalid_repair": 0}
    for entry in referee.transcript:
        source = entry.get("source")
        if source in counts:
            counts[source] += 1
        if entry.get("fallback_action_id"):
            counts["invalid_repair"] += 1
    return counts


def _write_transcript(referee: CodexHearthstoneRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "hyperdraft.hearthstone_codex_match.v1",
                "match_id": referee.match_id,
                "seed": referee.seed,
                "decks": referee.deck_ids,
                "decision_counts": _decision_counts(referee),
                "summary": public_summary(referee),
                "transcript": referee.transcript,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _deck(value: str) -> str:
    _resolve_deck(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hearthstone Codex mirror referee; no model/API calls.")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="Run deterministic fallback smoke match")
    smoke.add_argument("--p1-deck", type=_deck, default="stormrift_pyromancer")
    smoke.add_argument("--p2-deck", type=_deck, default="stormrift_cryomancer")
    smoke.add_argument("--seed", type=int, default=20260510)
    smoke.add_argument("--max-actions", type=int, default=24)
    smoke.add_argument("--out", default="logs/hearthstone_codex_smoke.json")
    smoke.add_argument("--match-id", default="hearthstone-codex-smoke")

    init = sub.add_parser("init", help="Initialize a persisted referee state")
    init.add_argument("--p1-deck", type=_deck, default="stormrift_pyromancer")
    init.add_argument("--p2-deck", type=_deck, default="stormrift_cryomancer")
    init.add_argument("--seed", type=int, default=20260510)
    init.add_argument("--state", required=True)
    init.add_argument("--match-id", default="hearthstone-codex-live")

    packet = sub.add_parser("packet", help="Print hidden-info-safe packet for current active seat")
    packet.add_argument("--state", required=True)

    apply = sub.add_parser("apply", help="Apply a validated action id and update state")
    apply.add_argument("--state", required=True)
    apply.add_argument("--action-id", required=True)
    apply.add_argument("--rationale", default="")
    apply.add_argument("--source", default="live_codex")
    apply.add_argument("--transcript", default="")

    response = sub.add_parser("response", help="Apply a raw JSON player response and update state")
    response.add_argument("--state", required=True)
    response.add_argument("--json", required=True)
    response.add_argument("--source", default="live_codex")
    response.add_argument("--transcript", default="")

    return parser


async def _main_async(args: argparse.Namespace) -> None:
    if args.command == "smoke":
        referee = await run_fallback_match(
            p1_deck=args.p1_deck,
            p2_deck=args.p2_deck,
            seed=args.seed,
            max_actions=args.max_actions,
            match_id=args.match_id,
        )
        _write_transcript(referee, Path(args.out))
        print(json.dumps({"summary": public_summary(referee), "decision_counts": _decision_counts(referee), "transcript": args.out}, indent=2))
        return
    if args.command == "init":
        referee = await initialize_referee(p1_deck=args.p1_deck, p2_deck=args.p2_deck, seed=args.seed, match_id=args.match_id)
        _save_state(referee, Path(args.state))
        print(json.dumps(public_summary(referee), indent=2))
        return
    if args.command == "packet":
        referee = _load_state(Path(args.state))
        packet = await current_packet(referee)
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
    if args.command == "response":
        referee = _load_state(Path(args.state))
        entry = await apply_player_json(referee, args.json, source=args.source)
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
