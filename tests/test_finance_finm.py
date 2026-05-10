"""Focused tests for the FINM Market Meltdown Finance expansion."""

from __future__ import annotations

import sys
import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.cards.finance.finm import FINM_CARDS, FINM_STARTER_DECKS  # noqa: E402
from src.engine.finance import setup_finance_player  # noqa: E402
from src.engine.finance_turn import FinanceTurnManager  # noqa: E402
from src.engine.game import Game  # noqa: E402
from src.engine.queries import get_power, get_toughness  # noqa: E402
from src.engine.types import CardType, Event, EventType, ZoneType  # noqa: E402


def _make_game():
    game = Game(mode="finance")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    setup_finance_player(game, p1)
    setup_finance_player(game, p2)
    p1.mana_crystals = p1.mana_crystals_available = 10
    p2.mana_crystals = p2.mana_crystals_available = 10
    return game, p1, p2


def _place(game, player_id: str, name: str):
    card_def = FINM_CARDS[name]
    obj = game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.state.summoning_sickness = False
    obj.state.tapped = False
    return obj


def _fire_etb(game, obj):
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=obj.id,
        controller=obj.controller,
    ))


def test_finm_loads_180_cards_and_six_decks():
    assert len(FINM_CARDS) == 180
    assert len(FINM_STARTER_DECKS) == 6
    for builder in FINM_STARTER_DECKS.values():
        deck = builder()
        assert len(deck) == 40
        assert all(card.domain == "FINM" for card in deck)


def test_finm_cards_have_playable_shapes():
    type_counts = {ctype: 0 for ctype in (
        CardType.FIN_TRADER,
        CardType.FIN_ORDER,
        CardType.FIN_STRATEGY,
        CardType.FIN_ASSET,
        CardType.FIN_STRUCTURE,
        CardType.FIN_DERIVATIVE,
    )}
    for card in FINM_CARDS.values():
        assert card.mana_cost.startswith("{")
        assert card.text
        assert card.characteristics.types
        for ctype in type_counts:
            if ctype in card.characteristics.types:
                type_counts[ctype] += 1
    assert type_counts[CardType.FIN_TRADER] == 60
    assert type_counts[CardType.FIN_ORDER] >= 20
    assert type_counts[CardType.FIN_STRATEGY] >= 20
    assert type_counts[CardType.FIN_DERIVATIVE] == 18


def test_covenant_and_coupon_pre_market_income():
    game, p1, p2 = _make_game()
    p1.life = 18
    p2.life = 22
    p1.mana_crystals_available = 3
    _place(game, p1.id, "Covenant Director")
    _place(game, p1.id, "Coupon Bill Vault")

    game.emit(Event(
        type=EventType.PHASE_START,
        payload={"phase": "pre_market", "player": p1.id},
        controller=p1.id,
    ))

    assert p1.mana_crystals_available >= 6
    assert p1.life == 18


def test_covenant_and_coupon_income_survives_real_pre_market_refill():
    game, p1, p2 = _make_game()
    p1.life = 18
    p2.life = 22
    p1.mana_crystals = 3
    p1.mana_crystals_available = 0
    _place(game, p1.id, "Covenant Director")
    _place(game, p1.id, "Coupon Bill Vault")

    tm = FinanceTurnManager(game.state)
    game.turn_manager = tm

    asyncio.run(tm._run_pre_market(p1.id))

    assert p1.mana_crystals == 4
    assert p1.mana_crystals_available == 7
    assert p1.mana_crystals_available > p1.mana_crystals


def test_hedge_reduces_first_damage_each_turn():
    game, p1, p2 = _make_game()
    obj = _place(game, p1.id, "Hedge Specialist")
    game.state.turn_number = 7

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": obj.id, "amount": 3, "source": "test", "is_finance": True},
        source="test",
        controller=p2.id,
    ))

    assert obj.state.damage == 2


def test_all_in_etb_pumps_when_liquidity_empty():
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 0
    obj = _place(game, p1.id, "All-In Director")
    events = _fire_etb(game, obj)

    assert any(e.type == EventType.PT_MODIFICATION for e in events)


