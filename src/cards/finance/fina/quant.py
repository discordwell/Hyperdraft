"""FINA — QUANT archetype card set (37 cards).

Strategy: Generate overwhelming Liquidity advantage through Arbitrage triggers
and passive Asset engines. High-defense/low-aggression Traders survive long
enough for Arbitrage to fire. Win by grinding out card advantage and outvaluing
the opponent.

Key mechanics implemented:
- ARBITRAGE N  — ETB trigger: if you lead in Trader count, gain N Liquidity.
- Static lord effects ("+0/+1 to Traders with Defense Rating 3+").
- Pre-Market passive income (Assets / Structures granting Liquidity if leading).
- MONOPOLY POSITION alternate win (Portfolio Value counters ≥ 20).
- Draw effects via EventType.DRAW.
- Counter target Strategy via EventType.COUNTER.
- Scry-style look-at-top via EventType.LOOK_AT_TOP.
"""

from __future__ import annotations

from src.engine.types import (
    CardDefinition,
    CardType,
    Characteristics,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)
from src.cards.interceptor_helpers import make_etb_trigger, make_upkeep_trigger


# =============================================================================
# Helpers shared across all Finance card factories in this file
# =============================================================================

def _cost_int(cost_str: str) -> int:
    """'{3}' -> 3. Simple generic-mana extractor."""
    return int(cost_str.strip("{}"))


# ---------------------------------------------------------------------------
# Trader-count helper
# ---------------------------------------------------------------------------

def _count_traders(state: GameState, player_id: str) -> int:
    """Count FIN_TRADER objects on the battlefield controlled by player_id."""
    bf = state.zones.get("battlefield")
    if not bf:
        return 0
    count = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if (o and o.zone == ZoneType.BATTLEFIELD and
                o.controller == player_id and
                CardType.FIN_TRADER in o.characteristics.types):
            count += 1
    return count


def _player_leads_traders(state: GameState, player_id: str) -> bool:
    """Return True if player_id controls more Traders than all opponents combined."""
    my_count = _count_traders(state, player_id)
    for pid in state.players:
        if pid != player_id:
            if _count_traders(state, pid) >= my_count:
                return False
    return my_count > 0 or True  # lead = strictly greater


def _player_leads_traders_strict(state: GameState, player_id: str) -> bool:
    """True only if player_id has strictly more Traders than any single opponent."""
    my_count = _count_traders(state, player_id)
    for pid in state.players:
        if pid != player_id and _count_traders(state, pid) >= my_count:
            return False
    return True


# ---------------------------------------------------------------------------
# Gain Liquidity helper
# ---------------------------------------------------------------------------

def _gain_liquidity(state: GameState, player_id: str, amount: int) -> None:
    """Directly increment player's available Liquidity, capped at maximum."""
    player = state.players.get(player_id)
    if not player:
        return
    player.mana_crystals_available = min(
        player.mana_crystals_available + amount,
        player.mana_crystals,
    )


# =============================================================================
# Card-type factory helpers
# =============================================================================

def make_trader(
    name: str,
    cost: str,
    power: int,
    toughness: int,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=Characteristics(
            types={CardType.FIN_TRADER},
            power=power,
            toughness=toughness,
            mana_cost=cost,
        ),
        domain="FINA",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


def make_order(
    name: str,
    cost: str,
    text: str = "",
    rarity: str = "common",
    resolve=None,
    setup_interceptors=None,
) -> CardDefinition:
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=Characteristics(types={CardType.FIN_ORDER}, mana_cost=cost),
        domain="FINA",
        text=text,
        rarity=rarity,
        resolve=resolve,
        setup_interceptors=setup_interceptors,
    )


def make_strategy(
    name: str,
    cost: str,
    text: str = "",
    rarity: str = "common",
    resolve=None,
) -> CardDefinition:
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=Characteristics(types={CardType.FIN_STRATEGY}, mana_cost=cost),
        domain="FINA",
        text=text,
        rarity=rarity,
        resolve=resolve,
    )


def make_asset(
    name: str,
    cost: str,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=Characteristics(types={CardType.FIN_ASSET}, mana_cost=cost),
        domain="FINA",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


def make_structure(
    name: str,
    cost: str,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=Characteristics(types={CardType.FIN_STRUCTURE}, mana_cost=cost),
        domain="FINA",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


def make_derivative(
    name: str,
    cost: str,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=Characteristics(types={CardType.FIN_DERIVATIVE}, mana_cost=cost),
        domain="FINA",
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


# =============================================================================
# ARBITRAGE setup factory
# =============================================================================

def _make_arbitrage_setup(n: int):
    """Return a setup_interceptors function that grants Arbitrage N on ETB."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect_fn(event: Event, state: GameState) -> list[Event]:
            if _player_leads_traders_strict(state, obj.controller):
                _gain_liquidity(state, obj.controller, n)
            return []

        return [make_etb_trigger(obj, effect_fn)]

    return setup


# =============================================================================
# PRE-MARKET phase filter (fires for controller at the start of Pre-Market)
# =============================================================================

def _make_pre_market_interceptor(
    obj: GameObject,
    effect_fn,
) -> Interceptor:
    """Register a REACT interceptor that fires at the start of the controller's Pre-Market."""
    def pm_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") in ("pre_market", "upkeep")
            and event.payload.get("player") == obj.controller
        )

    def pm_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=pm_filter,
        handler=pm_handler,
        duration="while_on_battlefield",
    )


def _make_research_phase_interceptor(obj: GameObject, effect_fn) -> Interceptor:
    """Fires at the start of the controller's Research phase."""
    def r_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") in ("research", "draw")
            and event.payload.get("player") == obj.controller
        )

    def r_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=r_filter,
        handler=r_handler,
        duration="while_on_battlefield",
    )


def _make_trading_session_interceptor(obj: GameObject, effect_fn) -> Interceptor:
    """Fires at the start of the controller's Trading Session."""
    def ts_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") in ("trading_session", "main")
            and event.payload.get("player") == obj.controller
        )

    def ts_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=ts_filter,
        handler=ts_handler,
        duration="while_on_battlefield",
    )


# =============================================================================
# STATIC TOUGHNESS LORD ("+0/+1 to your Traders with Defense Rating ≥ threshold")
# =============================================================================

def _make_defense_lord_interceptor(
    obj: GameObject,
    threshold: int = 3,
    bonus: int = 1,
) -> Interceptor:
    """Static: other FIN_TRADER objects you control with toughness ≥ threshold get +0/+bonus."""
    def toughness_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.QUERY_TOUGHNESS
            and event.payload.get("object_id") != obj.id
        )

    def toughness_effect(event: Event, state: GameState) -> InterceptorResult:
        target_id = event.payload.get("object_id")
        if not target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(target_id)
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        if target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if CardType.FIN_TRADER not in target.characteristics.types:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Use the base toughness from characteristics as "Defense Rating"
        base_t = target.characteristics.toughness or 0
        if base_t < threshold:
            return InterceptorResult(action=InterceptorAction.PASS)
        # bug #22 class: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + bonus
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        # bug #22 class: priority must be QUERY for queries.get_toughness to iterate it.
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_effect,
        duration="while_on_battlefield",
    )


