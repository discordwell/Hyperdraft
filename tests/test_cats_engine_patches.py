"""Tests that prove the Phase-2 engine patches actually fire card interceptors.

These cover the 3 gaps the agent flagged:
1. CATS_QUERY_PILE_SCORE — Trinket score-mod interceptors must rewrite final scores.
2. CATS_TRICK_RULE_QUERY — Mood interceptors must replace the active rule.
3. setup_in_pile — cards entering piles must have setup_interceptors invoked.
"""

from __future__ import annotations

import pytest

from src.engine.cats import (
    _make_object_from_def,
    _run_setup_on_pile_entry,
    claim_pile,
    make_cat_card,
    make_mood_card,
    make_trinket_card,
    play_card_to_trick,
    resolve_trick,
    score_cats_player,
    sleek_rule,
    scrappy_rule,
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


def _empty_state():
    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = 7
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    state.players["p1"].life = 0
    state.players["p2"].life = 0
    deck = [make_cat_card(name=f"C{i}", value=5, category="Sleek") for i in range(30)]
    setup_cats_player(state, "p1", list(deck))
    setup_cats_player(state, "p2", list(deck))
    return state


def test_trinket_score_mod_rewrites_score():
    """A Trinket TRANSFORM on CATS_QUERY_PILE_SCORE should change the final score."""
    state = _empty_state()
    state.cats_piles["p1"]["pile_territory"] = ["c1", "c2", "c3"]
    base = score_cats_player(state, "p1")
    assert base["territory"] == 3

    def yarn_ball_handler(event, state):
        if event.payload.get("pile") != "pile_territory":
            return InterceptorResult(action=InterceptorAction.PASS)
        new_event = Event(
            type=event.type,
            payload={**event.payload, "score": event.payload["score"] + 10},
            source=event.source,
        )
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    ic = Interceptor(
        id="yarn_ball_trinket",
        source="yarn_ball",
        controller="p1",
        priority=InterceptorPriority.TRANSFORM,
        filter=lambda e, s: e.type == EventType.CATS_QUERY_PILE_SCORE,
        handler=yarn_ball_handler,
    )
    state.interceptors[ic.id] = ic

    scored = score_cats_player(state, "p1")
    assert scored["territory"] == 13, f"Trinket TRANSFORM did not apply: {scored}"
    assert scored["total"] >= 13


def test_mood_rule_replacement_changes_winner():
    """A Mood that swaps the rule to Scrappy should flip the winner."""
    state = _empty_state()
    hi_cat = make_cat_card(name="HiCat", value=8, category="Sleek")
    lo_cat = make_cat_card(name="LoCat", value=3, category="Sleek")
    hi = _make_object_from_def(state, hi_cat, "p1", ZoneType.HAND)
    lo = _make_object_from_def(state, lo_cat, "p2", ZoneType.HAND)
    state.zones[f"HAND_p1"].objects.append(hi.id)
    state.zones[f"HAND_p2"].objects.append(lo.id)

    play_card_to_trick(state, "p1", hi.id, role="pounce")
    play_card_to_trick(state, "p2", lo.id, role="counter")
    resolve_trick(state)
    assert state.cats_current_trick["winner"] == "p1", "Sleek default: high should win"

    state2 = _empty_state()
    hi2 = _make_object_from_def(state2, make_cat_card(name="HiCat", value=8, category="Sleek"), "p1", ZoneType.HAND)
    lo2 = _make_object_from_def(state2, make_cat_card(name="LoCat", value=3, category="Sleek"), "p2", ZoneType.HAND)
    state2.zones[f"HAND_p1"].objects.append(hi2.id)
    state2.zones[f"HAND_p2"].objects.append(lo2.id)

    def mood_handler(event, state):
        if event.type != EventType.CATS_TRICK_RULE_QUERY:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_event = Event(
            type=event.type,
            payload={**event.payload, "rule": scrappy_rule},
            source=event.source,
        )
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    ic = Interceptor(
        id="zoomies_mood",
        source="zoomies",
        controller="p1",
        priority=InterceptorPriority.TRANSFORM,
        filter=lambda e, s: e.type == EventType.CATS_TRICK_RULE_QUERY,
        handler=mood_handler,
    )
    state2.interceptors[ic.id] = ic

    play_card_to_trick(state2, "p1", hi2.id, role="pounce")
    play_card_to_trick(state2, "p2", lo2.id, role="counter")
    resolve_trick(state2)
    assert state2.cats_current_trick["winner"] == "p2", "Mood Scrappy override should flip the winner"


def test_on_win_trigger_actually_fires():
    """P0 fix: on_win REACT interceptors fire when their card wins a trick, and
    DRAW events from that REACT are actually applied to the player's hand."""
    state = _empty_state()
    hand_p1 = state.zones["HAND_p1"].objects
    hand_p2 = state.zones["HAND_p2"].objects
    p1_hand_size_before = len(hand_p1)

    def draw_on_win_setup(obj, state):
        def handler(event, state):
            if event.type != EventType.CATS_TRICK_RESOLVE:
                return InterceptorResult(action=InterceptorAction.PASS)
            if event.payload.get("phase") != "on_win":
                return InterceptorResult(action=InterceptorAction.PASS)
            if event.payload.get("card_id") != obj.id:
                return InterceptorResult(action=InterceptorAction.PASS)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "amount": 1},
                    source=obj.id,
                )],
            )

        return [Interceptor(
            id=f"{obj.id}_draw_on_win",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: e.type == EventType.CATS_TRICK_RESOLVE,
            handler=handler,
        )]

    winner_cat = make_cat_card(
        name="DrawCat", value=9, category="Sleek",
        setup_interceptors=draw_on_win_setup,
    )
    loser_cat = make_cat_card(name="LoseCat", value=2, category="Sleek")

    wc = _make_object_from_def(state, winner_cat, "p1", ZoneType.HAND)
    lc = _make_object_from_def(state, loser_cat, "p2", ZoneType.HAND)
    state.zones["HAND_p1"].objects.append(wc.id)
    state.zones["HAND_p2"].objects.append(lc.id)
    interceptors = draw_on_win_setup(wc, state)
    for ic in interceptors:
        state.interceptors[ic.id] = ic
        wc.interceptor_ids.append(ic.id)

    p1_hand_before_trick = len(state.zones["HAND_p1"].objects)

    play_card_to_trick(state, "p1", wc.id, role="pounce")
    play_card_to_trick(state, "p2", lc.id, role="counter")
    p1_hand_during_trick = len(state.zones["HAND_p1"].objects)
    events = resolve_trick(state)

    assert state.cats_current_trick["winner"] == "p1", "DrawCat should win on value"
    has_draw_event = any(
        ev.type == EventType.DRAW and ev.payload.get("player") == "p1"
        for ev in events
    )
    assert has_draw_event, "on_win REACT should have emitted a DRAW event"
    p1_hand_after = len(state.zones["HAND_p1"].objects)
    assert p1_hand_after > p1_hand_during_trick, (
        f"P1 hand should grow from draw effect; was {p1_hand_during_trick} now {p1_hand_after}"
    )


