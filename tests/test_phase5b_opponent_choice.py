"""
Phase 5b — Agent K opponent-choice and tutor wirings.

Covers:
- RUSH_OF_DREAD mode 0 (sacrifice half their creatures, opponent's choice)
- RUSH_OF_DREAD mode 1 (discard half their hand, opponent's choice)
- SHIFTING_GRIFT (each player chooses a permanent; exchange control)
- CENTRAL_ELEVATOR door 1 (tutor for a Room with a non-collision name)

All four wirings rely on existing PendingChoice infrastructure
(``create_choice_and_resolve`` and ``create_library_search_choice``); no
engine changes were required.
"""

import asyncio
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    CardDefinition, Characteristics,
    PlayerAction, ActionType,
    make_instant, make_creature, make_enchantment,
)
from src.cards import outlaws_thunder_junction as otj
from src.cards import duskmourn as dsk


# ---------------------------------------------------------------------------
# Helpers (mirrored from other Phase 5b tests)
# ---------------------------------------------------------------------------


def make_two_player_game():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    return game, p1, p2


def add_mana(game, player_id, color="C", amount=1):
    from src.engine.mana import ManaType
    color_to_type = {
        "W": ManaType.WHITE,
        "U": ManaType.BLUE,
        "B": ManaType.BLACK,
        "R": ManaType.RED,
        "G": ManaType.GREEN,
        "C": ManaType.COLORLESS,
    }
    mtype = color_to_type[color]
    game.mana_system.produce_mana(player_id, mtype, amount)


def cast_spell(game, player_id, spell_obj):
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=player_id,
        card_id=spell_obj.id,
    )
    cast_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    emitted = []
    for ev in cast_events or []:
        emitted.extend(game.emit(ev))
    return cast_events + emitted


def make_spell(game, owner_id, card_def, zone=ZoneType.HAND):
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def submit_choice(game, player_id, payload):
    choice = game.state.pending_choice
    assert choice is not None, "expected a pending choice"
    return game.submit_choice(choice.id, player_id, payload)


def make_bear(game, owner_id, name="Bear", power=2, toughness=2, subtypes=None):
    if subtypes is None:
        subtypes = set()
    bear_def = make_creature(
        name=name, power=power, toughness=toughness,
        mana_cost="{2}", colors=set(),
        subtypes=subtypes,
    )
    return game.create_object(
        name=name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )


def make_card_in_hand(game, owner_id, name, mana_cost="{2}"):
    """Make a generic instant in the named player's hand for discard tests."""
    cdef = make_instant(
        name=name, mana_cost=mana_cost, colors=set(), text="",
    )
    return game.create_object(
        name=name, owner_id=owner_id, zone=ZoneType.HAND,
        characteristics=cdef.characteristics, card_def=cdef,
    )


def make_card_in_library(game, owner_id, card_def):
    """Make a card object in the named player's library."""
    return game.create_object(
        name=card_def.name, owner_id=owner_id, zone=ZoneType.LIBRARY,
        characteristics=card_def.characteristics, card_def=card_def,
    )


def make_room_def(name, mana_cost="{1}{U}", subtypes=None):
    """Build a minimal Room enchantment card definition for library/tutoring."""
    return make_enchantment(
        name=name,
        mana_cost=mana_cost,
        colors={Color.BLUE},
        subtypes=(subtypes or {"Room"}),
        text=f"{name}: tutored body.",
    )


# ---------------------------------------------------------------------------
# 1. RUSH_OF_DREAD mode 0 — opponent picks half their creatures to sacrifice
# ---------------------------------------------------------------------------


def test_rush_of_dread_sac_mode_opens_opponent_prompt():
    """Cast Rush of Dread + {1} on opponent → opens a sacrifice prompt owned
    by that opponent."""
    print("\n=== Test: Rush of Dread sac mode opens opponent prompt ===")
    game, p1, p2 = make_two_player_game()
    # P2 has 4 creatures.
    bears = [make_bear(game, p2.id, name=f"Opp Bear {i}") for i in range(4)]
    spell = make_spell(game, p1.id, otj.RUSH_OF_DREAD)
    add_mana(game, p1.id, "B", 2)
    add_mana(game, p1.id, "C", 2)  # {1}{B}{B} base + {1} mode
    cast_spell(game, p1.id, spell)

    # Spree mode select.
    choice = game.state.pending_choice
    assert choice is not None, "expected Spree mode prompt"
    payload = [{"index": 0}]  # mode 0 = sacrifice half
    ok, msg, _ = game.submit_choice(choice.id, p1.id, payload)
    assert ok, msg

    # Resolve_top opens the per-mode target_with_callback prompt (target opponent).
    events = game.stack.resolve_top()
    target_choice = game.state.pending_choice
    assert target_choice is not None, "expected per-mode target prompt"
    assert p2.id in target_choice.options

    # Submit target opponent.
    ok, msg, _events = game.submit_choice(target_choice.id, p1.id, [p2.id])
    assert ok, msg

    # Now: the new opponent-choice PendingChoice should be set, owned by p2.
    opp_choice = game.state.pending_choice
    assert opp_choice is not None, "expected opponent's sacrifice prompt"
    assert opp_choice.player == p2.id, \
        f"choice player should be opponent ({p2.id}), got {opp_choice.player}"
    assert opp_choice.choice_type == "rush_of_dread_sacrifice"
    # 4 creatures → ceil(4/2) = 2 picks required.
    assert opp_choice.min_choices == 2
    assert opp_choice.max_choices == 2
    print(f"OK: Rush of Dread opens sacrifice prompt for {p2.id} (pick 2 of 4)")


