"""
Hearthstone AI vs AI Stress Test

Runs 10 games with different hero matchups and reports detailed results
including crashes, turn counts, life totals, mana anomalies, and winner determination.
"""

import asyncio
import sys
import time
import traceback

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine.game import Game
from src.engine.types import EventType, ZoneType, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.decks import HEARTHSTONE_DECKS
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


async def run_game(class1: str, class2: str, game_number: int, max_turns: int = 50) -> dict:
    """
    Run a single AI vs AI Hearthstone game and return results dict.
    """
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
        # Create game
        game = Game(mode="hearthstone")
        p1 = game.add_player(f"Player1_{class1}", life=30)
        p2 = game.add_player(f"Player2_{class2}", life=30)

        # Setup heroes
        game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
        game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])

        # Load decks
        for card_def in HEARTHSTONE_DECKS[class1]:
            game.add_card_to_library(p1.id, card_def)
        for card_def in HEARTHSTONE_DECKS[class2]:
            game.add_card_to_library(p2.id, card_def)

        # Shuffle libraries
        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        # Setup AI for both players
        ai_adapter = HearthstoneAIAdapter(difficulty="hard")
        game.turn_manager.hearthstone_ai_handler = ai_adapter
        game.turn_manager.ai_players = {p1.id, p2.id}

        # Override mulligan to always keep (no lands in Hearthstone)
        game.get_mulligan_decision = lambda pid, hand, count: True

        # Start game
        await game.start_game()

        # Ensure active player is set
        if not game.state.active_player:
            game.state.active_player = p1.id

        total_events = 0
        turn_count = 0

        # Play turns
        while turn_count < max_turns:
            turn_count += 1

            # Check if game is over before starting turn
            if p1.has_lost or p2.has_lost:
                break
            if p1.life <= 0 or p2.life <= 0:
                break

            # Run the turn
            try:
                turn_events = await game.turn_manager.run_turn()
                total_events += len(turn_events)
            except Exception as e:
                result['anomalies'].append(
                    f"Turn {turn_count}: Exception during turn: {type(e).__name__}: {e}"
                )
                # Try to advance to next player
                try:
                    game.turn_manager.current_player_index = (
                        game.turn_manager.current_player_index + 1
                    ) % len(game.turn_manager.turn_order)
                except:
                    break

            # Record mana state
            result['mana_history_p1'].append(p1.mana_crystals)
            result['mana_history_p2'].append(p2.mana_crystals)

            # --- Anomaly checks ---

            # 1. Negative mana available
            if p1.mana_crystals_available < 0:
                result['anomalies'].append(
                    f"Turn {turn_count}: P1 has negative mana available: {p1.mana_crystals_available}"
                )
            if p2.mana_crystals_available < 0:
                result['anomalies'].append(
                    f"Turn {turn_count}: P2 has negative mana available: {p2.mana_crystals_available}"
                )

            # 2. Mana crystals above 10
            if p1.mana_crystals > 10:
                result['anomalies'].append(
                    f"Turn {turn_count}: P1 mana crystals exceed 10: {p1.mana_crystals}"
                )
            if p2.mana_crystals > 10:
                result['anomalies'].append(
                    f"Turn {turn_count}: P2 mana crystals exceed 10: {p2.mana_crystals}"
                )

            # 3. Life below -50 (extreme negative)
            if p1.life < -50:
                result['anomalies'].append(
                    f"Turn {turn_count}: P1 life extremely negative: {p1.life}"
                )
            if p2.life < -50:
                result['anomalies'].append(
                    f"Turn {turn_count}: P2 life extremely negative: {p2.life}"
                )

            # 4. Hand size exceeds max (10 in Hearthstone)
            p1_hand_size = len(game.get_hand(p1.id))
            p2_hand_size = len(game.get_hand(p2.id))
            if p1_hand_size > 10:
                result['anomalies'].append(
                    f"Turn {turn_count}: P1 hand size exceeds 10: {p1_hand_size}"
                )
            if p2_hand_size > 10:
                result['anomalies'].append(
                    f"Turn {turn_count}: P2 hand size exceeds 10: {p2_hand_size}"
                )

            # 5. Battlefield minion count (max 7 in Hearthstone)
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
                    result['anomalies'].append(
                        f"Turn {turn_count}: P1 has {p1_mc} minions (max 7)"
                    )
                if p2_mc > 7:
                    result['anomalies'].append(
                        f"Turn {turn_count}: P2 has {p2_mc} minions (max 7)"
                    )

            # Check for game end
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

        # Count final battlefield minions
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

        # Determine winner
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
            p1_effective = p1.life + p1.armor
            p2_effective = p2.life + p2.armor
            if p1_effective > p2_effective:
                result['winner'] = 'P1 (timeout)'
                result['winner_class'] = class1
            elif p2_effective > p1_effective:
                result['winner'] = 'P2 (timeout)'
                result['winner_class'] = class2
            else:
                result['winner'] = 'DRAW (timeout, tied)'
                result['winner_class'] = None
        else:
            result['winner'] = 'UNDETERMINED'
            result['winner_class'] = None
            result['anomalies'].append("Game ended without a clear winner determination")

        # Validate mana progression: should never decrease
        for pname, mana_hist in [("P1", result['mana_history_p1']), ("P2", result['mana_history_p2'])]:
            prev = 0
            for i, mana in enumerate(mana_hist):
                if mana < prev:
                    result['anomalies'].append(
                        f"Mana regression for {pname} at step {i}: {prev} -> {mana}"
                    )
                prev = mana

        result['completed'] = True

    except Exception as e:
        result['crashed'] = True
        result['error'] = f"{type(e).__name__}: {e}"
        result['traceback'] = traceback.format_exc()

    result['duration_ms'] = int((time.time() - start_time) * 1000)
    return result


