"""
Tests for the unified P/T-modifier event handler.

Motivation
----------
The engine previously had two separate handlers for temporary power/toughness
changes that differed only in payload keys:

- ``_handle_pt_modification`` — ``power_mod`` / ``toughness_mod`` / ``duration``
- ``_handle_pt_change``       — ``power`` / ``toughness`` / ``duration``

This split caused two latent bugs:
  1. ``EventType.GRANT_PT_MODIFIER`` was never registered in ``EVENT_HANDLERS``
     at all, so ~9 call sites silently no-oped.
  2. Several call sites use the key ``'until'`` rather than ``'duration'``.
     Neither handler read ``'until'``, so those durations were silently ignored.

After the refactor, all P/T-modifier event types route to the single unified
``_handle_pt_modification`` handler, which accepts both payload shapes and
normalizes ``'until'`` to ``'duration'``. These tests lock that behavior in.

They follow the plain-function style of ``tests/test_hearthstone.py`` — no
pytest fixtures — so they can be run directly with
``python tests/test_pt_handler_normalization.py``.
"""

import os
import sys

# Allow running this file directly with ``python tests/test_pt_handler_normalization.py``
# without needing PYTHONPATH to be set, matching the style of other tests.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine.game import Game
from src.engine.types import Event, EventType, ZoneType


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

# Every EventType that is supposed to route through the unified handler.
_PT_EVENT_TYPES = [
    EventType.PT_MODIFICATION,
    EventType.PT_MODIFIER,
    EventType.PT_CHANGE,
    EventType.PT_MODIFY,
    EventType.TEMPORARY_PT_CHANGE,
    EventType.PUMP,
    EventType.TEMPORARY_BOOST,
    EventType.GRANT_PT_MODIFIER,
]


def _make_game_with_creature():
    """Spin up a tiny MTG-mode game with a single creature on the battlefield."""
    game = Game(mode="mtg")
    player = game.add_player("Player 1")
    creature = game.create_object(
        name="Test Creature",
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
    )
    creature.characteristics.power = 2
    creature.characteristics.toughness = 2
    # Make sure we start from a clean slate.
    creature.state.pt_modifiers = []
    return game, player, creature


def _emit_pt(game, event_type, obj_id, *, payload):
    """Emit an event of the given type and return pt_modifiers after."""
    game.emit(Event(type=event_type, payload={"object_id": obj_id, **payload}))


def _only_modifier(obj):
    mods = getattr(obj.state, "pt_modifiers", [])
    assert len(mods) == 1, f"expected exactly 1 pt_modifier, got {len(mods)}: {mods}"
    return mods[0]


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


def test_all_pt_event_types_are_registered():
    """Every P/T-modifier event type must have a handler registered.

    Previously ``GRANT_PT_MODIFIER`` had no handler and was silently dropped.
    """
    from src.engine.pipeline import EVENT_HANDLERS

    for et in _PT_EVENT_TYPES:
        assert et in EVENT_HANDLERS, f"{et.name} is missing from EVENT_HANDLERS"


def test_canonical_payload_shape_power_mod_toughness_mod():
    """PT_MODIFICATION / PT_MODIFIER still accept the canonical shape."""
    for et in (EventType.PT_MODIFICATION, EventType.PT_MODIFIER):
        game, _, creature = _make_game_with_creature()
        _emit_pt(
            game, et, creature.id,
            payload={"power_mod": 2, "toughness_mod": 3, "duration": "end_of_turn"},
        )
        mod = _only_modifier(creature)
        assert mod["power"] == 2
        assert mod["toughness"] == 3
        assert mod["duration"] == "end_of_turn"


def test_legacy_payload_shape_power_toughness():
    """PT_CHANGE / PT_MODIFY / TEMPORARY_PT_CHANGE / PUMP / TEMPORARY_BOOST
    accept the legacy shape."""
    legacy_types = [
        EventType.PT_CHANGE,
        EventType.PT_MODIFY,
        EventType.TEMPORARY_PT_CHANGE,
        EventType.PUMP,
        EventType.TEMPORARY_BOOST,
    ]
    for et in legacy_types:
        game, _, creature = _make_game_with_creature()
        _emit_pt(
            game, et, creature.id,
            payload={"power": 1, "toughness": 1, "duration": "end_of_turn"},
        )
        mod = _only_modifier(creature)
        assert mod["power"] == 1, f"{et.name} dropped power delta"
        assert mod["toughness"] == 1, f"{et.name} dropped toughness delta"
        assert mod["duration"] == "end_of_turn"