def test_rush_of_dread_sac_destroys_half_rounded_up():
    """5 creatures → opponent picks ceil(5/2)=3, each emits OBJECT_DESTROYED
    with reason='sacrifice'."""
    print("\n=== Test: Rush of Dread sac destroys half rounded up ===")
    game, p1, p2 = make_two_player_game()
    bears = [make_bear(game, p2.id, name=f"Opp Bear {i}") for i in range(5)]
    spell = make_spell(game, p1.id, otj.RUSH_OF_DREAD)
    add_mana(game, p1.id, "B", 2)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    game.submit_choice(
        game.state.pending_choice.id, p1.id, [{"index": 0}]
    )
    game.stack.resolve_top()
    target_choice = game.state.pending_choice
    game.submit_choice(target_choice.id, p1.id, [p2.id])

    opp_choice = game.state.pending_choice
    assert opp_choice is not None, "expected opponent sacrifice prompt"
    assert opp_choice.min_choices == 3, \
        f"5 creatures → 3 picks required (got {opp_choice.min_choices})"

    # Opponent picks the first 3 by id.
    pick = [b.id for b in bears[:3]]
    ok, msg, events = game.submit_choice(opp_choice.id, p2.id, pick)
    assert ok, msg

    destroys = [
        e for e in events
        if e.type == EventType.OBJECT_DESTROYED
        and e.payload.get('reason') == 'sacrifice'
    ]
    destroyed_ids = {e.payload.get('object_id') for e in destroys}
    assert destroyed_ids == set(pick), \
        f"expected destroy events for {pick}, got {destroyed_ids}"
    print(f"OK: Rush of Dread destroyed {len(destroyed_ids)} sacrificed creatures")


def test_rush_of_dread_sac_no_creatures_noop():
    """If the opponent controls zero creatures the sacrifice mode does
    nothing (no choice opened, no events)."""
    print("\n=== Test: Rush of Dread sac mode no-ops on empty board ===")
    game, p1, p2 = make_two_player_game()
    spell = make_spell(game, p1.id, otj.RUSH_OF_DREAD)
    add_mana(game, p1.id, "B", 2)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    game.submit_choice(
        game.state.pending_choice.id, p1.id, [{"index": 0}]
    )
    game.stack.resolve_top()
    target_choice = game.state.pending_choice
    ok, msg, events = game.submit_choice(target_choice.id, p1.id, [p2.id])
    assert ok, msg
    # No sacrifice prompt should be open.
    assert game.state.pending_choice is None, \
        f"no pending choice expected; got {game.state.pending_choice}"
    sacs = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
    assert not sacs, f"expected no destroys; got {sacs}"
    print("OK: Rush of Dread sac mode is a no-op when opponent has no creatures")


# ---------------------------------------------------------------------------
# 2. RUSH_OF_DREAD mode 1 — opponent picks half their hand to discard
# ---------------------------------------------------------------------------


