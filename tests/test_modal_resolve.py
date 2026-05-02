"""make_modal_resolve helper test.

Builds a "Choose one or more — gain life / draw a card" spell, casts it
via the resolve= callback, picks both modes, and verifies both effects fire.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_sorcery,
)
from src.cards.interceptor_helpers import make_modal_resolve


def test_modal_single_choice_dispatches():
    """Choose one — A B C: pick A; only A's events fire."""
    def gain3(state, caster_id, spell_id):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': 3},
            source=spell_id, controller=caster_id,
        )]
    def draw1(state, caster_id, spell_id):
        return [Event(
            type=EventType.DRAW,
            payload={'player': caster_id, 'count': 1},
            source=spell_id, controller=caster_id,
        )]

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    card_def = make_sorcery(
        name="Choose One Test", mana_cost="{1}",
        colors=set(),
        text="Choose one —\n• You gain 3 life.\n• Draw a card.",
        resolve=make_modal_resolve(
            "Choose One Test",
            modes=[("Gain 3 life", gain3), ("Draw a card", draw1)],
            min_modes=1, max_modes=1,
        ),
    )

    spell = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.STACK,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    stack = game.state.zones.get('stack')
    if spell.id not in stack.objects:
        stack.objects.append(spell.id)

    card_def.resolve([], game.state)

    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "modal_with_callback"
    # Pick mode 1 (draw a card).
    p1_cards_before = len(game.state.zones[f'hand_{p1.id}'].objects)
    ok, _err, evs = game.submit_choice(pc.id, p1.id, [1])
    assert ok
    types = [e.type for e in evs]
    assert EventType.DRAW in types and EventType.LIFE_CHANGE not in types, (
        f"only mode 1 should fire, got {types}"
    )
    print("PASS: modal single-choice dispatches")


def test_modal_multi_choice_both_fire():
    """Choose one or more — A B; pick both; both effects fire."""
    def gain3(state, caster_id, spell_id):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': 3},
            source=spell_id, controller=caster_id,
        )]
    def loss2(state, caster_id, spell_id):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': -2},
            source=spell_id, controller=caster_id,
        )]

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    card_def = make_sorcery(
        name="Choose Both Test", mana_cost="{2}",
        colors=set(),
        text="Choose one or more —\n• You gain 3 life.\n• You lose 2 life.",
        resolve=make_modal_resolve(
            "Choose Both Test",
            modes=[("Gain 3 life", gain3), ("Lose 2 life", loss2)],
            min_modes=1, max_modes=2,
        ),
    )

    spell = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.STACK,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    stack = game.state.zones.get('stack')
    if spell.id not in stack.objects:
        stack.objects.append(spell.id)

    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc.min_choices == 1 and pc.max_choices == 2
    # Pick both.
    ok, _err, evs = game.submit_choice(pc.id, p1.id, [0, 1])
    assert ok
    life_events = [e for e in evs if e.type == EventType.LIFE_CHANGE]
    assert len(life_events) == 2, f"expected 2 life-change events, got {len(life_events)}"
    amounts = sorted(e.payload['amount'] for e in life_events)
    assert amounts == [-2, 3], f"expected [-2, 3], got {amounts}"
    print("PASS: modal multi-choice — both modes fire")


if __name__ == "__main__":
    test_modal_single_choice_dispatches()
    test_modal_multi_choice_both_fire()
    print("\nAll modal-resolve tests passed!")
