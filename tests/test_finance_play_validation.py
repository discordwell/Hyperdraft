"""Finance card-play boundary validation tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.cards.finance.finm import FINM_CARDS  # noqa: E402
from src.engine.finance import setup_finance_player  # noqa: E402
from src.engine.finance_stack import FinanceStackItem  # noqa: E402
from src.engine.game import Game  # noqa: E402
from src.engine.types import ZoneType  # noqa: E402


def _make_game():
    game = Game(mode="finance")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    setup_finance_player(game, p1)
    setup_finance_player(game, p2)
    p1.mana_crystals = p1.mana_crystals_available = 10
    p2.mana_crystals = p2.mana_crystals_available = 10
    return game, p1, p2


def _make_card(game, player_id: str, name: str, zone: ZoneType = ZoneType.HAND):
    card_def = FINM_CARDS[name]
    return game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_finance_player_cannot_play_opponent_hand_card():
    game, p1, p2 = _make_game()
    opponent_card = _make_card(game, p2.id, "Hedge Stop Loss")
    starting_liquidity = p1.mana_crystals_available

    events = asyncio.run(game.turn_manager._play_card_action(p1.id, opponent_card.id, []))

    assert events == []
    assert p1.mana_crystals_available == starting_liquidity
    assert opponent_card.zone == ZoneType.HAND
    assert opponent_card.id in game.state.zones[f"hand_{p2.id}"].objects


def test_finance_player_cannot_play_own_non_hand_card():
    game, p1, _ = _make_game()
    graveyard_card = _make_card(game, p1.id, "Hedge Stop Loss", ZoneType.GRAVEYARD)
    starting_liquidity = p1.mana_crystals_available

    events = asyncio.run(game.turn_manager._play_card_action(p1.id, graveyard_card.id, []))

    assert events == []
    assert p1.mana_crystals_available == starting_liquidity
    assert graveyard_card.zone == ZoneType.GRAVEYARD
    assert graveyard_card.id in game.state.zones[f"graveyard_{p1.id}"].objects


def test_finance_response_play_requires_actor_hand_card():
    game, p1, p2 = _make_game()
    opponent_card = _make_card(game, p2.id, "Hedge Stop Loss")
    game.turn_manager.fin_stack.push(FinanceStackItem(card_id="test-stack-card", controller=p2.id))
    starting_liquidity = p1.mana_crystals_available

    events = asyncio.run(game.turn_manager._cast_response_to_stack(p1.id, opponent_card.id, []))

    assert events == []
    assert p1.mana_crystals_available == starting_liquidity
    assert game.turn_manager.fin_stack.depth() == 1
    assert opponent_card.zone == ZoneType.HAND
    assert opponent_card.id in game.state.zones[f"hand_{p2.id}"].objects
