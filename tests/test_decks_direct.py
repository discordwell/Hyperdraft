#!/usr/bin/env python3
"""
Direct deck testing without requiring the server.
Tests decks against each other using the game engine directly.
"""

import asyncio
from typing import Optional
from src.engine import (
    Game, GameState, PlayerAction, ActionType, LegalAction,
    CardType, AttackDeclaration, BlockDeclaration
)
from src.cards import ALL_CARDS
from src.decks import load_deck, get_deck, STANDARD_DECKS, NETDECKS, get_netdeck


def simple_ai_action(player_id: str, state: GameState, legal_actions: list[LegalAction]) -> PlayerAction:
    """Simple AI that plays lands and creatures, then passes."""
    # Look for land plays
    for action in legal_actions:
        if action.type == ActionType.PLAY_LAND:
            return PlayerAction(
                type=ActionType.PLAY_LAND,
                player_id=player_id,
                card_id=action.card_id
            )

    # Look for creature spells we can cast
    for action in legal_actions:
        if action.type == ActionType.CAST_SPELL and not action.requires_mana:
            return PlayerAction(
                type=ActionType.CAST_SPELL,
                player_id=player_id,
                card_id=action.card_id
            )

    # Default: pass
    return PlayerAction(type=ActionType.PASS, player_id=player_id)


def get_attacks(player_id: str, legal_attackers: list[str], game: Game) -> list[AttackDeclaration]:
    """Attack with all legal attackers."""
    defending_players = [pid for pid in game.state.players.keys() if pid != player_id]
    if not defending_players:
        return []

    defender = defending_players[0]
    return [
        AttackDeclaration(attacker_id=aid, defending_player_id=defender)
        for aid in legal_attackers
    ]


def get_blocks(
    player_id: str,
    attackers: list[AttackDeclaration],
    legal_blockers: list[str]
) -> list[BlockDeclaration]:
    """Block with available creatures."""
    blocks = []
    available_blockers = list(legal_blockers)

    for attacker in attackers:
        if available_blockers:
            blocker = available_blockers.pop(0)
            blocks.append(BlockDeclaration(
                blocker_id=blocker,
                blocking_attacker_id=attacker.attacker_id
            ))

    return blocks


def _get_deck(deck_id: str):
    """Get a deck from either STANDARD_DECKS or NETDECKS."""
    if deck_id in STANDARD_DECKS:
        return STANDARD_DECKS[deck_id]
    elif deck_id in NETDECKS:
        return NETDECKS[deck_id]
    else:
        raise ValueError(f"Unknown deck: {deck_id}")


async def run_game(deck1_id: str, deck2_id: str, max_turns: int = 30, verbose: bool = False) -> dict:
    """Run a game between two decks."""
    game = Game()

    # Add players
    p1 = game.add_player('Player 1')
    p2 = game.add_player('Player 2')

    # Set both as AI
    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)

    # Set up handlers
    game.priority_system.get_ai_action = simple_ai_action
    game.combat_manager.get_attack_declarations = lambda pid, atks: get_attacks(pid, atks, game)
    game.combat_manager.get_block_declarations = get_blocks

    # Load and add decks
    deck1 = load_deck(ALL_CARDS, _get_deck(deck1_id))
    deck2 = load_deck(ALL_CARDS, _get_deck(deck2_id))

    for card in deck1:
        game.add_card_to_library(p1.id, card)
    game.shuffle_library(p1.id)

    for card in deck2:
        game.add_card_to_library(p2.id, card)
    game.shuffle_library(p2.id)

    # Start game
    await game.start_game()

    if verbose:
        print(f"Starting: {deck1_id} vs {deck2_id}")
        print(f"P1 hand: {len(game.get_hand(p1.id))} cards")
        print(f"P2 hand: {len(game.get_hand(p2.id))} cards")

    # Run turns
    turn = 0
    while turn < max_turns and not game.is_game_over():
        turn += 1

        if verbose and turn <= 5:
            p1_life = game.state.players[p1.id].life
            p2_life = game.state.players[p2.id].life
            print(f"Turn {turn}: P1={p1_life} P2={p2_life}")

        try:
            await game.turn_manager.run_turn()
        except Exception as e:
            if verbose:
                print(f"Error on turn {turn}: {e}")
            break

    # Get results
    p1_life = game.state.players[p1.id].life
    p2_life = game.state.players[p2.id].life
    p1_lost = game.state.players[p1.id].has_lost
    p2_lost = game.state.players[p2.id].has_lost

    winner = None
    if p1_lost and not p2_lost:
        winner = "p2"
    elif p2_lost and not p1_lost:
        winner = "p1"
    elif p1_life <= 0 and p2_life > 0:
        winner = "p2"
    elif p2_life <= 0 and p1_life > 0:
        winner = "p1"

    if verbose:
        print(f"Final: P1={p1_life} (lost={p1_lost}) vs P2={p2_life} (lost={p2_lost})")
        print(f"Winner: {winner or 'Draw'}")

    return {
        "turns": turn,
        "p1_life": p1_life,
        "p2_life": p2_life,
        "p1_lost": p1_lost,
        "p2_lost": p2_lost,
        "winner": winner
    }


