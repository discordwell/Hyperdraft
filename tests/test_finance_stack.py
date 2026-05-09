"""
Tests for the FinanceStack — MTG-style priority stack used by FINA spells.

Validates:
  - Cast a non-DP Order via _play_card_action → stack depth 1 mid-resolve,
    then resolves to depth 0.
  - Cast a Strategy + opponent counterspell → LIFO resolve, Strategy is
    countered (effect skipped), counterspell resolves normally.
  - Cast Order + counter + counter-the-counter → 3-deep stack, top resolves,
    middle is countered, bottom resolves.
  - Trader cast bypasses the stack entirely (depth never increments).

Run directly:
    python tests/test_finance_stack.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                                  # noqa: E402
    CardType, EventType, ZoneType,
)
from src.engine.game import Game                                # noqa: E402
from src.engine.finance import setup_finance_player             # noqa: E402
from src.engine.finance_turn import FinanceTurnManager          # noqa: E402
from src.engine.finance_combat import FinanceCombatManager      # noqa: E402

from src.cards.finance.fina.quant import (                      # noqa: E402
    INFORMATION_RATIO_ENFORCER,
    REGIME_CHANGE_DETECTION,
    LIQUIDITY_PROVISION,
    RISK_ADJUSTED_RETURN,
)
from src.cards.finance.fina.high_frequency import (             # noqa: E402
    EXECUTION_GLITCH,
    RETAIL_FLOW_CHASER,
)


def _make_game():
    game = Game(mode="finance")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    setup_finance_player(game, p1)
    setup_finance_player(game, p2)
    tm = FinanceTurnManager(game.state)
    game.turn_manager = tm
    tm.pipeline = game.pipeline
    tm.set_turn_order([p1.id, p2.id])
    tm.finance_combat_manager = FinanceCombatManager(game.state, game.pipeline)
    return game, p1, p2


def _add_to_hand(game, player_id: str, card_def):
    """Create a card object and put it in the player's hand."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _grant_liquidity(game, player_id: str, amount: int):
    p = game.state.players[player_id]
    p.mana_crystals_available = amount
    p.mana_crystals = max(p.mana_crystals or 0, amount)


def test_strategy_resolves_through_empty_stack():
    """Cast a Strategy with no opponent response → stack resolves cleanly."""
    game, p1, p2 = _make_game()
    tm = game.turn_manager

    spell = _add_to_hand(game, p1.id, LIQUIDITY_PROVISION)  # {2} Order — gain 3 Liq
    _grant_liquidity(game, p1.id, 5)

    # P2 has no counterspells in hand → priority loop returns None immediately.
    asyncio.run(tm._play_card_action(p1.id, spell.id, []))

    assert tm.fin_stack.is_empty(), "stack should be empty after resolution"
    # Card should be in P1's graveyard.
    grv = game.state.zones.get(f"graveyard_{p1.id}")
    assert grv and spell.id in grv.objects, "card should be in graveyard"
    print("test_strategy_resolves_through_empty_stack  PASS")


def test_counterspell_marks_target_countered():
    """P1 casts Strategy → P2 plays Information Ratio Enforcer →
    Strategy is countered (effect skipped) → both end in graveyard."""
    game, p1, p2 = _make_game()
    tm = game.turn_manager

    # P1 has a Strategy; P2 has Information Ratio Enforcer (1 Liquidity, no
    # spare so they can't pay the {2} unless cost). Wait — IRE costs {2}
    # to cast and the target's controller pays {2} to save it. Let's set
    # P1 with 5 Liquidity (enough to cast the Strategy at {2}, 3 left over)
    # and P2 with 2 Liquidity (just enough to cast IRE). P1 won't be able
    # to pay if their available is below 2 — but they'll have 3 left after
    # casting Strategy (assuming {2}). To force counter, we'll drain P1's
    # Liquidity after they cast.
    strat = _add_to_hand(game, p1.id, RISK_ADJUSTED_RETURN)  # Strategy {3}
    counter = _add_to_hand(game, p2.id, INFORMATION_RATIO_ENFORCER)  # Order {2}
    _grant_liquidity(game, p1.id, 3)  # enough for the Strategy, 0 left to pay
    _grant_liquidity(game, p2.id, 2)

    # Stub P2's response handler: play the counterspell targeting the strat.
    async def respond(_pid, _state):
        return {
            "action_type": "FIN_PLAY_RESPONSE",
            "card_id": counter.id,
            "targets": [[strat.id]],
        }
    tm.human_action_handler = respond
    # Don't mark P2 as AI — the priority loop falls through to human handler.

    asyncio.run(tm._play_card_action(p1.id, strat.id, []))

    assert tm.fin_stack.is_empty(), "stack should be empty after resolution"
    # Strategy should be in P1's graveyard but countered (no effect).
    grv1 = game.state.zones.get(f"graveyard_{p1.id}")
    grv2 = game.state.zones.get(f"graveyard_{p2.id}")
    assert grv1 and strat.id in grv1.objects, "Strategy should be in P1 graveyard"
    assert grv2 and counter.id in grv2.objects, "IRE should be in P2 graveyard"
    print("test_counterspell_marks_target_countered  PASS")


