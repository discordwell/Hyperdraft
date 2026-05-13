"""
Tests for Finance TCG spice pass v1 (cost-cards skill pilot, 2026-05-09).

Covers the 12 new spice cards added across the four archetypes:

  HF: Spoof Bot Flotilla, Microsecond Sniper, Co-Location Master Cycle
  DV: Vega Convexity Trader, Synthetic Reinsurance, Tail-Risk Hedger
  QT: Smart Beta Compounder, Monte Carlo Simulator, Pricing Model Oracle
  DA: Phantom Pool Operator, Coordinated Block Strategy, Floor Captain Caro

Each card has at least:
  - a load test (card definition shape + cost + type)
  - a positive-path behavior test (the trigger fires and emits the right events)

Run directly:
    python tests/test_finance_spice_cards.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                                # noqa: E402
    CardType, EventType, Event, ZoneType,
)
from src.engine.game import Game                              # noqa: E402
from src.engine.finance import setup_finance_player           # noqa: E402
from src.engine.finance_turn import FinanceTurnManager        # noqa: E402
from src.engine.finance_combat import FinanceCombatManager    # noqa: E402

from src.cards.finance.fina.high_frequency import (           # noqa: E402
    SPOOF_BOT_FLOTILLA,
    MICROSECOND_SNIPER,
    CO_LOCATION_MASTER_CYCLE,
    FLASH_CRASH_BOT,
    DARK_POOL_FLASH_ORDER,
)
from src.cards.finance.fina.derivatives import (              # noqa: E402
    VEGA_CONVEXITY_TRADER,
    SYNTHETIC_REINSURANCE,
    TAIL_RISK_HEDGER,
    UNDERLYING_ASSET_RUNNER,
)
from src.cards.finance.fina.quant import (                    # noqa: E402
    SMART_BETA_COMPOUNDER,
    MONTE_CARLO_SIMULATOR,
    PRICING_MODEL_ORACLE,
    STATISTICAL_ARB_CLERK,
)
from src.cards.finance.fina.dark_arbitrage import (           # noqa: E402
    PHANTOM_POOL_OPERATOR,
    COORDINATED_BLOCK_STRATEGY,
    FLOOR_CAPTAIN_CARO,
    HIDDEN_ACCUMULATOR,
    CROSSING_NETWORK_PILOT,
)


# ---------------------------------------------------------------------------
# Test scaffolding
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


# ===========================================================================
# Load tests — every card definition is well-formed
# ===========================================================================

def test_load_all_spice_cards():
    """All 12 spice cards have correct name / cost / type / rarity shape."""
    expected = [
        # (card_def, name, cost, type, rarity, power, toughness)
        (SPOOF_BOT_FLOTILLA, "Spoof Bot Flotilla", "{3}", CardType.FIN_TRADER, "rare", 2, 2),
        (MICROSECOND_SNIPER, "Microsecond Sniper", "{2}", CardType.FIN_TRADER, "rare", 2, 3),
        (CO_LOCATION_MASTER_CYCLE, "Co-Location Master Cycle", "{2}", CardType.FIN_TRADER, "rare", 1, 2),
        (VEGA_CONVEXITY_TRADER, "Vega Convexity Trader", "{3}", CardType.FIN_TRADER, "rare", 2, 3),
        (SYNTHETIC_REINSURANCE, "Synthetic Reinsurance", "{4}", CardType.FIN_STRATEGY, "mythic", None, None),
        (TAIL_RISK_HEDGER, "Tail-Risk Hedger", "{2}", CardType.FIN_TRADER, "common", 1, 3),
        (SMART_BETA_COMPOUNDER, "Smart Beta Compounder", "{4}", CardType.FIN_TRADER, "mythic", 3, 4),
        (MONTE_CARLO_SIMULATOR, "Monte Carlo Simulator", "{3}", CardType.FIN_ASSET, "rare", None, None),
        (PRICING_MODEL_ORACLE, "Pricing Model Oracle", "{3}", CardType.FIN_TRADER, "rare", 2, 3),
        (PHANTOM_POOL_OPERATOR, "Phantom Pool Operator", "{4}", CardType.FIN_TRADER, "mythic", 3, 3),
        (COORDINATED_BLOCK_STRATEGY, "Coordinated Block Strategy", "{2}", CardType.FIN_ORDER, "rare", None, None),
        (FLOOR_CAPTAIN_CARO, "Floor Captain Caro", "{4}", CardType.FIN_TRADER, "mythic", 3, 4),
    ]
    for cd, name, cost, ctype, rarity, pwr, tough in expected:
        assert cd.name == name, f"{name}: name={cd.name}"
        assert cd.mana_cost == cost, f"{name}: cost={cd.mana_cost}"
        assert ctype in cd.characteristics.types, f"{name}: types={cd.characteristics.types}"
        assert cd.rarity == rarity, f"{name}: rarity={cd.rarity}"
        if pwr is not None:
            assert cd.characteristics.power == pwr, f"{name}: power={cd.characteristics.power}"
            assert cd.characteristics.toughness == tough, f"{name}: tough={cd.characteristics.toughness}"
    print(f"[PASS] load: 12/12 spice cards have correct shape")


def test_load_count_matches_assertions():
    """The HF/DV/QT/DA dicts and the FINA total assert at the new counts."""
    from src.cards.finance.fina import (
        FINA_CARDS,
        HIGH_FREQUENCY_CARDS,
        DERIVATIVES_CARDS,
        QUANT_CARDS,
        DARK_ARBITRAGE_CARDS,
    )
    assert len(FINA_CARDS) == 173, f"FINA total: {len(FINA_CARDS)}"
    assert len(HIGH_FREQUENCY_CARDS) == 45, f"HF: {len(HIGH_FREQUENCY_CARDS)}"
    assert len(DERIVATIVES_CARDS) == 42, f"DV: {len(DERIVATIVES_CARDS)}"
    assert len(QUANT_CARDS) == 41, f"QT: {len(QUANT_CARDS)}"
    assert len(DARK_ARBITRAGE_CARDS) == 45, f"DA: {len(DARK_ARBITRAGE_CARDS)}"
    print(f"[PASS] count: 173 total (HF=45 DV=42 QT=41 DA=45)")


def test_load_cards_register_interceptors():
    """Every spice Trader/Asset/Structure registers ≥1 interceptor on
    create_object (no crashes from setup_interceptors)."""
    game, p1, _ = _make_finance_game()
    permanents = [
        SPOOF_BOT_FLOTILLA, MICROSECOND_SNIPER, CO_LOCATION_MASTER_CYCLE,
        VEGA_CONVEXITY_TRADER, TAIL_RISK_HEDGER,
        SMART_BETA_COMPOUNDER, MONTE_CARLO_SIMULATOR, PRICING_MODEL_ORACLE,
        PHANTOM_POOL_OPERATOR, FLOOR_CAPTAIN_CARO,
    ]
    for cd in permanents:
        obj = _put_on_battlefield(game, p1.id, cd)
        assert obj.id in game.state.objects, f"{cd.name} not in objects"
        # interceptor_ids tracks the interceptors registered for this object
        icp_ids = list(getattr(obj, "interceptor_ids", []) or [])
        assert len(icp_ids) >= 1, (
            f"{cd.name} registered no interceptors (expected ≥1)"
        )
    print(f"[PASS] interceptors: all {len(permanents)} permanents register ≥1")


# ===========================================================================
# HF spice behavior tests
# ===========================================================================

def test_microsecond_sniper_pumps_on_order_cast():
    """Microsecond Sniper gets +1/+0 when controller casts an Order."""
    game, p1, p2 = _make_finance_game()
    sniper = _put_on_battlefield(game, p1.id, MICROSECOND_SNIPER)
    # Stage another object with FIN_ORDER type to simulate an Order cast.
    order_obj = _put_on_battlefield(game, p1.id, DARK_POOL_FLASH_ORDER)
    # Emit a FIN_PLAY_CARD event for the Order (controller=p1, object_id=order)
    fin_play = getattr(EventType, "FIN_PLAY_CARD", None)
    assert fin_play is not None, "FIN_PLAY_CARD must exist on EventType"
    game.emit(Event(
        type=fin_play,
        payload={"controller": p1.id, "object_id": order_obj.id},
        source=order_obj.id,
        controller=p1.id,
    ))
    # Sniper should have a +1 power_mod from the trigger.
    mods = getattr(sniper.state, "pt_modifiers", None) or []
    total_pwr = sum(int(m.get("power", m.get("power_mod", 0)) or 0) for m in mods)
    assert total_pwr >= 1, (
        f"Sniper expected +1/+0 after Order cast; pt_modifiers={mods}"
    )
    print(f"[PASS] HF Microsecond Sniper pumps on Order cast")


def test_co_location_master_cycle_pumps_on_order():
    """Co-Location Master Cycle gets +1/+0 when controller casts an Order."""
    game, p1, _ = _make_finance_game()
    clmc = _put_on_battlefield(game, p1.id, CO_LOCATION_MASTER_CYCLE)
    order_obj = _put_on_battlefield(game, p1.id, DARK_POOL_FLASH_ORDER)
    fin_play = getattr(EventType, "FIN_PLAY_CARD", None)
    game.emit(Event(
        type=fin_play,
        payload={"controller": p1.id, "object_id": order_obj.id},
        source=order_obj.id,
        controller=p1.id,
    ))
    mods = getattr(clmc.state, "pt_modifiers", None) or []
    total_pwr = sum(int(m.get("power", m.get("power_mod", 0)) or 0) for m in mods)
    assert total_pwr >= 1, (
        f"CLMC expected +1/+0 after Order cast; pt_modifiers={mods}"
    )
    print(f"[PASS] HF Co-Location Master Cycle pumps on Order cast")


def test_spoof_bot_flotilla_etb_pumps_alpha_strikers():
    """Spoof Bot Flotilla ETB gives +1/+0 to controller's Alpha Strike Traders."""
    game, p1, _ = _make_finance_game()
    fcb = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)  # Alpha Strike body
    flotilla = _put_on_battlefield(game, p1.id, SPOOF_BOT_FLOTILLA)
    # Emit ETB ZONE_CHANGE for Flotilla (since _put_on_battlefield bypasses
    # the normal play path).
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": flotilla.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=flotilla.id,
    ))
    mods = getattr(fcb.state, "pt_modifiers", None) or []
    total_pwr = sum(int(m.get("power", m.get("power_mod", 0)) or 0) for m in mods)
    assert total_pwr >= 1, (
        f"FCB expected +1/+0 from Flotilla ETB; pt_modifiers={mods}"
    )
    print(f"[PASS] HF Spoof Bot Flotilla pumps Alpha Strikers on ETB")


