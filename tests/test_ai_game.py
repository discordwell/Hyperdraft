#!/usr/bin/env python3
"""
Full AI vs AI game with detailed turn-by-turn logging.
Uses the real AI engine for both players.
"""

import asyncio
import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, GameState, PlayerAction, ActionType, LegalAction,
    CardType, AttackDeclaration, BlockDeclaration, ZoneType
)
from src.cards import ALL_CARDS
from src.decks import load_deck, STANDARD_DECKS, NETDECKS

from src.ai import AIEngine, AggroStrategy, ControlStrategy, MidrangeStrategy


class GameLogger:
    """Logs game events for turn-by-turn analysis."""

    def __init__(self):
        self.turns = []
        self.current_turn = None

    def start_turn(self, turn_number: int, active_player: str):
        self.current_turn = {
            'turn': turn_number,
            'active_player': active_player,
            'actions': [],
            'combat': None,
            'end_state': None
        }

    def log_action(self, player: str, action_type: str, card_name: str = None, details: str = None):
        entry = f"[{player}] {action_type}"
        if card_name:
            entry += f": {card_name}"
        if details:
            entry += f" ({details})"
        self.current_turn['actions'].append(entry)

    def log_combat(self, attackers: list, blockers: list, damage_dealt: dict):
        self.current_turn['combat'] = {
            'attackers': attackers,
            'blockers': blockers,
            'damage': damage_dealt
        }

    def log_end_state(self, p1_life: int, p2_life: int, p1_board: list, p2_board: list):
        self.current_turn['end_state'] = {
            'p1_life': p1_life,
            'p2_life': p2_life,
            'p1_board': p1_board,
            'p2_board': p2_board
        }

    def end_turn(self):
        if self.current_turn:
            self.turns.append(self.current_turn)
            self.current_turn = None

    def print_summary(self):
        for turn in self.turns:
            print(f"\n{'='*60}")
            print(f"TURN {turn['turn']} - {turn['active_player']}'s turn")
            print('='*60)

            for action in turn['actions']:
                print(f"  {action}")

            if turn['combat']:
                combat = turn['combat']
                if combat['attackers']:
                    print(f"  COMBAT: {', '.join(combat['attackers'])} attack")
                if combat['blockers']:
                    print(f"  BLOCKS: {', '.join(combat['blockers'])}")
                if combat['damage']:
                    for target, dmg in combat['damage'].items():
                        print(f"  DAMAGE: {dmg} to {target}")

            if turn['end_state']:
                state = turn['end_state']
                print(f"  ---")
                print(f"  P1: {state['p1_life']} life | Board: {', '.join(state['p1_board']) or 'empty'}")
                print(f"  P2: {state['p2_life']} life | Board: {', '.join(state['p2_board']) or 'empty'}")


def get_deck(deck_id: str):
    """Get a deck from either STANDARD_DECKS or NETDECKS."""
    if deck_id in STANDARD_DECKS:
        return STANDARD_DECKS[deck_id]
    elif deck_id in NETDECKS:
        return NETDECKS[deck_id]
    else:
        raise ValueError(f"Unknown deck: {deck_id}")


def get_permanent_summary(obj) -> str:
    """Get a short summary of a permanent."""
    types = obj.characteristics.types
    if CardType.CREATURE in types:
        power = obj.characteristics.power or 0
        toughness = obj.characteristics.toughness or 0
        tapped = " (T)" if obj.state.tapped else ""
        return f"{obj.name} {power}/{toughness}{tapped}"
    elif CardType.PLANESWALKER in types:
        # Get loyalty from abilities list (stored as {'loyalty': X})
        loyalty = '?'
        for ability in (obj.characteristics.abilities or []):
            if isinstance(ability, dict) and 'loyalty' in ability:
                loyalty = ability['loyalty']
                break
        # Also check state counters for current loyalty (may be modified during game)
        if 'loyalty' in obj.state.counters:
            loyalty = obj.state.counters['loyalty']
        return f"{obj.name} [L:{loyalty}]"
    elif CardType.LAND in types:
        tapped = " (T)" if obj.state.tapped else ""
        return f"{obj.name}{tapped}"
    else:
        # Artifact, Enchantment, etc.
        tapped = " (T)" if obj.state.tapped else ""
        return f"{obj.name}{tapped}"