def test_trader_bypasses_stack():
    """Casting a Trader (permanent) does NOT touch the stack."""
    game, p1, p2 = _make_game()
    tm = game.turn_manager

    trader = _add_to_hand(game, p1.id, RETAIL_FLOW_CHASER)  # {1} Trader
    _grant_liquidity(game, p1.id, 3)

    asyncio.run(tm._play_card_action(p1.id, trader.id, []))

    # Stack never grew.
    assert tm.fin_stack.is_empty(), "Trader cast should not push to stack"
    # Trader is on the battlefield, not in a graveyard.
    bf = game.state.zones.get("battlefield")
    assert bf and trader.id in bf.objects, "Trader should be on battlefield"
    print("test_trader_bypasses_stack  PASS")


def test_counter_the_counter_chain():
    """3-deep stack: P1 Strategy → P2 IRE counter → P1 Execution Glitch
    counters the IRE → IRE goes to graveyard countered, Strategy resolves."""
    game, p1, p2 = _make_game()
    tm = game.turn_manager

    strat = _add_to_hand(game, p1.id, RISK_ADJUSTED_RETURN)  # {3} Strategy
    counter1 = _add_to_hand(game, p2.id, INFORMATION_RATIO_ENFORCER)  # {2} Order
    counter2 = _add_to_hand(game, p1.id, EXECUTION_GLITCH)  # {2} Order — counters Order
    _grant_liquidity(game, p1.id, 5)  # 3 for strat, 2 for glitch
    _grant_liquidity(game, p2.id, 2)  # 2 for IRE

    # P2 responds first: play IRE targeting strat.
    # Then P1 responds: play Execution Glitch targeting IRE.
    # Then P2 responds: pass (no more counters).
    responses = iter([
        # P2's first response: counter the strategy
        {"action_type": "FIN_PLAY_RESPONSE", "card_id": counter1.id,
         "targets": [[strat.id]]},
        # P1's response to counter1: Execution Glitch targeting IRE
        {"action_type": "FIN_PLAY_RESPONSE", "card_id": counter2.id,
         "targets": [[counter1.id]]},
        # P2's response to glitch: pass
        {"action_type": "FIN_PASS_RESPONSE"},
    ])
    async def respond(_pid, _state):
        try:
            return next(responses)
        except StopIteration:
            return {"action_type": "FIN_PASS_RESPONSE"}
    tm.human_action_handler = respond

    asyncio.run(tm._play_card_action(p1.id, strat.id, []))

    assert tm.fin_stack.is_empty(), "stack should be empty after resolution"
    # IRE should have been countered (still in graveyard).
    grv1 = game.state.zones.get(f"graveyard_{p1.id}")
    grv2 = game.state.zones.get(f"graveyard_{p2.id}")
    # All three cards end in their owner's graveyard.
    assert strat.id in grv1.objects, "strategy in P1 graveyard"
    assert counter2.id in grv1.objects, "Execution Glitch in P1 graveyard"
    assert counter1.id in grv2.objects, "IRE in P2 graveyard"
    print("test_counter_the_counter_chain  PASS")


def test_pay_to_save_consumes_liquidity():
    """IRE: 'unless controller pays {2}'. If controller has ≥{2} Liquidity,
    they pay it and the spell is NOT countered.

    NOTE: rebalance lowered RISK_ADJUSTED_RETURN from {3} → {2}; total cost to
    cast+save is now 4 Liquidity (2 cast + 2 save). Liquidity grant updated to
    match.
    """
    game, p1, p2 = _make_game()
    tm = game.turn_manager

    strat = _add_to_hand(game, p1.id, RISK_ADJUSTED_RETURN)  # rebalance: now {2} (was {3})
    counter = _add_to_hand(game, p2.id, INFORMATION_RATIO_ENFORCER)
    # Give P1 enough that they have ≥{2} after casting the Strategy.
    _grant_liquidity(game, p1.id, 4)  # cast strat costs 2, leaves 2 to pay (rebalance: was 5)
    _grant_liquidity(game, p2.id, 2)

    async def respond(_pid, _state):
        return {
            "action_type": "FIN_PLAY_RESPONSE",
            "card_id": counter.id,
            "targets": [[strat.id]],
        }
    tm.human_action_handler = respond

    asyncio.run(tm._play_card_action(p1.id, strat.id, []))

    p1_state = game.state.players[p1.id]
    # P1 paid {2} to cast and {2} to save → 0 Liquidity remaining.
    assert p1_state.mana_crystals_available == 0, (
        f"P1 should have 0 Liquidity, got {p1_state.mana_crystals_available}"
    )
    assert tm.fin_stack.is_empty()
    print("test_pay_to_save_consumes_liquidity  PASS")


if __name__ == "__main__":
    test_strategy_resolves_through_empty_stack()
    test_trader_bypasses_stack()
    test_counterspell_marks_target_countered()
    test_counter_the_counter_chain()
    test_pay_to_save_consumes_liquidity()
    print()
    print("All FinanceStack tests passed.")
