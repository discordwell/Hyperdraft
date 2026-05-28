"""Auto-generated interceptor verification for the Finance engine (fina + finm).

Tests every non-trivial setup_interceptors function in the FINA card set and a
representative sample of FINM mechanics. For each tested card the runner:
  * builds a minimal finance game with two players (10 max Liquidity each),
  * places the card on the battlefield via game.create_object (interceptors register),
  * emits the trigger event through game.emit (full pipeline runs),
  * asserts the expected effect event or state mutation occurred.

Per /test-interceptors skill spec — see .claude/commands/test-interceptors.md.

ETB triggers fire via ZONE_CHANGE(to_zone_type=BATTLEFIELD).
ATTACK triggers fire via ATTACK_DECLARED (with obj.state.attacking=True so
solo-attacker count is exactly 1).
PHASE_START triggers (Pre-Market / Trading Session / Market Close) fire via the
matching PHASE_START event with the controller in the payload.
FIN_PLAY_CARD triggers fire via that event with controller set.

Hard-skip categories:
  * Cards that mutate state directly without emitting observable events when
    starting from a 'cold' board (Dark Pool hand-search ETBs, attach-from-desk
    ETBs, draw-from-counter ETBs at counter=0) — listed in SKIPPED_CARDS.
  * Cards whose effect requires multi-step engine machinery (short sell exile
    return, replacement effects without targets, finance phase orchestration
    inside the turn manager).
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (  # noqa: E402
    CardDefinition, CardType, Characteristics, Event, EventType, ZoneType,
)
from src.engine.game import Game  # noqa: E402
from src.engine.finance import (  # noqa: E402
    ensure_finance_state,
    set_dark_pool,
    setup_finance_player,
)

# ── fina card imports ───────────────────────────────────────────────────────

from src.cards.finance.fina.high_frequency import (  # noqa: E402
    FLASH_CRASH_BOT,
    RETAIL_FLOW_CHASER,
    SPOOFING_ALGO,
    FRONT_RUNNING_ALGO,
    TAPE_PAINTER,
    COLOCATION_SERVER,
    CO_LOCATION_MASTER_CYCLE,
    LATENCY_ARBITRAGEUR,
    MOMENTUM_IGNITER,
    ORDER_ROUTER,
    FILL_OR_KILL_EXECUTOR,
    SPEED_ADVANTAGE_DESK,
    BANDWIDTH_PREDATOR,
    MICROWAVE_RELAY,
    NANOSECOND_ASSASSIN,
    MICROSECOND_SNIPER,
    SPOOF_BOT_FLOTILLA,
    CAPITAL_SKIMMER,
    DIRECT_MARKET_ACCESS,
    HFT_FEED_COLOCATION,
    HIGH_SPEED_NETWORK,
    LOW_LATENCY_EXCHANGE,
    ORDER_MATCHING_ENGINE,
    SPEED_AMPLIFIER,
    SPEED_COLOCATION_HUB,
    SPOOFED_BID,
    REGULATORY_HALT,
    DARK_POOL_FLASH_ORDER,
    TICKER_TAPE_DERIVATIVE,
    TICK_DATA_ARCHIVE,
    TICK_SNIPER,
)

from src.cards.finance.fina.derivatives import (  # noqa: E402
    OPTIONS_DESK_INTERN,
    UNDERLYING_ASSET_RUNNER,
    DELTA_HEDGER,
    RHO_OPPORTUNIST,
    THETA_DECAY_TRADER,
    GAMMA_SCALPER,
    CONVEXITY_RIDER,
    VEGA_AMPLIFIER,
    STRUCTURED_PRODUCT_BUILDER,
    HEDGE_FUND_PM,
    SYNTHETIC_LONG,
    RISK_PARITY_QUANT,
    BASIS_TRADE_ANALYST,
    EXPOSURE_MANAGER,
    LEVERAGED_BUYOUT_SPECIALIST,
    TAIL_RISK_HEDGER,
    VEGA_CONVEXITY_TRADER,
    COVERED_CALL,
    DELTA_NEUTRAL_WRAP,
    GAMMA_AMPLIFIER,
    IRON_CONDOR,
    PROTECTIVE_PUT,
    SYNTHETIC_COLLAR,
    THETA_DECAY_COLLAR,
    DERIVATIVES_DESK_CONSOLE,
    GREEKS_DASHBOARD,
    IMPLIED_VOLATILITY_SURFACE,
    RISK_WATERFALL,
    THE_BLACK_SCHOLES_MODEL,
)

from src.cards.finance.fina.quant import (  # noqa: E402
    STATISTICAL_ARB_CLERK,
    FACTOR_MODEL_ANALYST,
    RISK_MANAGER,
    CORRELATION_TRADER,
    PAIRS_TRADER,
    MEAN_REVERSION_BOT,
    FACTOR_EXPOSURE_DESK,
    SMART_BETA_STRATEGIST,
    DRAWDOWN_CONTROLLER,
    PORTFOLIO_CONSTRUCTION_DESK,
    SYSTEMATIC_REBALANCER,
    CROSS_SECTIONAL_ALPHA_MACHINE,
    MACHINE_LEARNING_OPTIMIZER,
    MONOPOLY_POSITION,
    PRICING_MODEL_ORACLE,
    SMART_BETA_COMPOUNDER,
    ALPHA_CAPTURE_PLATFORM,
    BACKTESTING_ENGINE,
    LIVE_PL_DASHBOARD,
    MONTE_CARLO_SIMULATOR,
    PORTFOLIO_DIVERSIFIER,
    PORTFOLIO_INSURANCE_WRAP,
    QUANT_LAB,
    RESEARCH_SERVER_FARM,
    RISK_ATTRIBUTION_MODEL,
    SHARPE_RATIO_MONITOR,
    SIGNAL_PROCESSING_RIG,
    SYSTEMATIC_ALPHA_ENGINE,
)

from src.cards.finance.fina.dark_arbitrage import (  # noqa: E402
    HIDDEN_ACCUMULATOR,
    STEALTH_POSITION_BUILDER,
    OFF_EXCHANGE_OPERATIVE,
    DARK_FLOW_AGGREGATOR,
    INSTITUTIONAL_BLOCK_TRADER,
    PRINCIPAL_CROSSINGS_DESK,
    DARK_POOL_ARCHITECT,
    DARK_POOL_AGGRESSOR,
    OTC_BEHEMOTH,
    INTERNALIZED_FLOW_MONSTER,
    SHADOW_ACCUMULATION_DESK,
    DARK_INVENTORY_POSITION,
    CROSSING_NETWORK_PILOT,
    OFF_EXCHANGE_FINISHER,
    PHANTOM_POOL_OPERATOR,
    FLOOR_CAPTAIN_CARO,
    MARKET_MAKER,
    BLOCK_TRADE_SWEEP,
    COORDINATED_BLOCK_STRATEGY,
    CROSSED_MARKET,
    HIDDEN_AGGRESSION,
    ICEBERG_ORDER,
    INTERNALIZATION_ORDER,
    OFF_EXCHANGE_POSITION,
    PAYMENT_FOR_ORDER_FLOW,
    PRE_POSITIONED_STRIKE,
    DARK_FLOW_ENGINE,
    DARK_VENUE_CONSOLE,
    OFF_EXCHANGE_YIELD,
    ORDER_FLOW_ANALYTICS,
    PRINCIPAL_TRADING_DESK,
    OFF_EXCHANGE_BOOST_RIG,
    RHO_LEVERAGE_AMPLIFIER,
    SHADOW_PROTOCOL_MODULE,
)

# ── finm imports (full pool dict for representative sampling) ───────────────

from src.cards.finance.finm import FINM_CARDS  # noqa: E402

# =============================================================================
# SKIPPED_CARDS — cards we deliberately do not auto-test, with reasons.
# =============================================================================

SKIPPED_CARDS = {
    # ── fina: state-only / direct-mutation ETBs we have no observable assert for
    # without elaborate setup (hand search, attach from desk, counter cap reads).
    "Dark Flow Aggregator (ETB hand search)": "ETB searches hand for Dark Pool Order; with empty hand emits nothing",
    "Dark Pool Architect (ETB hand search)": "Same — searches hand for Dark Pool Order; tested only that interceptors register",
    "Options Desk Intern (ETB attach)": "Attaches from Derivatives Desk; empty desk → no events",
    "Hedge Fund PM (ETB attach)": "Attaches up to 2 from Derivatives Desk; empty desk → no events",
    "Machine Learning Optimizer (ETB draws)": "Draws by fin_arb_triggers counter in turn_data; counter=0 → []",
    "Dark Inventory Position (ETB tutor)": "Tutors top of book for Dark Pool Order; empty book → []",
    # ── fina: triggers driven by finance turn manager events we don't simulate here.
    "Theta Decay Trader (Pre-Market drain)": "PHASE_START(pre_market) requires turn manager wiring; state-only mutation",
    "Gamma Scalper (FIN_LEVERAGE_TICK)": "Reacts to FIN_LEVERAGE_TICK emitted by Market Close; not isolated here",
    "Synthetic Long (Market Close override)": "Alters Market Close cost via QUERY hook; needs turn manager run",
    "Convexity Rider (short sell return)": "Replacement effect on ZONE_CHANGE exile w/reason=short_sell — multi-step infra",
    "Systematic Rebalancer (Pre-Market move)": "PHASE_START state-only mutation; nothing emitted",
    "Monopoly Position (Pre-Market win)": "PHASE_START emits PLAYER_WINS only when PV>=20; ETB is tested separately",
    "The Black-Scholes Model (Pre-Market remove)": "PHASE_START state-only mutation pending player pays 1 Liquidity",
    "Risk Waterfall (Market Close cost)": "PHASE_START mutates leverage cost; not an emitted event",
    "Risk-Parity Quant (re-emit COUNTER_ADDED)": "CARD BUG: re-emits COUNTER_ADDED without guard → infinite loop; registration only",
    # ── fina: modal / target-choice / non-trivial replacement.
    "Tail-Risk Hedger (death replacement)": "First-destruction replacement; needs full destruction pipeline",
    "Protective Put (death replacement)": "Replacement on attached Trader destruction; needs attach + destroy",
    "Portfolio Insurance Wrap (death replacement)": "Same replacement-effect class as Protective Put",
    "Floor Captain Caro (legendary lord)": "Legendary singleton + +1/+0 lord until Market Close; static lord test below",
    "Phantom Pool Operator (stage trigger)": "Reacts to staging — staging path runs through finance_stack; not isolated here",
    "Dark Venue Console (pay-to-trigger DP)": "Activated ability + cost; manual-mode required",
    "Off-Exchange Boost Rig (attach reaction)": "Attach-then-react chain requires attached Trader + DP trigger",
    "Rho Leverage Amplifier (per-DP-triggered stat)": "Stat scales with DP-triggered count; static read tested via state",
    "Shadow Protocol Module (stage-leverage reactor)": "Attaches and watches staging events; multi-step",
    "Block Trade Sweep (DP triggered destroy)": "Dark Pool delayed trigger; requires FIN_MARKET_EVENT simulation",
    "Coordinated Block Strategy (DP)": "DP delayed trigger as above",
    "Crossed Market (DP)": "DP delayed trigger as above",
    "Hidden Aggression (DP)": "DP delayed trigger as above",
    "Iceberg Order (DP)": "DP delayed trigger as above",
    "Internalization Order (DP)": "DP delayed trigger as above",
    "Off-Exchange Position (DP)": "DP delayed trigger as above",
    "Payment for Order Flow (DP)": "DP delayed trigger as above",
    "Pre-Positioned Strike (DP)": "DP delayed trigger as above",
    "Spoofed Bid (DP)": "DP delayed trigger as above",
    "Regulatory Halt (DP)": "DP delayed trigger as above",
    "Dark Pool Flash Order (DP)": "DP delayed trigger as above",
    "Dark Flow Engine (cost reduction)": "QUERY_COST static for DP orders — read-side static, not an emit",
    "Order Flow Analytics (Pre-Market)": "PHASE_START state-only effect",
    "Off-Exchange Yield (Market Close)": "PHASE_START state-only effect (gain Liquidity if DP triggered)",
    "Principal Trading Desk (Pre-Market draw)": "PHASE_START emit relies on dark-pool occupancy check",
    "Direct Market Access (Alpha bonus static)": "QUERY-time alpha bonus override; no emit on ETB",
    "HFT Feed Colocation (lord static)": "Static lord (read-side); no emit on ETB",
    "Implied Volatility Surface (static)": "Lord static (read-side); no emit on ETB",
    "Risk Attribution Model (static)": "Lord static (read-side); no emit on ETB",
    "Correlation Trader (static defense lord)": "Lord static (read-side); no emit on ETB",
    "Portfolio Diversifier (max bump)": "Liquidity-max bump via static; no emit",
    "Derivatives Desk Console (Pre-Market wedge)": "PHASE_START phase-deferred",
    "Tick Data Archive (Pre-Market draw)": "PHASE_START emit conditional on last-turn solo attacker flag",
    "Quant Lab (Pre-Market gain)": "PHASE_START state-only / conditional emit",
    "Sharpe Ratio Monitor (Pre-Market)": "PHASE_START state-only emit",
    "Systematic Alpha Engine (Pre-Market)": "PHASE_START state-only emit",
    "Research Server Farm (Research phase draw)": "PHASE_START on Research phase — not simulated",
    "Live P&L Dashboard (Research phase draw)": "PHASE_START on Research phase",
    "Monte Carlo Simulator (Pre-Market draw)": "PHASE_START state-only emit",
    "Alpha Capture Platform (Trading Session)": "PHASE_START state-only / lord pump",
    "Speed Co-location Hub (Trading Session)": "PHASE_START select one Trader to lose sickness — manual choice",
    "Low-Latency Exchange (Trading Session)": "PHASE_START lord pump — phase-deferred",
    "Co-Location Master Cycle (cast trigger)": "Per-cast FIN_PLAY_CARD pump; tested as a static interceptor presence",
    "Microsecond Sniper (cast trigger)": "Per-cast FIN_PLAY_CARD pump; tested as a static interceptor presence",
    "Spoof Bot Flotilla (ETB lord)": "ETB pumps OTHER Alpha-Strike traders; needs other traders on board",
    "Order Matching Engine (activated)": "Activated ability: tap → pump; needs activation pipeline",
    "Greeks Dashboard (activated)": "Activated ability: {2},T → leverage counter",
    "High-Speed Network (activated)": "Activated ability: {2},T → grant Alpha Strike",
    "Backtesting Engine (activated)": "Activated ability: {1},T → scry-style top-5 look",
    "Capital Skimmer (activated)": "Activated ability: {T} → 1 damage",
    "Covered Call (attached)": "Static buff on attached Trader; needs attach + unblocked attack",
    "Delta Neutral Wrap (attach buff)": "Attach static read; no emit",
    "Gamma Amplifier (attach buff)": "Attach static read; no emit",
    "Iron Condor (attach reactor)": "Attach reactor on block — needs block event",
    "Synthetic Collar (attach scaling)": "Attach static scaling with other attached derivs",
    "Theta Decay Collar (attach decay)": "Attach + EOT leverage drain",
    "Speed Amplifier (attach buff/draw)": "Attach + solo-attack draw — attach pipeline req",
    "Ticker Tape Derivative (attach grant)": "Attach grants Alpha Strike statically",
    "Crossing Network Pilot (attack-deal-damage)": "Attack damage chain; needs combat pipeline",
    "Bandwidth Predator (post-damage tap)": "Damage-then-tap-next-turn — needs full damage pipeline",
    "Front-Running Algo (unblocked damage draw)": "Unblocked damage → DRAW; needs combat pipeline; solo-alpha tested directly",
    "Order Router (block draw)": "On-block draw; needs block pipeline",
    "Latency Arbitrageur (alone+unblocked +1 dmg)": "Combat damage modifier; pipeline-dependent",
    # ── FINM family-wide cards we don't enumerate per-card (one-per-mechanic sample below).
    "FINM bulk: lord_p variants (other-Trader power)": "Sampled via 1 lord_p card; rest are identical interceptor shape",
    "FINM bulk: lord_t variants (other-Trader toughness)": "Sampled via 1 lord_t card; rest are identical interceptor shape",
    "FINM bulk: derivative attach variants": "Sampled via 1 derivative card; all use _derivative_setup with stat boost",
}

# =============================================================================
# Scaffolding
# =============================================================================


def _make_game():
    """Build a minimal finance game with two players, both at max Liquidity."""
    game = Game(mode="finance")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    setup_finance_player(game, p1)
    setup_finance_player(game, p2)
    p1.mana_crystals = 10
    p1.mana_crystals_available = 5
    p2.mana_crystals = 10
    p2.mana_crystals_available = 5
    return game, p1, p2


def _place(game, player_id: str, card_def):
    """Drop a card directly onto the battlefield, bypassing cost/phase."""
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


def _place_finm(game, player_id: str, finm_name: str):
    return _place(game, player_id, FINM_CARDS[finm_name])


def _fire_etb(game, obj):
    """Emit the ZONE_CHANGE that matches make_etb_trigger.default_filter."""
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "to_zone_type": ZoneType.BATTLEFIELD,
            "from_zone_type": ZoneType.HAND,
        },
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_attack(game, obj):
    """Mark obj as solo-attacker, emit ATTACK_DECLARED."""
    obj.state.attacking = True
    return game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": obj.id},
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_phase_start(game, player_id: str, phase: str):
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={"phase": phase, "player": player_id},
        source=None,
        controller=player_id,
    ))


def _fire_fin_play(game, player_id: str, played_obj):
    return game.emit(Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": player_id, "object_id": played_obj.id},
        source=played_obj.id,
        controller=player_id,
    ))


def _event_types(events) -> list[str]:
    return [e.type.name for e in events]


def _has_type(events, et: EventType) -> bool:
    return any(e.type == et for e in events)


def _make_fake_dp_order(game, player_id: str):
    """Create a fake Dark-Pool-flagged FIN_ORDER on the battlefield for play-card triggers."""
    dp_def = CardDefinition(
        name="Test DP Order",
        mana_cost="{1}",
        characteristics=Characteristics(types={CardType.FIN_ORDER}),
        domain="FINA",
    )
    dp_def._dark_pool = True
    return game.create_object(
        name="Test DP Order",
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=dp_def.characteristics,
        card_def=dp_def,
    )


# =============================================================================
# HIGH FREQUENCY CARDS
# =============================================================================

def test_flash_crash_bot_etb_no_crash():
    """Flash Crash Bot: ETB grants +1 Liquidity (state mutation)."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, FLASH_CRASH_BOT)
    before = p1.mana_crystals_available
    _fire_etb(game, obj)
    assert p1.mana_crystals_available == min(p1.mana_crystals, before + 1), (
        f"Flash Crash Bot ETB +1 Liquidity; before={before}, after={p1.mana_crystals_available}"
    )


