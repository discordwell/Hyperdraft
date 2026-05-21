"""Server-side dispatch tests for CATS_KNOCK_OVER.

The cats engine ships ``activate_pile_card`` + ``make_pile_activated`` (the
P1-punchlist primitives). This test verifies the server adapter exposes
them via a CATS_KNOCK_OVER action that:

  1. Rejects when card_id is missing
  2. Rejects cards not in the player's piles
  3. Rejects tapped cards
  4. Rejects cards with no registered handler
  5. Activates the card on a successful call (taps it, fires effect)
  6. Surfaces is_activatable=True in the serialized state on the viewer's
     own pile card

No card in the current 60-card pool uses pile-tap activation, so we wire
a synthetic Cat with a `make_pile_activated` interceptor for the test.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.cats import (  # noqa: E402
    _make_object_from_def,
    make_cat_card,
    make_pile_activated,
)
from src.engine.types import (  # noqa: E402
    Event,
    EventType,
    ZoneType,
)
from src.server.models import (  # noqa: E402
    ActionType,
    CreateMatchRequest,
    PlayerActionRequest,
)
from src.server.routes import match as match_routes  # noqa: E402
from src.server.routes.match import create_match  # noqa: E402
from src.server.session import session_manager  # noqa: E402


@pytest.fixture(autouse=True)
def _suppress_ultra_subprocess_spawn(monkeypatch):
    """Unit tests should not spawn background ultra-agent subprocesses."""
    async def _noop(**_kwargs):
        return True
    monkeypatch.setattr(match_routes, "_spawn_ultra_subprocess", _noop)


async def _create_cats_session():
    """Create a cats match session for testing. Returns (session, human_id, ai_id)."""
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
    session = session_manager.get_session(response.match_id)
    return session, response.player_id, response.opponent_id


def _wire_activator_card(state, player_id: str, pile: str = "pile_territory") -> tuple[str, dict]:
    """Construct a synthetic activator Cat, place it in the player's pile, and
    register its CATS_KNOCK_OVER interceptor. Returns (card_id, counter_dict).

    The counter_dict tracks how many times the effect fires; tests can read
    counter_dict["count"] to verify activation happened.
    """
    counter = {"count": 0, "last_payload": None}

    def effect_fn(event, state):
        counter["count"] += 1
        counter["last_payload"] = dict(event.payload)
        # Emit a DRAW so the effect has a visible side-effect — _process_cats_effect_events
        # will pull a card into the player's hand.
        return [Event(
            type=EventType.DRAW,
            payload={"player": event.payload["player"], "amount": 1},
            source=event.source,
        )]

    def setup_interceptors_fn(obj, state):
        return [make_pile_activated(obj, pile, effect_fn)]

    cat_def = make_cat_card(
        name="Synthetic Activator",
        value=5,
        category="Sleek",
        setup_interceptors=setup_interceptors_fn,
    )
    obj = _make_object_from_def(state, cat_def, player_id, ZoneType.HAND)
    # Pretend it's already in the pile (skip the trick-and-claim cycle).
    state.cats_piles[player_id][pile].append(obj.id)
    pile_zone_type = {
        "pile_territory": ZoneType.CATS_PILE_TERRITORY,
        "pile_nap": ZoneType.CATS_PILE_NAP,
        "pile_snack": ZoneType.CATS_PILE_SNACK,
        "pile_attention": ZoneType.CATS_PILE_ATTENTION,
    }[pile]
    obj.zone = pile_zone_type
    obj.state.tapped = False
    # Register the interceptor.
    for ic in setup_interceptors_fn(obj, state):
        state.interceptors[ic.id] = ic
        obj.interceptor_ids.append(ic.id)
    return obj.id, counter


def test_knock_over_dispatch_rejects_missing_card_id():
    """CATS_KNOCK_OVER with no card_id is rejected at the dispatch boundary."""

    async def _run():
        session, human_id, _ = await _create_cats_session()
        request = PlayerActionRequest(
            action_type=ActionType.CATS_KNOCK_OVER,
            player_id=human_id,
            # card_id intentionally absent
        )
        ok, msg = await session.handle_action(request)
        assert not ok, "missing card_id should be rejected"
        assert "card_id" in msg.lower()
        await session_manager.remove_session(session.id)

    asyncio.run(_run())


def test_knock_over_dispatch_rejects_card_not_in_pile():
    """A card_id that exists but is not in any of the player's piles is rejected."""

    async def _run():
        session, human_id, _ = await _create_cats_session()
        # Grab a card from the player's hand — by design that's not in a pile.
        hand_zone = session.game.state.zones[f"HAND_{human_id}"]
        hand_card_id = hand_zone.objects[0]
        request = PlayerActionRequest(
            action_type=ActionType.CATS_KNOCK_OVER,
            player_id=human_id,
            card_id=hand_card_id,
        )
        ok, msg = await session.handle_action(request)
        assert not ok
        assert "pile" in msg.lower()
        await session_manager.remove_session(session.id)

    asyncio.run(_run())


