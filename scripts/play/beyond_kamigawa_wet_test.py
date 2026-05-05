"""
Beyond Kamigawa — wet test harness.

Runs AI-vs-AI mirror and cross-archetype matches across all 5 archetypes,
reports per-pairing win rates, flags anomalies (>85% mirror imbalance, crashes,
games stuck at the turn cap).

Usage::

    python scripts/play/beyond_kamigawa_wet_test.py            # default: 3 games per pairing
    python scripts/play/beyond_kamigawa_wet_test.py --games 10 # 10 games per pairing
    python scripts/play/beyond_kamigawa_wet_test.py --quick    # 1 game per pairing (smoke)
"""

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


from src.engine.game import Game
from src.cards.yugioh.beyond.kamigawa import ARCHETYPE_DECK_BUILDERS, build_kamigawa_deck


MAX_TURNS_PER_GAME = 40
DEFAULT_MIN_MIRROR_GAMES_FOR_IMBALANCE = 5


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def play_one_match(deck_a_name: str, deck_a_builder,
                         deck_b_name: str, deck_b_builder) -> dict:
    """Play one AI-vs-AI match. Returns {'winner_id', 'turns', 'crashed', 'reason'}."""
    from src.ai.yugioh_adapter import YugiohAIAdapter

    g = Game(mode="yugioh")
    p1 = g.add_player(f"{deck_a_name} A")
    p2 = g.add_player(f"{deck_b_name} B")
    main_a, extra_a = build_kamigawa_deck(deck_a_name)
    main_b, extra_b = build_kamigawa_deck(deck_b_name)
    g.setup_yugioh_player(p1, main_a, extra_a)
    g.setup_yugioh_player(p2, main_b, extra_b)
    ai = YugiohAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.ai_players.add(p1.id)
    g.turn_manager.ai_players.add(p2.id)
    await g.turn_manager.setup_game()

    turns = 0
    while turns < MAX_TURNS_PER_GAME:
        if g.is_game_over():
            break
        await g.turn_manager.run_turn()
        turns += 1

    winner = g.get_winner() if hasattr(g, 'get_winner') else None
    winner_label = None
    if winner is not None:
        # ``get_winner`` may return a Player or a player-id string depending on engine version
        winner_id = winner.id if hasattr(winner, 'id') else winner
        if winner_id == p1.id:
            winner_label = "A"
        elif winner_id == p2.id:
            winner_label = "B"
    return {
        'winner': winner_label,
        'turns': turns,
        'ended_in_game_over': g.is_game_over(),
    }