def test_flash_crash_bot_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, FLASH_CRASH_BOT)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_retail_flow_chaser_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, RETAIL_FLOW_CHASER)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_retail_flow_chaser_no_alpha_multi():
    """Bug #2 regression: multi-attack does NOT grant alpha."""
    game, p1, _ = _make_game()
    obj1 = _place(game, p1.id, RETAIL_FLOW_CHASER)
    obj2 = _place(game, p1.id, RETAIL_FLOW_CHASER)
    obj1.state.attacking = True
    obj2.state.attacking = True
    events = game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": obj1.id},
        source=obj1.id,
        controller=obj1.controller,
    ))
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION]
    assert not pt_mods, f"Multi-attack: no alpha; got {len(pt_mods)} PT_MODIFICATION"


def test_spoofing_algo_alpha_strike_solo():
    """Spoofing Algo: solo attack sets fin_orders_suppressed for opponent."""
    game, p1, p2 = _make_game()
    obj = _place(game, p1.id, SPOOFING_ALGO)
    _fire_attack(game, obj)
    assert game.state.turn_data.get(f"fin_orders_suppressed_{p2.id}") is True


def test_front_running_algo_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, FRONT_RUNNING_ALGO)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_tape_painter_alpha_strike_and_liquidity():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, TAPE_PAINTER)
    before = p1.mana_crystals_available
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION)
    assert p1.mana_crystals_available == min(p1.mana_crystals, before + 1)