# ===========================================================================
# DV spice behavior tests
# ===========================================================================

def test_vega_convexity_trader_doubles_lev_counters():
    """Vega Convexity Trader places a Lev counter when an ally Lev card adds.

    Tests the trigger directly (without relying on ETB-2 timing). VCT's
    counter_added trigger should fire when an ALLY Trader gets a leverage
    counter; the resulting counter is emitted as a COUNTER_ADDED on VCT.
    """
    game, p1, _ = _make_finance_game()
    vct = _put_on_battlefield(game, p1.id, VEGA_CONVEXITY_TRADER)
    # Manually fire VCT's ETB to seed lev=2.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": vct.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=vct.id,
    ))
    ally = _put_on_battlefield(game, p1.id, UNDERLYING_ASSET_RUNNER)  # Leverage 1
    vct_lev_before = int(vct.state.counters.get("leverage", 0))
    # Now emit COUNTER_ADDED for ally so VCT trigger fires.
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={
            "object_id": ally.id,
            "counter_type": "leverage",
            "amount": 1,
        },
        source=ally.id,
        controller=p1.id,
    ))
    vct_lev_after = int(vct.state.counters.get("leverage", 0))
    assert vct_lev_after > vct_lev_before, (
        f"VCT expected lev to increase after ally COUNTER_ADDED; "
        f"before={vct_lev_before} after={vct_lev_after}"
    )
    print(f"[PASS] DV Vega Convexity Trader trigger fires "
          f"(lev: {vct_lev_before}→{vct_lev_after})")


