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

Fix 3: `ability_bundles` helpers (`etb_gain_life`, `etb_deal_damage`, ...) are
       no longer opaque to the v2 scorer. The AST walker can't descend into
       imported helper modules, so we declare each bundle's feature
       contribution upfront in `EngineProfile.bundle_features`. The walker
       injects those features whenever it sees a call to a known bundle.

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
from src.cards import ability_bundles as ab  # noqa: E402
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
# Fix 3: `ability_bundles` helpers contribute features to the scorer via the
# profile's `bundle_features` map. A card built purely from a bundle helper
# must score on the relevant axis (state for LIFE_CHANGE / DRAW; asymmetry
# for cross_controller damage; etc).
# ============================================================================


def _ab_gain_life_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Bundle-only setup: gain 3 life on ETB."""
    itc, _txt = ab.etb_gain_life(obj, 3)
    return [itc]


_AB_GAIN_LIFE_CARD = make_creature(
    name="Test Healer",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    setup_interceptors=_ab_gain_life_setup,
)


def _ab_deal_damage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Bundle-only setup: deal 2 damage to each opponent on ETB."""
    itc, _txt = ab.etb_deal_damage(obj, 2, target='each_opponent')
    return [itc]


_AB_DEAL_DAMAGE_CARD = make_creature(
    name="Test Shocker",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    setup_interceptors=_ab_deal_damage_setup,
)


def _ab_draw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Bundle-only setup: draw a card on ETB."""
    itc, _txt = ab.etb_draw(obj, 1)
    return [itc]


_AB_DRAW_CARD = make_creature(
    name="Test Scribe",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    setup_interceptors=_ab_draw_setup,
)


def test_etb_gain_life_bundle_scores_state_axis():
    """`etb_gain_life` injects LIFE_CHANGE + `life` state_attr; the state
    axis must fire (resource_attr match)."""
    mtg = get_profile("mtg")
    cs = score_card(_AB_GAIN_LIFE_CARD, mtg)
    assert "LIFE_CHANGE" in cs.features.event_types, (
        f"Bundle injection should surface LIFE_CHANGE from etb_gain_life; "
        f"got event_types={sorted(cs.features.event_types)}, "
        f"helpers={sorted(cs.features.helpers_called)}"
    )
    assert "life" in cs.features.state_attrs, (
        f"Bundle injection should surface `life` state_attr; "
        f"got state_attrs={sorted(cs.features.state_attrs)}"
    )
    assert cs.scores.state > 0, (
        f"etb_gain_life should score state > 0; got S={cs.scores.state}, "
        f"axes={cs.scores.fingerprint}"
    )


def test_etb_deal_damage_bundle_scores_state_and_asymmetry():
    """`etb_deal_damage(each_opponent)` injects DAMAGE + `life` + cross_controller.
    Both state and asymmetry axes should fire."""
    mtg = get_profile("mtg")
    cs = score_card(_AB_DEAL_DAMAGE_CARD, mtg)
    assert "DAMAGE" in cs.features.event_types, (
        f"Bundle should surface DAMAGE; "
        f"got event_types={sorted(cs.features.event_types)}"
    )
    assert cs.features.cross_controller, (
        "Bundle should flag cross_controller=True"
    )
    # State axis fires because `life` is in resource_attrs and cross_controller
    # is True (per _score_state_coupling: cross && kinds>=2 || len>=3 → 3,
    # else cross → 2). Asymmetry axis fires because cross && DAMAGE
    # (asymmetric_event_types) → 2.
    assert cs.scores.state > 0, (
        f"etb_deal_damage should score state > 0; got axes={cs.scores.fingerprint}"
    )
    assert cs.scores.asymmetry > 0, (
        f"etb_deal_damage should score asymmetry > 0; got axes={cs.scores.fingerprint}"
    )


def test_etb_draw_bundle_scores_state_axis():
    """`etb_draw` injects DRAW + library + hand zone access; state axis
    fires from zone touches."""
    mtg = get_profile("mtg")
    cs = score_card(_AB_DRAW_CARD, mtg)
    assert "DRAW" in cs.features.event_types, (
        f"Bundle should surface DRAW; "
        f"got event_types={sorted(cs.features.event_types)}"
    )
    assert {"library", "hand"} <= cs.features.zones_accessed, (
        f"Bundle should surface library + hand zones; "
        f"got zones_accessed={sorted(cs.features.zones_accessed)}"
    )
    assert cs.scores.state > 0, (
        f"etb_draw should score state > 0; got S={cs.scores.state}, "
        f"axes={cs.scores.fingerprint}"
    )


def test_bundle_features_registered_for_known_helpers():
    """Sanity check: the MTG profile's `bundle_features` map covers every
    bundle helper exported from `ability_bundles.py` that has an obvious
    runtime effect. If a new bundle is added without a profile entry, this
    test makes it easy to spot."""
    mtg = get_profile("mtg")
    # The bundles below all emit events / read state; if you add a new one,
    # add a `bundle_features` entry or extend this assertion.
    expected_bundles = {
        "etb_gain_life", "etb_lose_life", "etb_draw", "etb_create_token",
        "etb_deal_damage",
        "death_drain", "death_draw",
        "attack_deal_damage", "attack_add_counters",
        "static_pt_boost_all_you_control", "static_pt_boost_other_you_control",
        "static_pt_boost_by_subtype",
        "static_keyword_grant_others",
        "upkeep_gain_life", "spell_cast_draw",
    }
    missing = expected_bundles - set(mtg.bundle_features)
    assert not missing, f"MTG profile missing bundle_features for: {sorted(missing)}"


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
        test_etb_gain_life_bundle_scores_state_axis,
        test_etb_deal_damage_bundle_scores_state_and_asymmetry,
        test_etb_draw_bundle_scores_state_axis,
        test_bundle_features_registered_for_known_helpers,
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
