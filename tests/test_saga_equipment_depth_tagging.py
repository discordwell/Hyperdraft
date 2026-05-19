"""
Saga + Equipment depth-tagging sweep — Slice 7B.

The depth scorer walks each card's `setup_interceptors` callable to fingerprint
its mechanical depth. For Sagas built via `make_saga_setup(...)` and Equipment
built via `make_equipment_setup(..., granted_*_abilities=...)`, the
*chapter handlers* and *granted-ability effect functions* are passed as
values (dict values, list elements, kwargs) — not called directly inside the
setup body. Before this slice they were invisible to the AST walker.

These tests pin the new behaviour: when the walker hits a known
function-accepting helper, it follows function references inside the call's
arguments (dict values, list values, nested kwargs) and descends into them
the same way it descends into module-level helper calls. The result is that
sagas and granted-ability Equipment now surface their per-card mechanics
(event types, state/zone reads, cross-controller iteration) on the scorer.

Run:
    python -m pytest tests/test_saga_equipment_depth_tagging.py -q
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.depth import get_profile, score_card


# =============================================================================
# Saga sweep — chapter handlers must contribute to the bag.
# =============================================================================


def _mtg():
    return get_profile("mtg")


def test_saga_legacy_dict_api_picks_up_chapter_handler_events():
    """Legacy `make_saga_setup(obj, {1: ch_i, 2: ch_ii, ...})` calling
    convention. The chapter handlers are passed as dict values; the walker
    must follow them and surface the events they emit."""
    from src.cards.custom.lord_of_the_rings import THE_COUNCIL_OF_ELROND
    cs = score_card(THE_COUNCIL_OF_ELROND, _mtg())
    # Chapter I tutors a legendary (emits a search/draw flow); II creates a
    # token; III modifies P/T + grants flying. The walker should now see at
    # least one of: GRANT_KEYWORD / PT_MODIFICATION / CREATE_TOKEN /
    # LIBRARY_SEARCH / DRAW.
    assert cs.features.event_types, (
        f"Expected saga {cs.name!r} to surface chapter-handler events; got "
        f"event_types={cs.features.event_types}"
    )


def test_saga_declarative_api_picks_up_chapter_handler_events():
    """New `make_saga_setup(obj, chapters=[SagaChapter(label='I', effect_fn=...)])`
    API. Chapter handlers passed as `effect_fn=` kwargs in SagaChapter dataclass
    instances. The walker must follow these too."""
    from src.cards.custom.lord_of_the_rings import THE_MOUNT_DOOM_JOURNEY
    cs = score_card(THE_MOUNT_DOOM_JOURNEY, _mtg())
    assert "LIFE_CHANGE" in cs.features.event_types
    assert "DISCARD" in cs.features.event_types or "SACRIFICE_REQUIRED" in cs.features.event_types


def test_saga_chapter_handlers_surface_cross_controller():
    """Sagas whose chapter handlers iterate `for pid in state.players` should
    surface as cross-controller / opponent_iteration on the scorer's bag.

    Mount Doom Journey chapters all loop state.players and skip the
    controller. The walker should detect the state.players iteration."""
    from src.cards.custom.lord_of_the_rings import THE_MOUNT_DOOM_JOURNEY
    cs = score_card(THE_MOUNT_DOOM_JOURNEY, _mtg())
    # state.players read (via "players" attr access) or via for-loop
    # iteration on state.players (opponent_iteration True).
    surfaced = (
        "players" in cs.features.state_attrs
        or cs.features.opponent_iteration
    )
    assert surfaced, (
        f"Expected cross-controller signal from chapter handlers iterating "
        f"state.players; got state_attrs={cs.features.state_attrs} "
        f"opponent_iteration={cs.features.opponent_iteration}"
    )


def test_saga_chapter_handlers_surface_zone_reads():
    """Sagas whose chapter handlers read graveyards / battlefields surface
    those zones on the bag. Mount Doom III reads `graveyard_{pid}`."""
    from src.cards.custom.lord_of_the_rings import THE_MOUNT_DOOM_JOURNEY
    cs = score_card(THE_MOUNT_DOOM_JOURNEY, _mtg())
    assert "graveyard" in cs.features.zones_accessed


def test_saga_chapter_handlers_diversify_fingerprints():
    """Before slice 7B, every legacy-API saga collapsed to one
    `code_fingerprint`. After the chapter-handler descent, two sagas with
    different chapter event mixes must produce different fingerprints."""
    from src.cards.custom.lord_of_the_rings import (
        THE_COUNCIL_OF_ELROND, THE_MOUNT_DOOM_JOURNEY,
    )
    fp1 = score_card(THE_COUNCIL_OF_ELROND, _mtg()).code_fingerprint
    fp2 = score_card(THE_MOUNT_DOOM_JOURNEY, _mtg()).code_fingerprint
    assert fp1 != fp2, (
        f"Different sagas should fingerprint differently after chapter-"
        f"handler descent. Council={fp1} Mount Doom={fp2}"
    )


def test_sagas_across_sets_produce_diverse_fingerprints():
    """Sanity: the catalog-wide saga pool must produce more than two
    fingerprints after the tagging sweep. Before, every legacy-API saga
    fingerprinted the same."""
    from src.cards.custom.lord_of_the_rings import THE_COUNCIL_OF_ELROND
    from src.cards.custom.studio_ghibli import (
        THE_SPIRIT_REALM_SUMMONING, PRINCESS_MONONOKES_CURSE,
    )
    from src.cards.custom.attack_on_titan import BATTLE_OF_TROST
    from src.cards.custom.star_wars import THE_FORCE_ITSELF

    fps = set()
    for card in [
        THE_COUNCIL_OF_ELROND,
        THE_SPIRIT_REALM_SUMMONING,
        PRINCESS_MONONOKES_CURSE,
        BATTLE_OF_TROST,
        THE_FORCE_ITSELF,
    ]:
        fps.add(score_card(card, _mtg()).code_fingerprint)
    assert len(fps) >= 3, (
        f"Expected catalog of 5 diverse sagas to produce >=3 fingerprints; "
        f"got {len(fps)}: {fps}"
    )


# =============================================================================
# Equipment sweep — granted-ability effect_fn must contribute to the bag.
# =============================================================================


def test_equipment_granted_activated_ability_picks_up_per_card_effect():
    """`make_equipment_setup(granted_activated_abilities=[{'effect_fn': fn}])`
    — the per-card `effect_fn` lives outside the closure walk, but the
    function-arg descent must find it."""
    from src.cards.custom.attack_on_titan import ERENS_HARDENING
    cs = score_card(ERENS_HARDENING, _mtg())
    # ERENS_HARDENING's effect_fn emits GRANT_KEYWORD (indestructible until EOT).
    assert "GRANT_KEYWORD" in cs.features.event_types


def test_equipment_granted_triggered_ability_picks_up_filter_and_effect():
    """`make_equipment_setup(granted_triggered_abilities={'event_filter':...,
    'effect_fn':...})` — both the filter and the effect must surface."""
    from src.cards.custom.star_wars import SLAVE_TRACKER
    cs = score_card(SLAVE_TRACKER, _mtg())
    # SLAVE_TRACKER's effect_fn emits ACTIVATE (scry).
    assert "ACTIVATE" in cs.features.event_types
    # Its filter inspects DAMAGE events.
    assert "DAMAGE" in cs.features.event_types


def test_equipment_card_diversity_after_descent():
    """Before slice 7B, every Equipment with `granted_*` collapsed to
    fingerprint ababd2c75e63 because the closure walk only saw the shared
    listener machinery. After per-card effect_fn descent, different
    Equipment must produce different fingerprints."""
    from src.cards.custom.star_wars import SLAVE_TRACKER
    from src.cards.custom.attack_on_titan import ERENS_HARDENING
    fp1 = score_card(SLAVE_TRACKER, _mtg()).code_fingerprint
    fp2 = score_card(ERENS_HARDENING, _mtg()).code_fingerprint
    assert fp1 != fp2, (
        f"Equipment with distinct granted effects should fingerprint "
        f"differently; got both = {fp1}"
    )


# =============================================================================
# Engine-profile registry — confirm function-accepting helper allowlist exists.
# =============================================================================


def test_mtg_profile_lists_saga_helpers():
    """The function-arg descent reads `function_accepting_helpers` off the
    engine profile. MTG profile must list `make_saga_setup`, `SagaChapter`,
    `make_equipment_setup`, `make_aura_setup`."""
    prof = _mtg()
    fah = getattr(prof, "function_accepting_helpers", None)
    assert fah is not None, "MTG profile must expose function_accepting_helpers"
    assert "make_saga_setup" in fah
    assert "SagaChapter" in fah
    assert "make_equipment_setup" in fah
    assert "make_aura_setup" in fah