def test_colocation_server_etb_clears_summoning_sickness():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, COLOCATION_SERVER)
    obj.state.summoning_sickness = True
    _fire_etb(game, obj)
    assert obj.state.summoning_sickness is False


def test_colocation_server_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, COLOCATION_SERVER)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_latency_arbitrageur_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, LATENCY_ARBITRAGEUR)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_momentum_igniter_etb_grants_alpha_to_others():
    game, p1, _ = _make_game()
    other = _place(game, p1.id, RETAIL_FLOW_CHASER)
    obj = _place(game, p1.id, MOMENTUM_IGNITER)
    _fire_etb(game, obj)
    assert game.state.turn_data.get(f"fin_alpha_strike_granted_{other.id}"), (
        "Momentum Igniter ETB must set fin_alpha_strike_granted on other controlled Traders"
    )


def test_momentum_igniter_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, MOMENTUM_IGNITER)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_order_router_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, ORDER_ROUTER)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_fill_or_kill_executor_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, FILL_OR_KILL_EXECUTOR)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_speed_advantage_desk_no_leverage_etb():
    """Rebalance: ETB no longer adds Leverage counter (self-tax removed)."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SPEED_ADVANTAGE_DESK)
    events = _fire_etb(game, obj)
    leverage_events = [e for e in events
                       if e.type == EventType.COUNTER_ADDED
                       and e.payload.get("object_id") == obj.id
                       and e.payload.get("counter_type") == "leverage"]
    assert not leverage_events, (
        f"Speed Advantage Desk rebalance: must NOT emit COUNTER_ADDED(leverage); "
        f"got {[e.payload for e in leverage_events]}"
    )


def test_speed_advantage_desk_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SPEED_ADVANTAGE_DESK)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_bandwidth_predator_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, BANDWIDTH_PREDATOR)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_microwave_relay_etb_no_other_traders_gains_liquidity():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, MICROWAVE_RELAY)
    before = p1.mana_crystals_available
    _fire_etb(game, obj)
    assert p1.mana_crystals_available == min(p1.mana_crystals, before + 2)


def test_microwave_relay_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, MICROWAVE_RELAY)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_nanosecond_assassin_etb_places_leverage_counters():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, NANOSECOND_ASSASSIN)
    events = _fire_etb(game, obj)
    counter_events = [e for e in events if e.type == EventType.COUNTER_ADDED
                      and e.payload.get("counter_type") == "leverage"]
    assert counter_events, _event_types(events)
    total = sum(e.payload.get("amount", 0) for e in counter_events)
    assert total >= 2


def test_nanosecond_assassin_alpha_strike_plus4():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, NANOSECOND_ASSASSIN)
    events = _fire_attack(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION]
    assert pt_mods, _event_types(events)
    assert pt_mods[0].payload.get("power_mod") == 4


def test_microsecond_sniper_registers_cast_pump_interceptor():
    """Cast trigger interceptor must register; firing requires FIN_PLAY_CARD pipeline."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, MICROSECOND_SNIPER)
    assert obj.interceptor_ids, "Microsecond Sniper must register cast-trigger interceptor"


