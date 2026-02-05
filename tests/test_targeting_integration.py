"""
Test Targeting System Integration

Tests for the TARGET_REQUIRED event handler and targeted trigger helpers.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, PendingChoice
)
from src.engine.types import Characteristics, new_id
from src.cards.interceptor_helpers import (
    make_targeted_etb_trigger, make_targeted_attack_trigger,
    make_targeted_death_trigger, make_targeted_damage_trigger,
    make_targeted_spell_cast_trigger
)


def create_test_game():
    """Set up a basic two-player game for testing."""
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def create_creature(game, player, name, power, toughness, setup_fn=None):
    """Create a test creature on the battlefield."""
    from src.engine.types import CardDefinition

    characteristics = Characteristics(
        types={CardType.CREATURE},
        power=power,
        toughness=toughness
    )

    card_def = CardDefinition(
        name=name,
        mana_cost="{1}",
        characteristics=characteristics,
        setup_interceptors=setup_fn
    )

    creature = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=characteristics,
        card_def=None
    )
    creature.card_def = card_def

    # Move to battlefield
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    return creature


# =============================================================================
# Test TARGET_REQUIRED Handler
# =============================================================================

def test_target_required_creates_pending_choice():
    """Test that TARGET_REQUIRED creates a PendingChoice for target selection."""
    print("\n=== Test: TARGET_REQUIRED creates PendingChoice ===")

    game, p1, p2 = create_test_game()

    # Create a creature controlled by p1 (source of the ability)
    source = create_creature(game, p1, "Damage Dealer", 2, 2)

    # Create a target creature controlled by p2
    target = create_creature(game, p2, "Target Dummy", 3, 3)

    # Emit TARGET_REQUIRED event
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'any',
            'min_targets': 1,
            'max_targets': 1,
            'optional': False,
            'prompt': "Deal 2 damage to any target"
        },
        source=source.id
    ))

    # Check PendingChoice was created
    choice = game.state.pending_choice
    assert choice is not None, "Expected PendingChoice to be created"
    assert choice.choice_type == "target_with_callback", f"Expected target_with_callback, got {choice.choice_type}"
    assert choice.player == p1.id, f"Expected choice player to be {p1.id}"
    assert choice.min_choices == 1, f"Expected min_choices 1, got {choice.min_choices}"

    # Check legal targets include the creature and players
    assert target.id in choice.options, "Target creature should be in legal targets"
    assert p1.id in choice.options, "Player 1 should be in legal targets"
    assert p2.id in choice.options, "Player 2 should be in legal targets"

    print(f"✓ PendingChoice created with {len(choice.options)} legal targets")
    print("✓ TARGET_REQUIRED creates PendingChoice correctly!")


def test_target_required_damage_effect_execution():
    """Test that submitting a target choice executes the damage effect."""
    print("\n=== Test: TARGET_REQUIRED damage effect execution ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Damage Dealer", 2, 2)
    target = create_creature(game, p2, "Target Dummy", 3, 3)

    # Emit TARGET_REQUIRED event
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 1
        },
        source=source.id
    ))

    # Get the pending choice
    choice = game.state.pending_choice
    assert choice is not None, "Expected PendingChoice"

    # Submit target selection
    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )

    assert success, f"Choice submission failed: {error}"

    # Events are now automatically emitted by submit_choice
    # Check damage was dealt
    assert target.state.damage == 2, f"Expected 2 damage on target, got {target.state.damage}"
    print(f"✓ Target creature took 2 damage")
    print("✓ Damage effect executed correctly!")


def test_target_required_destroy_effect():
    """Test TARGET_REQUIRED with destroy effect."""
    print("\n=== Test: TARGET_REQUIRED destroy effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Destroyer", 2, 2)
    target = create_creature(game, p2, "Doomed Creature", 3, 3)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'destroy',
            'target_filter': 'creature'
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None

    # Submit target selection
    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )

    assert success

    # Events are now automatically emitted by submit_choice

    # Check creature was destroyed (moved to graveyard)
    assert target.zone == ZoneType.GRAVEYARD, f"Expected creature in graveyard, found in {target.zone}"
    print("✓ Target creature destroyed!")
    print("✓ Destroy effect executed correctly!")


def test_target_required_fizzles_with_no_targets():
    """Test that TARGET_REQUIRED fizzles when no legal targets exist."""
    print("\n=== Test: TARGET_REQUIRED fizzles with no targets ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Damage Dealer", 2, 2)
    # No other creatures exist - only target_filter='opponent_creature'

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'opponent_creature',  # No opponent creatures
            'min_targets': 1,
            'optional': False
        },
        source=source.id
    ))

    # No PendingChoice should be created - ability fizzles
    assert game.state.pending_choice is None, "Expected no PendingChoice when no legal targets"
    print("✓ Ability correctly fizzles with no legal targets!")


def test_target_required_optional_with_no_targets():
    """Test that optional TARGET_REQUIRED skips silently when no targets."""
    print("\n=== Test: Optional TARGET_REQUIRED with no targets ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Optional Damager", 2, 2)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'opponent_creature',
            'optional': True  # Optional targeting
        },
        source=source.id
    ))

    # No PendingChoice - skips silently when optional and no targets
    assert game.state.pending_choice is None, "Expected no PendingChoice for optional with no targets"
    print("✓ Optional ability skips silently with no targets!")


# =============================================================================
# Test Targeted Trigger Helpers
# =============================================================================

def test_targeted_etb_trigger():
    """Test make_targeted_etb_trigger helper."""
    print("\n=== Test: make_targeted_etb_trigger ===")

    game, p1, p2 = create_test_game()

    # Create a target creature first
    target = create_creature(game, p2, "Target Dummy", 3, 3)

    # Create creature with targeted ETB trigger
    def etb_setup(obj, state):
        return [make_targeted_etb_trigger(
            obj, effect='damage', effect_params={'amount': 3},
            target_filter='creature', prompt="Deal 3 damage to target creature"
        )]

    source = create_creature(game, p1, "ETB Shooter", 2, 2, setup_fn=etb_setup)

    # ETB should have created a PendingChoice
    choice = game.state.pending_choice
    assert choice is not None, "Expected ETB to create PendingChoice"
    assert choice.choice_type == "target_with_callback"
    print(f"✓ ETB trigger created PendingChoice with {len(choice.options)} options")

    # Submit target
    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )

    assert success

    # Events are now automatically emitted by submit_choice

    assert target.state.damage == 3, f"Expected 3 damage, got {target.state.damage}"
    print("✓ make_targeted_etb_trigger works correctly!")


def test_targeted_attack_trigger():
    """Test make_targeted_attack_trigger helper."""
    print("\n=== Test: make_targeted_attack_trigger ===")

    game, p1, p2 = create_test_game()

    # Create target creature
    target = create_creature(game, p2, "Target Dummy", 5, 5)

    # Create creature with targeted attack trigger
    def attack_setup(obj, state):
        return [make_targeted_attack_trigger(
            obj, effect='damage', effect_params={'amount': 2},
            target_filter='any', prompt="Deal 2 damage to any target"
        )]

    attacker = create_creature(game, p1, "Attack Shooter", 2, 2, setup_fn=attack_setup)

    # Trigger attack
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={
            'attacker_id': attacker.id,
            'defending_player': p2.id
        }
    ))

    # Attack trigger should create PendingChoice
    choice = game.state.pending_choice
    assert choice is not None, "Expected attack trigger to create PendingChoice"

    # Submit target
    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )

    assert success

    # Events are now automatically emitted by submit_choice

    assert target.state.damage == 2
    print("✓ make_targeted_attack_trigger works correctly!")


def test_targeted_death_trigger():
    """Test make_targeted_death_trigger helper."""
    print("\n=== Test: make_targeted_death_trigger ===")

    game, p1, p2 = create_test_game()

    target = create_creature(game, p2, "Target Dummy", 5, 5)

    # Create creature with targeted death trigger
    def death_setup(obj, state):
        return [make_targeted_death_trigger(
            obj, effect='damage', effect_params={'amount': 4},
            target_filter='any', prompt="Deal 4 damage to any target"
        )]

    dying_creature = create_creature(game, p1, "Death Dealer", 2, 2, setup_fn=death_setup)

    # Kill the creature
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': dying_creature.id}
    ))

    # Death trigger should create PendingChoice
    choice = game.state.pending_choice
    assert choice is not None, "Expected death trigger to create PendingChoice"

    # Submit target
    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )

    assert success

    # Events are now automatically emitted by submit_choice

    assert target.state.damage == 4
    print("✓ make_targeted_death_trigger works correctly!")


def test_pump_effect():
    """Test TARGET_REQUIRED with pump effect."""
    print("\n=== Test: TARGET_REQUIRED pump effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Pumper", 2, 2)
    target = create_creature(game, p1, "Pumpee", 2, 2)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'pump',
            'effect_params': {'power_mod': 3, 'toughness_mod': 3},
            'target_filter': 'your_creature'
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None

    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )

    assert success

    # Events are now automatically emitted by submit_choice

    # Check PT_MODIFICATION was applied
    mods = getattr(target.state, 'pt_modifiers', [])
    assert len(mods) > 0, "Expected pt_modifiers to be set"
    assert mods[0]['power'] == 3
    assert mods[0]['toughness'] == 3
    print("✓ Pump effect executed correctly!")


def test_player_targeting():
    """Test TARGET_REQUIRED with player target filter."""
    print("\n=== Test: TARGET_REQUIRED player targeting ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Player Burner", 2, 2)

    initial_life = p2.life

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 5},
            'target_filter': 'opponent',  # Only opponents
            'prompt': "Deal 5 damage to target opponent"
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None
    assert p2.id in choice.options, "Opponent should be in targets"
    assert p1.id not in choice.options, "Self should not be in opponent targets"

    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[p2.id]
    )

    assert success

    # Events are now automatically emitted by submit_choice

    assert p2.life == initial_life - 5, f"Expected opponent life {initial_life - 5}, got {p2.life}"
    print("✓ Player targeting works correctly!")


# =============================================================================
# Test AI Integration
# =============================================================================

def test_ai_target_selection():
    """Test that AI can make valid target selections."""
    print("\n=== Test: AI target selection ===")

    from src.ai import AIEngine

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "AI Damage Dealer", 2, 2)
    target1 = create_creature(game, p2, "Small Target", 1, 1)
    target2 = create_creature(game, p2, "Big Target", 5, 5)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 3},
            'target_filter': 'creature'
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None

    # AI should be able to make a valid choice
    ai = AIEngine(difficulty='medium')
    selected = ai.make_choice(p1.id, choice, game.state)

    assert len(selected) >= choice.min_choices, "AI should select at least min_choices targets"
    assert len(selected) <= choice.max_choices, "AI should select at most max_choices targets"

    for target_id in selected:
        assert target_id in choice.options, f"AI selected invalid target: {target_id}"

    print(f"✓ AI selected valid target(s): {selected}")
    print("✓ AI target selection works correctly!")


# =============================================================================
# Run All Tests
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("TARGETING SYSTEM INTEGRATION TESTS")
    print("=" * 60)

    # TARGET_REQUIRED handler tests
    test_target_required_creates_pending_choice()
    test_target_required_damage_effect_execution()
    test_target_required_destroy_effect()
    test_target_required_fizzles_with_no_targets()
    test_target_required_optional_with_no_targets()

    # Targeted trigger helper tests
    test_targeted_etb_trigger()
    test_targeted_attack_trigger()
    test_targeted_death_trigger()
    test_pump_effect()
    test_player_targeting()

    # AI integration test
    test_ai_target_selection()

    print("\n" + "=" * 60)
    print("ALL TARGETING INTEGRATION TESTS PASSED!")
    print("=" * 60)