def test_setup_on_pile_entry_runs_interceptors():
    """When a card enters a pile via claim_pile, its setup_interceptors should fire."""
    state = _empty_state()

    triggered = {"count": 0}

    def my_setup(obj, state):
        triggered["count"] += 1

        def handler(event, state):
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=f"{obj.id}_pile_entry_marker",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: e.type == EventType.CATS_CLAIM_PILE,
            handler=handler,
        )]

    triggered_cat = make_cat_card(
        name="TriggerCat", value=5, category="Sleek",
        setup_interceptors=my_setup,
    )
    other_cat = make_cat_card(name="OtherCat", value=3, category="Sleek")

    tc = _make_object_from_def(state, triggered_cat, "p1", ZoneType.HAND)
    oc = _make_object_from_def(state, other_cat, "p2", ZoneType.HAND)
    state.zones[f"HAND_p1"].objects.append(tc.id)
    state.zones[f"HAND_p2"].objects.append(oc.id)

    play_card_to_trick(state, "p1", tc.id, role="pounce")
    play_card_to_trick(state, "p2", oc.id, role="counter")
    resolve_trick(state)
    claim_pile(state, state.cats_current_trick["winner"], "pile_territory")

    assert triggered["count"] >= 1, "setup_interceptors should have run when card entered pile"
    assert any(
        ic.id.endswith("_pile_entry_marker") for ic in state.interceptors.values()
    ), "interceptor from setup_in_pile not registered"
