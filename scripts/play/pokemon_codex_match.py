"""Deterministic referee for Codex-supported Pokemon mirror playtests.

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
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.engine.game import Game
from src.engine.types import Event, EventType
from src.engine.pokemon_legal_actions import (
    legal_pokemon_actions,
    validate_pokemon_action,
    visible_pokemon_packet,
)
from src.engine.pokemon_turn import PokemonPhase

with contextlib.redirect_stdout(sys.stderr):
    from src.cards.pokemon.deck_builder import (
        build_sv_starter_deck,
        list_sv_starter_decks,
    )
    from src.cards.pokemon.beyond.ravnica.deck_builder import (
        build_ravnica_guild_deck,
        list_ravnica_guild_decks,
    )

try:  # cloudpickle handles local card hooks registered as interceptors.
    import cloudpickle as _pickle
except ImportError:  # pragma: no cover - standard pickle works for simple smoke tests.
    import pickle as _pickle


@dataclass
class CodexPokemonRefereeState:
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


def _resolve_deck(deck_id: str) -> list:
    name = deck_id.strip().lower()
    starters = set(list_sv_starter_decks())
    guilds = set(list_ravnica_guild_decks())
    if name.startswith("svs:"):
        name = name.split(":", 1)[1]
        deck, _strategy = build_sv_starter_deck(name, enforce_quality=False)
        return deck
    if name.startswith("brv:"):
        name = name.split(":", 1)[1]
        deck, _strategy = build_ravnica_guild_deck(name, enforce_balance=False)
        return deck
    if name in starters:
        deck, _strategy = build_sv_starter_deck(name, enforce_quality=False)
        return deck
    if name in guilds:
        deck, _strategy = build_ravnica_guild_deck(name, enforce_balance=False)
        return deck
    available = sorted([f"svs:{n}" for n in starters] + [f"brv:{g}" for g in guilds])
    raise ValueError(f"Unknown Pokemon deck id: {deck_id!r}. Available: {available}")


async def initialize_referee(
    *,
    p1_deck: str,
    p2_deck: str,
    seed: int,
    match_id: str = "pokemon-codex",
) -> CodexPokemonRefereeState:
    random.seed(seed)
    game = Game(mode="pokemon")
    p1 = game.add_player("Codex-P1")
    p2 = game.add_player("Codex-P2")
    game.setup_pokemon_player(p1, _resolve_deck(p1_deck))
    game.setup_pokemon_player(p2, _resolve_deck(p2_deck))

    await game.turn_manager.setup_game()
    turn_order = list(getattr(game.turn_manager, "turn_order", []) or [p1.id, p2.id])
    game.state.active_player = None
    game.state.priority_player = None
    return CodexPokemonRefereeState(
        game=game,
        player_ids=turn_order,
        deck_ids={p1.id: p1_deck, p2.id: p2_deck},
        seed=seed,
        match_id=match_id,
    )


def _save_state(referee: CodexPokemonRefereeState, path: Path) -> None:
    """Atomic write — fixes the v2-iter3 race condition where parallel pilots
    truncated the pickle to 0 bytes. Write to a tempfile alongside the
    target, then ``os.replace`` (POSIX atomic rename within same dir)."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _pickle.dumps(referee)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_state(path: Path) -> CodexPokemonRefereeState:
    return _pickle.loads(path.read_bytes())


def _emit(game: Game, event_type: EventType, payload: dict[str, Any], *, source: str = "PKM_CODEX") -> list[Event]:
    return game.emit(Event(type=event_type, payload=payload, source=source, controller=payload.get("player")))


def _winner(referee: CodexPokemonRefereeState) -> str | None:
    turn_mgr = referee.game.turn_manager
    if hasattr(turn_mgr, "check_win_conditions"):
        winner = turn_mgr.check_win_conditions()
        if winner:
            return winner
    return referee.game.get_winner()


def _game_over(referee: CodexPokemonRefereeState) -> bool:
    return _winner(referee) is not None or referee.game.is_game_over()


def _loss_reason(game: Game, player_id: str) -> str:
    player = game.state.players[player_id]
    if getattr(player, "prizes_remaining", 6) == 0:
        return "prizes_taken"
    if not getattr(player, "has_lost", False):
        return "not_lost"
    library = game.state.zones.get(f"library_{player_id}")
    active = game.state.zones.get(f"active_spot_{player_id}")
    bench = game.state.zones.get(f"bench_{player_id}")
    if library is not None and not library.objects:
        return "deck_out"
    if (active is None or not active.objects) and (bench is None or not bench.objects):
        return "no_pokemon"
    return "unknown_loss"


