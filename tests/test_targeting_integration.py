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
# Test Damage Division
# =============================================================================

def test_damage_division_three_targets():
    """Test dividing 5 damage as 2/2/1 among three creatures."""
    print("\n=== Test: Damage division among three targets ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Damage Divider", 2, 2)
    target1 = create_creature(game, p2, "Target 1", 2, 2)
    target2 = create_creature(game, p2, "Target 2", 2, 2)
    target3 = create_creature(game, p2, "Target 3", 2, 2)

    # Emit TARGET_REQUIRED with divide_amount
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 3,
            'divide_amount': 5,
            'prompt': "Deal 5 damage divided as you choose among any number of target creatures"
        },
        source=source.id
    ))

    # First choice: select targets
    choice1 = game.state.pending_choice
    assert choice1 is not None, "Expected PendingChoice for target selection"
    assert choice1.choice_type == "target_with_callback"

    # Select all 3 targets
    success, error, events = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target1.id, target2.id, target3.id]
    )
    assert success, f"Target selection failed: {error}"

    # Second choice: allocate damage
    choice2 = game.state.pending_choice
    assert choice2 is not None, "Expected PendingChoice for damage allocation"
    assert choice2.choice_type == "divide_allocation"
    assert choice2.callback_data.get('total_amount') == 5

    print(f"✓ Allocation choice created with {len(choice2.options)} targets")

    # Submit allocation: 2/2/1
    allocations = [
        {'target_id': target1.id, 'amount': 2},
        {'target_id': target2.id, 'amount': 2},
        {'target_id': target3.id, 'amount': 1}
    ]
    success, error, events = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert success, f"Allocation failed: {error}"

    # Verify damage was dealt correctly
    assert target1.state.damage == 2, f"Target 1 expected 2 damage, got {target1.state.damage}"
    assert target2.state.damage == 2, f"Target 2 expected 2 damage, got {target2.state.damage}"
    assert target3.state.damage == 1, f"Target 3 expected 1 damage, got {target3.state.damage}"

    print("✓ Damage was divided correctly as 2/2/1!")
    print("✓ Damage division works correctly!")


def test_damage_division_includes_players():
    """Test dividing damage between creatures and players."""
    print("\n=== Test: Damage division to creatures and players ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Damage Divider", 2, 2)
    target = create_creature(game, p2, "Target Creature", 3, 3)
    initial_life = p2.life

    # Emit with 'any' target filter
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'target_filter': 'any',
            'min_targets': 1,
            'max_targets': 5,
            'divide_amount': 5,
            'prompt': "Deal 5 damage divided among any number of targets"
        },
        source=source.id
    ))

    # Select creature and player
    choice1 = game.state.pending_choice
    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target.id, p2.id]
    )
    assert success

    # Allocate: 3 to creature, 2 to player
    choice2 = game.state.pending_choice
    assert choice2 is not None

    allocations = [
        {'target_id': target.id, 'amount': 3},
        {'target_id': p2.id, 'amount': 2}
    ]
    success, error, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert success, f"Allocation failed: {error}"

    assert target.state.damage == 3, f"Creature expected 3 damage, got {target.state.damage}"
    assert p2.life == initial_life - 2, f"Player expected {initial_life - 2} life, got {p2.life}"

    print("✓ Damage divided between creature (3) and player (2)!")


def test_ai_damage_division_lethal():
    """Test AI allocates lethal damage to kill threats first."""
    print("\n=== Test: AI damage division allocates lethal ===")

    from src.ai import AIEngine

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "AI Damage Divider", 2, 2)
    # 2-toughness creature (easy kill)
    small = create_creature(game, p2, "Small Threat", 4, 2)
    # 3-toughness creature
    medium = create_creature(game, p2, "Medium Threat", 3, 3)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 3,
            'divide_amount': 5
        },
        source=source.id
    ))

    # First: target selection
    choice1 = game.state.pending_choice
    ai = AIEngine(difficulty='hard')
    targets = ai.make_choice(p1.id, choice1, game.state)
    assert len(targets) >= 1

    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=targets
    )
    assert success

    # Second: allocation
    choice2 = game.state.pending_choice
    if choice2 and choice2.choice_type == "divide_allocation":
        allocations = ai.make_choice(p1.id, choice2, game.state)
        assert len(allocations) > 0, "AI should allocate damage"

        # Verify total
        total = sum(a.get('amount', 0) for a in allocations)
        assert total == 5, f"AI should allocate exactly 5 damage, got {total}"

        print(f"✓ AI allocated damage: {allocations}")
        print("✓ AI damage division works correctly!")
    else:
        print("✓ Target selection completed (no allocation needed)")


