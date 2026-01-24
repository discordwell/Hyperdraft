"""
Degenerate MTG Combo Tests

Testing weird edge cases and broken interactions.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    get_power, get_toughness, Characteristics
)
from src.cards.lorwyn_eclipsed import LORWYN_ECLIPSED_CARDS
from src.cards.test_cards import (
    SOUL_WARDEN, GLORIOUS_ANTHEM, RHOX_FAITHMENDER, FOG_BANK
)


def test_multiple_anthems_stacking():
    """Test multiple Glorious Anthems stacking +1/+1 effects."""
    print("\n=== Test: Triple Anthem Stacking ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a 1/1 creature
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=1,
            toughness=1
        )
    )

    print(f"Base stats: {get_power(creature, game.state)}/{get_toughness(creature, game.state)}")

    # Add THREE Glorious Anthems
    for i in range(3):
        game.create_object(
            name=f"Glorious Anthem {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=GLORIOUS_ANTHEM.characteristics,
            card_def=GLORIOUS_ANTHEM
        )

    power = get_power(creature, game.state)
    toughness = get_toughness(creature, game.state)
    print(f"With 3 Anthems: {power}/{toughness}")

    assert power == 4, f"Expected 4 (1+3), got {power}"
    assert toughness == 4, f"Expected 4 (1+3), got {toughness}"
    print("✓ Triple anthem stacking works!")


def test_multiple_rhox_faithmenders():
    """Test multiple Rhox Faithmenders - life gain should quadruple with 2."""
    print("\n=== Test: Double Rhox Faithmender (Quadruple Life Gain) ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Starting life: {p1.life}")

    # Add TWO Rhox Faithmenders
    for i in range(2):
        game.create_object(
            name=f"Rhox Faithmender {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=RHOX_FAITHMENDER.characteristics,
            card_def=RHOX_FAITHMENDER
        )

    # Gain 1 life - should become 4 (1 * 2 * 2)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 1}
    ))

    print(f"Life after gaining '1' with 2 Rhox: {p1.life}")
    assert p1.life == 24, f"Expected 24 (20 + 1*2*2), got {p1.life}"
    print("✓ Double Rhox quadruples life gain!")


def test_soul_warden_army():
    """Test Soul Warden triggering multiple times from army entering."""
    print("\n=== Test: Soul Warden Army (5 creatures enter) ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put Soul Warden on battlefield
    soul_warden = game.create_object(
        name="Soul Warden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN
    )

    print(f"Starting life: {p1.life}")

    # 5 creatures enter the battlefield
    for i in range(5):
        creature = game.create_object(
            name=f"Soldier Token {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1)
        )
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': creature.id,
                'from_zone': 'hand',
                'to_zone': 'battlefield',
                'to_zone_type': ZoneType.BATTLEFIELD
            }
        ))

    print(f"Life after 5 creatures ETB: {p1.life}")
    assert p1.life == 25, f"Expected 25 (20 + 5), got {p1.life}"
    print("✓ Soul Warden triggers 5 times!")


def test_soul_warden_plus_rhox_army():
    """Test Soul Warden + Rhox Faithmender with army entering."""
    print("\n=== Test: Soul Warden + Rhox + 5 Creatures (Doubled Triggers) ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Put both on battlefield
    game.create_object(
        name="Soul Warden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN
    )

    game.create_object(
        name="Rhox Faithmender",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=RHOX_FAITHMENDER.characteristics,
        card_def=RHOX_FAITHMENDER
    )

    print(f"Starting life: {p1.life}")

    # 5 creatures enter
    for i in range(5):
        creature = game.create_object(
            name=f"Soldier Token {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1)
        )
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': creature.id,
                'from_zone': 'hand',
                'to_zone': 'battlefield',
                'to_zone_type': ZoneType.BATTLEFIELD
            }
        ))

    # Each trigger gains 1 life, doubled to 2, 5 times = 10 life
    print(f"Life after 5 creatures ETB (doubled): {p1.life}")
    assert p1.life == 30, f"Expected 30 (20 + 5*2), got {p1.life}"
    print("✓ Soul Warden + Rhox combo works!")


def test_counter_shenanigans():
    """Test -1/-1 counters reducing a creature to lethal."""
    print("\n=== Test: -1/-1 Counter Death ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Burdened Stoneback is 4/4 that enters with two -1/-1 counters (becomes 2/2)
    card_def = LORWYN_ECLIPSED_CARDS["Burdened Stoneback"]

    creature = game.create_object(
        name="Burdened Stoneback",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # Trigger ETB for counters
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Counters: {creature.state.counters.get('-1/-1', 0)}")
    print(f"Stats: {get_power(creature, game.state)}/{get_toughness(creature, game.state)}")

    # Manually add 2 more -1/-1 counters (simulating Blight Rot or similar)
    creature.state.counters['-1/-1'] = creature.state.counters.get('-1/-1', 0) + 2

    toughness = get_toughness(creature, game.state)
    print(f"After 2 more counters: {get_power(creature, game.state)}/{toughness}")

    assert toughness == 0, f"Expected 0 toughness, got {toughness}"

    # Check SBAs - creature should die
    game.check_state_based_actions()

    print(f"Zone after SBA: {creature.zone}")
    assert creature.zone == ZoneType.GRAVEYARD, "Creature should be dead!"
    print("✓ -1/-1 counters kill creatures correctly!")


def test_lord_stacking():
    """Test multiple Kithkin lords stacking."""
    print("\n=== Test: Multiple Lords Stacking ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create a base Kithkin
    goldmeadow = LORWYN_ECLIPSED_CARDS["Goldmeadow Nomad"]
    kithkin = game.create_object(
        name="Goldmeadow Nomad",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=goldmeadow.characteristics,
        card_def=goldmeadow
    )

    base_power = get_power(kithkin, game.state)
    base_toughness = get_toughness(kithkin, game.state)
    print(f"Base Kithkin: {base_power}/{base_toughness}")

    # Add TWO Champion of the Clachan (each gives other Kithkin +1/+1)
    champion_def = LORWYN_ECLIPSED_CARDS["Champion of the Clachan"]
    for i in range(2):
        game.create_object(
            name=f"Champion of the Clachan {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=champion_def.characteristics,
            card_def=champion_def
        )

    boosted_power = get_power(kithkin, game.state)
    boosted_toughness = get_toughness(kithkin, game.state)
    print(f"With 2 Champions: {boosted_power}/{boosted_toughness}")

    # Base 1/2 + 2 lords = 3/4
    assert boosted_power == base_power + 2, f"Expected {base_power + 2}, got {boosted_power}"
    assert boosted_toughness == base_toughness + 2, f"Expected {base_toughness + 2}, got {boosted_toughness}"
    print("✓ Multiple lords stack correctly!")


def test_fog_bank_vs_massive_damage():
    """Test Fog Bank preventing absurd amounts of damage."""
    print("\n=== Test: Fog Bank vs 1000 Damage ===")

    game = Game()
    p1 = game.add_player("Alice")

    fog_bank = game.create_object(
        name="Fog Bank",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=FOG_BANK.characteristics,
        card_def=FOG_BANK
    )

    print(f"Fog Bank damage before: {fog_bank.state.damage}")

    # Try to deal 1000 damage
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': fog_bank.id, 'amount': 1000}
    ))

    print(f"Fog Bank damage after 1000 damage: {fog_bank.state.damage}")
    assert fog_bank.state.damage == 0, "Fog Bank should prevent all damage!"

    # Make sure it's still alive
    game.check_state_based_actions()
    assert fog_bank.zone == ZoneType.BATTLEFIELD, "Fog Bank should still be alive!"
    print("✓ Fog Bank prevents 1000 damage!")


def test_overkill_damage():
    """Test massive overkill damage to a player."""
    print("\n=== Test: Overkill Damage (100 damage to player) ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    print(f"Bob's life: {p2.life}")

    # Deal 100 damage to Bob
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 100}
    ))

    print(f"Bob's life after 100 damage: {p2.life}")
    assert p2.life == -80, f"Expected -80, got {p2.life}"

    # Check SBAs - Bob should lose
    game.check_state_based_actions()
    print(f"Bob has_lost: {p2.has_lost}")
    assert p2.has_lost, "Bob should have lost the game!"
    print("✓ Overkill damage works correctly!")


def test_triple_rhox_insanity():
    """Test TRIPLE Rhox Faithmender - 8x life gain."""
    print("\n=== Test: Triple Rhox (8x Life Gain) ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Starting life: {p1.life}")

    # THREE Rhox Faithmenders
    for i in range(3):
        game.create_object(
            name=f"Rhox Faithmender {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=RHOX_FAITHMENDER.characteristics,
            card_def=RHOX_FAITHMENDER
        )

    # Gain 1 life - should become 8 (1 * 2 * 2 * 2)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 1}
    ))

    print(f"Life after gaining '1' with 3 Rhox: {p1.life}")
    assert p1.life == 28, f"Expected 28 (20 + 1*8), got {p1.life}"

    # Now gain 10 life - should become 80!
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': 10}
    ))

    print(f"Life after gaining '10' with 3 Rhox: {p1.life}")
    assert p1.life == 108, f"Expected 108 (28 + 10*8), got {p1.life}"
    print("✓ Triple Rhox gives 8x life gain!")


def test_encumbered_reejerey_tap_spam():
    """Test tapping Encumbered Reejerey many times."""
    print("\n=== Test: Encumbered Reejerey Tap Spam ===")

    game = Game()
    p1 = game.add_player("Alice")

    card_def = LORWYN_ECLIPSED_CARDS["Encumbered Reejerey"]
    creature = game.create_object(
        name="Encumbered Reejerey",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # ETB to get 3 counters
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Counters after ETB: {creature.state.counters.get('-1/-1', 0)}")

    # Tap 3 times (remove all counters)
    for i in range(3):
        creature.state.tapped = False
        game.emit(Event(
            type=EventType.TAP,
            payload={'object_id': creature.id}
        ))
        print(f"After tap {i+1}: {creature.state.counters.get('-1/-1', 0)} counters")

    final_counters = creature.state.counters.get('-1/-1', 0)
    assert final_counters == 0, f"Expected 0 counters, got {final_counters}"

    # Now it's a full 5/4!
    power = get_power(creature, game.state)
    toughness = get_toughness(creature, game.state)
    print(f"Final stats (no counters): {power}/{toughness}")
    assert power == 5 and toughness == 4, "Should be full 5/4 now!"
    print("✓ Tap spam removes all counters!")


def test_anthem_on_zero_power_creature():
    """Test anthem effects on 0/X creatures."""
    print("\n=== Test: Anthem on 0/4 Creature ===")

    game = Game()
    p1 = game.add_player("Alice")

    # 0/4 creature
    wall = game.create_object(
        name="Wall",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=0,
            toughness=4
        )
    )

    print(f"Base: {get_power(wall, game.state)}/{get_toughness(wall, game.state)}")

    # Add anthem
    game.create_object(
        name="Glorious Anthem",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GLORIOUS_ANTHEM.characteristics,
        card_def=GLORIOUS_ANTHEM
    )

    power = get_power(wall, game.state)
    toughness = get_toughness(wall, game.state)
    print(f"With Anthem: {power}/{toughness}")
    assert power == 1 and toughness == 5, f"Expected 1/5, got {power}/{toughness}"
    print("✓ 0/4 becomes 1/5 with anthem!")


def test_negative_power_from_counters():
    """Test creature with negative power from counters."""
    print("\n=== Test: Negative Power from Counters ===")

    game = Game()
    p1 = game.add_player("Alice")

    # 1/1 creature
    creature = game.create_object(
        name="Tiny Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=1,
            toughness=3
        )
    )

    # Add 3 -1/-1 counters (power becomes -2, toughness becomes 0)
    creature.state.counters['-1/-1'] = 3

    power = get_power(creature, game.state)
    toughness = get_toughness(creature, game.state)
    print(f"With 3 counters on 1/3: {power}/{toughness}")

    # Power can go negative, but toughness at 0 should kill it
    assert power == -2, f"Expected -2 power, got {power}"
    assert toughness == 0, f"Expected 0 toughness, got {toughness}"

    game.check_state_based_actions()
    assert creature.zone == ZoneType.GRAVEYARD, "Should die from 0 toughness!"
    print("✓ Negative power allowed, 0 toughness kills!")


def test_life_loss_not_doubled():
    """Test that Rhox Faithmender doesn't affect life LOSS."""
    print("\n=== Test: Rhox Doesn't Double Life Loss ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Starting life: {p1.life}")

    # Add Rhox
    game.create_object(
        name="Rhox Faithmender",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=RHOX_FAITHMENDER.characteristics,
        card_def=RHOX_FAITHMENDER
    )

    # Take 5 damage (life loss)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 5}
    ))

    print(f"Life after 5 damage (should NOT be doubled): {p1.life}")
    assert p1.life == 15, f"Expected 15 (damage not doubled), got {p1.life}"
    print("✓ Rhox doesn't double life loss from damage!")


