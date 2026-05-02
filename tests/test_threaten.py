"""Sweep 7: threaten_creature helper test.

Standard "gain control + untap + haste EOT" — the helper emits three events
that the engine handlers process: CONTROL_CHANGE switches controller and
stashes the original; UNTAP readies the creature; GRANT_KEYWORD haste lets
it attack.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, has_ability,
)
from src.cards.interceptor_helpers import threaten_creature


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


def test_threaten_creature_steals_and_grants_haste():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    bear_def = make_creature(
        name="Bear", power=2, toughness=2, mana_cost="{1}{G}",
        colors={Color.GREEN}, subtypes={"Bear"}, text="",
    )
    bear = _spawn(game, p2, bear_def)
    # Tap + summoning sickness to verify untap and haste apply.
    bear.state.tapped = True
    bear.state.summoning_sickness = True

    assert bear.controller == p2.id
    assert not has_ability(bear, "haste", game.state)

    # Alice steals it.
    for ev in threaten_creature(bear.id, p1.id, source_id="threaten_spell"):
        game.emit(ev)

    assert bear.controller == p1.id, f"expected Alice to control bear, got {bear.controller}"
    assert not bear.state.tapped, "bear should be untapped"
    assert has_ability(bear, "haste", game.state), "bear should have haste"
    # Original controller is stashed for EOT restore.
    assert getattr(bear.state, "_restore_controller_eot", None) == p2.id
    print("PASS: threaten_creature steals + untaps + grants haste")


if __name__ == "__main__":
    test_threaten_creature_steals_and_grants_haste()
    print("\nAll Threaten tests passed!")