def begin_turn_if_needed(referee: CodexPokemonRefereeState) -> None:
    if referee.phase == "action" or _game_over(referee):
        return
    game = referee.game
    turn_mgr = game.turn_manager
    active = referee.player_ids[referee.active_index]
    turn_mgr.pkm_turn_state.active_player_id = active
    turn_mgr.current_player_index = referee.active_index
    turn_mgr.pkm_turn_state.turn_number += 1
    turn_mgr.pkm_turn_state.game_turn_count += 1
    turn_mgr.pkm_turn_state.phase = PokemonPhase.DRAW
    game.state.active_player = active
    game.state.priority_player = active
    game.state.turn_number = turn_mgr.pkm_turn_state.turn_number
    turn_mgr.turn_state.turn_number = turn_mgr.pkm_turn_state.turn_number
    turn_mgr._reset_turn_flags(active)
    _emit(game, EventType.TURN_START, {
        "player": active,
        "turn_number": game.state.turn_number,
    })
    if not (
        turn_mgr.pkm_turn_state.game_turn_count == 1
        and active == turn_mgr.pkm_turn_state.first_player_id
    ):
        game.draw_cards(active, 1)
    turn_mgr.pkm_turn_state.phase = PokemonPhase.MAIN
    referee.phase = "action"


def end_turn(referee: CodexPokemonRefereeState) -> list[Event]:
    game = referee.game
    turn_mgr = game.turn_manager
    player_id = referee.player_ids[referee.active_index]
    events: list[Event] = []
    if not _game_over(referee):
        turn_mgr.pkm_turn_state.phase = PokemonPhase.CHECKUP
        events.extend(turn_mgr._run_checkup())
        events.extend(turn_mgr._check_pokemon_knockouts())
    if not _game_over(referee):
        events.extend(_emit(game, EventType.TURN_END, {
            "player": player_id,
            "turn_number": game.state.turn_number,
        }))
    referee.active_index = (referee.active_index + 1) % len(referee.player_ids)
    referee.phase = "need_turn_start"
    game.state.priority_player = None
    return events


def current_packet(referee: CodexPokemonRefereeState) -> dict[str, Any]:
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
    legal = legal_pokemon_actions(referee.game, player_id)
    return visible_pokemon_packet(
        referee.game,
        player_id,
        legal,
        match_id=referee.match_id,
        seed=referee.seed,
    )


def public_summary(referee: CodexPokemonRefereeState) -> dict[str, Any]:
    game = referee.game
    players = {}
    for pid in referee.player_ids:
        player = game.state.players[pid]
        players[pid] = {
            "deck": referee.deck_ids[pid],
            "prizes_remaining": getattr(player, "prizes_remaining", 6),
            "hand_count": _zone_count(game, f"hand_{pid}"),
            "library_count": _zone_count(game, f"library_{pid}"),
            "bench_count": _zone_count(game, f"bench_{pid}"),
            "active_count": _zone_count(game, f"active_spot_{pid}"),
            "lost": bool(getattr(player, "has_lost", False)),
            "loss_reason": _loss_reason(game, pid),
        }
    return {
        "turn": game.state.turn_number,
        "active_player": game.state.active_player,
        "players": players,
        "winner": _winner(referee),
        "game_over": _game_over(referee),
    }