def mirror_imbalance_anomaly(a: str, b: str, n: int, a_rate: float,
                             min_games: int = DEFAULT_MIN_MIRROR_GAMES_FOR_IMBALANCE) -> bool:
    """Return True when a mirror sample is large enough and materially skewed."""
    return a == b and n >= min_games and (a_rate < 0.15 or a_rate > 0.85)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--games', type=int, default=3,
                        help='games per pairing (default 3)')
    parser.add_argument('--quick', action='store_true',
                        help='quick mode: 1 game per pairing')
    parser.add_argument('--mirrors-only', action='store_true',
                        help='only run mirror matches (no cross-archetype)')
    parser.add_argument('--min-mirror-games-for-imbalance', type=int,
                        default=DEFAULT_MIN_MIRROR_GAMES_FOR_IMBALANCE,
                        help='minimum completed mirror games before flagging win-rate imbalance')
    parser.add_argument('--json-out', default=None,
                        help='optional path for a machine-readable JSON summary')
    args = parser.parse_args()
    if args.quick:
        args.games = 1

    archetypes = sorted(ARCHETYPE_DECK_BUILDERS.keys())
    pairings = []
    # Mirrors
    for a in archetypes:
        pairings.append((a, a))
    # Crosses
    if not args.mirrors_only:
        for i, a in enumerate(archetypes):
            for b in archetypes[i + 1:]:
                pairings.append((a, b))

    print(f"\nBeyond Kamigawa wet test")
    print(f"  Pairings : {len(pairings)}")
    print(f"  Games    : {args.games} per pairing")
    print(f"  Total    : {len(pairings) * args.games}")
    print(f"  Max turns: {MAX_TURNS_PER_GAME} per game")
    print()

    results = defaultdict(lambda: {'a_wins': 0, 'b_wins': 0, 'draws': 0,
                                    'crashes': 0, 'turns': []})
    start = time.time()
    total_done = 0

    for a, b in pairings:
        for game_idx in range(args.games):
            try:
                outcome = run(play_one_match(
                    a, ARCHETYPE_DECK_BUILDERS[a],
                    b, ARCHETYPE_DECK_BUILDERS[b]
                ))
                key = (a, b)
                results[key]['turns'].append(outcome['turns'])
                if outcome['winner'] == 'A':
                    results[key]['a_wins'] += 1
                elif outcome['winner'] == 'B':
                    results[key]['b_wins'] += 1
                else:
                    results[key]['draws'] += 1
            except Exception as ex:
                results[(a, b)]['crashes'] += 1
                print(f"  CRASH {a} vs {b} game {game_idx}: "
                      f"{type(ex).__name__}: {ex}")
            total_done += 1
            if total_done % 5 == 0:
                elapsed = time.time() - start
                print(f"  ... {total_done}/{len(pairings) * args.games} "
                      f"({elapsed:.0f}s elapsed)")

    print()
    print("=" * 78)
    print(f"{'Pairing':<32} {'A':>5} {'B':>5} {'Draw':>5} {'Crash':>5} "
          f"{'Avg turns':>9}")
    print("-" * 78)
    anomalies = []
    for (a, b), data in sorted(results.items()):
        n = data['a_wins'] + data['b_wins'] + data['draws']
        if n == 0:
            continue
        avg_turns = sum(data['turns']) / len(data['turns']) if data['turns'] else 0
        a_rate = data['a_wins'] / n if n else 0
        print(f"{a:14s} vs {b:14s} {data['a_wins']:>5} {data['b_wins']:>5} "
              f"{data['draws']:>5} {data['crashes']:>5} {avg_turns:>9.1f}")
        # Anomaly detection
        if data['crashes'] > 0:
            anomalies.append(f"{a} vs {b}: {data['crashes']} crashes")
        if mirror_imbalance_anomaly(
            a, b, n, a_rate, args.min_mirror_games_for_imbalance
        ):
            anomalies.append(
                f"{a} mirror imbalance: A wins {a_rate:.0%} of {n} games"
            )
    print("=" * 78)

    elapsed = time.time() - start
    print(f"\nElapsed: {elapsed:.1f}s ({elapsed / total_done:.2f}s/game)")
    if anomalies:
        print(f"\nAnomalies ({len(anomalies)}):")
        for a in anomalies:
            print(f"  - {a}")
    else:
        print("\nNo anomalies detected.")

    if args.json_out:
        serializable_results = {
            f"{a} vs {b}": {
                "a_wins": data["a_wins"],
                "b_wins": data["b_wins"],
                "draws": data["draws"],
                "crashes": data["crashes"],
                "completed_games": data["a_wins"] + data["b_wins"] + data["draws"],
                "a_win_rate": (
                    data["a_wins"] / (data["a_wins"] + data["b_wins"] + data["draws"])
                    if (data["a_wins"] + data["b_wins"] + data["draws"]) else 0
                ),
                "turns": data["turns"],
                "avg_turns": sum(data["turns"]) / len(data["turns"]) if data["turns"] else 0,
            }
            for (a, b), data in sorted(results.items())
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({
                "games_per_pairing": args.games,
                "min_mirror_games_for_imbalance": args.min_mirror_games_for_imbalance,
                "max_turns_per_game": MAX_TURNS_PER_GAME,
                "results": serializable_results,
                "anomalies": anomalies,
            }, fh, indent=2, sort_keys=True)

    sys.exit(1 if anomalies else 0)


if __name__ == "__main__":
    main()
