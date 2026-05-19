"""
Regression tests for axis-scorer helper registration.

Guards three concrete scorer/profile mismatches found during the custom-set
health pass (slice 7). Each fix lands as its own commit; this file accumulates
tests as fixes are added.

Fix 1: every helper referenced by `axis_scorer._score_decision_pressure`'s
       `targeted_names` and `deep_modal_names` sets must be registered in
       `engine_profiles._MTG_MODAL_HELPERS`. Surfaced by LTR slice-1 agent:
       `make_library_search_etb_trigger` lived in the scorer's targeted_names
       list but was missing from the profile registry, so tutor cards scored
       decision=0.

Fix 2: `EventType.LOOK_AT_HAND` is a real enum member. NRT and TLAC slice
       agents noted using `LOOK_AT_HAND` in docstrings for AST visibility, but
       had to emit `DISCARD_CHOICE` at runtime because `LOOK_AT_HAND` was
       only a string in `_MTG_INFORMATION_EVENTS`. Adding the real enum
       member lets cards emit the natural information event.

Run:
    PYTHONPATH=. python tests/test_axis_scorer_helpers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine import (  # noqa: E402
    Event, EventType, Color, GameObject, GameState, Interceptor, make_creature,
)
from src.cards import interceptor_helpers as ih  # noqa: E402
from src.depth import get_profile, score_card  # noqa: E402
from src.depth.engine_profiles import (  # noqa: E402
    _MTG_MODAL_HELPERS,
    _MTG_INFORMATION_EVENTS,
)


# ============================================================================
# Fix 1: every helper in axis_scorer's `targeted_names` ∪ `deep_modal_names`
# is registered in the MTG profile's `modal_helpers` set. Without this, the
# AST walker never tags the helper into FeatureBag.modal_calls and the
# decision-axis bucket detection misses the call entirely.
# ============================================================================


def test_every_modal_helper_in_axis_scorer_is_registered_in_profile():
    """All helpers mentioned in the axis_scorer's decision-pressure rules must
    be present in `_MTG_MODAL_HELPERS`. Surfaced by LTR slice-1 agent:
    `make_library_search_etb_trigger` lived in the scorer's targeted_names
    list but was absent from the profile registry."""
    # Re-derive the union from the scorer source — keeping these synced is the
    # whole point of the test.
    from src.depth import axis_scorer as scorer
    import ast
    import inspect

    src = inspect.getsource(scorer._score_decision_pressure)
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in {"deep_modal_names", "targeted_names"}:
                    if isinstance(node.value, ast.Set):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                names.add(elt.value)
    assert names, "Failed to extract any helper names from _score_decision_pressure source"
    missing = names - _MTG_MODAL_HELPERS
    assert not missing, (
        f"Helpers referenced by axis_scorer but missing from "
        f"_MTG_MODAL_HELPERS: {sorted(missing)}"
    )


# Module-level test cards for the decision axis -----------------------------
# (the AST walker needs source it can read, so they live at module scope)


def _tutor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tiny tutor: ETB → search library."""
    return [ih.make_library_search_etb_trigger(obj, max_count=1)]


_TUTOR_CARD = make_creature(
    name="Test Tutor",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    setup_interceptors=_tutor_setup,
)


