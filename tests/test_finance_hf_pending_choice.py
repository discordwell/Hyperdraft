"""
Tests for Phase 4 migration of remaining HIGH-FREQUENCY deterministic-pick
cards onto ``PendingChoice``.

Migrated cards (9):

    Dark Pool Flash Order   (Dark Pool, target damage)
    Sub-Penny Intercept     (Market Order, target attacker -2/-0)
    Pre-Market Raid         (Market Order, target 1 damage)
    Spoofed Bid             (Dark Pool, target -3/-0)
    Cancel Order            (Market Order, target tap)
    Quote Stuffing Burst    (Market Order, target friendly +3/+0 + AS)
    Circuit Breaker Trip    (Market Order, target destroy ≥Aggr 4)
    Regulatory Halt         (Dark Pool, target tap)
    Pump-and-Dump           (Strategy, target friendly +4/+0 + 2 Lev)

For each card we verify:
  - human-path: emits a ``PendingChoice`` with the right type and options,
    and the underlying effect (damage / destroy / tap / PT_MOD) is NOT
    applied yet (the human still has to submit a choice).
  - heuristic_pick: matches the documented AI fallback target.
  - empty short-circuit: no candidates → no ``PendingChoice``, no events,
    ``fin_stack`` depth unchanged (key guarantee: mid-stack the engine's
    response stack must not be corrupted by an unsatisfiable choice).
  - AI inline auto-resolve: if controller is AI and there is no
    ``make_choice`` handler, the heuristic_pick fallback path applies the
    effect directly (destroy / damage / etc.) and clears
    ``state.pending_choice``.

Run directly:

    PYTHONPATH=. python tests/test_finance_hf_pending_choice.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                            # noqa: E402
    CardType, EventType, Event, ZoneType,
)
from src.engine.game import Game                          # noqa: E402
from src.engine.finance import setup_finance_player       # noqa: E402
from src.engine.finance_turn import FinanceTurnManager    # noqa: E402
from src.engine.finance_combat import FinanceCombatManager  # noqa: E402

from src.cards.finance.fina.high_frequency import (       # noqa: E402
    FLASH_CRASH_BOT,
    DARK_POOL_FLASH_ORDER,
    SUB_PENNY_INTERCEPT,
    PRE_MARKET_RAID,
    SPOOFED_BID,
    CANCEL_ORDER,
    QUOTE_STUFFING_BURST,
    CIRCUIT_BREAKER_TRIP,
    REGULATORY_HALT,
    PUMP_AND_DUMP,
    _dark_pool_flash_order_effect,
    _sub_penny_intercept_resolve,
    _pre_market_raid_resolve,
    _spoofed_bid_effect,
    _cancel_order_resolve,
    _quote_stuffing_burst_resolve,
    _circuit_breaker_trip_resolve,
    _regulatory_halt_effect,
    _pump_and_dump_resolve,
)
from src.cards.finance.fina.quant import (                # noqa: E402
    STATISTICAL_ARB_CLERK,
)


# ---------------------------------------------------------------------------
# Test scaffolding (copied from test_finance_spice_cards.py)
# ---------------------------------------------------------------------------

def _make_finance_game():
    game = Game(mode="finance")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    setup_finance_player(game, p1)
    setup_finance_player(game, p2)
    tm = FinanceTurnManager(game.state)
    game.turn_manager = tm
    tm.set_turn_order([p1.id, p2.id])
    tm.finance_combat_manager = FinanceCombatManager(game.state, game.pipeline)
    return game, p1, p2


def _put_on_battlefield(game, player_id: str, card_def):
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


def _stage_order(game, controller_id, card_def):
    """Place an Order in EXILE so its setup_interceptors can run."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=controller_id,
        zone=ZoneType.EXILE,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _fin_stack_depth(game):
    fs = getattr(game.state, "fin_stack", None)
    return fs.depth() if fs is not None else 0


