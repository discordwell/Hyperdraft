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
# Test Multi-Target Scenarios
# =============================================================================

def test_multiple_targets():
    """Test TARGET_REQUIRED with multiple targets (e.g., 'up to 2 targets')."""
    print("\n=== Test: Multiple targets ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Multi-Shooter", 2, 2)
    target1 = create_creature(game, p2, "Target 1", 3, 3)
    target2 = create_creature(game, p2, "Target 2", 3, 3)
    target3 = create_creature(game, p2, "Target 3", 3, 3)

    # Emit TARGET_REQUIRED for up to 2 targets
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 2,  # Up to 2 targets
            'prompt': "Deal 2 damage to up to 2 target creatures"
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.min_choices == 1
    assert choice.max_choices == 2
    assert len(choice.options) == 4  # 3 enemy creatures + source

    # Select 2 targets
    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target1.id, target2.id]
    )

    assert success, f"Choice submission failed: {error}"
    assert target1.state.damage == 2, f"Expected 2 damage on target1, got {target1.state.damage}"
    assert target2.state.damage == 2, f"Expected 2 damage on target2, got {target2.state.damage}"
    assert target3.state.damage == 0, "Target3 should have no damage"

    print("✓ Multi-target selection works correctly!")


def test_exile_effect():
    """Test TARGET_REQUIRED with exile effect."""
    print("\n=== Test: Exile effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Exiler", 2, 2)
    target = create_creature(game, p2, "Exile Target", 3, 3)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'exile',
            'target_filter': 'creature'
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
    assert target.zone == ZoneType.EXILE, f"Expected creature in exile, found in {target.zone}"
    print("✓ Exile effect works correctly!")


def test_bounce_effect():
    """Test TARGET_REQUIRED with bounce (return to hand) effect."""
    print("\n=== Test: Bounce effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Bouncer", 2, 2)
    target = create_creature(game, p2, "Bounce Target", 3, 3)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'bounce',
            'target_filter': 'creature'
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
    assert target.zone == ZoneType.HAND, f"Expected creature in hand, found in {target.zone}"
    print("✓ Bounce effect works correctly!")


def test_tap_effect():
    """Test TARGET_REQUIRED with tap effect."""
    print("\n=== Test: Tap effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Tapper", 2, 2)
    target = create_creature(game, p2, "Tap Target", 3, 3)

    assert not target.state.tapped, "Target should start untapped"

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'tap',
            'target_filter': 'creature'
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
    assert target.state.tapped, "Target should be tapped"
    print("✓ Tap effect works correctly!")


def test_life_gain_effect():
    """Test TARGET_REQUIRED with life gain effect targeting player."""
    print("\n=== Test: Life gain effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Healer", 2, 2)
    initial_life = p1.life

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'life_change',
            'effect_params': {'amount': 5},
            'target_filter': 'player',
            'prompt': "Target player gains 5 life"
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None
    assert p1.id in choice.options
    assert p2.id in choice.options

    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[p1.id]  # Heal self
    )

    assert success
    assert p1.life == initial_life + 5, f"Expected {initial_life + 5} life, got {p1.life}"
    print("✓ Life gain effect works correctly!")


def test_targeted_damage_trigger_combat_only():
    """Test make_targeted_damage_trigger with combat_only flag."""
    print("\n=== Test: Combat damage trigger ===")

    game, p1, p2 = create_test_game()

    target = create_creature(game, p2, "Target Dummy", 5, 5)

    # Create creature with combat damage trigger
    def combat_damage_setup(obj, state):
        return [make_targeted_damage_trigger(
            obj, effect='destroy', target_filter='creature',
            combat_only=True, prompt="Destroy target creature"
        )]

    attacker = create_creature(game, p1, "Combat Destroyer", 3, 3, setup_fn=combat_damage_setup)

    # Non-combat damage should NOT trigger
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': attacker.id,
            'target': p2.id,
            'amount': 2,
            'is_combat': False
        }
    ))

    assert game.state.pending_choice is None, "Non-combat damage should not trigger"

    # Combat damage SHOULD trigger
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': attacker.id,
            'target': p2.id,
            'amount': 3,
            'is_combat': True
        }
    ))

    choice = game.state.pending_choice
    assert choice is not None, "Combat damage should trigger targeting"

    success, error, events = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )

    assert success
    assert target.zone == ZoneType.GRAVEYARD
    print("✓ Combat damage trigger works correctly!")


