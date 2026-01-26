"""
Test Lorwyn Eclipsed cards
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import Game, Event, EventType, ZoneType, get_power, get_toughness
from src.cards.custom.lorwyn_custom import LORWYN_CUSTOM_CARDS


def create_creature_on_battlefield(game, player, card_name):
    """
    Helper to create a creature on the battlefield with proper ETB handling.

    Creates in hand first WITHOUT card_def to avoid premature interceptor setup,
    then moves to battlefield via ZONE_CHANGE event which properly sets up
    interceptors AND triggers ETB exactly once.
    """
    card_def = LORWYN_CUSTOM_CARDS[card_name]

    # Create in hand WITHOUT card_def to avoid premature interceptor setup
    creature = game.create_object(
        name=card_name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None  # Don't pass card_def to avoid double setup
    )
    # Store card_def on the object so ZONE_CHANGE handler can set up interceptors
    creature.card_def = card_def

    # Move to battlefield - this registers interceptors AND triggers ETB
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


def test_burdened_stoneback_counters():
    """Test that Burdened Stoneback enters with -1/-1 counters."""
    print("\n=== Test: Burdened Stoneback ETB Counters ===")

    game = Game()
    p1 = game.add_player("Alice")

    creature = create_creature_on_battlefield(game, p1, "Burdened Stoneback")

    counters = creature.state.counters.get('-1/-1', 0)
    print(f"Counters on Burdened Stoneback: {counters}")

    # Base 4/4, should be 2/2 with two -1/-1 counters
    power = get_power(creature, game.state)
    toughness = get_toughness(creature, game.state)
    print(f"Effective stats: {power}/{toughness}")

    assert counters == 2, f"Expected 2 counters, got {counters}"
    assert power == 2, f"Expected power 2, got {power}"
    assert toughness == 2, f"Expected toughness 2, got {toughness}"
    print("✓ Burdened Stoneback ETB counters work!")


def test_champion_of_clachan_lord():
    """Test Champion of the Clachan's lord effect."""
    print("\n=== Test: Champion of the Clachan Lord Effect ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create Champion first (no ETB needed, just for static effect)
    champion_def = LORWYN_CUSTOM_CARDS["Champion of the Clachan"]
    champion = game.create_object(
        name="Champion of the Clachan",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=champion_def.characteristics,
        card_def=champion_def
    )

    # Create a Kithkin (no ETB needed, just for static effect test)
    kithkin_def = LORWYN_CUSTOM_CARDS["Goldmeadow Nomad"]
    kithkin = game.create_object(
        name="Goldmeadow Nomad",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=kithkin_def.characteristics,
        card_def=kithkin_def
    )

    # Check Kithkin got +1/+1
    base_power = kithkin.characteristics.power
    base_toughness = kithkin.characteristics.toughness
    actual_power = get_power(kithkin, game.state)
    actual_toughness = get_toughness(kithkin, game.state)

    print(f"Goldmeadow Nomad base: {base_power}/{base_toughness}")
    print(f"Goldmeadow Nomad with Champion: {actual_power}/{actual_toughness}")

    assert actual_power == base_power + 1, f"Expected +1 power"
    assert actual_toughness == base_toughness + 1, f"Expected +1 toughness"

    # Check Champion doesn't buff itself
    champion_power = get_power(champion, game.state)
    print(f"Champion's own power: {champion_power} (should be base 4)")
    assert champion_power == 4, "Champion shouldn't buff itself"

    print("✓ Champion of the Clachan lord effect works!")


def test_encumbered_reejerey_tap_trigger():
    """Test Encumbered Reejerey removes counter when tapped."""
    print("\n=== Test: Encumbered Reejerey Tap Trigger ===")

    game = Game()
    p1 = game.add_player("Alice")

    creature = create_creature_on_battlefield(game, p1, "Encumbered Reejerey")

    counters_before = creature.state.counters.get('-1/-1', 0)
    print(f"Counters after ETB: {counters_before}")
    assert counters_before == 3

    # Tap the creature
    game.emit(Event(
        type=EventType.TAP,
        payload={'object_id': creature.id}
    ))

    counters_after = creature.state.counters.get('-1/-1', 0)
    print(f"Counters after tap: {counters_after}")
    assert counters_after == 2, f"Expected 2, got {counters_after}"

    # Tap again
    creature.state.tapped = False  # Reset for test
    game.emit(Event(
        type=EventType.TAP,
        payload={'object_id': creature.id}
    ))

    counters_final = creature.state.counters.get('-1/-1', 0)
    print(f"Counters after second tap: {counters_final}")
    assert counters_final == 1

    print("✓ Encumbered Reejerey tap trigger works!")


def test_rooftop_percher_life_gain():
    """Test Rooftop Percher ETB life gain."""
    print("\n=== Test: Rooftop Percher ETB Life Gain ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Starting life: {p1.life}")

    creature = create_creature_on_battlefield(game, p1, "Rooftop Percher")

    print(f"Life after ETB: {p1.life}")
    assert p1.life == 23, f"Expected 23, got {p1.life}"
    print("✓ Rooftop Percher ETB life gain works!")


def run_all_tests():
    print("=" * 60)
    print("LORWYN ECLIPSED CARD TESTS")
    print("=" * 60)

    test_burdened_stoneback_counters()
    test_champion_of_clachan_lord()
    test_encumbered_reejerey_tap_trigger()
    test_rooftop_percher_life_gain()

    print("\n" + "=" * 60)
    print("ALL LORWYN TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
