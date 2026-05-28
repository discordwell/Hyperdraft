"""
Tests for the DEPTHS_BECOME_UNDETECTED and DAMAGE_REMOVE event types
plus their REACT handlers in src/engine/depths.py.

Backs the 3 cards that previously failed the per-card interceptor
audit because they mutated state directly with no engine event:

  - Damage Control       (submarine_fleet/neutral.py)       -> DAMAGE_REMOVE
  - Dead-Stop Maneuver   (submarine_fleet/silent_hunter.py) -> DEPTHS_BECOME_UNDETECTED
  - Quiet Reload         (submarine_fleet/silent_hunter.py) -> DEPTHS_BECOME_UNDETECTED
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (  # noqa: E402
    CardDefinition, Characteristics, CardType, Event, EventType, ZoneType,
)
from src.engine.game import Game  # noqa: E402
from src.engine.depths import (  # noqa: E402
    DepthBand, FLAGSHIP_HULL, get_flagship, is_vessel, setup_depths_player,
)
from src.engine.depths_turn import DepthsTurnManager  # noqa: E402
from src.cards.depths.submarine_fleet.neutral import DAMAGE_CONTROL  # noqa: E402
from src.cards.depths.submarine_fleet.silent_hunter import (  # noqa: E402
    DEAD_STOP_MANEUVER, QUIET_RELOAD,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_flagship_def() -> CardDefinition:
    chars = Characteristics(
        types={CardType.DEPTHS_VESSEL},
        subtypes={"Flagship"},
        power=0,
        toughness=FLAGSHIP_HULL,
    )
    cd = CardDefinition(
        name="Test Flagship",
        mana_cost=None,
        characteristics=chars,
        text="Flagship.",
    )
    cd.depths_flagship = True
    cd.depths_starting_depth = DepthBand.PERISCOPE
    return cd


def _make_vessel_def(name: str = "Test Sub", *, power: int = 2, hull: int = 3) -> CardDefinition:
    chars = Characteristics(
        types={CardType.DEPTHS_VESSEL},
        subtypes={"Submarine"},
        power=power,
        toughness=hull,
    )
    return CardDefinition(
        name=name,
        mana_cost="{1T}",
        characteristics=chars,
        text="Vanilla sub.",
    )


def _bootstrap_game():
    """Spin up a Depths game with one Submarine on each side."""
    game = Game(mode="depths")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    tm = DepthsTurnManager(game.state)
    game.turn_manager = tm

    flagship_def = _make_flagship_def()
    # Tiny decks — we don't run turns, we just want the system
    # interceptors registered and the Flagships placed.
    sub_def = _make_vessel_def()
    deck = [sub_def] * 10

    setup_depths_player(game, p1, deck, flagship_def)
    setup_depths_player(game, p2, deck, flagship_def)
    # System interceptors are auto-registered by Game.__init__ via
    # mode_adapter.register_system_interceptors(self) — no second call.

    return game, p1, p2


def _place_submarine(game, player_id: str, *, detected: bool = False, damage: int = 0):
    """Create a non-Flagship submarine on the battlefield for ``player_id``."""
    sub_def = _make_vessel_def()
    import copy
    obj = game.create_object(
        name=sub_def.name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=copy.deepcopy(sub_def.characteristics),
        card_def=sub_def,
    )
    obj.state.depth_band = DepthBand.PERISCOPE
    obj.state.detected = detected
    if detected:
        obj.state.detected_until = "forever"
    obj.state.damage = damage
    obj.state.summoning_sickness = False
    return obj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_depths_become_undetected_event_flips_state():
    """Bare-bones: emitting DEPTHS_BECOME_UNDETECTED for a detected
    vessel flips state.detected to False."""
    game, p1, _ = _bootstrap_game()
    sub = _place_submarine(game, p1.id, detected=True)
    assert sub.state.detected is True

    game.emit(Event(
        type=EventType.DEPTHS_BECOME_UNDETECTED,
        payload={"object_id": sub.id, "source": "TEST"},
        source="TEST",
        controller=p1.id,
    ))
    assert sub.state.detected is False, "REACT handler should flip detected=False"
    assert sub.state.detected_until is None
    print("  [OK] DEPTHS_BECOME_UNDETECTED REACT handler works")


def test_damage_remove_event_decrements_damage():
    """Emitting DAMAGE_REMOVE for amount N reduces state.damage by N
    (clamped at 0)."""
    game, p1, _ = _bootstrap_game()
    sub = _place_submarine(game, p1.id, damage=5)
    assert sub.state.damage == 5

    game.emit(Event(
        type=EventType.DAMAGE_REMOVE,
        payload={"object_id": sub.id, "amount": 3},
        source="TEST",
        controller=p1.id,
    ))
    assert sub.state.damage == 2, f"expected damage=2 after removing 3, got {sub.state.damage}"

    # Clamp test — try to remove more damage than is present.
    game.emit(Event(
        type=EventType.DAMAGE_REMOVE,
        payload={"object_id": sub.id, "amount": 10},
        source="TEST",
        controller=p1.id,
    ))
    assert sub.state.damage == 0, f"damage should clamp at 0, got {sub.state.damage}"
    print("  [OK] DAMAGE_REMOVE REACT handler decrements + clamps")


def test_damage_remove_mirrors_onto_flagship_life():
    """When the target is a Flagship, DAMAGE_REMOVE should mirror the
    healed damage onto ``player.life`` so SBA/UI stay in sync."""
    game, p1, _ = _bootstrap_game()
    flagship = get_flagship(p1.id, game.state)
    assert flagship is not None
    flagship.state.damage = 7
    # Mirror initial state — flagship damage taken should be reflected.
    p1.life = FLAGSHIP_HULL - 7  # simulate prior apply_player_damage

    game.emit(Event(
        type=EventType.DAMAGE_REMOVE,
        payload={"object_id": flagship.id, "amount": 4},
        source="TEST",
        controller=p1.id,
    ))
    assert flagship.state.damage == 3, f"flagship damage should be 3, got {flagship.state.damage}"
    assert p1.life == FLAGSHIP_HULL - 3, (
        f"player.life should mirror flagship hull (expected {FLAGSHIP_HULL - 3}, got {p1.life})"
    )
    print("  [OK] DAMAGE_REMOVE mirrors Flagship onto player.life")


def test_damage_control_card_emits_damage_remove():
    """Cast Damage Control with a damaged friendly Vessel — the
    cast_effect_fn returns a DAMAGE_REMOVE event for the most-damaged
    target."""
    game, p1, _ = _bootstrap_game()
    sub = _place_submarine(game, p1.id, damage=5)

    # Build a synthetic source object for the cast_effect_fn.
    src = game.create_object(
        name="Damage Control",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(types={CardType.INSTANT}),
        card_def=DAMAGE_CONTROL,
    )

    produced = DAMAGE_CONTROL.cast_effect_fn(src, game.state)
    assert produced, "Damage Control should produce events when a damaged friendly Vessel exists"
    assert any(ev.type == EventType.DAMAGE_REMOVE for ev in produced), (
        f"expected DAMAGE_REMOVE in produced events, got {[e.type for e in produced]}"
    )

    # Push through pipeline and verify state.damage drops.
    for ev in produced:
        game.emit(ev)
    assert sub.state.damage == 2, f"after heal expected 2, got {sub.state.damage}"
    print("  [OK] Damage Control card emits DAMAGE_REMOVE and heals through pipeline")


def test_dead_stop_maneuver_emits_become_undetected():
    """Dead-Stop Maneuver picks a detected friendly Vessel and emits
    DEPTHS_BECOME_UNDETECTED + GRANT_KEYWORD."""
    game, p1, _ = _bootstrap_game()
    sub = _place_submarine(game, p1.id, detected=True)

    src = game.create_object(
        name="Dead-Stop Maneuver",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(types={CardType.INSTANT}),
        card_def=DEAD_STOP_MANEUVER,
    )

    produced = DEAD_STOP_MANEUVER.cast_effect_fn(src, game.state)
    types = [ev.type for ev in produced]
    assert EventType.DEPTHS_BECOME_UNDETECTED in types, (
        f"expected DEPTHS_BECOME_UNDETECTED, got {types}"
    )
    assert EventType.GRANT_KEYWORD in types, (
        f"expected GRANT_KEYWORD (silent_running), got {types}"
    )

    # Push through pipeline; the REACT handler should flip detected.
    for ev in produced:
        game.emit(ev)
    assert sub.state.detected is False, "detected should be False after pipeline"
    print("  [OK] Dead-Stop Maneuver emits DEPTHS_BECOME_UNDETECTED and undetects")


def test_quiet_reload_emits_become_undetected_and_grants_charges():
    """Quiet Reload emits DEPTHS_BECOME_UNDETECTED and grants 2 TC."""
    game, p1, _ = _bootstrap_game()
    sub = _place_submarine(game, p1.id, detected=True)
    initial_tc = p1.tc

    src = game.create_object(
        name="Quiet Reload",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(types={CardType.INSTANT}),
        card_def=QUIET_RELOAD,
    )

    produced = QUIET_RELOAD.cast_effect_fn(src, game.state)
    types = [ev.type for ev in produced]
    assert EventType.DEPTHS_BECOME_UNDETECTED in types, (
        f"expected DEPTHS_BECOME_UNDETECTED, got {types}"
    )

    for ev in produced:
        game.emit(ev)
    assert sub.state.detected is False, "detected should flip via REACT handler"
    assert p1.tc == min(10, initial_tc + 2), (
        f"expected TC +2 (cap 10), got {p1.tc} (was {initial_tc})"
    )
    print("  [OK] Quiet Reload emits DEPTHS_BECOME_UNDETECTED + grants 2 TC")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("DEPTHS — DEPTHS_BECOME_UNDETECTED + DAMAGE_REMOVE TESTS")
    print("=" * 60)
    tests = [
        test_depths_become_undetected_event_flips_state,
        test_damage_remove_event_decrements_damage,
        test_damage_remove_mirrors_onto_flagship_life,
        test_damage_control_card_emits_damage_remove,
        test_dead_stop_maneuver_emits_become_undetected,
        test_quiet_reload_emits_become_undetected_and_grants_charges,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
        except Exception as exc:
            failed += 1
            import traceback
            print(f"  [ERROR] {fn.__name__}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print("=" * 60)
    if failed:
        print(f"{failed}/{len(tests)} tests FAILED")
        sys.exit(1)
    print(f"All {len(tests)} tests passed.")
    sys.exit(0)
