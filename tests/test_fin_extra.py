"""
Final Fantasy "extra" wiring tests for the W14 follow-up gaps:

- ``make_token_copy_from_graveyard``: snapshot a graveyard card into a fresh
  token-copy on the battlefield. The original card stays in the graveyard
  (until the calling card opts to exile it).
- ``make_top_n_land_pick``: look at top N library cards, may put a LAND from
  among them onto the battlefield (tapped). Non-picked cards bottom in
  random order.
- Card wirings: Sin Spira's Punishment, Ignis Scientia, Sandworm.

Run directly: ``python tests/test_fin_extra.py``
"""

import os
import random
import sys

_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)

from src.cards.interceptor_helpers import (
    make_token_copy_from_graveyard,
    make_top_n_land_pick,
)
from src.cards.final_fantasy import (
    IGNIS_SCIENTIA,
    SIN_SPIRAS_PUNISHMENT,
    SANDWORM,
    FIRION_WILD_ROSE_WARRIOR,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _new_game(num_players: int = 2):
    g = Game(mode="mtg")
    players = [g.add_player(f"P{i}", life=20) for i in range(num_players)]
    if num_players >= 1:
        g.state.active_player = players[0].id
    return g, players


def _put_on_battlefield(game, owner_id, card_def, name=None):
    return game.create_object(
        name=name or card_def.name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _put_in_hand(game, owner_id, card_def, name=None):
    return game.create_object(
        name=name or card_def.name,
        owner_id=owner_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _emit_etb(game, obj, owner_id):
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{owner_id}',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))


def _put_in_graveyard(game, owner_id, *, name="Bear", power=2, toughness=2,
                     subtypes=None, types=None):
    """Spawn a card directly into a player's graveyard."""
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(
            types=types or {CardType.CREATURE},
            subtypes=subtypes or set(),
            power=power,
            toughness=toughness,
        ),
    )


def _put_in_library(game, owner_id, *, name="Filler", types=None,
                    supertypes=None, subtypes=None, power=None, toughness=None):
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types=types or {CardType.CREATURE},
            supertypes=supertypes or set(),
            subtypes=subtypes or set(),
            power=power,
            toughness=toughness,
        ),
    )


# =============================================================================
# Token-copy from graveyard
# =============================================================================

def test_token_copy_from_gy_snapshots_pt_types_subtypes_keywords():
    print("\n=== Test: make_token_copy_from_graveyard snapshots characteristics ===")
    g, (p, _) = _new_game(2)
    target = _put_in_graveyard(
        g, p.id, name="Goblin Hero", power=3, toughness=2,
        subtypes={"Goblin", "Warrior"},
    )
    target.characteristics.abilities = [{'keyword': 'haste'}]

    bf_before = len(g.state.zones['battlefield'].objects)

    events = make_token_copy_from_graveyard(
        g.state, controller=p.id, source_card_id=target.id, tapped=True,
    )
    assert len(events) == 1
    for ev in events:
        g.emit(ev)

    bf_after = len(g.state.zones['battlefield'].objects)
    assert bf_after == bf_before + 1, "Token should appear on battlefield"

    # Find the new token (battlefield's last entry).
    token_id = g.state.zones['battlefield'].objects[-1]
    token = g.state.objects[token_id]

    assert token.is_token, "Token should be marked as a token"
    assert token.controller == p.id, "Controller should be p"
    assert token.characteristics.power == 3
    assert token.characteristics.toughness == 2
    assert "Goblin" in token.characteristics.subtypes
    assert "Warrior" in token.characteristics.subtypes
    assert any(
        a.get('keyword') == 'haste' for a in token.characteristics.abilities
    ), "Haste should carry over from snapshot"
    assert token.state.tapped, "tapped=True should put the token in tapped"
    print(f"PASS: token snapshot 3/2 Goblin Warrior (haste, tapped) created")