def _fire_dark_effect(game, order_obj, effect_fn, *, controller_id=None):
    """For ``_make_dark_pool_setup``-style cards: synthesize a
    FIN_MARKET_EVENT and call the inner effect_fn(event, state, obj)
    directly. Returns the list of events the inner fn produced.
    """
    ev = Event(
        type=EventType.FIN_MARKET_EVENT,
        payload={
            "obj_id": order_obj.id,
            "controller": controller_id or order_obj.controller,
        },
        source=order_obj.id,
        controller=controller_id or order_obj.controller,
    )
    return effect_fn(ev, game.state, order_obj) or []


def _resolve_event(controller_id: str) -> Event:
    return Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": controller_id, "source_id": "test_src"},
        source="test_src",
        controller=controller_id,
    )


# ===========================================================================
# DARK_POOL_FLASH_ORDER (Dark Pool, target 2 damage)
# ===========================================================================

def test_dark_pool_flash_order_human_path_emits_target_choice():
    """Human controller: dark_effect emits a 'target' PendingChoice across
    every opposing Trader. No damage applied yet."""
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, DARK_POOL_FLASH_ORDER)
    order.controller = p1.id
    enemy_a = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    enemy_b = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    dmg_a_before = int(getattr(enemy_a.state, "damage", 0) or 0)
    fs_before = _fin_stack_depth(game)

    out = _fire_dark_effect(game, order, _dark_pool_flash_order_effect)

    pc = game.state.pending_choice
    assert pc is not None, "expected pending_choice for Dark Pool Flash Order"
    assert pc.choice_type == "target"
    assert pc.player == p1.id
    option_ids = {opt["id"] for opt in pc.options}
    assert enemy_a.id in option_ids and enemy_b.id in option_ids
    # Human path: no damage event emitted yet from the dark_effect direct
    # return — the choice handler emits damage AFTER the human picks.
    assert not any(e.type == EventType.DAMAGE for e in (out or []))
    # Object state untouched.
    assert int(getattr(enemy_a.state, "damage", 0) or 0) == dmg_a_before
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Dark Pool Flash Order human-path emits target choice")


def test_dark_pool_flash_order_heuristic_preserves_first_pick():
    """heuristic_pick = first opposing Trader (original behavior)."""
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, DARK_POOL_FLASH_ORDER)
    order.controller = p1.id
    enemy_a = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    _ = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)

    _fire_dark_effect(game, order, _dark_pool_flash_order_effect)

    hp = game.state.pending_choice.callback_data.get("heuristic_pick")
    assert hp == [enemy_a.id], f"expected [{enemy_a.id}], got {hp}"
    print("[PASS] HF Dark Pool Flash Order heuristic preserves first opp pick")


def test_dark_pool_flash_order_no_opp_traders_short_circuits():
    """No opp Traders: no PendingChoice, no events, fin_stack untouched."""
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, DARK_POOL_FLASH_ORDER)
    order.controller = p1.id
    fs_before = _fin_stack_depth(game)

    out = _fire_dark_effect(game, order, _dark_pool_flash_order_effect)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Dark Pool Flash Order short-circuits on empty opp")


def test_dark_pool_flash_order_ai_resolves_inline_to_first_pick():
    """AI controller, no make_choice handler: heuristic_pick fallback fires
    DAMAGE event on the first opp Trader; pending_choice is cleared."""
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    order = _stage_order(game, p1.id, DARK_POOL_FLASH_ORDER)
    order.controller = p1.id
    first = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    _ = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    fs_before = _fin_stack_depth(game)

    out = _fire_dark_effect(game, order, _dark_pool_flash_order_effect)

    assert game.state.pending_choice is None
    dmg = [e for e in (out or []) if e.type == EventType.DAMAGE]
    assert any(
        e.payload.get("target") == first.id and e.payload.get("amount") == 2
        for e in dmg
    ), (
        f"expected 2 DAMAGE on first opp {first.id}, got: "
        f"{[(e.type, e.payload) for e in (out or [])]}"
    )
    assert _fin_stack_depth(game) == fs_before, (
        "fin_stack must not be corrupted by mid-cast PendingChoice resolve"
    )
    print("[PASS] HF Dark Pool Flash Order AI inline resolve")


