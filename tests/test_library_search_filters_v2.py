"""Helper 2 — `card_name_any` + `mana_value_max` filters on SEARCH_LIBRARY.

Two new payload keys recognised by ``_handle_search_library_event``:

- ``card_name_any: list[str]`` — restrict candidates to specific card names
  (e.g. Beedle, Traveling Merchant: "Heart Container", "Bomb Bag", ...).
- ``mana_value_max: int`` — restrict candidates to MV <= N (e.g. Link, Hero
  of the Wild: "Equipment with mana value 3 or less"). X-costs count as 0.

These were the two filter shapes flagged in claudepad as missing engine
support during the ZLD spice pass — without them, cards punted to "tutor
any matching" or ate the wrong-cost find.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import Game, Event, EventType, ZoneType, make_creature, make_artifact


def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    return game, p1


def _put_in_library(game, player, card_def):
    library_key = f"library_{player.id}"
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.LIBRARY,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    library = game.state.zones.get(library_key)
    if library is not None and obj.id not in library.objects:
        library.objects.append(obj.id)
    return obj


def _emit_search(game, player, **payload):
    game.emit(Event(
        type=EventType.SEARCH_LIBRARY,
        payload={'player': player.id, **payload},
        source=None,
    ))


def test_card_name_any_restricts_candidates_to_named_list():
    """card_name_any: only objects whose .name is in the list are candidates."""
    game, p1 = _new_game()
    heart = _put_in_library(game, p1, make_artifact(name="Heart Container", mana_cost="{2}", text=""))
    bomb = _put_in_library(game, p1, make_artifact(name="Bomb Bag", mana_cost="{3}", text=""))
    hookshot = _put_in_library(game, p1, make_artifact(name="Hookshot", mana_cost="{2}", text=""))
    irrelevant = _put_in_library(game, p1, make_artifact(name="Random Tome", mana_cost="{1}", text=""))

    _emit_search(
        game, p1,
        card_name_any=["Heart Container", "Bomb Bag", "Hookshot", "Bunny Hood", "Fairy Bottle", "Sheikah Slate"],
        destination="hand",
        max_count=1,
    )

    choice = game.state.pending_choice
    assert choice is not None, "Expected a pending choice for the search"
    candidate_ids = set(choice.options)
    assert heart.id in candidate_ids
    assert bomb.id in candidate_ids
    assert hookshot.id in candidate_ids
    assert irrelevant.id not in candidate_ids, (
        f"Random Tome should NOT be a candidate; got options={candidate_ids}"
    )


def test_card_name_any_with_single_string_works():
    """Defensive: card_name_any accepts a single string too, not just a list."""
    game, p1 = _new_game()
    target = _put_in_library(game, p1, make_artifact(name="Heart Container", mana_cost="{2}", text=""))
    _put_in_library(game, p1, make_artifact(name="Bomb Bag", mana_cost="{3}", text=""))

    _emit_search(game, p1, card_name_any="Heart Container", destination="hand")

    choice = game.state.pending_choice
    assert choice is not None
    assert set(choice.options) == {target.id}, (
        f"Expected only Heart Container; got {choice.options}"
    )


def test_mana_value_max_restricts_by_cost():
    """mana_value_max=3 should only surface candidates with MV <= 3."""
    game, p1 = _new_game()
    cheap = _put_in_library(game, p1, make_artifact(
        name="Cheap Gauntlet", mana_cost="{2}", text="", subtypes={"Equipment"}
    ))
    mid = _put_in_library(game, p1, make_artifact(
        name="Mid Gauntlet", mana_cost="{3}", text="", subtypes={"Equipment"}
    ))
    expensive = _put_in_library(game, p1, make_artifact(
        name="Expensive Gauntlet", mana_cost="{6}", text="", subtypes={"Equipment"}
    ))
    colored = _put_in_library(game, p1, make_artifact(
        name="Colored Gauntlet", mana_cost="{1}{W}{W}", text="", subtypes={"Equipment"}
    ))  # MV=3

    _emit_search(
        game, p1,
        subtype="Equipment",
        mana_value_max=3,
        destination="battlefield",
        max_count=1,
    )

    choice = game.state.pending_choice
    assert choice is not None
    candidates = set(choice.options)
    assert cheap.id in candidates
    assert mid.id in candidates
    assert colored.id in candidates, "MV=3 from colored mana should be in"
    assert expensive.id not in candidates, (
        f"MV=6 should be excluded by mana_value_max=3; got {candidates}"
    )


def test_mana_value_max_combines_with_subtype_filter():
    """Filters AND together — subtype=Equipment AND mana_value_max=3 needs both."""
    game, p1 = _new_game()
    eq_cheap = _put_in_library(game, p1, make_artifact(
        name="Cheap Equip", mana_cost="{2}", text="", subtypes={"Equipment"}
    ))
    eq_expensive = _put_in_library(game, p1, make_artifact(
        name="Heavy Equip", mana_cost="{5}", text="", subtypes={"Equipment"}
    ))
    non_eq_cheap = _put_in_library(game, p1, make_artifact(
        name="Cheap Trinket", mana_cost="{1}", text=""
    ))

    _emit_search(
        game, p1,
        subtype="Equipment",
        mana_value_max=3,
        destination="battlefield",
    )

    choice = game.state.pending_choice
    assert choice is not None
    candidates = set(choice.options)
    assert eq_cheap.id in candidates
    assert eq_expensive.id not in candidates, "MV>3 should be excluded"
    assert non_eq_cheap.id not in candidates, "Non-equipment should be excluded"


def test_mana_value_max_zero_only_finds_zero_cost():
    """mana_value_max=0 restricts to 0-cost cards."""
    game, p1 = _new_game()
    zero = _put_in_library(game, p1, make_artifact(
        name="Zero Cost", mana_cost="{0}", text="", subtypes={"Equipment"}
    ))
    one = _put_in_library(game, p1, make_artifact(
        name="One Cost", mana_cost="{1}", text="", subtypes={"Equipment"}
    ))

    _emit_search(
        game, p1,
        subtype="Equipment",
        mana_value_max=0,
        destination="hand",
    )

    choice = game.state.pending_choice
    assert choice is not None
    candidates = set(choice.options)
    assert zero.id in candidates
    assert one.id not in candidates


if __name__ == "__main__":
    print("=" * 60)
    print("Helper 2 — card_name_any + mana_value_max SEARCH_LIBRARY filters")
    print("=" * 60)
    tests = [
        test_card_name_any_restricts_candidates_to_named_list,
        test_card_name_any_with_single_string_works,
        test_mana_value_max_restricts_by_cost,
        test_mana_value_max_combines_with_subtype_filter,
        test_mana_value_max_zero_only_finds_zero_cost,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print("=" * 60)
    print(f"Total: {passed}/{len(tests)} passed")
    print("=" * 60)
