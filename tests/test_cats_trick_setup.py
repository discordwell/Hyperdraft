"""Regression test: play_card_to_trick must invoke setup_interceptors.

Bug: cards played from HAND to the trick had no interceptors registered, so
all on_win / on_lose REACT triggers (Mister Whiskers, Duchess Velvet, Lord
Tufts, Pomf, Alley Phantom, Mayhem IV, Carnage, Whispertoes, Inkblot) were
silent no-ops in real games. Tests in test_cats_engine_patches.py masked this
by manually pre-registering interceptors before play_card_to_trick.

Fix: play_card_to_trick now calls _run_setup_on_pile_entry on the card after
it leaves the hand, registering on_win / on_lose triggers in time for
resolve_trick to dispatch them.

This test exercises the production code path with a real Cats card
(Duchess Velvet for on-win, Lord Tufts for on-lose) and one synthetic
on-win Cat — NO manual interceptor pre-registration anywhere.
"""

from __future__ import annotations

import pytest

from src.engine.cats import (
    _make_object_from_def,
    make_cat_card,
    play_card_to_trick,
    resolve_trick,
    setup_cats_player,
)
from src.cards.cats.CATS.sleek_cats import DUCHESS_VELVET, LORD_TUFTS
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


def _empty_state() -> GameState:
    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = 7
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    deck = [make_cat_card(name=f"C{i}", value=5, category="Sleek") for i in range(30)]
    setup_cats_player(state, "p1", list(deck))
    setup_cats_player(state, "p2", list(deck))
    return state


def _put_in_hand(state: GameState, card_def, owner: str):
    obj = _make_object_from_def(state, card_def, owner, ZoneType.HAND)
    state.zones[f"HAND_{owner}"].objects.append(obj.id)
    return obj


def test_play_card_to_trick_runs_setup_interceptors_on_win():
    """A synthetic Cat with an on_win REACT trigger must fire when its card
    wins the trick — without any manual pre-registration."""
    state = _empty_state()

    fired = {"count": 0}

    def on_win_setup(obj, state):
        def handler(event, state):
            if event.type != EventType.CATS_TRICK_RESOLVE:
                return InterceptorResult(action=InterceptorAction.PASS)
            if event.payload.get("phase") != "on_win":
                return InterceptorResult(action=InterceptorAction.PASS)
            if event.payload.get("card_id") != obj.id:
                return InterceptorResult(action=InterceptorAction.PASS)
            fired["count"] += 1
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "amount": 1},
                    source=obj.id,
                )],
            )

        return [Interceptor(
            id=f"{obj.id}_on_win_marker",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: e.type == EventType.CATS_TRICK_RESOLVE,
            handler=handler,
        )]

    winner = make_cat_card(
        name="OnWinCat", value=9, category="Sleek",
        setup_interceptors=on_win_setup,
    )
    loser = make_cat_card(name="QuietLoser", value=2, category="Sleek")

    wc = _put_in_hand(state, winner, "p1")
    lc = _put_in_hand(state, loser, "p2")

    # No manual interceptor registration here — production code path only.
    assert wc.interceptor_ids == [], "card in HAND should have no interceptors yet"

    play_card_to_trick(state, "p1", wc.id, role="pounce")
    play_card_to_trick(state, "p2", lc.id, role="counter")

    # After the trick play, the winner's setup_interceptors must have run.
    assert wc.interceptor_ids, (
        "play_card_to_trick must register setup_interceptors on the played card"
    )
    assert any(
        ic_id.endswith("_on_win_marker") for ic_id in wc.interceptor_ids
    ), "the on-win marker interceptor must be on the object's id list"

    events = resolve_trick(state)
    assert state.cats_current_trick["winner"] == "p1", (
        "Higher value (9 > 2) under Sleek default rule should win"
    )
    assert fired["count"] == 1, (
        f"on_win REACT should fire exactly once, fired {fired['count']} times"
    )
    has_draw = any(
        ev.type == EventType.DRAW and ev.payload.get("player") == "p1"
        for ev in events
    )
    assert has_draw, "on_win REACT must emit its DRAW event"