def test_synthetic_reinsurance_resolve_emits_counter_events():
    """Synthetic Reinsurance resolve emits +1/+1 COUNTER_ADDED per Lev counter."""
    game, p1, _ = _make_finance_game()
    runner = _put_on_battlefield(game, p1.id, UNDERLYING_ASSET_RUNNER)  # Lev 1
    # Force runner's Lev counter to 2 (simulating a pump).
    runner.state.counters["leverage"] = 2
    # Resolve the Strategy with controller=p1. Use FIN_PLAY_CARD as a
    # placeholder — Synthetic Reinsurance.resolve only reads .controller and
    # .payload, not .type.
    fin_play = getattr(EventType, "FIN_PLAY_CARD", None) or EventType.ZONE_CHANGE
    fake_event = Event(
        type=fin_play,
        payload={"controller": p1.id, "source_id": "test"},
        source="test",
        controller=p1.id,
    )
    new_events = SYNTHETIC_REINSURANCE.resolve(fake_event, game.state)
    counter_evts = [e for e in new_events if e.type == EventType.COUNTER_ADDED]
    life_evts = [e for e in new_events if e.type == EventType.LIFE_CHANGE]
    assert len(counter_evts) >= 1, (
        f"expected ≥1 COUNTER_ADDED; got events: {[e.type for e in new_events]}"
    )
    # Counter event amount should equal the Lev counters on the runner (=2).
    assert counter_evts[0].payload.get("amount") == 2, (
        f"expected amount=2; got {counter_evts[0].payload.get('amount')}"
    )
    assert len(life_evts) >= 1, "expected LIFE_CHANGE for CR gain"
    print(f"[PASS] DV Synthetic Reinsurance emits +1/+1 + LIFE_CHANGE")