# ===========================================================================
# SUB_PENNY_INTERCEPT (Market Order, target attacking -2/-0)
# ===========================================================================

def test_sub_penny_intercept_human_path_emits_target_choice():
    """Filter: only attacking opp Traders show up as options."""
    game, p1, p2 = _make_finance_game()
    attacker = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    attacker.state.attacking = True
    non_attacker = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    fs_before = _fin_stack_depth(game)

    out = _sub_penny_intercept_resolve(_resolve_event(p1.id), game.state)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert attacker.id in option_ids
    assert non_attacker.id not in option_ids, (
        "non-attacking opp Traders must NOT be options"
    )
    pt_events = [e for e in (out or []) if e.type == EventType.PT_MODIFICATION]
    assert not pt_events, "human path must not emit PT_MOD before choice"
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Sub-Penny Intercept human-path emits target choice")


def test_sub_penny_intercept_no_attackers_short_circuits():
    """If opp has Traders but none are attacking: no PendingChoice."""
    game, p1, p2 = _make_finance_game()
    _ = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)  # not attacking
    fs_before = _fin_stack_depth(game)

    out = _sub_penny_intercept_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Sub-Penny Intercept short-circuits when no attackers")


def test_sub_penny_intercept_ai_resolves_inline():
    """AI path: heuristic_pick applies -2/-0 to first attacker."""
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    attacker = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    attacker.state.attacking = True

    out = _sub_penny_intercept_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    pt = [e for e in (out or []) if e.type == EventType.PT_MODIFICATION]
    assert any(
        e.payload.get("object_id") == attacker.id and e.payload.get("power_mod") == -2
        for e in pt
    )
    print("[PASS] HF Sub-Penny Intercept AI inline resolve")


# ===========================================================================
# PRE_MARKET_RAID (Market Order, target 1 damage)
# ===========================================================================

def test_pre_market_raid_human_path_emits_target_choice():
    game, p1, p2 = _make_finance_game()
    enemy_a = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    enemy_b = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    fs_before = _fin_stack_depth(game)

    out = _pre_market_raid_resolve(_resolve_event(p1.id), game.state)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert enemy_a.id in option_ids and enemy_b.id in option_ids
    assert not any(e.type == EventType.DAMAGE for e in (out or []))
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Pre-Market Raid human-path emits target choice")


def test_pre_market_raid_no_opp_traders_short_circuits():
    game, p1, p2 = _make_finance_game()
    fs_before = _fin_stack_depth(game)

    out = _pre_market_raid_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Pre-Market Raid short-circuits on empty opp")


def test_pre_market_raid_ai_resolves_inline():
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    first = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    _ = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)

    out = _pre_market_raid_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    dmg = [e for e in (out or []) if e.type == EventType.DAMAGE]
    assert any(
        e.payload.get("target") == first.id and e.payload.get("amount") == 1
        for e in dmg
    )
    print("[PASS] HF Pre-Market Raid AI inline resolve")


# ===========================================================================
# SPOOFED_BID (Dark Pool, target -3/-0)
# ===========================================================================

def test_spoofed_bid_human_path_emits_target_choice():
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, SPOOFED_BID)
    order.controller = p1.id
    enemy_a = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    enemy_b = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    fs_before = _fin_stack_depth(game)

    out = _fire_dark_effect(game, order, _spoofed_bid_effect)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert enemy_a.id in option_ids and enemy_b.id in option_ids
    assert not any(e.type == EventType.PT_MODIFICATION for e in (out or []))
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Spoofed Bid human-path emits target choice")


def test_spoofed_bid_no_opp_traders_short_circuits():
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, SPOOFED_BID)
    order.controller = p1.id
    fs_before = _fin_stack_depth(game)

    out = _fire_dark_effect(game, order, _spoofed_bid_effect)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Spoofed Bid short-circuits on empty opp")