def test_knock_over_dispatch_rejects_card_without_handler():
    """A pile card with no registered CATS_KNOCK_OVER handler is rejected."""

    async def _run():
        session, human_id, _ = await _create_cats_session()
        # Take a card from the hand and put it in the territory pile directly
        # (no interceptor wired).
        hand_zone = session.game.state.zones[f"HAND_{human_id}"]
        card_id = hand_zone.objects[0]
        hand_zone.objects.remove(card_id)
        session.game.state.cats_piles[human_id]["pile_territory"].append(card_id)
        session.game.state.objects[card_id].zone = ZoneType.CATS_PILE_TERRITORY
        session.game.state.objects[card_id].state.tapped = False

        request = PlayerActionRequest(
            action_type=ActionType.CATS_KNOCK_OVER,
            player_id=human_id,
            card_id=card_id,
        )
        ok, msg = await session.handle_action(request)
        assert not ok
        assert "ability" in msg.lower() or "no" in msg.lower()
        await session_manager.remove_session(session.id)

    asyncio.run(_run())


def test_knock_over_dispatch_activates_card_with_handler():
    """A pile card with a wired CATS_KNOCK_OVER handler fires its effect."""

    async def _run():
        session, human_id, _ = await _create_cats_session()
        card_id, counter = _wire_activator_card(session.game.state, human_id)
        hand_before = len(session.game.state.zones[f"HAND_{human_id}"].objects)
        obj = session.game.state.objects[card_id]
        assert not obj.state.tapped

        request = PlayerActionRequest(
            action_type=ActionType.CATS_KNOCK_OVER,
            player_id=human_id,
            card_id=card_id,
        )
        ok, msg = await session.handle_action(request)
        assert ok, f"activation failed: {msg}"
        assert counter["count"] == 1, "effect_fn should have fired exactly once"
        assert obj.state.tapped, "card should be tapped after activation"
        hand_after = len(session.game.state.zones[f"HAND_{human_id}"].objects)
        assert hand_after == hand_before + 1, "DRAW event should have drawn one card"
        await session_manager.remove_session(session.id)

    asyncio.run(_run())


def test_knock_over_dispatch_rejects_tapped_card():
    """Once tapped, the card can't be activated again until untap."""

    async def _run():
        session, human_id, _ = await _create_cats_session()
        card_id, counter = _wire_activator_card(session.game.state, human_id)

        # First activation succeeds.
        request = PlayerActionRequest(
            action_type=ActionType.CATS_KNOCK_OVER,
            player_id=human_id,
            card_id=card_id,
        )
        ok, _ = await session.handle_action(request)
        assert ok
        assert counter["count"] == 1

        # Second activation should fail because the card is now tapped.
        ok, msg = await session.handle_action(request)
        assert not ok
        assert "tapped" in msg.lower() or "knocked over" in msg.lower()
        assert counter["count"] == 1, "tapped card should not re-fire"
        await session_manager.remove_session(session.id)

    asyncio.run(_run())


def test_serialized_state_marks_is_activatable_on_viewers_pile_card():
    """The cats wire payload exposes is_activatable=True for the viewer's own
    untapped pile card with a registered handler.
    """

    async def _run():
        session, human_id, _ = await _create_cats_session()
        card_id, _ = _wire_activator_card(session.game.state, human_id)

        # Pull the viewer-relative serialized state.
        cats_dto = session._serialize_cats_state(session.game.state, human_id)
        assert cats_dto is not None
        territory_cards = cats_dto["player"]["piles"]["territory"]
        # find the synthetic card
        matched = [c for c in territory_cards if c["id"] == card_id]
        assert matched, f"card {card_id} not present in territory pile DTO"
        assert matched[0].get("is_activatable") is True, (
            f"is_activatable should be True; got dto={matched[0]}"
        )
        # Opponent's pile cards should not have is_activatable populated.
        opp_territory = cats_dto["opponent"]["piles"]["territory"]
        for c in opp_territory:
            assert "is_activatable" not in c or c.get("is_activatable") is False, (
                "is_activatable should not appear on opponent pile cards"
            )

        # After activation, is_activatable should flip to False (tapped).
        request = PlayerActionRequest(
            action_type=ActionType.CATS_KNOCK_OVER,
            player_id=human_id,
            card_id=card_id,
        )
        await session.handle_action(request)
        cats_dto = session._serialize_cats_state(session.game.state, human_id)
        territory_cards = cats_dto["player"]["piles"]["territory"]
        matched = [c for c in territory_cards if c["id"] == card_id]
        assert matched[0].get("is_activatable") is False, (
            "after tap, is_activatable should be False"
        )
        await session_manager.remove_session(session.id)

    asyncio.run(_run())