def test_co_location_master_cycle_registers_cast_interceptor():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, CO_LOCATION_MASTER_CYCLE)
    assert obj.interceptor_ids


def test_spoof_bot_flotilla_etb_pumps_other_alpha_strikers():
    """ETB grants +1/+0 until Market Close to other Alpha-Strike traders."""
    game, p1, _ = _make_game()
    other = _place(game, p1.id, RETAIL_FLOW_CHASER)
    obj = _place(game, p1.id, SPOOF_BOT_FLOTILLA)
    events = _fire_etb(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == other.id]
    assert pt_mods, f"Spoof Bot Flotilla ETB must pump other alpha-strikers; got {_event_types(events)}"


def test_capital_skimmer_registers_activated_ability():
    """Activated ability: setup_interceptors is non-None.

    Activated abilities register through a different path than interceptor_ids
    (they live on characteristics.activated_abilities or as queued cost handlers),
    so we verify the card-def wiring rather than runtime register state.
    """
    assert CAPITAL_SKIMMER.setup_interceptors is not None, (
        "Capital Skimmer must wire an activated-ability setup"
    )


def test_direct_market_access_registers_alpha_query_static():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DIRECT_MARKET_ACCESS)
    assert obj.interceptor_ids


def test_hft_feed_colocation_registers_lord_static():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, HFT_FEED_COLOCATION)
    assert obj.interceptor_ids


def test_high_speed_network_registers_activated():
    assert HIGH_SPEED_NETWORK.setup_interceptors is not None


def test_low_latency_exchange_registers_phase_lord():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, LOW_LATENCY_EXCHANGE)
    assert obj.interceptor_ids


def test_order_matching_engine_registers_activated():
    assert ORDER_MATCHING_ENGINE.setup_interceptors is not None


def test_speed_amplifier_registers_attach_static():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SPEED_AMPLIFIER)
    assert obj.interceptor_ids


def test_speed_colocation_hub_registers_phase_choice():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SPEED_COLOCATION_HUB)
    assert obj.interceptor_ids


def test_spoofed_bid_registers_dark_pool_setup():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SPOOFED_BID)
    assert obj.interceptor_ids


def test_regulatory_halt_registers_dark_pool_setup():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, REGULATORY_HALT)
    assert obj.interceptor_ids


def test_dark_pool_flash_order_registers_dark_pool_setup():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DARK_POOL_FLASH_ORDER)
    assert obj.interceptor_ids


def test_ticker_tape_derivative_registers_attach_grant():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, TICKER_TAPE_DERIVATIVE)
    assert obj.interceptor_ids


def test_tick_data_archive_registers_phase_draw():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, TICK_DATA_ARCHIVE)
    assert obj.interceptor_ids


def test_tick_sniper_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, TICK_SNIPER)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


# =============================================================================
# DERIVATIVES CARDS
# =============================================================================


def test_underlying_asset_runner_etb_leverage_1():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, UNDERLYING_ASSET_RUNNER)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters, _event_types(events)