async def apply_action_id(
    referee: CodexPokemonRefereeState,
    action_id: str,
    *,
    rationale: str = "",
    source: str = "fallback",
) -> dict[str, Any]:
    begin_turn_if_needed(referee)
    game = referee.game
    if _game_over(referee):
        raise RuntimeError("Cannot apply an action to a completed Pokemon Codex match")

    player_id = referee.player_ids[referee.active_index]
    legal = legal_pokemon_actions(game, player_id)
    packet = visible_pokemon_packet(game, player_id, legal, match_id=referee.match_id, seed=referee.seed)
    validation = validate_pokemon_action(game, player_id, action_id)
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
        fallback = next((action for action in legal if action["type"] == "PKM_END_TURN"), legal[-1])
        entry["fallback_action_id"] = fallback["id"]
        validation = {"ok": True, "action": fallback, "error": None}

    action = validation["action"]
    payload = dict(action["payload"])
    action_type = action["type"]
    turn_mgr = game.turn_manager
    events: list[Event] = []

    if action_type == "PKM_END_TURN":
        events.extend(end_turn(referee))
    elif action_type == "PKM_ATTACK":
        events.extend(await turn_mgr._execute_attack(
            player_id,
            int(payload.get("attack_index", 0)),
            list(payload.get("targets", [])),
        ))
        events.extend(end_turn(referee))
    elif action_type == "PKM_PLAY_BASIC":
        events.extend(turn_mgr._play_basic(player_id, payload["card_id"]))
        events.extend(turn_mgr._check_pokemon_knockouts())
    elif action_type == "PKM_EVOLVE":
        events.extend(turn_mgr.evolve_pokemon(payload["target_id"], payload["card_id"]))
        events.extend(turn_mgr._check_pokemon_knockouts())
    elif action_type == "PKM_ATTACH_ENERGY":
        events.extend(turn_mgr._attach_energy(player_id, payload["energy_id"], payload["target_id"]))
        events.extend(turn_mgr._check_pokemon_knockouts())
    elif action_type == "PKM_PLAY_ITEM":
        events.extend(turn_mgr._play_trainer(player_id, payload["card_id"], "item"))
        events.extend(turn_mgr._check_pokemon_knockouts())
    elif action_type == "PKM_PLAY_SUPPORTER":
        events.extend(turn_mgr._play_trainer(player_id, payload["card_id"], "supporter"))
        events.extend(turn_mgr._check_pokemon_knockouts())
    elif action_type == "PKM_PLAY_STADIUM":
        events.extend(turn_mgr._play_trainer(player_id, payload["card_id"], "stadium"))
        events.extend(turn_mgr._check_pokemon_knockouts())
    elif action_type == "PKM_RETREAT":
        events.extend(turn_mgr._retreat(player_id, payload["bench_pokemon_id"]))
        events.extend(turn_mgr._check_pokemon_knockouts())
    elif action_type == "PKM_USE_ABILITY":
        events.extend(turn_mgr._use_ability(player_id, payload["pokemon_id"]))
        pokemon = game.state.objects.get(payload["pokemon_id"])
        if pokemon:
            pokemon.state.ability_used_this_turn = True
        events.extend(turn_mgr._check_pokemon_knockouts())
    else:  # pragma: no cover - legal generator controls action types.
        raise ValueError(f"Unsupported Pokemon Codex action type: {action_type}")

    entry["action"] = {
        "id": action["id"],
        "type": action["type"],
        "label": action["label"],
        "tags": list(action.get("tags", [])),
    }
    entry["engine_ok"] = action_type == "PKM_END_TURN" or bool(events)
    entry["events"] = [event.type.name for event in events]
    entry["public_summary"] = public_summary(referee)
    referee.transcript.append(entry)
    referee.action_index += 1
    return entry


def choose_fallback_action(packet: dict[str, Any]) -> str:
    """Deterministic fallback that prefers progress over passing."""
    legal = packet["legal_actions"]
    for tag in ("lethal", "resource", "setup", "value", "tempo", "attack"):
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
    match_id: str = "pokemon-codex-smoke",
) -> CodexPokemonRefereeState:
    referee = await initialize_referee(p1_deck=p1_deck, p2_deck=p2_deck, seed=seed, match_id=match_id)
    for _ in range(max_actions):
        if _game_over(referee):
            break
        packet = current_packet(referee)
        if not packet.get("legal_actions"):
            break
        await apply_action_id(referee, choose_fallback_action(packet), rationale="deterministic fallback", source="fallback")
    return referee


def _write_transcript(referee: CodexPokemonRefereeState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "hyperdraft.pokemon_codex_match.v1",
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
    parser = argparse.ArgumentParser(description="Pokemon Codex mirror referee; no model/API calls.")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="Run deterministic fallback smoke match")
    smoke.add_argument("--p1-deck", type=_deck, default="svs:fire")
    smoke.add_argument("--p2-deck", type=_deck, default="svs:water")
    smoke.add_argument("--seed", type=int, default=20260510)
    smoke.add_argument("--max-actions", type=int, default=24)
    smoke.add_argument("--out", default="logs/pokemon_codex_smoke.json")

    init = sub.add_parser("init", help="Initialize a persisted referee state")
    init.add_argument("--p1-deck", type=_deck, default="svs:fire")
    init.add_argument("--p2-deck", type=_deck, default="svs:water")
    init.add_argument("--seed", type=int, default=20260510)
    init.add_argument("--state", required=True)
    init.add_argument("--match-id", default="pokemon-codex-live")

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
        # packet is read-only; v2-iter3 race condition was partly caused by
        # this being a no-op write that still raced apply's write window.
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