def test_token_copy_original_stays_in_graveyard():
    print("\n=== Test: token-copy leaves original in graveyard ===")
    g, (p, _) = _new_game(2)
    target = _put_in_graveyard(g, p.id, name="Bear", power=2, toughness=2,
                                subtypes={"Bear"})

    events = make_token_copy_from_graveyard(
        g.state, controller=p.id, source_card_id=target.id,
    )
    for ev in events:
        g.emit(ev)

    # Original card is still in the graveyard.
    gy = g.state.zones[f'graveyard_{p.id}']
    assert target.id in gy.objects, "Original should still be in graveyard"
    assert target.zone == ZoneType.GRAVEYARD, "Original zone unchanged"
    print("PASS: original graveyard card untouched")


def test_token_copy_invalid_source_returns_empty():
    print("\n=== Test: token-copy with non-graveyard source returns [] ===")
    g, (p, _) = _new_game(2)
    # Source on battlefield, not in graveyard -> helper rejects.
    bf_card = g.create_object(
        name="Bear", owner_id=p.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2),
    )
    events = make_token_copy_from_graveyard(
        g.state, controller=p.id, source_card_id=bf_card.id,
    )
    assert events == [], "Helper should reject non-graveyard source"

    # Missing id -> [].
    events = make_token_copy_from_graveyard(
        g.state, controller=p.id, source_card_id="nonexistent",
    )
    assert events == [], "Helper should reject missing source"
    print("PASS: non-graveyard / missing source rejected")


# =============================================================================
# Look-N-land-pick
# =============================================================================

def test_top_n_land_pick_offers_choice_when_lands_present():
    print("\n=== Test: top-N-land-pick offers choice when lands present ===")
    random.seed(42)
    g, (p, _) = _new_game(2)
    # Build a library: 2 lands, 3 non-lands at the top.
    forest = _put_in_library(g, p.id, name="Forest", types={CardType.LAND},
                              supertypes={"Basic"}, subtypes={"Forest"})
    plains = _put_in_library(g, p.id, name="Plains", types={CardType.LAND},
                              supertypes={"Basic"}, subtypes={"Plains"})
    bear1 = _put_in_library(g, p.id, name="Bear1", power=2, toughness=2)
    bear2 = _put_in_library(g, p.id, name="Bear2", power=2, toughness=2)
    bear3 = _put_in_library(g, p.id, name="Bear3", power=2, toughness=2)

    # Library order is [forest, plains, bear1, bear2, bear3] (insertion order).
    bf_before = len(g.state.zones['battlefield'].objects)

    make_top_n_land_pick(
        g.state, controller=p.id, source_id="src", n=5,
        put_tapped=True, optional=True,
    )

    pc = g.state.pending_choice
    assert pc is not None, "Should install a PendingChoice"
    assert pc.choice_type == "top_n_land_pick"
    # Options: 2 lands + 1 'decline' (since optional).
    assert len(pc.options) == 3
    # Pick the forest.
    ok, err, _ = g.submit_choice(pc.id, p.id, [forest.id])
    assert ok, f"submit_choice should succeed: {err}"

    bf_after = g.state.zones['battlefield'].objects
    assert len(bf_after) == bf_before + 1, "Forest should land on battlefield"
    assert forest.id in bf_after, "Forest id should appear on battlefield"
    forest_obj = g.state.objects[forest.id]
    assert forest_obj.zone == ZoneType.BATTLEFIELD
    assert forest_obj.state.tapped, "Forest should enter tapped"

    # Remaining 4 cards (plains + 3 bears) should be on the bottom of the
    # library. Library starts with these 4 and the original cards we never
    # looked at (none in this test); they should all be present.
    lib = g.state.zones[f'library_{p.id}']
    assert plains.id in lib.objects, "Plains bottoms back into library"
    assert all(b.id in lib.objects for b in (bear1, bear2, bear3)), \
        "Non-picked cards bottom into library"
    print(f"PASS: forest on bf tapped; remaining 4 bottomed (lib size {len(lib.objects)})")