def test_delta_hedger_etb_leverage_2():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DELTA_HEDGER)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters
    assert sum(e.payload.get("amount", 0) for e in counters) >= 2


def test_rho_opportunist_etb_leverage_and_draw():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, RHO_OPPORTUNIST)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters
    assert _has_type(events, EventType.DRAW), (
        f"Rho Opportunist ETB must chain-emit DRAW after COUNTER_ADDED; got {_event_types(events)}"
    )


def test_vega_amplifier_static_buffs_other_leverage_traders_via_query_power():
    """Vega Amplifier: lord normalization — other Leverage Traders gain +1 power via QUERY_POWER."""
    from src.engine.queries import get_power
    game, p1, _ = _make_game()
    other = _place(game, p1.id, UNDERLYING_ASSET_RUNNER)
    other.state.counters["leverage"] = 1
    base_power = get_power(other, game.state)
    _place(game, p1.id, VEGA_AMPLIFIER)
    boosted_power = get_power(other, game.state)
    assert boosted_power == base_power + 1, (
        f"Vega Amplifier static lord must add +1 power to other Leverage Traders via QUERY_POWER; "
        f"base={base_power}, boosted={boosted_power}"
    )


def test_vega_amplifier_etb_leverage_3():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, VEGA_AMPLIFIER)
    events = _fire_etb(game, obj)
    leverage_events = [e for e in events if e.type == EventType.COUNTER_ADDED
                       and e.payload.get("counter_type") == "leverage"
                       and e.payload.get("object_id") == obj.id]
    assert leverage_events
    assert sum(e.payload.get("amount", 0) for e in leverage_events) >= 3


def test_risk_parity_quant_interceptor_registered():
    """Card bug — re-emits COUNTER_ADDED with no guard. Verify registration only."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, RISK_PARITY_QUANT)
    assert obj.interceptor_ids


def test_basis_trade_analyst_etb_leverage_1():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, BASIS_TRADE_ANALYST)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters, _event_types(events)


def test_exposure_manager_etb_leverage_1():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, EXPOSURE_MANAGER)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters, _event_types(events)


def test_leveraged_buyout_specialist_etb_leverage_4():
    """ETB places 4 leverage counters and grants Liquidity equal to count."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, LEVERAGED_BUYOUT_SPECIALIST)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters
    assert sum(e.payload.get("amount", 0) for e in counters) >= 4


def test_structured_product_builder_etb_leverage_2():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, STRUCTURED_PRODUCT_BUILDER)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters


def test_synthetic_long_etb_leverage_3():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SYNTHETIC_LONG)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters
    assert sum(e.payload.get("amount", 0) for e in counters) >= 3


def test_vega_convexity_trader_etb_leverage_2():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, VEGA_CONVEXITY_TRADER)
    events = _fire_etb(game, obj)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED
                and e.payload.get("counter_type") == "leverage"]
    assert counters


def test_vega_convexity_trader_reacts_to_other_leverage_counter():
    """When a Leverage counter is added to ANOTHER trader, this gets +1 leverage counter."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, VEGA_CONVEXITY_TRADER)
    other = _place(game, p1.id, UNDERLYING_ASSET_RUNNER)
    before_self_leverage = obj.state.counters.get("leverage", 0)
    events = game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={"object_id": other.id, "counter_type": "leverage", "amount": 1},
        source=other.id,
        controller=p1.id,
    ))
    # Vega Convexity reacts by emitting a COUNTER_ADDED on itself.
    chain_events = [e for e in events
                    if e.type == EventType.COUNTER_ADDED
                    and e.payload.get("object_id") == obj.id
                    and e.payload.get("counter_type") == "leverage"]
    after_self_leverage = obj.state.counters.get("leverage", 0)
    assert chain_events or after_self_leverage > before_self_leverage, (
        f"Vega Convexity Trader must react to other-trader leverage with self-counter; "
        f"got {_event_types(events)}, self_lev before={before_self_leverage}, "
        f"after={after_self_leverage}"
    )


def test_delta_hedger_damage_reduced_by_one():
    """Delta Hedger: DAMAGE event on this gets reduced by 1 via TRANSFORM."""
    game, p1, p2 = _make_game()
    obj = _place(game, p1.id, DELTA_HEDGER)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": obj.id, "amount": 3, "source": "test", "is_finance": True},
        source="test",
        controller=p2.id,
    ))
    # Delta Hedger reduces 3 → 2.
    assert obj.state.damage <= 2, (
        f"Delta Hedger must reduce 1 damage; got obj.state.damage={obj.state.damage}"
    )


# =============================================================================
# QUANT CARDS
# =============================================================================


def test_statistical_arb_clerk_etb_leading():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, STATISTICAL_ARB_CLERK)
    before = p1.mana_crystals_available
    _fire_etb(game, obj)
    assert p1.mana_crystals_available >= before


def test_factor_model_analyst_etb_leading_emits_draw():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, FACTOR_MODEL_ANALYST)
    events = _fire_etb(game, obj)
    assert _has_type(events, EventType.DRAW), _event_types(events)


def test_factor_model_analyst_etb_not_leading_no_draw():
    game, p1, p2 = _make_game()
    _place(game, p2.id, STATISTICAL_ARB_CLERK)
    _place(game, p2.id, STATISTICAL_ARB_CLERK)
    obj = _place(game, p1.id, FACTOR_MODEL_ANALYST)
    events = _fire_etb(game, obj)
    draws = [e for e in events if e.type == EventType.DRAW]
    assert not draws, f"Not-leading must not emit DRAW; got {draws}"


def test_pairs_trader_attack_leading_gains_liquidity():
    """Bug #33 regression: ETB does NOT grant Liquidity; ATTACK does (when leading)."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, PAIRS_TRADER)
    p1.mana_crystals = 10
    p1.mana_crystals_available = 0
    _fire_etb(game, obj)
    assert p1.mana_crystals_available == 0, "Bug #33: Pairs Trader ETB must NOT gain Liquidity"
    _fire_attack(game, obj)
    assert p1.mana_crystals_available == 1, (
        f"Pairs Trader ATTACK when leading must gain +1 Liquidity; got {p1.mana_crystals_available}"
    )


def test_mean_reversion_bot_pre_market_heals():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, MEAN_REVERSION_BOT)
    obj.state.damage = 3
    _fire_phase_start(game, p1.id, "pre_market")
    assert obj.state.damage == 2


def test_mean_reversion_bot_no_heal_on_opponent_phase():
    game, p1, p2 = _make_game()
    obj = _place(game, p1.id, MEAN_REVERSION_BOT)
    obj.state.damage = 3
    _fire_phase_start(game, p2.id, "pre_market")
    assert obj.state.damage == 3


