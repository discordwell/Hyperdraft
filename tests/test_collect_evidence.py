"""Phase 5B: collect_evidence helper test."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, make_instant,
)
from src.cards.interceptor_helpers import collect_evidence, was_bargained


def _put_in_graveyard(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def test_collect_evidence_picks_highest_mv_until_threshold():
    game = Game()
    p1 = game.add_player("Alice")

    # Stuff graveyard with a 1cmc, 2cmc, 4cmc creature.
    c1 = make_creature(
        name="Cheap", power=1, toughness=1, mana_cost="{W}",
        colors={Color.WHITE}, subtypes={"Human"}, text="",
    )
    c2 = make_creature(
        name="Mid", power=2, toughness=2, mana_cost="{1}{U}",
        colors={Color.BLUE}, subtypes={"Human"}, text="",
    )
    c4 = make_creature(
        name="Big", power=4, toughness=4, mana_cost="{2}{B}{B}",
        colors={Color.BLACK}, subtypes={"Demon"}, text="",
    )
    o1 = _put_in_graveyard(game, p1, c1)
    o2 = _put_in_graveyard(game, p1, c2)
    o4 = _put_in_graveyard(game, p1, c4)

    # collect_evidence 4 should pick the 4cmc card (alone covers the threshold).
    events = collect_evidence(p1.id, 4, game.state, source_id="src")
    assert events is not None, "should be able to collect evidence 4"
    assert len(events) == 1
    assert events[0].payload['object_id'] == o4.id

    # collect_evidence 5 should pick the 4cmc + 2cmc.
    events = collect_evidence(p1.id, 5, game.state, source_id="src")
    assert events is not None, "should be able to collect evidence 5"
    ids = [e.payload['object_id'] for e in events]
    assert o4.id in ids and o2.id in ids
    print("PASS: collect_evidence picks highest MV until threshold")


def test_collect_evidence_returns_none_when_insufficient():
    game = Game()
    p1 = game.add_player("Alice")

    c1 = make_creature(
        name="Cheap", power=1, toughness=1, mana_cost="{W}",
        colors={Color.WHITE}, subtypes={"Human"}, text="",
    )
    _put_in_graveyard(game, p1, c1)

    # Asking for 5 with only a 1cmc card available → None.
    events = collect_evidence(p1.id, 5, game.state, source_id="src")
    assert events is None, "should return None when can't meet threshold"
    print("PASS: collect_evidence returns None when insufficient")


def test_was_bargained_reads_stack_object():
    game = Game()
    p1 = game.add_player("Alice")

    spell_def = make_instant(
        name="Test Spell", mana_cost="{R}", colors={Color.RED},
        text="Test bargain spell",
    )
    spell = game.create_object(
        name=spell_def.name,
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=spell_def.characteristics,
        card_def=spell_def,
    )
    # Place on stack zone.
    stack = game.state.zones.get('stack')
    if stack and spell.id not in stack.objects:
        stack.objects.append(spell.id)

    assert not was_bargained(game.state, "Test Spell"), "default should be False"

    spell.state.was_bargained = True
    assert was_bargained(game.state, "Test Spell"), "should pick up the flag"
    print("PASS: was_bargained reads stack object")


if __name__ == "__main__":
    test_collect_evidence_picks_highest_mv_until_threshold()
    test_collect_evidence_returns_none_when_insufficient()
    test_was_bargained_reads_stack_object()
    print("\nAll Phase 5B helper tests passed!")
