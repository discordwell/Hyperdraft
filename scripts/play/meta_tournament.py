"""
Hearthstone Meta Deck Tournament

Builds classic meta archetype decks from available cards and runs
a round-robin tournament at Ultra difficulty.

Meta archetypes:
  - Zoo Warlock: Low curve, flood board, Knife Juggler synergy, Life Tap
  - Control Mage: Removal-heavy, board clears, Water Elemental, big finishers
  - Face Hunter: Maximum face damage, Charge minions, Steady Shot
  - Midrange Paladin: Balanced curve, buffs, weapons, taunts
  - Tempo Rogue: Backstab tempo, efficient minions, burst finish
"""

import asyncio
import sys
import time
import traceback
from itertools import combinations

sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine.game import Game
from src.engine.types import EventType, ZoneType, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.basic import *
from src.cards.hearthstone.classic import *
from src.cards.hearthstone.decks import validate_deck
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


# =============================================================================
# META ARCHETYPE DECKS
# =============================================================================

# Zoo Warlock: Low curve aggro, flood the board, Knife Juggler synergy
# Life Tap hero power keeps hand full. Win by turn 7-8.
ZOO_WARLOCK = [
    # 0-drops (2) - free board presence
    WISP, WISP,
    # 1-drops (6) - aggressive openers
    LEPER_GNOME, LEPER_GNOME,       # 1/1 deathrattle: 2 face damage
    STONETUSK_BOAR, STONETUSK_BOAR,  # 1/1 charge - immediate damage
    ELVEN_ARCHER, ELVEN_ARCHER,      # 1/1 battlecry: 1 damage (ping)
    # 2-drops (8) - the core
    KNIFE_JUGGLER, KNIFE_JUGGLER,    # 3/2 - triggers off every summon
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,# 3/2 - efficient stats
    ACIDIC_SWAMP_OOZE, ACIDIC_SWAMP_OOZE,  # 3/2 + weapon tech
    LOOT_HOARDER, LOOT_HOARDER,     # 2/1 - deathrattle draw
    # 3-drops (8) - maintain pressure
    RAID_LEADER, RAID_LEADER,        # 2/2 - lord effect: +1 Attack
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,  # 3/2 - buff a minion
    HARVEST_GOLEM, HARVEST_GOLEM,    # 2/3 sticky deathrattle
    WOLFRIDER, WOLFRIDER,            # 3/1 charge - burst damage
    # 4-drops (4) - top end
    CHILLWIND_YETI, CHILLWIND_YETI,  # 4/5 - efficient beater
    SILVERMOON_GUARDIAN, SILVERMOON_GUARDIAN,  # 3/3 divine shield - sticky
    # 5-drops (2) - finishers
    NIGHTBLADE, NIGHTBLADE,          # 4/4 battlecry: 3 face damage
]

# Control Mage: Removal-heavy, board clears, grind out with value
# Fireblast hero power for extra removal. Win in fatigue or with big threats.
CONTROL_MAGE = [
    # Spells (12) - removal suite
    ARCANE_MISSILES, ARCANE_MISSILES,  # 1 mana: 3 random damage
    FROSTBOLT, FROSTBOLT,              # 2 mana: 3 damage + freeze
    ARCANE_INTELLECT, ARCANE_INTELLECT,# 3 mana: draw 2
    FIREBALL, FIREBALL,                # 4 mana: 6 damage (removal or burn)
    POLYMORPH, POLYMORPH,              # 4 mana: hard removal
    FLAMESTRIKE, FLAMESTRIKE,          # 7 mana: board clear (4 to all enemy)
    # 2-drops (4) - early game
    NOVICE_ENGINEER, NOVICE_ENGINEER,  # 1/1 draw a card
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,  # 3/2 stat stick
    # 3-drops (4) - midgame
    HARVEST_GOLEM, HARVEST_GOLEM,      # 2/3 sticky blocker
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,  # 2/2 + 1 damage ping
    # 4-drops (6) - core midgame
    WATER_ELEMENTAL, WATER_ELEMENTAL,  # 3/6 freeze - excellent blocker
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,  # 3/5 taunt
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,# 2/4 draw a card
    # 6-drops (2) - big threats
    BOULDERFIST_OGRE, BOULDERFIST_OGRE,# 6/7 - huge stats
    # 7-drops (2) - finishers
    STORMWIND_CHAMPION, STORMWIND_CHAMPION,  # 6/6 + buff all
]