def test_spoofed_bid_ai_resolves_inline():
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    order = _stage_order(game, p1.id, SPOOFED_BID)
    order.controller = p1.id
    first = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)

    out = _fire_dark_effect(game, order, _spoofed_bid_effect)

    assert game.state.pending_choice is None
    pt = [e for e in (out or []) if e.type == EventType.PT_MODIFICATION]
    assert any(
        e.payload.get("object_id") == first.id and e.payload.get("power_mod") == -3
        for e in pt
    )
    print("[PASS] HF Spoofed Bid AI inline resolve")


# ===========================================================================
# CANCEL_ORDER (Market Order, target tap)
# ===========================================================================

def test_cancel_order_human_path_emits_target_choice():
    game, p1, p2 = _make_finance_game()
    enemy_a = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    tapped = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    tapped.state.tapped = True
    fs_before = _fin_stack_depth(game)

    out = _cancel_order_resolve(_resolve_event(p1.id), game.state)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert enemy_a.id in option_ids
    assert tapped.id not in option_ids, "tapped Traders excluded"
    assert not any(e.type == EventType.TAP for e in (out or []))
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Cancel Order human-path emits target choice")


def test_cancel_order_no_untapped_short_circuits():
    game, p1, p2 = _make_finance_game()
    tapped = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    tapped.state.tapped = True
    fs_before = _fin_stack_depth(game)

    out = _cancel_order_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Cancel Order short-circuits when no untapped opp")


def test_cancel_order_ai_resolves_inline():
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    first = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)

    out = _cancel_order_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    tap_events = [e for e in (out or []) if e.type == EventType.TAP]
    assert any(e.payload.get("object_id") == first.id for e in tap_events)
    print("[PASS] HF Cancel Order AI inline resolve")


# ===========================================================================
# QUOTE_STUFFING_BURST (Market Order, target friendly +3/+0 + AS)
# ===========================================================================

def test_quote_stuffing_burst_human_path_emits_target_choice():
    game, p1, p2 = _make_finance_game()
    ally_a = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)
    ally_b = _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    fs_before = _fin_stack_depth(game)

    out = _quote_stuffing_burst_resolve(_resolve_event(p1.id), game.state)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert ally_a.id in option_ids and ally_b.id in option_ids
    assert not any(e.type == EventType.PT_MODIFICATION for e in (out or []))
    # Alpha Strike flag not yet set.
    assert not game.state.turn_data.get(f"fin_alpha_strike_granted_{ally_a.id}")
    assert not game.state.turn_data.get(f"fin_alpha_strike_granted_{ally_b.id}")
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Quote Stuffing Burst human-path emits target choice")


def test_quote_stuffing_burst_heuristic_picks_highest_power():
    """Bug 22 fix: heuristic_pick must be highest-power friendly Trader,
    not the first-in-list."""
    game, p1, p2 = _make_finance_game()
    weak = _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)  # 1/3
    strong = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)       # 2/2
    assert (strong.characteristics.power or 0) > (weak.characteristics.power or 0)

    _quote_stuffing_burst_resolve(_resolve_event(p1.id), game.state)

    hp = game.state.pending_choice.callback_data.get("heuristic_pick")
    assert hp == [strong.id], (
        f"Bug 22: heuristic should pick highest-power {strong.id}; got {hp}"
    )
    print("[PASS] HF Quote Stuffing Burst heuristic = highest-power (Bug 22)")


def test_quote_stuffing_burst_no_friendly_short_circuits():
    game, p1, p2 = _make_finance_game()
    fs_before = _fin_stack_depth(game)

    out = _quote_stuffing_burst_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Quote Stuffing Burst short-circuits when no friendly")


def test_quote_stuffing_burst_ai_resolves_inline():
    """AI path: +3/+0 lands on highest-power friendly + AS flag set."""
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    _ = _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    strong = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)

    out = _quote_stuffing_burst_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    pt = [e for e in (out or []) if e.type == EventType.PT_MODIFICATION]
    assert any(
        e.payload.get("object_id") == strong.id and e.payload.get("power_mod") == 3
        for e in pt
    )
    assert game.state.turn_data.get(f"fin_alpha_strike_granted_{strong.id}") is True
    print("[PASS] HF Quote Stuffing Burst AI inline resolve")