def test_rush_of_dread_discard_mode():
    """Cast Rush of Dread + {2} on opponent who holds 3 cards → opponent
    picks ceil(3/2)=2 to discard."""
    print("\n=== Test: Rush of Dread discard mode ===")
    game, p1, p2 = make_two_player_game()
    cards = [
        make_card_in_hand(game, p2.id, name=f"Opp Card {i}")
        for i in range(3)
    ]
    spell = make_spell(game, p1.id, otj.RUSH_OF_DREAD)
    add_mana(game, p1.id, "B", 2)
    add_mana(game, p1.id, "C", 3)  # {1}{B}{B} base + {2} mode
    cast_spell(game, p1.id, spell)
    # Pick mode 1 (discard half).
    game.submit_choice(
        game.state.pending_choice.id, p1.id, [{"index": 1}]
    )
    game.stack.resolve_top()
    target_choice = game.state.pending_choice
    game.submit_choice(target_choice.id, p1.id, [p2.id])

    discard_choice = game.state.pending_choice
    assert discard_choice is not None, "expected discard prompt"
    assert discard_choice.player == p2.id, \
        f"discard prompt should be owned by opponent {p2.id}"
    assert discard_choice.choice_type == "rush_of_dread_discard"
    assert discard_choice.min_choices == 2 and discard_choice.max_choices == 2

    pick = [cards[0].id, cards[1].id]
    ok, msg, events = game.submit_choice(discard_choice.id, p2.id, pick)
    assert ok, msg

    discards = [
        e for e in events
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
    ]
    # We accept either per-card DISCARD events (the wiring's intent) OR
    # any DISCARD events targeting the chosen cards.
    discarded_ids = {e.payload.get('card_id') for e in discards}
    assert discarded_ids == set(pick), \
        f"expected DISCARD events for {pick}, got {[e.payload for e in discards]}"
    print(f"OK: Rush of Dread emitted {len(discards)} DISCARD events for opponent")


# ---------------------------------------------------------------------------
# 3. SHIFTING_GRIFT — exchange control of one permanent each
# ---------------------------------------------------------------------------


def test_shifting_grift_exchanges_control():
    """Each player chooses one permanent; control exchanges."""
    print("\n=== Test: Shifting Grift exchanges control ===")
    game, p1, p2 = make_two_player_game()
    my_perm = make_bear(game, p1.id, name="My Bear")
    opp_perm = make_bear(game, p2.id, name="Opp Bear")
    spell = make_spell(game, p1.id, otj.SHIFTING_GRIFT)
    add_mana(game, p1.id, "U", 2)
    cast_spell(game, p1.id, spell)
    # Sorcery resolves: opens caster's pick.
    events_resolve = game.stack.resolve_top()
    caster_choice = game.state.pending_choice
    assert caster_choice is not None, "expected caster pick prompt"
    assert caster_choice.player == p1.id
    assert caster_choice.choice_type == "shifting_grift_caster_pick"

    # P1 picks their permanent.
    ok, msg, after_caster = game.submit_choice(caster_choice.id, p1.id, [my_perm.id])
    assert ok, msg

    opp_choice = game.state.pending_choice
    assert opp_choice is not None, "expected opponent pick prompt"
    assert opp_choice.player == p2.id
    assert opp_choice.choice_type == "shifting_grift_opp_pick"

    ok, msg, events = game.submit_choice(opp_choice.id, p2.id, [opp_perm.id])
    assert ok, msg

    gain_events = [e for e in events if e.type == EventType.GAIN_CONTROL]
    assert len(gain_events) == 2, \
        f"expected 2 GAIN_CONTROL events; got {[e.payload for e in gain_events]}"
    payloads = {(e.payload.get('object_id'), e.payload.get('new_controller'))
                for e in gain_events}
    assert (my_perm.id, p2.id) in payloads, \
        f"expected my_perm -> p2 swap; got {payloads}"
    assert (opp_perm.id, p1.id) in payloads, \
        f"expected opp_perm -> p1 swap; got {payloads}"
    print("OK: Shifting Grift emitted both GAIN_CONTROL exchanges")


def test_shifting_grift_aborts_when_no_permanents():
    """Opponent has nothing → cast resolves gracefully (no crash)."""
    print("\n=== Test: Shifting Grift aborts when opponent has no permanents ===")
    game, p1, p2 = make_two_player_game()
    # P1 has a permanent; P2 has nothing.
    make_bear(game, p1.id, name="My Bear")
    spell = make_spell(game, p1.id, otj.SHIFTING_GRIFT)
    add_mana(game, p1.id, "U", 2)
    cast_spell(game, p1.id, spell)
    events = game.stack.resolve_top()
    # No pending choice should be set; resolve was a no-op.
    assert game.state.pending_choice is None, \
        f"no pending choice expected; got {game.state.pending_choice}"
    gain_events = [e for e in events if e.type == EventType.GAIN_CONTROL]
    assert not gain_events, f"expected no exchanges; got {gain_events}"
    print("OK: Shifting Grift aborts gracefully when opponent has no permanents")


def test_shifting_grift_aborts_when_caster_has_no_permanents():
    """Caster has nothing → cast resolves gracefully (no crash)."""
    print("\n=== Test: Shifting Grift aborts when caster has no permanents ===")
    game, p1, p2 = make_two_player_game()
    make_bear(game, p2.id, name="Opp Bear")
    spell = make_spell(game, p1.id, otj.SHIFTING_GRIFT)
    add_mana(game, p1.id, "U", 2)
    cast_spell(game, p1.id, spell)
    events = game.stack.resolve_top()
    assert game.state.pending_choice is None
    gain_events = [e for e in events if e.type == EventType.GAIN_CONTROL]
    assert not gain_events
    print("OK: Shifting Grift aborts when caster has no permanents")


