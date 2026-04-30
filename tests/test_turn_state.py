"""
Tests for the turn-state primitive trackers and the COIN_FLIP primitive.

Covers:
  * LIFE_CHANGE -> life_gained_<player>, life_lost_<player>
  * CAST/SPELL_CAST -> spells_cast_<player>, nth_spell_this_turn
  * ATTACK_DECLARED / COMBAT_DECLARED -> attacked_alone_<player>
  * OBJECT_DESTROYED + ZONE_CHANGE -> creatures_died_this_turn (deduped)
  * DAMAGE with target=player + is_combat -> combat_damage_to_<player>
  * DRAW -> cards_drawn_<player>
  * TURN_END clears turn_data
  * flip_coin determinism with state.rng_seed
  * COIN_FLIP events traverse the pipeline cleanly
"""

import os
import sys

# Put the project root (two levels up from this file) at the front of sys.path
# so we import the source tree this test actually lives in (worktree-friendly).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio
import pytest

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    GameObject, ObjectState, new_id,
)
from src.engine.turn_state import (
    life_gained_this_turn,
    life_lost_this_turn,
    spells_cast_this_turn,
    nth_spell_this_turn,
    attacked_alone_this_turn,
    creatures_died_this_turn,
    cards_drawn_this_turn,
    combat_damage_dealt_to_this_turn,
    flip_coin,
    emit_coin_flip,
    register_turn_state_tracker,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_game_with_two_players():
    g = Game(mode="mtg")
    p1 = g.add_player("Alice", life=20)
    p2 = g.add_player("Bob", life=20)
    return g, p1, p2


def _put_creature_on_battlefield(game, controller_id, name="Bear", power=2, toughness=2):
    """Drop a vanilla creature directly on the battlefield (no ETB triggers)."""
    obj = game.create_object(
        name=name,
        owner_id=controller_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness,
        ),
    )
    return obj


# =============================================================================
# LIFE_CHANGE tracking
# =============================================================================

def test_life_gained_tracker():
    g, p1, _ = _make_game_with_two_players()
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={"player": p1.id, "amount": 3}))
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={"player": p1.id, "amount": 5}))
    assert life_gained_this_turn(p1.id, g.state) == 8
    assert life_lost_this_turn(p1.id, g.state) == 0
    assert p1.life == 28


def test_life_lost_tracker():
    g, p1, _ = _make_game_with_two_players()
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={"player": p1.id, "amount": -4}))
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={"player": p1.id, "amount": -1}))
    assert life_lost_this_turn(p1.id, g.state) == 5
    assert life_gained_this_turn(p1.id, g.state) == 0
    assert p1.life == 15


def test_life_trackers_are_per_player():
    g, p1, p2 = _make_game_with_two_players()
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={"player": p1.id, "amount": 7}))
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={"player": p2.id, "amount": -3}))
    assert life_gained_this_turn(p1.id, g.state) == 7
    assert life_gained_this_turn(p2.id, g.state) == 0
    assert life_lost_this_turn(p2.id, g.state) == 3


# =============================================================================
# CAST tracking + nth-spell helper
# =============================================================================

def test_spells_cast_tracker():
    g, p1, _ = _make_game_with_two_players()
    for _ in range(3):
        g.emit(Event(type=EventType.CAST, payload={"caster": p1.id}))
    assert spells_cast_this_turn(p1.id, g.state) == 3


def test_spell_cast_alias_counts():
    g, p1, _ = _make_game_with_two_players()
    g.emit(Event(type=EventType.SPELL_CAST, payload={"caster": p1.id}))
    g.emit(Event(type=EventType.CAST, payload={"caster": p1.id}))
    assert spells_cast_this_turn(p1.id, g.state) == 2


def test_nth_spell_helper():
    g, p1, _ = _make_game_with_two_players()
    g.emit(Event(type=EventType.CAST, payload={"caster": p1.id}))
    assert nth_spell_this_turn(p1.id, 1, g.state) is True
    assert nth_spell_this_turn(p1.id, 2, g.state) is False
    g.emit(Event(type=EventType.CAST, payload={"caster": p1.id}))
    assert nth_spell_this_turn(p1.id, 2, g.state) is True