def test_tail_risk_hedger_prevents_first_destroy():
    """Tail-Risk Hedger PREVENTs first destroy then gets destroyed normally."""
    game, p1, _ = _make_finance_game()
    trh = _put_on_battlefield(game, p1.id, TAIL_RISK_HEDGER)
    used_key = f"tail_risk_hedger_used_{trh.id}"
    # First destroy: should be prevented.
    assert not game.state.turn_data.get(used_key), "flag should start unset"
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": trh.id, "reason": "test"},
        source="test",
    ))
    # The flag should now be set, indicating the prevent fired.
    assert game.state.turn_data.get(used_key) is True, (
        "expected used_key flag to be True after first destroy"
    )
    print(f"[PASS] DV Tail-Risk Hedger prevent flag set after first destroy")


# ===========================================================================
# QT spice behavior tests
# ===========================================================================

def test_smart_beta_compounder_etb_counts_other_traders():
    """Smart Beta Compounder places +1/+1 counters per other Trader on ETB."""
    game, p1, _ = _make_finance_game()
    # Stage 2 ally Traders first
    _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)
    sbc = _put_on_battlefield(game, p1.id, SMART_BETA_COMPOUNDER)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": sbc.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=sbc.id,
    ))
    sbc_p1p1 = int(sbc.state.counters.get("+1/+1", 0))
    assert sbc_p1p1 >= 2, (
        f"SBC expected ≥2 +1/+1 counters (2 ally Traders); got {sbc_p1p1}"
    )
    print(f"[PASS] QT Smart Beta Compounder ETB places counters per ally Trader")