# ===========================================================================
# CIRCUIT_BREAKER_TRIP (Market Order, target destroy Aggr ≥4)
# ===========================================================================

def test_circuit_breaker_trip_human_path_emits_target_choice():
    """Filter: only opp Traders with Aggression ≥4 show up."""
    game, p1, p2 = _make_finance_game()
    weak = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)          # 2 power
    # Boost a Trader's power so it qualifies. Use a PT_MOD via state directly.
    big = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    big.state.pt_modifiers = [
        {"power_mod": 5, "toughness_mod": 0, "duration": "permanent"}
    ]
    # Recompute characteristics power via pt_modifiers — STATISTICAL_ARB_CLERK
    # is 1/3 base; we use the raw characteristic instead for the test filter
    # since the card filters on characteristics.power. Easier: overwrite
    # the cached power directly so the filter sees ≥4.
    big.characteristics.power = 4
    fs_before = _fin_stack_depth(game)

    out = _circuit_breaker_trip_resolve(_resolve_event(p1.id), game.state)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert big.id in option_ids
    assert weak.id not in option_ids, "low-Aggression Traders excluded"
    assert not any(e.type == EventType.OBJECT_DESTROYED for e in (out or []))
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Circuit Breaker Trip human-path emits target choice")


def test_circuit_breaker_trip_no_high_aggression_short_circuits():
    """Only low-Aggression Traders → no PendingChoice."""
    game, p1, p2 = _make_finance_game()
    _ = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)  # 2 power, no boost
    fs_before = _fin_stack_depth(game)

    out = _circuit_breaker_trip_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Circuit Breaker Trip short-circuits without high-Aggr")


def test_circuit_breaker_trip_ai_resolves_inline():
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    big = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    big.characteristics.power = 5

    out = _circuit_breaker_trip_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    dest = [e for e in (out or []) if e.type == EventType.OBJECT_DESTROYED]
    assert any(e.payload.get("object_id") == big.id for e in dest)
    print("[PASS] HF Circuit Breaker Trip AI inline resolve")


# ===========================================================================
# REGULATORY_HALT (Dark Pool, target tap)
# ===========================================================================

def test_regulatory_halt_human_path_emits_target_choice():
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, REGULATORY_HALT)
    order.controller = p1.id
    enemy_a = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    enemy_b = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    fs_before = _fin_stack_depth(game)

    out = _fire_dark_effect(game, order, _regulatory_halt_effect)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert enemy_a.id in option_ids and enemy_b.id in option_ids
    assert not any(e.type == EventType.TAP for e in (out or []))
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Regulatory Halt human-path emits target choice")


def test_regulatory_halt_no_opp_traders_short_circuits():
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, REGULATORY_HALT)
    order.controller = p1.id
    fs_before = _fin_stack_depth(game)

    out = _fire_dark_effect(game, order, _regulatory_halt_effect)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Regulatory Halt short-circuits on empty opp")


def test_regulatory_halt_ai_resolves_inline():
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    order = _stage_order(game, p1.id, REGULATORY_HALT)
    order.controller = p1.id
    first = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)

    out = _fire_dark_effect(game, order, _regulatory_halt_effect)

    assert game.state.pending_choice is None
    tap_events = [e for e in (out or []) if e.type == EventType.TAP]
    assert any(e.payload.get("object_id") == first.id for e in tap_events)
    print("[PASS] HF Regulatory Halt AI inline resolve")


# ===========================================================================
# PUMP_AND_DUMP (Strategy, target friendly +4/+0 + 2 Lev)
# ===========================================================================

