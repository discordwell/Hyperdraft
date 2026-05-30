"""
Test Fae but Mid cards
"""

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

from src.engine import Game, Event, EventType, ZoneType, get_power, get_toughness
from src.cards.custom.fae_but_mid import FAE_BUT_MID_CARDS


def create_creature_on_battlefield(game, player, card_name):
    """
    Helper to create a creature on the battlefield with proper ETB handling.

    Creates in hand first WITHOUT card_def to avoid premature interceptor setup,
    then moves to battlefield via ZONE_CHANGE event which properly sets up
    interceptors AND triggers ETB exactly once.
    """
    card_def = FAE_BUT_MID_CARDS[card_name]

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
    champion_def = FAE_BUT_MID_CARDS["Champion of the Clachan"]
    champion = game.create_object(
        name="Champion of the Clachan",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=champion_def.characteristics,
        card_def=champion_def
    )

    # Create a Kithkin (no ETB needed, just for static effect test)
    kithkin_def = FAE_BUT_MID_CARDS["Goldmeadow Nomad"]
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


def test_heritage_druid_no_infinite_loop():
    """Heritage Druid's mana ability must be FINITE and precondition-gated.

    Regression for the 2026-05-29 polish-pass infinite-loop bug: the original
    cost "Tap three untapped Elves you control" parsed to a `tap` CostStep the
    cost-payer never implemented, so the ability was free + infinitely
    re-activatable and the priority loop ground to the 5000-iteration cap in
    every Elf game. The engine-payable rework uses {T} (self-tap, so a tapped
    Druid can't re-activate) + a precondition of three+ untapped Elves.
    """
    print("\n=== Test: Heritage Druid finite mana ability (loop fix) ===")
    from src.engine import CardType
    from src.engine.activated import can_pay_activation

    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")

    def make_bf(name):
        cd = FAE_BUT_MID_CARDS[name]
        o = game.create_object(name=name, owner_id=p1.id, zone=ZoneType.HAND,
                               characteristics=cd.characteristics, card_def=None)
        o.card_def = cd
        game.emit(Event(type=EventType.ZONE_CHANGE, payload={
            'object_id': o.id, 'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield', 'to_zone_type': ZoneType.BATTLEFIELD}))
        return o

    druid = make_bf("Heritage Druid")
    abils = getattr(druid.state, 'activated_abilities', None) \
        or getattr(druid, 'activated_abilities', None) or []
    assert abils, "Heritage Druid should register an activated ability"
    ab = abils[0]

    # The cost must be the engine-payable {T} self-tap, NOT a free 'tap others'
    # CostStep (which paid nothing and looped forever).
    assert ab.requires_tap is True, "Heritage Druid must tap itself (finite gate)"
    assert ab.additional_cost_plan is None, \
        "Must not carry the unpayable 'tap N others' CostStep"
    assert ab.precondition_fn is not None, "Must be precondition-gated"

    ms = getattr(game, 'mana_system', None)

    # Only the Druid on board (1 untapped Elf) -> precondition fails.
    assert can_pay_activation(ab, druid, game.state, p1.id, mana_system=ms) is False, \
        "Should be illegal with fewer than three untapped Elves"

    # Three untapped Elves + Druid no longer summoning-sick -> legal.
    make_bf("Imperious Perfect")  # Elf
    make_bf("Imperious Perfect")  # Elf
    druid.state.summoning_sickness = False
    assert can_pay_activation(ab, druid, game.state, p1.id, mana_system=ms) is True, \
        "Should be legal with three untapped Elves"

    # After tapping the Druid, it CANNOT re-activate -> the loop is broken.
    druid.state.tapped = True
    assert can_pay_activation(ab, druid, game.state, p1.id, mana_system=ms) is False, \
        "A tapped Druid must not be able to re-activate (no infinite loop)"

    print("✓ Heritage Druid ability is finite + precondition-gated!")


def run_all_tests():
    print("=" * 60)
    print("FAE BUT MID CARD TESTS")
    print("=" * 60)

    test_burdened_stoneback_counters()
    test_champion_of_clachan_lord()
    test_encumbered_reejerey_tap_trigger()
    test_rooftop_percher_life_gain()
    test_heritage_druid_no_infinite_loop()

    print("\n" + "=" * 60)
    print("ALL FAE BUT MID TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
