"""Phase 5b sweep — "activated-from-graveyard" card-set sweep.

Lightweight smoke tests covering the migration of 8 audited cards from
no-op setup_interceptors stubs to real ``setup_in_graveyard`` framework
hooks.

For each wired card we assert:
  * ``CARDDEF.setup_in_graveyard`` is not None,
  * placing the card into the graveyard and invoking the gy-setup
    manually registers either an activated ability or an interceptor
    (depending on the card's pattern).

For deferred cards (engine-gap territory) we assert
``CARDDEF.setup_in_graveyard`` is None (i.e. we did NOT silently wire
something broken) and the printed text remains intact.

Cards covered:

Wired:
  - dutiful_griffin       (WOE)  — activated: {2}{W}, sac 2 enchantments
  - redtooth_vanguard     (WOE)  — trigger: enchantment ETB -> may pay {2}
  - bonebind_orator       (BLB)  — activated: {3}{B}, exile self
  - undead_sprinter       (DSK)  — cast-permission gated on non-Zombie death
  - wolfbat               (TLA)  — trigger: 2nd draw -> may pay {B}

Deferred (engine gap):
  - wishing_well          (BLB)  — reflex-trigger + per-act gy-cast
  - timeline_culler       (EOE)  — warp from gy + life cost
  - muldrotha_the_gravetide (FDN) — per-turn per-type cast slots

Each test runs standalone via ``python tests/test_phase5b_gy_activated.py``
(matching the convention used by the rest of the phase5b suite).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
)


# =============================================================================
# Helpers
# =============================================================================

def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put_card(game, owner, card_def, zone=ZoneType.GRAVEYARD):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _has_activated_ability(obj, cost_substr: str) -> bool:
    abilities = getattr(obj.state, "activated_abilities", None) or []
    for a in abilities:
        ct = getattr(a, "cost_text", "") or ""
        if cost_substr.lower() in ct.lower():
            return True
    return False


def _interceptor_count(game, source_id: str) -> int:
    return sum(1 for i in game.state.interceptors.values() if i.source == source_id)


# =============================================================================
# WIRED — activated-ability migrations
# =============================================================================

def test_dutiful_griffin_gy_activated():
    print("\n=== dutiful_griffin: graveyard {2}{W}, sac two enchantments ===")
    from src.cards.wilds_of_eldraine import DUTIFUL_GRIFFIN
    assert getattr(DUTIFUL_GRIFFIN, "setup_in_graveyard", None) is not None, (
        "DUTIFUL_GRIFFIN should have setup_in_graveyard"
    )
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, DUTIFUL_GRIFFIN, zone=ZoneType.GRAVEYARD)
    DUTIFUL_GRIFFIN.setup_in_graveyard(obj, game.state)
    assert _has_activated_ability(obj, "{2}{W}"), (
        f"Griffin missing gy ability; got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


def test_bonebind_orator_gy_activated():
    print("\n=== bonebind_orator: graveyard {3}{B}, exile self ===")
    from src.cards.bloomburrow import BONEBIND_ORATOR
    assert getattr(BONEBIND_ORATOR, "setup_in_graveyard", None) is not None
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, BONEBIND_ORATOR, zone=ZoneType.GRAVEYARD)
    BONEBIND_ORATOR.setup_in_graveyard(obj, game.state)
    assert _has_activated_ability(obj, "{3}{B}"), (
        f"Bonebind missing gy ability; got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


# =============================================================================
# WIRED — triggered / interceptor migrations
# =============================================================================

def test_redtooth_vanguard_gy_trigger_registered():
    print("\n=== redtooth_vanguard: graveyard enchantment-ETB trigger ===")
    from src.cards.wilds_of_eldraine import REDTOOTH_VANGUARD
    assert getattr(REDTOOTH_VANGUARD, "setup_in_graveyard", None) is not None
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, REDTOOTH_VANGUARD, zone=ZoneType.GRAVEYARD)
    new_ints = REDTOOTH_VANGUARD.setup_in_graveyard(obj, game.state)
    assert new_ints, "Expected 1+ interceptor from gy-setup"
    # Register them on state (mirroring what the engine handler would do).
    for it in new_ints:
        game.state.interceptors[it.id] = it
        obj.interceptor_ids.append(it.id)
    assert _interceptor_count(game, obj.id) >= 1
    # Confirm duration is forever + cleanup-on-zone-change tag set.
    it = new_ints[0]
    assert it.duration == "forever", f"Expected forever, got {it.duration!r}"
    assert getattr(it, "_cleanup_on_zone_change", False) is True, (
        "Trigger should carry _cleanup_on_zone_change=True"
    )
    print("  PASS")


def test_wolfbat_gy_trigger_registered():
    print("\n=== wolfbat: graveyard 2nd-draw trigger ===")
    from src.cards.avatar_tla import WOLFBAT
    assert getattr(WOLFBAT, "setup_in_graveyard", None) is not None
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, WOLFBAT, zone=ZoneType.GRAVEYARD)
    new_ints = WOLFBAT.setup_in_graveyard(obj, game.state)
    assert new_ints, "Expected 1+ interceptor from gy-setup"
    for it in new_ints:
        game.state.interceptors[it.id] = it
        obj.interceptor_ids.append(it.id)
    assert _interceptor_count(game, obj.id) >= 1
    it = new_ints[0]
    assert it.duration == "forever"
    assert getattr(it, "_cleanup_on_zone_change", False) is True
    print("  PASS")


def test_undead_sprinter_gy_cast_permission_registered():
    print("\n=== undead_sprinter: graveyard cast permission interceptor ===")
    from src.cards.duskmourn import UNDEAD_SPRINTER
    assert getattr(UNDEAD_SPRINTER, "setup_in_graveyard", None) is not None
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, UNDEAD_SPRINTER, zone=ZoneType.GRAVEYARD)
    new_ints = UNDEAD_SPRINTER.setup_in_graveyard(obj, game.state)
    assert new_ints, "Expected QUERY-priority cast-permission interceptor"
    for it in new_ints:
        game.state.interceptors[it.id] = it
        obj.interceptor_ids.append(it.id)
    assert _interceptor_count(game, obj.id) >= 1
    # The interceptor should not fire (return False) when no non-Zombie has
    # died this turn. Verify by emitting a synthetic QUERY_CAST_LEGALITY.
    from src.engine.cast_permission import ALLOWED_KEY
    query = Event(
        type=EventType.QUERY_CAST_LEGALITY,
        payload={"card_id": obj.id, ALLOWED_KEY: False},
        controller=p1.id,
    )
    assert not new_ints[0].filter(query, game.state), (
        "Cast permission should NOT be granted when no non-Zombie died this turn"
    )
    # Now simulate a non-Zombie death: add a creature to graveyard and stamp
    # the died-this-turn tracker.
    from src.engine.types import Characteristics
    elf = game.create_object(
        name="Elf",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Elf"},
            colors={Color.GREEN},
            power=1, toughness=1,
        ),
    )
    game.state.turn_data.setdefault("_died_counted_this_turn", set()).add(elf.id)
    assert new_ints[0].filter(query, game.state), (
        "Cast permission SHOULD be granted after a non-Zombie has died"
    )
    print("  PASS")


# =============================================================================
# DEFERRED — engine-gap stubs (assert they remain unset)
# =============================================================================

def test_wishing_well_remains_deferred():
    print("\n=== wishing_well: deferred engine-gap stub ===")
    from src.cards.bloomburrow import WISHING_WELL
    # Reflex-trigger + per-act gy-cast not yet wired. Confirm no
    # setup_in_graveyard hook was added by mistake.
    assert getattr(WISHING_WELL, "setup_in_graveyard", None) is None, (
        "WISHING_WELL must remain deferred until reflex-trigger primitive lands"
    )
    print("  PASS (correctly deferred)")


def test_timeline_culler_remains_deferred():
    print("\n=== timeline_culler: deferred engine-gap stub ===")
    from src.cards.edge_of_eternities import TIMELINE_CULLER
    assert getattr(TIMELINE_CULLER, "setup_in_graveyard", None) is None, (
        "TIMELINE_CULLER must remain deferred until warp-from-gy + life cost lands"
    )
    print("  PASS (correctly deferred)")


def test_muldrotha_remains_deferred():
    print("\n=== muldrotha_the_gravetide: deferred engine-gap stub ===")
    from src.cards.foundations import MULDROTHA_THE_GRAVETIDE
    assert getattr(MULDROTHA_THE_GRAVETIDE, "setup_in_graveyard", None) is None, (
        "MULDROTHA must remain deferred until per-type cast slots land"
    )
    print("  PASS (correctly deferred)")


# =============================================================================
# Aggregate: 5/8 wired this sweep
# =============================================================================

def test_phase5b_gy_sweep_size():
    """Pin the wired delta from this sweep so regressions stay loud."""
    print("\n=== aggregate: 5 wired + 3 deferred in this sweep ===")
    from src.cards.wilds_of_eldraine import DUTIFUL_GRIFFIN, REDTOOTH_VANGUARD
    from src.cards.bloomburrow import BONEBIND_ORATOR, WISHING_WELL
    from src.cards.duskmourn import UNDEAD_SPRINTER
    from src.cards.avatar_tla import WOLFBAT
    from src.cards.edge_of_eternities import TIMELINE_CULLER
    from src.cards.foundations import MULDROTHA_THE_GRAVETIDE

    wired = [DUTIFUL_GRIFFIN, REDTOOTH_VANGUARD, BONEBIND_ORATOR,
             UNDEAD_SPRINTER, WOLFBAT]
    deferred = [WISHING_WELL, TIMELINE_CULLER, MULDROTHA_THE_GRAVETIDE]

    wired_count = sum(1 for c in wired if getattr(c, "setup_in_graveyard", None))
    deferred_count = sum(1 for c in deferred if getattr(c, "setup_in_graveyard", None) is None)

    assert wired_count == 5, f"Expected 5 wired, got {wired_count}"
    assert deferred_count == 3, f"Expected 3 deferred, got {deferred_count}"
    print(f"  wired={wired_count} deferred={deferred_count}")
    print("  PASS")


# =============================================================================
# Driver
# =============================================================================

if __name__ == "__main__":
    tests = [
        test_dutiful_griffin_gy_activated,
        test_bonebind_orator_gy_activated,
        test_redtooth_vanguard_gy_trigger_registered,
        test_wolfbat_gy_trigger_registered,
        test_undead_sprinter_gy_cast_permission_registered,
        test_wishing_well_remains_deferred,
        test_timeline_culler_remains_deferred,
        test_muldrotha_remains_deferred,
        test_phase5b_gy_sweep_size,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"  FAIL: {t.__name__}: {e!r}")
            import traceback
            traceback.print_exc()
            failed.append(t.__name__)
    print()
    print("=" * 60)
    if failed:
        print(f"FAILED ({len(failed)}/{len(tests)}): {failed}")
        sys.exit(1)
    print(f"ALL {len(tests)} PHASE 5b GY-ACTIVATED TESTS PASSED")
    print("=" * 60)