def test_restructure_death_refunds_liquidity():
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 0
    obj = _place(game, p1.id, "Restructure Partner")

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": obj.id, "reason": "test"},
        source="test",
        controller=p1.id,
    ))

    assert p1.mana_crystals_available >= 2


def test_buyback_spell_counter_and_derivative_buff():
    game, p1, _ = _make_game()
    trader = _place(game, p1.id, "Buyback Analyst")
    order = _place(game, p1.id, "Buyback Term Sheet")
    deriv = _place(game, p1.id, "Buyback Earnout Clause")
    deriv.state.attached_to = trader.id

    before_power = get_power(trader, game.state)
    game.emit(Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": p1.id, "object_id": order.id},
        source=order.id,
        controller=p1.id,
    ))
    game.emit(Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": p1.id, "object_id": order.id},
        source=order.id,
        controller=p1.id,
    ))
    game.emit(Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": p1.id, "object_id": order.id},
        source=order.id,
        controller=p1.id,
    ))

    assert trader.state.counters.get("+1/+1", 0) >= 1
    assert get_power(trader, game.state) > before_power


def test_buyback_count_persists_across_turns_to_match_text():
    game, p1, _ = _make_game()
    trader = _place(game, p1.id, "Buyback Analyst")
    order = _place(game, p1.id, "Buyback Term Sheet")

    assert "Order or Strategy you cast gives this" in FINM_CARDS["Buyback Analyst"].text
    assert "this turn" not in FINM_CARDS["Buyback Analyst"].text.lower()

    for _ in range(2):
        game.emit(Event(
            type=EventType.FIN_PLAY_CARD,
            payload={"controller": p1.id, "object_id": order.id},
            source=order.id,
            controller=p1.id,
        ))

    assert trader.state.counters.get("+1/+1", 0) == 0
    asyncio.run(game.turn_manager._emit_turn_end())

    game.emit(Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": p1.id, "object_id": order.id},
        source=order.id,
        controller=p1.id,
    ))

    assert trader.state.counters.get("+1/+1", 0) == 1


def test_destroy_small_rejects_big_or_nonhostile_explicit_target():
    game, p1, p2 = _make_game()
    own_trader = _place(game, p1.id, "Coupon Associate")
    big_enemy = _place(game, p2.id, "Coupon Chief")
    resolve = FINM_CARDS["Hedge Stop Loss"].resolve

    for target in (own_trader, big_enemy):
        events = resolve(Event(
            type=EventType.FIN_PLAY_CARD,
            payload={
                "controller": p1.id,
                "source_id": "test",
                "target_id": target.id,
                "targets": [target.id],
            },
            source="test",
            controller=p1.id,
        ), game.state)
        assert events == []
        assert target.zone == ZoneType.BATTLEFIELD


def test_destroy_small_fallback_selects_legal_hostile_trader_only():
    game, p1, p2 = _make_game()
    big_enemy = _place(game, p2.id, "Coupon Chief")
    small_enemy = _place(game, p2.id, "Coupon Associate")
    resolve = FINM_CARDS["Hedge Stop Loss"].resolve

    events = resolve(Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": p1.id, "source_id": "test", "targets": []},
        source="test",
        controller=p1.id,
    ), game.state)

    destroyed_ids = [event.payload.get("object_id") for event in events]
    assert destroyed_ids == [small_enemy.id]
    assert big_enemy.id not in destroyed_ids


def test_destroy_small_uses_effective_defense_for_explicit_target():
    game, p1, p2 = _make_game()
    boosted_enemy = _place(game, p2.id, "Covenant Associate")
    derivative = _place(game, p2.id, "Covenant Priming Lien")
    derivative.state.attached_to = boosted_enemy.id

    assert boosted_enemy.characteristics.toughness == 3
    assert get_toughness(boosted_enemy, game.state) == 5

    events = FINM_CARDS["Hedge Stop Loss"].resolve(Event(
        type=EventType.FIN_PLAY_CARD,
        payload={
            "controller": p1.id,
            "source_id": "test",
            "target_id": boosted_enemy.id,
            "targets": [boosted_enemy.id],
        },
        source="test",
        controller=p1.id,
    ), game.state)

    assert events == []
    assert boosted_enemy.zone == ZoneType.BATTLEFIELD
