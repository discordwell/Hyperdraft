"""
STORMRIFT AI vs AI Stress Test

Runs games between Pyromancer and Cryomancer with global modifiers:
  1. Rift Storm   - Start of turn, 1 damage to ALL minions
  2. Soul Residue - First minion death each turn spawns a 1/1 Spirit
  3. Arcane Feedback - Each spell cast pings a random enemy minion for 1

Reports detailed results including crashes, anomalies, and winner distribution.
"""

import asyncio
import sys
import time
import traceback

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine.game import Game
from src.engine.types import EventType, ZoneType, CardType
from src.cards.hearthstone.stormrift import (
    STORMRIFT_HEROES, STORMRIFT_HERO_POWERS, STORMRIFT_DECKS,
    install_stormrift_modifiers,
)
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


async def run_game(class1: str, class2: str, game_number: int, max_turns: int = 50) -> dict:
    """Run a single Stormrift AI vs AI game."""
    result = {
        'game_number': game_number,
        'class1': class1,
        'class2': class2,
        'completed': False,
        'crashed': False,
        'error': None,
        'traceback': None,
        'turn_count': 0,
        'p1_life': 30,
        'p2_life': 30,
        'p1_armor': 0,
        'p2_armor': 0,
        'winner': None,
        'winner_class': None,
        'anomalies': [],
        'mana_history_p1': [],
        'mana_history_p2': [],
        'events_count': 0,
        'duration_ms': 0,
        'p1_minions_final': 0,
        'p2_minions_final': 0,
    }

    start_time = time.time()

    try:
        # Create game in Hearthstone mode
        game = Game(mode="hearthstone")
        p1 = game.add_player(f"Player1_{class1}", life=30)
        p2 = game.add_player(f"Player2_{class2}", life=30)

        # Setup heroes
        game.setup_hearthstone_player(p1, STORMRIFT_HEROES[class1], STORMRIFT_HERO_POWERS[class1])
        game.setup_hearthstone_player(p2, STORMRIFT_HEROES[class2], STORMRIFT_HERO_POWERS[class2])

        # Load decks
        for card_def in STORMRIFT_DECKS[class1]:
            game.add_card_to_library(p1.id, card_def)
        for card_def in STORMRIFT_DECKS[class2]:
            game.add_card_to_library(p2.id, card_def)

        # Shuffle
        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        # Install global modifiers
        install_stormrift_modifiers(game)

        # Setup AI
        ai_adapter = HearthstoneAIAdapter(difficulty="hard")
        game.turn_manager.hearthstone_ai_handler = ai_adapter
        game.turn_manager.ai_players = {p1.id, p2.id}

        # Override mulligan
        game.get_mulligan_decision = lambda pid, hand, count: True

        # Start
        await game.start_game()
        if not game.state.active_player:
            game.state.active_player = p1.id

        total_events = 0
        turn_count = 0

        while turn_count < max_turns:
            turn_count += 1

            if p1.has_lost or p2.has_lost:
                break
            if p1.life <= 0 or p2.life <= 0:
                break

            try:
                turn_events = await game.turn_manager.run_turn()
                total_events += len(turn_events)
            except Exception as e:
                result['anomalies'].append(
                    f"Turn {turn_count}: Exception: {type(e).__name__}: {e}"
                )
                try:
                    game.turn_manager.current_player_index = (
                        game.turn_manager.current_player_index + 1
                    ) % len(game.turn_manager.turn_order)
                except:
                    break

            result['mana_history_p1'].append(p1.mana_crystals)
            result['mana_history_p2'].append(p2.mana_crystals)

            # Anomaly checks
            if p1.mana_crystals_available < 0:
                result['anomalies'].append(f"Turn {turn_count}: P1 negative mana: {p1.mana_crystals_available}")
            if p2.mana_crystals_available < 0:
                result['anomalies'].append(f"Turn {turn_count}: P2 negative mana: {p2.mana_crystals_available}")
            if p1.mana_crystals > 10:
                result['anomalies'].append(f"Turn {turn_count}: P1 mana > 10: {p1.mana_crystals}")
            if p2.mana_crystals > 10:
                result['anomalies'].append(f"Turn {turn_count}: P2 mana > 10: {p2.mana_crystals}")

            battlefield = game.state.zones.get('battlefield')
            if battlefield:
                p1_mc = sum(
                    1 for oid in battlefield.objects
                    if oid in game.state.objects
                    and game.state.objects[oid].controller == p1.id
                    and CardType.MINION in game.state.objects[oid].characteristics.types
                )
                p2_mc = sum(
                    1 for oid in battlefield.objects
                    if oid in game.state.objects
                    and game.state.objects[oid].controller == p2.id
                    and CardType.MINION in game.state.objects[oid].characteristics.types
                )
                if p1_mc > 7:
                    result['anomalies'].append(f"Turn {turn_count}: P1 has {p1_mc} minions (max 7)")
                if p2_mc > 7:
                    result['anomalies'].append(f"Turn {turn_count}: P2 has {p2_mc} minions (max 7)")

            if p1.has_lost or p2.has_lost:
                break
            if p1.life <= 0 or p2.life <= 0:
                break

        # Final state
        result['turn_count'] = turn_count
        result['p1_life'] = p1.life
        result['p2_life'] = p2.life
        result['p1_armor'] = p1.armor
        result['p2_armor'] = p2.armor
        result['events_count'] = total_events

        battlefield = game.state.zones.get('battlefield')
        if battlefield:
            result['p1_minions_final'] = sum(
                1 for oid in battlefield.objects
                if oid in game.state.objects
                and game.state.objects[oid].controller == p1.id
                and CardType.MINION in game.state.objects[oid].characteristics.types
            )
            result['p2_minions_final'] = sum(
                1 for oid in battlefield.objects
                if oid in game.state.objects
                and game.state.objects[oid].controller == p2.id
                and CardType.MINION in game.state.objects[oid].characteristics.types
            )

        # Winner determination
        if p1.has_lost and not p2.has_lost:
            result['winner'] = 'P2'
            result['winner_class'] = class2
        elif p2.has_lost and not p1.has_lost:
            result['winner'] = 'P1'
            result['winner_class'] = class1
        elif p1.life <= 0 and p2.life > 0:
            result['winner'] = 'P2'
            result['winner_class'] = class2
        elif p2.life <= 0 and p1.life > 0:
            result['winner'] = 'P1'
            result['winner_class'] = class1
        elif p1.life <= 0 and p2.life <= 0:
            result['winner'] = 'DRAW (both dead)'
            result['winner_class'] = None
        elif turn_count >= max_turns:
            p1_eff = p1.life + p1.armor
            p2_eff = p2.life + p2.armor
            if p1_eff > p2_eff:
                result['winner'] = 'P1 (timeout)'
                result['winner_class'] = class1
            elif p2_eff > p1_eff:
                result['winner'] = 'P2 (timeout)'
                result['winner_class'] = class2
            else:
                result['winner'] = 'DRAW (timeout)'
                result['winner_class'] = None
        else:
            result['winner'] = 'UNDETERMINED'
            result['winner_class'] = None

        result['completed'] = True

    except Exception as e:
        result['crashed'] = True
        result['error'] = f"{type(e).__name__}: {e}"
        result['traceback'] = traceback.format_exc()

    result['duration_ms'] = int((time.time() - start_time) * 1000)
    return result


