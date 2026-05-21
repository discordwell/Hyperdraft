"""
Finance bot-vs-bot integration test.

Regression cover for the END_TURN-spam bug: when the bot-game route had no
Finance branch, both seats fell through to the MTG/HS else block which
filled their libraries with TEST_CARDS (Forest/Plains/Lightning Bolt).
None of those carry FIN_TRADER/FIN_ORDER/FIN_STRATEGY/FIN_ASSET/
FIN_STRUCTURE/FIN_DERIVATIVE types, so ``FinanceTurnManager._play_card_action``
recognised them as neither permanents nor one-shots and silently dropped
every play. End result: 89 turns of END_TURN spam with 0 battlefield
objects.

The test exercises the real ``start_bot_game`` + ``run_bot_game`` route
handlers (no HTTP/uvicorn) and asserts the regression conditions:
  - both bots are set up via ``setup_finance_player`` (life=30, max_life=30)
  - the match plays at least 5 turns
  - at least one bot plays at least one non-END_TURN action
  - at some point each player has > 0 cards on the battlefield (Trading Floor)
  - the match ends with a real winner (not a Draw)

Mirrors ``tests/test_depths_bot_game.py``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fastapi import BackgroundTasks  # noqa: E402

from src.server.routes.bot_game import (  # noqa: E402
    start_bot_game, run_bot_game, active_bot_games, completed_replays,
)
from src.server.models import StartBotGameRequest, AIDifficulty  # noqa: E402
from src.engine.finance import STARTING_CAPITAL  # noqa: E402


# Finance matches at heuristic medium typically finish in ~25-40 turns. 120s
# leaves slack for slower CI hardware.
GAME_TIMEOUT_S = 120.0


async def _run_one_match(deck1: str, deck2: str) -> dict:
    """Drive a single Finance bot-vs-bot match and return result metadata."""
    bgt = BackgroundTasks()
    req = StartBotGameRequest(
        mode="finance",
        bot1_deck_id=deck1,
        bot2_deck_id=deck2,
        bot1_difficulty=AIDifficulty.MEDIUM,
        bot2_difficulty=AIDifficulty.MEDIUM,
        delay_ms=0,
    )

    resp = await start_bot_game(req, bgt)
    session = active_bot_games[resp.game_id]

    # Both seats must be set up via setup_finance_player — proves the
    # route's finance branch ran. The default Player life is 20; the
    # finance setup bumps it to STARTING_CAPITAL=30.
    for pid, p in session.game.state.players.items():
        assert p.life == STARTING_CAPITAL, (
            f"player {pid} life={p.life}, expected {STARTING_CAPITAL} — "
            f"setup_finance_player did not run"
        )
        assert p.max_life == STARTING_CAPITAL, (
            f"player {pid} max_life={p.max_life}, expected {STARTING_CAPITAL}"
        )

    # Track maximum battlefield population per player across the match.
    # We sample after every turn so a transient battlefield (e.g. attackers
    # die in combat) still proves the bot deployed cards.
    max_bf_per_player: dict[str, int] = {pid: 0 for pid in session.game.state.players}

    # Wrap run_bot_game so we can interleave samples between turns.
    async def _run_with_samples() -> None:
        try:
            await session.start_game()

            while not session.is_finished:
                await session.game.turn_manager.run_turn()

                # Sample battlefield by controller for this turn.
                bf = session.game.state.zones.get("battlefield")
                if bf is not None:
                    counts: dict[str, int] = {}
                    for obj_id in bf.objects:
                        obj = session.game.state.objects.get(obj_id)
                        if obj is None:
                            continue
                        counts[obj.controller] = counts.get(obj.controller, 0) + 1
                    for pid, c in counts.items():
                        if c > max_bf_per_player.get(pid, 0):
                            max_bf_per_player[pid] = c

                if session.game.is_game_over():
                    session.is_finished = True
                    session.winner_id = session.game.get_winner()
                    break

                if session.game.turn_manager.turn_number > 100:
                    session.is_finished = True
                    break
        except Exception as e:  # pragma: no cover — defensive
            print(f"Finance bot match error: {e}")
            session.is_finished = True

    try:
        await asyncio.wait_for(_run_with_samples(), timeout=GAME_TIMEOUT_S)
    except asyncio.TimeoutError:
        session.is_finished = True

    return {
        "game_id": resp.game_id,
        "turn": session.game.turn_manager.turn_number,
        "winner": session.winner_id,
        "is_over": session.game.is_game_over(),
        "max_bf_per_player": dict(max_bf_per_player),
        "players_lost": {
            pid: bool(p.has_lost)
            for pid, p in session.game.state.players.items()
        },
    }


def _cleanup_session(game_id: str) -> None:
    active_bot_games.pop(game_id, None)
    completed_replays.pop(game_id, None)


def test_finance_bot_vs_bot_plays_out():
    """Regression: Finance bot-vs-bot must play cards, not pass-only END_TURN spam."""
    result = asyncio.run(_run_one_match("FINA_high_frequency", "FINA_quant"))

    try:
        assert result["turn"] >= 5, (
            f"Finance bot match ended on turn {result['turn']} "
            f"(expected >= 5) — likely the pass-only END_TURN regression. "
            f"Result: {result}"
        )

        # Each player must have deployed at least one card at some point.
        # This is the core regression assertion: under the bug, both
        # max_bf values stay at 0 for the entire match.
        for pid, max_bf in result["max_bf_per_player"].items():
            assert max_bf > 0, (
                f"player {pid} never had a card on the battlefield "
                f"(max_bf={max_bf}) — bot orchestrator gave them a "
                f"non-Finance deck or AI returned only END_TURN. "
                f"Result: {result}"
            )

        assert result["is_over"], (
            f"Finance bot match did not finish within {GAME_TIMEOUT_S}s. "
            f"Result: {result}"
        )

        assert result["winner"] is not None, (
            f"Finance bot match ended in a Draw (no winner). "
            f"Result: {result}"
        )

        # Exactly one player should have lost (the loser); the winner stays
        # solvent.
        lost_count = sum(1 for v in result["players_lost"].values() if v)
        assert lost_count == 1, (
            f"Expected exactly one player to have lost, got {lost_count}. "
            f"Result: {result}"
        )

    finally:
        _cleanup_session(result["game_id"])


def test_finance_bot_vs_bot_random_decks():
    """A second pair to catch deck-specific edge cases."""
    result = asyncio.run(_run_one_match("FINA_derivatives", "FINA_dark_arbitrage"))
    try:
        assert result["turn"] >= 5, f"Match ended on turn {result['turn']}: {result}"
        # Don't require a winner here — the FINA_dark_arbitrage / derivatives
        # matchup can occasionally stall or time out on slow hardware. Card
        # plays are still the load-bearing assertion.
        for pid, max_bf in result["max_bf_per_player"].items():
            assert max_bf > 0, (
                f"player {pid} max_bf={max_bf} — orchestrator gap. Result: {result}"
            )
    finally:
        _cleanup_session(result["game_id"])


if __name__ == "__main__":
    print("[1/2] Finance bot-vs-bot: high_frequency vs quant")
    test_finance_bot_vs_bot_plays_out()
    print("  PASS")

    print("[2/2] Finance bot-vs-bot: derivatives vs dark_arbitrage")
    test_finance_bot_vs_bot_random_decks()
    print("  PASS")

    print("\nAll Finance bot-vs-bot tests passed.")
