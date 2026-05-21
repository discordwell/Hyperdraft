"""
Depths bot-vs-bot integration test.

Regression cover for the Turn-1 Draw bug: when the bot-game route had no
Depths branch, neither player was set up via ``setup_depths_player`` so
neither had a Flagship. The Depths SBA loss check (``flagship is None``)
then immediately flagged both players as lost on the first ``_check_sba``
call inside turn 1, producing a Turn-1 / 0-cards-played Draw.

The test exercises the real ``start_bot_game`` + ``run_bot_game`` route
handlers (no HTTP/uvicorn) and asserts:
  - the match plays at least 3 turns
  - both bots get a Flagship installed in setup
  - at least one bot played a card from hand (battlefield > flagships)
  - the match ends with a real winner (not a Draw)

Mirrors the spirit of the YGO wet test (``scripts/wet/wet_test_ygo_bvb.py``)
but runs in-process so it can live in CI without spinning a server.
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
from src.engine.depths import get_flagship, is_vessel  # noqa: E402


# Per-game hard timeout. Real Depths matches finish in <30 turns of heuristic
# play; 90 s is generous slack for slower CI hardware.
GAME_TIMEOUT_S = 90.0


async def _run_one_match(deck1: str, deck2: str) -> dict:
    """Drive a single Depths bot-vs-bot match and return result metadata."""
    bgt = BackgroundTasks()
    req = StartBotGameRequest(
        mode="depths",
        bot1_deck_id=deck1,
        bot2_deck_id=deck2,
        bot1_difficulty=AIDifficulty.MEDIUM,
        bot2_difficulty=AIDifficulty.MEDIUM,
        delay_ms=0,
    )

    resp = await start_bot_game(req, bgt)
    session = active_bot_games[resp.game_id]

    # Both flagships must exist immediately after setup — proves the route's
    # depths branch ran ``setup_depths_player`` for each seat.
    for pid in session.game.state.players:
        flagship = get_flagship(pid, session.game.state)
        assert flagship is not None, (
            f"player {pid} has no Flagship after start_bot_game — "
            f"setup_depths_player did not run"
        )

    try:
        await asyncio.wait_for(run_bot_game(session), timeout=GAME_TIMEOUT_S)
    except asyncio.TimeoutError:
        # Match still running — finalize what we can and let the assertion
        # below report a useful failure mode.
        session.is_finished = True

    # Count non-flagship vessels that ever existed on the battlefield. A
    # non-zero count proves at least one bot deployed something.
    deployed_vessels = 0
    for obj in session.game.state.objects.values():
        if not is_vessel(obj):
            continue
        if "Flagship" in obj.characteristics.subtypes:
            continue
        deployed_vessels += 1

    return {
        "game_id": resp.game_id,
        "turn": session.game.turn_manager.turn_number,
        "winner": session.winner_id,
        "is_over": session.game.is_game_over(),
        "frames": len(session.replay_frames),
        "deployed_vessels": deployed_vessels,
        "players_lost": {
            pid: bool(p.has_lost)
            for pid, p in session.game.state.players.items()
        },
    }


def _cleanup_session(game_id: str) -> None:
    active_bot_games.pop(game_id, None)
    completed_replays.pop(game_id, None)


def test_depths_bot_vs_bot_plays_out():
    """Regression: Depths bot-vs-bot must reach turn>=3 with a real winner."""
    result = asyncio.run(_run_one_match("SUBS_wolfpack", "SUBS_silent_hunter"))

    try:
        assert result["turn"] >= 3, (
            f"Depths bot match ended on turn {result['turn']} "
            f"(expected >= 3) — likely the Turn-1 Draw regression. "
            f"Result: {result}"
        )

        assert result["is_over"], (
            f"Depths bot match did not finish within {GAME_TIMEOUT_S}s. "
            f"Result: {result}"
        )

        assert result["winner"] is not None, (
            f"Depths bot match ended in a Draw (no winner). "
            f"This was the original Turn-1 bug; the orchestrator must "
            f"setup_depths_player so the SBA loss check doesn't fire on "
            f"missing flagships. Result: {result}"
        )

        assert result["deployed_vessels"] > 0, (
            f"No non-Flagship vessels ever deployed — bots played "
            f"zero cards. Result: {result}"
        )

        # Exactly one player should have lost (the loser); the winner stays
        # standing. If both lost we're back in the Turn-1 Draw failure
        # mode in disguise.
        lost_count = sum(1 for v in result["players_lost"].values() if v)
        assert lost_count == 1, (
            f"Expected exactly one player to have lost, got {lost_count}. "
            f"Result: {result}"
        )

    finally:
        _cleanup_session(result["game_id"])


def test_depths_bot_vs_bot_random_decks():
    """A second pair to catch deck-specific edge cases."""
    result = asyncio.run(_run_one_match("SUBS_carrier", "SUBS_deep_strike"))
    try:
        assert result["turn"] >= 3, f"Match ended on turn {result['turn']}: {result}"
        assert result["winner"] is not None, f"Draw / no winner: {result}"
        assert result["deployed_vessels"] > 0, f"Zero cards played: {result}"
    finally:
        _cleanup_session(result["game_id"])


if __name__ == "__main__":
    print("[1/2] Depths bot-vs-bot: wolfpack vs silent_hunter")
    test_depths_bot_vs_bot_plays_out()
    print("  PASS")

    print("[2/2] Depths bot-vs-bot: carrier vs deep_strike")
    test_depths_bot_vs_bot_random_decks()
    print("  PASS")

    print("\nAll Depths bot-vs-bot tests passed.")
