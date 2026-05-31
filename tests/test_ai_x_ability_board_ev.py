"""Board-aware valuation + optimal-X selection for X-cost activated abilities.

Review follow-up #2 (broader board-EV): the AI's action scorer
(``AIEngine._score_x_ability``, wired into ``_score_action_candidate``)
re-values each X-cost activated ability by its board impact and overrides
``action.x_value`` with the board-optimal X, instead of firing at a blind
max-affordable X with no board awareness. One archetype valuator per class:
board-pump, self-pump, damage, debuff, draw, copy-graveyard, copy-ability.

priority.py bakes ``action.x_value`` = max affordable X; these tests feed that
in and assert the scorer picks the right X and a sensible value (~0 = no board
benefit / don't fire; >=6 = lethal/dominant).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine import (
    Game, ZoneType, Color, CardType, make_creature,
)
from src.engine.priority import LegalAction, ActionType
from src.engine.turn import Phase
from src.ai.engine import AIEngine
from src.ai.evaluator import BoardEvaluator

_MIRROR_DESC = "creatures you control have base power and toughness x/x and gain all creature types"


def _ai():
    return AIEngine(difficulty='medium')


def _ev(game):
    return BoardEvaluator(game.state)


def _x_action(desc, x_value=5, source_id=None):
    return LegalAction(
        type=ActionType.ACTIVATE_ABILITY,
        source_id=source_id,
        ability_id="activated:0",
        description=desc,
        x_value=x_value,
    )


def _bf_creature(game, owner, name, power, tough, *, sick=False, cost="{1}"):
    cd = make_creature(name=name, power=power, toughness=tough, mana_cost=cost,
                       colors={Color.RED}, subtypes={"Goblin"})
    obj = game.create_object(name=name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
                             characteristics=cd.characteristics, card_def=cd)
    obj.card_def = cd
    obj.state.summoning_sickness = sick
    # Attack-eligibility mirrors combat.py / evaluator._can_attack_now, which key
    # off `entered_zone_at == state.timestamp` (NOT the summoning_sickness flag,
    # which the MTG turn manager never clears). Set it explicitly so sickness is
    # deterministic and independent of object-creation order (each create_object
    # bumps the timestamp, so a literal "== timestamp" would drift stale as more
    # creatures are added): -1 can never equal a real (>=0) timestamp, so an
    # established creature stays attack-ready; a sick creature clears
    # entered_zone_at so _can_attack_now falls back to the (True) flag.
    obj.entered_zone_at = None if sick else -1
    return obj


def _gy_creature(game, owner, name, power, tough, cost):
    cd = make_creature(name=name, power=power, toughness=tough, mana_cost=cost,
                       colors={Color.GREEN}, subtypes={"Bear"})
    game.create_object(name=name, owner_id=owner.id, zone=ZoneType.GRAVEYARD,
                       characteristics=cd.characteristics, card_def=cd)


# --------------------------------------------------------------------------- #
# Root-cause regression: summoning-sickness signal the evaluator trusts
# --------------------------------------------------------------------------- #
def test_can_attack_now_keys_off_timestamp_not_stale_flag():
    """Regression for the stale-summoning_sickness bug that made board-EV inert.

    evaluator._can_attack_now must mirror combat.py's AUTHORITATIVE sickness
    check (``entered_zone_at == state.timestamp``), NOT the per-object
    ``summoning_sickness`` flag — which the MTG turn manager never clears, so it
    is stale (always True) and silently blanked every attack-based valuation
    (lethal detection, attack/evasive pressure, blocker coverage, and the
    X-ability board-pump EV: my_attackers() came back empty 459/459 times in a
    6-game self-play probe, so board_pump always scored 0.0)."""
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    ev = BoardEvaluator(game.state)
    c = _bf_creature(game, p1, "C", 2, 2)
    game.state.timestamp = 100

    # (1) THE BUG GUARD: entered on a PRIOR timestamp => established => CAN
    #     attack, even though the stale always-True flag claims "sick".
    c.entered_zone_at = 99
    c.state.summoning_sickness = True
    assert ev._can_attack_now(c) is True

    # (2) entered THIS timestamp => genuinely summoning sick => CANNOT attack
    #     (flag says "not sick" here, proving the flag is not what's consulted).
    c.entered_zone_at = 100
    c.state.summoning_sickness = False
    assert ev._can_attack_now(c) is False

    # (3) haste beats summoning sickness.
    c.characteristics.abilities.append({'keyword': 'haste'})
    assert ev._can_attack_now(c) is True
    c.characteristics.abilities.pop()

    # (4) tapped always short-circuits.
    c.entered_zone_at = 99
    c.state.tapped = True
    assert ev._can_attack_now(c) is False
    c.state.tapped = False

    # (5) fallback: when entered_zone_at is unavailable, trust the flag.
    c.entered_zone_at = None
    c.state.summoning_sickness = True
    assert ev._can_attack_now(c) is False
    c.state.summoning_sickness = False
    assert ev._can_attack_now(c) is True
    print("PASS: _can_attack_now keys off entered_zone_at==timestamp, not the stale flag")


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #
def test_classifier_covers_all_archetypes():
    ai = _ai()
    assert ai._classify_x_ability(_MIRROR_DESC) == "board_pump"
    assert ai._classify_x_ability("draw x cards") == "draw"
    assert ai._classify_x_ability("deals x damage to any target") == "damage"
    assert ai._classify_x_ability("each other nonartifact creature gets -x/-x") == "debuff"
    assert ai._classify_x_ability(
        "becomes a copy of target creature card in your graveyard with mana value x") == "copy_gy"
    assert ai._classify_x_ability(
        "copy target activated or triggered ability you control x times") == "copy_ability"
    assert ai._classify_x_ability("this creature gets +x/+x until end of turn") == "self_pump"
    print("PASS: classifier covers all 7 archetypes")


# --------------------------------------------------------------------------- #
# Board-wide pump (Mirror Entity)
# --------------------------------------------------------------------------- #
def test_board_pump_finds_lethal_at_minimal_x():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 3
    for i in range(3):
        _bf_creature(game, p1, f"G{i}", 1, 1)
    val, x = _ai()._score_x_ability(_x_action(_MIRROR_DESC, 5), game.state, _ev(game), p1.id)
    assert val >= 6.0, f"lethal pump should be dominant value, got {val}"
    assert x == 1, f"3 creatures at X/X reach 3 life at X=1 (minimal lethal), got {x}"
    print("PASS: board_pump finds lethal at the minimal X")


def test_board_pump_zero_without_attackers():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 20
    for i in range(3):
        _bf_creature(game, p1, f"G{i}", 1, 1, sick=True)  # summoning sick -> can't attack
    val, x = _ai()._score_x_ability(_x_action(_MIRROR_DESC, 5), game.state, _ev(game), p1.id)
    assert val == 0.0, f"no attack-ready creatures -> no pump value, got {val}"
    print("PASS: board_pump gives 0 with no attack-ready creatures (combat-timing)")


def test_board_pump_nonlethal_uses_max_x():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 20
    for i in range(3):
        _bf_creature(game, p1, f"G{i}", 1, 1)
    val, x = _ai()._score_x_ability(_x_action(_MIRROR_DESC, 5), game.state, _ev(game), p1.id)
    assert val > 0.0, f"a non-lethal alpha-strike pump still has value, got {val}"
    assert x == 5, f"non-lethal -> max pressure (max X), got {x}"
    print("PASS: board_pump non-lethal uses max X")


def test_board_pump_become_does_not_shrink_board():
    # "become X/X" with max X below our biggest attacker would shrink it -> don't fire.
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 20
    _bf_creature(game, p1, "Big", 6, 6)
    val, x = _ai()._score_x_ability(_x_action(_MIRROR_DESC, 4), game.state, _ev(game), p1.id)
    assert val == 0.0, f"become-X/X below our biggest power should not fire, got {val}"
    print("PASS: become-X/X won't shrink our own board")


def test_board_pump_blocked_out_is_zero():
    # All attackers blockable and opponent has enough blockers -> no damage through.
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 20
    _bf_creature(game, p1, "G0", 1, 1)
    _bf_creature(game, p2, "Blk0", 1, 1)
    _bf_creature(game, p2, "Blk1", 1, 1)
    val, x = _ai()._score_x_ability(_x_action(_MIRROR_DESC, 5), game.state, _ev(game), p1.id)
    assert val == 0.0, f"pump adds no unblocked damage when fully blockable, got {val}"
    print("PASS: board_pump gives 0 when the swing is fully blocked")


# --------------------------------------------------------------------------- #
# Self pump
# --------------------------------------------------------------------------- #
def test_self_pump_finds_lethal_at_minimal_x():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 4
    striker = _bf_creature(game, p1, "Striker", 2, 2)
    val, x = _ai()._score_x_ability(
        _x_action("this creature gets +x/+x until end of turn", 5, source_id=striker.id),
        game.state, _ev(game), p1.id)
    assert val >= 6.0 and x == 2, f"2 power +X is lethal vs 4 life at X=2, got {(val, x)}"
    print("PASS: self_pump finds lethal at the minimal X")


# --------------------------------------------------------------------------- #
# Direct damage
# --------------------------------------------------------------------------- #
def test_damage_lethal_to_face_at_opp_life():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 4
    val, x = _ai()._score_x_ability(_x_action("deals x damage to any target", 6),
                                    game.state, _ev(game), p1.id)
    assert val >= 6.0 and x == 4, f"burn is lethal at X=opp life (4), got {(val, x)}"
    print("PASS: damage X is lethal to the face at X=opp life")


def test_damage_kills_creature_at_its_toughness():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 20
    _bf_creature(game, p2, "Bear", 3, 3)
    val, x = _ai()._score_x_ability(_x_action("deals x damage to any target", 6),
                                    game.state, _ev(game), p1.id)
    assert x == 3 and val > 0, f"burn exactly enough (X=3) to kill the 3/3, got {(val, x)}"
    print("PASS: damage X kills the creature at X = its toughness")


# --------------------------------------------------------------------------- #
# Symmetric debuff sweep (Winter, Cursed Rider)
# --------------------------------------------------------------------------- #
def test_debuff_picks_x_for_best_net_sweep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _bf_creature(game, p2, "OppBear", 3, 3)   # value 6, dies at X>=3
    _bf_creature(game, p2, "OppWall", 1, 5)   # value 6, dies at X>=5
    _bf_creature(game, p1, "MyBear", 2, 2)    # value 4, dies at X>=2 (collateral)
    val, x = _ai()._score_x_ability(
        _x_action("each other nonartifact creature gets -x/-x until end of turn", 5),
        game.state, _ev(game), p1.id)
    # X=5 kills both opp creatures (12) minus my bear (4) = net 8 -> best.
    assert x == 5 and val > 0, f"best net sweep is X=5 (kills both opp, nets +8), got {(val, x)}"
    print("PASS: debuff picks X for the best net (opp - mine) sweep")


def test_debuff_zero_when_only_hurts_self():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _bf_creature(game, p2, "OppFatty", 5, 8)  # too big to kill within budget
    _bf_creature(game, p1, "MyBear", 2, 2)
    val, x = _ai()._score_x_ability(
        _x_action("each other nonartifact creature gets -x/-x until end of turn", 4),
        game.state, _ev(game), p1.id)
    assert val == 0.0, f"sweep that only kills our own creature has no value, got {val}"
    print("PASS: debuff gives 0 when it only hurts our own board")


# --------------------------------------------------------------------------- #
# Draw X
# --------------------------------------------------------------------------- #
def test_draw_caps_x_to_avoid_decking():
    game = Game(); p1 = game.add_player("A"); game.add_player("B")
    # 4-card library -> never draw more than 3 (keep a 1-card buffer).
    for i in range(4):
        cd = make_creature(name=f"Lib{i}", power=1, toughness=1, mana_cost="{1}",
                           colors={Color.BLUE}, subtypes={"Bird"})
        game.create_object(name=cd.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
                           characteristics=cd.characteristics, card_def=cd)
    val, x = _ai()._score_x_ability(_x_action("draw x cards", 10), game.state, _ev(game), p1.id)
    assert x == 3, f"draw X capped at library-1 (=3), got {x}"
    assert val > 0, f"drawing 3 cards has positive value, got {val}"
    print("PASS: draw X caps at library size minus a buffer")


# --------------------------------------------------------------------------- #
# Copy a graveyard creature with mana value X (Likeness Looter)
# --------------------------------------------------------------------------- #
def test_copy_gy_picks_x_for_best_affordable_creature():
    game = Game(); p1 = game.add_player("A"); game.add_player("B")
    _gy_creature(game, p1, "GY Bear", 2, 2, "{1}{G}")        # MV 2
    _gy_creature(game, p1, "GY Giant", 6, 6, "{4}{G}{G}")    # MV 6
    desc = "becomes a copy of target creature card in your graveyard with mana value x"
    v2, x2 = _ai()._score_x_ability(_x_action(desc, 5), game.state, _ev(game), p1.id)
    assert x2 == 2 and v2 > 0, f"max X=5 only affords the MV-2 bear -> X=2, got {(v2, x2)}"
    v6, x6 = _ai()._score_x_ability(_x_action(desc, 6), game.state, _ev(game), p1.id)
    assert x6 == 6 and v6 >= v2, f"max X=6 affords the bigger MV-6 giant -> X=6, got {(v6, x6)}"
    print("PASS: copy_gy picks X = best affordable graveyard-creature MV")


# --------------------------------------------------------------------------- #
# Integration: scorer overrides x_value + records the score
# --------------------------------------------------------------------------- #
def test_scorer_overrides_x_value_and_records_breakdown():
    from src.cards.custom.fae_but_mid import FAE_BUT_MID_CARDS
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    p2.life = 3
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    me_def = FAE_BUT_MID_CARDS["Mirror Entity"]
    me = game.create_object(name=me_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
                            characteristics=me_def.characteristics, card_def=me_def)
    me.card_def = me_def
    for i in range(3):
        _bf_creature(game, p1, f"G{i}", 1, 1)
    xab = [a for a in me.state.activated_abilities if getattr(a, "has_x_cost", False)][0]
    action = LegalAction(
        type=ActionType.ACTIVATE_ABILITY, source_id=me.id, ability_id="activated:0",
        description=xab.description, mana_cost=xab.mana_cost, x_value=5,  # baked max
    )
    cand = _ai()._score_action_candidate(action, game.state, _ev(game), p1.id)
    assert cand.breakdown.x_ability >= 6.0, \
        f"lethal pump should record a high x_ability score, got {cand.breakdown.x_ability}"
    assert action.x_value == 1, \
        f"scorer must override the baked max X (5) with the lethal-minimal X (1), got {action.x_value}"
    print("PASS: scorer overrides x_value (5->1 lethal) and records breakdown.x_ability")


if __name__ == "__main__":
    test_classifier_covers_all_archetypes()
    test_board_pump_finds_lethal_at_minimal_x()
    test_board_pump_zero_without_attackers()
    test_board_pump_nonlethal_uses_max_x()
    test_board_pump_become_does_not_shrink_board()
    test_board_pump_blocked_out_is_zero()
    test_self_pump_finds_lethal_at_minimal_x()
    test_damage_lethal_to_face_at_opp_life()
    test_damage_kills_creature_at_its_toughness()
    test_debuff_picks_x_for_best_net_sweep()
    test_debuff_zero_when_only_hurts_self()
    test_draw_caps_x_to_avoid_decking()
    test_copy_gy_picks_x_for_best_affordable_creature()
    test_scorer_overrides_x_value_and_records_breakdown()
    print("\nAll X-ability board-EV tests passed.")
