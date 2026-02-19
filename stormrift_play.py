"""
STORMRIFT Interactive Game Manager

Replay-based game state management for interactive play via Claude Code.
Each invocation replays all prior moves from a JSON log, executes the
requested command, and saves the updated log.

Usage:
    python stormrift_play.py new <player_class> <ai_class> [seed]
    python stormrift_play.py show
    python stormrift_play.py play <hand_index>
    python stormrift_play.py attack <minion_index> <target_index|hero>
    python stormrift_play.py hero_power
    python stormrift_play.py end_turn

State file: /tmp/stormrift_game.json
"""

import asyncio
import json
import os
import random
import re
import sys

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine.game import Game
from src.engine.types import EventType, ZoneType, CardType, Event
from src.cards.hearthstone.stormrift import (
    STORMRIFT_HEROES, STORMRIFT_HERO_POWERS, STORMRIFT_DECKS,
    install_stormrift_modifiers,
)
from src.ai.hearthstone_adapter import HearthstoneAIAdapter

STATE_FILE = '/tmp/stormrift_game.json'


# =============================================================================
# State persistence
# =============================================================================

def load_state() -> dict | None:
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state: dict):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


# =============================================================================
# Mana cost helper (mirrors AI adapter logic)
# =============================================================================

def get_mana_cost(card) -> int:
    if not card.characteristics or not card.characteristics.mana_cost:
        return 0
    cost_str = card.characteristics.mana_cost
    numbers = re.findall(r'\{(\d+)\}', cost_str)
    return sum(int(n) for n in numbers)


def has_keyword(obj, keyword: str) -> bool:
    """Check if a game object has a keyword ability (charge, taunt, etc)."""
    for ability in (obj.characteristics.abilities or []):
        if isinstance(ability, dict) and ability.get('keyword') == keyword:
            return True
    return False


def can_attack(obj) -> bool:
    """Check if a minion can attack (handles charge/rush)."""
    if obj.state.attacks_this_turn > 0:
        return False
    if not obj.state.summoning_sickness:
        return True
    # Charge and rush bypass summoning sickness
    return has_keyword(obj, 'charge') or has_keyword(obj, 'rush')


# =============================================================================
# Card play / attack helpers (mirrors AI adapter event emission)
# =============================================================================

async def play_card_from_hand(game, player, hand_index: int) -> bool:
    """Play card at hand_index. Returns True if successful."""
    hand = game.get_hand(player.id)
    if hand_index >= len(hand):
        return False

    card = hand[hand_index]
    cost = get_mana_cost(card)

    if player.mana_crystals_available < cost:
        return False

    if CardType.MINION in card.characteristics.types:
        # Check board limit
        battlefield = game.state.zones.get('battlefield')
        if battlefield:
            my_minions = sum(
                1 for oid in battlefield.objects
                if oid in game.state.objects
                and game.state.objects[oid].controller == player.id
                and CardType.MINION in game.state.objects[oid].characteristics.types
            )
            if my_minions >= 7:
                return False

        player.mana_crystals_available -= cost
        zone_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': card.id,
                'from_zone': f'hand_{player.id}',
                'from_zone_type': ZoneType.HAND,
                'to_zone': 'battlefield',
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=card.id,
        )
        game.pipeline.emit(zone_event)
        player.cards_played_this_turn += 1

    elif CardType.SPELL in card.characteristics.types:
        player.mana_crystals_available -= cost

        # Emit spell cast event
        spell_event = Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': card.id, 'caster': player.id},
            source=card.id,
        )
        game.pipeline.emit(spell_event)

        # Execute spell effect
        card_def = card.card_def
        if card_def and card_def.spell_effect:
            try:
                game.pipeline.sba_deferred = True
                effect_events = card_def.spell_effect(card, game.state, [])
                for ev in effect_events:
                    game.pipeline.emit(ev)
            finally:
                game.pipeline.sba_deferred = False
            if hasattr(game.turn_manager, '_check_state_based_actions'):
                await game.turn_manager._check_state_based_actions()

        # Move to graveyard
        zone_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': card.id,
                'from_zone': f'hand_{player.id}',
                'from_zone_type': ZoneType.HAND,
                'to_zone': f'graveyard_{player.id}',
                'to_zone_type': ZoneType.GRAVEYARD,
            },
            source=card.id,
        )
        game.pipeline.emit(zone_event)
        player.cards_played_this_turn += 1

    # SBA check
    if hasattr(game.turn_manager, '_check_state_based_actions'):
        await game.turn_manager._check_state_based_actions()

    return True


