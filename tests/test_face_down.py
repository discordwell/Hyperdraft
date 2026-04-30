"""
Test the face-down zone / state mechanic.

Covers:
1. A face-down 2/2 reports 2/2/colourless/no-types/no-name regardless of the
   underlying card's real characteristics.
2. Turning the card face-up via the TURN_FACE_UP event reveals its real P/T,
   colours, and types, and re-runs ``card_def.setup_interceptors`` so any ETB
   triggers fire.
3. The masking interceptors are removed on flip so subsequent QUERY effects
   (e.g. counter-derived stats) work as if the card had entered face-up.

The test bypasses the casting subsystem and operates at the engine level —
mirroring how other Hyperdraft test suites exercise interceptor behaviour.
"""

import os
import sys
# Allow this test to run from inside a Claude worktree (where the cwd is the
# worktree, not the parent repo). Compute the project root from this file
# and put it on sys.path explicitly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness, get_types, get_colors, has_ability,
    make_creature,
)
from src.cards.interceptor_helpers import (
    make_face_down_setup, make_manifest_etb_event,
    is_face_down, turn_face_up,
    make_etb_trigger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_face_down_creature(game, player, card_def):
    """
    Manifest a card_def's creature into the battlefield face-down.

    Returns the resulting GameObject. We bypass the LIBRARY_SEARCH choice
    machinery and invoke the OBJECT_CREATED + masking-setup path directly.
    """
    # Emit OBJECT_CREATED with face_down=True. The pipeline's object-created
    # handler will install the masking QUERY interceptors automatically.
    create_event = make_manifest_etb_event(player.id, card_def=card_def)
    game.emit(create_event)
    obj_id = create_event.payload.get('object_id')
    return game.state.objects[obj_id]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_face_down_reports_vanilla_22():
    """A face-down 2/2 must mask the underlying card's characteristics."""
    print("\n=== Test: Face-down reports 2/2 / colourless / no name ===")

    game = Game()
    p1 = game.add_player("Alice")

    # Underlying card: a 5/5 red Dragon with flying.
    underneath = make_creature(
        name="Mighty Dragon",
        power=5, toughness=5,
        mana_cost="{4}{R}",
        colors={Color.RED},
        subtypes={"Dragon"},
        text="Flying.",
    )
    underneath.characteristics.abilities = [{'keyword': 'flying'}]

    obj = _build_face_down_creature(game, p1, underneath)

    # Sanity: the underlying card_def is preserved.
    assert obj.card_def is underneath, "card_def must survive being masked"
    assert is_face_down(obj), "object should report face-down"

    power = get_power(obj, game.state)
    toughness = get_toughness(obj, game.state)
    colors = get_colors(obj, game.state)
    types = get_types(obj, game.state)
    has_flying = has_ability(obj, 'flying', game.state)

    print(f"Reported P/T: {power}/{toughness}")
    print(f"Reported colours: {colors}")
    print(f"Reported types: {types}")
    print(f"Has flying? {has_flying}")
    print(f"Public name: {obj.name!r}")

    assert power == 2, f"face-down should be 2 power, got {power}"
    assert toughness == 2, f"face-down should be 2 toughness, got {toughness}"
    assert colors == set(), f"face-down should be colourless, got {colors}"
    assert types == {CardType.CREATURE}, \
        f"face-down should be just CREATURE, got {types}"
    assert not has_flying, "face-down must not expose underlying keywords"
    assert obj.name == "", "face-down should have no public name"

    print("PASS: face-down 2/2 masks the underlying card.")


def test_turn_face_up_reveals_real_characteristics_and_fires_etb():
    """
    Flipping a face-down permanent:
      * resets P/T to the real card's values
      * restores types/colours
      * re-runs setup_interceptors so ETB triggers fire (CR 707.4 spirit)
    """
    print("\n=== Test: TURN_FACE_UP reveals real card and fires ETB ===")

    game = Game()
    p1 = game.add_player("Alice")
    p1.life = 20

    etb_fired = {'count': 0}

    def life_gain_setup(obj, state):
        # When this card enters (face-up), gain 7 life. We use a simple flag
        # rather than emitting a LIFE_CHANGE to keep the test self-contained.
        def etb_effect(event, state):
            etb_fired['count'] += 1
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 7},
                source=obj.id,
            )]
        return [make_etb_trigger(obj, etb_effect)]

    underneath = make_creature(
        name="Lifebringer",
        power=3, toughness=4,
        mana_cost="{2}{W}",
        colors={Color.WHITE},
        subtypes={"Angel"},
        text="When this creature enters, gain 7 life.",
        setup_interceptors=life_gain_setup,
    )

    obj = _build_face_down_creature(game, p1, underneath)

    # Cement the masking attaches a face-up cost & activation closure.
    setup_ints = make_face_down_setup(obj, face_up_cost="{2}{W}")
    for ic in setup_ints:
        ic.timestamp = game.state.next_timestamp()
        game.state.interceptors[ic.id] = ic
        obj.interceptor_ids.append(ic.id)

    # Pre-flip baseline.
    assert get_power(obj, game.state) == 2
    assert get_toughness(obj, game.state) == 2
    assert get_colors(obj, game.state) == set()
    pre_flip_life = p1.life

    # Flip via the TURN_FACE_UP event (this is the public engine API).
    game.emit(Event(
        type=EventType.TURN_FACE_UP,
        payload={'object_id': obj.id, 'mana_paid_cost': '{2}{W}'},
        source=obj.id,
        controller=p1.id,
    ))

    print(f"face_down after flip: {is_face_down(obj)}")
    print(f"Reported P/T after flip: {get_power(obj, game.state)}/{get_toughness(obj, game.state)}")
    print(f"Reported colours after flip: {get_colors(obj, game.state)}")
    print(f"Types after flip: {get_types(obj, game.state)}")
    print(f"ETB fired count: {etb_fired['count']}")
    print(f"Life: {pre_flip_life} -> {p1.life}")

    assert not is_face_down(obj), "object should no longer be face-down"
    assert get_power(obj, game.state) == 3
    assert get_toughness(obj, game.state) == 4
    assert get_colors(obj, game.state) == {Color.WHITE}
    assert CardType.CREATURE in get_types(obj, game.state)
    assert etb_fired['count'] == 1, "ETB trigger must fire exactly once on flip"
    assert p1.life == pre_flip_life + 7, "ETB-driven life gain should resolve"

    print("PASS: flip restores characteristics and fires ETB.")


