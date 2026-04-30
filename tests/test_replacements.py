"""
Replacement Effects Framework Tests

Covers:
- make_life_gain_replacer: Angel of Vitality (gain X+1 instead)
- make_life_gain_prevention: Giant Cindermaw (no one gains life)
- make_draw_replacer: "draw twice as many"
- make_counter_doubler: Doubling Season + Loading Zone variant
- make_dies_to_exile_replacer: "If a creature would die, exile it instead"
- make_skip_to_graveyard_replacer: Progenitus / Darksteel Colossus
- make_damage_doubler: Gratuitous Violence + Twinflame Tyrant
- make_graveyard_to_exile_replacer: Dryad Militant
- Anti-loop guard: a doubler does not fire on its own output
"""

import os
import sys

# Resolve project root from this file's location so the test runs both in the
# main checkout and inside a worktree.
_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
sys.path.insert(0, _ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, GameState,
)
from src.engine.replacements import (
    make_life_gain_replacer,
    make_life_gain_prevention,
    make_draw_replacer,
    make_counter_doubler,
    make_dies_to_exile_replacer,
    make_skip_to_graveyard_replacer,
    make_damage_doubler,
    make_graveyard_to_exile_replacer,
)


def _make_game_with_battlefield(players=1):
    game = Game()
    out = []
    for i in range(players):
        p = game.add_player(f"P{i}")
        out.append(p)
    return game, out


def _create_source(game, player, name="Source"):
    return game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=1, toughness=1
        ),
    )


# =============================================================================
# LIFE GAIN
# =============================================================================

def test_life_gain_replacer_angel_of_vitality():
    print("\n=== Test: make_life_gain_replacer (Angel of Vitality) ===")
    game, (p,) = _make_game_with_battlefield()
    p.life = 20
    src = _create_source(game, p, "Angel of Vitality")
    game.register_interceptor(make_life_gain_replacer(src, multiplier=1, addend=1))

    game.emit(Event(type=EventType.LIFE_CHANGE, payload={'player': p.id, 'amount': 3}))
    print(f"Life after gaining 3 (with +1 replacement): {p.life}")
    assert p.life == 24, f"Expected 24, got {p.life}"

    # Life loss must NOT be touched.
    game.emit(Event(type=EventType.LIFE_CHANGE, payload={'player': p.id, 'amount': -2}))
    print(f"Life after losing 2: {p.life}")
    assert p.life == 22, f"Expected 22, got {p.life}"
    print("✓ Angel of Vitality replacement works")


def test_life_gain_prevention_giant_cindermaw():
    print("\n=== Test: make_life_gain_prevention (Giant Cindermaw) ===")
    game, (p,) = _make_game_with_battlefield()
    p.life = 20
    src = _create_source(game, p, "Giant Cindermaw")
    game.register_interceptor(make_life_gain_prevention(src, affects_controller=True, affects_opponents=True))

    game.emit(Event(type=EventType.LIFE_CHANGE, payload={'player': p.id, 'amount': 5}))
    print(f"Life after attempting to gain 5 (with prevention): {p.life}")
    assert p.life == 20, f"Expected 20 (no gain), got {p.life}"
    print("✓ Life gain prevention works")


# =============================================================================
# DRAW
# =============================================================================

def test_draw_replacer_doubles():
    print("\n=== Test: make_draw_replacer (multiplier=2) ===")
    game, (p,) = _make_game_with_battlefield()
    # Seed library with 5 cards.
    library_key = f"library_{p.id}"
    hand_key = f"hand_{p.id}"
    library = game.state.zones[library_key]
    for _ in range(5):
        card = game.create_object(
            name="Filler",
            owner_id=p.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
        )
        # create_object already adds to the right zone, but make sure.
        if card.id not in library.objects:
            library.objects.append(card.id)

    src = _create_source(game, p)
    game.register_interceptor(make_draw_replacer(src, multiplier=2))

    starting_hand = len(game.state.zones[hand_key].objects)
    game.emit(Event(type=EventType.DRAW, payload={'player': p.id, 'amount': 1}))
    drawn = len(game.state.zones[hand_key].objects) - starting_hand
    print(f"Cards drawn after 'draw 1' with x2 replacer: {drawn}")
    assert drawn == 2, f"Expected 2 cards drawn, got {drawn}"
    print("✓ Draw replacer doubles draws")


# =============================================================================
# COUNTERS
# =============================================================================

def test_counter_doubler_doubling_season():
    print("\n=== Test: make_counter_doubler (Doubling Season) ===")
    game, (p,) = _make_game_with_battlefield()
    src = _create_source(game, p, "Doubling Season")
    target = game.create_object(
        name="Counter Target",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
    )
    game.register_interceptor(make_counter_doubler(src))

    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 2},
    ))
    counters = target.state.counters.get('+1/+1', 0)
    print(f"+1/+1 counters after adding 2 with doubler: {counters}")
    assert counters == 4, f"Expected 4, got {counters}"
    print("✓ Counter doubler works")


def test_counter_doubler_anti_loop():
    """A doubler should not fire on the event it just transformed."""
    print("\n=== Test: counter doubler anti-loop ===")
    game, (p,) = _make_game_with_battlefield()
    src = _create_source(game, p)
    target = game.create_object(
        name="Counter Target",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
    )
    game.register_interceptor(make_counter_doubler(src))

    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
    ))
    counters = target.state.counters.get('+1/+1', 0)
    # Should be 2 (1 * 2), NOT 4 (1 * 2 * 2 from re-applying).
    assert counters == 2, f"Expected 2 (no self-loop), got {counters}"
    print(f"Counters after anti-loop check: {counters}")
    print("✓ Anti-loop guard works")