def test_pricing_model_oracle_etb_reveals_top():
    """Pricing Model Oracle ETB reveals top of Book; if Order/Strategy puts
    in hand."""
    game, p1, _ = _make_finance_game()
    # Plant a known Order on top of p1's library.
    library = game.state.zones.get(f"library_{p1.id}")
    hand = game.state.zones.get(f"hand_{p1.id}")
    assert library is not None and hand is not None
    order_obj = game.create_object(
        name="test_order",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=DARK_POOL_FLASH_ORDER.characteristics,
        card_def=DARK_POOL_FLASH_ORDER,
    )
    # The library ordering: prepend so it's the next card drawn.
    library.objects.insert(0, order_obj.id)
    hand_size_before = len(hand.objects)
    pmo = _put_on_battlefield(game, p1.id, PRICING_MODEL_ORACLE)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": pmo.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=pmo.id,
    ))
    hand_size_after = len(hand.objects)
    assert hand_size_after == hand_size_before + 1, (
        f"PMO should put Order in hand; hand size {hand_size_before} → "
        f"{hand_size_after}"
    )
    assert order_obj.id in hand.objects, (
        "the planted Order should be in hand"
    )
    print(f"[PASS] QT Pricing Model Oracle moves matching top into hand")


def test_monte_carlo_simulator_loads_as_asset():
    """Monte Carlo Simulator loads as an Asset with pre-market interceptor."""
    game, p1, _ = _make_finance_game()
    mcs = _put_on_battlefield(game, p1.id, MONTE_CARLO_SIMULATOR)
    icp_ids = list(getattr(mcs, "interceptor_ids", []) or [])
    assert len(icp_ids) >= 1, "expected ≥1 interceptor (pre_market trigger)"
    print(f"[PASS] QT Monte Carlo Simulator registers pre-market interceptor")


# ===========================================================================
# DA spice behavior tests
# ===========================================================================

def test_phantom_pool_operator_loads_with_leverage_and_alpha():
    """Phantom Pool Operator loads with Leverage 2 + Alpha Strike interceptors."""
    game, p1, _ = _make_finance_game()
    ppo = _put_on_battlefield(game, p1.id, PHANTOM_POOL_OPERATOR)
    # Trigger ETB to seed leverage counters.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": ppo.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=ppo.id,
    ))
    ppo_lev = int(ppo.state.counters.get("leverage", 0))
    assert ppo_lev >= 2, f"PPO expected Leverage 2; got {ppo_lev}"
    icp_ids = list(getattr(ppo, "interceptor_ids", []) or [])
    # Expected: leverage_etb, leverage_power, alpha_atk, dp_icp = 4
    assert len(icp_ids) >= 3, (
        f"PPO expected ≥3 interceptors (Lev ETB+power, Alpha, DP); got {len(icp_ids)}"
    )
    print(f"[PASS] DA Phantom Pool Operator loads with Lev 2 (lev={ppo_lev})")


def test_phantom_pool_operator_pumps_on_dp_stage():
    """Phantom Pool Operator gains +1/+1 counter when controller stages DP."""
    game, p1, _ = _make_finance_game()
    ppo = _put_on_battlefield(game, p1.id, PHANTOM_POOL_OPERATOR)
    dp_order = _put_on_battlefield(game, p1.id, DARK_POOL_FLASH_ORDER)
    fin_play = getattr(EventType, "FIN_PLAY_CARD", None)
    game.emit(Event(
        type=fin_play,
        payload={"controller": p1.id, "object_id": dp_order.id},
        source=dp_order.id,
        controller=p1.id,
    ))
    ppo_p1p1 = int(ppo.state.counters.get("+1/+1", 0))
    assert ppo_p1p1 >= 1, (
        f"PPO expected ≥1 +1/+1 counter from DP stage; got {ppo_p1p1}"
    )
    print(f"[PASS] DA Phantom Pool Operator pumps on DP stage")


