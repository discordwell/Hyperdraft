"""
Engine Tests

Test the core mechanics with our 5 test cards.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    get_power, get_toughness
)
from src.cards.test_cards import (
    LIGHTNING_BOLT, SOUL_WARDEN, GLORIOUS_ANTHEM,
    RHOX_FAITHMENDER, FOG_BANK
)


def test_basic_damage():
    """Test basic damage dealing."""
    print("\n=== Test: Basic Damage ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    print(f"Bob's life: {p2.life}")
    assert p2.life == 20

    # Deal 5 damage to Bob
    events = game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 5}
    ))

    print(f"Bob's life after 5 damage: {p2.life}")
    assert p2.life == 15
    print("✓ Basic damage works!")


def test_creature_stats():
    """Test creature power/toughness."""
    print("\n=== Test: Creature Stats ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a 2/3 creature
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics
    )

    power = get_power(creature, game.state)
    toughness = get_toughness(creature, game.state)

    print(f"Soul Warden stats: {power}/{toughness}")
    assert power == 1
    assert toughness == 1
    print("✓ Creature stats work!")


def test_triggered_ability():
    """Test Soul Warden's triggered ability."""
    print("\n=== Test: Triggered Ability (Soul Warden) ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Alice's starting life: {p1.life}")

    # Put Soul Warden on the battlefield
    soul_warden = game.create_object(
        name="Soul Warden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN
    )

    print(f"Interceptors registered: {len(game.state.interceptors)}")
    assert len(game.state.interceptors) == 1

    # Another creature enters
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': 'dummy_creature',
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    # Need to add the dummy creature to state for the trigger to fully work
    from src.engine import Characteristics
    dummy = game.create_object(
        name="Dummy",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE})
    )

    # Emit the zone change event again with the real object
    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': dummy.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Events processed: {len(events)}")
    print(f"Alice's life after creature ETB: {p1.life}")
    assert p1.life == 21, f"Expected 21, got {p1.life}"
    print("✓ Triggered ability works!")


def test_continuous_effect():
    """Test Glorious Anthem's +1/+1 effect."""
    print("\n=== Test: Continuous Effect (Glorious Anthem) ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a 1/1 creature
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics
    )

    power_before = get_power(creature, game.state)
    toughness_before = get_toughness(creature, game.state)
    print(f"Before Anthem: {power_before}/{toughness_before}")

    # Put Glorious Anthem on the battlefield
    anthem = game.create_object(
        name="Glorious Anthem",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GLORIOUS_ANTHEM.characteristics,
        card_def=GLORIOUS_ANTHEM
    )

    power_after = get_power(creature, game.state)
    toughness_after = get_toughness(creature, game.state)
    print(f"After Anthem: {power_after}/{toughness_after}")

    assert power_after == power_before + 1
    assert toughness_after == toughness_before + 1
    print("✓ Continuous effect works!")


def test_replacement_effect():
    """Test Rhox Faithmender's life doubling."""
    print("\n=== Test: Replacement Effect (Rhox Faithmender) ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Alice's starting life: {p1.life}")

    # Put Rhox Faithmender on the battlefield
    rhox = game.create_object(
        name="Rhox Faithmender",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=RHOX_FAITHMENDER.characteristics,
        card_def=RHOX_FAITHMENDER
    )

    print(f"Interceptors registered: {len(game.state.interceptors)}")

    # Gain 3 life - should become 6
    events = game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 3}
    ))

    print(f"Alice's life after gaining '3' life: {p1.life}")
    assert p1.life == 26, f"Expected 26 (20 + 3*2), got {p1.life}"
    print("✓ Replacement effect works!")


def test_prevention_effect():
    """Test Fog Bank's damage prevention."""
    print("\n=== Test: Prevention Effect (Fog Bank) ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Fog Bank on the battlefield
    fog_bank = game.create_object(
        name="Fog Bank",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=FOG_BANK.characteristics,
        card_def=FOG_BANK
    )

    print(f"Fog Bank damage before: {fog_bank.state.damage}")

    # Try to deal 5 damage to Fog Bank
    events = game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': fog_bank.id, 'amount': 5}
    ))

    print(f"Fog Bank damage after 5 damage: {fog_bank.state.damage}")
    assert fog_bank.state.damage == 0, f"Expected 0 (prevented), got {fog_bank.state.damage}"
    print("✓ Prevention effect works!")


def test_complex_interaction():
    """Test Soul Warden + Rhox Faithmender combo."""
    print("\n=== Test: Complex Interaction (Soul Warden + Rhox Faithmender) ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Alice's starting life: {p1.life}")

    # Put both creatures on the battlefield
    soul_warden = game.create_object(
        name="Soul Warden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN
    )

    # Life goes from 20 to 21 (Soul Warden triggers on Rhox entering)
    # BUT Rhox's doubling effect is on the battlefield too by then
    # Actually, we need to simulate this properly...

    rhox = game.create_object(
        name="Rhox Faithmender",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=RHOX_FAITHMENDER.characteristics,
        card_def=RHOX_FAITHMENDER
    )

    # Now both are on battlefield. Emit a zone change event to trigger Soul Warden.
    from src.engine import Characteristics
    dummy = game.create_object(
        name="Another Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE})
    )

    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': dummy.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    # Soul Warden triggers: gain 1 life
    # Rhox Faithmender doubles it: gain 2 life
    print(f"Alice's life after creature ETB: {p1.life}")
    assert p1.life == 22, f"Expected 22 (20 + 1*2), got {p1.life}"
    print("✓ Complex interaction works! Soul Warden's 1 life was doubled to 2 by Rhox Faithmender!")


def test_state_based_actions():
    """Test creature death from damage."""
    print("\n=== Test: State-Based Actions (Lethal Damage) ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a 1/1 creature
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics
    )

    battlefield = game.state.zones['battlefield']
    print(f"Creatures on battlefield: {len(battlefield.objects)}")
    assert creature.id in battlefield.objects

    # Deal 1 damage (lethal to a 1/1)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': creature.id, 'amount': 1}
    ))

    print(f"Creature damage: {creature.state.damage}")

    # Check SBAs
    game.check_state_based_actions()

    print(f"Creature zone after SBA: {creature.zone}")
    print(f"Creatures on battlefield: {len(battlefield.objects)}")

    assert creature.zone == ZoneType.GRAVEYARD
    assert creature.id not in battlefield.objects
    print("✓ State-based actions work!")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("HYPERDRAFT ENGINE TESTS")
    print("=" * 60)

    test_basic_damage()
    test_creature_stats()
    test_triggered_ability()
    test_continuous_effect()
    test_replacement_effect()
    test_prevention_effect()
    test_complex_interaction()
    test_state_based_actions()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
