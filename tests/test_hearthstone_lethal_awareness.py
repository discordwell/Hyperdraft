"""
Hearthstone AI Lethal Awareness & Prevention Tests

Tests for the AI's ability to detect opponent lethal threats,
enter survival mode, and make defensive decisions.
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


def _setup_game(hero1="Warrior", hero2="Mage"):
    """Create a game with two players and heroes."""
    game = Game(mode="hearthstone")
    p1 = game.add_player("Player 1", life=30)
    p2 = game.add_player("Player 2", life=30)
    game.setup_hearthstone_player(p1, HEROES[hero1], HERO_POWERS[hero1])
    game.setup_hearthstone_player(p2, HEROES[hero2], HERO_POWERS[hero2])
    return game, p1, p2


def _add_minion(game, owner_id, power, toughness, keywords=None):
    """Add a minion to the battlefield."""
    abilities = []
    if keywords:
        for kw in keywords:
            abilities.append({'keyword': kw})
    minion = game.create_object(
        name=f"Test Minion {power}/{toughness}",
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
    )
    minion.characteristics.types = {CardType.MINION}
    minion.characteristics.power = power
    minion.characteristics.toughness = toughness
    minion.characteristics.abilities = abilities
    return minion


def test_opponent_lethal_detected_from_board():
    """Opponent has enough attack on board to kill us."""
    game, p1, p2 = _setup_game()
    adapter = HearthstoneAIAdapter(difficulty="hard")

    # P1 (Warrior) at 8 HP, 0 armor
    p1.life = 8
    p1.armor = 0

    # P2 has two 5/5 minions = 10 attack, enough to kill P1
    _add_minion(game, p2.id, 5, 5)
    _add_minion(game, p2.id, 5, 5)

    lethal_info = adapter._estimate_opponent_lethal(p1.id, game.state)
    assert lethal_info['is_lethal'], "Should detect opponent has lethal from board"
    assert lethal_info['board_damage'] == 10
    assert lethal_info['total_damage'] >= 10


def test_own_taunts_block_opponent_lethal():
    """Our taunts should reduce opponent's effective damage."""
    game, p1, p2 = _setup_game()
    adapter = HearthstoneAIAdapter(difficulty="hard")

    # P1 at 8 HP
    p1.life = 8
    p1.armor = 0

    # P2 has 10 damage on board
    _add_minion(game, p2.id, 5, 5)
    _add_minion(game, p2.id, 5, 5)

    # P1 has a 0/5 taunt — absorbs 5 damage, so only 5 gets through
    _add_minion(game, p1.id, 0, 5, keywords=['taunt'])

    lethal_info = adapter._estimate_opponent_lethal(p1.id, game.state)
    assert not lethal_info['is_lethal'], "Taunt wall should prevent lethal"
    assert lethal_info['board_damage'] == 5  # 10 attack - 5 taunt HP = 5 through


def test_survival_mode_scores_taunt_higher():
    """In survival mode, taunt minions should get a significant scoring bonus."""
    game, p1, p2 = _setup_game()
    adapter = HearthstoneAIAdapter(difficulty="hard")

    # P1 at 5 HP, facing lethal
    p1.life = 5
    p1.armor = 0
    p1.mana_crystals_available = 10

    # P2 has 8 damage on board
    _add_minion(game, p2.id, 4, 4)
    _add_minion(game, p2.id, 4, 4)

    # Create two cards in hand: a vanilla 3/3 and a taunt 2/4
    vanilla = game.create_object(name="Vanilla 3/3", owner_id=p1.id, zone=ZoneType.HAND)
    vanilla.characteristics.types = {CardType.MINION}
    vanilla.characteristics.power = 3
    vanilla.characteristics.toughness = 3
    vanilla.characteristics.mana_cost = "{3}"
    vanilla.characteristics.abilities = []

    taunt = game.create_object(name="Taunt 2/4", owner_id=p1.id, zone=ZoneType.HAND)
    taunt.characteristics.types = {CardType.MINION}
    taunt.characteristics.power = 2
    taunt.characteristics.toughness = 4
    taunt.characteristics.mana_cost = "{3}"
    taunt.characteristics.abilities = [{'keyword': 'taunt'}]

    # Verify survival mode is active
    assert adapter._is_in_survival_mode(p1.id, game.state), "Should be in survival mode"

    vanilla_score = adapter._score_card_play(vanilla, game.state, p1.id)
    taunt_score = adapter._score_card_play(taunt, game.state, p1.id)

    assert taunt_score > vanilla_score + 30, (
        f"Taunt ({taunt_score}) should score much higher than vanilla ({vanilla_score}) in survival mode"
    )


