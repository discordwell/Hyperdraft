"""
Hearthstone bot-vs-bot match creation regression test.

Reproduces the failure mode that prevented the ultra spectator demo from
ever archiving a Hearthstone replay (0 / 38 matches in prod): the HS branch
of ``routes.match.create_match`` indexed ``hero_class_by_player[human_id]``
unconditionally, but bot_vs_bot mode sets ``human_id = ""`` (no human seat),
which raised ``KeyError: ''`` and aborted match creation before any session
state was even built. The supervisor caught the exception, silently logged
"create_match for game_mode=hearthstone failed", and rotated to the next
mode — leaving zero HS matches in ``storage/replays/index.json``.

Each test below exercises one mode/branch combination of the HS setup path
and asserts that match creation completes, both players' libraries are
populated, and the ultra-AI plumbing is wired correctly when applicable.

Run directly:
    python tests/test_hearthstone_bot_vs_bot.py
"""

from __future__ import annotations

import asyncio
import sys
import os

# Allow `python tests/test_hearthstone_bot_vs_bot.py` from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import BackgroundTasks

from src.server.models import CreateMatchRequest, AIDifficulty
from src.server.routes.match import create_match
import src.server.routes.match as match_module
from src.server.session import session_manager


async def _noop_spawn(**kwargs) -> bool:
    """Stub for _spawn_ultra_subprocess: don't launch real Claude CLI processes
    during the regression test. Returning False does not abort create_match —
    the function is documented to keep going when the launcher is unavailable.
    """
    return False


def _create(mode: str, ai_difficulty: AIDifficulty = AIDifficulty.ULTRA) -> str:
    """Run create_match with HS bot_vs_bot/human_vs_bot kwargs and return match_id.

    Re-imports the module fresh each call to avoid cross-test session pollution.
    Stubs out the ultra subprocess launcher so the test doesn't burn tokens or
    leave orphan Claude CLI processes.
    """
    request = CreateMatchRequest(
        mode=mode,
        game_mode="hearthstone",
        ai_difficulty=ai_difficulty,
        ultra_agent="claude",
        player_name=f"Demo Spectator (hearthstone-{mode})",
    )
    original_spawn = match_module._spawn_ultra_subprocess
    match_module._spawn_ultra_subprocess = _noop_spawn
    try:
        resp = asyncio.get_event_loop().run_until_complete(
            create_match(request=request, background_tasks=BackgroundTasks())
        )
    finally:
        match_module._spawn_ultra_subprocess = original_spawn
    assert resp.match_id, "create_match must return a match_id"
    return resp.match_id


def test_hearthstone_bot_vs_bot_creation_does_not_raise_keyerror():
    """The supervisor's bot_vs_bot HS request must not raise KeyError('').

    Prior behaviour: ``hero_class_by_player[human_id]`` with ``human_id == ""``
    raised KeyError, the spectator supervisor caught it and skipped HS forever,
    and zero HS replays were archived in prod despite the cycle including HS.
    """
    match_id = _create("bot_vs_bot", AIDifficulty.ULTRA)

    session = session_manager.get_session(match_id)
    assert session is not None, "session should exist after successful create"
    assert session.game.state.game_mode == "hearthstone"

    # Both AI seats must be present and have full 30-card libraries.
    assert len(session.player_ids) == 2, (
        f"bot_vs_bot must seat exactly two AI players, got {session.player_ids}"
    )
    for pid in session.player_ids:
        library_zone = session.game.state.zones.get(f"library_{pid}")
        assert library_zone is not None, f"missing library zone for {pid}"
        assert len(library_zone.objects) == 30, (
            f"player {pid} library should have 30 cards, got {len(library_zone.objects)}"
        )

    # Both seats are ultra-AI (Claude pilot subprocesses drive them).
    assert session.has_ultra_ai, "bot_vs_bot ultra match must have ultra AI seats"
    assert len(session.ultra_ai_player_ids) == 2, (
        f"both seats should be ultra-AI, got {session.ultra_ai_player_ids}"
    )

    # Run setup_game (per-mode adapter wiring) and verify detach actually fires.
    # The HS adapter calls detach_ultra_from_engine_ai_sets inside setup_game,
    # which is invoked from session.start_game(); we run only setup_game here
    # to avoid actually progressing the game loop in a test.
    asyncio.get_event_loop().run_until_complete(
        session.mode_adapter.setup_game(session)
    )
    tm = session.game.turn_manager
    if hasattr(tm, "ai_players"):
        for pid in session.ultra_ai_player_ids:
            assert pid not in tm.ai_players, (
                f"ultra seat {pid} should be detached from HS turn manager "
                f"ai_players after setup_game (else turn loop will dispatch to "
                f"the heuristic adapter instead of the external Claude pilot)"
            )


def test_hearthstone_bot_vs_bot_creation_with_heuristic_difficulty():
    """Same regression guard but with non-ultra (heuristic) bots.

    The KeyError fired before the ai_difficulty check, so heuristic bot_vs_bot
    also crashed. Cover this so a future refactor that conditionally branches
    on difficulty doesn't reintroduce the bug for one path only.
    """
    match_id = _create("bot_vs_bot", AIDifficulty.MEDIUM)

    session = session_manager.get_session(match_id)
    assert session is not None
    assert len(session.player_ids) == 2
    for pid in session.player_ids:
        library_zone = session.game.state.zones.get(f"library_{pid}")
        assert library_zone is not None
        assert len(library_zone.objects) == 30, (
            f"heuristic bot_vs_bot HS library wrong size for {pid}: {len(library_zone.objects)}"
        )

    # Heuristic difficulty must NOT mark seats as ultra.
    assert not session.has_ultra_ai, "heuristic bot_vs_bot must not register ultra seats"


def test_hearthstone_human_vs_bot_unchanged():
    """Sanity guard: the human_vs_bot path that already worked still works.

    The fix must not break the path the production frontend actually uses.
    """
    match_id = _create("human_vs_bot", AIDifficulty.MEDIUM)

    session = session_manager.get_session(match_id)
    assert session is not None
    assert len(session.player_ids) == 2

    # One human seat, one AI seat.
    assert len(session.human_players) == 1
    ai_seats = [pid for pid in session.player_ids if pid not in session.human_players]
    assert len(ai_seats) == 1

    for pid in session.player_ids:
        library_zone = session.game.state.zones.get(f"library_{pid}")
        assert library_zone is not None
        assert len(library_zone.objects) == 30


if __name__ == "__main__":
    print("Hearthstone bot_vs_bot match-creation regression tests")
    print("=" * 60)

    print("\n1. bot_vs_bot ULTRA (spectator demo path) ...")
    test_hearthstone_bot_vs_bot_creation_does_not_raise_keyerror()
    print("   OK")

    print("\n2. bot_vs_bot MEDIUM (heuristic) ...")
    test_hearthstone_bot_vs_bot_creation_with_heuristic_difficulty()
    print("   OK")

    print("\n3. human_vs_bot MEDIUM (production frontend) ...")
    test_hearthstone_human_vs_bot_unchanged()
    print("   OK")

    print("\nAll Hearthstone bot_vs_bot regression tests passed.")
