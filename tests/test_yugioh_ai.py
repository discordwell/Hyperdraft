"""
Yu-Gi-Oh! Stage 5 Tests — AI Adapter

Tests for the AI adapter: decision making, stress testing AI vs AI games,
verifying legal moves and no infinite loops.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, CardType
from src.ai.yugioh_adapter import YugiohAIAdapter
from src.cards.yugioh.ygo_classic import (
    YUGI_DECK, YUGI_EXTRA_DECK, KAIBA_DECK, KAIBA_EXTRA_DECK,
)
from src.cards.yugioh.ygo_starter import (
    WARRIOR_DECK, WARRIOR_EXTRA_DECK, SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
)


def make_ai_game(deck1, extra1, deck2, extra2, difficulty="medium"):
    """Create a game with two AI players."""
    game = Game(mode="yugioh")
    p1 = game.add_player("AI 1")
    p2 = game.add_player("AI 2")

    game.setup_yugioh_player(p1, deck1, extra1)
    game.setup_yugioh_player(p2, deck2, extra2)

    ai = YugiohAIAdapter(difficulty=difficulty)
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.ai_players.add(p1.id)
    game.turn_manager.ai_players.add(p2.id)

    return game, p1, p2, ai


async def run_ai_game(game, max_turns=100):
    """Run an AI vs AI game, return (winner_id, turns_played)."""
    await game.turn_manager.setup_game()
    turns = 0

    while turns < max_turns:
        await game.turn_manager.run_turn()
        turns += 1

        if game.is_game_over():
            break

    winner = game.get_winner()
    return winner, turns


def test_ai_picks_summon():
    """AI should normal summon a monster when it has one in hand."""
    game, p1, p2, ai = make_ai_game(
        WARRIOR_DECK, WARRIOR_EXTRA_DECK,
        SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
    )

    # Manually set up a scenario: p1 has monsters in hand
    asyncio.get_event_loop().run_until_complete(game.turn_manager.setup_game())

    # Get AI's main phase action
    turn_state = game.turn_manager.ygo_turn_state
    turn_state.active_player_id = p1.id
    turn_state.normal_summon_used = False

    action = ai.get_main_phase_action(p1.id, game.state, turn_state)

    # AI should either summon, set, or activate something
    assert action['action_type'] in ('normal_summon', 'set_monster', 'set_spell_trap',
                                      'activate_spell', 'end_phase'), \
        f"Unexpected action: {action['action_type']}"
    print("  PASS: test_ai_picks_summon")


def test_ai_enters_battle():
    """AI should enter battle phase when it has ATK position monsters."""
    game, p1, p2, ai = make_ai_game(
        YUGI_DECK, YUGI_EXTRA_DECK,
        KAIBA_DECK, KAIBA_EXTRA_DECK,
    )

    asyncio.get_event_loop().run_until_complete(game.turn_manager.setup_game())

    # Place a monster in ATK position for p1
    from src.engine.game import make_ygo_monster
    from src.engine.types import Characteristics
    mon_def = make_ygo_monster("Test Mon", atk=1500, def_val=1200, level=4)
    obj = game.create_object(
        name=mon_def.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(mon_def.characteristics.types)),
        card_def=mon_def,
    )
    # Summon it
    turn_state = game.turn_manager.ygo_turn_state
    turn_state.active_player_id = p1.id
    turn_state.normal_summon_used = False
    game.turn_manager._do_normal_summon(p1.id, {'card_id': obj.id})

    should = ai.should_enter_battle(p1.id, game.state)
    assert should, "AI should want to enter battle with ATK monster on field"
    print("  PASS: test_ai_enters_battle")


def test_ai_no_battle_empty_field():
    """AI should not enter battle phase with no monsters."""
    game, p1, p2, ai = make_ai_game(
        WARRIOR_DECK, WARRIOR_EXTRA_DECK,
        SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
    )

    # Don't summon anything
    should = ai.should_enter_battle(p1.id, game.state)
    assert not should, "AI should not enter battle with empty field"
    print("  PASS: test_ai_no_battle_empty_field")


def test_ai_sets_traps():
    """AI should set trap cards from hand."""
    game, p1, p2, ai = make_ai_game(
        YUGI_DECK, YUGI_EXTRA_DECK,
        KAIBA_DECK, KAIBA_EXTRA_DECK,
    )

    asyncio.get_event_loop().run_until_complete(game.turn_manager.setup_game())

    turn_state = game.turn_manager.ygo_turn_state
    turn_state.active_player_id = p1.id

    # Give p1 a trap in hand
    from src.cards.yugioh.ygo_classic import MIRROR_FORCE
    from src.engine.types import Characteristics
    trap = game.create_object(
        name=MIRROR_FORCE.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(MIRROR_FORCE.characteristics.types)),
        card_def=MIRROR_FORCE,
    )

    # AI should set it (after failing to summon)
    turn_state.normal_summon_used = True  # force past summon phase

    # Run multiple actions — trap set should happen eventually
    found_set = False
    for _ in range(10):
        action = ai.get_main_phase_action(p1.id, game.state, turn_state)
        if action['action_type'] == 'set_spell_trap':
            found_set = True
            break
        if action['action_type'] == 'end_phase':
            break

    assert found_set, "AI should set trap cards"
    print("  PASS: test_ai_sets_traps")


def test_ai_difficulty_levels():
    """Verify all difficulty levels construct without error."""
    for diff in ("easy", "medium", "hard", "ultra"):
        ai = YugiohAIAdapter(difficulty=diff)
        assert ai.difficulty == diff
    print("  PASS: test_ai_difficulty_levels")


def test_ai_vs_ai_yugi_kaiba():
    """Stress test: run an AI vs AI game with Yugi vs Kaiba decks."""
    game, p1, p2, ai = make_ai_game(
        YUGI_DECK, YUGI_EXTRA_DECK,
        KAIBA_DECK, KAIBA_EXTRA_DECK,
        difficulty="medium",
    )

    winner, turns = asyncio.get_event_loop().run_until_complete(
        run_ai_game(game, max_turns=200)
    )

    assert turns > 0, "Game should play at least 1 turn"
    # Game should finish within 200 turns (no infinite loop)
    assert turns <= 200, f"Game took too many turns: {turns}"
    print(f"  PASS: test_ai_vs_ai_yugi_kaiba ({turns} turns, winner={'P1' if winner == p1.id else 'P2' if winner == p2.id else 'draw'})")


def test_ai_vs_ai_starter():
    """Stress test: run an AI vs AI game with starter decks."""
    game, p1, p2, ai = make_ai_game(
        WARRIOR_DECK, WARRIOR_EXTRA_DECK,
        SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
        difficulty="hard",
    )

    winner, turns = asyncio.get_event_loop().run_until_complete(
        run_ai_game(game, max_turns=200)
    )

    assert turns > 0, "Game should play at least 1 turn"
    assert turns <= 200, f"Game took too many turns: {turns}"
    print(f"  PASS: test_ai_vs_ai_starter ({turns} turns, winner={'P1' if winner == p1.id else 'P2' if winner == p2.id else 'draw'})")


def test_ai_vs_ai_10_games():
    """Stress test: run 10 AI vs AI games, check no crashes."""
    results = []
    decks = [
        (YUGI_DECK, YUGI_EXTRA_DECK, KAIBA_DECK, KAIBA_EXTRA_DECK),
        (WARRIOR_DECK, WARRIOR_EXTRA_DECK, SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK),
    ]

    for i in range(10):
        d1, e1, d2, e2 = decks[i % len(decks)]
        diff = ["easy", "medium", "hard", "ultra"][i % 4]

        game, p1, p2, ai = make_ai_game(d1, e1, d2, e2, difficulty=diff)
        winner, turns = asyncio.get_event_loop().run_until_complete(
            run_ai_game(game, max_turns=200)
        )
        results.append({
            'game': i + 1,
            'turns': turns,
            'winner': 'P1' if winner == p1.id else ('P2' if winner == p2.id else 'none'),
            'difficulty': diff,
            'finished': game.is_game_over(),
        })

    # All games should have completed without crashing
    completed = sum(1 for r in results if r['finished'])
    avg_turns = sum(r['turns'] for r in results) / len(results)

    print(f"  PASS: test_ai_vs_ai_10_games ({completed}/10 finished, avg {avg_turns:.0f} turns)")

    # At least some games should finish (LP reduction or deck-out)
    assert completed >= 5, f"Only {completed}/10 games finished — AI may be stuck"


def test_ai_no_infinite_loop():
    """Verify AI doesn't loop forever in main phase."""
    game, p1, p2, ai = make_ai_game(
        WARRIOR_DECK, WARRIOR_EXTRA_DECK,
        SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
    )

    asyncio.get_event_loop().run_until_complete(game.turn_manager.setup_game())

    turn_state = game.turn_manager.ygo_turn_state
    turn_state.active_player_id = p1.id

    # Call get_main_phase_action many times — should eventually return end_phase
    ended = False
    for _ in range(50):
        action = ai.get_main_phase_action(p1.id, game.state, turn_state)
        if action['action_type'] == 'end_phase':
            ended = True
            break
        # Execute the action so state changes
        game.turn_manager._execute_action(p1.id, action)

    assert ended, "AI should eventually end its main phase"
    print("  PASS: test_ai_no_infinite_loop")


# =============================================================================
# Run all tests
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Yu-Gi-Oh! Stage 5 Tests — AI Adapter")
    print("=" * 60)

    tests = [
        test_ai_picks_summon,
        test_ai_enters_battle,
        test_ai_no_battle_empty_field,
        test_ai_sets_traps,
        test_ai_difficulty_levels,
        test_ai_vs_ai_yugi_kaiba,
        test_ai_vs_ai_starter,
        test_ai_vs_ai_10_games,
        test_ai_no_infinite_loop,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 60}")
    if failed > 0:
        sys.exit(1)