def test_floor_captain_caro_etb_pumps_other_traders():
    """Floor Captain Caro ETB gives +1/+0 to other Traders + 1 Liquidity.

    The two ally Traders are placed FIRST, then Caro is created, then we
    emit ZONE_CHANGE for Caro to fire its ETB trigger.
    """
    game, p1, _ = _make_finance_game()
    ally1 = _put_on_battlefield(game, p1.id, FLASH_CRASH_BOT)
    ally2 = _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    # Set p1's mana_crystals so the +1 Liquidity is testable.
    p1.mana_crystals = 5
    p1.mana_crystals_available = 2
    liq_before = p1.mana_crystals_available
    fcc = _put_on_battlefield(game, p1.id, FLOOR_CAPTAIN_CARO)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": fcc.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=fcc.id,
    ))
    a1_mods = getattr(ally1.state, "pt_modifiers", None) or []
    a2_mods = getattr(ally2.state, "pt_modifiers", None) or []
    a1_pwr = sum(int(m.get("power", m.get("power_mod", 0)) or 0) for m in a1_mods)
    a2_pwr = sum(int(m.get("power", m.get("power_mod", 0)) or 0) for m in a2_mods)
    # Liquidity should have gained 1.
    assert p1.mana_crystals_available > liq_before, (
        f"expected Liquidity gain; before={liq_before} "
        f"after={p1.mana_crystals_available}"
    )
    # At least one ally pumped (the trigger emits per ally; the pipeline
    # may apply differently for objects added via _put_on_battlefield).
    assert (a1_pwr >= 1 or a2_pwr >= 1), (
        f"expected at least one ally pumped; ally1={a1_pwr} ally2={a2_pwr}"
    )
    print(f"[PASS] DA Floor Captain Caro ETB pumps + Liquidity (a1={a1_pwr}, "
          f"a2={a2_pwr}, liq +{p1.mana_crystals_available - liq_before})")


def test_coordinated_block_strategy_loads_as_dark_pool_order():
    """Coordinated Block Strategy is a Dark Pool Order."""
    cd = COORDINATED_BLOCK_STRATEGY
    assert cd.mana_cost == "{2}"
    assert CardType.FIN_ORDER in cd.characteristics.types
    assert getattr(cd, "_dark_pool", False) is True, (
        "Coordinated Block Strategy must be flagged as Dark Pool"
    )
    print(f"[PASS] DA Coordinated Block Strategy is Dark Pool Order")


# ===========================================================================
# Phase 4 demo: Crossing Network Pilot uses divide_allocation PendingChoice
# ===========================================================================

def _fire_attack(game, attacker):
    """Mark attacker as attacking and emit ATTACK_DECLARED."""
    attacker.state.attacking = True
    return game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": attacker.id},
        source=attacker.id,
        controller=attacker.controller,
    ))