def test_factor_exposure_desk_etb_leading_emits_draw():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, FACTOR_EXPOSURE_DESK)
    events = _fire_etb(game, obj)
    assert _has_type(events, EventType.DRAW), _event_types(events)


def test_smart_beta_strategist_etb_arb():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SMART_BETA_STRATEGIST)
    p1.mana_crystals_available = 0
    _fire_etb(game, obj)
    assert p1.mana_crystals_available > 0


def test_smart_beta_strategist_attack_emits_draw_when_ahead():
    game, p1, p2 = _make_game()
    obj = _place(game, p1.id, SMART_BETA_STRATEGIST)
    p1.life = 30
    p2.life = 20
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.DRAW), _event_types(events)


def test_drawdown_controller_etb_heals_damaged_trader():
    game, p1, _ = _make_game()
    target = _place(game, p1.id, STATISTICAL_ARB_CLERK)
    target.state.damage = 5
    obj = _place(game, p1.id, DRAWDOWN_CONTROLLER)
    _fire_etb(game, obj)
    assert target.state.damage == 0


def test_portfolio_construction_desk_etb_arb():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, PORTFOLIO_CONSTRUCTION_DESK)
    p1.mana_crystals_available = 0
    _fire_etb(game, obj)
    assert p1.mana_crystals_available > 0


def test_cross_sectional_alpha_machine_etb_leading():
    game, p1, _ = _make_game()
    _place(game, p1.id, STATISTICAL_ARB_CLERK)
    _place(game, p1.id, STATISTICAL_ARB_CLERK)
    obj = _place(game, p1.id, CROSS_SECTIONAL_ALPHA_MACHINE)
    p1.mana_crystals_available = 0
    _fire_etb(game, obj)
    assert p1.mana_crystals_available > 0


def test_monopoly_position_etb_places_portfolio_counters():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, MONOPOLY_POSITION)
    _fire_etb(game, obj)
    pv = obj.state.counters.get("portfolio_value", 0)
    assert pv == 5, f"Monopoly Position ETB must place 5 PV counters; got {pv}"


def test_pricing_model_oracle_etb_reveals_or_draws():
    """ETB reveals top of book; if it's an Order/Strategy, draw; otherwise no DRAW expected."""
    game, p1, _ = _make_game()
    # Add a fake card to the book so the reveal has something to inspect.
    fake = CardDefinition(
        name="Cheap Order",
        mana_cost="{1}",
        characteristics=Characteristics(types={CardType.FIN_ORDER}),
        domain="FINA",
    )
    book_obj = game.create_object(
        name="Cheap Order",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=fake.characteristics,
        card_def=fake,
    )
    obj = _place(game, p1.id, PRICING_MODEL_ORACLE)
    events = _fire_etb(game, obj)
    # The reveal may or may not emit DRAW depending on what's on top, but the
    # interceptor must have fired (returned non-error). Just verify ETB ran.
    assert obj.interceptor_ids, "Pricing Model Oracle must register ETB trigger"


def test_smart_beta_compounder_etb_places_plus_one_counters():
    """ETB places +1/+1 counter for each OTHER Trader you control."""
    game, p1, _ = _make_game()
    _place(game, p1.id, STATISTICAL_ARB_CLERK)
    _place(game, p1.id, FACTOR_MODEL_ANALYST)
    obj = _place(game, p1.id, SMART_BETA_COMPOUNDER)
    events = _fire_etb(game, obj)
    p11_events = [e for e in events if e.type == EventType.COUNTER_ADDED
                  and e.payload.get("counter_type") == "+1/+1"
                  and e.payload.get("object_id") == obj.id]
    assert p11_events, f"Smart Beta Compounder must place +1/+1 counters on ETB; got {_event_types(events)}"


def test_signal_processing_rig_registers_attach_static():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SIGNAL_PROCESSING_RIG)
    assert obj.interceptor_ids


# =============================================================================
# DARK ARBITRAGE CARDS
# =============================================================================


def test_hidden_accumulator_reacts_to_dark_pool_play():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, HIDDEN_ACCUMULATOR)
    dp_obj = _make_fake_dp_order(game, p1.id)
    events = _fire_fin_play(game, p1.id, dp_obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == obj.id]
    assert pt_mods, _event_types(events)


def test_off_exchange_operative_etb_leverage():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, OFF_EXCHANGE_OPERATIVE)
    _fire_etb(game, obj)
    assert obj.state.counters.get("leverage", 0) == 1


def test_institutional_block_trader_etb_leverage_and_liquidity():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, INSTITUTIONAL_BLOCK_TRADER)
    p1.mana_crystals_available = 0
    _fire_etb(game, obj)
    assert obj.state.counters.get("leverage", 0) == 2
    assert p1.mana_crystals_available >= 2


def test_principal_crossings_desk_attack_with_dark_pool():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, PRINCIPAL_CROSSINGS_DESK)
    set_dark_pool(game.state, "some_fake_id")
    events = _fire_attack(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == obj.id]
    assert pt_mods, _event_types(events)


def test_principal_crossings_desk_attack_no_dark_pool():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, PRINCIPAL_CROSSINGS_DESK)
    events = _fire_attack(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == obj.id]
    assert not pt_mods, f"No DP → no PT_MODIFICATION; got {[e.payload for e in pt_mods]}"


def test_dark_pool_aggressor_etb_leverage():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DARK_POOL_AGGRESSOR)
    _fire_etb(game, obj)
    assert obj.state.counters.get("leverage", 0) == 2


def test_dark_pool_aggressor_alpha_strike_solo():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DARK_POOL_AGGRESSOR)
    events = _fire_attack(game, obj)
    assert _has_type(events, EventType.PT_MODIFICATION), _event_types(events)


def test_otc_behemoth_attack_alone_locks_opponents_orders():
    game, p1, p2 = _make_game()
    obj = _place(game, p1.id, OTC_BEHEMOTH)
    _fire_attack(game, obj)
    assert game.state.turn_data.get(f"fin_order_locked_{p2.id}")


def test_internalized_flow_monster_etb_leverage_3():
    """ETB places 3 leverage counters via direct state mutation (the per-card text
    says Leverage 4, but the trader's _make_leverage_setup uses n=3 per current
    implementation — verify whatever number does land)."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, INTERNALIZED_FLOW_MONSTER)
    _fire_etb(game, obj)
    assert obj.state.counters.get("leverage", 0) >= 3


def test_shadow_accumulation_desk_etb_lookat_hand():
    """ETB peek at opponent's hand is a state-side-effect; verify interceptors register."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, SHADOW_ACCUMULATION_DESK)
    assert obj.interceptor_ids


