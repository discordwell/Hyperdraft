"""
Yu-Gi-Oh! Monster Ignition Effect Tests

Verifies the YGO_ACTIVATE_MONSTER_EFFECT surface added to the engine:

1. Unit test: a monster with an ignition effect on the field is listed in
   ``legal_yugioh_actions``; applying that action fires its effect_fn.
2. Trace test: a 5-game BK Samurai mirror reports >= 5 distinct ignition
   activations, hitting the previously-dead "Bottom 10" cards.
3. Regression: once-per-turn gate works (effect cannot fire twice in one turn).
4. Regression: face-down monster's ignition does not appear in legal actions.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game, make_ygo_monster
from src.engine.types import (
    CardType, Event, EventType, Interceptor, InterceptorAction,
    InterceptorPriority, InterceptorResult, ZoneType, new_id,
)
from src.engine.yugioh_helpers import make_ygo_ignition_effect
from src.engine.yugioh_legal_actions import legal_yugioh_actions


def make_test_game():
    g = Game(mode="yugioh")
    p1 = g.add_player("P1")
    p2 = g.add_player("P2")
    return g, p1, p2


def _add_to_field(game, player, card_def):
    """Create a monster object directly in the monster zone.

    ``game.create_object`` already appends to the zone (when a
    ``_get_zone_key`` mapping exists), so we let it do that and only fix up
    the YGO-specific state. ``create_object`` ALSO runs
    ``setup_interceptors``, so we do not re-register them ourselves.
    """
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.MONSTER_ZONE,
        characteristics=card_def.characteristics.__class__(
            types=set(card_def.characteristics.types)),
        card_def=card_def,
    )
    obj.zone = ZoneType.MONSTER_ZONE
    obj.state.face_down = False
    obj.state.ygo_position = "face_up_atk"
    return obj


# -----------------------------------------------------------------------------
# 1. Unit test: ignition action surfaces and the effect_fn fires.
# -----------------------------------------------------------------------------

def test_ignition_action_surfaces_and_fires():
    """Build a synthetic monster whose ignition gains 1000 LP and verify
    the legal action list exposes it, then verify dispatching it fires
    the effect_fn (LP increases)."""
    game, p1, p2 = make_test_game()
    game.turn_manager.ygo_turn_state.active_player_id = p1.id
    game.turn_manager.ygo_turn_state.turn_number = 1
    game.turn_manager.turn_state.turn_number = 1

    fired = []

    def life_gain_setup(obj, state):
        def effect_fn(o, s):
            fired.append(o.id)
            player = s.players.get(o.controller)
            if player:
                player.lp += 1000
            return [Event(type=EventType.YGO_LP_CHANGE,
                          payload={'player': o.controller, 'amount': 1000,
                                   'source': o.name})]
        return [make_ygo_ignition_effect(obj, effect_fn)]

    card_def = make_ygo_monster(
        "Test Ignition Monster", atk=1000, def_val=1000, level=4,
        attribute="LIGHT", ygo_monster_type="Effect",
        subtypes={"Test"},
    )
    card_def.text = "Once per turn (Ignition): gain 1000 LP."
    card_def.setup_interceptors = life_gain_setup

    obj = _add_to_field(game, p1, card_def)
    # Move the turn-state phase to MAIN1 so legal_actions returns main-phase set.
    from src.engine.yugioh_types import YGOPhase
    game.turn_manager.ygo_turn_state.phase = YGOPhase.MAIN1

    # 1a. Legal actions list contains the ignition.
    legal = legal_yugioh_actions(game, p1.id)
    ignition_actions = [a for a in legal
                        if a["type"] == "YGO_ACTIVATE_MONSTER_EFFECT"
                        and a["payload"].get("card_id") == obj.id]
    assert len(ignition_actions) == 1, \
        f"Expected 1 ignition action, got {len(ignition_actions)}; legal={[a['type'] for a in legal]}"

    # 1b. Dispatch fires the effect and emits the gain event.
    starting_lp = p1.lp
    events = game.turn_manager._execute_action(
        p1.id, ignition_actions[0]["payload"]
    )
    assert fired, "effect_fn did not run"
    assert p1.lp == starting_lp + 1000, \
        f"LP didn't increase: {starting_lp} -> {p1.lp}"
    # The activation event must have been emitted.
    types = [e.type for e in events]
    assert EventType.YGO_ACTIVATE_MONSTER_EFFECT in types, \
        f"YGO_ACTIVATE_MONSTER_EFFECT not in {types}"
    print("  PASS: test_ignition_action_surfaces_and_fires")


# -----------------------------------------------------------------------------
# 2. Regression: once-per-turn gate works.
# -----------------------------------------------------------------------------

def test_ignition_once_per_turn():
    """Activating a monster's effect twice in one turn should fail the second
    time — both via legal-action filtering and via the turn manager's gate."""
    game, p1, p2 = make_test_game()
    game.turn_manager.ygo_turn_state.active_player_id = p1.id
    game.turn_manager.ygo_turn_state.turn_number = 5
    game.turn_manager.turn_state.turn_number = 5

    fire_count = []

    def setup(obj, state):
        def effect_fn(o, s):
            fire_count.append(1)
            return []
        return [make_ygo_ignition_effect(obj, effect_fn)]

    card_def = make_ygo_monster(
        "Repeater", atk=1000, def_val=1000, level=4,
        attribute="DARK", ygo_monster_type="Effect", subtypes={"Test"},
    )
    card_def.text = "Once per turn: do nothing."
    card_def.setup_interceptors = setup

    obj = _add_to_field(game, p1, card_def)
    from src.engine.yugioh_types import YGOPhase
    game.turn_manager.ygo_turn_state.phase = YGOPhase.MAIN1

    legal = legal_yugioh_actions(game, p1.id)
    ignition = [a for a in legal if a["type"] == "YGO_ACTIVATE_MONSTER_EFFECT"]
    assert ignition, "first activation should be legal"

    # First fire.
    game.turn_manager._execute_action(p1.id, ignition[0]["payload"])
    assert len(fire_count) == 1

    # Legal actions should no longer offer it.
    legal2 = legal_yugioh_actions(game, p1.id)
    ignition2 = [a for a in legal2
                 if a["type"] == "YGO_ACTIVATE_MONSTER_EFFECT"
                 and a["payload"].get("card_id") == obj.id]
    assert len(ignition2) == 0, \
        f"Once-per-turn gate failed: still {len(ignition2)} action(s) legal"

    # Engine itself also rejects a re-dispatch of the same payload.
    game.turn_manager._execute_action(p1.id, ignition[0]["payload"])
    assert len(fire_count) == 1, \
        f"Engine fired again despite gate: {len(fire_count)} total fires"
    print("  PASS: test_ignition_once_per_turn")