def test_threats_around_every_corner_manifests_face_down():
    """
    Wet-ish: Threats Around Every Corner's ETB should put a face-down 2/2 onto
    the battlefield. We seed the controller's library with one card so the
    'top of library' lookup has something to bite on.
    """
    print("\n=== Test: Threats Around Every Corner manifests face-down ===")

    from src.cards.duskmourn import THREATS_AROUND_EVERY_CORNER

    game = Game()
    p1 = game.add_player("Alice")

    # Seed the library with a known creature.
    seed = make_creature(
        name="Library Top",
        power=4, toughness=5,
        mana_cost="{3}{G}",
        colors={Color.GREEN},
        subtypes={"Beast"},
    )
    library_obj = game.create_object(
        name="Library Top",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=seed.characteristics,
        card_def=seed,
    )

    # Bring Threats Around Every Corner onto the battlefield via ZONE_CHANGE so
    # its ETB (manifest dread) runs through the same path used by real plays.
    threats = game.create_object(
        name="Threats Around Every Corner",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=THREATS_AROUND_EVERY_CORNER.characteristics,
        card_def=None,  # avoid premature setup; ZONE_CHANGE re-installs.
    )
    threats.card_def = THREATS_AROUND_EVERY_CORNER

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': threats.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))

    # Find the face-down permanent we just minted.
    face_down_objs = [
        o for o in game.state.objects.values()
        if o.id != threats.id and o.id != library_obj.id and is_face_down(o)
    ]
    print(f"Face-down permanents on battlefield: {len(face_down_objs)}")
    assert len(face_down_objs) == 1, \
        f"expected exactly one face-down 2/2, got {len(face_down_objs)}"

    fd = face_down_objs[0]
    assert get_power(fd, game.state) == 2
    assert get_toughness(fd, game.state) == 2
    assert fd.controller == p1.id
    # The seed card was the top of library — its card_def must be preserved
    # on the manifested object so we can flip it face-up later.
    assert fd.card_def is seed

    print("PASS: Threats Around Every Corner manifests a face-down 2/2.")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("FACE-DOWN MECHANIC TESTS")
    print("=" * 60)

    test_face_down_reports_vanilla_22()
    test_turn_face_up_reveals_real_characteristics_and_fires_etb()
    test_threats_around_every_corner_manifests_face_down()

    print()
    print("=" * 60)
    print("ALL FACE-DOWN TESTS PASSED!")
    print("=" * 60)