def test_multiple_soul_wardens():
    """Test multiple Soul Wardens all triggering."""
    print("\n=== Test: 3 Soul Wardens (Triple Triggers) ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Create 3 Soul Wardens
    for i in range(3):
        game.create_object(
            name=f"Soul Warden {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=SOUL_WARDEN.characteristics,
            card_def=SOUL_WARDEN
        )

    print(f"Starting life: {p1.life}")

    # One creature enters - all 3 wardens should trigger
    creature = game.create_object(
        name="Random Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2)
    )

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    print(f"Life after 1 creature ETB with 3 Soul Wardens: {p1.life}")
    assert p1.life == 23, f"Expected 23 (20 + 3), got {p1.life}"
    print("✓ All 3 Soul Wardens trigger!")


def test_anthem_plus_counters():
    """Test anthem effect combined with -1/-1 counters."""
    print("\n=== Test: Anthem + Counters Interaction ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Add anthem first
    game.create_object(
        name="Glorious Anthem",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=GLORIOUS_ANTHEM.characteristics,
        card_def=GLORIOUS_ANTHEM
    )

    # Burdened Stoneback: base 4/4, enters with 2 counters, + anthem = 3/3
    card_def = LORWYN_ECLIPSED_CARDS["Burdened Stoneback"]
    creature = game.create_object(
        name="Burdened Stoneback",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )

    # ETB for counters
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': creature.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD
        }
    ))

    # Base 4/4, -2 counters = 2/2, +1/+1 anthem = 3/3
    power = get_power(creature, game.state)
    toughness = get_toughness(creature, game.state)
    print(f"4/4 with 2 counters + anthem: {power}/{toughness}")
    assert power == 3 and toughness == 3, f"Expected 3/3, got {power}/{toughness}"
    print("✓ Anthem + counters layer correctly!")