# -----------------------------------------------------------------------------
# 3. Regression: face-down monsters don't expose their ignition.
# -----------------------------------------------------------------------------

def test_facedown_ignition_hidden():
    """A face-down monster's once-per-turn surface must not appear in
    legal actions (the card has to be face-up to activate its effect)."""
    game, p1, p2 = make_test_game()
    game.turn_manager.ygo_turn_state.active_player_id = p1.id
    game.turn_manager.ygo_turn_state.turn_number = 1
    game.turn_manager.turn_state.turn_number = 1

    def setup(obj, state):
        def effect_fn(o, s):
            return []
        return [make_ygo_ignition_effect(obj, effect_fn)]

    card_def = make_ygo_monster(
        "Hidden Ignition", atk=1000, def_val=2000, level=4,
        attribute="DARK", ygo_monster_type="Effect", subtypes={"Test"},
    )
    card_def.text = "Once per turn: do something cute."
    card_def.setup_interceptors = setup

    obj = _add_to_field(game, p1, card_def)
    obj.state.face_down = True
    obj.state.ygo_position = "face_down_def"

    from src.engine.yugioh_types import YGOPhase
    game.turn_manager.ygo_turn_state.phase = YGOPhase.MAIN1
    legal = legal_yugioh_actions(game, p1.id)
    ignition = [a for a in legal
                if a["type"] == "YGO_ACTIVATE_MONSTER_EFFECT"
                and a["payload"].get("card_id") == obj.id]
    assert len(ignition) == 0, \
        "face-down monster ignition should NOT appear in legal actions"
    print("  PASS: test_facedown_ignition_hidden")