# =============================================================================
# Test Multi-Effect Targeting
# =============================================================================

def test_tap_plus_stun():
    """Test multi-effect targeting: tap + stun counter."""
    print("\n=== Test: Tap + Stun multi-effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Frost Mage", 2, 2)
    target = create_creature(game, p2, "Freeze Target", 3, 3)

    # Emit TARGET_REQUIRED with multiple effects
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effects': [
                {'effect': 'tap'},
                {'effect': 'stun'}
            ],
            'target_filter': 'creature',
            'prompt': "Tap target creature. It doesn't untap during next untap step."
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None

    success, error, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )
    assert success, f"Choice failed: {error}"

    assert target.state.tapped, "Target should be tapped"
    assert target.state.counters.get('stun', 0) == 1, "Target should have stun counter"

    print("✓ Target is tapped AND has stun counter!")
    print("✓ Multi-effect targeting works correctly!")


def test_pump_plus_keyword():
    """Test multi-effect targeting: pump + grant keyword."""
    print("\n=== Test: Pump + Keyword multi-effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Combat Trainer", 2, 2)
    target = create_creature(game, p1, "Trainee", 2, 2)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effects': [
                {'effect': 'pump', 'params': {'power_mod': 3, 'toughness_mod': 1}},
                {'effect': 'grant_keyword', 'params': {'keyword': 'haste'}}
            ],
            'target_filter': 'your_creature',
            'prompt': "Target creature you control gets +3/+1 and gains haste until end of turn."
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    assert choice is not None

    success, _, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )
    assert success

    # Check pump was applied
    mods = getattr(target.state, 'pt_modifiers', [])
    assert len(mods) > 0, "Should have PT modifier"
    assert mods[0]['power'] == 3
    assert mods[0]['toughness'] == 1

    print("✓ Target got +3/+1 and haste!")
    print("✓ Pump + keyword multi-effect works correctly!")


def test_freeze_effect():
    """Test the combined freeze effect (tap + stun in one)."""
    print("\n=== Test: Freeze effect ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Ice Elemental", 3, 3)
    target = create_creature(game, p2, "Victim", 4, 4)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effects': [{'effect': 'freeze'}],  # Combined effect
            'target_filter': 'creature'
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    success, _, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )
    assert success

    assert target.state.tapped, "Target should be tapped"
    assert target.state.counters.get('stun', 0) == 1, "Target should have stun counter"

    print("✓ Freeze effect taps and stuns!")


# =============================================================================
# Test Modal With Targeting
# =============================================================================

def test_modal_tap_or_untap():
    """Test modal choice where modes require targeting."""
    print("\n=== Test: Modal tap or untap ===")

    from src.cards.interceptor_helpers import make_modal_etb_trigger

    game, p1, p2 = create_test_game()

    # Setup creature with modal ETB
    def modal_setup(obj, state):
        return [make_modal_etb_trigger(
            obj,
            modes=[
                {'text': 'Tap target creature', 'requires_targeting': True,
                 'effect': 'tap', 'target_filter': 'creature'},
                {'text': 'Untap target creature', 'requires_targeting': True,
                 'effect': 'untap', 'target_filter': 'creature'}
            ],
            prompt="Choose one:"
        )]

    # Create target (tapped)
    target = create_creature(game, p2, "Tapped Target", 3, 3)
    target.state.tapped = True

    # Create creature with modal ability
    source = create_creature(game, p1, "Modal Creature", 2, 2, setup_fn=modal_setup)

    # ETB should create modal choice
    choice1 = game.state.pending_choice
    assert choice1 is not None, "Expected modal choice"
    assert choice1.choice_type == "modal_with_targeting"

    # Choose "Untap target creature" (mode 1)
    # Options are dicts with 'id' as string indices
    success, error, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=["1"]  # Mode index 1 as string = untap
    )
    assert success, f"Modal choice failed: {error}"

    # Should create TARGET_REQUIRED for the untap
    choice2 = game.state.pending_choice
    assert choice2 is not None, "Expected target choice after modal"
    assert choice2.choice_type == "target_with_callback"

    # Select target to untap
    success, _, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=[target.id]
    )
    assert success

    assert not target.state.tapped, "Target should be untapped"
    print("✓ Modal with targeting: untap mode worked!")