# Face Hunter: Pure aggro, everything goes face. Steady Shot = 2/turn.
# Win by turn 6-7 or lose.
FACE_HUNTER = [
    # 1-drops (8) - maximum early pressure
    WISP, WISP,                      # 0 mana: free body
    LEPER_GNOME, LEPER_GNOME,       # 1/1 deathrattle: 2 face
    STONETUSK_BOAR, STONETUSK_BOAR,  # 1/1 charge - instant 1 damage
    ELVEN_ARCHER, ELVEN_ARCHER,      # 1/1 + 1 damage
    # 2-drops (8) - efficient damage
    KNIFE_JUGGLER, KNIFE_JUGGLER,    # 3/2 + free damage per summon
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,# 3/2
    LOOT_HOARDER, LOOT_HOARDER,     # 2/1 draw on death
    RIVER_CROCOLISK, RIVER_CROCOLISK,# 2/3 - sticks around
    # 3-drops (8) - burst and pressure
    WOLFRIDER, WOLFRIDER,            # 3/1 charge - 3 instant face
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,  # 2/2 + 1 damage
    RAID_LEADER, RAID_LEADER,        # 2/2 lord +1 attack
    HARVEST_GOLEM, HARVEST_GOLEM,    # 2/3 sticky
    # 5-drops (4) - burn finishers
    NIGHTBLADE, NIGHTBLADE,          # 4/4 + 3 face damage
    STRANGLETHORN_TIGER, STRANGLETHORN_TIGER,  # 5/5 stealth - guaranteed hit
    # 6-drops (2) - charge finishers
    RECKLESS_ROCKETEER, RECKLESS_ROCKETEER,  # 5/2 charge - 5 burst
]

# Midrange Paladin: Balanced curve, buffs, weapons, grind board advantage
# Reinforce hero power fills board gaps. Win by board domination.
MIDRANGE_PALADIN = [
    # Weapons (2) - early removal
    LIGHT_S_JUSTICE, LIGHT_S_JUSTICE,   # 1/4 weapon - 4 pings
    # 1-drops (2) - flex
    ELVEN_ARCHER, ELVEN_ARCHER,         # 1/1 + 1 damage
    # 2-drops (6) - solid early game
    ACIDIC_SWAMP_OOZE, ACIDIC_SWAMP_OOZE,  # 3/2 + weapon tech
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,   # 3/2
    RIVER_CROCOLISK, RIVER_CROCOLISK,   # 2/3
    # 3-drops (6) - buff core
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,  # 3/2 + give +1/+1
    HARVEST_GOLEM, HARVEST_GOLEM,       # 2/3 sticky for buffs
    RAID_LEADER, RAID_LEADER,           # 2/2 lord +1 attack
    # 4-drops (6) - midgame powerhouse
    CHILLWIND_YETI, CHILLWIND_YETI,     # 4/5 best vanilla
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,  # 3/5 taunt
    SILVERMOON_GUARDIAN, SILVERMOON_GUARDIAN,    # 3/3 divine shield
    # 5-drops (2) - big boys
    STORMPIKE_COMMANDO, STORMPIKE_COMMANDO,  # 4/2 + 2 damage
    # 6-drops (4) - top end
    BOULDERFIST_OGRE, BOULDERFIST_OGRE, # 6/7
    LORD_OF_THE_ARENA, LORD_OF_THE_ARENA,  # 6/5 taunt
    # 7-drops (2) - finisher
    STORMWIND_CHAMPION, STORMWIND_CHAMPION,  # 6/6 buff all
]

# Tempo Rogue: Efficient removal + tempo plays, burst finishers
# Dagger Mastery hero power for constant board control.
TEMPO_ROGUE = [
    # 0-drops (2) - tempo
    BACKSTAB, BACKSTAB,              # 0 mana: 2 damage to undamaged
    # 1-drops (4) - aggressive start
    LEPER_GNOME, LEPER_GNOME,       # 1/1 + 2 face deathrattle
    STONETUSK_BOAR, STONETUSK_BOAR,  # 1/1 charge
    # 2-drops (8) - efficient bodies
    KNIFE_JUGGLER, KNIFE_JUGGLER,    # 3/2 + free damage
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,# 3/2
    LOOT_HOARDER, LOOT_HOARDER,     # 2/1 draw
    ACIDIC_SWAMP_OOZE, ACIDIC_SWAMP_OOZE,  # 3/2 + weapon hate
    # 3-drops (8) - maintain tempo
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,  # 3/2 + buff
    HARVEST_GOLEM, HARVEST_GOLEM,    # 2/3 sticky
    WOLFRIDER, WOLFRIDER,            # 3/1 charge
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,  # 2/2 + ping
    # 4-drops (4) - solid midgame
    CHILLWIND_YETI, CHILLWIND_YETI,  # 4/5
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,  # 2/4 draw
    # 5-drops (2) - burst
    NIGHTBLADE, NIGHTBLADE,          # 4/4 + 3 face
    # 6-drops (2) - finishers
    ARGENT_COMMANDER, ARGENT_COMMANDER,  # 4/2 charge + divine shield
]