# =============================================================================
# Attack tracking — "attacks alone"
# =============================================================================

def test_attacks_alone_via_combat_declared():
    g, p1, p2 = _make_game_with_two_players()
    bear = _put_creature_on_battlefield(g, p1.id, name="Bear")
    # Simulate the consolidated event combat manager fires.
    g.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={"attacking_player": p1.id, "attackers": [bear.id]},
    ))
    assert attacked_alone_this_turn(p1.id, g.state) is True
    assert attacked_alone_this_turn(p2.id, g.state) is False


def test_attacks_not_alone_via_combat_declared():
    g, p1, _ = _make_game_with_two_players()
    bear = _put_creature_on_battlefield(g, p1.id, name="Bear")
    elk = _put_creature_on_battlefield(g, p1.id, name="Elk")
    g.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={"attacking_player": p1.id, "attackers": [bear.id, elk.id]},
    ))
    assert attacked_alone_this_turn(p1.id, g.state) is False


def test_attacks_alone_via_per_attacker_path():
    """If only ATTACK_DECLARED events fire (no consolidated COMBAT_DECLARED),
    the tracker still notices attack count == 1."""
    g, p1, _ = _make_game_with_two_players()
    bear = _put_creature_on_battlefield(g, p1.id, name="Bear")
    g.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": bear.id, "attacking_player": p1.id},
    ))
    assert attacked_alone_this_turn(p1.id, g.state) is True


# =============================================================================
# Creature death tracking (Morbid)
# =============================================================================

def test_creatures_died_via_object_destroyed():
    g, p1, p2 = _make_game_with_two_players()
    bear = _put_creature_on_battlefield(g, p1.id, name="Bear")
    g.emit(Event(type=EventType.OBJECT_DESTROYED,
                 payload={"object_id": bear.id}))
    assert creatures_died_this_turn(g.state) >= 1
    assert creatures_died_this_turn(g.state, p1.id) >= 1
    assert creatures_died_this_turn(g.state, p2.id) == 0


def test_creatures_died_dedupes_zone_change_and_destroyed():
    """Some flows emit BOTH OBJECT_DESTROYED and ZONE_CHANGE for the same death.
    The tracker should count once, not twice."""
    g, p1, _ = _make_game_with_two_players()
    bear = _put_creature_on_battlefield(g, p1.id, name="Bear")
    g.emit(Event(type=EventType.OBJECT_DESTROYED,
                 payload={"object_id": bear.id}))
    # OBJECT_DESTROYED handler routes to graveyard; emitting a follow-up
    # ZONE_CHANGE should not double-count.
    g.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": bear.id,
            "from_zone_type": ZoneType.BATTLEFIELD,
            "to_zone_type": ZoneType.GRAVEYARD,
        },
    ))
    assert creatures_died_this_turn(g.state) == 1


# =============================================================================
# Combat damage tracking
# =============================================================================

def test_combat_damage_to_player_tracker():
    g, p1, p2 = _make_game_with_two_players()
    g.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": p2.id, "amount": 3, "is_combat": True, "source": "x"},
    ))
    g.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": p2.id, "amount": 2, "is_combat": True, "source": "x"},
    ))
    assert combat_damage_dealt_to_this_turn(p2.id, g.state) == 5
    assert combat_damage_dealt_to_this_turn(p1.id, g.state) == 0


def test_noncombat_damage_excluded():
    g, _p1, p2 = _make_game_with_two_players()
    g.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": p2.id, "amount": 4, "is_combat": False},
    ))
    assert combat_damage_dealt_to_this_turn(p2.id, g.state) == 0


# =============================================================================
# Cards drawn tracking
# =============================================================================

