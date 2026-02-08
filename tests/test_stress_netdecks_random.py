#!/usr/bin/env python3
"""
Randomized netdeck stress test (engine-only, no server).

Goal: play real Standard netdecks (downloaded from MTGGoldfish) against each other
with the AI engine, and ensure the game loop + zone bookkeeping stay consistent.

Usage:
  python tests/test_stress_netdecks_random.py --games 25
  python tests/test_stress_netdecks_random.py --games 100 --seed 123
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys

sys.path.insert(0, ".")

from src.ai import AIEngine, BoardEvaluator
from src.cards import ALL_CARDS
from src.decks import NETDECKS, load_deck
from src.engine import (
    ActionType,
    AttackDeclaration,
    BlockDeclaration,
    Game,
    PlayerAction,
)


def _check_zone_invariants(game: Game) -> None:
    """
    Basic bookkeeping checks:
    - no duplicates within zones
    - objects referenced by zones exist
    """
    state = game.state

    # No duplicates within any zone list.
    for zone_key, zone in state.zones.items():
        ids = list(zone.objects)
        if len(ids) != len(set(ids)):
            raise AssertionError(f"Duplicate object IDs in zone {zone_key}")

    # Every zone member exists in state.objects.
    for zone_key, zone in state.zones.items():
        for obj_id in zone.objects:
            if obj_id not in state.objects:
                raise AssertionError(f"Zone {zone_key} references missing object {obj_id}")


async def _run_one_game(deck1_id: str, deck2_id: str, seed: int, max_turns: int) -> None:
    rng = random.Random(seed)

    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)

    ai1 = AIEngine(difficulty="hard")
    ai2 = AIEngine(difficulty="hard")

    def _ai_action(player_id, state, legal_actions):
        pending = game.get_pending_choice()
        if pending and pending.player == player_id:
            ai = ai1 if player_id == p1.id else ai2
            selected = ai.make_choice(player_id, pending, state)
            ok, _msg, _events = game.submit_choice(pending.id, player_id, selected)
            if not ok:
                fallback = list(pending.options[: pending.min_choices])
                game.submit_choice(pending.id, player_id, fallback)
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

        ai = ai1 if player_id == p1.id else ai2
        return ai.get_action(player_id, state, legal_actions)

    def _attacks(player_id: str, legal_attackers: list[str]) -> list[AttackDeclaration]:
        ai = ai1 if player_id == p1.id else ai2
        evaluator = BoardEvaluator(game.state)
        try:
            return ai.strategy.plan_attacks(game.state, player_id, evaluator, legal_attackers)
        except Exception:
            defender = p2.id if player_id == p1.id else p1.id
            return [AttackDeclaration(attacker_id=a, defending_player_id=defender) for a in legal_attackers]

    def _blocks(
        player_id: str,
        attackers: list[AttackDeclaration],
        legal_blockers: list[str],
    ) -> list[BlockDeclaration]:
        ai = ai1 if player_id == p1.id else ai2
        evaluator = BoardEvaluator(game.state)
        try:
            return ai.strategy.plan_blocks(game.state, player_id, evaluator, attackers, legal_blockers)
        except Exception:
            blocks: list[BlockDeclaration] = []
            avail = list(legal_blockers)
            for atk in attackers:
                if not avail:
                    break
                blocks.append(BlockDeclaration(blocker_id=avail.pop(0), blocking_attacker_id=atk.attacker_id))
            return blocks

    game.set_ai_action_handler(_ai_action)
    game.set_attack_handler(_attacks)
    game.set_block_handler(_blocks)

    deck1 = load_deck(ALL_CARDS, NETDECKS[deck1_id])
    deck2 = load_deck(ALL_CARDS, NETDECKS[deck2_id])

    for card_def in deck1:
        game.add_card_to_library(p1.id, card_def)
    game.shuffle_library(p1.id)

    for card_def in deck2:
        game.add_card_to_library(p2.id, card_def)
    game.shuffle_library(p2.id)

    await game.start_game()
    _check_zone_invariants(game)

    turns = 0
    while not game.is_game_over() and turns < max_turns:
        turns += 1
        await game.turn_manager.run_turn()
        _check_zone_invariants(game)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Random netdeck engine stress test")
    p.add_argument("--games", type=int, default=25, help="Number of games to run (default: 25)")
    p.add_argument("--seed", type=int, default=None, help="Random seed")
    p.add_argument("--turns", type=int, default=60, help="Max turns per game (default: 60)")
    args = p.parse_args(argv)

    seed = args.seed if args.seed is not None else random.randrange(1_000_000_000)
    rng = random.Random(seed)

    deck_ids = list(NETDECKS.keys())
    if len(deck_ids) < 2:
        print("Not enough netdecks available.", file=sys.stderr)
        return 2

    print(f"Seed: {seed}")
    print(f"Netdecks: {len(deck_ids)}")

    try:
        for i in range(args.games):
            d1, d2 = rng.sample(deck_ids, 2)
            game_seed = rng.randrange(1_000_000_000)
            print(f"game {i + 1}/{args.games} {d1} vs {d2} seed={game_seed}")
            asyncio.run(_run_one_game(d1, d2, game_seed, args.turns))
        print("OK")
        return 0
    except Exception as e:
        print("FAILED")
        print(repr(e))
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

