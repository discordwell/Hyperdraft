"""Sweep 4: becomes_creature tests.

Covers:
- A non-creature artifact becomes a 4/4 creature
- A land becomes a 3/3 Elemental with haste
- Power and toughness queries reflect the override
- Granted keywords flow through QUERY_ABILITIES
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_artifact, make_land,
    get_power, get_toughness, get_types, has_ability,
)
from src.cards.interceptor_helpers import becomes_creature


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


def test_artifact_becomes_creature():
    game = Game()
    p1 = game.add_player("Alice")

    art_def = make_artifact(name="Trinket", mana_cost="{1}", text="")
    art = _spawn(game, p1, art_def)

    # Sanity: not a creature.
    types = get_types(art, game.state)
    assert CardType.CREATURE not in types
    assert CardType.ARTIFACT in types

    # Apply becomes_creature.
    becomes_creature(art, game.state, power=4, toughness=4)

    # After: should be a creature with P/T 4/4.
    types = get_types(art, game.state)
    assert CardType.CREATURE in types, f"expected CREATURE in types, got {types}"
    assert CardType.ARTIFACT in types, f"ARTIFACT should still be present, got {types}"
    assert get_power(art, game.state) == 4, f"expected 4 power, got {get_power(art, game.state)}"
    assert get_toughness(art, game.state) == 4, f"expected 4 toughness, got {get_toughness(art, game.state)}"
    print("PASS: artifact becomes creature 4/4")


def test_land_becomes_creature_with_haste():
    game = Game()
    p1 = game.add_player("Alice")

    land_def = make_land(name="Mountain", text="", subtypes={"Mountain"})
    land = _spawn(game, p1, land_def)

    becomes_creature(
        land, game.state, power=3, toughness=3,
        subtypes={"Elemental"}, keywords=["haste"],
    )

    types = get_types(land, game.state)
    assert CardType.CREATURE in types and CardType.LAND in types, f"expected CREATURE+LAND, got {types}"
    assert get_power(land, game.state) == 3
    assert get_toughness(land, game.state) == 3
    assert has_ability(land, "haste", game.state), "should have haste"
    assert "Elemental" in land.characteristics.subtypes, "should have Elemental subtype"
    print("PASS: land becomes 3/3 Elemental with haste")


if __name__ == "__main__":
    test_artifact_becomes_creature()
    test_land_becomes_creature_with_haste()
    print("\nAll becomes_creature tests passed!")
