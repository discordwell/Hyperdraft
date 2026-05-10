"""Constructed Finance deck registry tests."""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

from fastapi import BackgroundTasks

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.cards.finance import (  # noqa: E402
    FINANCE_CARDS,
    FINANCE_CONSTRUCTED_DECKS,
    FINANCE_DECKS,
)
from src.engine.game import Game  # noqa: E402
from src.engine.types import ZoneType  # noqa: E402
from src.server.models import CreateMatchRequest  # noqa: E402
from src.server.routes.match import create_match  # noqa: E402
from src.server.session import session_manager  # noqa: E402


def test_finance_voltron_premium_registered_and_legal():
    assert "FINX_voltron_premium" in FINANCE_CONSTRUCTED_DECKS
    assert FINANCE_DECKS["FINX_voltron_premium"] is FINANCE_CONSTRUCTED_DECKS["FINX_voltron_premium"]

    deck = FINANCE_CONSTRUCTED_DECKS["FINX_voltron_premium"]()
    counts = Counter(card.name for card in deck)

    assert len(deck) == 40
    assert set(counts) <= set(FINANCE_CARDS)
    assert max(counts.values()) <= 4


def test_finance_voltron_premium_uses_fina_and_finm_cards():
    deck = FINANCE_CONSTRUCTED_DECKS["FINX_voltron_premium"]()
    domains = Counter(card.domain for card in deck)

    assert domains["FINA"] == 38
    assert domains["FINM"] == 2
    assert domains["FINM"] == Counter(card.name for card in deck)["All-In Control Premium"]


def test_create_match_finance_respects_finm_and_finx_deck_ids():
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="finance",
                player_deck_id="FINM_treasury_coupon",
                ai_deck_id="FINX_voltron_premium",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None
        try:
            human_id, ai_id = session.player_ids[:2]
            human_library = session.game.state.zones[f"library_{human_id}"]
            ai_library = session.game.state.zones[f"library_{ai_id}"]
            human_names = [session.game.state.objects[oid].name for oid in human_library.objects]
            ai_names = [session.game.state.objects[oid].name for oid in ai_library.objects]

            assert len(human_names) == 40
            assert len(ai_names) == 40
            assert "Coupon Bill Vault" in human_names
            assert "All-In Control Premium" in ai_names
            assert "Speed Trade" not in human_names
        finally:
            await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_finance_wet_test_resolves_finm_and_finx_decks():
    from scripts.play.finance_wet_test import _resolve_deck

    finm = _resolve_deck("FINM_treasury_coupon")
    finx = _resolve_deck("FINX_voltron_premium")

    assert len(finm) == 40
    assert len(finx) == 40
    assert any(card.name == "Coupon Bill Vault" for card in finm)
    assert any(card.name == "All-In Control Premium" for card in finx)


def test_finance_tournament_cast_tracker_reads_hand_zone():
    from scripts.play.finance_tournament import CardTracker, TrackingAI

    class DummyAI:
        def __init__(self, card_id: str):
            self.card_id = card_id

        def choose_play_action(self, state, player_id):
            return {"type": "play_card", "card_id": self.card_id}

    game = Game(mode="finance")
    player = game.add_player("P1")
    card_def = FINANCE_DECKS["FINM_treasury_coupon"]()[0]
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )

    tracker = CardTracker()
    ai = TrackingAI(DummyAI(obj.id), "FINM_treasury_coupon", tracker)
    ai.choose_play_action(game.state, player.id)

    scores = tracker.to_card_scores()
    assert scores[f"FINM_treasury_coupon::{card_def.name}"]["cast"] == 1