# =============================================================================
# DECK REGISTRY
# =============================================================================
META_DECKS = {
    "Zoo Warlock": ("Warlock", ZOO_WARLOCK),
    "Control Mage": ("Mage", CONTROL_MAGE),
    "Face Hunter": ("Hunter", FACE_HUNTER),
    "Midrange Paladin": ("Paladin", MIDRANGE_PALADIN),
    "Tempo Rogue": ("Rogue", TEMPO_ROGUE),
}


async def run_game(deck1_name: str, deck2_name: str, game_number: int,
                   difficulty: str = "ultra", max_turns: int = 50) -> dict:
    """Run a single meta deck vs meta deck game."""
    class1, cards1 = META_DECKS[deck1_name]
    class2, cards2 = META_DECKS[deck2_name]

    result = {
        'game_number': game_number,
        'deck1': deck1_name,
        'deck2': deck2_name,
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
        'winner_deck': None,
        'anomalies': [],
        'events_count': 0,
        'duration_ms': 0,
        'p1_minions_final': 0,
        'p2_minions_final': 0,
    }

    start_time = time.time()

    try:
        game = Game(mode="hearthstone")
        p1 = game.add_player(f"P1_{deck1_name}", life=30)
        p2 = game.add_player(f"P2_{deck2_name}", life=30)

        game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
        game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])

        for card_def in cards1:
            game.add_card_to_library(p1.id, card_def)
        for card_def in cards2:
            game.add_card_to_library(p2.id, card_def)

        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        ai_adapter = HearthstoneAIAdapter(difficulty=difficulty)
        game.turn_manager.hearthstone_ai_handler = ai_adapter
        game.turn_manager.ai_players = {p1.id, p2.id}
        game.get_mulligan_decision = lambda pid, hand, count: True

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
                    f"Turn {turn_count}: {type(e).__name__}: {e}"
                )
                try:
                    game.turn_manager.current_player_index = (
                        game.turn_manager.current_player_index + 1
                    ) % len(game.turn_manager.turn_order)
                except:
                    break

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
                for pid, pname in [(p1.id, "P1"), (p2.id, "P2")]:
                    mc = sum(
                        1 for oid in battlefield.objects
                        if oid in game.state.objects
                        and game.state.objects[oid].controller == pid
                        and CardType.MINION in game.state.objects[oid].characteristics.types
                    )
                    if mc > 7:
                        result['anomalies'].append(f"Turn {turn_count}: {pname} has {mc} minions")

            if p1.has_lost or p2.has_lost:
                break
            if p1.life <= 0 or p2.life <= 0:
                break

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

        # Determine winner
        if p1.has_lost and not p2.has_lost:
            result['winner'] = 'P2'
            result['winner_deck'] = deck2_name
        elif p2.has_lost and not p1.has_lost:
            result['winner'] = 'P1'
            result['winner_deck'] = deck1_name
        elif p1.life <= 0 and p2.life > 0:
            result['winner'] = 'P2'
            result['winner_deck'] = deck2_name
        elif p2.life <= 0 and p1.life > 0:
            result['winner'] = 'P1'
            result['winner_deck'] = deck1_name
        elif p1.life <= 0 and p2.life <= 0:
            result['winner'] = 'DRAW'
            result['winner_deck'] = None
        elif turn_count >= max_turns:
            p1e = p1.life + p1.armor
            p2e = p2.life + p2.armor
            if p1e > p2e:
                result['winner'] = 'P1 (timeout)'
                result['winner_deck'] = deck1_name
            elif p2e > p1e:
                result['winner'] = 'P2 (timeout)'
                result['winner_deck'] = deck2_name
            else:
                result['winner'] = 'DRAW (timeout)'
                result['winner_deck'] = None
        else:
            result['winner'] = 'UNDETERMINED'

        result['completed'] = True

    except Exception as e:
        result['crashed'] = True
        result['error'] = f"{type(e).__name__}: {e}"
        result['traceback'] = traceback.format_exc()

    result['duration_ms'] = int((time.time() - start_time) * 1000)
    return result