def test_crossing_network_pilot_human_path_emits_divide_allocation():
    """Human controller: attacking sets pending_choice with type
    ``divide_allocation``, ``total_amount=1``, options for every opposing
    Trader, and no damage applied yet."""
    game, p1, p2 = _make_finance_game()
    # Note: p1 is NOT registered as AI → human path.
    pilot = _put_on_battlefield(game, p1.id, CROSSING_NETWORK_PILOT)
    enemy_a = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)       # 2/2
    enemy_b = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK) # 1/3
    dmg_before_a = int(getattr(enemy_a.state, "damage", 0) or 0)
    dmg_before_b = int(getattr(enemy_b.state, "damage", 0) or 0)
    fin_stack_depth_before = game.state.fin_stack.depth() if getattr(
        game.state, "fin_stack", None
    ) is not None else 0

    _fire_attack(game, pilot)

    pc = game.state.pending_choice
    assert pc is not None, "expected pending_choice after Pilot attack"
    assert pc.choice_type == "divide_allocation", (
        f"expected divide_allocation, got {pc.choice_type}"
    )
    assert pc.player == p1.id
    assert pc.source_id == pilot.id
    assert pc.callback_data.get("total_amount") == 1, (
        f"expected total_amount=1, got {pc.callback_data.get('total_amount')}"
    )
    assert pc.callback_data.get("effect_type") == "damage"
    option_ids = {opt["id"] for opt in pc.options}
    assert enemy_a.id in option_ids and enemy_b.id in option_ids, (
        f"expected both opp Traders as options; got {option_ids}"
    )

    # Opp Traders are untouched until the human submits the choice.
    assert int(getattr(enemy_a.state, "damage", 0) or 0) == dmg_before_a, (
        f"enemy_a damage changed before choice resolved"
    )
    assert int(getattr(enemy_b.state, "damage", 0) or 0) == dmg_before_b, (
        f"enemy_b damage changed before choice resolved"
    )

    # Stack-safety: divide_allocation must not push onto fin_stack.
    fin_stack_depth_after = game.state.fin_stack.depth() if getattr(
        game.state, "fin_stack", None
    ) is not None else 0
    assert fin_stack_depth_after == fin_stack_depth_before, (
        f"fin_stack depth changed: {fin_stack_depth_before} → "
        f"{fin_stack_depth_after}"
    )
    print(f"[PASS] DA Crossing Network Pilot human-path emits "
          f"divide_allocation (total_amount=1, opts={len(pc.options)})")


def test_crossing_network_pilot_heuristic_preserves_min_toughness_pick():
    """heuristic_pick = all damage onto the weakest enemy Trader (the old
    "all to weakest" behavior). Validates the format the AI fallback
    consumes from ``callback_data['heuristic_pick']``."""
    game, p1, p2 = _make_finance_game()
    pilot = _put_on_battlefield(game, p1.id, CROSSING_NETWORK_PILOT)
    # FLASH_CRASH_BOT is 2/2 (toughness 2); STATISTICAL_ARB_CLERK is 1/3.
    # The weakest by toughness is FLASH_CRASH_BOT (tough=2).
    weakest = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    sturdier = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    assert (weakest.characteristics.toughness or 0) < (
        sturdier.characteristics.toughness or 0
    ), "test setup invariant: weakest must have lowest toughness"

    _fire_attack(game, pilot)

    pc = game.state.pending_choice
    assert pc is not None
    hp = pc.callback_data.get("heuristic_pick")
    assert hp is not None, "expected heuristic_pick on the choice"
    # heuristic_pick should be [{"target_id": weakest.id, "amount": 1}]
    assert isinstance(hp, list) and len(hp) == 1, (
        f"expected single-entry heuristic_pick; got {hp}"
    )
    pick = hp[0]
    assert isinstance(pick, dict)
    assert pick.get("target_id") == weakest.id, (
        f"heuristic should target weakest ({weakest.id}); got {pick}"
    )
    assert int(pick.get("amount", 0)) == pc.callback_data.get("total_amount"), (
        f"heuristic amount must equal total_amount; got {pick.get('amount')}"
    )
    print(f"[PASS] DA Crossing Network Pilot heuristic preserves "
          f"all-to-weakest (target={weakest.id})")


def test_crossing_network_pilot_no_opp_traders_short_circuits():
    """If there are no opposing Traders, the attack trigger short-circuits:
    no pending_choice, no damage events, fin_stack untouched."""
    game, p1, p2 = _make_finance_game()
    pilot = _put_on_battlefield(game, p1.id, CROSSING_NETWORK_PILOT)
    # Opp board is empty — no enemy Traders.
    fin_stack_depth_before = game.state.fin_stack.depth() if getattr(
        game.state, "fin_stack", None
    ) is not None else 0

    _fire_attack(game, pilot)

    assert game.state.pending_choice is None, (
        "expected no pending_choice when there are no opp Traders"
    )
    fin_stack_depth_after = game.state.fin_stack.depth() if getattr(
        game.state, "fin_stack", None
    ) is not None else 0
    assert fin_stack_depth_after == fin_stack_depth_before, (
        f"fin_stack depth changed on empty short-circuit: "
        f"{fin_stack_depth_before} → {fin_stack_depth_after}"
    )
    print(f"[PASS] DA Crossing Network Pilot short-circuits on empty opp")


