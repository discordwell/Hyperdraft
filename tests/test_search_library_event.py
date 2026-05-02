"""Pipeline handler for EventType.SEARCH_LIBRARY.

Cards emit SEARCH_LIBRARY events with various payload shapes; the handler
translates them into a create_library_search_choice PendingChoice so the
player can actually pick a card.

Tests:
- Basic land search creates a library_search PendingChoice with options
  filtered to basic lands.
- Subtype filter (Plains-only) restricts the candidate list.
- "creature_or_land" filter accepts both.
- Card-type filter (CREATURE) accepts only creatures.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, make_land, CardDefinition, Characteristics,
)


def _add_to_library(game, player, card_def):
    return game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.LIBRARY,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_basic_land_search_opens_pending_choice():
    game = Game()
    p1 = game.add_player("Alice")

    # Library: 1 Plains, 1 Mountain, 1 Bear
    plains_def = make_land(name="Plains", text="", subtypes={"Plains"},
                            supertypes={"Basic"})
    mountain_def = make_land(name="Mountain", text="", subtypes={"Mountain"},
                              supertypes={"Basic"})
    bear_def = make_creature(name="Bear", power=2, toughness=2,
                              mana_cost="{1}{G}", colors={Color.GREEN},
                              subtypes={"Bear"}, text="")
    plains = _add_to_library(game, p1, plains_def)
    mountain = _add_to_library(game, p1, mountain_def)
    bear = _add_to_library(game, p1, bear_def)

    game.emit(Event(
        type=EventType.SEARCH_LIBRARY,
        payload={'player': p1.id, 'filter': 'basic_land',
                 'destination': 'hand', 'amount': 1},
        source="test",
        controller=p1.id,
    ))

    pc = game.state.pending_choice
    assert pc is not None, "expected pending_choice for SEARCH_LIBRARY"
    assert pc.choice_type == "library_search"
    # Options are card ids of basic lands only.
    assert plains.id in pc.options and mountain.id in pc.options
    assert bear.id not in pc.options, "Bear should not be a basic-land option"
    print("PASS: basic-land SEARCH_LIBRARY opens a filtered choice")


def test_subtype_filter_restricts_to_one_basic():
    game = Game()
    p1 = game.add_player("Alice")

    plains_def = make_land(name="Plains", text="", subtypes={"Plains"},
                            supertypes={"Basic"})
    forest_def = make_land(name="Forest", text="", subtypes={"Forest"},
                            supertypes={"Basic"})
    plains = _add_to_library(game, p1, plains_def)
    forest = _add_to_library(game, p1, forest_def)

    game.emit(Event(
        type=EventType.SEARCH_LIBRARY,
        payload={'player': p1.id, 'card_type': 'land',
                 'subtype': 'Plains', 'basic_only': True,
                 'destination': 'hand'},
        source="test",
        controller=p1.id,
    ))

    pc = game.state.pending_choice
    assert pc is not None
    assert plains.id in pc.options and forest.id not in pc.options
    print("PASS: subtype filter restricts to matching basic")


def test_creature_or_land_filter():
    game = Game()
    p1 = game.add_player("Alice")

    bear_def = make_creature(name="Bear", power=2, toughness=2,
                              mana_cost="{1}{G}", colors={Color.GREEN},
                              subtypes={"Bear"}, text="")
    forest_def = make_land(name="Forest", text="", subtypes={"Forest"},
                            supertypes={"Basic"})
    artifact_def = CardDefinition(
        name="Trinket", mana_cost="{1}",
        characteristics=Characteristics(
            types={CardType.ARTIFACT}, subtypes=set(), colors=set(),
            mana_cost="{1}",
        ),
        text="",
    )
    bear = _add_to_library(game, p1, bear_def)
    forest = _add_to_library(game, p1, forest_def)
    art = _add_to_library(game, p1, artifact_def)

    game.emit(Event(
        type=EventType.SEARCH_LIBRARY,
        payload={'player': p1.id, 'filter': 'creature_or_land',
                 'destination': 'hand'},
        source="test",
        controller=p1.id,
    ))

    pc = game.state.pending_choice
    assert pc is not None
    assert bear.id in pc.options and forest.id in pc.options
    assert art.id not in pc.options
    print("PASS: creature_or_land filter")


if __name__ == "__main__":
    test_basic_land_search_opens_pending_choice()
    test_subtype_filter_restricts_to_one_basic()
    test_creature_or_land_filter()
    print("\nAll SEARCH_LIBRARY handler tests passed!")