def test_pump_and_dump_human_path_emits_target_choice():
    game, p1, p2 = _make_finance_game()
    ally_a = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)
    ally_b = _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    fs_before = _fin_stack_depth(game)
    lev_before = {
        ally_a.id: ally_a.state.counters.get("leverage", 0),
        ally_b.id: ally_b.state.counters.get("leverage", 0),
    }

    out = _pump_and_dump_resolve(_resolve_event(p1.id), game.state)

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    option_ids = {opt["id"] for opt in pc.options}
    assert ally_a.id in option_ids and ally_b.id in option_ids
    assert not any(e.type == EventType.PT_MODIFICATION for e in (out or []))
    assert not any(e.type == EventType.COUNTER_ADDED for e in (out or []))
    # Counters untouched (no Leverage applied yet).
    for tid, lv in lev_before.items():
        obj = game.state.objects.get(tid)
        assert obj.state.counters.get("leverage", 0) == lv
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Pump-and-Dump human-path emits target choice")


def test_pump_and_dump_heuristic_picks_highest_power():
    """heuristic_pick = highest-power friendly Trader (best buff target)."""
    game, p1, p2 = _make_finance_game()
    _ = _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    strong = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)

    _pump_and_dump_resolve(_resolve_event(p1.id), game.state)

    hp = game.state.pending_choice.callback_data.get("heuristic_pick")
    assert hp == [strong.id], f"expected [{strong.id}], got {hp}"
    print("[PASS] HF Pump-and-Dump heuristic preserves max-power friendly")


def test_pump_and_dump_no_friendly_short_circuits():
    game, p1, p2 = _make_finance_game()
    fs_before = _fin_stack_depth(game)

    out = _pump_and_dump_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    assert out == []
    assert _fin_stack_depth(game) == fs_before
    print("[PASS] HF Pump-and-Dump short-circuits when no friendly")


def test_pump_and_dump_ai_resolves_inline():
    """AI path emits PT_MOD (+4/+0) AND COUNTER_ADDED (2 lev) on strongest."""
    game, p1, p2 = _make_finance_game()
    game.turn_manager.set_ai_player(p1.id)
    game.state._game = game
    _ = _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    strong = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)

    out = _pump_and_dump_resolve(_resolve_event(p1.id), game.state)

    assert game.state.pending_choice is None
    pt = [e for e in (out or []) if e.type == EventType.PT_MODIFICATION]
    counter = [e for e in (out or []) if e.type == EventType.COUNTER_ADDED]
    assert any(
        e.payload.get("object_id") == strong.id and e.payload.get("power_mod") == 4
        for e in pt
    ), f"expected +4/+0 to strong; got: {[e.payload for e in pt]}"
    assert any(
        e.payload.get("object_id") == strong.id
        and e.payload.get("counter_type") == "leverage"
        and e.payload.get("amount") == 2
        for e in counter
    ), f"expected 2 Lev counters on strong; got: {[e.payload for e in counter]}"
    print("[PASS] HF Pump-and-Dump AI inline resolve")


# ===========================================================================
# FinanceStack invariant: a mid-cast PendingChoice must not corrupt the stack.
#
# The Finance engine has an MTG-style response stack. When a non-permanent
# spell is cast, it pushes onto fin_stack and the opponent gets a priority
# window. During resolve, the resolve fn can emit a PendingChoice. The
# PendingChoice MUST NOT push another item onto fin_stack (it lives on
# state.pending_choice, distinct from the stack). This test verifies the
# invariant for one card per resolve-pathway (a Dark Pool effect and a
# direct-resolve effect).
# ===========================================================================

def test_dark_pool_flash_order_pending_choice_does_not_push_fin_stack():
    """Dark Pool effect runs OFF the stack (Dark Pool triggers fire from a
    FIN_MARKET_EVENT). PendingChoice must not push fin_stack."""
    game, p1, p2 = _make_finance_game()
    order = _stage_order(game, p1.id, DARK_POOL_FLASH_ORDER)
    order.controller = p1.id
    _ = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    depth_before = _fin_stack_depth(game)

    _fire_dark_effect(game, order, _dark_pool_flash_order_effect)

    pc = game.state.pending_choice
    assert pc is not None
    assert _fin_stack_depth(game) == depth_before, (
        f"PendingChoice corrupted fin_stack: depth {depth_before} → "
        f"{_fin_stack_depth(game)}"
    )
    print("[PASS] HF Dark Pool Flash Order: PendingChoice + fin_stack invariant")