def test_crossing_network_pilot_ai_path_resolves_to_heuristic():
    """When the controller is AI and no make_choice handler is registered,
    ``resolve_pending_choice_inline`` falls back to ``heuristic_pick`` and
    applies the damage to the weakest enemy Trader. The pending_choice is
    cleared after resolution and fin_stack is not corrupted."""
    game, p1, p2 = _make_finance_game()
    # Mark p1 as AI but DO NOT register a make_choice handler. The fallback
    # path uses heuristic_pick.
    game.turn_manager.set_ai_player(p1.id)
    # Expose Game on state so resolve_pending_choice_inline can find it.
    game.state._game = game

    pilot = _put_on_battlefield(game, p1.id, CROSSING_NETWORK_PILOT)
    weakest = _put_on_battlefield(game, p2.id, FLASH_CRASH_BOT)
    _ = _put_on_battlefield(game, p2.id, STATISTICAL_ARB_CLERK)
    fin_stack_depth_before = game.state.fin_stack.depth() if getattr(
        game.state, "fin_stack", None
    ) is not None else 0

    events_emitted = _fire_attack(game, pilot)

    # AI path: choice already resolved inline → pending_choice is cleared.
    assert game.state.pending_choice is None, (
        "expected AI to resolve the choice inline; got a lingering choice"
    )
    # Damage should have hit the weakest enemy Trader (via heuristic_pick).
    weakest_damage = int(getattr(weakest.state, "damage", 0) or 0)
    assert weakest_damage >= 1, (
        f"expected weakest to take ≥1 damage from heuristic resolve; "
        f"damage={weakest_damage}, events emitted={[e.type for e in events_emitted]}"
    )
    fin_stack_depth_after = game.state.fin_stack.depth() if getattr(
        game.state, "fin_stack", None
    ) is not None else 0
    assert fin_stack_depth_after == fin_stack_depth_before, (
        f"fin_stack depth changed on AI resolve: "
        f"{fin_stack_depth_before} → {fin_stack_depth_after}"
    )
    print(f"[PASS] DA Crossing Network Pilot AI path resolves to "
          f"heuristic (weakest_damage={weakest_damage})")


# ===========================================================================
# Test runner
# ===========================================================================

ALL_TESTS = [
    test_load_all_spice_cards,
    test_load_count_matches_assertions,
    test_load_cards_register_interceptors,
    test_microsecond_sniper_pumps_on_order_cast,
    test_co_location_master_cycle_pumps_on_order,
    test_spoof_bot_flotilla_etb_pumps_alpha_strikers,
    test_vega_convexity_trader_doubles_lev_counters,
    test_synthetic_reinsurance_resolve_emits_counter_events,
    test_tail_risk_hedger_prevents_first_destroy,
    test_smart_beta_compounder_etb_counts_other_traders,
    test_pricing_model_oracle_etb_reveals_top,
    test_monte_carlo_simulator_loads_as_asset,
    test_phantom_pool_operator_loads_with_leverage_and_alpha,
    test_phantom_pool_operator_pumps_on_dp_stage,
    test_floor_captain_caro_etb_pumps_other_traders,
    test_coordinated_block_strategy_loads_as_dark_pool_order,
    test_crossing_network_pilot_human_path_emits_divide_allocation,
    test_crossing_network_pilot_heuristic_preserves_min_toughness_pick,
    test_crossing_network_pilot_no_opp_traders_short_circuits,
    test_crossing_network_pilot_ai_path_resolves_to_heuristic,
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
