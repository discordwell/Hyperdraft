"""Sweep 5: manifest_dread tests.

Manifest dread looks at the top 2 cards, manifests the first as a face-
down 2/2, and puts the second into the graveyard.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature,
)


def _add_to_library(game, player, card_def):
    """Push a card_def onto the top of the player's library."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.LIBRARY,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def test_manifest_dread_creates_face_down_and_mills():
    game = Game()
    p1 = game.add_player("Alice")

    # Push two cards onto p1's library top.
    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    wolf_def = make_creature(
        name="Wolf", power=3, toughness=2, mana_cost="{2}{G}",
        colors={Color.GREEN}, subtypes={"Wolf"}, text="",
    )

    bear = _add_to_library(game, p1, bear_def)
    wolf = _add_to_library(game, p1, wolf_def)

    # Library order: Bear is first (manifest target); Wolf is second (milled).
    library = game.state.zones[f'library_{p1.id}']
    initial_lib = list(library.objects)
    assert initial_lib[0] == bear.id
    assert initial_lib[1] == wolf.id

    # Fire MANIFEST_DREAD.
    game.emit(Event(
        type=EventType.MANIFEST_DREAD,
        payload={'controller': p1.id, 'source_id': 'test'},
    ))

    # Library should have lost both cards.
    library_after = game.state.zones[f'library_{p1.id}']
    assert bear.id not in library_after.objects, "Bear (manifested) should leave library"
    assert wolf.id not in library_after.objects, "Wolf (milled) should leave library"

    # Wolf should be in graveyard.
    graveyard = game.state.zones[f'graveyard_{p1.id}']
    assert wolf.id in graveyard.objects, f"Wolf should be in graveyard, got {graveyard.objects}"

    # Bear should NOT be on the battlefield with its original ID — instead a
    # new face-down GameObject was created. Find the face-down creature.
    battlefield = game.state.zones['battlefield']
    face_down_creatures = [
        cid for cid in battlefield.objects
        if game.state.objects[cid].state.face_down
    ]
    assert face_down_creatures, "expected a face-down creature on battlefield"
    fd_obj = game.state.objects[face_down_creatures[0]]
    assert fd_obj.controller == p1.id
    print("PASS: manifest_dread creates face-down creature and mills second")


if __name__ == "__main__":
    test_manifest_dread_creates_face_down_and_mills()
    print("\nAll manifest_dread tests passed!")