def test_circuit_breaker_trip_pending_choice_does_not_push_fin_stack():
    """Direct-resolve effect (no Dark Pool — fires from _resolve_stack_item).
    PendingChoice must not push another stack item."""
    game, p1, p2 = _make_finance_game()
    big = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    big.characteristics.power = 5
    depth_before = _fin_stack_depth(game)

    _circuit_breaker_trip_resolve(_resolve_event(p1.id), game.state)

    pc = game.state.pending_choice
    assert pc is not None
    assert _fin_stack_depth(game) == depth_before, (
        f"PendingChoice corrupted fin_stack: depth {depth_before} → "
        f"{_fin_stack_depth(game)}"
    )
    print("[PASS] HF Circuit Breaker Trip: PendingChoice + fin_stack invariant")


# ===========================================================================
# Test runner
# ===========================================================================

ALL_TESTS = [
    # Dark Pool Flash Order — 4 tests
    test_dark_pool_flash_order_human_path_emits_target_choice,
    test_dark_pool_flash_order_heuristic_preserves_first_pick,
    test_dark_pool_flash_order_no_opp_traders_short_circuits,
    test_dark_pool_flash_order_ai_resolves_inline_to_first_pick,
    # Sub-Penny Intercept — 3 tests
    test_sub_penny_intercept_human_path_emits_target_choice,
    test_sub_penny_intercept_no_attackers_short_circuits,
    test_sub_penny_intercept_ai_resolves_inline,
    # Pre-Market Raid — 3 tests
    test_pre_market_raid_human_path_emits_target_choice,
    test_pre_market_raid_no_opp_traders_short_circuits,
    test_pre_market_raid_ai_resolves_inline,
    # Spoofed Bid — 3 tests
    test_spoofed_bid_human_path_emits_target_choice,
    test_spoofed_bid_no_opp_traders_short_circuits,
    test_spoofed_bid_ai_resolves_inline,
    # Cancel Order — 3 tests
    test_cancel_order_human_path_emits_target_choice,
    test_cancel_order_no_untapped_short_circuits,
    test_cancel_order_ai_resolves_inline,
    # Quote Stuffing Burst — 4 tests
    test_quote_stuffing_burst_human_path_emits_target_choice,
    test_quote_stuffing_burst_heuristic_picks_highest_power,
    test_quote_stuffing_burst_no_friendly_short_circuits,
    test_quote_stuffing_burst_ai_resolves_inline,
    # Circuit Breaker Trip — 3 tests
    test_circuit_breaker_trip_human_path_emits_target_choice,
    test_circuit_breaker_trip_no_high_aggression_short_circuits,
    test_circuit_breaker_trip_ai_resolves_inline,
    # Regulatory Halt — 3 tests
    test_regulatory_halt_human_path_emits_target_choice,
    test_regulatory_halt_no_opp_traders_short_circuits,
    test_regulatory_halt_ai_resolves_inline,
    # Pump-and-Dump — 4 tests
    test_pump_and_dump_human_path_emits_target_choice,
    test_pump_and_dump_heuristic_picks_highest_power,
    test_pump_and_dump_no_friendly_short_circuits,
    test_pump_and_dump_ai_resolves_inline,
    # FinanceStack invariant — 2 tests
    test_dark_pool_flash_order_pending_choice_does_not_push_fin_stack,
    test_circuit_breaker_trip_pending_choice_does_not_push_fin_stack,
]


def main() -> int:
    failed = 0
    for fn in ALL_TESTS:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {fn.__name__}: {type(e).__name__}: {e}")
    total = len(ALL_TESTS)
    print(f"\n{total - failed}/{total} tests passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