def test_grant_pt_modifier_now_takes_effect():
    """Regression: GRANT_PT_MODIFIER used to be a silent no-op because it
    wasn't registered in EVENT_HANDLERS. It should now apply a modifier using
    the legacy ``power`` / ``toughness`` keys."""
    game, _, creature = _make_game_with_creature()
    _emit_pt(
        game, EventType.GRANT_PT_MODIFIER, creature.id,
        payload={"power": 1, "toughness": 0, "duration": "end_of_turn"},
    )
    mod = _only_modifier(creature)
    assert mod["power"] == 1
    assert mod["toughness"] == 0
    assert mod["duration"] == "end_of_turn"


def test_until_key_is_honored():
    """Regression: payloads that used ``'until'`` instead of ``'duration'``
    used to have their duration silently ignored. Now both spellings are
    accepted and equivalent."""
    # Legacy-shape event with the legacy ``until`` key.
    game, _, creature = _make_game_with_creature()
    _emit_pt(
        game, EventType.PUMP, creature.id,
        payload={"power": 2, "toughness": 2, "until": "end_of_turn"},
    )
    mod = _only_modifier(creature)
    assert mod["duration"] == "end_of_turn", (
        f"'until' key was ignored — got duration={mod['duration']!r}"
    )
    assert mod["power"] == 2
    assert mod["toughness"] == 2


def test_until_key_with_canonical_payload_shape():
    """Duskmourn uses canonical ``power_mod``/``toughness_mod`` with ``until``
    rather than ``duration``. That combination must also be normalized."""
    game, _, creature = _make_game_with_creature()
    _emit_pt(
        game, EventType.PT_MODIFICATION, creature.id,
        payload={"power_mod": -2, "toughness_mod": 0, "until": "next_turn"},
    )
    mod = _only_modifier(creature)
    assert mod["power"] == -2
    assert mod["toughness"] == 0
    # 'next_turn' is not in the eot-alias set, so it passes through verbatim.
    assert mod["duration"] == "next_turn"


def test_until_end_of_turn_alias_is_normalized():
    """String forms like ``'until_end_of_turn'`` / ``'eot'`` should be
    normalized to ``'end_of_turn'`` regardless of which key carried them."""
    for key in ("duration", "until"):
        for raw in ("until_end_of_turn", "until end of turn", "eot", "EOT"):
            game, _, creature = _make_game_with_creature()
            _emit_pt(
                game, EventType.PT_CHANGE, creature.id,
                payload={"power": 1, "toughness": 1, key: raw},
            )
            mod = _only_modifier(creature)
            assert mod["duration"] == "end_of_turn", (
                f"raw={raw!r} via key={key!r} -> {mod['duration']!r}"
            )


def test_unknown_object_id_is_a_no_op():
    """Events targeting a nonexistent object must be ignored silently."""
    game, _, creature = _make_game_with_creature()
    _emit_pt(
        game, EventType.PT_MODIFICATION, "does-not-exist",
        payload={"power_mod": 99, "toughness_mod": 99, "duration": "end_of_turn"},
    )
    assert creature.state.pt_modifiers == []


# -----------------------------------------------------------------------------
# Script entry point (mirrors tests/test_hearthstone.py style)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("all PT event types registered", test_all_pt_event_types_are_registered),
        ("canonical payload (power_mod/toughness_mod)", test_canonical_payload_shape_power_mod_toughness_mod),
        ("legacy payload (power/toughness)", test_legacy_payload_shape_power_toughness),
        ("GRANT_PT_MODIFIER applies", test_grant_pt_modifier_now_takes_effect),
        ("'until' key honored (legacy shape)", test_until_key_is_honored),
        ("'until' key honored (canonical shape)", test_until_key_with_canonical_payload_shape),
        ("eot alias normalization", test_until_end_of_turn_alias_is_normalized),
        ("unknown object_id is no-op", test_unknown_object_id_is_a_no_op),
    ]

    print("Running PT handler normalization tests...")
    failed = 0
    for label, fn in tests:
        try:
            fn()
            print(f"  PASS  {label}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {label}: {type(e).__name__}: {e}")

    if failed:
        raise SystemExit(f"{failed} test(s) failed")
    print(f"\nAll {len(tests)} tests passed.")
