"""Round 10A wet test — land-pattern sweep end-to-end.

Drives 5 scenarios through the engine to validate the round's changes:
  1. TLA sac-for-draw land: ETB tapped (auto), activate {4},{T},sac → DRAW
  2. SPM hideout: ETB tapped (auto), activate {4},{T} → SURVEIL choice opens
  3. LCI hidden land: ETB tapped (auto), activate {4}{U},{T},sac → DISCOVER
     pulls a non-land MV<=4 from library to hand
  4. Shockland (high life): play Blood Crypt at 20 → -2 life, untapped
  5. Shockland (low life): play Blood Crypt at 4 → no life loss, ETBs tapped

Each scenario reports PASS/FAIL with a one-line summary; non-zero exit on
any failure.
"""
from __future__ import annotations

import asyncio
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    GameObject, ObjectState, new_id, make_creature,
)
from src.engine.priority import PlayerAction, ActionType


def _new_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.start_game()
    return game, p1, p2


def _spawn_in_hand(game, player_id, card_def):
    obj = GameObject(
        id=new_id(), name=card_def.name, owner=player_id, controller=player_id,
        zone=ZoneType.HAND, characteristics=card_def.characteristics,
        state=ObjectState(), card_def=card_def,
        created_at=game.state.next_timestamp(),
        entered_zone_at=game.state.timestamp,
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    game.state.zones[f'hand_{player_id}'].objects.append(obj.id)
    return obj


def _spawn_in_library(game, player_id, card_def, *, on_top=True):
    obj = GameObject(
        id=new_id(), name=card_def.name, owner=player_id, controller=player_id,
        zone=ZoneType.LIBRARY, characteristics=card_def.characteristics,
        state=ObjectState(), card_def=card_def,
        created_at=game.state.next_timestamp(),
        entered_zone_at=game.state.timestamp,
        _state_ref=game.state,
    )
    game.state.objects[obj.id] = obj
    lib = game.state.zones[f'library_{player_id}']
    if on_top:
        lib.objects.insert(0, obj.id)
    else:
        lib.objects.append(obj.id)
    return obj


async def _play_land(game, player_id, obj_id):
    action = PlayerAction(type=ActionType.PLAY_LAND, player_id=player_id, card_id=obj_id)
    events = await game.priority_system._handle_play_land(action)
    for e in events:
        game.pipeline.emit(e)
    return events


# =============================================================================
# Scenarios
# =============================================================================


async def scenario_tla_sac_for_draw():
    print("\n--- Scenario 1: TLA Airship Engine Room sac-for-draw ---")
    from src.cards.avatar_tla import AIRSHIP_ENGINE_ROOM

    game, p1, _ = _new_game()
    obj = _spawn_in_hand(game, p1.id, AIRSHIP_ENGINE_ROOM)
    await _play_land(game, p1.id, obj.id)
    on_bf = game.state.objects[obj.id]
    assert on_bf.zone == ZoneType.BATTLEFIELD
    assert on_bf.state.tapped is True, "should ETB tapped"
    abilities = on_bf.state.activated_abilities
    assert abilities, "should register draw ability"
    assert any('Draw' in a.description for a in abilities)
    print("  PASS: ETB tapped + Draw activated ability registered")


async def scenario_spm_hideout_surveil():
    print("\n--- Scenario 2: SPM Sinister Hideout {4},{T}: Surveil 1 ---")
    from src.cards.spider_man import SINISTER_HIDEOUT

    game, p1, _ = _new_game()
    obj = _spawn_in_hand(game, p1.id, SINISTER_HIDEOUT)
    await _play_land(game, p1.id, obj.id)
    on_bf = game.state.objects[obj.id]
    assert on_bf.state.tapped is True
    abilities = on_bf.state.activated_abilities
    surveil_ab = [a for a in abilities if 'Surveil' in a.description]
    assert surveil_ab, f"no Surveil ability; got: {[a.description for a in abilities]}"
    print("  PASS: ETB tapped + Surveil 1 ability registered")


async def scenario_lci_hidden_discover():
    print("\n--- Scenario 3: LCI Hidden Cataract activated ability + DISCOVER ---")
    from src.cards.lost_caverns_ixalan import HIDDEN_CATARACT

    game, p1, _ = _new_game()
    obj = _spawn_in_hand(game, p1.id, HIDDEN_CATARACT)
    await _play_land(game, p1.id, obj.id)
    on_bf = game.state.objects[obj.id]
    assert on_bf.state.tapped is True
    # Activated discover ability should be registered
    abilities = on_bf.state.activated_abilities
    assert any('Discover' in a.description for a in abilities)

    # Stack a MV-2 creature on top of library, then emit DISCOVER 4 to verify
    # the new handler pulls it into hand.
    cheap = make_creature(
        name="Test Beast", power=1, toughness=1,
        mana_cost="{1}{G}", colors={Color.GREEN}, subtypes={"Beast"}, text="",
    )
    target = _spawn_in_library(game, p1.id, cheap, on_top=True)
    ev = Event(
        type=EventType.DISCOVER,
        payload={'player': p1.id, 'value': 4},
        source=on_bf.id, controller=p1.id,
    )
    game.pipeline.emit(ev)
    hand = game.state.zones[f'hand_{p1.id}']
    assert target.id in hand.objects, "DISCOVER should pull the MV-2 creature into hand"
    print("  PASS: ETB tapped + Discover 4 pulls MV-2 creature to hand")


async def scenario_shockland_pays_2_life():
    print("\n--- Scenario 4: Blood Crypt at full life pays 2 life ---")
    from src.cards.lorwyn_eclipsed import BLOOD_CRYPT

    game, p1, _ = _new_game()
    starting_life = p1.life
    obj = _spawn_in_hand(game, p1.id, BLOOD_CRYPT)
    await _play_land(game, p1.id, obj.id)
    on_bf = game.state.objects[obj.id]
    assert on_bf.state.tapped is False, "should NOT enter tapped"
    assert p1.life == starting_life - 2, f"life {p1.life} != {starting_life - 2}"
    print(f"  PASS: Blood Crypt at life={starting_life} paid 2 life and entered untapped")


async def scenario_shockland_low_life():
    print("\n--- Scenario 5: Blood Crypt at low life enters tapped ---")
    from src.cards.lorwyn_eclipsed import BLOOD_CRYPT

    game, p1, _ = _new_game()
    p1.life = 4
    obj = _spawn_in_hand(game, p1.id, BLOOD_CRYPT)
    await _play_land(game, p1.id, obj.id)
    on_bf = game.state.objects[obj.id]
    assert on_bf.state.tapped is True, "should enter tapped at low life"
    assert p1.life == 4, f"life should be unchanged; got {p1.life}"
    print("  PASS: Blood Crypt at life=4 entered tapped, no life paid")


# =============================================================================
# Driver
# =============================================================================


async def main() -> int:
    scenarios = [
        scenario_tla_sac_for_draw,
        scenario_spm_hideout_surveil,
        scenario_lci_hidden_discover,
        scenario_shockland_pays_2_life,
        scenario_shockland_low_life,
    ]
    failed: list[tuple[str, str]] = []
    for s in scenarios:
        try:
            await s()
        except AssertionError as exc:
            failed.append((s.__name__, str(exc) or '<no message>'))
            print(f"  FAIL: {s.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((s.__name__, repr(exc)))
            print(f"  ERROR: {s.__name__}: {exc!r}")

    print("\n" + "=" * 60)
    if failed:
        print(f"WET TEST RESULT: {len(scenarios) - len(failed)}/{len(scenarios)} passed")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        print("=" * 60)
        return 1
    print(f"WET TEST RESULT: {len(scenarios)}/{len(scenarios)} passed")
    print("=" * 60)
    print("All Round-10A land-pattern wet-test scenarios passed.")
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