def test_top_n_land_pick_no_land_auto_bottoms_all():
    print("\n=== Test: top-N-land-pick auto-bottoms when no lands ===")
    random.seed(7)
    g, (p, _) = _new_game(2)
    bears = [
        _put_in_library(g, p.id, name=f"Bear{i}", power=2, toughness=2)
        for i in range(4)
    ]
    bf_before = len(g.state.zones['battlefield'].objects)

    make_top_n_land_pick(
        g.state, controller=p.id, source_id="src", n=4,
        put_tapped=True, optional=True,
    )

    # No land -> no choice presented; all bottomed.
    assert g.state.pending_choice is None, "No choice should be presented"
    bf_after = len(g.state.zones['battlefield'].objects)
    assert bf_after == bf_before, "Battlefield count unchanged"

    lib = g.state.zones[f'library_{p.id}']
    for b in bears:
        assert b.id in lib.objects, f"{b.name} should still be in library"
    print(f"PASS: no land -> all 4 bottomed, no choice presented")


def test_top_n_land_pick_decline_bottoms_all():
    print("\n=== Test: top-N-land-pick decline bottoms all ===")
    random.seed(123)
    g, (p, _) = _new_game(2)
    forest = _put_in_library(g, p.id, name="Forest", types={CardType.LAND},
                              supertypes={"Basic"}, subtypes={"Forest"})
    bear = _put_in_library(g, p.id, name="Bear", power=2, toughness=2)

    bf_before = len(g.state.zones['battlefield'].objects)

    make_top_n_land_pick(
        g.state, controller=p.id, source_id="src", n=2,
        put_tapped=True, optional=True,
    )

    pc = g.state.pending_choice
    assert pc is not None
    # Decline.
    ok, err, _ = g.submit_choice(pc.id, p.id, [{'id': 'decline'}])
    assert ok, f"submit_choice decline should succeed: {err}"

    bf_after = len(g.state.zones['battlefield'].objects)
    assert bf_after == bf_before, "Decline -> nothing onto battlefield"

    lib = g.state.zones[f'library_{p.id}']
    assert forest.id in lib.objects
    assert bear.id in lib.objects
    print("PASS: decline bottoms forest + bear")


def test_top_n_land_pick_library_smaller_than_n():
    print("\n=== Test: top-N-land-pick handles library smaller than N ===")
    random.seed(99)
    g, (p, _) = _new_game(2)
    forest = _put_in_library(g, p.id, name="Forest", types={CardType.LAND},
                              supertypes={"Basic"}, subtypes={"Forest"})

    make_top_n_land_pick(
        g.state, controller=p.id, source_id="src", n=10,
        put_tapped=True, optional=True,
    )

    pc = g.state.pending_choice
    assert pc is not None, "Choice should still be presented (forest is a land)"
    # Options: forest + decline.
    assert len(pc.options) == 2
    ok, err, _ = g.submit_choice(pc.id, p.id, [forest.id])
    assert ok, f"submit_choice should succeed: {err}"

    bf = g.state.zones['battlefield'].objects
    assert forest.id in bf
    print("PASS: library of 1 still works under n=10")


def test_top_n_land_pick_empty_library_returns_empty():
    print("\n=== Test: top-N-land-pick handles empty library ===")
    g, (p, _) = _new_game(2)
    make_top_n_land_pick(
        g.state, controller=p.id, source_id="src", n=5,
        put_tapped=True, optional=True,
    )
    assert g.state.pending_choice is None, "No choice for empty library"
    print("PASS: empty library -> no choice")


# =============================================================================
# Sin, Spira's Punishment
# =============================================================================

