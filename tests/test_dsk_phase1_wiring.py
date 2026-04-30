"""
Phase 1 wiring sweep tests for Duskmourn (DSK).

Validates the noop-cleanup wirings from .phase1_briefings/duskmourn.json:

- Leyline of Hope: life-gain +1 replacement.
- Leyline of the Void: opponent-graveyard-to-exile replacement.
- Valgavoth, Terror Eater: opponent-graveyard-to-exile replacement.
- Lionheart Glimmer: COMBAT_DECLARED team-pump trigger registration.

These tests confirm the cards register the expected interceptors on entering
the battlefield and exercise the replacement effect (where directly testable
without door/room state). They are intentionally lightweight - the underlying
helpers themselves are covered by tests/test_replacements.py.
"""

import os
import sys

_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
sys.path.insert(0, _ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.cards.duskmourn import (
    LEYLINE_OF_HOPE,
    LEYLINE_OF_THE_VOID,
    VALGAVOTH_TERROR_EATER,
    LIONHEART_GLIMMER,
)


def _make_game(num_players: int = 1):
    game = Game()
    players = [game.add_player(f"P{i}") for i in range(num_players)]
    return game, players


def test_leyline_of_hope_life_gain_replacement():
    """Leyline of Hope adds +1 to controller's life-gain events."""
    print("\n=== Test: Leyline of Hope adds +1 to life gain ===")
    game, (p,) = _make_game(1)
    p.life = 20

    leyline = game.create_object(
        name="Leyline of Hope",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LEYLINE_OF_HOPE.characteristics,
        card_def=LEYLINE_OF_HOPE,
    )
    assert leyline.interceptor_ids, "Leyline of Hope should register interceptors"

    # Gaining 3 life should become 4 life.
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p.id, 'amount': 3},
    ))
    assert p.life == 24, f"Expected 24, got {p.life}"

    # Life loss must be untouched.
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p.id, 'amount': -2},
    ))
    assert p.life == 22, f"Expected 22, got {p.life}"
    print("PASS: Leyline of Hope life-gain replacement works")


def test_leyline_of_the_void_redirects_opponent_graveyard():
    """Leyline of the Void exiles cards going to an opponent's graveyard."""
    print("\n=== Test: Leyline of the Void redirects opponent's GY to exile ===")
    game, (p, opp) = _make_game(2)

    leyline = game.create_object(
        name="Leyline of the Void",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LEYLINE_OF_THE_VOID.characteristics,
        card_def=LEYLINE_OF_THE_VOID,
    )
    assert leyline.interceptor_ids, "Leyline of the Void should register interceptors"

    # Create a creature owned by the opponent on the stack/graveyard transit.
    victim = game.create_object(
        name="Goblin",
        owner_id=opp.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=1, toughness=1,
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': victim.id,
            'from_zone_type': ZoneType.STACK,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    assert victim.zone == ZoneType.EXILE, (
        f"Opponent's card should be exiled, ended up in {victim.zone}"
    )
    print("PASS: Leyline of the Void redirects opponent GY -> exile")


def test_leyline_of_the_void_does_not_affect_owners_graveyard():
    """Leyline of the Void does not redirect controller's own graveyard moves."""
    print("\n=== Test: Leyline of the Void leaves own GY alone ===")
    game, (p, opp) = _make_game(2)

    leyline = game.create_object(
        name="Leyline of the Void",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LEYLINE_OF_THE_VOID.characteristics,
        card_def=LEYLINE_OF_THE_VOID,
    )

    own_card = game.create_object(
        name="My Goblin",
        owner_id=p.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=1, toughness=1,
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': own_card.id,
            'from_zone_type': ZoneType.STACK,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    assert own_card.zone == ZoneType.GRAVEYARD, (
        f"Own card should land in graveyard, ended up in {own_card.zone}"
    )
    print("PASS: Leyline of the Void does not affect own graveyard")


def test_valgavoth_terror_eater_redirects_opponent_graveyard():
    """Valgavoth, Terror Eater exiles cards going to an opponent's graveyard."""
    print("\n=== Test: Valgavoth, Terror Eater redirects opponent GY -> exile ===")
    game, (p, opp) = _make_game(2)

    valgavoth = game.create_object(
        name="Valgavoth, Terror Eater",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=VALGAVOTH_TERROR_EATER.characteristics,
        card_def=VALGAVOTH_TERROR_EATER,
    )
    assert valgavoth.interceptor_ids, (
        "Valgavoth should register graveyard-to-exile interceptors"
    )

    victim = game.create_object(
        name="Lightning Bolt",
        owner_id=opp.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': victim.id,
            'from_zone_type': ZoneType.STACK,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    assert victim.zone == ZoneType.EXILE, (
        f"Opponent's card should be exiled, ended up in {victim.zone}"
    )
    print("PASS: Valgavoth, Terror Eater redirects opponent GY -> exile")


def test_lionheart_glimmer_registers_combat_trigger():
    """Lionheart Glimmer registers a COMBAT_DECLARED reaction interceptor."""
    print("\n=== Test: Lionheart Glimmer registers a combat trigger ===")
    game, (p,) = _make_game(1)

    glimmer = game.create_object(
        name="Lionheart Glimmer",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LIONHEART_GLIMMER.characteristics,
        card_def=LIONHEART_GLIMMER,
    )
    assert glimmer.interceptor_ids, (
        "Lionheart Glimmer should register at least one interceptor"
    )

    # We can't easily spin a full combat phase here without combat plumbing,
    # but we can verify the interceptor reacts to a hand-rolled COMBAT_DECLARED
    # event by emitting PT modifications for our other creatures.
    target = game.create_object(
        name="Soldier",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=2, toughness=2,
        ),
    )

    game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': p.id, 'attackers': [target.id]},
    ))

    # Both Lionheart Glimmer (an enchantment creature) and the Soldier should
    # have a temporary +1/+1 modifier registered.
    soldier_mods = getattr(target.state, 'pt_modifiers', [])
    assert any(
        m.get('power') == 1 and m.get('toughness') == 1 for m in soldier_mods
    ), f"Soldier should get +1/+1, got modifiers: {soldier_mods}"
    print("PASS: Lionheart Glimmer issues +1/+1 on combat declaration")


def run_all():
    print("=" * 60)
    print("DUSKMOURN PHASE 1 WIRING TESTS")
    print("=" * 60)

    test_leyline_of_hope_life_gain_replacement()
    test_leyline_of_the_void_redirects_opponent_graveyard()
    test_leyline_of_the_void_does_not_affect_owners_graveyard()
    test_valgavoth_terror_eater_redirects_opponent_graveyard()
    test_lionheart_glimmer_registers_combat_trigger()

    print("\n" + "=" * 60)
    print("ALL DSK PHASE 1 WIRING TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
