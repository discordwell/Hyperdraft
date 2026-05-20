"""Tests for the P1 punchlist items implemented in Phase 6:
- make_pile_activated + activate_pile_card (knock-over abilities)
- attach_trinket (Trinket play-to-pile mechanic)
- _untap_all_piles at round start
"""

from __future__ import annotations

import pytest

from src.engine.cats import (
    _empty_trick,
    _make_object_from_def,
    activate_pile_card,
    attach_trinket,
    begin_round,
    make_cat_card,
    make_pile_activated,
    make_trinket_card,
    score_cats_player,
    setup_cats_player,
)
from src.engine.types import (
    Event,
    EventType,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
    ZoneType,
)


def _state():
    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = 11
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    deck = [make_cat_card(name=f"C{i}", value=5, category="Sleek") for i in range(30)]
    setup_cats_player(state, "p1", list(deck))
    setup_cats_player(state, "p2", list(deck))
    return state


def test_pile_activated_ability_fires_on_knock_over():
    """activate_pile_card taps a card and triggers its registered effect."""
    state = _state()

    fired = {"count": 0, "payload": None}

    def my_effect(event, state):
        fired["count"] += 1
        fired["payload"] = event.payload
        return [Event(
            type=EventType.DRAW,
            payload={"player": event.payload["player"], "amount": 1},
            source=event.source,
        )]

    def setup(obj, state):
        return [make_pile_activated(obj, "pile_territory", my_effect)]

    cat = make_cat_card(name="ActivatorCat", value=5, category="Sleek", setup_interceptors=setup)
    obj = _make_object_from_def(state, cat, "p1", ZoneType.HAND)
    # Pretend it entered Territory pile
    state.cats_piles["p1"]["pile_territory"].append(obj.id)
    obj.zone = ZoneType.CATS_PILE_TERRITORY
    obj.state.tapped = False
    interceptors = setup(obj, state)
    for ic in interceptors:
        state.interceptors[ic.id] = ic
        obj.interceptor_ids.append(ic.id)

    p1_hand_before = len(state.zones["HAND_p1"].objects)
    events = activate_pile_card(state, "p1", obj.id)
    assert obj.state.tapped, "card should be tapped after activation"
    assert fired["count"] == 1, "effect should have fired exactly once"
    assert fired["payload"]["pile"] == "pile_territory"
    p1_hand_after = len(state.zones["HAND_p1"].objects)
    assert p1_hand_after > p1_hand_before, "DRAW event should have drawn a card"


def test_cannot_activate_tapped_card():
    """Once tapped, the card can't be activated again until untap."""
    state = _state()
    fired = {"count": 0}

    def my_effect(event, state):
        fired["count"] += 1
        return []

    def setup(obj, state):
        return [make_pile_activated(obj, "pile_nap", my_effect)]

    cat = make_cat_card(name="OneShot", value=5, category="Fluffy", setup_interceptors=setup)
    obj = _make_object_from_def(state, cat, "p1", ZoneType.HAND)
    state.cats_piles["p1"]["pile_nap"].append(obj.id)
    obj.zone = ZoneType.CATS_PILE_NAP
    interceptors = setup(obj, state)
    for ic in interceptors:
        state.interceptors[ic.id] = ic

    activate_pile_card(state, "p1", obj.id)
    activate_pile_card(state, "p1", obj.id)
    assert fired["count"] == 1, "tapped card should not re-activate"

    # Now untap by running begin_round
    state.cats_round_number = 2
    begin_round(state)
    assert not obj.state.tapped, "round start should have untapped"
    activate_pile_card(state, "p1", obj.id)
    assert fired["count"] == 2, "after untap, should activate again"


def test_attach_trinket_to_territory_and_score_rewrites():
    """attach_trinket places a Trinket on a pile and its score-mod fires."""
    state = _state()

    def yarn_setup(obj, state):
        def handler(event, state):
            if event.payload.get("pile") != "pile_territory":
                return InterceptorResult(action=InterceptorAction.PASS)
            new_event = Event(
                type=event.type,
                payload={**event.payload, "score": event.payload["score"] + 7},
                source=event.source,
            )
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        return [Interceptor(
            id=f"{obj.id}_yarn_score_mod",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=lambda e, s: e.type == EventType.CATS_QUERY_PILE_SCORE,
            handler=handler,
        )]

    yarn = make_trinket_card(name="YarnBall", attaches_to="pile_territory", setup_interceptors=yarn_setup)
    yarn_obj = _make_object_from_def(state, yarn, "p1", ZoneType.HAND)
    state.zones["HAND_p1"].objects.append(yarn_obj.id)

    state.cats_piles["p1"]["pile_territory"] = ["c1", "c2"]
    base = score_cats_player(state, "p1")
    assert base["territory"] == 2

    events = attach_trinket(state, "p1", yarn_obj.id, "pile_territory")
    assert events, "attach should emit at least one event"
    assert yarn_obj.id in state.cats_pile_trinkets["p1"]["pile_territory"]
    assert yarn_obj.id not in state.zones["HAND_p1"].objects

    new = score_cats_player(state, "p1")
    # Score breakdown: 2 cards + 2 (trinket-attached bonus) + 7 (TRANSFORM) = 11
    assert new["territory"] == 11, f"Trinket should bump territory: {new}"


def test_trinket_pile_cap_enforced():
    """A pile can hold at most 2 Trinkets; the 3rd attach should fail."""
    state = _state()
    for i in range(3):
        t = make_trinket_card(name=f"T{i}", attaches_to="pile_nap")
        obj = _make_object_from_def(state, t, "p1", ZoneType.HAND)
        state.zones["HAND_p1"].objects.append(obj.id)
        result = attach_trinket(state, "p1", obj.id, "pile_nap")
        if i < 2:
            assert result, f"attach {i} should succeed"
            assert obj.id in state.cats_pile_trinkets["p1"]["pile_nap"]
        else:
            assert not result, "3rd attach should fail (cap=2)"
            assert obj.id not in state.cats_pile_trinkets["p1"]["pile_nap"]
            assert obj.id in state.zones["HAND_p1"].objects, "card should still be in hand"


def test_attach_rejects_non_trinket():
    """attach_trinket should refuse a non-Trinket card."""
    state = _state()
    cat = make_cat_card(name="NotATrinket", value=5, category="Sleek")
    cat_obj = _make_object_from_def(state, cat, "p1", ZoneType.HAND)
    state.zones["HAND_p1"].objects.append(cat_obj.id)
    result = attach_trinket(state, "p1", cat_obj.id, "pile_territory")
    assert not result, "should refuse non-Trinket"