def test_massive_life_gain_combo():
    """Test Soul Warden + 3 Rhox + 10 creatures = INSANE life gain."""
    print("\n=== Test: Soul Warden + 3 Rhox + 10 Creatures ===")

    game = Game()
    p1 = game.add_player("Alice")

    print(f"Starting life: {p1.life}")

    # Soul Warden
    game.create_object(
        name="Soul Warden",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN
    )

    # 3 Rhox (8x multiplier)
    for i in range(3):
        game.create_object(
            name=f"Rhox {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=RHOX_FAITHMENDER.characteristics,
            card_def=RHOX_FAITHMENDER
        )

    # 10 creatures enter (each triggers Soul Warden for 1 life, x8 = 8 each)
    for i in range(10):
        creature = game.create_object(
            name=f"Token {i+1}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1)
        )
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': creature.id,
                'from_zone': 'hand',
                'to_zone': 'battlefield',
                'to_zone_type': ZoneType.BATTLEFIELD
            }
        ))

    # 10 triggers × 1 life × 8 (from 3 Rhox) = 80 life gained
    print(f"Life after insane combo: {p1.life}")
    assert p1.life == 100, f"Expected 100 (20 + 10*8), got {p1.life}"
    print("✓ Gained 80 life from the combo! Starting 20 → 100!")


def run_all_degenerate_tests():
    """Run all degenerate combo tests."""
    print("=" * 60)
    print("DEGENERATE MTG COMBO TESTS")
    print("=" * 60)

    test_multiple_anthems_stacking()
    test_multiple_rhox_faithmenders()
    test_soul_warden_army()
    test_soul_warden_plus_rhox_army()
    test_counter_shenanigans()
    test_lord_stacking()
    test_fog_bank_vs_massive_damage()
    test_overkill_damage()
    test_triple_rhox_insanity()
    test_encumbered_reejerey_tap_spam()
    test_anthem_on_zero_power_creature()
    test_negative_power_from_counters()
    test_life_loss_not_doubled()
    test_multiple_soul_wardens()
    test_anthem_plus_counters()
    test_massive_life_gain_combo()

    print("\n" + "=" * 60)
    print("ALL DEGENERATE TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_degenerate_tests()
