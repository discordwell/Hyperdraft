from __future__ import annotations

from src.engine import Game, Event, EventType, ZoneType


def test_zone_change_supports_type_and_owner_payload() -> None:
    """
    Some card implementations emit ZONE_CHANGE with {from_zone_type, to_zone_type, to_zone_owner}
    (no from_zone/to_zone strings). The engine should normalize that into real zone keys.
    """
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    obj = game.create_object("Test Permanent", owner_id=p1.id, zone=ZoneType.BATTLEFIELD)

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone_type": ZoneType.BATTLEFIELD,
            "to_zone_type": ZoneType.HAND,
            "to_zone_owner": p1.id,
        },
        controller=p1.id,
    ))

    assert obj.zone == ZoneType.HAND
    assert obj.id in game.state.zones[f"hand_{p1.id}"].objects
    assert obj.id not in game.state.zones["battlefield"].objects


def test_zone_change_recomputes_zone_key_when_type_is_transformed() -> None:
    """
    Replacement effects often transform only the *type* (e.g. graveyard -> exile).
    If to_zone_type and to_zone disagree, the handler should treat the type as canonical.
    """
    game = Game()
    p1 = game.add_player("P1")
    game.add_player("P2")

    obj = game.create_object("Test Card", owner_id=p1.id, zone=ZoneType.BATTLEFIELD)

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone": "battlefield",
            "to_zone": f"graveyard_{p1.id}",      # stale key
            "from_zone_type": ZoneType.BATTLEFIELD,
            "to_zone_type": ZoneType.EXILE,       # canonical type
        },
        controller=p1.id,
    ))

    assert obj.zone == ZoneType.EXILE
    assert obj.id in game.state.zones["exile"].objects
    assert obj.id not in game.state.zones[f"graveyard_{p1.id}"].objects

