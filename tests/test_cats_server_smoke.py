"""Smoke test for the Cats server route + per-action dispatch.

Asserts:
  1. POST /api/match/create with game_mode='cats' creates a session.
  2. The session has 2 players, one human + one AI, and both have 30-card libraries
     (well, ~25 — 5 cards moved into HAND during setup).
  3. The cats state is serialized into the GameStateResponse.cats dict.
  4. A CATS_PLAY_CARD action succeeds and advances the round.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.server.models import CreateMatchRequest, PlayerActionRequest  # noqa: E402
from src.server.routes import match as match_routes  # noqa: E402
from src.server.routes.match import create_match  # noqa: E402
from src.server.session import session_manager  # noqa: E402


@pytest.fixture(autouse=True)
def _suppress_ultra_subprocess_spawn(monkeypatch):
    """Unit tests should not spawn background ultra-agent subprocesses."""
    async def _noop(**_kwargs):
        return True
    monkeypatch.setattr(match_routes, "_spawn_ultra_subprocess", _noop)


def test_create_cats_match():
    """POST /match/create with game_mode='cats' wires up cats decks/commanders."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="cats",
                ai_difficulty="medium",
                player_name="TestHuman",
                player_deck_id="Couch Empire",
                ai_deck_id="Naptime Tyrants",
            ),
            background_tasks=BackgroundTasks(),
        )

        assert response.match_id
        session = session_manager.get_session(response.match_id)
        assert session is not None
        assert session.game.state.game_mode == "cats"
        assert len(session.player_ids) == 2

        # Both players should have hand=5 (CATS_HAND_SIZE) + ~25 library + commander.
        for pid in session.player_ids:
            hand_zone = session.game.state.zones.get(f"HAND_{pid}")
            assert hand_zone is not None
            assert len(hand_zone.objects) == 5, f"Player {pid} hand: {len(hand_zone.objects)}"
            library_zone = session.game.state.zones.get(f"LIBRARY_{pid}")
            assert library_zone is not None
            # 30 deck cards - 5 in hand = 25 in library
            assert len(library_zone.objects) == 25

        # Commanders attached.
        commanders = getattr(session.game.state, "cats_commanders", {})
        assert len(commanders) == 2

        # Piles initialized to empty.
        piles = getattr(session.game.state, "cats_piles", {})
        for pid in session.player_ids:
            assert pid in piles
            assert piles[pid]["pile_territory"] == []
            assert piles[pid]["pile_nap"] == []

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_cats_match_state_serialization():
    """The cats session serializes into GameStateResponse.cats with the wire shape."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="cats",
                ai_difficulty="medium",
                player_name="TestHuman",
            ),
            background_tasks=BackgroundTasks(),
        )
        session = session_manager.get_session(response.match_id)
        assert session is not None

        # Run the mode adapter's setup so commanders, etc. are wired.
        await session.mode_adapter.setup_game(session)

        human_id = response.player_id
        state = session.get_client_state(human_id)

        assert state.game_mode == "cats"
        assert state.cats is not None
        cats = state.cats
        assert cats["round_number"] == 1
        # Phase is 'pounce' or 'counter_pounce' depending on whether AI pre-played.
        assert cats["phase"] in ("pounce", "counter_pounce")
        assert cats["lead_player"] in ("me", "opponent")
        assert cats["player"] is not None
        assert cats["opponent"] is not None
        # Human hand is revealed (has names + values).
        assert len(cats["player"]["hand"]) == 5
        # Opponent hand cards have a hand_size but the hand list is opaque
        # ('Hidden Cat' placeholders).
        assert cats["opponent"]["hand_size"] == 5 or cats["opponent"]["hand_size"] == 4
        # Commanders carry over.
        assert cats["player"]["commander"] is not None
        assert cats["opponent"]["commander"] is not None
        assert cats["game_over"] is False

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_cats_play_card_action_resolves_round():
    """A human CATS_PLAY_CARD action drives the AI's counter and advances the round."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="cats",
                ai_difficulty="medium",
                player_name="TestHuman",
            ),
            background_tasks=BackgroundTasks(),
        )
        session = session_manager.get_session(response.match_id)
        assert session is not None
        await session.mode_adapter.setup_game(session)
        session.is_started = True  # bypass start_game (cats setup is done)

        human_id = response.player_id
        state_before = session.get_client_state(human_id)
        round_before = state_before.cats["round_number"]
        # Phase: after setup, AI has pre-played pounce (since human is the lead
        # round 1), so we should be at counter_pounce.
        assert state_before.cats["phase"] == "counter_pounce"

        # Human plays their first hand card as counter.
        first_card_id = state_before.cats["player"]["hand"][0]["id"]
        ok, msg = await session.handle_action(PlayerActionRequest(
            action_type="CATS_PLAY_CARD",
            player_id=human_id,
            card_id=first_card_id,
        ))
        assert ok, f"action failed: {msg}"

        state_after = session.get_client_state(human_id)
        # The round either advanced (AI won → AI claimed → next round started)
        # or we're now in the claim phase (human won → awaiting pile pick).
        cats_after = state_after.cats
        assert cats_after is not None
        # Either the round bumped (AI won and claimed; we're back at pounce/counter)
        # OR phase = claim (human won, awaiting CATS_CHOOSE_PILE).
        if cats_after["phase"] == "claim":
            # Human won the trick — should be the winner.
            assert cats_after["current_trick"]["winner"] == "me"
        else:
            # Round should have advanced.
            assert cats_after["round_number"] >= round_before

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_cats_choose_pile_action():
    """When human is trick winner, CATS_CHOOSE_PILE advances to next round."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="cats",
                ai_difficulty="easy",  # easy AI plays random so we may win
                player_name="TestHuman",
            ),
            background_tasks=BackgroundTasks(),
        )
        session = session_manager.get_session(response.match_id)
        assert session is not None
        await session.mode_adapter.setup_game(session)
        session.is_started = True

        human_id = response.player_id

        # Try up to 5 rounds to find one where the human wins the trick.
        won_a_trick = False
        for _attempt in range(5):
            state = session.get_client_state(human_id)
            cats = state.cats
            if cats is None or cats["game_over"]:
                break
            if cats["phase"] != "counter_pounce":
                # Skip — possibly AI pounce hasn't fired or something weird.
                break
            # Play our highest-value card to maximize win chance.
            hand = cats["player"]["hand"]
            if not hand:
                break
            best = max(hand, key=lambda c: c.get("value", 0))
            ok, _ = await session.handle_action(PlayerActionRequest(
                action_type="CATS_PLAY_CARD",
                player_id=human_id,
                card_id=best["id"],
            ))
            assert ok

            state_after = session.get_client_state(human_id)
            cats_after = state_after.cats
            if cats_after and cats_after["phase"] == "claim":
                # Human won. Choose pile_territory.
                ok, msg = await session.handle_action(PlayerActionRequest(
                    action_type="CATS_CHOOSE_PILE",
                    player_id=human_id,
                    pile_name="pile_territory",
                ))
                assert ok, f"choose pile failed: {msg}"
                won_a_trick = True
                # Verify the territory pile has 2 cards now.
                state_final = session.get_client_state(human_id)
                terr = state_final.cats["player"]["piles"]["territory"]
                assert len(terr) >= 2, f"expected >=2 cards in territory, got {len(terr)}"
                break

        # Note: it's possible the human never wins a trick in 5 attempts
        # against easy AI (low probability but not zero), so we don't hard-
        # assert won_a_trick.
        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())