def test_matchup(deck1_id: str, deck2_id: str, games: int = 5, verbose: bool = False):
    """Test a matchup multiple times."""
    print(f"\n{'='*60}")
    print(f"MATCHUP: {deck1_id} vs {deck2_id}")
    print(f"Running {games} games...")
    print("="*60)

    p1_wins = 0
    p2_wins = 0
    draws = 0

    for i in range(games):
        result = asyncio.run(run_game(deck1_id, deck2_id, verbose=verbose))

        if result["winner"] == "p1":
            p1_wins += 1
            print(f"Game {i+1}: {deck1_id} WINS (P1={result['p1_life']} vs P2={result['p2_life']}, {result['turns']} turns)")
        elif result["winner"] == "p2":
            p2_wins += 1
            print(f"Game {i+1}: {deck2_id} WINS (P1={result['p1_life']} vs P2={result['p2_life']}, {result['turns']} turns)")
        else:
            draws += 1
            print(f"Game {i+1}: DRAW (P1={result['p1_life']} vs P2={result['p2_life']}, {result['turns']} turns)")

    print(f"\nResults: {deck1_id}={p1_wins} wins, {deck2_id}={p2_wins} wins, Draws={draws}")
    return {"p1_wins": p1_wins, "p2_wins": p2_wins, "draws": draws}


def test_all_matchups(games_per: int = 3, netdecks_only: bool = False):
    """Test all deck matchups."""
    if netdecks_only:
        # Use tournament netdecks
        complete_decks = list(NETDECKS.keys())
    else:
        # Use standard decks
        complete_decks = [
            "mono_red_aggro",
            "mono_green_ramp",
            "dimir_control",
            "boros_aggro",
            "simic_tempo",
            "lorwyn_faeries",
        ]

    results = {}
    for d1 in complete_decks:
        for d2 in complete_decks:
            if d1 < d2:  # Only test each pair once
                key = f"{d1} vs {d2}"
                results[key] = test_matchup(d1, d2, games=games_per)

    print("\n" + "="*60)
    print("OVERALL RESULTS")
    print("="*60)
    for matchup, r in results.items():
        print(f"{matchup}: {r['p1_wins']}-{r['p2_wins']}-{r['draws']}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Direct deck testing")
    parser.add_argument("--deck1", "-d1", default="mono_red_netdeck", help="First deck")
    parser.add_argument("--deck2", "-d2", default="dimir_midrange_netdeck", help="Second deck")
    parser.add_argument("--games", "-g", type=int, default=5, help="Number of games")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--all", action="store_true", help="Test all matchups")
    parser.add_argument("--netdecks", action="store_true", help="Use netdecks for --all")
    parser.add_argument("--list", "-l", action="store_true", help="List available decks")

    args = parser.parse_args()

    if args.list:
        print("Standard Decks:")
        for deck_id, deck in STANDARD_DECKS.items():
            print(f"  {deck_id}: {deck.name} ({deck.archetype})")
        print("\nNetdecks (Tournament):")
        for deck_id, deck in NETDECKS.items():
            print(f"  {deck_id}: {deck.name} ({deck.archetype})")
    elif args.all:
        test_all_matchups(games_per=args.games, netdecks_only=args.netdecks)
    else:
        test_matchup(args.deck1, args.deck2, games=args.games, verbose=args.verbose)