def test_play_card_to_trick_runs_setup_interceptors_on_lose():
    """A synthetic Cat with an on_lose REACT trigger must fire when its card
    loses the trick — without any manual pre-registration."""
    state = _empty_state()

    fired = {"count": 0}

    def on_lose_setup(obj, state):
        def handler(event, state):
            if event.type != EventType.CATS_TRICK_RESOLVE:
                return InterceptorResult(action=InterceptorAction.PASS)
            if event.payload.get("phase") != "on_lose":
                return InterceptorResult(action=InterceptorAction.PASS)
            if event.payload.get("card_id") != obj.id:
                return InterceptorResult(action=InterceptorAction.PASS)
            fired["count"] += 1
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=f"{obj.id}_on_lose_marker",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: e.type == EventType.CATS_TRICK_RESOLVE,
            handler=handler,
        )]

    consolation = make_cat_card(
        name="ConsolationCat", value=2, category="Sleek",
        setup_interceptors=on_lose_setup,
    )
    winner = make_cat_card(name="LoudWinner", value=9, category="Sleek")

    lc = _put_in_hand(state, consolation, "p1")
    wc = _put_in_hand(state, winner, "p2")

    play_card_to_trick(state, "p1", lc.id, role="pounce")
    play_card_to_trick(state, "p2", wc.id, role="counter")

    assert lc.interceptor_ids, (
        "play_card_to_trick must register setup_interceptors on the losing card too"
    )

    resolve_trick(state)
    assert state.cats_current_trick["winner"] == "p2", "Sleek default: high wins"
    assert fired["count"] == 1, (
        f"on_lose REACT should fire exactly once, fired {fired['count']} times"
    )


def test_real_duchess_velvet_draws_on_win():
    """Production card Duchess Velvet (real on_win => DRAW) must fire its draw
    event through the play_card_to_trick → resolve_trick path with no manual
    interceptor priming."""
    state = _empty_state()
    velvet = _put_in_hand(state, DUCHESS_VELVET, "p1")
    weakling = _put_in_hand(state, make_cat_card(name="Weakling", value=1, category="Sleek"), "p2")

    play_card_to_trick(state, "p1", velvet.id, role="pounce")
    play_card_to_trick(state, "p2", weakling.id, role="counter")
    events = resolve_trick(state)

    assert state.cats_current_trick["winner"] == "p1", "Velvet (6) > Weakling (1) wins"
    has_velvet_draw = any(
        ev.type == EventType.DRAW
        and ev.payload.get("player") == "p1"
        and ev.payload.get("reason") == "duchess_velvet"
        for ev in events
    )
    assert has_velvet_draw, (
        "Duchess Velvet's on_win DRAW must fire (this is the bug under test). "
        f"Events seen: {[(e.type.name, e.payload) for e in events]}"
    )


def test_real_lord_tufts_draws_on_lose():
    """Production card Lord Tufts (real on_lose => DRAW consolation) must fire
    its draw event through the play path with no manual priming."""
    state = _empty_state()
    tufts = _put_in_hand(state, LORD_TUFTS, "p1")
    heavy = _put_in_hand(state, make_cat_card(name="Heavy", value=9, category="Sleek"), "p2")

    play_card_to_trick(state, "p1", tufts.id, role="pounce")
    play_card_to_trick(state, "p2", heavy.id, role="counter")
    events = resolve_trick(state)

    assert state.cats_current_trick["winner"] == "p2", "Heavy (9) > Tufts (3) wins"
    has_tufts_draw = any(
        ev.type == EventType.DRAW
        and ev.payload.get("player") == "p1"
        and ev.payload.get("reason") == "lord_tufts_consolation"
        for ev in events
    )
    assert has_tufts_draw, (
        "Lord Tufts's on_lose DRAW must fire (this is the bug under test). "
        f"Events seen: {[(e.type.name, e.payload) for e in events]}"
    )


def test_no_duplicate_interceptors_when_card_moves_trick_to_pile():
    """After trick entry (registers interceptors) AND claim_pile (also calls
    _run_setup_on_pile_entry), the card must NOT have duplicate interceptors —
    idempotency guard required."""
    from src.engine.cats import claim_pile
    state = _empty_state()
    velvet = _put_in_hand(state, DUCHESS_VELVET, "p1")
    weakling = _put_in_hand(state, make_cat_card(name="Weakling", value=1, category="Sleek"), "p2")

    play_card_to_trick(state, "p1", velvet.id, role="pounce")
    play_card_to_trick(state, "p2", weakling.id, role="counter")
    interceptors_after_trick = list(velvet.interceptor_ids)
    resolve_trick(state)
    claim_pile(state, "p1", "pile_territory")

    # No new interceptors should have been added by the claim_pile path.
    assert velvet.interceptor_ids == interceptors_after_trick, (
        "claim_pile must not duplicate setup_interceptors registrations. "
        f"Was {interceptors_after_trick}, now {velvet.interceptor_ids}"
    )