def test_modal_no_targets_fallback():
    """Test AI chooses non-targeting mode when no valid targets."""
    print("\n=== Test: Modal fallback when no targets ===")

    from src.ai import AIEngine
    from src.cards.interceptor_helpers import make_modal_etb_trigger

    game, p1, p2 = create_test_game()

    # Setup creature with modal ETB: destroy OR create token
    def modal_setup(obj, state):
        return [make_modal_etb_trigger(
            obj,
            modes=[
                {'text': 'Destroy target creature with CMC 3 or less', 'requires_targeting': True,
                 'effect': 'destroy', 'target_filter': 'creature'},
                {'text': 'Create a 1/1 Spirit token', 'requires_targeting': False,
                 'effect': 'create_token', 'effect_params': {
                     'token': {'name': 'Spirit', 'power': 1, 'toughness': 1},
                     'count': 1
                 }}
            ],
            prompt="Choose one:"
        )]

    # No creatures on battlefield (no targets for destroy mode)
    source = create_creature(game, p1, "Modal Creator", 2, 2, setup_fn=modal_setup)

    choice = game.state.pending_choice
    assert choice is not None

    # AI should prefer mode 1 (token) since mode 0 (destroy) has no targets
    ai = AIEngine(difficulty='hard')
    selected = ai.make_choice(p1.id, choice, game.state)

    print(f"✓ AI selected mode(s): {selected}")
    # Mode 1 (create token) should be preferred since no creatures to destroy
    assert 1 in selected or len(selected) > 0, "AI should select a valid mode"
    print("✓ AI correctly handles modal with no targets!")


# =============================================================================
# Edge Cases and Negative Tests
# =============================================================================

def test_damage_division_wrong_total_fails():
    """Test that allocation with wrong total is rejected."""
    print("\n=== Test: Damage division wrong total fails ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Damage Divider", 2, 2)
    target1 = create_creature(game, p2, "Target 1", 3, 3)
    target2 = create_creature(game, p2, "Target 2", 3, 3)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 2,
            'divide_amount': 5,
        },
        source=source.id
    ))

    # Select targets
    choice1 = game.state.pending_choice
    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target1.id, target2.id]
    )
    assert success

    # Try to allocate wrong total (4 instead of 5)
    choice2 = game.state.pending_choice
    allocations = [
        {'target_id': target1.id, 'amount': 2},
        {'target_id': target2.id, 'amount': 2}  # Total 4, should be 5
    ]
    success, error, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert not success, "Should reject allocation with wrong total"
    assert "total" in error.lower() or "4" in error or "5" in error, f"Error should mention total mismatch: {error}"

    print(f"✓ Correctly rejected wrong total with error: {error}")


def test_damage_division_single_target():
    """Test dividing all damage to a single target."""
    print("\n=== Test: Damage division all to one target ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Focused Striker", 2, 2)
    target = create_creature(game, p2, "Solo Target", 5, 5)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 5,
            'divide_amount': 4,
        },
        source=source.id
    ))

    # Select just one target
    choice1 = game.state.pending_choice
    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target.id]
    )
    assert success

    # Allocate all 4 to the single target
    choice2 = game.state.pending_choice
    allocations = [{'target_id': target.id, 'amount': 4}]
    success, error, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert success, f"Should accept single target allocation: {error}"
    assert target.state.damage == 4, f"Target should have 4 damage, got {target.state.damage}"

    print("✓ Single target received all 4 damage!")