async def main():
    print("=" * 80)
    print("  STORMRIFT AI vs AI STRESS TEST")
    print("  Global Modifiers: Rift Storm | Soul Residue | Arcane Feedback")
    print("=" * 80)
    print()
    print("  Rift Storm:      Start of turn, 1 damage to ALL minions")
    print("  Soul Residue:    First minion death each turn -> 1/1 Rift Spirit")
    print("  Arcane Feedback: Each spell cast pings a random enemy minion")
    print()

    matchups = [
        ("Pyromancer", "Cryomancer"),
        ("Cryomancer", "Pyromancer"),
        ("Pyromancer", "Pyromancer"),
        ("Cryomancer", "Cryomancer"),
        ("Pyromancer", "Cryomancer"),
        ("Cryomancer", "Pyromancer"),
        ("Pyromancer", "Cryomancer"),
        ("Cryomancer", "Pyromancer"),
        ("Pyromancer", "Pyromancer"),
        ("Cryomancer", "Cryomancer"),
    ]

    results = []

    for i, (c1, c2) in enumerate(matchups):
        print(f"--- Game {i+1}/10: {c1} vs {c2} ---")
        result = await run_game(c1, c2, i + 1)
        results.append(result)

        if result['crashed']:
            print(f"  CRASHED: {result['error']}")
        elif result['completed']:
            winner_str = result['winner'] or "NONE"
            anomaly_count = len(result['anomalies'])
            print(f"  {result['turn_count']} turns, {result['duration_ms']}ms | "
                  f"P1({c1}): {result['p1_life']}hp+{result['p1_armor']}arm | "
                  f"P2({c2}): {result['p2_life']}hp+{result['p2_armor']}arm | "
                  f"Winner: {winner_str} | Anomalies: {anomaly_count}")
        else:
            print(f"  DID NOT COMPLETE")
        print()

    # Summary
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)

    completed = sum(1 for r in results if r['completed'] and not r['crashed'])
    crashed = sum(1 for r in results if r['crashed'])
    total_anomalies = sum(len(r['anomalies']) for r in results)

    print(f"\n  Games:     {len(results)}")
    print(f"  Completed: {completed}")
    print(f"  Crashed:   {crashed}")
    print(f"  Anomalies: {total_anomalies}")

    turn_counts = [r['turn_count'] for r in results if r['completed']]
    if turn_counts:
        print(f"\n  Turns: min={min(turn_counts)} max={max(turn_counts)} avg={sum(turn_counts)/len(turn_counts):.1f}")

    durations = [r['duration_ms'] for r in results]
    if durations:
        print(f"  Time:  min={min(durations)}ms max={max(durations)}ms avg={sum(durations)/len(durations):.0f}ms total={sum(durations)}ms")

    # Winner distribution
    print(f"\n  WINNER DISTRIBUTION")
    print(f"  {'='*40}")
    class_wins = {}
    for r in results:
        if r['winner_class']:
            class_wins[r['winner_class']] = class_wins.get(r['winner_class'], 0) + 1
    draws = sum(1 for r in results if r['winner'] and 'DRAW' in str(r['winner']))
    for cls, wins in sorted(class_wins.items(), key=lambda x: -x[1]):
        print(f"    {cls}: {wins} win(s)")
    if draws:
        print(f"    Draws: {draws}")
    if not class_wins and not draws:
        print(f"    No winners determined")

    # Per-game details
    print(f"\n  PER-GAME DETAILS")
    print(f"  {'='*40}")
    for r in results:
        status = 'CRASH' if r['crashed'] else 'OK' if r['completed'] else '???'
        winner = r['winner'] or 'NONE'
        print(f"  G{r['game_number']:2d} [{status}] {r['class1']:11s} vs {r['class2']:11s} | "
              f"{r['turn_count']:2d}t {r['duration_ms']:5d}ms | "
              f"P1:{r['p1_life']:3d}hp+{r['p1_armor']:2d}a P2:{r['p2_life']:3d}hp+{r['p2_armor']:2d}a | "
              f"{winner}")
        if r['anomalies']:
            for a in r['anomalies'][:3]:
                print(f"       {a}")
            if len(r['anomalies']) > 3:
                print(f"       ... +{len(r['anomalies'])-3} more")
        if r['crashed'] and r['traceback']:
            for line in r['traceback'].strip().split('\n')[-3:]:
                print(f"       {line}")

    print(f"\n{'='*80}")
    print(f"  STORMRIFT STRESS TEST COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
