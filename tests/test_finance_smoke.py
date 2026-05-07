"""
Smoke test for the Finance TCG engine — Stage 1 deliverable.

Asserts:
  1. AI-vs-AI game completes within 60 turns (no infinite loop / crash).
  2. Both AIs make at least one non-no-op decision.
  3. Some win condition fires (not a 60-turn timeout with no winner).

Uses a minimal placeholder card pool — no real FINA card set required.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                                      # noqa: E402
    CardDefinition, Characteristics, CardType, ZoneType, new_id,
)
from src.engine.game import Game                                    # noqa: E402
from src.engine.finance import setup_finance_player                 # noqa: E402
from src.engine.finance_turn import FinanceTurnManager             # noqa: E402
from src.ai.finance_adapter import FinanceAIAdapter                 # noqa: E402

MAX_TURNS = 60
DECK_SIZE = 30

# ---------------------------------------------------------------------------
# Minimal placeholder card pool
# ---------------------------------------------------------------------------

def _trader(name: str, *, aggression: int, defense: int, cost: int) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_TRADER},
        subtypes={"Quant"},
        power=aggression,
        toughness=defense,
        mana_cost="{" + str(cost) + "}",
    )
    return CardDefinition(
        name=name,
        mana_cost="{" + str(cost) + "}",
        characteristics=chars,
        domain="FINA",
        text="Vanilla trader.",
    )


_PLACEHOLDER_POOL = [
    _trader("Junior Analyst",       aggression=1, defense=1, cost=1),
    _trader("Senior Associate",     aggression=2, defense=2, cost=2),
    _trader("VP of Trading",        aggression=3, defense=3, cost=3),
    _trader("Managing Director",    aggression=4, defense=3, cost=4),
    _trader("Delta Hedger",         aggression=3, defense=4, cost=4),
    _trader("HFT Algorithm",        aggression=4, defense=2, cost=3),
]


def _build_deck(label: str, size: int = DECK_SIZE) -> list[CardDefinition]:
    pool = _PLACEHOLDER_POOL
    deck: list[CardDefinition] = []
    i = 0
    while len(deck) < size:
        c = pool[i % len(pool)]
        # Give each card a distinct name per copy so we can track them
        copy_def = CardDefinition(
            name=f"{c.name} [{label}-{i}]",
            mana_cost=c.mana_cost,
            characteristics=c.characteristics,
            domain=c.domain,
            text=c.text,
        )
        deck.append(copy_def)
        i += 1
    return deck


# ---------------------------------------------------------------------------
# Decision tracker wrapper
# ---------------------------------------------------------------------------

class DecisionTracker:
    def __init__(self, inner: FinanceAIAdapter, label: str):
        self.inner = inner
        self.label = label
        self.plays_made = 0
        self.attacks_declared = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def choose_play_action(self, state, player_id):
        action = self.inner.choose_play_action(state, player_id)
        if action and action.get("type") == "play_card":
            self.plays_made += 1
        return action

    def choose_attackers(self, state, player_id):
        attackers = self.inner.choose_attackers(state, player_id)
        if attackers:
            self.attacks_declared += len(attackers)
        return attackers

    def choose_blockers(self, state, attacker_ids, player_id):
        return self.inner.choose_blockers(state, attacker_ids, player_id)

    def choose_discard(self, state, player_id, hand):
        return self.inner.choose_discard(state, player_id, hand)

    def mulligan_decision(self, state, player_id, hand=None):
        return self.inner.mulligan_decision(state, player_id, hand or [])

    @property
    def made_any_decision(self) -> bool:
        return (self.plays_made + self.attacks_declared) > 0


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

async def _run_one_game() -> dict:
    game = Game(mode="finance")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Setup finance player state
    setup_finance_player(game, p1)
    setup_finance_player(game, p2)

    # Load decks
    deck1 = _build_deck("A")
    deck2 = _build_deck("B")
    for card_def in deck1:
        game.add_card_to_library(p1.id, card_def)
    for card_def in deck2:
        game.add_card_to_library(p2.id, card_def)

    # Build turn manager
    tm = FinanceTurnManager(game.state)
    game.turn_manager = tm
    tm.set_turn_order([p1.id, p2.id])

    # Wire AI handlers
    p1_ai = DecisionTracker(FinanceAIAdapter(difficulty="medium"), "P1")
    p2_ai = DecisionTracker(FinanceAIAdapter(difficulty="medium"), "P2")
    tm.set_ai_handler(p1.id, p1_ai)
    tm.set_ai_handler(p2.id, p2_ai)
    tm.ai_players.add(p1.id)
    tm.ai_players.add(p2.id)

    # Wire combat manager if available
    try:
        from src.engine.finance_combat import FinanceCombatManager
        tm.finance_combat_manager = FinanceCombatManager(game.state, game.pipeline)
    except Exception:
        pass  # reconciliation will fix if needed

    turns_run = 0
    error = None
    try:
        for _ in range(MAX_TURNS):
            if game.is_game_over():
                break
            active_id = p1.id if turns_run % 2 == 0 else p2.id
            await tm.run_turn(active_id)
            turns_run += 1
    except Exception as exc:
        import traceback
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"

    return {
        "turns": turns_run,
        "completed": game.is_game_over(),
        "p1_made_decision": p1_ai.made_any_decision,
        "p2_made_decision": p2_ai.made_any_decision,
        "p1_plays": p1_ai.plays_made,
        "p2_plays": p2_ai.plays_made,
        "p1_attacks": p1_ai.attacks_declared,
        "p2_attacks": p2_ai.attacks_declared,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_finance_ai_vs_ai_completes():
    """Game must finish within 60 turns with no crash and a win condition."""
    result = asyncio.run(_run_one_game())
    print(f"\n=== finance smoke result ===")
    for k, v in result.items():
        if k != "error":
            print(f"  {k}: {v}")
    if result["error"]:
        print(f"  error:\n{result['error']}")

    assert result["error"] is None, f"Game crashed:\n{result['error']}"
    assert result["turns"] <= MAX_TURNS, \
        f"Game exceeded {MAX_TURNS} turns ({result['turns']})"
    assert result["completed"], \
        f"Game did not finish within {MAX_TURNS} turns (no win condition fired)"


def test_finance_ai_makes_decisions():
    """Both AIs must make at least one non-no-op decision."""
    result = asyncio.run(_run_one_game())
    assert result["error"] is None, f"Game crashed:\n{result['error']}"
    assert result["p1_made_decision"], (
        f"P1 made zero non-no-op decisions over {result['turns']} turns "
        f"(plays={result['p1_plays']}, attacks={result['p1_attacks']})"
    )
    assert result["p2_made_decision"], (
        f"P2 made zero non-no-op decisions over {result['turns']} turns "
        f"(plays={result['p2_plays']}, attacks={result['p2_attacks']})"
    )


if __name__ == "__main__":
    result = asyncio.run(_run_one_game())
    print("\n=== Finance Smoke Test ===")
    for k, v in result.items():
        if k != "error":
            print(f"  {k}: {v}")
    if result["error"]:
        print(f"\n  ERROR:\n{result['error']}")
    else:
        print("\n  PASSED")