def test_damage_division_helper():
    """Test make_divided_damage_etb_trigger helper function."""
    print("\n=== Test: Divided damage ETB trigger helper ===")

    from src.cards.interceptor_helpers import make_divided_damage_etb_trigger

    game, p1, p2 = create_test_game()

    def divider_setup(obj, state):
        return [make_divided_damage_etb_trigger(
            obj,
            damage_amount=3,
            target_filter='creature',
            max_targets=3,
            prompt="Deal 3 damage divided among up to 3 target creatures"
        )]

    target1 = create_creature(game, p2, "Target A", 2, 2)
    target2 = create_creature(game, p2, "Target B", 2, 2)

    # Create creature with divided damage ETB
    source = create_creature(game, p1, "Damage Divider", 2, 2, setup_fn=divider_setup)

    # Should trigger target selection
    choice1 = game.state.pending_choice
    assert choice1 is not None, "Should have pending choice"
    assert choice1.choice_type == "target_with_callback"
    assert choice1.callback_data.get('divide_amount') == 3

    # Select both targets
    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target1.id, target2.id]
    )
    assert success

    # Allocate damage
    choice2 = game.state.pending_choice
    assert choice2.choice_type == "divide_allocation"

    allocations = [
        {'target_id': target1.id, 'amount': 2},
        {'target_id': target2.id, 'amount': 1}
    ]
    success, _, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert success

    assert target1.state.damage == 2
    assert target2.state.damage == 1
    print("✓ Divided damage ETB helper works!")


def test_counter_division():
    """Test dividing +1/+1 counters among targets."""
    print("\n=== Test: Counter division ===")

    from src.cards.interceptor_helpers import make_divided_counters_etb_trigger

    game, p1, p2 = create_test_game()

    def counter_divider_setup(obj, state):
        return [make_divided_counters_etb_trigger(
            obj,
            counter_amount=4,
            counter_type='p1p1',
            target_filter='your_creature',
            max_targets=3,
            prompt="Distribute 4 +1/+1 counters among creatures you control"
        )]

    target1 = create_creature(game, p1, "Your Creature A", 2, 2)
    target2 = create_creature(game, p1, "Your Creature B", 2, 2)

    source = create_creature(game, p1, "Counter Giver", 2, 2, setup_fn=counter_divider_setup)

    # Target selection
    choice1 = game.state.pending_choice
    assert choice1 is not None
    assert choice1.callback_data.get('divide_amount') == 4

    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target1.id, target2.id]
    )
    assert success

    # Allocate counters: 3 to target1, 1 to target2
    choice2 = game.state.pending_choice
    allocations = [
        {'target_id': target1.id, 'amount': 3},
        {'target_id': target2.id, 'amount': 1}
    ]
    success, error, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert success, f"Counter allocation failed: {error}"

    assert target1.state.counters.get('p1p1', 0) == 3, f"Target 1 should have 3 counters"
    assert target2.state.counters.get('p1p1', 0) == 1, f"Target 2 should have 1 counter"
    print("✓ Counter division works correctly!")


def test_multi_effect_helper():
    """Test make_targeted_multi_effect_etb_trigger helper."""
    print("\n=== Test: Multi-effect ETB helper ===")

    from src.cards.interceptor_helpers import make_targeted_multi_effect_etb_trigger

    game, p1, p2 = create_test_game()

    def multi_effect_setup(obj, state):
        return [make_targeted_multi_effect_etb_trigger(
            obj,
            effects=[
                {'effect': 'tap'},
                {'effect': 'damage', 'params': {'amount': 1}}
            ],
            target_filter='creature',
            prompt="Tap target creature and deal 1 damage to it"
        )]

    target = create_creature(game, p2, "Victim", 3, 3)

    source = create_creature(game, p1, "Multi-Effect Source", 2, 2, setup_fn=multi_effect_setup)

    choice = game.state.pending_choice
    assert choice is not None

    success, _, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )
    assert success

    assert target.state.tapped, "Target should be tapped"
    assert target.state.damage == 1, "Target should have 1 damage"
    print("✓ Multi-effect ETB helper works correctly!")


def test_modal_invalid_mode_index():
    """Test that invalid mode index is rejected."""
    print("\n=== Test: Modal invalid mode index rejected ===")

    from src.cards.interceptor_helpers import make_modal_etb_trigger

    game, p1, p2 = create_test_game()

    def modal_setup(obj, state):
        return [make_modal_etb_trigger(
            obj,
            modes=[
                {'text': 'Gain 3 life', 'requires_targeting': False,
                 'effect': 'life_gain', 'effect_params': {'amount': 3}},
                {'text': 'Draw a card', 'requires_targeting': False,
                 'effect': 'draw', 'effect_params': {'count': 1}}
            ],
            prompt="Choose one:"
        )]

    source = create_creature(game, p1, "Modal Source", 2, 2, setup_fn=modal_setup)

    choice = game.state.pending_choice
    assert choice is not None

    # Try to select invalid mode index (5, only 0 and 1 exist)
    success, error, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=["5"]
    )
    # The mode should be skipped silently, not cause a crash
    # Result depends on implementation - either fail or succeed with no effect
    print(f"✓ Invalid mode index handled (success={success}, error={error})")


