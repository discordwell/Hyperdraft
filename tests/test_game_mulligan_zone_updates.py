from __future__ import annotations

from src.engine import CardType, Characteristics, Game, ZoneType


def test_shuffle_hand_into_library_updates_object_zones() -> None:
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    a = game.create_object("Card A", owner_id=p1.id, zone=ZoneType.HAND)
    b = game.create_object("Card B", owner_id=p1.id, zone=ZoneType.HAND)

    assert a.zone == ZoneType.HAND
    assert b.zone == ZoneType.HAND

    game._shuffle_hand_into_library(p1.id)

    hand = game.state.zones[f"hand_{p1.id}"].objects
    library = game.state.zones[f"library_{p1.id}"].objects

    assert a.id not in hand
    assert b.id not in hand
    assert a.id in library
    assert b.id in library
    assert game.state.objects[a.id].zone == ZoneType.LIBRARY
    assert game.state.objects[b.id].zone == ZoneType.LIBRARY


def test_put_cards_on_bottom_moves_to_library_bottom_and_updates_zone() -> None:
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    # Pre-seed library with 2 cards so we can verify "bottom" insertion.
    lib1 = game.create_object("Lib 1", owner_id=p1.id, zone=ZoneType.LIBRARY)
    lib2 = game.create_object("Lib 2", owner_id=p1.id, zone=ZoneType.LIBRARY)

    # Put 2 lands in hand.
    land1 = game.create_object(
        "Land 1",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.LAND}),
    )
    land2 = game.create_object(
        "Land 2",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.LAND}),
    )

    game._put_cards_on_bottom(p1.id, 1)

    hand = game.state.zones[f"hand_{p1.id}"].objects
    library = game.state.zones[f"library_{p1.id}"].objects

    moved = {land1.id, land2.id} - set(hand)
    assert len(moved) == 1
    moved_id = next(iter(moved))

    # The moved card should be at the bottom (end) of the library list.
    assert library[:2] == [lib1.id, lib2.id]
    assert library[-1] == moved_id
    assert game.state.objects[moved_id].zone == ZoneType.LIBRARY