def test_sin_spira_etb_creates_token_copy_from_gy():
    print("\n=== Test: Sin Spira's Punishment ETB exiles + token-copies ===")
    random.seed(31337)
    g, (p, _) = _new_game(2)
    # Stock the controller's graveyard with a creature.
    bear = _put_in_graveyard(g, p.id, name="Bear", power=2, toughness=2,
                              subtypes={"Bear"})

    sin_obj = _put_in_hand(g, p.id, SIN_SPIRAS_PUNISHMENT)
    bf_before = len(g.state.zones['battlefield'].objects)
    gy_before = len(g.state.zones[f'graveyard_{p.id}'].objects)
    exile_before = len(g.state.zones['exile'].objects)

    _emit_etb(g, sin_obj, p.id)

    bf_after = len(g.state.zones['battlefield'].objects)
    gy_after = len(g.state.zones[f'graveyard_{p.id}'].objects)
    exile_after = len(g.state.zones['exile'].objects)

    # Sin enters battlefield (+1) plus a token-copy of the bear (+1) = +2.
    assert bf_after == bf_before + 2, f"Expected +2 on bf, got {bf_after - bf_before}"
    # Bear exiled from graveyard.
    assert gy_after == gy_before - 1, "Bear should have left the graveyard"
    assert exile_after == exile_before + 1, "Bear should be in exile"

    # The token has Bear's stats and is tapped.
    bf_objs = [g.state.objects[oid] for oid in g.state.zones['battlefield'].objects]
    tokens = [o for o in bf_objs if o.is_token and o.name == "Bear"]
    assert tokens, "Bear token should exist on battlefield"
    tok = tokens[0]
    assert tok.characteristics.power == 2
    assert tok.characteristics.toughness == 2
    assert tok.state.tapped, "Sin's tokens enter tapped"
    print("PASS: Sin Spira's ETB -> Bear exiled, tapped 2/2 Bear token created")


def test_sin_spira_no_permanents_in_gy_no_op():
    print("\n=== Test: Sin Spira's Punishment with empty graveyard ===")
    g, (p, _) = _new_game(2)

    sin_obj = _put_in_hand(g, p.id, SIN_SPIRAS_PUNISHMENT)
    bf_before = len(g.state.zones['battlefield'].objects)

    _emit_etb(g, sin_obj, p.id)

    bf_after = len(g.state.zones['battlefield'].objects)
    # Only Sin enters; no extra token.
    assert bf_after == bf_before + 1
    print("PASS: empty graveyard -> Sin enters alone")


# =============================================================================
# Ignis Scientia
# =============================================================================

def test_ignis_scientia_etb_opens_top_6_choice_with_land():
    print("\n=== Test: Ignis Scientia ETB opens top-6-land-pick ===")
    random.seed(0xDEAD)
    g, (p, _) = _new_game(2)
    forest = _put_in_library(g, p.id, name="Forest", types={CardType.LAND},
                              supertypes={"Basic"}, subtypes={"Forest"})
    for i in range(5):
        _put_in_library(g, p.id, name=f"Bear{i}", power=2, toughness=2)

    ignis = _put_in_hand(g, p.id, IGNIS_SCIENTIA)
    _emit_etb(g, ignis, p.id)

    pc = g.state.pending_choice
    assert pc is not None, "Ignis should open a top-N-land-pick choice"
    assert pc.choice_type == "top_n_land_pick"
    # Forest + decline.
    assert any(o == forest.id for o in pc.options if not isinstance(o, dict))
    # Submit Forest.
    ok, err, _ = g.submit_choice(pc.id, p.id, [forest.id])
    assert ok, f"submit_choice should succeed: {err}"

    bf = g.state.zones['battlefield'].objects
    assert forest.id in bf
    forest_obj = g.state.objects[forest.id]
    assert forest_obj.state.tapped, "Ignis puts the land tapped"
    print("PASS: Ignis ETB -> Forest tapped on battlefield")


def test_ignis_scientia_etb_no_land_no_choice():
    print("\n=== Test: Ignis Scientia ETB with no land in top 6 ===")
    g, (p, _) = _new_game(2)
    for i in range(8):
        _put_in_library(g, p.id, name=f"Bear{i}", power=2, toughness=2)

    ignis = _put_in_hand(g, p.id, IGNIS_SCIENTIA)
    bf_before = len(g.state.zones['battlefield'].objects)
    _emit_etb(g, ignis, p.id)

    # No land -> no choice; only Ignis on bf.
    assert g.state.pending_choice is None
    bf_after = len(g.state.zones['battlefield'].objects)
    assert bf_after == bf_before + 1, "Only Ignis enters when no land in top 6"
    print("PASS: no land in top 6 -> no choice")


# =============================================================================
# Firion, Wild Rose Warrior — characteristics.name AttributeError regression
# =============================================================================