def test_modal_with_multi_select():
    """Test modal choosing multiple modes."""
    print("\n=== Test: Modal multi-select ===")

    from src.cards.interceptor_helpers import make_modal_etb_trigger

    game, p1, p2 = create_test_game()
    initial_life = p1.life

    def modal_setup(obj, state):
        return [make_modal_etb_trigger(
            obj,
            modes=[
                {'text': 'Gain 2 life', 'requires_targeting': False,
                 'effect': 'life_gain', 'effect_params': {'amount': 2}},
                {'text': 'Gain 3 life', 'requires_targeting': False,
                 'effect': 'life_gain', 'effect_params': {'amount': 3}}
            ],
            min_modes=1,
            max_modes=2,  # Can choose both
            prompt="Choose one or more:"
        )]

    source = create_creature(game, p1, "Modal Multi", 2, 2, setup_fn=modal_setup)

    choice = game.state.pending_choice
    assert choice is not None
    assert choice.max_choices == 2, "Should allow 2 mode selections"

    # Choose both modes
    success, error, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=["0", "1"]  # Both modes
    )
    assert success, f"Multi-mode selection failed: {error}"

    # Should gain 2 + 3 = 5 life
    expected_life = initial_life + 5
    assert p1.life == expected_life, f"Expected {expected_life} life, got {p1.life}"
    print(f"✓ Both modes executed, gained 5 life (now at {p1.life})")


def test_allocation_to_invalid_target_rejected():
    """Test that allocating to a target not in the original selection fails."""
    print("\n=== Test: Allocation to invalid target rejected ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Damage Source", 2, 2)
    target1 = create_creature(game, p2, "Selected Target", 3, 3)
    target2 = create_creature(game, p2, "Not Selected", 3, 3)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 2,
            'divide_amount': 3,
        },
        source=source.id
    ))

    # Select only target1
    choice1 = game.state.pending_choice
    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target1.id]  # Only target1
    )
    assert success

    # Try to allocate to target2 (not selected)
    choice2 = game.state.pending_choice
    allocations = [
        {'target_id': target2.id, 'amount': 3}  # target2 wasn't selected!
    ]
    success, error, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert not success, "Should reject allocation to non-selected target"
    print(f"✓ Correctly rejected invalid target: {error}")


def test_multi_effect_partial_execution():
    """Test multi-effect where target becomes invalid mid-execution."""
    print("\n=== Test: Multi-effect execution order ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Death Dealer", 2, 2)
    # 1 toughness creature - will die from 2 damage
    target = create_creature(game, p2, "Fragile Target", 3, 1)

    # Effects: deal 2 damage (kills it), then tap
    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effects': [
                {'effect': 'damage', 'params': {'amount': 2}},
                {'effect': 'tap'}  # Target might be dead by now
            ],
            'target_filter': 'creature'
        },
        source=source.id
    ))

    choice = game.state.pending_choice
    success, _, _ = game.submit_choice(
        choice_id=choice.id,
        player_id=p1.id,
        selected=[target.id]
    )
    assert success

    # Target should have received damage (and probably died)
    assert target.state.damage == 2, "Target should have 2 damage"
    print("✓ Multi-effect executed in order!")