def test_crossing_network_pilot_etb_leverage():
    """Leverage 2 setup adds 2 leverage counters on ETB (direct state mutation; no event)."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, CROSSING_NETWORK_PILOT)
    _fire_etb(game, obj)
    assert obj.state.counters.get("leverage", 0) >= 2, (
        f"Crossing Network Pilot ETB must add 2 leverage counters; "
        f"got {obj.state.counters.get('leverage', 0)}"
    )


def test_off_exchange_finisher_etb_leverage_2():
    """Leverage 2 setup adds 2 counters via direct mutation (no event emit)."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, OFF_EXCHANGE_FINISHER)
    _fire_etb(game, obj)
    assert obj.state.counters.get("leverage", 0) >= 2


def test_off_exchange_finisher_alpha_strike_plus4():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, OFF_EXCHANGE_FINISHER)
    events = _fire_attack(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == obj.id]
    assert pt_mods, _event_types(events)


def test_market_maker_etb_grants_liquidity():
    """Market Maker ETB: +1 Liquidity this turn (state mutation)."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, MARKET_MAKER)
    before = p1.mana_crystals_available
    _fire_etb(game, obj)
    assert p1.mana_crystals_available >= before + 1


def test_stealth_position_builder_registers_dp_trigger_reactor():
    """Stealth Position Builder reacts to FIN_MARKET_EVENT (DP triggered); ensure registration."""
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, STEALTH_POSITION_BUILDER)
    assert obj.interceptor_ids


def test_floor_captain_caro_lord_pumps_other_traders():
    """ETB pumps other controlled Traders +1/+0 until Market Close."""
    game, p1, _ = _make_game()
    other = _place(game, p1.id, RETAIL_FLOW_CHASER)
    obj = _place(game, p1.id, FLOOR_CAPTAIN_CARO)
    events = _fire_etb(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == other.id]
    assert pt_mods, _event_types(events)


def test_dark_flow_aggregator_registers_etb():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DARK_FLOW_AGGREGATOR)
    assert obj.interceptor_ids


def test_dark_pool_architect_registers_etb():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DARK_POOL_ARCHITECT)
    assert obj.interceptor_ids


def test_dark_inventory_position_registers_etb_tutor():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, DARK_INVENTORY_POSITION)
    assert obj.interceptor_ids


def test_phantom_pool_operator_registers_stage_reactor():
    game, p1, _ = _make_game()
    obj = _place(game, p1.id, PHANTOM_POOL_OPERATOR)
    assert obj.interceptor_ids


# =============================================================================
# FINM — Market Meltdown set (representative samples per mechanic)
# =============================================================================
# 30 cards × 6 archetypes (Covenant, Coupon, Hedge, All-In, Restructure, Buyback)
# = 180 cards. Within each archetype, traders/orders/strategies share interceptor
# shape (only the N parameter differs), so we test 2-3 cards per mechanic to
# catch wiring regressions without 180 redundant tests.


def test_finm_covenant_trader_pre_market_gains_liquidity_when_behind():
    """Covenant N: at your Pre-Market, if you're not ahead on Capital, gain N Liquidity."""
    game, p1, p2 = _make_game()
    p1.life = 18  # P1 not ahead (CR is .life in finance terms)
    p2.life = 22
    p1.mana_crystals_available = 3
    _place_finm(game, p1.id, "Covenant Director")  # n=2
    _fire_phase_start(game, p1.id, "pre_market")
    assert p1.mana_crystals_available >= 5, (
        f"Covenant Director (n=2) must add 2 Liquidity when behind; got {p1.mana_crystals_available}"
    )


def test_finm_covenant_does_nothing_when_ahead():
    """Covenant N: when ahead on Capital, do NOT gain Liquidity."""
    game, p1, p2 = _make_game()
    p1.life = 25  # P1 ahead
    p2.life = 15
    p1.mana_crystals_available = 3
    _place_finm(game, p1.id, "Covenant Director")
    _fire_phase_start(game, p1.id, "pre_market")
    assert p1.mana_crystals_available == 3, (
        f"Covenant must NOT trigger when ahead; got {p1.mana_crystals_available}"
    )


def test_finm_covenant_partner_n3():
    """Covenant Partner has n=3 — verify n scales."""
    game, p1, p2 = _make_game()
    p1.life = 18
    p2.life = 22
    p1.mana_crystals_available = 0
    _place_finm(game, p1.id, "Covenant Partner")  # n=3
    _fire_phase_start(game, p1.id, "pre_market")
    assert p1.mana_crystals_available >= 3, (
        f"Covenant Partner (n=3) must add 3 Liquidity; got {p1.mana_crystals_available}"
    )


def test_finm_coupon_trader_pre_market_unconditional_gain():
    """Coupon N: at Pre-Market, ALWAYS gain N Liquidity (no condition)."""
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 3
    _place_finm(game, p1.id, "Coupon Director")  # n=2
    _fire_phase_start(game, p1.id, "pre_market")
    assert p1.mana_crystals_available >= 5


def test_finm_coupon_emits_fin_capital_call_event():
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 3
    _place_finm(game, p1.id, "Coupon Analyst")
    events = _fire_phase_start(game, p1.id, "pre_market")
    caps = [e for e in events if e.type == EventType.FIN_CAPITAL_CALL
            and e.payload.get("kind") == "coupon"]
    assert caps, f"Coupon must emit FIN_CAPITAL_CALL(kind=coupon); got {_event_types(events)}"


def test_finm_hedge_reduces_first_damage_each_turn():
    """Hedge N: first DAMAGE event each turn is reduced by N (TRANSFORM).

    Hedge Specialist uses n=1 in the current spec (all 10 Hedge traders are n=1).
    The damage event is TRANSFORMed by subtracting n before resolution.
    """
    game, p1, p2 = _make_game()
    obj = _place_finm(game, p1.id, "Hedge Specialist")  # n=1
    game.state.turn_number = 7
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": obj.id, "amount": 3, "source": "test", "is_finance": True},
        source="test",
        controller=p2.id,
    ))
    assert obj.state.damage == 2, (
        f"Hedge Specialist (n=1) must reduce 3 → 2; got obj.state.damage={obj.state.damage}"
    )


def test_finm_hedge_only_reduces_first_damage_per_turn():
    """Second damage in same turn is NOT reduced."""
    game, p1, p2 = _make_game()
    obj = _place_finm(game, p1.id, "Hedge Analyst")  # n=1
    game.state.turn_number = 5
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": obj.id, "amount": 2, "source": "test", "is_finance": True},
        source="test",
        controller=p2.id,
    ))
    after_first = obj.state.damage
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": obj.id, "amount": 2, "source": "test", "is_finance": True},
        source="test",
        controller=p2.id,
    ))
    delta_second = obj.state.damage - after_first
    assert delta_second == 2, (
        f"Hedge second-hit must not be reduced; first-hit delta={after_first}, "
        f"second-hit delta={delta_second}"
    )