# ---------------------------------------------------------------------------
# 4. CENTRAL_ELEVATOR door 1 — tutor for a Room with a non-collision name
# ---------------------------------------------------------------------------


def _spawn_room_on_battlefield(game, player, card_def):
    """Spawn ``card_def`` in HAND then emit ZONE_CHANGE so the ETB pipeline
    fires (matches src/engine/pipeline path that runs setup_interceptors on
    battlefield entry, which is what unlocks Door 1).
    """
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


def test_central_elevator_door1_searches_for_non_collision_room():
    """Control a Room named X; library has Rooms named X, Y, Z; only Y and Z
    legal in the prompt."""
    print("\n=== Test: Central Elevator door 1 non-collision tutor ===")
    game, p1, _p2 = make_two_player_game()

    # Put a Room named "X" on the battlefield, controlled by p1.
    x_def = make_room_def("X")
    x_room = game.create_object(
        name="X", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=x_def.characteristics, card_def=x_def,
    )

    # Library: a colliding Room (X), and two non-colliders (Y, Z), plus a
    # non-Room "Junk".
    lib_cards = []
    for name in ("X", "Y", "Z"):
        rdef = make_room_def(name)
        lib_cards.append(make_card_in_library(game, p1.id, rdef))
    junk_def = make_creature(
        name="Junk", power=1, toughness=1, mana_cost="{1}", colors=set(),
    )
    lib_cards.append(make_card_in_library(game, p1.id, junk_def))

    # Spawn Central Elevator via HAND → BATTLEFIELD ZONE_CHANGE so the
    # ETB-unlock-door-1 chain runs.
    elev = _spawn_room_on_battlefield(game, p1, dsk.CENTRAL_ELEVATOR)

    pc = game.state.pending_choice
    assert pc is not None, \
        "expected library_search PendingChoice after door 1 unlock"
    assert pc.choice_type == "library_search"
    # Options should be Y and Z only; X is excluded (collides), Junk is
    # excluded (not a Room).
    option_ids = set(pc.options)
    legal_names = {state_obj.name for state_obj in
                   (game.state.objects.get(oid) for oid in option_ids)
                   if state_obj is not None}
    assert legal_names == {"Y", "Z"}, \
        f"expected only non-collision Rooms (Y, Z); got {legal_names}"
    print(f"OK: Central Elevator door 1 prompt offered {legal_names}")


def test_central_elevator_door1_aborts_when_all_collide():
    """Control all Room names; prompt has zero options (search yields
    nothing)."""
    print("\n=== Test: Central Elevator door 1 with all collisions ===")
    game, p1, _p2 = make_two_player_game()

    # Battlefield: Rooms named X, Y, Z all under p1's control.
    for name in ("X", "Y", "Z"):
        rdef = make_room_def(name)
        game.create_object(
            name=name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=rdef.characteristics, card_def=rdef,
        )

    # Library: only X, Y, Z (all collide).
    for name in ("X", "Y", "Z"):
        rdef = make_room_def(name)
        make_card_in_library(game, p1.id, rdef)

    # Spawn Central Elevator via HAND → BATTLEFIELD ZONE_CHANGE so door 1
    # fires its tutor effect.
    _spawn_room_on_battlefield(game, p1, dsk.CENTRAL_ELEVATOR)

    # Since the tutor is optional and zero candidates exist, the helper
    # gracefully no-ops (no PendingChoice opened) and merely shuffles.
    assert game.state.pending_choice is None, \
        f"expected no choice (all collisions); got {game.state.pending_choice}"
    print("OK: Central Elevator door 1 yielded zero options when all collide")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    tests = [
        test_rush_of_dread_sac_mode_opens_opponent_prompt,
        test_rush_of_dread_sac_destroys_half_rounded_up,
        test_rush_of_dread_sac_no_creatures_noop,
        test_rush_of_dread_discard_mode,
        test_shifting_grift_exchanges_control,
        test_shifting_grift_aborts_when_no_permanents,
        test_shifting_grift_aborts_when_caster_has_no_permanents,
        test_central_elevator_door1_searches_for_non_collision_room,
        test_central_elevator_door1_aborts_when_all_collide,
    ]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        print("\nFailures:")
        for name, msg in failed:
            print(f"  {name}: {msg}")
        sys.exit(1)