def test_two_independent_doublers_stack():
    """Two independent counter doublers should multiply counters by 4."""
    print("\n=== Test: two independent doublers stack to 4x ===")
    game, (p,) = _make_game_with_battlefield()
    src1 = _create_source(game, p, "Doubler 1")
    src2 = _create_source(game, p, "Doubler 2")
    target = game.create_object(
        name="Counter Target",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
    )
    game.register_interceptor(make_counter_doubler(src1))
    game.register_interceptor(make_counter_doubler(src2))

    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
    ))
    counters = target.state.counters.get('+1/+1', 0)
    print(f"Counters with two independent doublers: {counters}")
    assert counters == 4, f"Expected 4 (two doublers compose), got {counters}"
    print("✓ Independent doublers compose")


# =============================================================================
# DEATH -> EXILE
# =============================================================================

def test_dies_to_exile_replacer():
    print("\n=== Test: make_dies_to_exile_replacer ===")
    game, (p,) = _make_game_with_battlefield()
    src = _create_source(game, p, "Anafenza")
    victim = game.create_object(
        name="Victim",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
    )
    game.register_interceptor(make_dies_to_exile_replacer(src))

    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': victim.id}))
    print(f"Victim zone after destroyed: {victim.zone}")
    assert victim.zone == ZoneType.EXILE, f"Expected EXILE, got {victim.zone}"
    print("✓ Dies-to-exile replacement works")


# =============================================================================
# DEATH -> LIBRARY
# =============================================================================

def test_skip_to_graveyard_progenitus():
    print("\n=== Test: make_skip_to_graveyard_replacer (Progenitus) ===")
    game, (p,) = _make_game_with_battlefield()
    progenitus = game.create_object(
        name="Progenitus",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=10, toughness=10),
    )
    game.register_interceptor(make_skip_to_graveyard_replacer(progenitus, redirect_to=ZoneType.LIBRARY))

    library_key = f"library_{p.id}"
    library = game.state.zones[library_key]
    starting_lib = len(library.objects)

    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': progenitus.id}))
    ending_lib = len(library.objects)

    print(f"Library before: {starting_lib}, after: {ending_lib}")
    print(f"Progenitus zone after destroy attempt: {progenitus.zone}")
    assert progenitus.zone == ZoneType.LIBRARY, f"Expected LIBRARY, got {progenitus.zone}"
    assert ending_lib == starting_lib + 1, "Progenitus should be in library"
    print("✓ Progenitus replacement (-> shuffle into library) works")


# =============================================================================
# DAMAGE doubling
# =============================================================================

def test_damage_doubler_gratuitous_violence():
    print("\n=== Test: make_damage_doubler (Gratuitous Violence) ===")
    game, players = _make_game_with_battlefield(players=2)
    p1, p2 = players
    src = _create_source(game, p1, "Gratuitous Violence")
    attacker = game.create_object(
        name="Attacker",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=3, toughness=3),
    )
    p2.life = 20

    def your_creature_source(damage_source, state: GameState) -> bool:
        if damage_source is None:
            return False
        if damage_source.controller != p1.id:
            return False
        return CardType.CREATURE in damage_source.characteristics.types

    game.register_interceptor(make_damage_doubler(src, source_filter=your_creature_source))

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 3},
        source=attacker.id,
    ))
    expected_dmg = 6
    actual = 20 - p2.life
    print(f"Damage dealt to p2: {actual}")
    assert actual == expected_dmg, f"Expected {expected_dmg} damage, got {actual}"
    print("✓ Damage doubler works")


# =============================================================================
# GRAVEYARD -> EXILE (Dryad Militant)
# =============================================================================

def test_graveyard_to_exile_dryad_militant():
    print("\n=== Test: make_graveyard_to_exile_replacer (Dryad Militant) ===")
    game, (p,) = _make_game_with_battlefield()
    militant = game.create_object(
        name="Dryad Militant",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=1),
    )
    instant = game.create_object(
        name="Lightning Bolt",
        owner_id=p.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )
    game.register_interceptor(make_graveyard_to_exile_replacer(
        militant,
        card_type_filter={CardType.INSTANT, CardType.SORCERY},
    ))

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': instant.id,
            'from_zone_type': ZoneType.STACK,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    print(f"Instant final zone: {instant.zone}")
    assert instant.zone == ZoneType.EXILE, f"Expected EXILE, got {instant.zone}"
    print("✓ Dryad Militant graveyard->exile replacement works")


def run_all():
    print("=" * 60)
    print("REPLACEMENT EFFECTS FRAMEWORK TESTS")
    print("=" * 60)

    test_life_gain_replacer_angel_of_vitality()
    test_life_gain_prevention_giant_cindermaw()
    test_draw_replacer_doubles()
    test_counter_doubler_doubling_season()
    test_counter_doubler_anti_loop()
    test_two_independent_doublers_stack()
    test_dies_to_exile_replacer()
    test_skip_to_graveyard_progenitus()
    test_damage_doubler_gratuitous_violence()
    test_graveyard_to_exile_dryad_militant()

    print("\n" + "=" * 60)
    print("ALL REPLACEMENT TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
