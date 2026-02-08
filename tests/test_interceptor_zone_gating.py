from __future__ import annotations

from src.cards import ALL_CARDS
from src.engine import Event, EventStatus, EventType, Game, ZoneType


def test_rest_in_peace_can_be_added_to_library() -> None:
    """
    Regression: some card setup_interceptors mistakenly treated a single Interceptor
    as an iterable (e.g. list(make_etb_trigger(...))) and crashed during deck load.
    """
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    rip = ALL_CARDS["Rest in Peace"]
    obj = game.add_card_to_library(p1.id, rip)

    assert obj.zone == ZoneType.LIBRARY
    assert obj.card_def is rip
    assert obj.interceptor_ids  # setup_interceptors should register something


def test_while_on_battlefield_interceptors_are_gated_by_source_zone() -> None:
    """
    Interceptors are registered when card objects are created (including in library),
    but most are intended to apply only while the source is on the battlefield.
    """
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    abolisher = ALL_CARDS["Grand Abolisher"]
    obj = game.add_card_to_library(p1.id, abolisher)

    # Simulate it being P1's turn.
    game.state.active_player = p1.id

    # Opponent casts a spell; should NOT be prevented while Abolisher is in library.
    e1 = Event(type=EventType.CAST, payload={}, controller=p2.id)
    processed1 = game.emit(e1)
    assert processed1[0].status != EventStatus.PREVENTED

    # Move Abolisher to the battlefield.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone": f"library_{p1.id}",
            "to_zone": "battlefield",
            "from_zone_type": ZoneType.LIBRARY,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        controller=p1.id,
    ))

    # Now the same opponent cast should be prevented.
    e2 = Event(type=EventType.CAST, payload={}, controller=p2.id)
    processed2 = game.emit(e2)
    assert processed2[0].status == EventStatus.PREVENTED

    # Move Abolisher off the battlefield; its interceptors should be cleaned up.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone": "battlefield",
            "to_zone": f"graveyard_{p1.id}",
            "from_zone_type": ZoneType.BATTLEFIELD,
            "to_zone_type": ZoneType.GRAVEYARD,
        },
        controller=p1.id,
    ))

    assert obj.interceptor_ids == []

    e3 = Event(type=EventType.CAST, payload={}, controller=p2.id)
    processed3 = game.emit(e3)
    assert processed3[0].status != EventStatus.PREVENTED