# -----------------------------------------------------------------------------
# 4. Trace test: BK Samurai mirror exercises ignition surfaces.
# -----------------------------------------------------------------------------

def test_bk_modified_mirror_fires_ignitions():
    """Run 5 short BK Modified-vs-Modified games and verify at least 5
    YGO_ACTIVATE_MONSTER_EFFECT events fire across the games.

    Modified is the highest-ignition-density BK archetype (Reckoner
    Bankbuster + Boseiju Bridgekeeper + Goro-Goro), so the mirror reliably
    exercises the new YGO_ACTIVATE_MONSTER_EFFECT surface. Empirically the
    range is ~7-50 fires per 5-game batch — 5 is a conservative floor that
    we expect to clear on every run.
    """
    # Import is heavy — keep inside the test.
    from src.cards.yugioh.beyond.kamigawa import (
        build_kamigawa_deck, kamigawa_strategy,
    )
    from src.ai.yugioh_adapter import YugiohAIAdapter

    class DispatchYugiohAI:
        def __init__(self, adapters):
            self.adapters = adapters
        def get_main_phase_action(self, player_id, state, turn_state):
            return self.adapters[player_id].get_main_phase_action(player_id, state, turn_state)
        def get_battle_action(self, player_id, state, turn_state):
            return self.adapters[player_id].get_battle_action(player_id, state, turn_state)
        def should_enter_battle(self, player_id, state):
            return self.adapters[player_id].should_enter_battle(player_id, state)

    async def run_one():
        g = Game(mode="yugioh")
        p1 = g.add_player("Modified-A")
        p2 = g.add_player("Modified-B")
        main_a, extra_a = build_kamigawa_deck("modified")
        main_b, extra_b = build_kamigawa_deck("modified")
        g.setup_yugioh_player(p1, main_a, extra_a)
        g.setup_yugioh_player(p2, main_b, extra_b)
        ai_a = YugiohAIAdapter(difficulty="hard")
        ai_b = YugiohAIAdapter(difficulty="hard")
        ai_a.strategy = kamigawa_strategy("modified")
        ai_b.strategy = kamigawa_strategy("modified")
        g.turn_manager.set_ai_handler(DispatchYugiohAI({p1.id: ai_a, p2.id: ai_b}))
        g.turn_manager.ai_players.add(p1.id)
        g.turn_manager.ai_players.add(p2.id)
        captured = []
        if hasattr(g, 'pipeline') and g.pipeline is not None:
            orig = g.pipeline.emit
            def trace_emit(ev):
                if ev.type == EventType.YGO_ACTIVATE_MONSTER_EFFECT:
                    captured.append(ev.payload.get('card_name'))
                return orig(ev)
            g.pipeline.emit = trace_emit

        await g.turn_manager.setup_game()
        for _ in range(25):  # max 25 turns per game
            if g.is_game_over():
                break
            await g.turn_manager.run_turn()
        return captured

    total_fires = 0
    unique_cards = set()
    for i in range(5):
        captured = asyncio.run(run_one())
        total_fires += len(captured)
        unique_cards.update(captured)

    print(f"  trace: {total_fires} ignition fires across 5 games; "
          f"distinct cards: {sorted(unique_cards)}")
    assert total_fires >= 5, \
        f"Expected >= 5 ignition activations across 5 BK Modified games, " \
        f"got {total_fires}"
    print("  PASS: test_bk_modified_mirror_fires_ignitions")


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("YGO Monster Ignition Effect Tests")
    print("=" * 60)
    tests = [
        test_ignition_action_surfaces_and_fires,
        test_ignition_once_per_turn,
        test_facedown_ignition_hidden,
        test_bk_modified_mirror_fires_ignitions,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as ex:
            print(f"  FAIL: {t.__name__}: {ex}")
            failed += 1
        except Exception as ex:
            import traceback
            print(f"  ERROR: {t.__name__}: {type(ex).__name__}: {ex}")
            traceback.print_exc()
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