def get_board_state(game: Game, player_id: str) -> list:
    """Get list of permanent names on a player's board (excluding lands)."""
    permanents = []
    battlefield = game.state.zones.get('battlefield')
    if battlefield:
        for obj_id in battlefield.objects:
            obj = game.state.objects.get(obj_id)
            # Include all permanents except lands
            if obj and obj.controller == player_id and CardType.LAND not in obj.characteristics.types:
                permanents.append(get_permanent_summary(obj))
    return permanents


async def run_logged_game(
    deck1_id: str,
    deck2_id: str,
    max_turns: int = 15,
    p1_strategy: str = 'aggro',
    p2_strategy: str = 'midrange'
) -> dict:
    """Run a game with detailed logging."""

    # Create AI engines based on strategy
    strategies = {
        'aggro': AggroStrategy(),
        'control': ControlStrategy(),
        'midrange': MidrangeStrategy()
    }

    ai1 = AIEngine(strategy=strategies.get(p1_strategy, MidrangeStrategy()), difficulty='hard')
    ai2 = AIEngine(strategy=strategies.get(p2_strategy, MidrangeStrategy()), difficulty='hard')

    logger = GameLogger()
    game = Game()

    # Add players
    p1 = game.add_player('Player 1 (You)')
    p2 = game.add_player('Player 2 (AI)')

    # Set both as AI-controlled
    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)

    # Track actions for logging
    action_log = []

    def make_ai_action(player_id: str, state: GameState, legal_actions: list) -> PlayerAction:
        """AI action with logging."""
        ai = ai1 if player_id == p1.id else ai2
        action = ai.get_action(player_id, state, legal_actions)

        # Log the action
        player_name = "P1" if player_id == p1.id else "P2"

        if action.type == ActionType.PLAY_LAND and action.card_id:
            card = state.objects.get(action.card_id)
            card_name = card.name if card else "Land"
            logger.log_action(player_name, "PLAY LAND", card_name)
        elif action.type == ActionType.CAST_SPELL and action.card_id:
            card = state.objects.get(action.card_id)
            card_name = card.name if card else "Spell"
            logger.log_action(player_name, "CAST", card_name)
        elif action.type == ActionType.ACTIVATE_ABILITY:
            logger.log_action(player_name, "ACTIVATE", details="ability")
        # Skip logging PASS to reduce noise

        return action

    def make_attacks(player_id: str, legal_attackers: list) -> list:
        """AI attack declarations with logging."""
        ai = ai1 if player_id == p1.id else ai2
        player_name = "P1" if player_id == p1.id else "P2"

        from src.ai import BoardEvaluator
        evaluator = BoardEvaluator(game.state)

        attacks = ai.strategy.plan_attacks(game.state, player_id, evaluator, legal_attackers)

        if attacks:
            attacker_names = []
            for atk in attacks:
                obj = game.state.objects.get(atk.attacker_id)
                if obj:
                    attacker_names.append(get_permanent_summary(obj))

            # Find defender
            defender_id = [pid for pid in game.state.players.keys() if pid != player_id][0]
            logger.log_action(player_name, "ATTACK", details=f"{', '.join(attacker_names)}")

            # Store for combat logging
            logger.current_turn['combat'] = {
                'attackers': attacker_names,
                'blockers': [],
                'damage': {}
            }

        return attacks

    def make_blocks(player_id: str, attackers: list, legal_blockers: list) -> list:
        """AI block declarations with logging."""
        ai = ai1 if player_id == p1.id else ai2
        player_name = "P1" if player_id == p1.id else "P2"

        from src.ai import BoardEvaluator
        evaluator = BoardEvaluator(game.state)

        blocks = ai.strategy.plan_blocks(game.state, player_id, evaluator, attackers, legal_blockers)

        if blocks and logger.current_turn and logger.current_turn['combat']:
            blocker_names = []
            for blk in blocks:
                obj = game.state.objects.get(blk.blocker_id)
                attacker = game.state.objects.get(blk.blocking_attacker_id)
                if obj and attacker:
                    blocker_names.append(f"{obj.name} blocks {attacker.name}")
            logger.current_turn['combat']['blockers'] = blocker_names

        return blocks

    # Set up handlers
    game.priority_system.get_ai_action = make_ai_action
    game.combat_manager.get_attack_declarations = make_attacks
    game.combat_manager.get_block_declarations = make_blocks

    # Load decks. Custom-card domains are resolved via set_registry when deck
    # entries include a domain (e.g. "TMH", "TLAC").
    deck1 = load_deck(ALL_CARDS, get_deck(deck1_id))
    deck2 = load_deck(ALL_CARDS, get_deck(deck2_id))

    for card in deck1:
        game.add_card_to_library(p1.id, card)
    game.shuffle_library(p1.id)

    for card in deck2:
        game.add_card_to_library(p2.id, card)
    game.shuffle_library(p2.id)

    # Start game
    await game.start_game()

    print(f"\n{'#'*60}")
    print(f"# GAME: {deck1_id} vs {deck2_id}")
    print(f"# Strategies: {p1_strategy.upper()} vs {p2_strategy.upper()}")
    print(f"{'#'*60}")
    print(f"\nP1 starting hand: {len(game.get_hand(p1.id))} cards")
    print(f"P2 starting hand: {len(game.get_hand(p2.id))} cards")

    # Run turns
    turn = 0
    while turn < max_turns and not game.is_game_over():
        turn += 1
        # Active player alternates - P1 goes on odd turns, P2 on even
        active_name = "P1" if turn % 2 == 1 else "P2"
        logger.start_turn(turn, active_name)

        try:
            await game.turn_manager.run_turn()
        except Exception as e:
            print(f"Error on turn {turn}: {e}")
            import traceback
            traceback.print_exc()
            break

        # Log end state
        logger.log_end_state(
            p1_life=game.state.players[p1.id].life,
            p2_life=game.state.players[p2.id].life,
            p1_board=get_board_state(game, p1.id),
            p2_board=get_board_state(game, p2.id)
        )

        logger.end_turn()

        # Early exit if someone is dead
        if game.state.players[p1.id].life <= 0 or game.state.players[p2.id].life <= 0:
            break

    # Print the full game log
    logger.print_summary()

    # Final results
    p1_life = game.state.players[p1.id].life
    p2_life = game.state.players[p2.id].life
    p1_lost = game.state.players[p1.id].has_lost or p1_life <= 0
    p2_lost = game.state.players[p2.id].has_lost or p2_life <= 0

    print(f"\n{'='*60}")
    print("GAME OVER")
    print('='*60)
    print(f"Final: P1={p1_life} life vs P2={p2_life} life")
    print(f"Turns: {turn}")

    if p1_lost and not p2_lost:
        print(f"\n*** {deck2_id} (P2) WINS! ***")
        winner = "p2"
    elif p2_lost and not p1_lost:
        print(f"\n*** {deck1_id} (P1) WINS! ***")
        winner = "p1"
    else:
        print("\n*** DRAW ***")
        winner = None

    return {
        'winner': winner,
        'turns': turn,
        'p1_life': p1_life,
        'p2_life': p2_life
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run AI vs AI game with detailed logging")
    parser.add_argument("--deck1", "-d1", default="mono_red_aggro", help="First deck")
    parser.add_argument("--deck2", "-d2", default="dimir_control", help="Second deck")
    parser.add_argument("--strategy1", "-s1", default="aggro", choices=['aggro', 'control', 'midrange'])
    parser.add_argument("--strategy2", "-s2", default="control", choices=['aggro', 'control', 'midrange'])
    parser.add_argument("--turns", "-t", type=int, default=15, help="Max turns")

    args = parser.parse_args()

    result = asyncio.run(run_logged_game(
        args.deck1, args.deck2,
        max_turns=args.turns,
        p1_strategy=args.strategy1,
        p2_strategy=args.strategy2
    ))
