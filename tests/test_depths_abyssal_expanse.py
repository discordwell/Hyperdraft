from __future__ import annotations

from src.cards.depths.abyssal_expanse import ABYS_CARDS
from src.cards.depths.abyssal_expanse.decks import ABYS_STARTER_DECKS, make_abys_flagship
from src.engine.depths import DepthBand, deploy_vessel, dive_vessel
from src.engine.game import Game
from src.engine.types import Event, EventType, ZoneType


def _game():
    game = Game(mode="depths")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.create_object(
        name="P1 Flagship",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=make_abys_flagship().characteristics,
        card_def=make_abys_flagship(),
    ).state.depth_band = DepthBand.PERISCOPE
    game.create_object(
        name="P2 Flagship",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=make_abys_flagship().characteristics,
        card_def=make_abys_flagship(),
    ).state.depth_band = DepthBand.PERISCOPE
    return game, p1, p2


def _object(game, player, card_name: str, zone=ZoneType.BATTLEFIELD):
    card = ABYS_CARDS[card_name]
    obj = game.create_object(
        name=card.name,
        owner_id=player.id,
        zone=zone,
        characteristics=card.characteristics,
        card_def=card,
    )
    if getattr(card, "depths_default_depth", None) is not None:
        obj.state.depth_band = card.depths_default_depth
    return obj


def test_abys_card_pool_and_decks_are_complete():
    assert len(ABYS_CARDS) == 180
    assert all(getattr(card, "domain", None) == "ABYS" for card in ABYS_CARDS.values())
    assert set(ABYS_STARTER_DECKS) == {
        "ABYS_thermals",
        "ABYS_salvage",
        "ABYS_leviathans",
        "ABYS_convoy",
        "ABYS_minefield",
        "ABYS_research",
    }
    for builder in ABYS_STARTER_DECKS.values():
        deck = builder()
        assert len(deck) == 30
        assert sum(1 for card in deck if card.characteristics.power is not None) >= 18


def test_vent_refunds_dive_charge_at_deep():
    game, p1, _ = _game()
    vessel = _object(game, p1, "Vent Minnow")
    vessel.state.depth_band = DepthBand.MID
    p1.sc = 3

    ok, msg, _events = dive_vessel(game, p1.id, vessel_id=vessel.id)

    assert ok, msg
    assert vessel.state.depth_band == DepthBand.DEEP
    assert p1.sc == 3


def test_scan_etb_marks_opposing_vessel_detected():
    game, p1, p2 = _game()
    target = _object(game, p2, "Scrap Skimmer")
    target.state.detected = False
    scout = _object(game, p1, "Harbor Shepherd", zone=ZoneType.HAND)
    p1.tc = 5
    p1.sc = 5

    ok, msg, _events = deploy_vessel(game, p1.id, card_id=scout.id)

    assert ok, msg
    assert target.state.detected is True


def test_salvage_applies_when_vessel_is_sunk():
    game, p1, _ = _game()
    vessel = _object(game, p1, "Scrap Skimmer")
    p1.tc = 0

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": vessel.id, "reason": "test_sunk"},
        source="test",
    ))

    assert p1.tc == 1
    assert vessel.zone == ZoneType.GRAVEYARD
