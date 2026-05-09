"""FINA — DERIVATIVES archetype cards (37 total).

Archetype strategy: Stack Leverage counters on powerful Traders; use Short
Selling to reset and double +1/+1 counters. Derivatives Desk accelerates tempo.
Win mid-game when opponents can't trade favorably into a Leverage-pumped Trader.

Key mechanics implemented here:
  - LEVERAGE N: ETB adds N counters; QUERY_POWER boost; global drain handled by
    finance.py's _register_leverage_tick system interceptor.
  - SHORT SELLING: exile half via ZONE_CHANGE; return marker stored in turn_data
    (reconcile: finance_turn.py must honour "short_sell_return_*" in pre_market).
  - Derivative attachment: objects stage on Derivatives Desk (finance.py system
    interceptor); QUERY_POWER/QUERY_TOUGHNESS boost references obj.state.attached_to.
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
    new_id,
)
from src.cards.interceptor_helpers import (
    make_etb_trigger,
    make_attack_trigger,
    make_activated_ability,
)


# =============================================================================
# Card factory functions
# =============================================================================

def make_trader(
    name: str,
    cost: str,
    power: int,
    toughness: int,
    *,
    subtypes: set[str] | None = None,
    text: str = "",
    setup_interceptors=None,
    domain: str = "FINA",
    rarity: str | None = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_TRADER},
        subtypes=subtypes or set(),
        mana_cost=cost,
        power=power,
        toughness=toughness,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        text=text,
        domain=domain,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


def make_order(
    name: str,
    cost: str,
    *,
    text: str = "",
    resolve=None,
    setup_interceptors=None,
    dark_pool: bool = False,
    domain: str = "FINA",
    rarity: str | None = None,
) -> CardDefinition:
    subtypes: set[str] = {"Dark Pool Order"} if dark_pool else {"Market Order"}
    chars = Characteristics(
        types={CardType.FIN_ORDER},
        subtypes=subtypes,
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        text=text,
        domain=domain,
        rarity=rarity,
        resolve=resolve,
        setup_interceptors=setup_interceptors,
    )


def make_strategy(
    name: str,
    cost: str,
    *,
    text: str = "",
    resolve=None,
    domain: str = "FINA",
    rarity: str | None = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_STRATEGY},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        text=text,
        domain=domain,
        rarity=rarity,
        resolve=resolve,
    )


def make_asset(
    name: str,
    cost: str,
    *,
    text: str = "",
    setup_interceptors=None,
    domain: str = "FINA",
    rarity: str | None = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_ASSET},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        text=text,
        domain=domain,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


def make_structure(
    name: str,
    cost: str,
    *,
    text: str = "",
    setup_interceptors=None,
    domain: str = "FINA",
    rarity: str | None = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_STRUCTURE},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        text=text,
        domain=domain,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


def make_derivative(
    name: str,
    cost: str,
    *,
    text: str = "",
    setup_interceptors=None,
    domain: str = "FINA",
    rarity: str | None = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_DERIVATIVE},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        text=text,
        domain=domain,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


# =============================================================================
# Leverage helper — shared by all Traders with Leverage N
# =============================================================================

def _make_leverage_setup(n: int):
    """Return a setup_interceptors function that gives a Trader Leverage N.

    Registers:
    1. ETB trigger that places N Leverage counters via a single COUNTER_ADDED
       event. Pipeline's _handle_counter_added writes the counters; we do NOT
       direct-set as a fallback because that double-stacks (bug #14).
    2. QUERY_POWER interceptor granting +1/+0 per leverage counter.
    """
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        # ------------------------------------------------------------------
        # ETB: add N leverage counters (single event, pipeline applies amount)
        # bug #14: previously emitted N events AND direct-set, doubling counters
        # ------------------------------------------------------------------
        def etb_effect(event: Event, state: GameState) -> list[Event]:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    "object_id": obj.id,
                    "counter_type": "leverage",
                    "amount": n,
                },
                source=obj.id,
                controller=obj.controller,
            )]

        etb_interceptor = make_etb_trigger(obj, etb_effect)

        # ------------------------------------------------------------------
        # QUERY_POWER: grant +1/+0 per leverage counter (continuous)
        # bug #19 fellow: must return TRANSFORM with payload['value'] updated;
        # get_power reads result.transformed_event.payload['value'].
        # ------------------------------------------------------------------
        def power_filter(event: Event, state: GameState) -> bool:
            return (
                event.type == EventType.QUERY_POWER
                and event.payload.get("object_id") == obj.id
            )

        def power_effect(event: Event, state: GameState) -> InterceptorResult:
            current = state.objects.get(obj.id)
            lev = 0
            if current:
                lev = int(current.state.counters.get("leverage", 0) or 0)
            if lev <= 0:
                return InterceptorResult(action=InterceptorAction.PASS)
            new_event = event.copy()
            new_event.payload["value"] = new_event.payload.get("value", 0) + lev
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event,
            )

        power_interceptor = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_effect,
            duration="while_on_battlefield",
        )

        return [etb_interceptor, power_interceptor]

    return setup


# =============================================================================
# Short Selling helper
# =============================================================================

def _short_sell_resolve(event: Event, state: GameState) -> list[Event]:
    """Strategy resolve for Short Squeeze — exile target Trader you control.

    Stores a marker in state.turn_data so the FinanceTurnManager can return
    the Trader at the start of the next Pre-Market with two +1/+1 counters.

    RECONCILE TODO: finance_turn.py must check
      state.turn_data["short_sell_return_{obj_id}"] = True
    during the PRE_MARKET phase and emit:
      ZONE_CHANGE(to_zone=BATTLEFIELD) + two COUNTER_ADDED(+1/+1) events.
    """
    events: list[Event] = []
    targets = event.payload.get("targets", [[]])
    target_id: str | None = None
    if targets and targets[0]:
        target_id = targets[0][0]
    if not target_id:
        return []

    # Exile the Trader
    events.append(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": target_id,
            "from_zone": "battlefield",
            "to_zone": "exile",
            "reason": "short_sell",
        },
        source=event.source,
        controller=event.controller,
    ))

    # Store return marker — turn manager handles the return next Pre-Market
    state.turn_data[f"short_sell_return_{target_id}"] = True

    return events


# =============================================================================
# TRADERS (15 cards)
# =============================================================================

# 1. Options Desk Intern {1} 1/2
# "When this enters, you may attach a Derivative from your Derivatives Desk
#  to it for free."
def _options_desk_intern_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Attempt to attach the first Derivative from this player's Derivatives Desk
        from src.engine.finance import get_deriv_desk, remove_from_deriv_desk
        desk = get_deriv_desk(state, obj.controller)
        if not desk:
            return []
        deriv_id = desk[0]
        remove_from_deriv_desk(state, obj.controller, deriv_id)
        deriv_obj = state.objects.get(deriv_id)
        if deriv_obj:
            deriv_obj.state.attached_to = obj.id
        return []

    return [make_etb_trigger(obj, etb_effect)]


OPTIONS_DESK_INTERN = make_trader(
    "Options Desk Intern",
    "{1}",
    2, 2,  # balanced: power 1 → 2 (FIN_TRADER buff, power ≤ 3)
    text="When this enters, you may attach a Derivative from your Derivatives Desk to it for free.",
    setup_interceptors=_options_desk_intern_setup,
    rarity="common",
)

# 2. Underlying Asset Runner {2} 3/2 — Leverage 1
UNDERLYING_ASSET_RUNNER = make_trader(
    "Underlying Asset Runner",
    "{2}",
    3, 3,  # cyc3: toughness 2→3 (too frail for 2-drop)
    text="Leverage 1.",
    setup_interceptors=_make_leverage_setup(1),
    rarity="common",
)

# 3. Delta Hedger {3} 2/4 — Leverage 2. Damage reduction.
def _delta_hedger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(2)(obj, state)

    # TRANSFORM on DAMAGE targeting this Trader: reduce by 1 (min 0)
    def dmg_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.DAMAGE
            and event.payload.get("target") == obj.id
        )

    def dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        amt = event.payload.get("amount", 0)
        event.payload["amount"] = max(0, amt - 1)
        return InterceptorResult(action=InterceptorAction.PASS)

    damage_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=dmg_filter,
        handler=dmg_handler,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [damage_interceptor]


DELTA_HEDGER = make_trader(
    "Delta Hedger",
    "{3}",
    3, 4,  # balanced: power 2 → 3 (FIN_TRADER buff, power ≤ 3)
    text="Leverage 2. When damage is dealt to this Trader, reduce it by 1 (minimum 0).",
    setup_interceptors=_delta_hedger_setup,
    rarity="uncommon",
)

# 4. Rho Opportunist {3} 3/2 — Leverage 1. Draw a card when counter added.
def _rho_opportunist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(1)(obj, state)

    # REACT on COUNTER_ADDED targeting this Trader with "leverage" counter
    def counter_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.COUNTER_ADDED
            and event.payload.get("object_id") == obj.id
            and event.payload.get("counter_type") == "leverage"
        )

    def counter_effect(event: Event, state: GameState) -> InterceptorResult:
        draw = Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "amount": 1},
            source=obj.id,
            controller=obj.controller,
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[draw])

    counter_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=counter_filter,
        handler=counter_effect,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [counter_interceptor]


RHO_OPPORTUNIST = make_trader(
    "Rho Opportunist",
    "{3}",
    4, 3,  # cyc3: toughness 2→3 (4/2 for 3 died to everything)
    text="Leverage 1. When a Leverage counter is added to this, draw a card.",
    setup_interceptors=_rho_opportunist_setup,
    rarity="uncommon",
)

# 5. Theta Decay Trader {3} 2/3 — Leverage 2. Pre-Market: remove 1 Leverage
#    counter for free.
def _theta_decay_trader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(2)(obj, state)

    # REACT on PHASE_START(pre_market) for this controller
    def pre_market_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "pre_market"
            and event.payload.get("player") == obj.controller
        )

    def pre_market_effect(event: Event, state: GameState) -> InterceptorResult:
        current = state.objects.get(obj.id)
        if current and current.state.counters.get("leverage", 0) > 0:
            current.state.counters["leverage"] -= 1
            remove_event = Event(
                type=EventType.COUNTER_REMOVED,
                payload={
                    "object_id": obj.id,
                    "counter_type": "leverage",
                    "amount": 1,
                    "reason": "theta_decay_free",
                },
                source=obj.id,
                controller=obj.controller,
            )
            return InterceptorResult(
                action=InterceptorAction.REACT, new_events=[remove_event]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    pre_market_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=pre_market_filter,
        handler=pre_market_effect,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [pre_market_interceptor]


THETA_DECAY_TRADER = make_trader(
    "Theta Decay Trader",
    "{3}",
    3, 3,  # balanced: power 2 → 3 (FIN_TRADER buff, power ≤ 3)
    text="Leverage 2. At the start of your Pre-Market, remove 1 Leverage counter from this (does not cost Capital Reserve).",
    setup_interceptors=_theta_decay_trader_setup,
    rarity="uncommon",
)

# 6. Gamma Scalper {4} 3/3 — Leverage 3. Once per game: if Market Close drain
#    would reduce Capital Reserve to 0, remove all Leverage counters instead.
def _gamma_scalper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(3)(obj, state)

    # TRANSFORM on FIN_LEVERAGE_TICK for this object: if player's life would
    # drop to <=0, remove all counters instead and suppress the LIFE_CHANGE.
    used_key = f"gamma_scalper_once_{obj.id}"

    def tick_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.FIN_LEVERAGE_TICK
            and event.payload.get("object_id") == obj.id
        )

    def tick_handler(event: Event, state: GameState) -> InterceptorResult:
        if state.turn_data.get(used_key):
            return InterceptorResult(action=InterceptorAction.PASS)

        controller = obj.controller
        player = state.players.get(controller)
        if not player:
            return InterceptorResult(action=InterceptorAction.PASS)

        current = state.objects.get(obj.id)
        if not current:
            return InterceptorResult(action=InterceptorAction.PASS)

        lev = int(current.state.counters.get("leverage", 0) or 0)
        if player.life - lev <= 0:
            # Once-per-game: remove all counters instead of draining
            state.turn_data[used_key] = True
            current.state.counters["leverage"] = 0
            # Suppress the leverage drain by preventing the tick event
            return InterceptorResult(action=InterceptorAction.PREVENT)

        return InterceptorResult(action=InterceptorAction.PASS)

    tick_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=tick_filter,
        handler=tick_handler,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [tick_interceptor]


GAMMA_SCALPER = make_trader(
    "Gamma Scalper",
    "{4}",
    3, 3,
    text="Leverage 3. Once per game, if the Market Close drain would reduce your Capital Reserve to 0, remove all Leverage counters instead.",
    setup_interceptors=_gamma_scalper_setup,
    rarity="rare",
)

# 7. Convexity Rider {4} 2/5 — Leverage 2. When Short Sold, return with 3
#    +1/+1 counters instead of 2.
def _convexity_rider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(2)(obj, state)

    # TRANSFORM on ZONE_CHANGE to EXILE with reason "short_sell" for this obj:
    # override the return counter marker to give 3 counters instead of 2.
    def exile_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get("object_id") == obj.id
            and event.payload.get("to_zone") == "exile"
            and event.payload.get("reason") == "short_sell"
        )

    def exile_handler(event: Event, state: GameState) -> InterceptorResult:
        # Override: store 3-counter marker instead of default 2
        state.turn_data[f"short_sell_bonus_counters_{obj.id}"] = 3
        return InterceptorResult(action=InterceptorAction.PASS)

    exile_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=exile_filter,
        handler=exile_handler,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [exile_interceptor]


CONVEXITY_RIDER = make_trader(
    "Convexity Rider",
    "{4}",
    3, 5,  # balanced: power 2 → 3 (FIN_TRADER buff, power ≤ 3)
    text="Leverage 2. When this is Short Sold, return with 3 +1/+1 counters instead of 2.",
    setup_interceptors=_convexity_rider_setup,
    rarity="rare",
)

# 8. Vega Amplifier {4} 4/3 — Leverage 3. ETB: other Leverage Traders get
#    +1/+0 until Market Close.
def _vega_amplifier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(3)(obj, state)

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return []
        for oid in list(battlefield.objects):
            if oid == obj.id:
                continue
            target = state.objects.get(oid)
            if not target:
                continue
            if target.controller != obj.controller:
                continue
            if CardType.FIN_TRADER not in target.characteristics.types:
                continue
            if target.state.counters.get("leverage", 0) <= 0:
                continue
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": oid,
                    "power_mod": 1,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return leverage_interceptors + [make_etb_trigger(obj, etb_effect)]


VEGA_AMPLIFIER = make_trader(
    "Vega Amplifier",
    "{4}",
    4, 3,
    text="Leverage 3. When this enters, each other Trader you control with Leverage gets +1/+0 until Market Close.",
    setup_interceptors=_vega_amplifier_setup,
    rarity="rare",
)

# 9. Structured Product Builder {4} 3/4 — Leverage 2. Derivatives attached to
#    this cost {1} less to play.
def _structured_product_builder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(2)(obj, state)

    # QUERY on QUERY_COST for FIN_DERIVATIVE cards being played by controller.
    # RECONCILE TODO: The cost reduction targeting "attached to this" requires the
    # turn manager to know the intended host. For now, apply reduction globally
    # to all FIN_DERIVATIVE plays by this controller while this Trader is in play.
    def cost_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_COST:
            return False
        # cost_query synthetic event exposes 'player_id' and 'card' (the casting card).
        if event.payload.get("player_id") != obj.controller:
            return False
        card = event.payload.get("card")
        if card is None:
            return False
        return CardType.FIN_DERIVATIVE in card.characteristics.types

    def cost_handler(event: Event, state: GameState) -> InterceptorResult:
        # priority class: cost_query reads transformed_event.payload['reduction'].
        new_event = event.copy()
        new_event.payload["reduction"] = new_event.payload.get("reduction", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    cost_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        # priority class: must be QUERY for cost_query.get_effective_mana_cost to iterate it.
        priority=InterceptorPriority.QUERY,
        filter=cost_filter,
        handler=cost_handler,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [cost_interceptor]


STRUCTURED_PRODUCT_BUILDER = make_trader(
    "Structured Product Builder",
    "{4}",
    4, 4,  # balanced: power 3 → 4 (FIN_TRADER buff, power ≤ 3)
    text="Leverage 2. Derivatives attached to this cost {1} less to play.",
    setup_interceptors=_structured_product_builder_setup,
    rarity="uncommon",
)

# 10. Hedge Fund PM {5} 4/4 — Leverage 2. ETB: attach all Derivatives from
#     Derivatives Desk to this Trader.
def _hedge_fund_pm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(2)(obj, state)

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        from src.engine.finance import get_deriv_desk, remove_from_deriv_desk
        desk = get_deriv_desk(state, obj.controller)
        for deriv_id in list(desk):
            remove_from_deriv_desk(state, obj.controller, deriv_id)
            deriv_obj = state.objects.get(deriv_id)
            if deriv_obj:
                deriv_obj.state.attached_to = obj.id
        return []

    return leverage_interceptors + [make_etb_trigger(obj, etb_effect)]


HEDGE_FUND_PM = make_trader(
    "Hedge Fund PM",
    "{4}",  # balanced: cost {5} → {4} (5+ cost reduction buff)
    4, 4,
    text="Leverage 2. When this enters, attach all Derivatives from your Derivatives Desk to this Trader.",
    setup_interceptors=_hedge_fund_pm_setup,
    rarity="rare",
)

# 11. Synthetic Long {5} 5/4 — Leverage 3. At Market Close, may pay 2 CR per
#     counter instead of 1 to keep all; if so, get +1/+0 permanently.
def _synthetic_long_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(3)(obj, state)

    # RECONCILE TODO: The "may pay 2 instead of 1 to keep counters and get
    # permanent +1/+0" requires player choice at Market Close. The global
    # leverage tick handles standard drain. For now, register the power
    # boost query modifier and track permanent +1/+0 stacks in turn_data.
    boost_key = f"synthetic_long_boost_{obj.id}"

    def power_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.QUERY_POWER
            and event.payload.get("object_id") == obj.id
        )

    def power_effect(event: Event, state: GameState) -> InterceptorResult:
        bonus = int(state.turn_data.get(boost_key, 0))
        if bonus <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        # priority class: queries.get_power reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + bonus
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    boost_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_effect,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [boost_interceptor]


SYNTHETIC_LONG = make_trader(
    "Synthetic Long",
    "{4}",  # balanced: cost {5} → {4} (5+ cost reduction buff)
    5, 4,
    text="Leverage 3. At Market Close, you may pay 2 Capital Reserve per counter instead of 1 to keep all Leverage counters; if you do, this gets +1/+0 permanently.",
    setup_interceptors=_synthetic_long_setup,
    rarity="rare",
)

# 12. Risk-Parity Quant {3} 2/3 — When a +1/+1 counter is placed on this,
#     place an additional +1/+1 counter on it.
def _risk_parity_quant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # REACT on COUNTER_ADDED targeting this Trader with "+1/+1" counter
    def counter_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.COUNTER_ADDED
            and event.payload.get("object_id") == obj.id
            and event.payload.get("counter_type") in ("+1/+1", "plus_one")
        )

    def counter_effect(event: Event, state: GameState) -> InterceptorResult:
        extra = Event(
            type=EventType.COUNTER_ADDED,
            payload={
                "object_id": obj.id,
                "counter_type": "+1/+1",
                "amount": 1,
            },
            source=obj.id,
            controller=obj.controller,
        )
        # Also apply stat change directly
        current = state.objects.get(obj.id)
        if current:
            current.characteristics.power = (current.characteristics.power or 0) + 1
            current.characteristics.toughness = (current.characteristics.toughness or 0) + 1
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[extra])

    counter_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=counter_filter,
        handler=counter_effect,
        duration="while_on_battlefield",
    )

    return [counter_interceptor]


RISK_PARITY_QUANT = make_trader(
    "Risk-Parity Quant",
    "{3}",
    3, 3,  # balanced: power 2 → 3 (FIN_TRADER buff, power ≤ 3)
    text="When a +1/+1 counter is placed on this, place an additional +1/+1 counter on it.",
    setup_interceptors=_risk_parity_quant_setup,
    rarity="uncommon",
)

# 13. Leveraged Buyout Specialist {6} 5/5 — Leverage 4. ETB: gain Liquidity
#     equal to its Leverage count this turn.
def _lbo_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(4)(obj, state)

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        current = state.objects.get(obj.id)
        lev = 4  # Leverage count at ETB time
        if current:
            lev = int(current.state.counters.get("leverage", 4))
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals, player.mana_crystals_available + lev
            )
        return []

    return leverage_interceptors + [make_etb_trigger(obj, etb_effect)]


LEVERAGED_BUYOUT_SPECIALIST = make_trader(
    "Leveraged Buyout Specialist",
    "{5}",  # balanced: cost {6} → {5} (5+ cost reduction buff)
    5, 5,
    text="Leverage 4. When this enters, gain Liquidity equal to its Leverage count this turn.",
    setup_interceptors=_lbo_specialist_setup,
    rarity="rare",
)

# 14. Exposure Manager {2} 1/3 — Leverage 1. When any Leverage counter is
#     removed from a Trader you control, gain 1 Liquidity.
def _exposure_manager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(1)(obj, state)

    def counter_removed_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_REMOVED:
            return False
        if event.payload.get("counter_type") != "leverage":
            return False
        # Must be a Trader controlled by this player
        target_id = event.payload.get("object_id")
        return bool(target_id)

    def counter_removed_effect(event: Event, state: GameState) -> InterceptorResult:
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id) if target_id else None
        if not target or target.controller != obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        if CardType.FIN_TRADER not in target.characteristics.types:
            return InterceptorResult(action=InterceptorAction.PASS)
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals, player.mana_crystals_available + 1
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    removal_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=counter_removed_filter,
        handler=counter_removed_effect,
        duration="while_on_battlefield",
    )

    return leverage_interceptors + [removal_interceptor]


EXPOSURE_MANAGER = make_trader(
    "Exposure Manager",
    "{2}",
    2, 3,  # balanced: power 1 → 2 (FIN_TRADER buff, power ≤ 3)
    text="Leverage 1. When any Leverage counter is removed from a Trader you control, gain 1 Liquidity.",
    setup_interceptors=_exposure_manager_setup,
    rarity="uncommon",
)

# 15. Basis Trade Analyst {3} 3/2 — Leverage 1. When this attacks, you may
#     move 1 Leverage counter from it to another Trader you control.
def _basis_trade_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_interceptors = _make_leverage_setup(1)(obj, state)

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        current = state.objects.get(obj.id)
        if not current or current.state.counters.get("leverage", 0) <= 0:
            return []

        # Find another Trader controlled by this player
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return []
        target_id = None
        for oid in list(battlefield.objects):
            if oid == obj.id:
                continue
            candidate = state.objects.get(oid)
            if (candidate
                    and candidate.controller == obj.controller
                    and CardType.FIN_TRADER in candidate.characteristics.types):
                target_id = oid
                break

        if not target_id:
            return []

        # Move 1 counter
        current.state.counters["leverage"] = max(0, current.state.counters["leverage"] - 1)
        target_obj = state.objects.get(target_id)
        if target_obj:
            target_obj.state.counters["leverage"] = (
                target_obj.state.counters.get("leverage", 0) + 1
            )
        return [
            Event(
                type=EventType.COUNTER_REMOVED,
                payload={"object_id": obj.id, "counter_type": "leverage", "amount": 1},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={"object_id": target_id, "counter_type": "leverage", "amount": 1},
                source=obj.id,
                controller=obj.controller,
            ),
        ]

    def attack_filter(event, state, src_obj):
        return (
            event.type == EventType.ATTACK_DECLARED
            and event.payload.get("attacker_id") == src_obj.id
        )

    return leverage_interceptors + [make_attack_trigger(obj, attack_effect, filter_fn=attack_filter)]


BASIS_TRADE_ANALYST = make_trader(
    "Basis Trade Analyst",
    "{3}",
    4, 2,  # balanced: power 3 → 4 (FIN_TRADER buff, power ≤ 3)
    text="Leverage 1. When this attacks, you may move 1 Leverage counter from it to another Trader you control.",
    setup_interceptors=_basis_trade_analyst_setup,
    rarity="uncommon",
)


# =============================================================================
# STRATEGIES (6 cards)
# =============================================================================

# 16. Short Squeeze {2} — Short Selling
def _short_squeeze_resolve(event: Event, state: GameState) -> list[Event]:
    return _short_sell_resolve(event, state)


SHORT_SQUEEZE = make_strategy(
    "Short Squeeze",
    "{2}",
    text="Short Selling — exile target Trader you control. Return it at the start of your next Pre-Market with two +1/+1 counters.",
    resolve=_short_squeeze_resolve,
    rarity="uncommon",
)

# 17. Vega Spike {3} — Place 2 Leverage counters on target Trader you control.
def _vega_spike_resolve(event: Event, state: GameState) -> list[Event]:
    # bug #24: AI passes targets as a flat list ``[card_id]`` (see
    # finance_adapter._choose_play_action), but this code previously assumed a
    # nested ``[[card_id]]`` shape and indexed ``targets[0][0]`` — picking up
    # the first character of the card_id string, which never matched a real
    # object. Result: 2 COUNTER_ADDED events emitted at a non-existent target,
    # the pipeline silently dropped them, and counters never landed.
    # Now: read ``target_id`` (set explicitly by finance_turn._play_card_action)
    # first, fall back to either flat ``targets[0]=str`` or nested
    # ``targets[0]=[id, ...]``. Emit ONE COUNTER_ADDED with amount=2 (matching
    # bug #14's invariant in _make_leverage_setup); pipeline applies exactly
    # once. The previous direct-set fallback double-counted with the pipeline
    # write so it has been removed.
    target_id: str | None = event.payload.get("target_id")
    if not target_id:
        targets = event.payload.get("targets", [])
        if targets:
            first = targets[0]
            if isinstance(first, str):
                target_id = first
            elif isinstance(first, list) and first:
                target_id = first[0]
    if not target_id or target_id not in state.objects:
        return []

    return [Event(
        type=EventType.COUNTER_ADDED,
        payload={
            "object_id": target_id,
            "counter_type": "leverage",
            "amount": 2,
        },
        source=event.source,
        controller=event.controller,
    )]


VEGA_SPIKE = make_strategy(
    "Vega Spike",
    "{3}",
    text="Place 2 Leverage counters on target Trader you control.",
    resolve=_vega_spike_resolve,
    rarity="common",
)

# 18. Margin Call {4} — Each of your Traders loses all Leverage counters. For
#     each counter removed, deal 1 damage to target opponent Trader.
def _margin_call_resolve(event: Event, state: GameState) -> list[Event]:
    events: list[Event] = []
    controller = event.controller
    targets = event.payload.get("targets", [[]])
    target_id: str | None = None
    if targets and targets[0]:
        target_id = targets[0][0]

    total_removed = 0
    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in list(battlefield.objects):
            obj = state.objects.get(oid)
            if not obj or obj.controller != controller:
                continue
            if CardType.FIN_TRADER not in obj.characteristics.types:
                continue
            lev = int(obj.state.counters.get("leverage", 0) or 0)
            if lev > 0:
                obj.state.counters["leverage"] = 0
                total_removed += lev
                events.append(Event(
                    type=EventType.COUNTER_REMOVED,
                    payload={
                        "object_id": oid,
                        "counter_type": "leverage",
                        "amount": lev,
                    },
                    source=event.source,
                    controller=controller,
                ))

    if target_id and total_removed > 0:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={"target": target_id, "amount": total_removed},
            source=event.source,
            controller=controller,
        ))

    return events


MARGIN_CALL = make_strategy(
    "Margin Call",
    "{3}",  # balanced: cost {4} → {3} (FIN_STRATEGY 4+ cost buff)
    text="Each of your Traders loses all Leverage counters. For each counter removed this way, deal 1 damage to target opponent Trader.",
    resolve=_margin_call_resolve,
    rarity="uncommon",
)

# 19. Capital Call {5} — Search your Book for a Trader with Leverage and put
#     it into your hand. Gain Liquidity equal to its Leverage value this turn.
def _capital_call_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.controller
    player = state.players.get(controller)
    if not player:
        return []

    # Search library for any Trader with Leverage (has "Leverage" in text)
    library_zone = None
    for zone_key, zone in state.zones.items():
        if hasattr(zone, "type") and str(zone.type).endswith("LIBRARY") and zone.owner == controller:
            library_zone = zone
            break

    found_id = None
    found_leverage = 0
    if library_zone:
        for oid in list(library_zone.objects):
            obj = state.objects.get(oid)
            if not obj:
                continue
            if CardType.FIN_TRADER not in obj.characteristics.types:
                continue
            if "Leverage" in (obj.characteristics.abilities or []) or \
               "Leverage" in (getattr(obj, "text", "") or ""):
                found_id = oid
                # Estimate leverage from counter setup (cards have N=1..4 at ETB)
                found_leverage = int(obj.state.counters.get("leverage", 1))
                break

    if not found_id:
        return []

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": found_id,
            "from_zone": "library",
            "to_zone": "hand",
            "reason": "search",
        },
        source=event.source,
        controller=controller,
    )]

    if found_leverage > 0:
        player.mana_crystals_available = min(
            player.mana_crystals, player.mana_crystals_available + found_leverage
        )

    return events


CAPITAL_CALL = make_strategy(
    "Capital Call",
    "{4}",  # balanced: cost {5} → {4} (FIN_STRATEGY 4+ cost buff)
    text="Search your Book for a Trader with Leverage and put it into your hand. Gain Liquidity equal to its Leverage value this turn.",
    resolve=_capital_call_resolve,
    rarity="rare",
)

# 20. Leveraged Buyout {5} — Gain control of target Trader. Place Leverage
#     counters on it equal to its Defense Rating.
def _leveraged_buyout_resolve(event: Event, state: GameState) -> list[Event]:
    events: list[Event] = []
    controller = event.controller
    targets = event.payload.get("targets", [[]])
    target_id: str | None = None
    if targets and targets[0]:
        target_id = targets[0][0]
    if not target_id:
        return []

    target_obj = state.objects.get(target_id)
    if not target_obj:
        return []

    toughness = target_obj.characteristics.toughness or 0

    events.append(Event(
        type=EventType.GAIN_CONTROL,
        payload={"object_id": target_id, "new_controller": controller},
        source=event.source,
        controller=controller,
    ))

    # Place Leverage counters equal to Defense Rating
    for _ in range(toughness):
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={
                "object_id": target_id,
                "counter_type": "leverage",
                "amount": 1,
            },
            source=event.source,
            controller=controller,
        ))

    # Fallback: set counters directly
    target_obj.state.counters["leverage"] = (
        target_obj.state.counters.get("leverage", 0) + toughness
    )

    return events


LEVERAGED_BUYOUT = make_strategy(
    "Leveraged Buyout",
    "{4}",  # balanced: cost {5} → {4} (FIN_STRATEGY 4+ cost buff)
    text="Gain control of target Trader. Place Leverage counters on it equal to its Defense Rating.",
    resolve=_leveraged_buyout_resolve,
    rarity="mythic",
)

# 21. Carry Trade {3} — Gain 1 Liquidity for each Leverage counter across all
#     Traders you control (maximum 5).
def _carry_trade_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.controller
    player = state.players.get(controller)
    if not player:
        return []

    total_leverage = 0
    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in list(battlefield.objects):
            obj = state.objects.get(oid)
            if not obj or obj.controller != controller:
                continue
            if CardType.FIN_TRADER not in obj.characteristics.types:
                continue
            total_leverage += int(obj.state.counters.get("leverage", 0) or 0)

    gain = min(5, total_leverage)
    if gain > 0:
        player.mana_crystals_available = min(
            player.mana_crystals, player.mana_crystals_available + gain
        )

    return []


CARRY_TRADE = make_strategy(
    "Carry Trade",
    "{3}",
    text="Gain 1 Liquidity for each Leverage counter across all Traders you control (maximum 5).",
    resolve=_carry_trade_resolve,
    rarity="common",
)


# =============================================================================
# ORDERS (3 cards)
# =============================================================================

# 22. Volatility Crush {2} — Remove all Leverage counters from target Trader.
#     If opponent's, deal damage equal to counters removed.
def _volatility_crush_resolve(event: Event, state: GameState) -> list[Event]:
    events: list[Event] = []
    controller = event.controller
    targets = event.payload.get("targets", [[]])
    target_id: str | None = None
    if targets and targets[0]:
        target_id = targets[0][0]
    if not target_id:
        return []

    target_obj = state.objects.get(target_id)
    if not target_obj:
        return []

    lev = int(target_obj.state.counters.get("leverage", 0) or 0)
    is_opponent = target_obj.controller != controller

    if lev > 0:
        target_obj.state.counters["leverage"] = 0
        events.append(Event(
            type=EventType.COUNTER_REMOVED,
            payload={
                "object_id": target_id,
                "counter_type": "leverage",
                "amount": lev,
            },
            source=event.source,
            controller=controller,
        ))

    if is_opponent and lev > 0:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={"target": target_id, "amount": lev},
            source=event.source,
            controller=controller,
        ))

    return events


VOLATILITY_CRUSH = make_order(
    "Volatility Crush",
    "{2}",
    text="Remove all Leverage counters from target Trader. If opponent's, deal damage equal to counters removed to that Trader.",
    resolve=_volatility_crush_resolve,
    rarity="common",
)

# 23. Gamma Hedge {2} — Target Trader you control gets +1/+1 for each Leverage
#     counter on it until Market Close.
def _gamma_hedge_resolve(event: Event, state: GameState) -> list[Event]:
    targets = event.payload.get("targets", [[]])
    target_id: str | None = None
    if targets and targets[0]:
        target_id = targets[0][0]
    if not target_id:
        return []

    target_obj = state.objects.get(target_id)
    if not target_obj:
        return []

    lev = int(target_obj.state.counters.get("leverage", 0) or 0)
    if lev <= 0:
        return []

    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={
            "object_id": target_id,
            "power_mod": lev,
            "toughness_mod": lev,
            "duration": "end_of_turn",
        },
        source=event.source,
        controller=event.controller,
    )]


GAMMA_HEDGE = make_order(
    "Gamma Hedge",
    "{2}",
    text="Target Trader you control gets +1/+1 for each Leverage counter on it until Market Close.",
    resolve=_gamma_hedge_resolve,
    rarity="common",
)

# 24. Delta Neutral {3} — Target Trader you control loses all Leverage counters.
#     Remove all damage from it.
def _delta_neutral_resolve(event: Event, state: GameState) -> list[Event]:
    events: list[Event] = []
    targets = event.payload.get("targets", [[]])
    target_id: str | None = None
    if targets and targets[0]:
        target_id = targets[0][0]
    if not target_id:
        return []

    target_obj = state.objects.get(target_id)
    if not target_obj:
        return []

    lev = int(target_obj.state.counters.get("leverage", 0) or 0)
    if lev > 0:
        target_obj.state.counters["leverage"] = 0
        events.append(Event(
            type=EventType.COUNTER_REMOVED,
            payload={
                "object_id": target_id,
                "counter_type": "leverage",
                "amount": lev,
            },
            source=event.source,
            controller=event.controller,
        ))

    # Remove all damage
    target_obj.state.damage = 0

    return events


DELTA_NEUTRAL = make_order(
    "Delta Neutral",
    "{2}",  # balanced: cost {3} → {2} (FIN_ORDER 3+ cost buff — immediate value)
    text="Target Trader you control loses all Leverage counters. Remove all damage from it.",
    resolve=_delta_neutral_resolve,
    rarity="uncommon",
)

# 25. Cover Short {2} — Return an exiled Trader you own to the Trading Floor
#     immediately, with its counters.
def _cover_short_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.controller

    # Find an exiled Trader owned by this player
    exile_zone = None
    for zone_key, zone in state.zones.items():
        if (hasattr(zone, "type") and str(zone.type).endswith("EXILE")
                and zone.owner == controller):
            exile_zone = zone
            break

    if not exile_zone:
        return []

    target_id = None
    for oid in list(exile_zone.objects):
        obj = state.objects.get(oid)
        if obj and obj.owner == controller and CardType.FIN_TRADER in obj.characteristics.types:
            target_id = oid
            break

    if not target_id:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": target_id,
            "from_zone": "exile",
            "to_zone": "battlefield",
            "reason": "cover_short",
        },
        source=event.source,
        controller=controller,
    )]


COVER_SHORT = make_order(
    "Cover Short",
    "{2}",
    text="Return an exiled Trader you own to the Trading Floor immediately, with its counters.",
    resolve=_cover_short_resolve,
    rarity="uncommon",
)


# =============================================================================
# ASSETS (3 cards)
# =============================================================================

# 26. The Black-Scholes Model {3} — Pre-Market: may pay 1 Liquidity to remove
#     1 Leverage counter from any Trader you control.
def _black_scholes_model_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def pre_market_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "pre_market"
            and event.payload.get("player") == obj.controller
        )

    def pre_market_effect(event: Event, state: GameState) -> InterceptorResult:
        player = state.players.get(obj.controller)
        if not player or player.mana_crystals_available < 1:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Find a Trader with Leverage counters
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)

        for oid in list(battlefield.objects):
            target = state.objects.get(oid)
            if not target or target.controller != obj.controller:
                continue
            if CardType.FIN_TRADER not in target.characteristics.types:
                continue
            if target.state.counters.get("leverage", 0) > 0:
                # Pay 1 Liquidity and remove 1 counter
                player.mana_crystals_available -= 1
                target.state.counters["leverage"] -= 1
                remove_event = Event(
                    type=EventType.COUNTER_REMOVED,
                    payload={
                        "object_id": oid,
                        "counter_type": "leverage",
                        "amount": 1,
                        "reason": "black_scholes",
                    },
                    source=obj.id,
                    controller=obj.controller,
                )
                return InterceptorResult(
                    action=InterceptorAction.REACT, new_events=[remove_event]
                )

        return InterceptorResult(action=InterceptorAction.PASS)

    pre_market_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=pre_market_filter,
        handler=pre_market_effect,
        duration="while_on_battlefield",
    )

    return [pre_market_interceptor]


THE_BLACK_SCHOLES_MODEL = make_asset(
    "The Black-Scholes Model",
    "{3}",
    text="At the start of your Pre-Market, you may pay 1 Liquidity to remove 1 Leverage counter from any Trader you control.",
    setup_interceptors=_black_scholes_model_setup,
    rarity="rare",
)

# 27. Implied Volatility Surface {3} — Static: Traders you control with
#     Leverage counters get +0/+1.
def _implied_volatility_surface_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get("object_id")
        if not target_id:
            return False
        target = state.objects.get(target_id)
        if not target or target.controller != obj.controller:
            return False
        if CardType.FIN_TRADER not in target.characteristics.types:
            return False
        return target.state.counters.get("leverage", 0) > 0

    def toughness_effect(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    toughness_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_effect,
        duration="while_on_battlefield",
    )

    return [toughness_interceptor]


IMPLIED_VOLATILITY_SURFACE = make_asset(
    "Implied Volatility Surface",
    "{3}",
    text="Static: Traders you control with Leverage counters get +0/+1.",
    setup_interceptors=_implied_volatility_surface_setup,
    rarity="uncommon",
)

# 28. Greeks Dashboard {4} — Activated: {2}, tap — add 1 Leverage counter to
#     target Trader you control.
def _greeks_dashboard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def add_leverage(src_obj: GameObject, st: GameState, targets: list) -> list[Event]:
        events: list[Event] = []
        target_id = targets[0].object_id if targets else None
        if not target_id:
            return []
        target = st.objects.get(target_id)
        if not target:
            return []
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={
                "object_id": target_id,
                "counter_type": "leverage",
                "amount": 1,
            },
            source=src_obj.id,
            controller=src_obj.controller,
        ))
        # Fallback: direct update
        target.state.counters["leverage"] = target.state.counters.get("leverage", 0) + 1
        return events

    make_activated_ability(
        obj,
        cost="{2}, Tap",
        effect_fn=add_leverage,
        description="Add 1 Leverage counter to target Trader you control.",
        targets_required=1,
        target_kind="fin_trader",
    )
    return []


GREEKS_DASHBOARD = make_asset(
    "Greeks Dashboard",
    "{4}",
    text="Activated: {2}, tap — add 1 Leverage counter to target Trader you control.",
    setup_interceptors=_greeks_dashboard_setup,
    rarity="uncommon",
)


# =============================================================================
# STRUCTURES (2 cards)
# =============================================================================

# 29. Derivatives Desk Console {3} — Pre-Market: if you have at least one
#     Derivative on your Derivatives Desk, draw a card.
def _derivatives_desk_console_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def pre_market_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "pre_market"
            and event.payload.get("player") == obj.controller
        )

    def pre_market_effect(event: Event, state: GameState) -> InterceptorResult:
        from src.engine.finance import get_deriv_desk
        desk = get_deriv_desk(state, obj.controller)
        if desk:
            draw = Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "amount": 1},
                source=obj.id,
                controller=obj.controller,
            )
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[draw])
        return InterceptorResult(action=InterceptorAction.PASS)

    pre_market_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=pre_market_filter,
        handler=pre_market_effect,
        duration="while_on_battlefield",
    )

    return [pre_market_interceptor]


DERIVATIVES_DESK_CONSOLE = make_structure(
    "Derivatives Desk Console",
    "{3}",
    text="At the start of your Pre-Market, if you have at least one Derivative on your Derivatives Desk, draw a card.",
    setup_interceptors=_derivatives_desk_console_setup,
    rarity="rare",
)

# 30. Risk Waterfall {4} — Pre-Market Market Close: reduce Capital Reserve cost
#     of Leverage counters on one Trader by 1 (minimum 0 per counter).
def _risk_waterfall_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # TRANSFORM on FIN_LEVERAGE_TICK: reduce cost for one Trader by 1.
    # Track which Trader we've already discounted this Market Close.
    discount_key = f"risk_waterfall_discounted_{obj.id}"

    def tick_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.FIN_LEVERAGE_TICK
            and event.payload.get("player") == obj.controller
        )

    def tick_handler(event: Event, state: GameState) -> InterceptorResult:
        # Only discount the first Trader's leverage tick per Market Close
        turn_key = f"risk_waterfall_turn_{obj.id}"
        current_turn = state.turn_data.get("current_turn", 0)
        last_used = state.turn_data.get(turn_key, -1)
        if last_used == current_turn:
            return InterceptorResult(action=InterceptorAction.PASS)

        state.turn_data[turn_key] = current_turn
        oid = event.payload.get("object_id")
        target_obj = state.objects.get(oid) if oid else None
        if not target_obj:
            return InterceptorResult(action=InterceptorAction.PASS)

        lev = int(target_obj.state.counters.get("leverage", 0) or 0)
        if lev <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Reduce the LIFE_CHANGE that will follow this tick by 1
        # We do this by scheduling a compensating LIFE_CHANGE of +1
        compensate = Event(
            type=EventType.LIFE_CHANGE,
            payload={"player": obj.controller, "amount": 1},
            source=obj.id,
            controller=obj.controller,
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[compensate])

    tick_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=tick_filter,
        handler=tick_handler,
        duration="while_on_battlefield",
    )

    return [tick_interceptor]


RISK_WATERFALL = make_structure(
    "Risk Waterfall",
    "{4}",
    text="At the start of your Market Close, reduce the Capital Reserve cost of Leverage counters on one of your Traders by 1 (minimum 0 per counter).",
    setup_interceptors=_risk_waterfall_setup,
    rarity="rare",
)


# =============================================================================
# DERIVATIVES (7 cards)
# =============================================================================
# NOTE: Derivative attachment mechanic is handled by the finance.py system
# interceptor (_register_derivative_attach_on_etb). Cards stage to the
# Derivatives Desk and attach when a Trader enters. The QUERY_POWER /
# QUERY_TOUGHNESS interceptors below check obj.state.attached_to.
#
# RECONCILE TODO: Derivative attachment not yet fully supported;
# effect applies to the Trader this Derivative is attached to via
# obj.state.attached_to.

# 31. Theta Decay Collar {2} — Attach to a Trader: it gets +1/+2 and loses
#     1 Leverage counter at the end of each Pre-Market.
def _theta_decay_collar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        host_id = obj.state.attached_to
        return host_id is not None and event.payload.get("object_id") == host_id

    def power_effect(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_power reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        host_id = obj.state.attached_to
        return host_id is not None and event.payload.get("object_id") == host_id

    def toughness_effect(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    def pre_market_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            host_id is not None
            and event.type == EventType.PHASE_START
            and event.payload.get("phase") == "pre_market"
            and event.payload.get("player") == obj.controller
        )

    def pre_market_effect(event: Event, state: GameState) -> InterceptorResult:
        host_id = obj.state.attached_to
        host = state.objects.get(host_id) if host_id else None
        if host and host.state.counters.get("leverage", 0) > 0:
            host.state.counters["leverage"] -= 1
            remove_event = Event(
                type=EventType.COUNTER_REMOVED,
                payload={
                    "object_id": host_id,
                    "counter_type": "leverage",
                    "amount": 1,
                    "reason": "theta_decay_collar",
                },
                source=obj.id,
                controller=obj.controller,
            )
            return InterceptorResult(
                action=InterceptorAction.REACT, new_events=[remove_event]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter, handler=power_effect,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter, handler=toughness_effect,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=pre_market_filter, handler=pre_market_effect,
            duration="while_on_battlefield",
        ),
    ]


THETA_DECAY_COLLAR = make_derivative(
    "Theta Decay Collar",
    "{2}",
    text="Attach to a Trader: it gets +1/+2 and loses 1 Leverage counter at the end of each Pre-Market.",
    setup_interceptors=_theta_decay_collar_setup,
    rarity="uncommon",
)

# 32. Gamma Amplifier {3} — Attach to a Trader: it gets +2/+1. Its Leverage
#     counters cost 0 Capital Reserve at Market Close this turn.
def _gamma_amplifier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def power_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.QUERY_POWER
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def power_effect(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_power reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    def toughness_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.QUERY_TOUGHNESS
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def toughness_effect(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    # TRANSFORM on FIN_LEVERAGE_TICK for the host this turn: prevent drain once.
    prevent_key = f"gamma_amp_prevent_{obj.id}"

    def tick_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.FIN_LEVERAGE_TICK
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def tick_handler(event: Event, state: GameState) -> InterceptorResult:
        current_turn = state.turn_data.get("current_turn", 0)
        last_used = state.turn_data.get(prevent_key, -1)
        if last_used == current_turn:
            return InterceptorResult(action=InterceptorAction.PASS)
        state.turn_data[prevent_key] = current_turn
        # Compensate the drain with an equal LIFE_CHANGE positive
        host_id = obj.state.attached_to
        host = state.objects.get(host_id) if host_id else None
        if not host:
            return InterceptorResult(action=InterceptorAction.PASS)
        lev = int(host.state.counters.get("leverage", 0) or 0)
        if lev <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        compensate = Event(
            type=EventType.LIFE_CHANGE,
            payload={"player": obj.controller, "amount": lev},
            source=obj.id,
            controller=obj.controller,
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[compensate])

    return [
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter, handler=power_effect,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter, handler=toughness_effect,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=tick_filter, handler=tick_handler,
            duration="while_on_battlefield",
        ),
    ]


GAMMA_AMPLIFIER = make_derivative(
    "Gamma Amplifier",
    "{3}",
    text="Attach to a Trader: it gets +2/+1. Its Leverage counters cost 0 Capital Reserve at Market Close this turn.",
    setup_interceptors=_gamma_amplifier_setup,
    rarity="rare",
)

# 33. Delta Neutral Wrap {2} — Attach to a Trader: remove all damage from it
#     and it gets +0/+2.
def _delta_neutral_wrap_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # On attachment ETB: clear host's damage
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        host_id = obj.state.attached_to
        host = state.objects.get(host_id) if host_id else None
        if host:
            host.state.damage = 0
        return []

    def toughness_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.QUERY_TOUGHNESS
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def toughness_effect(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter, handler=toughness_effect,
            duration="while_on_battlefield",
        ),
    ]


DELTA_NEUTRAL_WRAP = make_derivative(
    "Delta Neutral Wrap",
    "{2}",
    text="Attach to a Trader: remove all damage from it and it gets +0/+2.",
    setup_interceptors=_delta_neutral_wrap_setup,
    rarity="common",
)

# 34. Iron Condor {3} — Attach to a Trader: when this Trader is blocked, deal
#     1 damage to the blocker.
def _iron_condor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def block_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.BLOCK_DECLARED
            and host_id is not None
            and event.payload.get("attacker_id") == host_id
        )

    def block_effect(event: Event, state: GameState) -> InterceptorResult:
        blocker_id = event.payload.get("blocker_id")
        if not blocker_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        damage_event = Event(
            type=EventType.DAMAGE,
            payload={"target": blocker_id, "amount": 1},
            source=obj.id,
            controller=obj.controller,
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[damage_event])

    block_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=block_filter,
        handler=block_effect,
        duration="while_on_battlefield",
    )

    return [block_interceptor]


IRON_CONDOR = make_derivative(
    "Iron Condor",
    "{3}",
    text="Attach to a Trader: when this Trader is blocked, deal 1 damage to the blocker.",
    setup_interceptors=_iron_condor_setup,
    rarity="uncommon",
)

# 35. Protective Put {2} — Attach to a Trader: the first time this Trader would
#     be destroyed, remove this Derivative instead.
def _protective_put_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    used_key = f"protective_put_used_{obj.id}"

    def destroy_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            host_id is not None
            and event.type == EventType.OBJECT_DESTROYED
            and event.payload.get("object_id") == host_id
        )

    def destroy_handler(event: Event, state: GameState) -> InterceptorResult:
        if state.turn_data.get(used_key):
            return InterceptorResult(action=InterceptorAction.PASS)
        state.turn_data[used_key] = True

        # Remove this Derivative from the board instead of letting the host die
        obj.state.attached_to = None
        remove_event = Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": obj.id,
                "from_zone": "battlefield",
                "to_zone": "graveyard",
                "reason": "protective_put_sacrifice",
            },
            source=obj.id,
            controller=obj.controller,
        )
        # Prevent the host's destruction
        return InterceptorResult(
            action=InterceptorAction.PREVENT,
            new_events=[remove_event],
        )

    destroy_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        # priority class: PREVENT action is only honored by _run_prevent_phase,
        # which iterates priority == PREVENT. TRANSFORM never invokes PREVENT.
        priority=InterceptorPriority.PREVENT,
        filter=destroy_filter,
        handler=destroy_handler,
        duration="while_on_battlefield",
    )

    return [destroy_interceptor]


PROTECTIVE_PUT = make_derivative(
    "Protective Put",
    "{2}",
    text="Attach to a Trader: the first time this Trader would be destroyed, remove this Derivative instead.",
    setup_interceptors=_protective_put_setup,
    rarity="rare",
)

# 36. Covered Call {2} — Attach to a Trader: it gets +1/+0 and, when it
#     attacks unblocked, gain 1 Liquidity.
def _covered_call_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def power_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.QUERY_POWER
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def power_effect(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_power reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    # REACT on DAMAGE event where source is the host Trader and target is a player
    # (unblocked damage = direct to player)
    def unblocked_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.DAMAGE
            and host_id is not None
            and event.payload.get("source") == host_id
            and event.payload.get("target") in (state.players if hasattr(state, "players") else {})
        )

    def unblocked_effect(event: Event, state: GameState) -> InterceptorResult:
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals, player.mana_crystals_available + 1
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    # Alternative: listen to ATTACK_DECLARED on host and check is_unblocked
    # For now use a simpler PHASE_based approach — RECONCILE TODO: tie to
    # unblocked-attack confirmation event when available in engine.

    return [
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter, handler=power_effect,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=unblocked_filter, handler=unblocked_effect,
            duration="while_on_battlefield",
        ),
    ]


COVERED_CALL = make_derivative(
    "Covered Call",
    "{2}",
    text="Attach to a Trader: it gets +1/+0 and, when it attacks unblocked, gain 1 Liquidity.",
    setup_interceptors=_covered_call_setup,
    rarity="common",
)

# 37. Synthetic Collar {3} — Attach to a Trader: it gets +1/+1 for each
#     Derivative attached to it (including this one).
def _synthetic_collar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def power_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.QUERY_POWER
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def power_effect(event: Event, state: GameState) -> InterceptorResult:
        host_id = obj.state.attached_to
        host = state.objects.get(host_id) if host_id else None
        if not host:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Count Derivatives attached to the host (attached_to == host_id)
        count = 0
        for oid, o in state.objects.items():
            if (CardType.FIN_DERIVATIVE in o.characteristics.types
                    and o.state.attached_to == host_id):
                count += 1
        if count <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        # bug #25: queries.get_power reads transformed_event.payload['value'] only.
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + count
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    def toughness_filter(event: Event, state: GameState) -> bool:
        host_id = obj.state.attached_to
        return (
            event.type == EventType.QUERY_TOUGHNESS
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def toughness_effect(event: Event, state: GameState) -> InterceptorResult:
        host_id = obj.state.attached_to
        host = state.objects.get(host_id) if host_id else None
        if not host:
            return InterceptorResult(action=InterceptorAction.PASS)
        count = 0
        for oid, o in state.objects.items():
            if (CardType.FIN_DERIVATIVE in o.characteristics.types
                    and o.state.attached_to == host_id):
                count += 1
        if count <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        # bug #25: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + count
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return [
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            # bug #25: priority must be QUERY for queries.get_power to iterate it.
            priority=InterceptorPriority.QUERY,
            filter=power_filter, handler=power_effect,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            # bug #25: priority must be QUERY for queries.get_toughness to iterate it.
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter, handler=toughness_effect,
            duration="while_on_battlefield",
        ),
    ]


SYNTHETIC_COLLAR = make_derivative(
    "Synthetic Collar",
    "{3}",
    text="Attach to a Trader: it gets +1/+1 for each Derivative attached to it (including this one).",
    setup_interceptors=_synthetic_collar_setup,
    rarity="rare",
)


# =============================================================================
# Export dict
# =============================================================================

DERIVATIVES_CARDS: dict[str, CardDefinition] = {
    # Traders (15)
    "Options Desk Intern": OPTIONS_DESK_INTERN,
    "Underlying Asset Runner": UNDERLYING_ASSET_RUNNER,
    "Delta Hedger": DELTA_HEDGER,
    "Rho Opportunist": RHO_OPPORTUNIST,
    "Theta Decay Trader": THETA_DECAY_TRADER,
    "Gamma Scalper": GAMMA_SCALPER,
    "Convexity Rider": CONVEXITY_RIDER,
    "Vega Amplifier": VEGA_AMPLIFIER,
    "Structured Product Builder": STRUCTURED_PRODUCT_BUILDER,
    "Hedge Fund PM": HEDGE_FUND_PM,
    "Synthetic Long": SYNTHETIC_LONG,
    "Risk-Parity Quant": RISK_PARITY_QUANT,
    "Leveraged Buyout Specialist": LEVERAGED_BUYOUT_SPECIALIST,
    "Exposure Manager": EXPOSURE_MANAGER,
    "Basis Trade Analyst": BASIS_TRADE_ANALYST,
    # Strategies (6)
    "Short Squeeze": SHORT_SQUEEZE,
    "Vega Spike": VEGA_SPIKE,
    "Margin Call": MARGIN_CALL,
    "Capital Call": CAPITAL_CALL,
    "Leveraged Buyout": LEVERAGED_BUYOUT,
    "Carry Trade": CARRY_TRADE,
    # Orders (4)
    "Volatility Crush": VOLATILITY_CRUSH,
    "Gamma Hedge": GAMMA_HEDGE,
    "Delta Neutral": DELTA_NEUTRAL,
    "Cover Short": COVER_SHORT,
    # Assets (3)
    "The Black-Scholes Model": THE_BLACK_SCHOLES_MODEL,
    "Implied Volatility Surface": IMPLIED_VOLATILITY_SURFACE,
    "Greeks Dashboard": GREEKS_DASHBOARD,
    # Structures (2)
    "Derivatives Desk Console": DERIVATIVES_DESK_CONSOLE,
    "Risk Waterfall": RISK_WATERFALL,
    # Derivatives (7)
    "Theta Decay Collar": THETA_DECAY_COLLAR,
    "Gamma Amplifier": GAMMA_AMPLIFIER,
    "Delta Neutral Wrap": DELTA_NEUTRAL_WRAP,
    "Iron Condor": IRON_CONDOR,
    "Protective Put": PROTECTIVE_PUT,
    "Covered Call": COVERED_CALL,
    "Synthetic Collar": SYNTHETIC_COLLAR,
}
