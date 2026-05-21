"""
Bot game /list response enrichment — WatchLive lobby slice.

Drops the WatchLive mock fallback by extending BotGameStatus with engine
code, per-seat brain/difficulty labels, and a deck archetype blurb. This
test exercises the new fields by starting a real bot-vs-bot session via
the route handler (no HTTP/uvicorn) and asserting that ``/list`` surfaces
them.

Covers two flavours:
  - MTG with explicit netdeck IDs (deck blurb resolved through ALL_DECKS).
  - Depths with random fallback (deck blurb resolved through the resolved
    SUBS deck key).

Mirrors the spirit of ``tests/test_depths_bot_game.py`` — in-process so
it runs fast on CI.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fastapi import BackgroundTasks  # noqa: E402

from src.server.routes.bot_game import (  # noqa: E402
    start_bot_game, list_bot_games, get_bot_game_status,
    active_bot_games, completed_replays,
)
from src.server.models import (  # noqa: E402
    StartBotGameRequest, AIDifficulty, BotBrain, BotGameStatus,
)


def _cleanup(game_id: str) -> None:
    active_bot_games.pop(game_id, None)
    completed_replays.pop(game_id, None)


def test_bot_game_list_enriches_mtg_session():
    """MTG bot-vs-bot with netdeck IDs surfaces brain + difficulty + deck."""

    async def go():
        bgt = BackgroundTasks()
        req = StartBotGameRequest(
            mode="mtg",
            bot1_deck_id="mono_red_netdeck",
            bot2_deck_id="azorius_simulacrum_netdeck",
            bot1_brain=BotBrain.HEURISTIC,
            bot2_brain=BotBrain.HEURISTIC,
            bot1_difficulty=AIDifficulty.MEDIUM,
            bot2_difficulty=AIDifficulty.ULTRA,
            delay_ms=0,
        )
        resp = await start_bot_game(req, bgt)
        try:
            # Listing 'running' should pick up the freshly-started session.
            listed = await list_bot_games(status="running")
            row = next(
                (r for r in listed.games if r.game_id == resp.game_id),
                None,
            )
            assert row is not None, (
                f"started game {resp.game_id} not in /list response: "
                f"{[r.game_id for r in listed.games]}"
            )
            assert isinstance(row, BotGameStatus)

            # --- The point of this test: enrichment fields. ---------------
            # Engine code matches the request mode.
            assert row.game_mode == "mtg", row

            # Player labels embed brain + difficulty. Bot1 is heuristic
            # medium; bot2 is heuristic ultra. Bot1's brain "heuristic"
            # title-cases to "Heuristic".
            assert row.player1_label == "Heuristic · medium", row.player1_label
            assert row.player2_label == "Heuristic · ultra", row.player2_label

            # Deck blurb resolves through ALL_DECKS to the registered Deck
            # name. mono_red_netdeck is a known netdeck.
            assert row.deck_blurb, f"no deck_blurb on row: {row}"
            # The first seat wins — bot1_deck_id was mono_red_netdeck.
            # Accept either the registered display name (preferred) or
            # the de-slugged fallback.
            assert "Mono" in row.deck_blurb and "Red" in row.deck_blurb, (
                f"deck_blurb {row.deck_blurb!r} doesn't look like mono-red"
            )

            # Status round-trips through the single-game endpoint too.
            status_row = await get_bot_game_status(resp.game_id)
            assert status_row.game_mode == "mtg"
            assert status_row.player1_label == "Heuristic · medium"
            assert status_row.deck_blurb == row.deck_blurb
        finally:
            _cleanup(resp.game_id)

    asyncio.run(go())


def test_bot_game_list_enriches_depths_session():
    """Depths bot-vs-bot with resolved random keys surfaces engine + decks."""

    async def go():
        bgt = BackgroundTasks()
        req = StartBotGameRequest(
            mode="depths",
            bot1_deck_id="SUBS_wolfpack",
            bot2_deck_id="SUBS_carrier",
            bot1_difficulty=AIDifficulty.HARD,
            bot2_difficulty=AIDifficulty.MEDIUM,
            delay_ms=0,
        )
        resp = await start_bot_game(req, bgt)
        try:
            listed = await list_bot_games(status="running")
            row = next(
                (r for r in listed.games if r.game_id == resp.game_id),
                None,
            )
            assert row is not None
            assert row.game_mode == "depths"
            assert row.player1_label == "Heuristic · hard"
            assert row.player2_label == "Heuristic · medium"
            # SUBS_wolfpack de-slugs to "Subs Wolfpack" (no registered Deck).
            assert row.deck_blurb, row
            assert "wolfpack" in row.deck_blurb.lower(), row.deck_blurb
        finally:
            _cleanup(resp.game_id)

    asyncio.run(go())


if __name__ == "__main__":
    print("[1/2] /bot-game/list — MTG enrichment")
    test_bot_game_list_enriches_mtg_session()
    print("  PASS")

    print("[2/2] /bot-game/list — Depths enrichment")
    test_bot_game_list_enriches_depths_session()
    print("  PASS")

    print("\nAll bot-game list tests passed.")