async def main():
    print("=" * 80)
    print("  HEARTHSTONE META DECK TOURNAMENT")
    print("  Round-Robin at Ultra Difficulty (best of 3 per matchup)")
    print("=" * 80)
    print()

    # Validate all decks
    for name, (hero_class, deck) in META_DECKS.items():
        valid, err = validate_deck(deck)
        if not valid:
            print(f"  INVALID DECK: {name}: {err}")
            return
        print(f"  {name} ({hero_class}): {len(deck)} cards - VALID")
    print()

    # Round-robin: every deck plays every other deck (best of 3)
    deck_names = list(META_DECKS.keys())
    matchups = list(combinations(deck_names, 2))

    # Track wins for standings
    deck_wins = {name: 0 for name in deck_names}
    deck_losses = {name: 0 for name in deck_names}
    deck_draws = {name: 0 for name in deck_names}
    matchup_results = {}

    game_num = 0
    total_games = len(matchups) * 3  # best of 3

    for d1, d2 in matchups:
        print(f"{'='*60}")
        print(f"  MATCHUP: {d1} vs {d2} (Best of 3)")
        print(f"{'='*60}")

        series_wins = {d1: 0, d2: 0}

        for game_in_series in range(3):
            game_num += 1
            # Alternate who goes first
            if game_in_series % 2 == 0:
                first, second = d1, d2
            else:
                first, second = d2, d1

            print(f"\n  Game {game_in_series+1}/3 (#{game_num}/{total_games}): {first} (P1) vs {second} (P2)")
            result = await run_game(first, second, game_num)

            if result['crashed']:
                print(f"    CRASHED: {result['error']}")
                if result['traceback']:
                    for line in result['traceback'].strip().split('\n')[-3:]:
                        print(f"      {line}")
            elif result['completed']:
                winner_str = result['winner_deck'] or result['winner']
                anom = len(result['anomalies'])
                print(f"    {result['turn_count']} turns, {result['duration_ms']}ms | "
                      f"P1({first}): {result['p1_life']}hp+{result['p1_armor']}arm [{result['p1_minions_final']}min] | "
                      f"P2({second}): {result['p2_life']}hp+{result['p2_armor']}arm [{result['p2_minions_final']}min] | "
                      f"Winner: {winner_str} | Anomalies: {anom}")

                if result['anomalies']:
                    for a in result['anomalies'][:3]:
                        print(f"      ! {a}")
                    if len(result['anomalies']) > 3:
                        print(f"      ... +{len(result['anomalies'])-3} more")

                # Record series wins
                if result['winner_deck'] == first:
                    series_wins[d1 if first == d1 else d2] += 1
                elif result['winner_deck'] == second:
                    series_wins[d2 if second == d2 else d1] += 1

        # Determine series winner
        if series_wins[d1] > series_wins[d2]:
            series_winner = d1
            series_loser = d2
            deck_wins[d1] += 1
            deck_losses[d2] += 1
            print(f"\n  >> SERIES WINNER: {d1} ({series_wins[d1]}-{series_wins[d2]})")
        elif series_wins[d2] > series_wins[d1]:
            series_winner = d2
            series_loser = d1
            deck_wins[d2] += 1
            deck_losses[d1] += 1
            print(f"\n  >> SERIES WINNER: {d2} ({series_wins[d2]}-{series_wins[d1]})")
        else:
            series_winner = "DRAW"
            series_loser = None
            deck_draws[d1] += 1
            deck_draws[d2] += 1
            print(f"\n  >> SERIES DRAW ({series_wins[d1]}-{series_wins[d2]})")

        matchup_results[(d1, d2)] = {
            'wins_d1': series_wins[d1],
            'wins_d2': series_wins[d2],
            'series_winner': series_winner,
        }
        print()

    # ==========================================================================
    # TOURNAMENT STANDINGS
    # ==========================================================================
    print()
    print("=" * 80)
    print("  TOURNAMENT STANDINGS")
    print("=" * 80)
    print()
    print(f"  {'Deck':<25} {'W':>3} {'L':>3} {'D':>3} {'Win%':>6}")
    print(f"  {'-'*25} {'-'*3} {'-'*3} {'-'*3} {'-'*6}")

    standings = sorted(
        deck_names,
        key=lambda d: (deck_wins[d], -deck_losses[d]),
        reverse=True
    )

    for deck in standings:
        total = deck_wins[deck] + deck_losses[deck] + deck_draws[deck]
        win_pct = (deck_wins[deck] / total * 100) if total > 0 else 0
        print(f"  {deck:<25} {deck_wins[deck]:>3} {deck_losses[deck]:>3} {deck_draws[deck]:>3} {win_pct:>5.1f}%")

    # Head-to-head matrix
    print()
    print("=" * 80)
    print("  HEAD-TO-HEAD RESULTS")
    print("=" * 80)
    print()

    for (d1, d2), res in matchup_results.items():
        winner = res['series_winner']
        print(f"  {d1} vs {d2}: {res['wins_d1']}-{res['wins_d2']} -> {winner}")

    print()
    print("=" * 80)
    print("  META TOURNAMENT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