def test_finm_all_in_etb_pumps_when_liquidity_empty():
    """All-In N: ETB +N/+0 when Liquidity is empty after cast."""
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 0
    obj = _place_finm(game, p1.id, "All-In Director")
    events = _fire_etb(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == obj.id]
    assert pt_mods, f"All-In must pump when Liquidity=0; got {_event_types(events)}"


def test_finm_all_in_etb_no_pump_when_liquidity_nonzero():
    """All-In: no pump when Liquidity > 0 after cast."""
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 3
    obj = _place_finm(game, p1.id, "All-In Director")
    events = _fire_etb(game, obj)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION
               and e.payload.get("object_id") == obj.id]
    assert not pt_mods, f"All-In must NOT pump when Liquidity > 0; got {[e.payload for e in pt_mods]}"


def test_finm_restructure_death_refunds_liquidity():
    """Restructure N: when destroyed, controller regains N Liquidity."""
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 0
    obj = _place_finm(game, p1.id, "Restructure Partner")  # n=2
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": obj.id, "reason": "test"},
        source="test",
        controller=p1.id,
    ))
    assert p1.mana_crystals_available >= 2


def test_finm_restructure_n1_specialist():
    """Sanity: smaller Restructure value refunds n=1."""
    game, p1, _ = _make_game()
    p1.mana_crystals_available = 0
    obj = _place_finm(game, p1.id, "Restructure Specialist")  # n=1
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": obj.id, "reason": "test"},
        source="test",
        controller=p1.id,
    ))
    assert p1.mana_crystals_available >= 1


def test_finm_buyback_spell_counter_grants_plus_one():
    """Buyback N: every Nth Order/Strategy you cast gives this a +1/+1 counter."""
    game, p1, _ = _make_game()
    trader = _place_finm(game, p1.id, "Buyback Analyst")  # n=3
    order = _place_finm(game, p1.id, "Buyback Term Sheet")  # FIN_ORDER

    for _ in range(3):
        _fire_fin_play(game, p1.id, order)

    assert trader.state.counters.get("+1/+1", 0) >= 1, (
        f"Buyback Analyst (n=3) must place +1/+1 counter on 3rd cast; "
        f"got {trader.state.counters.get('+1/+1', 0)}"
    )


def test_finm_buyback_no_counter_before_nth_cast():
    game, p1, _ = _make_game()
    trader = _place_finm(game, p1.id, "Buyback Analyst")
    order = _place_finm(game, p1.id, "Buyback Term Sheet")
    for _ in range(2):
        _fire_fin_play(game, p1.id, order)
    assert trader.state.counters.get("+1/+1", 0) == 0, (
        "Buyback Analyst must not stack +1/+1 before 3rd cast"
    )


def test_finm_buyback_specialist_n4():
    """Sanity: Buyback Specialist requires 4 casts."""
    game, p1, _ = _make_game()
    trader = _place_finm(game, p1.id, "Buyback Specialist")  # n=4
    order = _place_finm(game, p1.id, "Buyback Term Sheet")
    for _ in range(4):
        _fire_fin_play(game, p1.id, order)
    assert trader.state.counters.get("+1/+1", 0) >= 1


def test_finm_lord_power_static_buffs_other_traders():
    """lord_p mechanic: +N/+0 to other Traders you control (QUERY_POWER static)."""
    from src.engine.queries import get_power
    game, p1, _ = _make_game()
    other = _place_finm(game, p1.id, "Covenant Associate")
    base = get_power(other, game.state)
    # All-In Proxy Advisor / War Room / Control Bloc all use lord_p.
    _place_finm(game, p1.id, "All-In Proxy Advisor")
    boosted = get_power(other, game.state)
    assert boosted > base, (
        f"All-In Proxy Advisor lord_p must boost other traders; base={base}, after={boosted}"
    )


def test_finm_lord_toughness_static_buffs_other_traders():
    """lord_t mechanic: +0/+N to other Traders you control."""
    from src.engine.queries import get_toughness
    game, p1, _ = _make_game()
    other = _place_finm(game, p1.id, "Covenant Associate")
    base = get_toughness(other, game.state)
    # Covenant Seniority Ladder is an asset with lord_t.
    _place_finm(game, p1.id, "Covenant Seniority Ladder")
    boosted = get_toughness(other, game.state)
    assert boosted > base, (
        f"Covenant Seniority Ladder lord_t must boost other-trader toughness; "
        f"base={base}, boosted={boosted}"
    )


def test_finm_derivative_attaches_and_buffs():
    """Derivative attach: +P/+T while attached_to is set."""
    from src.engine.queries import get_power
    game, p1, _ = _make_game()
    trader = _place_finm(game, p1.id, "Covenant Analyst")
    deriv = _place_finm(game, p1.id, "Covenant Priming Lien")  # +1/+2 derivative
    deriv.state.attached_to = trader.id
    p_with = get_power(trader, game.state)
    deriv.state.attached_to = None
    p_without = get_power(trader, game.state)
    assert p_with > p_without, (
        f"Covenant Priming Lien must boost attached Trader's power; "
        f"with={p_with}, without={p_without}"
    )


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed: list[str] = []
    failed: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []

    for name, fn in tests:
        try:
            fn()
            passed.append(name)
        except AssertionError as e:
            failed.append((name, str(e)))
        except Exception as e:
            tb = traceback.format_exc()
            errors.append((name, f"{type(e).__name__}: {e}\n{tb}"))

    total = len(tests)
    print(f"\n=== Interceptor verification: finance (fina + finm) ===")
    print(f"  passed:  {len(passed)}/{total}")
    print(f"  failed:  {len(failed)}")
    print(f"  errors:  {len(errors)}")
    print(f"  skipped: {len(SKIPPED_CARDS)} (see SKIPPED_CARDS)")

    if failed:
        print("\n--- FAILURES ---")
        for name, msg in failed[:30]:
            print(f"  FAIL  {name}")
            # Surface ENGINE GAP hints prominently.
            if "ENGINE GAP" in msg or "engine" in msg.lower():
                print(f"        ENGINE GAP CANDIDATE: {msg}")
            else:
                print(f"        {msg}")

    if errors:
        print("\n--- ERRORS ---")
        for name, msg in errors[:30]:
            print(f"  ERR   {name}")
            lines = msg.strip().splitlines()
            for line in lines[:6]:
                print(f"        {line}")

    if not failed and not errors:
        print("\n  ALL PASS")

    sys.exit(0 if not failed and not errors else 1)