def test_survival_mode_triggers_early_armor_hero_power():
    """In survival mode, armor hero power should fire early (before card plays)."""
    game, p1, p2 = _setup_game(hero1="Warrior")
    adapter = HearthstoneAIAdapter(difficulty="hard")

    # P1 at 4 HP, facing lethal
    p1.life = 4
    p1.armor = 0
    p1.mana_crystals_available = 5
    p1.hero_power_used = False

    # P2 has 6 damage on board
    _add_minion(game, p2.id, 3, 3)
    _add_minion(game, p2.id, 3, 3)

    should_early = adapter._should_use_hero_power_early(game.state, p1.id)
    assert should_early, "Armor hero power should trigger early in survival mode"


def test_survival_mode_does_not_skip_heal():
    """In survival mode, heal hero power should not be skipped even at full HP edge cases."""
    game, p1, p2 = _setup_game(hero1="Priest")
    adapter = HearthstoneAIAdapter(difficulty="hard")

    # P1 at low HP but NOT full — but normally skipped if no damaged friendlies
    # Actually test the real scenario: life < max_life so heal is useful,
    # but facing lethal so it should definitely not be skipped
    p1.life = 6
    p1.armor = 0
    p1.mana_crystals_available = 5
    p1.hero_power_used = False

    # P2 has enough damage
    _add_minion(game, p2.id, 4, 4)
    _add_minion(game, p2.id, 4, 4)

    should_use = adapter._should_use_hero_power(game.state, p1.id)
    assert should_use, "Should use heal hero power when facing lethal"


def test_lethal_first_burn_spell_scoring():
    """Ultra should massively boost burn spells when having lethal."""
    game, p1, p2 = _setup_game(hero1="Mage")
    adapter = HearthstoneAIAdapter(difficulty="ultra")

    # P1 has a 5/5 on board (can attack), P2 at 8 HP → 5 + 3 burn = 8 = lethal
    p1.life = 30
    p1.mana_crystals_available = 10
    attacker = _add_minion(game, p1.id, 5, 5)
    attacker.state.summoning_sickness = False  # Can attack
    p2.life = 8
    p2.armor = 0

    # Create a burn spell in hand: "Deal 3 damage"
    from src.engine.types import CardDefinition, Characteristics
    burn_def = CardDefinition(
        name="Fireball",
        mana_cost="{4}",
        characteristics=Characteristics(types={CardType.SPELL}, mana_cost="{4}"),
        text="Deal 3 damage to a target.",
    )
    burn = game.create_object(name="Fireball", owner_id=p1.id, zone=ZoneType.HAND)
    burn.characteristics.types = {CardType.SPELL}
    burn.characteristics.mana_cost = "{4}"
    burn.characteristics.abilities = []
    burn.card_def = burn_def

    score = adapter._score_card_play(burn, game.state, p1.id)
    # Should have +100 lethal bonus
    assert score >= 100, f"Burn spell should score >= 100 with lethal (got {score})"