def test_cards_drawn_tracker():
    g, p1, _ = _make_game_with_two_players()
    # Library is empty; we don't care about the actual draw side-effect, only
    # that the tracker reads the event payload.
    g.emit(Event(type=EventType.DRAW,
                 payload={"player": p1.id, "amount": 2}))
    g.emit(Event(type=EventType.DRAW,
                 payload={"player": p1.id, "count": 1}))
    assert cards_drawn_this_turn(p1.id, g.state) == 3


# =============================================================================
# Turn-end clears turn_data
# =============================================================================

def test_turn_end_clears_trackers():
    g, p1, _ = _make_game_with_two_players()
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={"player": p1.id, "amount": 5}))
    g.emit(Event(type=EventType.CAST, payload={"caster": p1.id}))
    assert life_gained_this_turn(p1.id, g.state) == 5
    assert spells_cast_this_turn(p1.id, g.state) == 1

    # Run the turn-end clear path.
    asyncio.get_event_loop().run_until_complete(
        g.turn_manager._emit_turn_end()
    )
    assert life_gained_this_turn(p1.id, g.state) == 0
    assert spells_cast_this_turn(p1.id, g.state) == 0


# =============================================================================
# Coin flip determinism
# =============================================================================

def test_flip_coin_determinism_with_seed():
    g1 = Game(mode="mtg")
    g1.state.rng_seed = 12345
    g2 = Game(mode="mtg")
    g2.state.rng_seed = 12345
    seq1 = [flip_coin(g1.state) for _ in range(20)]
    seq2 = [flip_coin(g2.state) for _ in range(20)]
    assert seq1 == seq2, "Same seed must produce identical flip sequences"
    # Sanity: not all the same value.
    assert len(set(seq1)) == 2


def test_flip_coin_returns_bool():
    g = Game(mode="mtg")
    g.state.rng_seed = 42
    result = flip_coin(g.state)
    assert isinstance(result, bool)


def test_emit_coin_flip_event():
    g, p1, _ = _make_game_with_two_players()
    g.state.rng_seed = 7
    ev = emit_coin_flip(g.state, player_id=p1.id, source="x")
    assert ev.type == EventType.COIN_FLIP
    assert ev.payload["result"] in (True, False)
    assert ev.payload["player"] == p1.id


def test_coin_flip_event_traverses_pipeline():
    """Emitting a COIN_FLIP event should not raise and should be observed."""
    g, p1, _ = _make_game_with_two_players()
    g.state.rng_seed = 1

    observed = []

    def filt(event, state):
        return event.type == EventType.COIN_FLIP

    def handler(event, state):
        observed.append(event.payload.get("result"))
        from src.engine import InterceptorAction, InterceptorResult
        return InterceptorResult(action=InterceptorAction.PASS)

    from src.engine import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    )
    g.register_interceptor(Interceptor(
        id=new_id(),
        source="TEST",
        controller="TEST",
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="forever",
    ))
    g.emit(emit_coin_flip(g.state, player_id=p1.id))
    assert len(observed) == 1
    assert observed[0] in (True, False)


# =============================================================================
# Test runner — direct invocation
# =============================================================================

def _run_all():
    tests = [
        test_life_gained_tracker,
        test_life_lost_tracker,
        test_life_trackers_are_per_player,
        test_spells_cast_tracker,
        test_spell_cast_alias_counts,
        test_nth_spell_helper,
        test_attacks_alone_via_combat_declared,
        test_attacks_not_alone_via_combat_declared,
        test_attacks_alone_via_per_attacker_path,
        test_creatures_died_via_object_destroyed,
        test_creatures_died_dedupes_zone_change_and_destroyed,
        test_combat_damage_to_player_tracker,
        test_noncombat_damage_excluded,
        test_cards_drawn_tracker,
        test_turn_end_clears_trackers,
        test_flip_coin_determinism_with_seed,
        test_flip_coin_returns_bool,
        test_emit_coin_flip_event,
        test_coin_flip_event_traverses_pipeline,
    ]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
            print(f"OK  {t.__name__}")
        except Exception as exc:
            failed.append((t.__name__, exc))
            print(f"FAIL  {t.__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} tests passed")
    if failed:
        for name, exc in failed:
            print(f"  - {name}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