def _multi_etb_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tiny card using `make_targeted_multi_effect_etb_trigger`."""
    return [ih.make_targeted_multi_effect_etb_trigger(
        obj,
        effects=[('damage', {'amount': 1})],
        target_filter='any',
        min_targets=1, max_targets=1,
    )]


_MULTI_ETB_CARD = make_creature(
    name="Test MultiEtb",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    setup_interceptors=_multi_etb_setup,
)


def test_library_search_etb_trigger_scores_decision_axis():
    """The canonical Fix-1 regression: a card calling
    `make_library_search_etb_trigger` must score decision >= 1."""
    mtg = get_profile("mtg")
    cs = score_card(_TUTOR_CARD, mtg)
    assert "make_library_search_etb_trigger" in cs.features.modal_calls, (
        f"Walker should tag make_library_search_etb_trigger; "
        f"got modal_calls={sorted(cs.features.modal_calls)}, "
        f"helpers={sorted(cs.features.helpers_called)}"
    )
    assert cs.scores.decision >= 1, (
        f"Tutor card should score decision >= 1; got D={cs.scores.decision}, "
        f"axes={cs.scores.fingerprint}"
    )


def test_multi_effect_etb_trigger_scores_decision_axis():
    """`make_targeted_multi_effect_etb_trigger` is the multi-effect variant
    used by some custom-set tutors; it must score decision >= 1."""
    mtg = get_profile("mtg")
    cs = score_card(_MULTI_ETB_CARD, mtg)
    assert "make_targeted_multi_effect_etb_trigger" in cs.features.modal_calls, (
        f"Walker should tag make_targeted_multi_effect_etb_trigger; "
        f"got modal_calls={sorted(cs.features.modal_calls)}"
    )
    assert cs.scores.decision >= 1


# ============================================================================
# Fix 2: EventType.LOOK_AT_HAND exists and is in _MTG_INFORMATION_EVENTS.
# Cards previously used DISCARD_CHOICE as a workaround because the enum
# member didn't exist at runtime even though it was named in the profile.
# ============================================================================


def test_look_at_hand_eventtype_exists():
    """`LOOK_AT_HAND` must be a real EventType member so cards can emit it
    naturally (information event for search/reveal effects)."""
    assert hasattr(EventType, "LOOK_AT_HAND"), (
        "EventType.LOOK_AT_HAND should exist — referenced by "
        "_MTG_INFORMATION_EVENTS and card docstrings"
    )


def test_look_at_hand_in_information_events():
    """The event name must remain in the information-events set so the
    asymmetry-axis scorer treats LOOK_AT_HAND emission as info asymmetry."""
    assert "LOOK_AT_HAND" in _MTG_INFORMATION_EVENTS


def _look_at_hand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tiny card that emits LOOK_AT_HAND on ETB — opponent reveals hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        opp = ih.all_opponents(obj, state)
        target = opp[0] if opp else obj.controller
        return [Event(
            type=EventType.LOOK_AT_HAND,
            payload={'player': target, 'looker': obj.controller},
            source=obj.id,
        )]
    return [ih.make_etb_trigger(obj, effect_fn)]


_LOOK_AT_HAND_CARD = make_creature(
    name="Test Mind-Walker",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    setup_interceptors=_look_at_hand_setup,
)


def test_look_at_hand_emission_scores_asymmetry():
    """A card emitting LOOK_AT_HAND must score asymmetry > 0 (information
    event signal). End-to-end: enum exists, AST walker tags the event,
    asymmetry scorer fires."""
    mtg = get_profile("mtg")
    cs = score_card(_LOOK_AT_HAND_CARD, mtg)
    assert "LOOK_AT_HAND" in cs.features.event_types, (
        f"Walker should pick up EventType.LOOK_AT_HAND; "
        f"got event_types={sorted(cs.features.event_types)}"
    )
    assert cs.scores.asymmetry > 0, (
        f"LOOK_AT_HAND should score asymmetry > 0; got A={cs.scores.asymmetry}, "
        f"axes={cs.scores.fingerprint}"
    )


def test_look_at_hand_runtime_emission_does_not_crash():
    """Critical: a card actually emitting EventType.LOOK_AT_HAND at runtime
    must not crash with AttributeError. Pre-fix, the docstring named the
    event but accessing `EventType.LOOK_AT_HAND` raised."""
    evt = Event(
        type=EventType.LOOK_AT_HAND,
        payload={'player': 'p1', 'looker': 'p2'},
        source='src',
    )
    assert evt.type is EventType.LOOK_AT_HAND


# ============================================================================
# Driver — running this file directly invokes every test.
# ============================================================================


if __name__ == "__main__":
    tests = [
        test_every_modal_helper_in_axis_scorer_is_registered_in_profile,
        test_library_search_etb_trigger_scores_decision_axis,
        test_multi_effect_etb_trigger_scores_decision_axis,
        test_look_at_hand_eventtype_exists,
        test_look_at_hand_in_information_events,
        test_look_at_hand_emission_scores_asymmetry,
        test_look_at_hand_runtime_emission_does_not_crash,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {e!r}")
            failed += 1
    print(f"\n{passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
