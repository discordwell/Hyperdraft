"""Phase 9 tests:
- CATS_REVEAL event fires when Gary's commander watches a Sneaky resolve
- Mood-vs-Mood stacking: counter-pounce Mood wins the rule swap
"""

from __future__ import annotations

import pytest

from src.engine.cats import (
    _make_object_from_def,
    install_category_rule,
    make_cat_card,
    make_commander_card,
    make_mood_card,
    play_card_to_trick,
    resolve_trick,
    scrappy_rule,
    setup_cats_player,
    sleek_rule,
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
    state.rng_seed = 31
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    deck = [make_cat_card(name=f"C{i}", value=5, category="Sleek") for i in range(30)]
    setup_cats_player(state, "p1", list(deck))
    setup_cats_player(state, "p2", list(deck))
    return state


def test_gary_reveals_sneaky_value():
    """Gary's commander emits CATS_REVEAL when a Sneaky resolves; tracker is populated."""
    from src.cards.cats.CATS.commanders import GARY_THE_ONE_EYED_TABBY

    # Fresh state — Gary's setup needs to be the first setup_cats_player call
    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = 31
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    deck = [make_cat_card(name=f"C{i}", value=5, category="Sleek") for i in range(30)]
    setup_cats_player(state, "p1", list(deck), commander=GARY_THE_ONE_EYED_TABBY)
    setup_cats_player(state, "p2", list(deck))

    sneaky = make_cat_card(name="HiddenAce", value=2, category="Sneaky", sneaky_value=9)
    sleek = make_cat_card(name="OpenCat", value=5, category="Sleek")
    s_obj = _make_object_from_def(state, sneaky, "p2", ZoneType.HAND)
    s_obj.card_def.cats_sneaky_value = 9
    o_obj = _make_object_from_def(state, sleek, "p1", ZoneType.HAND)
    state.zones["HAND_p2"].objects.append(s_obj.id)
    state.zones["HAND_p1"].objects.append(o_obj.id)

    play_card_to_trick(state, "p2", s_obj.id, role="pounce")
    play_card_to_trick(state, "p1", o_obj.id, role="counter")
    events = resolve_trick(state)

    reveal_events = [e for e in events if e.type == EventType.CATS_REVEAL]
    assert reveal_events, "Gary should have emitted CATS_REVEAL"
    assert reveal_events[0].payload["sneaky_value"] == 9
    assert hasattr(state, "cats_sneaky_known")
    assert state.cats_sneaky_known.get("p1", {}).get(s_obj.id) == 9


def test_mood_vs_mood_counter_pounce_wins():
    """When both players play Moods, the Counter-pounce Mood's rule wins."""
    state = _state()
    hi = _make_object_from_def(state, make_cat_card(name="Hi", value=8, category="Sleek"), "p1", ZoneType.HAND)
    lo = _make_object_from_def(state, make_cat_card(name="Lo", value=2, category="Sleek"), "p2", ZoneType.HAND)
    state.zones["HAND_p1"].objects.append(hi.id)
    state.zones["HAND_p2"].objects.append(lo.id)

    def make_rule_interceptor(source_id, rule_fn, controller):
        def handler(event, state):
            if event.type != EventType.CATS_TRICK_RULE_QUERY:
                return InterceptorResult(action=InterceptorAction.PASS)
            new_event = Event(
                type=event.type,
                payload={**event.payload, "rule": rule_fn},
                source=event.source,
            )
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        return Interceptor(
            id=f"{source_id}_mood",
            source=source_id,
            controller=controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=lambda e, s: e.type == EventType.CATS_TRICK_RULE_QUERY,
            handler=handler,
        )

    play_card_to_trick(state, "p1", hi.id, role="pounce")
    play_card_to_trick(state, "p2", lo.id, role="counter")

    pounce_ic = make_rule_interceptor(hi.id, sleek_rule, "p1")
    counter_ic = make_rule_interceptor(lo.id, scrappy_rule, "p2")
    state.interceptors[pounce_ic.id] = pounce_ic
    state.interceptors[counter_ic.id] = counter_ic

    resolve_trick(state)
    assert state.cats_current_trick["winner"] == "p2", (
        f"Counter-pounce scrappy Mood should win; got {state.cats_current_trick['winner']}"
    )


def test_mood_pounce_only_still_works():
    """Pounce-side Mood with no counter-side Mood still installs its rule."""
    state = _state()
    hi = _make_object_from_def(state, make_cat_card(name="Hi", value=8, category="Sleek"), "p1", ZoneType.HAND)
    lo = _make_object_from_def(state, make_cat_card(name="Lo", value=2, category="Sleek"), "p2", ZoneType.HAND)
    state.zones["HAND_p1"].objects.append(hi.id)
    state.zones["HAND_p2"].objects.append(lo.id)

    def scrappy_handler(event, state):
        if event.type != EventType.CATS_TRICK_RULE_QUERY:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_event = Event(
            type=event.type,
            payload={**event.payload, "rule": scrappy_rule},
            source=event.source,
        )
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    play_card_to_trick(state, "p1", hi.id, role="pounce")
    play_card_to_trick(state, "p2", lo.id, role="counter")

    pounce_ic = Interceptor(
        id=f"{hi.id}_mood",
        source=hi.id,
        controller="p1",
        priority=InterceptorPriority.TRANSFORM,
        filter=lambda e, s: e.type == EventType.CATS_TRICK_RULE_QUERY,
        handler=scrappy_handler,
    )
    state.interceptors[pounce_ic.id] = pounce_ic

    resolve_trick(state)
    assert state.cats_current_trick["winner"] == "p2"
