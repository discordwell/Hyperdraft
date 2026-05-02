"""Sweep 10: grant_death_trigger framework test."""
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
from src.cards.interceptor_helpers import grant_death_trigger


def _spawn(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def test_granted_death_trigger_fires_on_destroy():
    """When target is destroyed, the granted trigger emits its effect."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    source_def = make_creature(
        name="Source", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED}, subtypes={"Wizard"}, text="",
    )

    bear = _spawn(game, p1, bear_def)
    source = _spawn(game, p1, source_def)

    captured = []
    def on_die(target_obj, state):
        captured.append(target_obj.id)
        # Just emit a placeholder LIFE_CHANGE so we can see the chain fire.
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 5},
            source=source.id, controller=p1.id,
        )]

    grant_death_trigger(bear, source, game.state, on_die)

    # Sanity: nothing fired yet.
    p1_life_before = game.state.players[p1.id].life

    # Destroy the bear — fire OBJECT_DESTROYED.
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': bear.id, 'reason': 'lethal_damage'},
    ))

    # The grant should have fired and the LIFE_CHANGE chained.
    assert captured == [bear.id], f"expected captured=[bear.id], got {captured}"
    p1_life_after = game.state.players[p1.id].life
    assert p1_life_after == p1_life_before + 5, f"expected life +5, got {p1_life_before} -> {p1_life_after}"
    print("PASS: granted death trigger fires on destroy")


def test_granted_death_trigger_does_not_fire_for_other_creatures():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p1, bear_def)
    other = _spawn(game, p1, bear_def)
    source_def = make_creature(
        name="Source", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED}, subtypes={"Wizard"}, text="",
    )
    source = _spawn(game, p1, source_def)

    captured = []
    def on_die(target_obj, state):
        captured.append(target_obj.id)
        return []

    grant_death_trigger(bear, source, game.state, on_die)

    # Destroy the OTHER creature.
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': other.id},
    ))
    assert captured == [], f"expected no capture, got {captured}"
    print("PASS: granted death trigger doesn't fire for other creatures")


if __name__ == "__main__":
    test_granted_death_trigger_fires_on_destroy()
    test_granted_death_trigger_does_not_fire_for_other_creatures()
    print("\nAll grant_death_trigger tests passed!")