async def main():
    print("=" * 80)
    print("  HEARTHSTONE AI vs AI STRESS TEST")
    print("  Running 10 games with different hero matchups")
    print("=" * 80)
    print()

    matchups = [
        ("Mage", "Warrior"),
        ("Hunter", "Paladin"),
        ("Priest", "Rogue"),
        ("Shaman", "Warlock"),
        ("Druid", "Mage"),
        ("Warrior", "Hunter"),
        ("Paladin", "Priest"),
        ("Rogue", "Shaman"),
        ("Warlock", "Druid"),
        ("Mage", "Mage"),
    ]

    results = []

    for i, (c1, c2) in enumerate(matchups):
        print(f"--- Game {i+1}/10: {c1} vs {c2} ---")
        result = await run_game(c1, c2, i + 1)
        results.append(result)

        # Brief inline status
        if result['crashed']:
            print(f"  CRASHED: {result['error']}")
        elif result['completed']:
            winner_str = result['winner'] or "NONE"
            anomaly_count = len(result['anomalies'])
            print(f"  Completed in {result['turn_count']} turns, {result['duration_ms']}ms | "
                  f"P1({c1}): {result['p1_life']}hp+{result['p1_armor']}arm | "
                  f"P2({c2}): {result['p2_life']}hp+{result['p2_armor']}arm | "
                  f"Winner: {winner_str} | Anomalies: {anomaly_count}")
        else:
            print(f"  DID NOT COMPLETE (unknown state)")
        print()

    # =========================================================================
    # Detailed Summary
    # =========================================================================
    print()
    print("=" * 80)
    print("  DETAILED SUMMARY")
    print("=" * 80)

    total_games = len(results)
    completed = sum(1 for r in results if r['completed'] and not r['crashed'])
    crashed = sum(1 for r in results if r['crashed'])
    games_with_winner = sum(1 for r in results if r['winner'] and 'UNDETERMINED' not in (r['winner'] or ''))
    games_with_anomalies = sum(1 for r in results if r['anomalies'])
    total_anomalies = sum(len(r['anomalies']) for r in results)

    print(f"\n  Games run:            {total_games}")
    print(f"  Completed:            {completed}")
    print(f"  Crashed:              {crashed}")
    print(f"  Winner determined:    {games_with_winner}")
    print(f"  Games with anomalies: {games_with_anomalies}")
    print(f"  Total anomalies:      {total_anomalies}")

    # Turn count stats
    turn_counts = [r['turn_count'] for r in results if r['completed']]
    if turn_counts:
        print(f"\n  Turn counts:")
        print(f"    Min:     {min(turn_counts)}")
        print(f"    Max:     {max(turn_counts)}")
        print(f"    Average: {sum(turn_counts) / len(turn_counts):.1f}")

    # Duration stats
    durations = [r['duration_ms'] for r in results]
    if durations:
        print(f"\n  Duration (ms):")
        print(f"    Min:     {min(durations)}")
        print(f"    Max:     {max(durations)}")
        print(f"    Average: {sum(durations) / len(durations):.1f}")
        print(f"    Total:   {sum(durations)}")

    # Per-game details
    print(f"\n  {'='*78}")
    print(f"  PER-GAME DETAILS")
    print(f"  {'='*78}")

    for r in results:
        print(f"\n  Game {r['game_number']}: {r['class1']} vs {r['class2']}")
        print(f"    Status:     {'CRASHED' if r['crashed'] else 'COMPLETED' if r['completed'] else 'UNKNOWN'}")
        print(f"    Turns:      {r['turn_count']}")
        print(f"    Duration:   {r['duration_ms']}ms")
        print(f"    Events:     {r['events_count']}")
        print(f"    P1 ({r['class1']}): {r['p1_life']} life, {r['p1_armor']} armor, {r['p1_minions_final']} minions")
        print(f"    P2 ({r['class2']}): {r['p2_life']} life, {r['p2_armor']} armor, {r['p2_minions_final']} minions")
        print(f"    Winner:     {r['winner'] or 'NONE'} ({r['winner_class'] or 'N/A'})")

        # Mana progression summary
        if r['mana_history_p1']:
            p1_max_mana = max(r['mana_history_p1']) if r['mana_history_p1'] else 0
            p2_max_mana = max(r['mana_history_p2']) if r['mana_history_p2'] else 0
            print(f"    P1 max mana: {p1_max_mana}, P2 max mana: {p2_max_mana}")

        if r['anomalies']:
            print(f"    ANOMALIES ({len(r['anomalies'])}):")
            for a in r['anomalies']:
                print(f"      - {a}")

        if r['crashed'] and r['traceback']:
            print(f"    TRACEBACK:")
            for line in r['traceback'].strip().split('\n'):
                print(f"      {line}")

    # Anomaly summary
    if total_anomalies > 0:
        print(f"\n  {'='*78}")
        print(f"  ANOMALY SUMMARY ({total_anomalies} total)")
        print(f"  {'='*78}")

        categories = {}
        for r in results:
            for a in r['anomalies']:
                if 'negative mana' in a:
                    cat = 'Negative mana available'
                elif 'mana crystals exceed' in a:
                    cat = 'Mana crystals > 10'
                elif 'life extremely negative' in a:
                    cat = 'Life below -50'
                elif 'hand size exceeds' in a:
                    cat = 'Hand size > 10'
                elif 'minions (max 7)' in a:
                    cat = 'Minion count > 7'
                elif 'Mana regression' in a:
                    cat = 'Mana regression'
                elif 'Exception during turn' in a:
                    cat = 'Turn execution exception'
                elif 'winner determination' in a:
                    cat = 'No winner determined'
                else:
                    cat = 'Other'

                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((r['game_number'], a))

        for cat, instances in sorted(categories.items()):
            print(f"\n  [{cat}] - {len(instances)} occurrence(s):")
            for game_num, detail in instances[:5]:
                print(f"    Game {game_num}: {detail}")
            if len(instances) > 5:
                print(f"    ... and {len(instances) - 5} more")

    # Winner distribution
    print(f"\n  {'='*78}")
    print(f"  WINNER DISTRIBUTION")
    print(f"  {'='*78}")

    class_wins = {}
    for r in results:
        if r['winner_class']:
            class_wins[r['winner_class']] = class_wins.get(r['winner_class'], 0) + 1

    if class_wins:
        for cls, wins in sorted(class_wins.items(), key=lambda x: -x[1]):
            print(f"    {cls}: {wins} win(s)")
    else:
        print(f"    No winners determined")

    # Mana progression display
    print(f"\n  {'='*78}")
    print(f"  MANA PROGRESSION VALIDATION")
    print(f"  {'='*78}")

    for r in results:
        if r['completed'] and not r['crashed']:
            p1_hist = r['mana_history_p1']
            p2_hist = r['mana_history_p2']
            if p1_hist:
                p1_display = p1_hist[:20]
                p2_display = p2_hist[:20]
                suffix1 = '...' if len(p1_hist) > 20 else ''
                suffix2 = '...' if len(p2_hist) > 20 else ''
                print(f"  Game {r['game_number']} ({r['class1']} vs {r['class2']}):")
                print(f"    P1 mana: {p1_display}{suffix1}")
                print(f"    P2 mana: {p2_display}{suffix2}")

    print(f"\n{'='*80}")
    print(f"  STRESS TEST COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