def test_firion_etb_does_not_attributeerror_on_equipment():
    """Regression: Firion's equipment-ETB trigger previously read
    ``entering.characteristics.name`` (no such attribute on Characteristics),
    which silently swallowed an AttributeError in the trigger drain and ate
    the token. Patch swaps to ``entering.card_def.name``; the trigger should
    now emit a CREATE_TOKEN event whose name matches the source equipment.
    """
    print("\n=== Test: Firion equipment-ETB trigger no longer AttributeErrors ===")
    g, (p, _) = _new_game(2)

    firion = _put_on_battlefield(g, p.id, FIRION_WILD_ROSE_WARRIOR)

    # Build a vanilla Equipment with a card_def so card_def.name is readable.
    from src.engine.types import CardDefinition
    eq_def = CardDefinition(
        name="Test Sword",
        mana_cost="{2}",
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes={"Equipment"},
        ),
    )
    eq = g.create_object(
        name=eq_def.name,
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=eq_def.characteristics,
        card_def=eq_def,
    )

    # Snapshot current event log size, then emit equipment ETB.
    log_size_before = len(g.state.event_log)
    g.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': eq.id,
            'from_zone': f'hand_{p.id}',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))

    # Find the CREATE_TOKEN events that fired after the ZONE_CHANGE.
    new_events = g.state.event_log[log_size_before:]
    token_events = [e for e in new_events if e.type == EventType.CREATE_TOKEN]
    assert token_events, (
        "Firion's ETB trigger should produce a CREATE_TOKEN; pre-fix this was "
        "lost when entering.characteristics.name raised AttributeError"
    )
    # The trigger payload should carry the source equipment's name.
    payload = token_events[0].payload
    assert payload.get('name') == "Test Sword", (
        f"Expected token named 'Test Sword' (from card_def.name); got {payload!r}"
    )
    print("PASS: Firion ETB trigger emits CREATE_TOKEN with card_def.name")


# =============================================================================
# Sandworm
# =============================================================================

def test_sandworm_wired():
    print("\n=== Test: Sandworm ETB still wired (W14 baseline) ===")
    g, (p, opp) = _new_game(2)
    # A land to target.
    g.create_object(
        name="Mountain", owner_id=opp.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.LAND}, supertypes={"Basic"}, subtypes={"Mountain"},
        ),
    )
    sw = _put_in_hand(g, p.id, SANDWORM)
    _emit_etb(g, sw, p.id)

    pc = g.state.pending_choice
    assert pc is not None, "Sandworm should open a target-with-callback for the land"
    assert pc.choice_type == "target_with_callback"
    print(f"PASS: Sandworm wired (target choice with {len(pc.options)} option(s))")


# =============================================================================
# Test runner
# =============================================================================

def main():
    tests = [
        # Token-copy helper
        test_token_copy_from_gy_snapshots_pt_types_subtypes_keywords,
        test_token_copy_original_stays_in_graveyard,
        test_token_copy_invalid_source_returns_empty,
        # Top-N-land-pick helper
        test_top_n_land_pick_offers_choice_when_lands_present,
        test_top_n_land_pick_no_land_auto_bottoms_all,
        test_top_n_land_pick_decline_bottoms_all,
        test_top_n_land_pick_library_smaller_than_n,
        test_top_n_land_pick_empty_library_returns_empty,
        # Sin Spira's Punishment
        test_sin_spira_etb_creates_token_copy_from_gy,
        test_sin_spira_no_permanents_in_gy_no_op,
        # Ignis Scientia
        test_ignis_scientia_etb_opens_top_6_choice_with_land,
        test_ignis_scientia_etb_no_land_no_choice,
        # Firion regression
        test_firion_etb_does_not_attributeerror_on_equipment,
        # Sandworm baseline
        test_sandworm_wired,
    ]

    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ERROR: {t.__name__}: {e}")

    total = len(tests)
    passed = total - len(failed)
    print(f"\n{'='*60}\nResults: {passed}/{total} tests passed")
    if failed:
        print("Failures:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    else:
        print("All FIN extra tests passed.")


if __name__ == "__main__":
    main()