def test_charge_minion_enables_lethal_detection():
    """Ultra should detect that a charge minion in hand enables lethal."""
    game, p1, p2 = _setup_game()
    adapter = HearthstoneAIAdapter(difficulty="ultra")

    # P1 has a 3/3 on board, P2 at 7 HP
    p1.life = 30
    p1.mana_crystals_available = 10
    _add_minion(game, p1.id, 3, 3)
    p2.life = 7
    p2.armor = 0

    # Charge minion with 4 attack in hand — 3 (board) + 4 (charge) = 7 = lethal
    charge = game.create_object(name="Charge Minion", owner_id=p1.id, zone=ZoneType.HAND)
    charge.characteristics.types = {CardType.MINION}
    charge.characteristics.power = 4
    charge.characteristics.toughness = 2
    charge.characteristics.mana_cost = "{4}"
    charge.characteristics.abilities = [{'keyword': 'charge'}]

    score = adapter._score_card_play(charge, game.state, p1.id)
    # Should get the +90 enables-lethal bonus
    assert score >= 90, f"Charge minion enabling lethal should score >= 90 (got {score})"


def test_survival_mode_prefers_trades_over_face():
    """In survival mode, the AI should trade into enemy minions instead of going face."""
    game, p1, p2 = _setup_game()
    adapter = HearthstoneAIAdapter(difficulty="hard")

    # P1 at 6 HP facing lethal
    p1.life = 6
    p1.armor = 0

    # P2 has a 4/4 and a 3/3 (7 damage = lethal)
    enemy_big = _add_minion(game, p2.id, 4, 4)
    enemy_small = _add_minion(game, p2.id, 3, 3)

    # P1 has a 4/5 that can attack
    attacker = _add_minion(game, p1.id, 4, 5)
    attacker.state.summoning_sickness = False

    target = adapter._choose_attack_target(attacker.id, game.state, p1.id)

    # Should trade into the 4/4 (highest threat), NOT go face
    assert target == enemy_big.id, (
        f"Should trade into highest threat minion in survival mode, "
        f"got target={target}, expected={enemy_big.id}"
    )


def test_hard_has_lethal_prevention_medium_does_not():
    """Hard difficulty should have lethal prevention, medium should not."""
    game, p1, p2 = _setup_game()

    hard_adapter = HearthstoneAIAdapter(difficulty="hard")
    medium_adapter = HearthstoneAIAdapter(difficulty="medium")

    # P1 at 5 HP, facing lethal
    p1.life = 5
    p1.armor = 0

    _add_minion(game, p2.id, 5, 5)
    _add_minion(game, p2.id, 5, 5)

    assert hard_adapter._is_in_survival_mode(p1.id, game.state), \
        "Hard should detect survival mode"
    assert not medium_adapter._is_in_survival_mode(p1.id, game.state), \
        "Medium should NOT detect survival mode"


if __name__ == "__main__":
    print("Running Hearthstone Lethal Awareness tests...\n")

    tests = [
        ("1. Opponent lethal detected from board", test_opponent_lethal_detected_from_board),
        ("2. Own taunts block opponent lethal", test_own_taunts_block_opponent_lethal),
        ("3. Survival mode scores taunt higher than vanilla", test_survival_mode_scores_taunt_higher),
        ("4. Survival mode triggers early armor hero power", test_survival_mode_triggers_early_armor_hero_power),
        ("5. Survival mode does not skip heal hero power", test_survival_mode_does_not_skip_heal),
        ("6. Lethal-first burn spell scoring (ultra)", test_lethal_first_burn_spell_scoring),
        ("7. Charge minion enables lethal detection (ultra)", test_charge_minion_enables_lethal_detection),
        ("8. Survival mode prefers trades over face", test_survival_mode_prefers_trades_over_face),
        ("9. Hard has lethal prevention, medium does not", test_hard_has_lethal_prevention_medium_does_not),
    ]

    passed = 0
    failed = 0
    for label, test_fn in tests:
        try:
            test_fn()
            print(f"   ✓ {label}")
            passed += 1
        except Exception as e:
            print(f"   ✗ {label}: {e}")
            failed += 1

    print(f"\n{'✅' if failed == 0 else '❌'} {passed}/{passed + failed} tests passed")
    if failed > 0:
        exit(1)