def test_sequential_targeting():
    """Test that multiple TARGET_REQUIRED events can be handled in sequence."""
    print("\n=== Test: Sequential targeting ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Double Striker", 2, 2)
    target1 = create_creature(game, p2, "Target 1", 3, 3)
    target2 = create_creature(game, p2, "Target 2", 3, 3)

    # First targeting event
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'creature',
            'prompt': "Deal 2 damage to target creature"
        },
        source=source.id
    ))

    # Resolve first choice
    choice1 = game.state.pending_choice
    assert choice1 is not None

    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target1.id]
    )
    assert success
    assert target1.state.damage == 2

    # Second targeting event
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 3},
            'target_filter': 'creature',
            'prompt': "Deal 3 damage to target creature"
        },
        source=source.id
    ))

    # Resolve second choice
    choice2 = game.state.pending_choice
    assert choice2 is not None
    assert choice2.id != choice1.id, "Should be a new choice"

    success, _, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=[target2.id]
    )
    assert success
    assert target2.state.damage == 3

    print("✓ Sequential targeting works correctly!")


def test_invalid_target_rejection():
    """Test that invalid target selections are rejected."""
    print("\n=== Test: Invalid target rejection ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Damager", 2, 2)
    own_creature = create_creature(game, p1, "Own Creature", 3, 3)
    enemy_creature = create_creature(game, p2, "Enemy Creature", 3, 3)

    # Request opponent creature target only
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'effect_params': {'amount': 2},
            'target_filter': 'opponent_creature',  # Only opponent creatures
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None
    assert enemy_creature.id in choice.options, "Enemy creature should be valid"
    assert own_creature.id not in choice.options, "Own creature should not be valid"

    # Try to submit own creature (should fail validation)
    success, error, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[own_creature.id]  # Invalid!
    )

    assert not success, "Should reject invalid target"
    assert "Invalid choice" in error

    # Submit valid target
    success, _, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[enemy_creature.id]
    )
    assert success
    print("✓ Invalid target rejection works correctly!")


def test_legal_targets_override():
    """Test TARGET_REQUIRED with legal_targets_override for custom filtering."""
    print("\n=== Test: Legal targets override ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Custom Targeter", 2, 2)
    small_creature = create_creature(game, p2, "Small", 1, 1)
    big_creature = create_creature(game, p2, "Big", 5, 5)

    # Only allow targeting the small creature via override
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'destroy',
            'target_filter': 'creature',  # Would normally include both
            'legal_targets_override': [small_creature.id],  # Override to just small
            'prompt': "Destroy target small creature"
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None
    assert small_creature.id in choice.options
    assert big_creature.id not in choice.options, "Big creature should be excluded by override"

    success, _, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[small_creature.id]
    )
    assert success
    assert small_creature.zone == ZoneType.GRAVEYARD
    print("✓ Legal targets override works correctly!")


def test_graveyard_targeting():
    """Test TARGET_REQUIRED with graveyard_to_hand effect."""
    print("\n=== Test: Graveyard targeting ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Graveshifter", 2, 2)

    # Create a creature and put it in the graveyard
    dead_creature = create_creature(game, p1, "Dead Creature", 3, 3)
    # Move to graveyard
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': dead_creature.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD
        }
    ))
    assert dead_creature.zone == ZoneType.GRAVEYARD, "Creature should be in graveyard"

    # Request graveyard targeting
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'graveyard_to_hand',
            'target_filter': 'creature_in_your_graveyard',
            'prompt': "Return target creature card from your graveyard to your hand"
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None, "Should create targeting choice for graveyard"
    assert dead_creature.id in choice.options, "Dead creature should be targetable"

    success, _, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[dead_creature.id]
    )
    assert success
    assert dead_creature.zone == ZoneType.HAND, f"Creature should be in hand, found in {dead_creature.zone}"
    print("✓ Graveyard targeting works correctly!")


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

    # Multi-target and effect type tests
    test_multiple_targets()
    test_exile_effect()
    test_bounce_effect()
    test_tap_effect()
    test_life_gain_effect()
    test_targeted_damage_trigger_combat_only()
    test_sequential_targeting()
    test_invalid_target_rejection()
    test_legal_targets_override()
    test_graveyard_targeting()

    # AI integration test
    test_ai_target_selection()

    print("\n" + "=" * 60)
    print("ALL TARGETING INTEGRATION TESTS PASSED!")
    print("=" * 60)