async def do_attack(game, player, attacker_index: int, target_str: str, opponent) -> bool:
    """Attack with minion at attacker_index targeting target_str ('hero' or enemy index)."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return False

    # Get all my minions (matching board display indexes)
    my_minions = [
        oid for oid in battlefield.objects
        if oid in game.state.objects
        and game.state.objects[oid].controller == player.id
        and CardType.MINION in game.state.objects[oid].characteristics.types
    ]
    if attacker_index >= len(my_minions):
        return False

    attacker_id = my_minions[attacker_index]
    if not can_attack(game.state.objects[attacker_id]):
        return False

    # Check for taunt
    enemy_minions_with_taunt = [
        oid for oid in battlefield.objects
        if oid in game.state.objects
        and game.state.objects[oid].controller == opponent.id
        and CardType.MINION in game.state.objects[oid].characteristics.types
        and has_keyword(game.state.objects[oid], 'taunt')
    ]

    if target_str.lower() == 'hero':
        if enemy_minions_with_taunt:
            return False  # Must attack taunt first
        target_id = opponent.hero_id
    else:
        enemy_minions = [
            oid for oid in battlefield.objects
            if oid in game.state.objects
            and game.state.objects[oid].controller == opponent.id
            and CardType.MINION in game.state.objects[oid].characteristics.types
        ]
        try:
            t_idx = int(target_str)
        except ValueError:
            return False
        if t_idx >= len(enemy_minions):
            return False
        target_id = enemy_minions[t_idx]
        # If taunt minions exist, can only attack taunt minions
        if enemy_minions_with_taunt and target_id not in enemy_minions_with_taunt:
            return False

    if not target_id:
        return False

    await game.combat_manager.declare_attack(attacker_id, target_id)
    if hasattr(game.turn_manager, '_check_state_based_actions'):
        await game.turn_manager._check_state_based_actions()
    return True


# =============================================================================
# Replay engine
# =============================================================================

async def replay_game(state_data: dict) -> tuple:
    """Replay the game from scratch using the move log."""
    seed = state_data['seed']
    random.seed(seed)

    player_class = state_data['player_class']
    ai_class = state_data['ai_class']
    moves = state_data.get('moves', [])

    game = Game(mode="hearthstone")
    p1 = game.add_player(f"You ({player_class})", life=30)
    p2 = game.add_player(f"AI ({ai_class})", life=30)

    game.setup_hearthstone_player(p1, STORMRIFT_HEROES[player_class], STORMRIFT_HERO_POWERS[player_class])
    game.setup_hearthstone_player(p2, STORMRIFT_HEROES[ai_class], STORMRIFT_HERO_POWERS[ai_class])

    # Fixed shuffle from seed
    deck1 = list(STORMRIFT_DECKS[player_class])
    deck2 = list(STORMRIFT_DECKS[ai_class])
    random.shuffle(deck1)
    random.shuffle(deck2)
    for card_def in deck1:
        game.add_card_to_library(p1.id, card_def)
    for card_def in deck2:
        game.add_card_to_library(p2.id, card_def)

    install_stormrift_modifiers(game)

    ai_adapter = HearthstoneAIAdapter(difficulty="hard")
    game.turn_manager.hearthstone_ai_handler = ai_adapter
    game.turn_manager.ai_players = {p2.id}

    game.get_mulligan_decision = lambda pid, hand, count: True
    await game.start_game()

    # Check who goes first (determined by seeded shuffle in start_game)
    first_player_id = game.turn_manager.turn_order[game.turn_manager.current_player_index]

    if first_player_id == p2.id:
        # AI goes first - run their full turn (draw + main + end, automatic)
        await game.turn_manager.run_turn()

    # Now run human player's draw phase (non-AI: draw only, no auto-actions)
    await game.turn_manager.run_turn()

    # Replay moves
    for move in moves:
        if game.is_game_over() or p1.life <= 0 or p2.life <= 0:
            break

        action = move['action']
        if action == 'play':
            await play_card_from_hand(game, p1, move['hand_index'])
        elif action == 'attack':
            await do_attack(game, p1, move['attacker_index'], move['target'], p2)
        elif action == 'hero_power':
            await game.use_hero_power(p1.id)
        elif action == 'end_turn':
            # End player's turn
            await game.turn_manager.end_turn()
            if game.is_game_over() or p1.life <= 0 or p2.life <= 0:
                break
            # AI's full turn (draw + main + end, all automatic)
            await game.turn_manager.run_turn()
            if game.is_game_over() or p1.life <= 0 or p2.life <= 0:
                break
            # Start next player turn (draw phase)
            await game.turn_manager.run_turn()

    return game, p1, p2


# =============================================================================
# Display
# =============================================================================

def get_game_display(game, p1, p2, state_data) -> str:
    lines = []
    turn = state_data.get('turn_number', 1)
    is_over = p1.has_lost or p2.has_lost or p1.life <= 0 or p2.life <= 0

    lines.append("=" * 64)
    lines.append(f"  STORMRIFT  |  Turn {turn}  |  Rift Storm + Soul Residue + Arcane Feedback")
    lines.append("=" * 64)

    # Opponent
    ai_class = state_data['ai_class']
    ai_hand = game.get_hand(p2.id)
    ai_lib = game.get_library_size(p2.id)
    lines.append(f"\n  OPPONENT: {ai_class}  |  HP: {p2.life}  Armor: {p2.armor}  |  Hand: {len(ai_hand)}  Deck: {ai_lib}")

    # Enemy board
    battlefield = game.state.zones.get('battlefield')
    enemy_minions = []
    if battlefield:
        for oid in battlefield.objects:
            obj = game.state.objects.get(oid)
            if obj and obj.controller == p2.id and CardType.MINION in obj.characteristics.types:
                hp = obj.characteristics.toughness - obj.state.damage
                atk = obj.characteristics.power
                has_taunt = any(isinstance(a, dict) and a.get('keyword') == 'taunt'
                                for a in (obj.characteristics.abilities or []))
                t = " TAUNT" if has_taunt else ""
                enemy_minions.append(f"{obj.name} ({atk}/{hp}){t}")

    if enemy_minions:
        lines.append(f"  Board:")
        for i, m in enumerate(enemy_minions):
            lines.append(f"    [{i}] {m}")
    else:
        lines.append(f"  Board: (empty)")

    lines.append(f"\n  {'─' * 60}")

    # Your board
    my_minions = []
    if battlefield:
        for oid in battlefield.objects:
            obj = game.state.objects.get(oid)
            if obj and obj.controller == p1.id and CardType.MINION in obj.characteristics.types:
                hp = obj.characteristics.toughness - obj.state.damage
                atk = obj.characteristics.power
                has_taunt = any(isinstance(a, dict) and a.get('keyword') == 'taunt'
                                for a in (obj.characteristics.abilities or []))
                t = " TAUNT" if has_taunt else ""
                can_atk = can_attack(obj)
                a = " *READY*" if can_atk and not is_over else ""
                my_minions.append(f"{obj.name} ({atk}/{hp}){t}{a}")

    if my_minions:
        lines.append(f"\n  Your Board:")
        for i, m in enumerate(my_minions):
            lines.append(f"    [{i}] {m}")
    else:
        lines.append(f"\n  Your Board: (empty)")

    # Player stats
    player_class = state_data['player_class']
    my_lib = game.get_library_size(p1.id)
    lines.append(f"\n  YOU: {player_class}  |  HP: {p1.life}  Armor: {p1.armor}  |  Mana: {p1.mana_crystals_available}/{p1.mana_crystals}  Deck: {my_lib}")

    # Hand
    my_hand = game.get_hand(p1.id)
    if my_hand:
        lines.append(f"  Hand:")
        for i, card in enumerate(my_hand):
            cost = get_mana_cost(card)
            is_minion = CardType.MINION in card.characteristics.types
            if is_minion:
                stats = f" ({card.characteristics.power}/{card.characteristics.toughness})"
            else:
                stats = ""
            ctype = "MINION" if is_minion else "SPELL"
            text = (card.card_def.text if card.card_def else "") or ""
            text_s = f'  "{text}"' if text else ""
            playable = "*" if cost <= p1.mana_crystals_available else " "
            lines.append(f"   {playable}[{i}] ({cost}) {card.name}{stats} [{ctype}]{text_s}")
    else:
        lines.append(f"  Hand: (empty)")

    # Hero power
    hp_used = p1.hero_power_used
    hp_name = STORMRIFT_HERO_POWERS[player_class].name
    hp_text = STORMRIFT_HERO_POWERS[player_class].text
    avail = "AVAILABLE" if not hp_used and p1.mana_crystals_available >= 2 else "USED" if hp_used else "NO MANA"
    lines.append(f"\n  Hero Power: {hp_name} (2) - {hp_text} [{avail}]")

    if is_over:
        lines.append(f"\n  {'=' * 60}")
        if p1.life <= 0 or p1.has_lost:
            lines.append(f"  GAME OVER - AI wins! Better luck next time.")
        else:
            lines.append(f"  GAME OVER - YOU WIN!")
        lines.append(f"  {'=' * 60}")

    lines.append("")
    return '\n'.join(lines)


# =============================================================================
# Commands
# =============================================================================

async def cmd_new(player_class: str, ai_class: str, seed: int = None):
    if seed is None:
        seed = random.randint(1, 999999)
    state_data = {
        'player_class': player_class,
        'ai_class': ai_class,
        'seed': seed,
        'moves': [],
        'turn_number': 1,
        'game_over': False,
    }
    save_state(state_data)
    game, p1, p2 = await replay_game(state_data)
    print(get_game_display(game, p1, p2, state_data))


async def cmd_show():
    state_data = load_state()
    if not state_data:
        print("No active game. Start with: new <class> <ai_class>")
        return
    game, p1, p2 = await replay_game(state_data)
    print(get_game_display(game, p1, p2, state_data))


async def cmd_move(action: str, **kwargs):
    state_data = load_state()
    if not state_data:
        print("No active game.")
        return
    if state_data.get('game_over'):
        print("Game is over!")
        return

    move = {'action': action, **kwargs}
    state_data['moves'].append(move)
    if action == 'end_turn':
        state_data['turn_number'] = state_data.get('turn_number', 1) + 1
    save_state(state_data)

    game, p1, p2 = await replay_game(state_data)
    print(get_game_display(game, p1, p2, state_data))

    if p1.has_lost or p2.has_lost or p1.life <= 0 or p2.life <= 0:
        state_data['game_over'] = True
        save_state(state_data)


async def main():
    if len(sys.argv) < 2:
        print("STORMRIFT Interactive Game")
        print("  new <class> <ai_class> [seed]")
        print("  show | play <i> | attack <i> <t|hero> | hero_power | end_turn")
        print("  Classes: Pyromancer, Cryomancer")
        return

    cmd = sys.argv[1].lower()
    if cmd == 'new':
        pc = sys.argv[2] if len(sys.argv) > 2 else "Pyromancer"
        ac = sys.argv[3] if len(sys.argv) > 3 else "Cryomancer"
        seed = int(sys.argv[4]) if len(sys.argv) > 4 else None
        await cmd_new(pc, ac, seed)
    elif cmd == 'show':
        await cmd_show()
    elif cmd == 'play':
        await cmd_move('play', hand_index=int(sys.argv[2]))
    elif cmd == 'attack':
        await cmd_move('attack', attacker_index=int(sys.argv[2]),
                        target=sys.argv[3] if len(sys.argv) > 3 else 'hero')
    elif cmd in ('hero_power', 'hp'):
        await cmd_move('hero_power')
    elif cmd in ('end_turn', 'end', 'pass'):
        await cmd_move('end_turn')
    else:
        print(f"Unknown: {cmd}")

if __name__ == "__main__":
    asyncio.run(main())
