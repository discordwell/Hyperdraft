"""Summoning sickness is enforced via the per-turn baseline `turn_start_timestamp`.

Bug (found in the a7c32e7e code-review): combat.py's `_can_attack` compared
`entered_zone_at` against the LIVE `state.timestamp`, which bumps on every event
after a creature enters — so a creature read as sick for only a tick and could
then attack the turn it was cast. The turn manager now stamps
`state.turn_start_timestamp = next_timestamp()` at turn-begin, and a creature is
summoning sick iff `entered_zone_at >= turn_start_timestamp` (it entered at/after
this turn began). When no turn has run (turn_start_timestamp == 0) combat falls
back to the legacy `entered == timestamp` probe so direct-combat unit harnesses
keep working.
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import Game, ZoneType, Color, make_creature
from src.ai.evaluator import BoardEvaluator


def _new_game(*names):
    game = Game()
    pids = []
    for n in names:
        pids.append(game.add_player(n).id)
    game.turn_manager.set_turn_order(pids)
    game.state.active_player = pids[0]
    return (game, *pids)


def _spawn_creature(game, controller, name, *, power=2, toughness=2, tapped=False):
    cd = make_creature(name=name, power=power, toughness=toughness,
                       mana_cost="{1}{G}", colors={Color.GREEN}, subtypes={"Survivor"})
    obj = game.create_object(name=cd.name, owner_id=controller,
                             zone=ZoneType.BATTLEFIELD,
                             characteristics=cd.characteristics, card_def=cd)
    obj.controller = controller
    obj.state.tapped = tapped
    return obj


def _run_turn(game, player_id):
    return asyncio.run(game.turn_manager.run_turn(player_id))


# --------------------------------------------------------------------------- #
# combat._can_attack — the core sickness gate
# --------------------------------------------------------------------------- #
def test_can_attack_enforces_turn_start_sickness():
    game, p1, p2 = _new_game("A", "B")
    cm = game.combat_manager
    game.state.turn_start_timestamp = 100  # this turn began at ts=100

    est = _spawn_creature(game, p1, "Established")
    est.entered_zone_at = 50  # entered a PRIOR turn
    assert cm._can_attack(est.id, p1) is True, "established creature may attack"

    fresh = _spawn_creature(game, p1, "Fresh")
    fresh.entered_zone_at = 105  # entered AFTER this turn began
    assert cm._can_attack(fresh.id, p1) is False, "creature cast this turn is summoning sick"

    fresh.entered_zone_at = 100  # entered exactly at the baseline -> still "this turn"
    assert cm._can_attack(fresh.id, p1) is False, "entered == baseline counts as this turn"
    print("PASS: combat enforces summoning sickness via turn_start_timestamp")


def test_can_attack_legacy_fallback_when_no_turn_has_run():
    # turn_start_timestamp == 0 (no turn loop) -> legacy entered==timestamp probe,
    # so direct-combat harnesses that never call run_turn behave as before.
    game, p1, p2 = _new_game("A", "B")
    cm = game.combat_manager
    game.state.turn_start_timestamp = 0
    c = _spawn_creature(game, p1, "C")
    game.state.timestamp = 200
    c.entered_zone_at = 200
    assert cm._can_attack(c.id, p1) is False, "legacy: entered==live timestamp -> sick"
    c.entered_zone_at = 150
    assert cm._can_attack(c.id, p1) is True, "legacy: entered!=live timestamp -> established"
    print("PASS: legacy fallback preserved when no turn has run")


def test_haste_overrides_summoning_sickness():
    game, p1, p2 = _new_game("A", "B")
    cm = game.combat_manager
    game.state.turn_start_timestamp = 100
    c = _spawn_creature(game, p1, "Hasty")
    c.entered_zone_at = 105  # entered this turn -> sick...
    assert cm._can_attack(c.id, p1) is False
    c.characteristics.abilities.append({'keyword': 'haste'})
    assert cm._can_attack(c.id, p1) is True, "haste lets a fresh creature attack"
    print("PASS: haste overrides summoning sickness")


# --------------------------------------------------------------------------- #
# Integration: run_turn stamps the baseline; combat consumes it
# --------------------------------------------------------------------------- #
def test_run_turn_stamps_baseline_and_blocks_post_baseline_creature():
    game, p1, p2 = _new_game("A", "B")
    cm = game.combat_manager
    est = _spawn_creature(game, p1, "Established")
    est_entered = est.entered_zone_at

    _run_turn(game, p1)  # turn.py stamps turn_start_timestamp at turn-begin

    ts = game.state.turn_start_timestamp
    assert ts > est_entered, \
        f"baseline ({ts}) must exceed a pre-existing creature's entry ({est_entered})"
    # the established creature entered before the baseline -> may attack
    assert cm._can_attack(est.id, p1) is True
    # a creature entering AFTER the baseline (as if cast this turn) is sick
    fresh = _spawn_creature(game, p1, "Fresh")
    assert fresh.entered_zone_at > ts
    assert cm._can_attack(fresh.id, p1) is False
    print("PASS: run_turn stamps the baseline; post-baseline creatures are sick")


# --------------------------------------------------------------------------- #
# Evaluator mirrors combat on the turn_start path
# --------------------------------------------------------------------------- #
def test_evaluator_can_attack_now_mirrors_turn_start():
    game, p1, p2 = _new_game("A", "B")
    ev = BoardEvaluator(game.state)
    game.state.turn_start_timestamp = 100
    c = _spawn_creature(game, p1, "C")
    c.entered_zone_at = 50
    assert ev._can_attack_now(c) is True, "established -> attack-eligible in valuation"
    c.entered_zone_at = 105
    assert ev._can_attack_now(c) is False, "sick this turn -> not an attacker"
    c.characteristics.abilities.append({'keyword': 'haste'})
    assert ev._can_attack_now(c) is True, "haste overrides in valuation too"
    print("PASS: evaluator._can_attack_now mirrors combat on the turn_start path")


if __name__ == "__main__":
    test_can_attack_enforces_turn_start_sickness()
    test_can_attack_legacy_fallback_when_no_turn_has_run()
    test_haste_overrides_summoning_sickness()
    test_run_turn_stamps_baseline_and_blocks_post_baseline_creature()
    test_evaluator_can_attack_now_mirrors_turn_start()
    print("\nAll summoning-sickness tests passed.")