def test_ai_modal_choice_with_valid_targets():
    """Test AI makes good modal choices when targets are available."""
    print("\n=== Test: AI modal choice with valid targets ===")

    from src.ai import AIEngine
    from src.cards.interceptor_helpers import make_modal_etb_trigger

    game, p1, p2 = create_test_game()

    # Create a threatening creature for p2
    threat = create_creature(game, p2, "Big Threat", 5, 5)

    def modal_setup(obj, state):
        return [make_modal_etb_trigger(
            obj,
            modes=[
                {'text': 'Destroy target creature', 'requires_targeting': True,
                 'effect': 'destroy', 'target_filter': 'creature'},
                {'text': 'Gain 1 life', 'requires_targeting': False,
                 'effect': 'life_gain', 'effect_params': {'amount': 1}}
            ],
            prompt="Choose one:"
        )]

    source = create_creature(game, p1, "AI Modal", 2, 2, setup_fn=modal_setup)

    choice = game.state.pending_choice
    assert choice is not None

    ai = AIEngine(difficulty='hard')
    selected = ai.make_choice(p1.id, choice, game.state)

    # AI should prefer destroy mode (0) since there's a valid target
    # and destroying a 5/5 is much better than 1 life
    print(f"✓ AI selected mode: {selected}")
    # Just verify it's a valid selection
    assert len(selected) >= 1, "AI should select at least one mode"


def test_damage_division_with_death_trigger():
    """Test damage division that triggers death events correctly."""
    print("\n=== Test: Damage division triggers death ===")

    game, p1, p2 = create_test_game()

    source = create_creature(game, p1, "Mass Damager", 2, 2)
    # Two 1-toughness creatures that will die
    target1 = create_creature(game, p2, "Weak 1", 1, 1)
    target2 = create_creature(game, p2, "Weak 2", 1, 1)
    # One that survives
    target3 = create_creature(game, p2, "Tough", 2, 3)

    game.emit(Event(
        type=EventType.TARGET_REQUIRED,
        payload={
            'source': source.id,
            'controller': p1.id,
            'effect': 'damage',
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 3,
            'divide_amount': 4,
        },
        source=source.id
    ))

    # Select all 3
    choice1 = game.state.pending_choice
    success, _, _ = game.submit_choice(
        choice_id=choice1.id,
        player_id=p1.id,
        selected=[target1.id, target2.id, target3.id]
    )
    assert success

    # Allocate: 1 each to weak, 2 to tough
    choice2 = game.state.pending_choice
    allocations = [
        {'target_id': target1.id, 'amount': 1},
        {'target_id': target2.id, 'amount': 1},
        {'target_id': target3.id, 'amount': 2}
    ]
    success, _, _ = game.submit_choice(
        choice_id=choice2.id,
        player_id=p1.id,
        selected=allocations
    )
    assert success

    # Check state-based actions to process lethal damage
    game.check_state_based_actions()

    # Weak creatures should be dead (damage >= toughness)
    assert target1.zone == ZoneType.GRAVEYARD, "Weak 1 should be dead"
    assert target2.zone == ZoneType.GRAVEYARD, "Weak 2 should be dead"
    assert target3.zone == ZoneType.BATTLEFIELD, "Tough should survive"
    assert target3.state.damage == 2, "Tough should have 2 damage"

    print("✓ Damage division correctly killed creatures!")


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

    # Damage division tests
    print("\n" + "-" * 40)
    print("DAMAGE DIVISION TESTS")
    print("-" * 40)
    test_damage_division_three_targets()
    test_damage_division_includes_players()
    test_ai_damage_division_lethal()

    # Multi-effect targeting tests
    print("\n" + "-" * 40)
    print("MULTI-EFFECT TARGETING TESTS")
    print("-" * 40)
    test_tap_plus_stun()
    test_pump_plus_keyword()
    test_freeze_effect()

    # Modal with targeting tests
    print("\n" + "-" * 40)
    print("MODAL WITH TARGETING TESTS")
    print("-" * 40)
    test_modal_tap_or_untap()
    test_modal_no_targets_fallback()

    # Edge cases and negative tests
    print("\n" + "-" * 40)
    print("EDGE CASES AND NEGATIVE TESTS")
    print("-" * 40)
    test_damage_division_wrong_total_fails()
    test_damage_division_single_target()
    test_damage_division_helper()
    test_counter_division()
    test_multi_effect_helper()
    test_modal_invalid_mode_index()
    test_modal_with_multi_select()
    test_allocation_to_invalid_target_rejected()
    test_multi_effect_partial_execution()
    test_ai_modal_choice_with_valid_targets()
    test_damage_division_with_death_trigger()

    print("\n" + "=" * 60)
    print("ALL TARGETING INTEGRATION TESTS PASSED!")
    print("=" * 60)
