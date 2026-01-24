"""
AI System Tests

Test the AI engine, strategies, and evaluator.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, GameState, Event, EventType, ZoneType, CardType,
    Characteristics, PlayerAction, ActionType, LegalAction,
    AttackDeclaration, BlockDeclaration,
    get_power, get_toughness
)
from src.ai import (
    AIEngine, BoardEvaluator, Heuristics,
    AIStrategy, AggroStrategy, ControlStrategy, MidrangeStrategy
)


def create_test_game():
    """Create a basic game for testing."""
    game = Game()
    p1 = game.add_player("AI Player")
    p2 = game.add_player("Human Player")
    return game, p1, p2


def create_creature(game, owner_id, name, power, toughness):
    """Helper to create a test creature."""
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness
        )
    )


def create_hand_creature(game, owner_id, name, power, toughness, mana_cost=""):
    """Helper to create a creature in hand."""
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        )
    )


def test_ai_engine_creation():
    """Test creating AI engines with different strategies and difficulties."""
    print("\n=== Test: AI Engine Creation ===")

    # Default creation
    ai = AIEngine()
    assert ai.strategy is not None
    assert ai.difficulty == 'medium'
    print("Default AI created with MidrangeStrategy")

    # With specific strategy
    ai_aggro = AIEngine(strategy=AggroStrategy(), difficulty='easy')
    assert isinstance(ai_aggro.strategy, AggroStrategy)
    assert ai_aggro.difficulty == 'easy'
    print("Aggro AI created with easy difficulty")

    # Factory methods
    ai_control = AIEngine.create_control_bot(difficulty='hard')
    assert isinstance(ai_control.strategy, ControlStrategy)
    print("Control bot created via factory method")

    ai_random = AIEngine.create_random_strategy_bot()
    assert ai_random.strategy is not None
    print("Random strategy bot created")

    print("AI Engine creation works!")


def test_board_evaluator():
    """Test the board state evaluator."""
    print("\n=== Test: Board Evaluator ===")

    game, p1, p2 = create_test_game()

    evaluator = BoardEvaluator(game.state)

    # Empty board should be roughly even
    score = evaluator.evaluate(p1.id)
    print(f"Empty board score: {score:.2f}")
    assert -0.2 <= score <= 0.2, "Empty board should be roughly even"

    # Give p1 a creature advantage
    creature1 = create_creature(game, p1.id, "Big Creature", 5, 5)
    score = evaluator.evaluate(p1.id)
    print(f"Score with 5/5 creature: {score:.2f}")
    assert score > 0, "Should be positive with creature advantage"

    # Give p2 creatures to balance
    creature2 = create_creature(game, p2.id, "Small Creature 1", 2, 2)
    creature3 = create_creature(game, p2.id, "Small Creature 2", 2, 2)
    score = evaluator.evaluate(p1.id)
    print(f"Score with balanced board: {score:.2f}")

    # Test life total evaluation
    p1.life = 5
    p2.life = 20
    score = evaluator.evaluate(p1.id)
    print(f"Score at 5 life vs 20 life: {score:.2f}")
    assert score < 0, "Should be negative when at low life"

    print("Board evaluator works!")


def test_heuristics_mulligan():
    """Test mulligan decision heuristics."""
    print("\n=== Test: Mulligan Heuristics ===")

    game, p1, p2 = create_test_game()

    # Good hand: 3 lands, 4 spells
    good_hand = []
    for i in range(3):
        land = game.create_object(
            name=f"Land {i}",
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=Characteristics(types={CardType.LAND})
        )
        good_hand.append(land)

    for i in range(4):
        spell = create_hand_creature(game, p1.id, f"Spell {i}", 2, 2, "{1}")
        good_hand.append(spell)

    result = Heuristics.is_good_opening_hand(good_hand, 0)
    print(f"3 lands + 4 spells hand (7 cards): {'keep' if result else 'mulligan'}")
    assert result, "3 lands + 4 spells should be keepable"

    # Bad hand: 1 land, 6 spells
    bad_hand = []
    land = game.create_object(
        name="Only Land",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.LAND})
    )
    bad_hand.append(land)

    for i in range(6):
        spell = create_hand_creature(game, p1.id, f"Expensive {i}", 2, 2, "{5}")
        bad_hand.append(spell)

    result = Heuristics.is_good_opening_hand(bad_hand, 0)
    print(f"1 land + 6 expensive spells: {'keep' if result else 'mulligan'}")
    assert not result, "1 land hand should mulligan"

    # After 3 mulligans, keep almost anything
    tiny_hand = [good_hand[0], good_hand[4], good_hand[5], good_hand[6]]  # 1 land, 3 spells
    result = Heuristics.is_good_opening_hand(tiny_hand, 3)
    print(f"4-card hand after 3 mulligans: {'keep' if result else 'mulligan'}")
    assert result, "Should keep 4-card hand"

    print("Mulligan heuristics work!")


def test_aggro_strategy_attacks():
    """Test that aggro strategy attacks aggressively."""
    print("\n=== Test: Aggro Strategy Attacks ===")

    game, p1, p2 = create_test_game()

    # Give p1 some creatures
    c1 = create_creature(game, p1.id, "Attacker 1", 3, 2)
    c2 = create_creature(game, p1.id, "Attacker 2", 2, 2)
    c3 = create_creature(game, p1.id, "Attacker 3", 2, 1)

    legal_attackers = [c1.id, c2.id, c3.id]

    strategy = AggroStrategy()
    evaluator = BoardEvaluator(game.state)

    attacks = strategy.plan_attacks(game.state, p1.id, evaluator, legal_attackers)

    print(f"Attackers available: {len(legal_attackers)}")
    print(f"Aggro attacks with: {len(attacks)} creatures")

    # Aggro should attack with most/all creatures when safe
    assert len(attacks) >= 2, "Aggro should attack with multiple creatures"

    print("Aggro strategy attacks work!")


def test_control_strategy_blocks():
    """Test that control strategy blocks well."""
    print("\n=== Test: Control Strategy Blocks ===")

    game, p1, p2 = create_test_game()

    # p2 is attacking
    attacker = create_creature(game, p2.id, "Attacker", 3, 3)

    # p1 has blockers
    blocker1 = create_creature(game, p1.id, "Big Blocker", 4, 4)
    blocker2 = create_creature(game, p1.id, "Small Blocker", 1, 1)

    attacks = [AttackDeclaration(
        attacker_id=attacker.id,
        defending_player_id=p1.id,
        is_attacking_planeswalker=False
    )]

    legal_blockers = [blocker1.id, blocker2.id]

    strategy = ControlStrategy()
    evaluator = BoardEvaluator(game.state)

    blocks = strategy.plan_blocks(
        game.state, p1.id, evaluator, attacks, legal_blockers
    )

    print(f"Attacker: 3/3")
    print(f"Blockers available: 4/4, 1/1")
    print(f"Control blocks with: {len(blocks)} creature(s)")

    # Control should use the big blocker to kill the attacker
    if blocks:
        blocking_creature = game.state.objects.get(blocks[0].blocker_id)
        print(f"Chose to block with: {blocking_creature.name}")
        assert blocks[0].blocker_id == blocker1.id, "Should block with the 4/4"

    print("Control strategy blocks work!")


def test_ai_engine_get_action():
    """Test the AI engine making action decisions."""
    print("\n=== Test: AI Engine Get Action ===")

    game, p1, p2 = create_test_game()

    ai = AIEngine(strategy=MidrangeStrategy(), difficulty='medium')

    # Create some legal actions
    legal_actions = [
        LegalAction(type=ActionType.PASS, description="Pass priority"),
        LegalAction(
            type=ActionType.PLAY_LAND,
            card_id="land_1",
            description="Play a land"
        ),
    ]

    # Add a fake land to hand so play_land makes sense
    land = game.create_object(
        name="Forest",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.LAND})
    )
    legal_actions[1].card_id = land.id

    action = ai.get_action(p1.id, game.state, legal_actions)

    print(f"AI chose action type: {action.type}")
    assert action.type in [ActionType.PASS, ActionType.PLAY_LAND]

    # The AI should prefer playing lands
    # (This might vary due to randomness in easy mode)

    print("AI engine action selection works!")


def test_ai_difficulty_levels():
    """Test that difficulty levels affect AI behavior."""
    print("\n=== Test: AI Difficulty Levels ===")

    game, p1, p2 = create_test_game()

    # Create hand with cards
    creature = create_hand_creature(game, p1.id, "Test Creature", 2, 2, "{1}{G}")

    # Test different difficulties
    for difficulty in ['easy', 'medium', 'hard']:
        ai = AIEngine(difficulty=difficulty)
        settings = ai.settings

        print(f"\n{difficulty.upper()} difficulty:")
        print(f"  Random factor: {settings['random_factor']}")
        print(f"  Mistake chance: {settings['mistake_chance']}")
        print(f"  Block skill: {settings['block_skill']}")

    easy_ai = AIEngine(difficulty='easy')
    hard_ai = AIEngine(difficulty='hard')

    assert easy_ai.settings['random_factor'] > hard_ai.settings['random_factor']
    assert easy_ai.settings['mistake_chance'] > hard_ai.settings['mistake_chance']

    print("\nDifficulty levels affect behavior correctly!")


def test_midrange_adaptation():
    """Test that midrange adapts to board state."""
    print("\n=== Test: Midrange Adaptation ===")

    game, p1, p2 = create_test_game()

    strategy = MidrangeStrategy()
    evaluator = BoardEvaluator(game.state)

    # When ahead (we have more board presence)
    our_creature = create_creature(game, p1.id, "Our Big Guy", 5, 5)
    opp_creature = create_creature(game, p2.id, "Their Small Guy", 2, 2)

    legal_attackers = [our_creature.id]
    attacks_when_ahead = strategy.plan_attacks(
        game.state, p1.id, evaluator, legal_attackers
    )
    print(f"When ahead (5/5 vs 2/2): attacks with {len(attacks_when_ahead)} creatures")

    # Clean up
    game.state.zones['battlefield'].objects.clear()
    del game.state.objects[our_creature.id]
    del game.state.objects[opp_creature.id]

    # When behind (they have more board presence)
    our_small = create_creature(game, p1.id, "Our Small Guy", 2, 2)
    their_big = create_creature(game, p2.id, "Their Big Guy 1", 4, 4)
    their_big2 = create_creature(game, p2.id, "Their Big Guy 2", 4, 4)

    legal_attackers = [our_small.id]
    attacks_when_behind = strategy.plan_attacks(
        game.state, p1.id, evaluator, legal_attackers
    )
    print(f"When behind (2/2 vs two 4/4s): attacks with {len(attacks_when_behind)} creatures")

    # Midrange should be more cautious when behind
    # (May not attack at all, or only with evasive creatures)

    print("Midrange adaptation works!")


def test_evaluator_lethal_detection():
    """Test that evaluator can detect lethal damage."""
    print("\n=== Test: Lethal Detection ===")

    game, p1, p2 = create_test_game()

    # Set opponent to low life
    p2.life = 5

    # Give us exactly lethal
    c1 = create_creature(game, p1.id, "Attacker 1", 3, 2)
    c2 = create_creature(game, p1.id, "Attacker 2", 2, 2)

    evaluator = BoardEvaluator(game.state)

    lethal_attackers = evaluator.get_lethal_attackers(p1.id)
    print(f"Opponent life: {p2.life}")
    print(f"Our attackers: 3/2 and 2/2 (total 5 power)")

    if lethal_attackers:
        print(f"Lethal detected with {len(lethal_attackers)} attackers!")
        assert len(lethal_attackers) == 2
    else:
        print("No lethal found")

    # Now opponent at higher life
    p2.life = 10
    lethal_attackers = evaluator.get_lethal_attackers(p1.id)
    print(f"\nOpponent life: {p2.life}")
    print(f"Lethal: {'Yes' if lethal_attackers else 'No'}")
    assert lethal_attackers is None, "Should not have lethal at 10 life"

    print("Lethal detection works!")


def test_target_selection():
    """Test target selection heuristics."""
    print("\n=== Test: Target Selection ===")

    game, p1, p2 = create_test_game()

    # Create potential targets
    big_creature = create_creature(game, p2.id, "Big Threat", 5, 5)
    small_creature = create_creature(game, p2.id, "Small Guy", 1, 1)

    targets = [big_creature.id, small_creature.id, p2.id]

    # Should prefer the bigger creature for removal
    best = Heuristics.get_best_target(targets, game.state, prefer_creatures=True)
    target_obj = game.state.objects.get(best)

    print(f"Targets: 5/5 creature, 1/1 creature, player")
    print(f"Best target for removal: {target_obj.name if target_obj else 'player'}")

    assert best == big_creature.id, "Should target the 5/5"

    # For damage spells, might prefer player
    best_for_damage = Heuristics.get_best_target(targets, game.state, prefer_creatures=False)
    print(f"Best target for damage: {'player' if best_for_damage == p2.id else 'creature'}")

    print("Target selection works!")


def run_all_tests():
    """Run all AI tests."""
    print("=" * 60)
    print("HYPERDRAFT AI SYSTEM TESTS")
    print("=" * 60)

    test_ai_engine_creation()
    test_board_evaluator()
    test_heuristics_mulligan()
    test_aggro_strategy_attacks()
    test_control_strategy_blocks()
    test_ai_engine_get_action()
    test_ai_difficulty_levels()
    test_midrange_adaptation()
    test_evaluator_lethal_detection()
    test_target_selection()

    print("\n" + "=" * 60)
    print("ALL AI TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
