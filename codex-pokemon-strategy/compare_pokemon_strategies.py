#!/usr/bin/env python3
"""Focused Pokemon strategy comparison harness.

Compares the promoted extra-hard Pokemon profile against the main Pokemon
baseline on same-deck mirrors, alternating play/draw seating. The public
difficulties remain ``easy``, ``medium``, ``hard``, and ``ultra``; this harness
defaults to ``ultra`` versus ``medium``. This is intentionally separate from the
full test suite.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.pokemon_adapter import PokemonAIAdapter  # noqa: E402
from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS  # noqa: E402
from src.engine.game import Game  # noqa: E402
from src.engine.types import Event, EventType, ZoneType  # noqa: E402


DEFAULT_DECKS = "boros,izzet,gruul,orzhov,simic"
DEFAULT_SEEDS = "20260502,20260503,20260504,20260505"

COUNTED_EVENTS = {
    EventType.PKM_ATTACK_DECLARE: "attacks",
    EventType.PKM_ATTACH_ENERGY: "energy_attached",
    EventType.PKM_PLAY_ITEM: "items_played",
    EventType.PKM_PLAY_SUPPORTER: "supporters_played",
    EventType.PKM_PLAY_STADIUM: "stadiums_played",
    EventType.PKM_PLAY_BASIC: "basics_played",
    EventType.PKM_EVOLVE: "evolutions",
    EventType.PKM_RETREAT: "retreats",
    EventType.PKM_TAKE_PRIZE: "prizes_taken",
}


def _other_role(role: str | None) -> str | None:
    if role == "codex":
        return "baseline"
    if role == "baseline":
        return "codex"
    return None


def _parse_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_int_csv(value: str) -> list[int]:
    return [int(part) for part in _parse_csv(value)]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _event_player(event: Event, game: Game) -> str | None:
    payload = event.payload or {}
    player = payload.get("player") or event.controller
    if player:
        return player
    source = event.source
    obj = game.state.objects.get(source) if source else None
    if obj:
        return obj.controller or obj.owner
    return None


def _collect_event_metrics(events: list[Event], game: Game,
                           role_by_player: dict[str, str]) -> dict[str, Counter]:
    metrics = {"codex": Counter(), "baseline": Counter()}
    for event in events:
        if event.type == EventType.PKM_PLACE_DAMAGE_COUNTERS:
            damaged_id = (event.payload or {}).get("pokemon_id")
            damaged = game.state.objects.get(damaged_id) if damaged_id else None
            damaged_role = role_by_player.get(
                (damaged.controller or damaged.owner) if damaged else "")
            dealt_role = _other_role(damaged_role)
            counters = int((event.payload or {}).get("count", 0) or 0)
            if damaged_role in metrics:
                metrics[damaged_role]["damage_counters_taken"] += counters
            if dealt_role in metrics:
                metrics[dealt_role]["damage_counters_dealt"] += counters
            continue

        if event.type == EventType.PKM_KNOCKOUT:
            owner = (event.payload or {}).get("owner")
            victim_role = role_by_player.get(owner or "")
            ko_role = _other_role(victim_role)
            if victim_role in metrics:
                metrics[victim_role]["pokemon_lost"] += 1
            if ko_role in metrics:
                metrics[ko_role]["knockouts"] += 1
            continue

        metric = COUNTED_EVENTS.get(event.type)
        if not metric:
            continue
        player_id = _event_player(event, game)
        role = role_by_player.get(player_id or "")
        if role in metrics:
            metrics[role][metric] += 1
    return metrics


def _merge_metrics(total: dict[str, Counter], update: dict[str, Counter]) -> None:
    for role, counter in update.items():
        total[role].update(counter)


def _zone_count(game: Game, player_id: str, zone_type: ZoneType) -> int:
    zone = game.state.zones.get(f"{zone_type.name.lower()}_{player_id}")
    return len(zone.objects) if zone else 0


def _attached_energy_count(game: Game, player_id: str) -> int:
    total = 0
    for zone in game.state.zones.values():
        if zone.owner != player_id:
            continue
        if zone.type not in (ZoneType.ACTIVE_SPOT, ZoneType.BENCH):
            continue
        for obj_id in zone.objects:
            obj = game.state.objects.get(obj_id)
            if obj:
                total += len(obj.state.attached_energy)
    return total


def _board_damage_counters(game: Game, player_id: str) -> int:
    total = 0
    for zone in game.state.zones.values():
        if zone.owner != player_id:
            continue
        if zone.type not in (ZoneType.ACTIVE_SPOT, ZoneType.BENCH):
            continue
        for obj_id in zone.objects:
            obj = game.state.objects.get(obj_id)
            if obj:
                total += obj.state.damage_counters
    return total


def _final_player_stats(game: Game, player_id: str) -> dict[str, Any]:
    player = game.state.players[player_id]
    return {
        "has_lost": bool(player.has_lost),
        "prizes_remaining": player.prizes_remaining,
        "prizes_taken": max(0, 6 - player.prizes_remaining),
        "hand": _zone_count(game, player_id, ZoneType.HAND),
        "library": _zone_count(game, player_id, ZoneType.LIBRARY),
        "bench": _zone_count(game, player_id, ZoneType.BENCH),
        "attached_energy": _attached_energy_count(game, player_id),
        "board_damage_counters": _board_damage_counters(game, player_id),
    }


def _winner_role(game: Game, role_by_player: dict[str, str]) -> str | None:
    alive = [
        player_id
        for player_id, player in game.state.players.items()
        if not player.has_lost
    ]
    if len(alive) == 1:
        return role_by_player.get(alive[0])
    for player_id, player in game.state.players.items():
        if player.prizes_remaining == 0:
            return role_by_player.get(player_id)
    return None


async def _play_game(deck_name: str, seed: int, p1_difficulty: str,
                     p2_difficulty: str, first_player: str,
                     max_turns: int, codex_difficulty: str,
                     baseline_difficulty: str) -> dict[str, Any]:
    random.seed(seed)

    game = Game(mode="pokemon")
    p1 = game.add_player(f"{deck_name}-p1")
    p2 = game.add_player(f"{deck_name}-p2")
    builder = GUILD_DECK_BUILDERS[deck_name]
    game.setup_pokemon_player(p1, list(builder()))
    game.setup_pokemon_player(p2, list(builder()))

    ai = PokemonAIAdapter(difficulty=p1_difficulty)
    ai.player_difficulties[p1.id] = p1_difficulty
    ai.player_difficulties[p2.id] = p2_difficulty
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)

    await game.turn_manager.setup_game()
    first_id = p1.id if first_player == "p1" else p2.id
    second_id = p2.id if first_player == "p1" else p1.id
    game.turn_manager.pkm_turn_state.first_player_id = first_id
    game.turn_manager.turn_order = [first_id, second_id]
    game.turn_manager.current_player_index = 0

    role_by_player = {}
    for player_id, diff in ((p1.id, p1_difficulty), (p2.id, p2_difficulty)):
        if diff == codex_difficulty:
            role_by_player[player_id] = "codex"
        elif diff == baseline_difficulty:
            role_by_player[player_id] = "baseline"
        else:
            role_by_player[player_id] = diff

    metrics = {"codex": Counter(), "baseline": Counter()}
    turn_count = 0
    for _ in range(max_turns):
        if game.is_game_over():
            break
        turn_events = await game.turn_manager.run_turn()
        turn_count += 1
        _merge_metrics(metrics, _collect_event_metrics(
            turn_events, game, role_by_player))

    game.turn_manager.check_win_conditions()
    winner = _winner_role(game, role_by_player)
    p1_stats = _final_player_stats(game, p1.id)
    p2_stats = _final_player_stats(game, p2.id)

    codex_player = p1.id if role_by_player[p1.id] == "codex" else p2.id
    baseline_player = p1.id if role_by_player[p1.id] == "baseline" else p2.id
    codex_stats = _final_player_stats(game, codex_player)
    baseline_stats = _final_player_stats(game, baseline_player)

    return {
        "deck": deck_name,
        "seed": seed,
        "p1_difficulty": p1_difficulty,
        "p2_difficulty": p2_difficulty,
        "first_player": first_player,
        "turns": turn_count,
        "timeout": winner is None,
        "winner": winner,
        "codex_on_play": role_by_player[first_id] == "codex",
        "prize_margin": (
            baseline_stats["prizes_remaining"]
            - codex_stats["prizes_remaining"]
        ),
        "codex": codex_stats,
        "baseline": baseline_stats,
        "p1": p1_stats,
        "p2": p2_stats,
        "metrics": {role: dict(counter) for role, counter in metrics.items()},
    }


async def _play_codex_mirror(deck_name: str, seed: int, max_turns: int,
                             codex_difficulty: str) -> dict[str, Any]:
    random.seed(seed)

    game = Game(mode="pokemon")
    p1 = game.add_player(f"{deck_name}-codex-a")
    p2 = game.add_player(f"{deck_name}-codex-b")
    builder = GUILD_DECK_BUILDERS[deck_name]
    game.setup_pokemon_player(p1, list(builder()))
    game.setup_pokemon_player(p2, list(builder()))

    ai = PokemonAIAdapter(difficulty=codex_difficulty)
    ai.player_difficulties[p1.id] = codex_difficulty
    ai.player_difficulties[p2.id] = codex_difficulty
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)

    await game.turn_manager.setup_game()
    game.turn_manager.pkm_turn_state.first_player_id = p1.id
    game.turn_manager.turn_order = [p1.id, p2.id]
    game.turn_manager.current_player_index = 0

    turn_count = 0
    for _ in range(max_turns):
        if game.is_game_over():
            break
        await game.turn_manager.run_turn()
        turn_count += 1

    game.turn_manager.check_win_conditions()
    winner = None
    if p1.has_lost and not p2.has_lost:
        winner = "p2"
    elif p2.has_lost and not p1.has_lost:
        winner = "p1"
    elif p1.prizes_remaining == 0:
        winner = "p1"
    elif p2.prizes_remaining == 0:
        winner = "p2"

    p1_stats = _final_player_stats(game, p1.id)
    p2_stats = _final_player_stats(game, p2.id)
    return {
        "deck": deck_name,
        "seed": seed,
        "turns": turn_count,
        "timeout": winner is None,
        "winner": winner,
        "p1": p1_stats,
        "p2": p2_stats,
        "total_prizes_taken": p1_stats["prizes_taken"] + p2_stats["prizes_taken"],
    }


def _summarize(results: list[dict[str, Any]], mirror_results: list[dict[str, Any]],
               codex_difficulty: str, baseline_difficulty: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "codex_difficulty": codex_difficulty,
        "baseline_difficulty": baseline_difficulty,
        "games": len(results),
        "codex_wins": 0,
        "baseline_wins": 0,
        "draws_or_timeouts": 0,
        "prize_margin": 0,
        "attack_margin": 0,
        "damage_counter_margin": 0,
        "knockout_margin": 0,
        "codex_on_play": {"games": 0, "wins": 0, "prize_margin": 0},
        "codex_on_draw": {"games": 0, "wins": 0, "prize_margin": 0},
        "by_deck": {},
        "metrics": {"codex": Counter(), "baseline": Counter()},
    }

    by_deck = defaultdict(lambda: {
        "games": 0,
        "codex_wins": 0,
        "baseline_wins": 0,
        "draws_or_timeouts": 0,
        "prize_margin": 0,
        "attack_margin": 0,
        "damage_counter_margin": 0,
        "knockout_margin": 0,
    })

    for result in results:
        deck = result["deck"]
        bucket = by_deck[deck]
        bucket["games"] += 1
        summary["prize_margin"] += result["prize_margin"]
        bucket["prize_margin"] += result["prize_margin"]
        codex_metrics = result["metrics"].get("codex", {})
        baseline_metrics = result["metrics"].get("baseline", {})
        attack_margin = (
            codex_metrics.get("attacks", 0)
            - baseline_metrics.get("attacks", 0)
        )
        damage_margin = (
            codex_metrics.get("damage_counters_dealt", 0)
            - baseline_metrics.get("damage_counters_dealt", 0)
        )
        knockout_margin = (
            codex_metrics.get("knockouts", 0)
            - baseline_metrics.get("knockouts", 0)
        )
        summary["attack_margin"] += attack_margin
        summary["damage_counter_margin"] += damage_margin
        summary["knockout_margin"] += knockout_margin
        bucket["attack_margin"] += attack_margin
        bucket["damage_counter_margin"] += damage_margin
        bucket["knockout_margin"] += knockout_margin
        play_bucket = summary["codex_on_play" if result["codex_on_play"] else "codex_on_draw"]
        play_bucket["games"] += 1
        play_bucket["prize_margin"] += result["prize_margin"]

        if result["winner"] == "codex":
            summary["codex_wins"] += 1
            bucket["codex_wins"] += 1
            play_bucket["wins"] += 1
        elif result["winner"] == "baseline":
            summary["baseline_wins"] += 1
            bucket["baseline_wins"] += 1
        else:
            summary["draws_or_timeouts"] += 1
            bucket["draws_or_timeouts"] += 1

        for role, metrics in result["metrics"].items():
            if role in summary["metrics"]:
                summary["metrics"][role].update(metrics)

    summary["by_deck"] = dict(sorted(by_deck.items()))
    summary["metrics"] = {
        role: dict(counter)
        for role, counter in summary["metrics"].items()
    }
    summary["mirror"] = {
        "games": len(mirror_results),
        "timeouts": sum(1 for result in mirror_results if result["timeout"]),
        "average_turns": (
            sum(result["turns"] for result in mirror_results) / len(mirror_results)
            if mirror_results else 0
        ),
        "average_total_prizes_taken": (
            sum(result["total_prizes_taken"] for result in mirror_results)
            / len(mirror_results)
            if mirror_results else 0
        ),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decks", default=DEFAULT_DECKS)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--max-turns", type=int, default=60)
    parser.add_argument("--baseline", default="medium")
    parser.add_argument("--codex", default="ultra")
    parser.add_argument("--out", default="codex-pokemon-strategy/pokemon_strategy_results.json")
    parser.add_argument("--summary-out", default="codex-pokemon-strategy/pokemon_strategy_summary.json")
    parser.add_argument("--skip-mirror", action="store_true")
    args = parser.parse_args()

    decks = _parse_csv(args.decks)
    unknown = [deck for deck in decks if deck not in GUILD_DECK_BUILDERS]
    if unknown:
        raise SystemExit(f"Unknown deck(s): {', '.join(unknown)}")
    seeds = _parse_int_csv(args.seeds)

    t0 = time.time()
    results = []
    mirror_results = []
    errors = []

    for deck in decks:
        for seed in seeds:
            scenarios = [
                ("codex_play", args.codex, args.baseline, "p1"),
                ("codex_draw", args.baseline, args.codex, "p1"),
            ]
            for scenario, p1_diff, p2_diff, first_player in scenarios:
                try:
                    result = _run(_play_game(
                        deck, seed, p1_diff, p2_diff, first_player,
                        args.max_turns, args.codex, args.baseline))
                    result["scenario"] = scenario
                    results.append(result)
                except Exception as exc:  # noqa: BLE001 - harness should report all failures
                    errors.append({
                        "deck": deck,
                        "seed": seed,
                        "scenario": scenario,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            if not args.skip_mirror:
                try:
                    mirror_results.append(_run(_play_codex_mirror(
                        deck, seed, args.max_turns, args.codex)))
                except Exception as exc:  # noqa: BLE001
                    errors.append({
                        "deck": deck,
                        "seed": seed,
                        "scenario": "codex_mirror",
                        "error": f"{type(exc).__name__}: {exc}",
                    })

    summary = _summarize(results, mirror_results, args.codex, args.baseline)
    summary["errors"] = len(errors)
    summary["elapsed_seconds"] = round(time.time() - t0, 3)

    output = {
        "summary": summary,
        "errors": errors,
        "results": results,
        "mirror_results": mirror_results,
    }

    out_path = PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    summary_path = PROJECT_ROOT / args.summary_out
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    if errors:
        print(f"errors: {len(errors)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