def _make_global_toughness_lord_interceptor(obj: GameObject, bonus: int = 1) -> Interceptor:
    """Static: all other FIN_TRADER objects you control get +0/+bonus."""
    def toughness_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.QUERY_TOUGHNESS
            and event.payload.get("object_id") != obj.id
        )

    def toughness_effect(event: Event, state: GameState) -> InterceptorResult:
        target_id = event.payload.get("object_id")
        if not target_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(target_id)
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        if target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if CardType.FIN_TRADER not in target.characteristics.types:
            return InterceptorResult(action=InterceptorAction.PASS)
        # bug #22: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + bonus
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        # bug #22: priority must be QUERY for queries.get_toughness to iterate it.
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_effect,
        duration="while_on_battlefield",
    )


# =============================================================================
# STATIC TOUGHNESS LORD for Traders with Defense Rating 4+
# =============================================================================

def _make_defense4_lord_interceptor(obj: GameObject, bonus: int = 1) -> Interceptor:
    return _make_defense_lord_interceptor(obj, threshold=4, bonus=bonus)


# =============================================================================
# Arbitrage-aware draw helper (ETB draw if Arbitrage triggered)
# =============================================================================

def _make_arbitrage_draw_setup(n_arb: int, draw_count: int = 1):
    """ETB: gain N Liquidity if leading, then draw draw_count card(s) if Arbitrage triggered."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect_fn(event: Event, state: GameState) -> list[Event]:
            if _player_leads_traders_strict(state, obj.controller):
                _gain_liquidity(state, obj.controller, n_arb)
                return [Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "count": draw_count},
                    source=obj.id,
                )]
            return []

        return [make_etb_trigger(obj, effect_fn)]

    return setup


# =============================================================================
# TRADER CARDS (14)
# =============================================================================

# --- Statistical Arb Clerk {1} 1/2 — Arbitrage 1 ---
def _statistical_arb_clerk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return _make_arbitrage_setup(1)(obj, state)


STATISTICAL_ARB_CLERK = make_trader(
    name="Statistical Arb Clerk",
    cost="{1}",
    power=1,
    toughness=2,
    text="Arbitrage 1. (When this enters, if you control more Traders than your opponent, gain 1 Liquidity this turn.)",
    rarity="common",
    setup_interceptors=_statistical_arb_clerk_setup,
)


# --- Factor Model Analyst {2} 1/3 — Arbitrage 1. When Arbitrage triggers, draw a card. ---
def _factor_model_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        if _player_leads_traders_strict(state, obj.controller):
            _gain_liquidity(state, obj.controller, 1)
            return [Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1},
                source=obj.id,
            )]
        return []

    return [make_etb_trigger(obj, effect_fn)]


FACTOR_MODEL_ANALYST = make_trader(
    name="Factor Model Analyst",
    cost="{2}",
    power=1,
    # rebalance: toughness 3 → 2. FMA at 1/3 + Arb 1 effective 1/4 was
    # blocking 3-power attackers cleanly + drawing on ETB. 1/2 makes it
    # trade with 2-power attackers, dies to 3-power, still draws on ETB.
    toughness=2,
    text="Arbitrage 1. When Arbitrage triggers, draw a card.",
    rarity="common",
    setup_interceptors=_factor_model_analyst_setup,
)


# --- Risk Manager {2} 1/4 — Arbitrage 1. When this blocks, remove 1 damage from it after combat. ---
def _risk_manager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    arb_interceptor = _make_arbitrage_setup(1)(obj, state)[0]

    # Bug #9: previously this reacted on BLOCK_DECLARED and decremented
    # damage BEFORE combat damage was assigned — no-op against the lethal
    # check downstream. Re-implement as a TRANSFORM on combat DAMAGE: while
    # blocking, reduce incoming combat damage by 1. Net effect = "heal 1
    # after combat" because the lethal check sees damage_dealt - 1.
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get("target") != obj.id:
            return False
        if not event.payload.get("is_combat"):
            return False
        # Only reduce when this Trader is currently blocking.
        o = state.objects.get(obj.id)
        return bool(o and o.zone == ZoneType.BATTLEFIELD and o.state.blocking)

    def damage_effect(event: Event, state: GameState) -> InterceptorResult:
        amt = int(event.payload.get("amount", 0) or 0)
        new_amt = max(0, amt - 1)
        event.payload["amount"] = new_amt
        return InterceptorResult(action=InterceptorAction.TRANSFORM)

    arb_dmg_reduction = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=damage_filter,
        handler=damage_effect,
        duration="while_on_battlefield",
    )
    return [arb_interceptor, arb_dmg_reduction]


RISK_MANAGER = make_trader(
    name="Risk Manager",
    cost="{2}",
    power=1,
    toughness=4,
    text="Arbitrage 1. When this blocks, remove 1 damage from it after combat.",
    rarity="uncommon",
    setup_interceptors=_risk_manager_setup,
)


# --- Correlation Trader {3} 2/4 — Arbitrage 1. Static: other Traders with Defense Rating 3+ get +0/+1. ---
def _correlation_trader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    arb = _make_arbitrage_setup(1)(obj, state)[0]
    lord = _make_defense_lord_interceptor(obj, threshold=3, bonus=1)
    return [arb, lord]


CORRELATION_TRADER = make_trader(
    name="Correlation Trader",
    cost="{3}",
    power=2,
    toughness=4,
    text="Arbitrage 1. Static: your other Traders with Defense Rating 3 or greater get +0/+1.",
    rarity="uncommon",
    setup_interceptors=_correlation_trader_setup,
)


# --- Pairs Trader {3} 2/3 — Arbitrage 2. When this attacks, gain 4 Liquidity this turn. ---
def _pairs_trader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Bug #33: previously gained Liquidity on ETB via two _gain_liquidity calls
    # (Arb 2 + bonus 2). Card text says "when this attacks". Pilot A T9/T11
    # confirmed casting PT did not move Liquidity (full-cap masked the ETB
    # gain), then attacking PT also did nothing. Fix: rebuild as an
    # ATTACK_DECLARED REACT trigger filtered to obj.id, mirroring
    # _smart_beta_strategist_setup above. Effect: +4 Liquidity each time PT
    # attacks (Arb 2 baseline 2 + bonus 2 = 4 total per attack).
    def attack_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ATTACK_DECLARED
            and event.payload.get("attacker_id") == obj.id
        )

    def attack_effect(event: Event, state: GameState) -> InterceptorResult:
        # rebalance: +4 → +1 Liquidity on attack. The +4 was Smothering-Tithe
        # tier on a {3} 2/3 body — 4 of top 5 decks ran 4-of PT. Nerfing the
        # gain to +1 keeps PT a positive-tempo attacker (still gains mana,
        # still has Arb 2 = effective 2/5 on block) without making it a
        # ramp-engine on a creature. Smart Beta Strategist's +1 card on
        # attack is the peer benchmark.
        if _player_leads_traders_strict(state, obj.controller):
            _gain_liquidity(state, obj.controller, 1)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    attack_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_effect,
        duration="while_on_battlefield",
    )
    return [attack_interceptor]


PAIRS_TRADER = make_trader(
    name="Pairs Trader",
    cost="{3}",
    power=2,
    toughness=3,
    text="Arbitrage 2. When this attacks, if you lead in Traders, gain 1 Liquidity this turn.",
    rarity="uncommon",
    setup_interceptors=_pairs_trader_setup,
)


# --- Mean Reversion Bot {3} 1/4 — At the start of your Pre-Market, remove 1 damage from this Trader. ---
def _mean_reversion_bot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        o = state.objects.get(obj.id)
        if o and o.zone == ZoneType.BATTLEFIELD:
            o.state.damage = max(0, o.state.damage - 1)
        return []

    return [_make_pre_market_interceptor(obj, effect_fn)]


MEAN_REVERSION_BOT = make_trader(
    name="Mean Reversion Bot",
    cost="{3}",
    power=1,
    toughness=4,
    text="At the start of your Pre-Market, remove 1 damage from this Trader.",
    rarity="common",
    setup_interceptors=_mean_reversion_bot_setup,
)


# --- Factor Exposure Desk {4} 2/5 — Arbitrage 2. When this enters, if Arbitrage triggers, draw a card. ---
def _factor_exposure_desk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return _make_arbitrage_draw_setup(n_arb=2, draw_count=1)(obj, state)


FACTOR_EXPOSURE_DESK = make_trader(
    name="Factor Exposure Desk",
    cost="{4}",
    power=2,
    toughness=5,
    text="Arbitrage 2. When this enters, if Arbitrage triggers, draw a card.",
    rarity="uncommon",
    setup_interceptors=_factor_exposure_desk_setup,
)


# --- Smart Beta Strategist {4} 3/4 — Arbitrage 1. When this attacks, if your Capital Reserve is higher than opponent's, draw a card. ---
def _smart_beta_strategist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    arb = _make_arbitrage_setup(1)(obj, state)[0]

    def attack_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ATTACK_DECLARED
            and event.payload.get("attacker_id") == obj.id
        )

    def attack_effect(event: Event, state: GameState) -> InterceptorResult:
        my_player = state.players.get(obj.controller)
        if not my_player:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        for pid, p in state.players.items():
            if pid != obj.controller:
                if my_player.life > p.life:
                    return InterceptorResult(
                        action=InterceptorAction.REACT,
                        new_events=[Event(
                            type=EventType.DRAW,
                            payload={"player": obj.controller, "count": 1},
                            source=obj.id,
                        )],
                    )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    attack_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_effect,
        duration="while_on_battlefield",
    )
    return [arb, attack_interceptor]


SMART_BETA_STRATEGIST = make_trader(
    name="Smart Beta Strategist",
    cost="{4}",
    power=3,
    toughness=4,
    text="Arbitrage 1. When this attacks, if your Capital Reserve is higher than your opponent's, draw a card.",
    rarity="uncommon",
    setup_interceptors=_smart_beta_strategist_setup,
)


# --- Drawdown Controller {4} 2/5 — When this enters, remove all damage from one Trader you control. ---
def _drawdown_controller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Heal the controller's most-damaged Trader (greedy: most damage)
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        best = None
        best_dmg = -1
        for oid in bf.objects:
            o = state.objects.get(oid)
            if (o and o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.FIN_TRADER in o.characteristics.types and
                    o.state.damage > best_dmg):
                best = o
                best_dmg = o.state.damage
        if best:
            best.state.damage = 0
        return []

    return [make_etb_trigger(obj, effect_fn)]


DRAWDOWN_CONTROLLER = make_trader(
    name="Drawdown Controller",
    cost="{4}",
    power=2,
    toughness=5,
    text="When this enters, remove all damage from one Trader you control.",
    rarity="uncommon",
    setup_interceptors=_drawdown_controller_setup,
)


# --- Portfolio Construction Desk {4} 3/4 — Arbitrage 2. Your other Traders get +0/+1. ---
def _portfolio_construction_desk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    arb = _make_arbitrage_setup(2)(obj, state)[0]
    lord = _make_global_toughness_lord_interceptor(obj, bonus=1)
    return [arb, lord]


PORTFOLIO_CONSTRUCTION_DESK = make_trader(
    name="Portfolio Construction Desk",
    cost="{4}",
    power=3,
    toughness=4,
    text="Arbitrage 2. Your other Traders get +0/+1.",
    rarity="rare",
    setup_interceptors=_portfolio_construction_desk_setup,
)


# --- Systematic Rebalancer {5} 3/5 — Arbitrage 2. At the start of your Pre-Market, you may move 1 damage counter from one of your Traders to another. ---
def _systematic_rebalancer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    arb = _make_arbitrage_setup(2)(obj, state)[0]

    def pm_effect(event: Event, state: GameState) -> list[Event]:
        # Greedy auto-move: take 1 damage from most-damaged Trader,
        # put it on the least-damaged Trader (not the most-damaged itself).
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        my_traders = [
            state.objects.get(oid) for oid in bf.objects
            if (o := state.objects.get(oid)) and
            o.zone == ZoneType.BATTLEFIELD and
            o.controller == obj.controller and
            CardType.FIN_TRADER in o.characteristics.types
        ]
        my_traders = [t for t in my_traders if t is not None]
        if len(my_traders) < 2:
            return []
        most_dmg = max(my_traders, key=lambda t: t.state.damage)
        if most_dmg.state.damage == 0:
            return []
        least_dmg = min(
            [t for t in my_traders if t.id != most_dmg.id],
            key=lambda t: t.state.damage,
        )
        most_dmg.state.damage -= 1
        least_dmg.state.damage += 1
        return []

    pm_interceptor = _make_pre_market_interceptor(obj, pm_effect)
    return [arb, pm_interceptor]


SYSTEMATIC_REBALANCER = make_trader(
    name="Systematic Rebalancer",
    cost="{5}",
    power=3,
    toughness=5,
    text="Arbitrage 2. At the start of your Pre-Market, you may move 1 damage counter from one of your Traders to another.",
    rarity="rare",
    setup_interceptors=_systematic_rebalancer_setup,
)


# --- Cross-Sectional Alpha Machine {5} 4/5 — Arbitrage 3. When Arbitrage triggers, also gain 1 Liquidity for each Trader you control beyond the opponent count. ---
def _cross_sectional_alpha_machine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        my_count = _count_traders(state, obj.controller)
        max_opp = 0
        for pid in state.players:
            if pid != obj.controller:
                max_opp = max(max_opp, _count_traders(state, pid))
        leads = my_count > max_opp
        if leads:
            _gain_liquidity(state, obj.controller, 3)  # Arbitrage 3
            surplus = my_count - max_opp
            _gain_liquidity(state, obj.controller, surplus)
        return []

    return [make_etb_trigger(obj, effect_fn)]


CROSS_SECTIONAL_ALPHA_MACHINE = make_trader(
    name="Cross-Sectional Alpha Machine",
    cost="{6}",  # cyc3: {5}→{6} (Arb3 + bonus liq too efficient)
    power=4,
    toughness=5,
    text="Arbitrage 3. When Arbitrage triggers, also gain 1 Liquidity for each Trader you control beyond the opponent count.",
    rarity="rare",
    setup_interceptors=_cross_sectional_alpha_machine_setup,
)


# --- Machine Learning Optimizer {6} 4/6 — Arbitrage 3. When this enters, draw cards equal to your Arbitrage triggers this game (max 4). ---
def _machine_learning_optimizer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Arbitrage 3 fires first
        if _player_leads_traders_strict(state, obj.controller):
            _gain_liquidity(state, obj.controller, 3)
        # Draw equal to Arbitrage triggers this game; tracked in turn_data
        trigger_count = int(state.turn_data.get(f"fin_arb_triggers_{obj.controller}", 0))
        draw_count = min(4, trigger_count)
        if draw_count > 0:
            return [Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": draw_count},
                source=obj.id,
            )]
        return []

    return [make_etb_trigger(obj, effect_fn)]


MACHINE_LEARNING_OPTIMIZER = make_trader(
    name="Machine Learning Optimizer",
    cost="{7}",  # cyc3: {6}→{7} (Arb3 + mass draw too efficient)
    power=4,
    toughness=6,
    text="Arbitrage 3. When this enters, draw cards equal to your Arbitrage triggers this game (maximum 4).",
    rarity="rare",
    setup_interceptors=_machine_learning_optimizer_setup,
)


# --- Monopoly Position {7} 3/5 — Alternate win condition ---
def _monopoly_position_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB: place 5 Portfolio Value counters
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        o = state.objects.get(obj.id)
        if o:
            o.state.counters["portfolio_value"] = (
                o.state.counters.get("portfolio_value", 0) + 5
            )
        return []

    etb_interceptor = make_etb_trigger(obj, etb_effect)

    # Pre-Market: (1) each other Trader with Arbitrage adds 1 PV counter
    #             (2) if total >= 20, emit PLAYER_WINS
    def pm_effect(event: Event, state: GameState) -> list[Event]:
        o = state.objects.get(obj.id)
        if not o or o.zone != ZoneType.BATTLEFIELD:
            return []

        # Other Traders you control with Arbitrage add 1 PV counter each
        bf = state.zones.get("battlefield")
        if bf:
            for oid in bf.objects:
                t = state.objects.get(oid)
                if (t and t.id != obj.id and
                        t.zone == ZoneType.BATTLEFIELD and
                        t.controller == obj.controller and
                        CardType.FIN_TRADER in t.characteristics.types and
                        "arbitrage" in (t.characteristics.abilities or [])):
                    o.state.counters["portfolio_value"] = (
                        o.state.counters.get("portfolio_value", 0) + 1
                    )

        pv = o.state.counters.get("portfolio_value", 0)
        if pv >= 20:
            return [Event(
                type=EventType.PLAYER_WINS,
                payload={"player": obj.controller, "reason": "monopoly_position"},
                source=obj.id,
            )]
        return []

    pm_interceptor = _make_pre_market_interceptor(obj, pm_effect)
    return [etb_interceptor, pm_interceptor]


MONOPOLY_POSITION = make_trader(
    name="Monopoly Position",
    cost="{7}",
    power=3,
    toughness=5,
    text=(
        "Alternate win: at the start of your Pre-Market, if your Portfolio Value "
        "counter total is 20 or greater, you win the game. When this enters, place "
        "5 Portfolio Value counters on it. Each other Trader you control with "
        "Arbitrage places 1 Portfolio Value counter on this each Pre-Market."
    ),
    rarity="mythic",
    setup_interceptors=_monopoly_position_setup,
)


# =============================================================================
# ORDER CARDS (7)
# =============================================================================

# --- Information Ratio Enforcer {2} — Counter target Order or Strategy unless its controller pays {2}. ---
def _information_ratio_enforcer_resolve(event: Event, state: GameState) -> list[Event]:
    target_id = event.payload.get("target_id")
    if not target_id:
        return []
    fin_stack = getattr(state, "fin_stack", None)
    if fin_stack is None:
        return []
    target_item = fin_stack.find(target_id)
    if target_item is None:
        return []
    # "unless its controller pays {2}". V1 heuristic: controller pays
    # if they have ≥{2} Liquidity. V2 could ask via a sub-priority window.
    target_player = state.players.get(target_item.controller)
    if target_player and target_player.mana_crystals_available >= 2:
        target_player.mana_crystals_available -= 2
        return []
    fin_stack.mark_countered(target_id)
    return []


INFORMATION_RATIO_ENFORCER = make_order(
    name="Information Ratio Enforcer",
    cost="{2}",
    text="Counter target Order or Strategy unless its controller pays {2}.",
    rarity="uncommon",
    resolve=_information_ratio_enforcer_resolve,
)


# --- Rebalancing Halt {2} — Target Trader cannot attack this turn. Draw a card. ---
def _rebalancing_halt_resolve(event: Event, state: GameState) -> list[Event]:
    # Bug #17: previously TAP-only; targeted attacker remained in the combat
    # manager's declared-attackers list and damage still resolved. Now we
    # ALSO un-declare the attacker (clear it from the combat state and zero
    # any pending block assignment). Effect: works at instant speed during
    # the block window.
    target_id = event.payload.get("target_id")
    controller = event.payload.get("controller", "")
    events: list[Event] = []

    if target_id:
        target_obj = state.objects.get(target_id)
        # Clear the attacking flag so finance_combat skips it during damage
        # resolution AND remove it from the turn-state attackers_declared
        # list so the assertion-based fairness checks see an accurate set.
        if target_obj is not None:
            target_obj.state.attacking = False
        # Reach into the active turn manager (if any) to scrub the attacker
        # from the declared-attackers list and any pre-recorded block.
        tm = getattr(state, "turn_manager", None)
        if tm is None:
            game = getattr(state, "_game", None)
            tm = getattr(game, "turn_manager", None) if game is not None else None
        fin_state = getattr(tm, "fin_turn_state", None) if tm is not None else None
        if fin_state is not None:
            if hasattr(fin_state, "attackers_declared"):
                try:
                    fin_state.attackers_declared = [
                        aid for aid in fin_state.attackers_declared
                        if aid != target_id
                    ]
                except Exception:
                    pass
            if hasattr(fin_state, "combat_blocks"):
                try:
                    fin_state.combat_blocks = {
                        a: b for a, b in fin_state.combat_blocks.items()
                        if a != target_id
                    }
                except Exception:
                    pass
        # Tap the target Trader to prevent attack on subsequent declarations.
        events.append(Event(
            type=EventType.TAP,
            payload={"object_id": target_id},
            source=event.payload.get("source_id", ""),
        ))
    if controller:
        events.append(Event(
            type=EventType.DRAW,
            payload={"player": controller, "count": 1},
            source=event.payload.get("source_id", ""),
        ))
    return events


REBALANCING_HALT = make_order(
    name="Rebalancing Halt",
    cost="{2}",
    text="Target Trader cannot attack this turn. Draw a card.",
    rarity="common",
    resolve=_rebalancing_halt_resolve,
)


# --- Efficient Frontier {3} — Prevent all damage to target Trader you control until end of Trading Session. ---
def _efficient_frontier_resolve(event: Event, state: GameState) -> list[Event]:
    target_id = event.payload.get("target_id")
    if not target_id:
        return []
    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            "object_id": target_id,
            "effect": "damage_prevention",
            "duration": "end_of_turn",
        },
        source=event.payload.get("source_id", ""),
    )]


EFFICIENT_FRONTIER = make_order(
    name="Efficient Frontier",
    cost="{2}",  # rebalance: removal cost-cut {3} → {2} (prevent-damage trick should be cheap)
    text="Prevent all damage to target Trader you control until end of Trading Session.",
    rarity="uncommon",
    resolve=_efficient_frontier_resolve,
)


# --- Quant Signal {1} — Look at the top 3 cards of your Book. Put one into your hand, the rest on the bottom. ---
def _quant_signal_resolve(event: Event, state: GameState) -> list[Event]:
    # Bug #8: previously emitted a LOOK_AT_TOP event with no handler, so no
    # card ever landed in hand. Resolve inline: pop top of library into hand,
    # rotate the next two to the bottom (greedy first-card-keep heuristic).
    controller = event.payload.get("controller", "")
    if not controller:
        return []
    library = state.zones.get(f"library_{controller}")
    hand = state.zones.get(f"hand_{controller}")
    if library is None or hand is None or not library.objects:
        return []
    # Take top card → hand.
    top_id = library.objects.pop(0)
    hand.objects.append(top_id)
    obj = state.objects.get(top_id)
    if obj is not None:
        obj.zone = ZoneType.HAND
        obj.entered_zone_at = state.timestamp
    # Rotate next two to the bottom (if available).
    for _ in range(2):
        if not library.objects:
            break
        next_id = library.objects.pop(0)
        library.objects.append(next_id)
    return []


QUANT_SIGNAL = make_order(
    name="Quant Signal",
    cost="{1}",
    text="Look at the top 3 cards of your Book. Put one into your hand, the rest on the bottom.",
    rarity="common",
    resolve=_quant_signal_resolve,
)


# --- Sharpe Ratio Alert {2} — If your Capital Reserve is at least 5 more than your opponent's, draw 2 cards. ---
def _sharpe_ratio_alert_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller", "")
    if not controller:
        return []
    my_player = state.players.get(controller)
    if not my_player:
        return []
    for pid, p in state.players.items():
        if pid != controller:
            if my_player.life >= p.life + 5:
                return [Event(
                    type=EventType.DRAW,
                    payload={"player": controller, "count": 2},
                    source=event.payload.get("source_id", ""),
                )]
    return []


SHARPE_RATIO_ALERT = make_order(
    name="Sharpe Ratio Alert",
    cost="{2}",
    text="If your Capital Reserve is at least 5 more than your opponent's, draw 2 cards.",
    rarity="common",
    resolve=_sharpe_ratio_alert_resolve,
)


# --- Regime Change Detection {3} — Counter target Strategy. ---
def _regime_change_detection_resolve(event: Event, state: GameState) -> list[Event]:
    target_id = event.payload.get("target_id")
    if not target_id:
        return []
    fin_stack = getattr(state, "fin_stack", None)
    if fin_stack is None:
        return []
    target_item = fin_stack.find(target_id)
    if target_item is None:
        return []
    # "Counter target Strategy" — only fizzle if the target is a Strategy.
    target_obj = state.objects.get(target_id)
    if target_obj is None:
        return []
    from src.engine.types import CardType
    fin_strategy = getattr(CardType, "FIN_STRATEGY", None)
    if fin_strategy is None or fin_strategy not in target_obj.characteristics.types:
        return []
    fin_stack.mark_countered(target_id)
    return []


REGIME_CHANGE_DETECTION = make_order(
    name="Regime Change Detection",
    cost="{2}",  # rebalance: removal cost-cut {3} → {2} (counter-Strategy is narrower than counter-spell)
    text="Counter target Strategy.",
    rarity="uncommon",
    resolve=_regime_change_detection_resolve,
)


# --- Liquidity Provision {2} — Gain 3 Liquidity this turn. ---
def _liquidity_provision_resolve(event: Event, state: GameState) -> list[Event]:
    # rebalance: cost {2} → {1}, gain flat 3 → 50/50 of {2, 3}.
    # The flat-3 ritual at {2} was a guaranteed +1 net mana per cast.
    # New design: {1} cost (cheaper to slot), variance reward (EV +2.5 net,
    # so a {1} ritual averaging +1.5 mana). Adds skill expression — when
    # to chance the ritual matters. Mirrors MTG's variance rituals like
    # Wild Cantor / Manamorphose at {1} with a coin-flip payoff.
    import random
    controller = event.payload.get("controller", "")
    if not controller:
        return []
    rng = getattr(state, "_rng", None)
    if rng is None and getattr(state, "rng_seed", None) is not None:
        rng = random.Random(state.rng_seed)
        state._rng = rng
    if rng is None:
        rng = random
    amount = 3 if rng.random() < 0.5 else 2
    _gain_liquidity(state, controller, amount)
    return []


LIQUIDITY_PROVISION = make_order(
    name="Liquidity Provision",
    cost="{1}",
    text="Gain 2 or 3 Liquidity this turn (50/50). (Cannot exceed your Liquidity maximum.)",
    rarity="common",
    resolve=_liquidity_provision_resolve,
)


# =============================================================================
# STRATEGY CARDS (5)
# =============================================================================

# --- Risk-Adjusted Return {3} — Gain Liquidity equal to (your Traders - opponent's Traders), min 0, max 4. ---
def _risk_adjusted_return_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller", "")
    if not controller:
        return []
    my_count = _count_traders(state, controller)
    max_opp = max(
        (_count_traders(state, pid) for pid in state.players if pid != controller),
        default=0,
    )
    gain = max(0, min(4, my_count - max_opp))
    if gain > 0:
        _gain_liquidity(state, controller, gain)
    return []


RISK_ADJUSTED_RETURN = make_strategy(
    name="Risk-Adjusted Return",
    cost="{2}",  # rebalance: dead-card repair cost {3} → {2} (dominated by Liquidity Provision {2} flat +3)
    text="Gain Liquidity equal to the number of Traders you control beyond your opponent's count (minimum 0, maximum 4).",
    rarity="uncommon",
    resolve=_risk_adjusted_return_resolve,
)


# --- Correlation Matrix {4} — Draw cards equal to (your Traders - opponent's Traders), min 0, max 4. ---
def _correlation_matrix_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller", "")
    if not controller:
        return []
    my_count = _count_traders(state, controller)
    max_opp = max(
        (_count_traders(state, pid) for pid in state.players if pid != controller),
        default=0,
    )
    draw_count = max(0, min(4, my_count - max_opp))
    if draw_count > 0:
        return [Event(
            type=EventType.DRAW,
            payload={"player": controller, "count": draw_count},
            source=event.payload.get("source_id", ""),
        )]
    return []


CORRELATION_MATRIX = make_strategy(
    name="Correlation Matrix",
    cost="{4}",
    text="Draw cards equal to Traders you control minus opponent's Traders (minimum 0, maximum 4).",
    rarity="rare",
    resolve=_correlation_matrix_resolve,
)


# --- Information Advantage {3} — Draw 2 cards. If you control more Traders than your opponent, draw 3 instead. ---
def _information_advantage_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller", "")
    if not controller:
        return []
    leads = _player_leads_traders_strict(state, controller)
    draw_count = 3 if leads else 2
    return [Event(
        type=EventType.DRAW,
        payload={"player": controller, "count": draw_count},
        source=event.payload.get("source_id", ""),
    )]


INFORMATION_ADVANTAGE = make_strategy(
    name="Information Advantage",
    cost="{3}",
    text="Draw 2 cards. If you control more Traders than your opponent, draw 3 instead.",
    rarity="uncommon",
    resolve=_information_advantage_resolve,
)


# --- Factor Neutralization {5} — Destroy all Traders with Aggression greater than Defense Rating. ---
def _factor_neutralization_resolve(event: Event, state: GameState) -> list[Event]:
    events: list[Event] = []
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in list(bf.objects):
        o = state.objects.get(oid)
        if not o or o.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.FIN_TRADER not in o.characteristics.types:
            continue
        power = o.characteristics.power or 0
        toughness = o.characteristics.toughness or 0
        if power > toughness:
            events.append(Event(
                type=EventType.DESTROY,
                payload={"object_id": oid},
                source=event.payload.get("source_id", ""),
            ))
    return events


FACTOR_NEUTRALIZATION = make_strategy(
    name="Factor Neutralization",
    cost="{4}",  # rebalance: removal cost-cut {5} → {4} (conditional sweeper, MTG benchmark for sweepers is {3}-{4})
    text="Destroy all Traders with Aggression greater than Defense Rating.",
    rarity="rare",
    resolve=_factor_neutralization_resolve,
)


# --- Portfolio Stress Test {4} — Each player discards down to 3 cards. You draw 2 cards. ---
def _portfolio_stress_test_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller", "")
    events: list[Event] = []
    # Each player discards down to 3
    for pid in state.players:
        events.append(Event(
            type=EventType.DISCARD,
            payload={"player": pid, "down_to": 3},
            source=event.payload.get("source_id", ""),
        ))
    # Then controller draws 2
    if controller:
        events.append(Event(
            type=EventType.DRAW,
            payload={"player": controller, "count": 2},
            source=event.payload.get("source_id", ""),
        ))
    return events


PORTFOLIO_STRESS_TEST = make_strategy(
    name="Portfolio Stress Test",
    cost="{4}",
    text="Each player discards down to 3 cards. You draw 2 cards.",
    rarity="uncommon",
    resolve=_portfolio_stress_test_resolve,
)


# =============================================================================
# ASSET CARDS (6)
# =============================================================================

# --- Portfolio Diversifier {2} — Your Liquidity maximum is 1 higher than normal (max 11). ---
def _portfolio_diversifier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB: increment the player's Liquidity max by 1
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals = min(11, player.mana_crystals + 1)
        return []

    return [make_etb_trigger(obj, etb_effect)]


PORTFOLIO_DIVERSIFIER = make_asset(
    name="Portfolio Diversifier",
    cost="{2}",
    text="Your Liquidity maximum is 1 higher than normal (max 11).",
    rarity="uncommon",
    setup_interceptors=_portfolio_diversifier_setup,
)


# --- Sharpe Ratio Monitor {2} — At the start of your Pre-Market, if you control more Traders than your opponent, gain 1 Liquidity this turn. ---
def _sharpe_ratio_monitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def pm_effect(event: Event, state: GameState) -> list[Event]:
        if _player_leads_traders_strict(state, obj.controller):
            _gain_liquidity(state, obj.controller, 1)
        return []

    return [_make_pre_market_interceptor(obj, pm_effect)]


SHARPE_RATIO_MONITOR = make_asset(
    name="Sharpe Ratio Monitor",
    cost="{2}",
    text="At the start of your Pre-Market, if you control more Traders than your opponent, gain 1 Liquidity this turn.",
    rarity="common",
    setup_interceptors=_sharpe_ratio_monitor_setup,
)


# --- Backtesting Engine {3} — Activated: {2}, tap — look at top 5 of your Book; put one into your hand and the rest on the bottom. ---
def _backtesting_engine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # The activated ability is registered as a tap ability; effect handled via resolve
    # For now register the ETB marker; actual activation is handled by the turn manager.
    def activate_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ACTIVATE
            and event.payload.get("object_id") == obj.id
        )

    def activate_handler(event: Event, state: GameState) -> InterceptorResult:
        player = state.players.get(obj.controller)
        if not player:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        # rebalance: dead-card repair activation cost {2} → {1} (dominated by Quant Signal at {1})
        if player.mana_crystals_available < 1:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        player.mana_crystals_available -= 1
        o = state.objects.get(obj.id)
        if o:
            o.state.tapped = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LOOK_AT_TOP,
                payload={
                    "player": obj.controller,
                    "count": 5,
                    "put_to_hand": 1,
                    "put_to_bottom": 4,
                },
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=activate_filter,
        handler=activate_handler,
        duration="while_on_battlefield",
    )]


BACKTESTING_ENGINE = make_asset(
    name="Backtesting Engine",
    cost="{3}",
    text="Activated: {1}, tap — look at the top 5 cards of your Book; put one into your hand and the rest on the bottom.",
    rarity="uncommon",
    setup_interceptors=_backtesting_engine_setup,
)


# --- Systematic Alpha Engine {4} — At the start of your Pre-Market, if you control more Traders than your opponent, gain 2 Liquidity this turn. ---
def _systematic_alpha_engine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def pm_effect(event: Event, state: GameState) -> list[Event]:
        if _player_leads_traders_strict(state, obj.controller):
            _gain_liquidity(state, obj.controller, 2)
        return []

    return [_make_pre_market_interceptor(obj, pm_effect)]


SYSTEMATIC_ALPHA_ENGINE = make_asset(
    name="Systematic Alpha Engine",
    cost="{4}",
    text="At the start of your Pre-Market, if you control more Traders than your opponent, gain 2 Liquidity this turn.",
    rarity="rare",
    setup_interceptors=_systematic_alpha_engine_setup,
)


# --- Risk Attribution Model {3} — Static: your Traders with Defense Rating 4 or greater get +0/+1. ---
def _risk_attribution_model_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [_make_defense4_lord_interceptor(obj, bonus=1)]


RISK_ATTRIBUTION_MODEL = make_asset(
    name="Risk Attribution Model",
    cost="{2}",  # rebalance: lord normalization cost {3} → {2} (too narrow at ≥4-tough Traders)
    text="Static: your Traders with Defense Rating 4 or greater get +0/+1.",
    rarity="uncommon",
    setup_interceptors=_risk_attribution_model_setup,
)


# --- Live P&L Dashboard {4} — At the start of your Research phase, draw an additional card if you control more Traders than your opponent. ---
def _live_pl_dashboard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def r_effect(event: Event, state: GameState) -> list[Event]:
        if _player_leads_traders_strict(state, obj.controller):
            return [Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1},
                source=obj.id,
            )]
        return []

    return [_make_research_phase_interceptor(obj, r_effect)]


LIVE_PL_DASHBOARD = make_asset(
    name="Live P&L Dashboard",
    cost="{3}",  # rebalance: dead-card repair cost {4} → {3}
    text="At the start of your Research phase, draw an additional card if you control more Traders than your opponent.",
    rarity="rare",
    setup_interceptors=_live_pl_dashboard_setup,
)


# =============================================================================
# STRUCTURE CARDS (3)
# =============================================================================

# --- Quant Lab {3} — At the start of your Pre-Market, if you control more Traders than your opponent, gain 2 Liquidity this turn. ---
def _quant_lab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def pm_effect(event: Event, state: GameState) -> list[Event]:
        if _player_leads_traders_strict(state, obj.controller):
            _gain_liquidity(state, obj.controller, 2)
        return []

    return [_make_pre_market_interceptor(obj, pm_effect)]


QUANT_LAB = make_structure(
    name="Quant Lab",
    cost="{3}",
    text="At the start of your Pre-Market, if you control more Traders than your opponent, gain 2 Liquidity this turn.",
    rarity="rare",
    setup_interceptors=_quant_lab_setup,
)


# --- Research Server Farm {4} — At the start of your Research phase, draw an additional card if your Capital Reserve is 5+ above your opponent's. ---
# rebalance: dead-card repair lead threshold +10 → +5 (easier trigger)
def _research_server_farm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def r_effect(event: Event, state: GameState) -> list[Event]:
        my_player = state.players.get(obj.controller)
        if not my_player:
            return []
        for pid, p in state.players.items():
            if pid != obj.controller:
                if my_player.life >= p.life + 5:  # rebalance: +10 → +5
                    return [Event(
                        type=EventType.DRAW,
                        payload={"player": obj.controller, "count": 1},
                        source=obj.id,
                    )]
        return []

    return [_make_research_phase_interceptor(obj, r_effect)]


RESEARCH_SERVER_FARM = make_structure(
    name="Research Server Farm",
    cost="{4}",
    text="At the start of your Research phase, draw an additional card if your Capital Reserve is 5 or more above your opponent's.",
    rarity="rare",
    setup_interceptors=_research_server_farm_setup,
)


# --- Alpha Capture Platform {4} — At the start of your Trading Session, your Traders with Arbitrage get +1/+0 until Market Close. ---
def _alpha_capture_platform_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def ts_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        for oid in bf.objects:
            o = state.objects.get(oid)
            if (o and o.zone == ZoneType.BATTLEFIELD and
                    o.controller == obj.controller and
                    CardType.FIN_TRADER in o.characteristics.types):
                # Grant +1/+0 until end of turn via PT_MODIFICATION
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        "object_id": oid,
                        "power_mod": 1,
                        "toughness_mod": 0,
                        "duration": "end_of_turn",
                    },
                    source=obj.id,
                ))
        return events

    return [_make_trading_session_interceptor(obj, ts_effect)]


ALPHA_CAPTURE_PLATFORM = make_structure(
    name="Alpha Capture Platform",
    cost="{4}",
    text="At the start of your Trading Session, your Traders with Arbitrage get +1/+0 until Market Close.",
    rarity="rare",
    setup_interceptors=_alpha_capture_platform_setup,
)


# =============================================================================
# DERIVATIVE CARDS (2)
# =============================================================================

# --- Signal Processing Rig {2} — Attach to a Trader: it gains Arbitrage 1. When Arbitrage triggers, remove 1 damage from it. ---
def _signal_processing_rig_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # When this derivative is attached to a Trader, grant Arbitrage 1 effect.
    # We listen for ATTACH events targeting this derivative's host.
    def attach_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ATTACH
            and event.payload.get("attachment_id") == obj.id
        )

    def attach_handler(event: Event, state: GameState) -> InterceptorResult:
        host_id = event.payload.get("target_id") or event.payload.get("host_id")
        if not host_id:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

        # Register an ETB-like trigger on the host to provide Arbitrage 1 when host ETBs
        # For already-on-battlefield host: immediately register bonus
        # (simplified: the host gets Arbitrage check at next ETB-equivalent)
        # Also register a static interceptor: if host's controller leads Traders at
        # start of Pre-Market, remove 1 damage from host.
        host = state.objects.get(host_id)
        if host:
            host.state.counters["signal_rig_arbitrage"] = 1

        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    attach_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attach_filter,
        handler=attach_handler,
        duration="while_on_battlefield",
    )

    # Pre-market: if attached host's controller leads Traders, remove 1 damage from host
    def pm_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") in ("pre_market", "upkeep")
            and event.payload.get("player") == obj.controller
        )

    def pm_handler(event: Event, state: GameState) -> InterceptorResult:
        o = state.objects.get(obj.id)
        if not o:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        host_id = o.state.attached_to
        if not host_id:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        if _player_leads_traders_strict(state, obj.controller):
            # Arbitrage 1: gain 1 Liquidity
            _gain_liquidity(state, obj.controller, 1)
            # Remove 1 damage from host
            host = state.objects.get(host_id)
            if host:
                host.state.damage = max(0, host.state.damage - 1)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    pm_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=pm_filter,
        handler=pm_handler,
        duration="while_on_battlefield",
    )

    return [attach_interceptor, pm_interceptor]


SIGNAL_PROCESSING_RIG = make_derivative(
    name="Signal Processing Rig",
    cost="{2}",
    text="Attach to a Trader: it gains Arbitrage 1. When Arbitrage triggers, remove 1 damage from it.",
    rarity="uncommon",
    setup_interceptors=_signal_processing_rig_setup,
)


# --- Portfolio Insurance Wrap {3} — Attach to a Trader: when it would be destroyed, instead remove this Derivative and it survives with 1 Defense Rating remaining. ---
def _portfolio_insurance_wrap_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def destroy_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        destroyed_id = event.payload.get("object_id")
        if not destroyed_id:
            return False
        o = state.objects.get(obj.id)
        if not o:
            return False
        return o.state.attached_to == destroyed_id

    def destroy_handler(event: Event, state: GameState) -> InterceptorResult:
        destroyed_id = event.payload.get("object_id")
        if not destroyed_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        host = state.objects.get(destroyed_id)
        if not host:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Prevent the destruction
        host.state.damage = (host.characteristics.toughness or 1) - 1
        # "Remove this Derivative" — zone change to graveyard
        return InterceptorResult(
            action=InterceptorAction.PREVENT,
            new_events=[Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": obj.id,
                    "from_zone_type": ZoneType.BATTLEFIELD,
                    "to_zone_type": ZoneType.GRAVEYARD,
                },
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=destroy_filter,
        handler=destroy_handler,
        duration="while_on_battlefield",
    )]


PORTFOLIO_INSURANCE_WRAP = make_derivative(
    name="Portfolio Insurance Wrap",
    cost="{3}",
    text="Attach to a Trader: when this Trader would be destroyed, instead remove this Derivative and it survives with 1 Defense Rating remaining.",
    rarity="rare",
    setup_interceptors=_portfolio_insurance_wrap_setup,
)


# --- Black Monday {4} — Strategy: destroy all Traders. Wrath-of-God tier sweeper. ---
# Design: unconditional Trader board wipe. {4} matches MTG benchmark for
# unconditional sweepers (Wrath of God, Day of Judgment). Gives stax/control
# decks a real reset button against wide aggro AND voltron-style stacked
# threats. Symmetric — hits both players' Traders.
def _black_monday_resolve(event: Event, state: GameState) -> list[Event]:
    events: list[Event] = []
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in list(bf.objects):
        o = state.objects.get(oid)
        if not o or o.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.FIN_TRADER not in o.characteristics.types:
            continue
        events.append(Event(
            type=EventType.DESTROY,
            payload={"object_id": oid},
            source=event.payload.get("source_id", ""),
        ))
    return events


BLACK_MONDAY = make_strategy(
    name="Black Monday",
    cost="{4}",
    text="Destroy all Traders.",
    rarity="rare",
    resolve=_black_monday_resolve,
)


# =============================================================================
# SPICE PASS v1 — cost-cards skill pilot (2026-05-09)
# =============================================================================
# Three QT cards priced via cost-cards heuristics. QT closes at 33.3% WR per
# polish punchlist — spice extends Arbitrage scaling and selection consistency
# (pattern 7 tutoring, pattern 4 compression).

# --- Smart Beta Compounder {4} 3/4 Arbitrage 2 (Mythic) ---
# Patterns: 11 (build-around — Trader tribal), 3 (snowball).
# Heuristic walk:
#   vanilla 3/4 = {3} (HS curve, P+T=7)
#   Arbitrage 2 = +0.6 (×0.6 lead-condition discount)
#   ETB +1/+1 per other Trader (avg 2-3 ally Traders) = +1.5
#   total {5.1} → push to {4} as build-around mythic (×0.6 build-around
#   discount: depends on a wide Quant board to be on-curve).
def _smart_beta_compounder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    arb_setup = _make_arbitrage_setup(2)
    base_interceptors = arb_setup(obj, state)

    def etb_count_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        other_count = 0
        for oid in list(getattr(bf, "objects", [])):
            if oid == obj.id:
                continue
            o = state.objects.get(oid)
            if (o is not None
                    and o.controller == obj.controller
                    and CardType.FIN_TRADER in o.characteristics.types):
                other_count += 1
        if other_count <= 0:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                "object_id": obj.id,
                "counter_type": "+1/+1",
                "amount": other_count,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return base_interceptors + [make_etb_trigger(obj, etb_count_fn)]


SMART_BETA_COMPOUNDER = make_trader(
    "Smart Beta Compounder",
    "{4}",
    3, 4,
    "Arbitrage 2. When this enters, place a +1/+1 counter on it for each "
    "other Trader you control.",
    rarity="mythic",
    setup_interceptors=_smart_beta_compounder_setup,
)


# --- Monte Carlo Simulator {3} Asset (Rare) ---
# Patterns: 7 (consistency), 11 (build-around — leads-board condition).
# Heuristic walk:
#   Asset baseline = 0
#   recurring conditional pre-market scry-1-to-hand (×0.6 lead-condition,
#     ~5 fires per game) = +2.5
#   total {2.5} → fair {3} (round up: card slot + multi-turn engine).
def _monte_carlo_simulator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def pm_effect(event: Event, state: GameState) -> list[Event]:
        if not _player_leads_traders_strict(state, obj.controller):
            return []
        library = state.zones.get(f"library_{obj.controller}")
        hand = state.zones.get(f"hand_{obj.controller}")
        if library is None or hand is None or not library.objects:
            return []
        top_id = library.objects.pop(0)
        hand.objects.append(top_id)
        top_obj = state.objects.get(top_id)
        if top_obj is not None:
            top_obj.zone = ZoneType.HAND
            top_obj.entered_zone_at = state.timestamp
        return []

    return [_make_pre_market_interceptor(obj, pm_effect)]


MONTE_CARLO_SIMULATOR = make_asset(
    "Monte Carlo Simulator",
    "{3}",
    "At the start of your Pre-Market, if you control more Traders than your "
    "opponent, look at the top card of your Book and put it into your hand.",
    rarity="rare",
    setup_interceptors=_monte_carlo_simulator_setup,
)


# --- Pricing Model Oracle {3} 2/3 Arbitrage 1 (Rare) ---
# Patterns: 7 (consistency), 4 (compression — body + selection).
# Heuristic walk:
#   vanilla 2/3 = {2} (HS curve, P+T=5)
#   Arbitrage 1 = +0.3
#   ETB conditional reveal-and-keep-if-Order-or-Strategy (~50% hit-rate
#     in QT/HF mixed deck × 1 mana of value) = +0.5
#   total {2.8} → fair {3}.
def _pricing_model_oracle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    arb_setup = _make_arbitrage_setup(1)
    base_interceptors = arb_setup(obj, state)

    def etb_reveal_fn(event: Event, state: GameState) -> list[Event]:
        library = state.zones.get(f"library_{obj.controller}")
        hand = state.zones.get(f"hand_{obj.controller}")
        if library is None or hand is None or not library.objects:
            return []
        top_id = library.objects[0]
        top_obj = state.objects.get(top_id)
        if top_obj is None:
            return []
        keep_types = {CardType.FIN_ORDER, CardType.FIN_STRATEGY}
        if top_obj.characteristics.types & keep_types:
            library.objects.pop(0)
            hand.objects.append(top_id)
            top_obj.zone = ZoneType.HAND
            top_obj.entered_zone_at = state.timestamp
        return []

    return base_interceptors + [make_etb_trigger(obj, etb_reveal_fn)]


PRICING_MODEL_ORACLE = make_trader(
    "Pricing Model Oracle",
    "{3}",
    2, 3,
    "Arbitrage 1. When this enters, reveal the top card of your Book. If it "
    "is an Order or Strategy, put it into your hand.",
    rarity="rare",
    setup_interceptors=_pricing_model_oracle_setup,
)


# =============================================================================
# EXPORT
# =============================================================================

QUANT_CARDS: dict[str, CardDefinition] = {
    # Traders (14)
    "Statistical Arb Clerk": STATISTICAL_ARB_CLERK,
    "Factor Model Analyst": FACTOR_MODEL_ANALYST,
    "Risk Manager": RISK_MANAGER,
    "Correlation Trader": CORRELATION_TRADER,
    "Pairs Trader": PAIRS_TRADER,
    "Mean Reversion Bot": MEAN_REVERSION_BOT,
    "Factor Exposure Desk": FACTOR_EXPOSURE_DESK,
    "Smart Beta Strategist": SMART_BETA_STRATEGIST,
    "Drawdown Controller": DRAWDOWN_CONTROLLER,
    "Portfolio Construction Desk": PORTFOLIO_CONSTRUCTION_DESK,
    "Systematic Rebalancer": SYSTEMATIC_REBALANCER,
    "Cross-Sectional Alpha Machine": CROSS_SECTIONAL_ALPHA_MACHINE,
    "Machine Learning Optimizer": MACHINE_LEARNING_OPTIMIZER,
    "Monopoly Position": MONOPOLY_POSITION,
    # Orders (7)
    "Information Ratio Enforcer": INFORMATION_RATIO_ENFORCER,
    "Rebalancing Halt": REBALANCING_HALT,
    "Efficient Frontier": EFFICIENT_FRONTIER,
    "Quant Signal": QUANT_SIGNAL,
    "Sharpe Ratio Alert": SHARPE_RATIO_ALERT,
    "Regime Change Detection": REGIME_CHANGE_DETECTION,
    "Liquidity Provision": LIQUIDITY_PROVISION,
    # Strategies (5)
    "Risk-Adjusted Return": RISK_ADJUSTED_RETURN,
    "Correlation Matrix": CORRELATION_MATRIX,
    "Information Advantage": INFORMATION_ADVANTAGE,
    "Factor Neutralization": FACTOR_NEUTRALIZATION,
    "Portfolio Stress Test": PORTFOLIO_STRESS_TEST,
    # Assets (6)
    "Portfolio Diversifier": PORTFOLIO_DIVERSIFIER,
    "Sharpe Ratio Monitor": SHARPE_RATIO_MONITOR,
    "Backtesting Engine": BACKTESTING_ENGINE,
    "Systematic Alpha Engine": SYSTEMATIC_ALPHA_ENGINE,
    "Risk Attribution Model": RISK_ATTRIBUTION_MODEL,
    "Live P&L Dashboard": LIVE_PL_DASHBOARD,
    # Structures (3)
    "Quant Lab": QUANT_LAB,
    "Research Server Farm": RESEARCH_SERVER_FARM,
    "Alpha Capture Platform": ALPHA_CAPTURE_PLATFORM,
    # Derivatives (2)
    "Signal Processing Rig": SIGNAL_PROCESSING_RIG,
    "Portfolio Insurance Wrap": PORTFOLIO_INSURANCE_WRAP,
    "Black Monday": BLACK_MONDAY,
    # Spice pass v1 (cost-cards skill pilot, 2026-05-09): +3 cards
    "Smart Beta Compounder": SMART_BETA_COMPOUNDER,
    "Monte Carlo Simulator": MONTE_CARLO_SIMULATOR,
    "Pricing Model Oracle": PRICING_MODEL_ORACLE,
}
