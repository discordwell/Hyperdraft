"""FINA Dark Arbitrage + Neutral card set.

36 DARK ARBITRAGE cards + 3 NEUTRAL cards = 39 total.

Dark Arbitrage strategy: Stage Dark Pool Orders defensively turns 1–4,
suppress the opponent's board, deploy one enormous Leverage + Arbitrage
Trader turn 5–6, Arbitrage refuels, Alpha Strike closes the game.

Exported as DARK_ARBITRAGE_CARDS dict (includes the 3 neutral cards).
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
from src.cards.interceptor_helpers import make_etb_trigger, make_attack_trigger
from src.engine.finance import get_dark_pool, set_dark_pool


# =============================================================================
# Finance card factory helpers
# =============================================================================

def _parse_cost(cost_str: str) -> int:
    """Return integer Liquidity cost from '{N}' strings."""
    if not cost_str:
        return 0
    s = cost_str.strip("{}")
    try:
        return int(s)
    except ValueError:
        return 0


def make_trader(
    name: str,
    mana_cost: str,
    power: int,
    toughness: int,
    *,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    """Factory for FIN_TRADER cards."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        domain="FINA",
        text=text,
        rarity=rarity,
        characteristics=Characteristics(
            types={CardType.FIN_TRADER},
            power=power,
            toughness=toughness,
            mana_cost=mana_cost,
        ),
        setup_interceptors=setup_interceptors,
    )


def make_order(
    name: str,
    mana_cost: str,
    *,
    text: str = "",
    rarity: str = "common",
    dark_pool: bool = False,
    dark_pool_consumer: bool = False,
    setup_interceptors=None,
    resolve=None,
) -> CardDefinition:
    """Factory for FIN_ORDER cards (instant-speed).

    If dark_pool_consumer=True (bug #13), the card refuses to cast unless
    the Dark Pool slot is already populated.
    """
    cd = CardDefinition(
        name=name,
        mana_cost=mana_cost,
        domain="FINA",
        text=text,
        rarity=rarity,
        characteristics=Characteristics(
            types={CardType.FIN_ORDER},
            mana_cost=mana_cost,
        ),
        setup_interceptors=setup_interceptors,
        resolve=resolve,
    )
    # Tag dark pool status for the engine's dark pool handler
    cd._dark_pool = dark_pool
    cd._dark_pool_consumer = dark_pool_consumer
    return cd


def make_strategy(
    name: str,
    mana_cost: str,
    *,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
    resolve=None,
) -> CardDefinition:
    """Factory for FIN_STRATEGY cards (sorcery-speed)."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        domain="FINA",
        text=text,
        rarity=rarity,
        characteristics=Characteristics(
            types={CardType.FIN_STRATEGY},
            mana_cost=mana_cost,
        ),
        setup_interceptors=setup_interceptors,
        resolve=resolve,
    )


def make_asset(
    name: str,
    mana_cost: str,
    *,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    """Factory for FIN_ASSET cards (permanent, passive/activated)."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        domain="FINA",
        text=text,
        rarity=rarity,
        characteristics=Characteristics(
            types={CardType.FIN_ASSET},
            mana_cost=mana_cost,
        ),
        setup_interceptors=setup_interceptors,
    )


def make_structure(
    name: str,
    mana_cost: str,
    *,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    """Factory for FIN_STRUCTURE cards (building, max 3 per player)."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        domain="FINA",
        text=text,
        rarity=rarity,
        characteristics=Characteristics(
            types={CardType.FIN_STRUCTURE},
            mana_cost=mana_cost,
        ),
        setup_interceptors=setup_interceptors,
    )


def make_derivative(
    name: str,
    mana_cost: str,
    *,
    text: str = "",
    rarity: str = "common",
    setup_interceptors=None,
) -> CardDefinition:
    """Factory for FIN_DERIVATIVE cards (enchantment-on-Trader)."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        domain="FINA",
        text=text,
        rarity=rarity,
        characteristics=Characteristics(
            types={CardType.FIN_DERIVATIVE},
            mana_cost=mana_cost,
        ),
        setup_interceptors=setup_interceptors,
    )


# =============================================================================
# Shared helper — Dark Pool trigger registration
# =============================================================================

def dark_pool_setup(obj: GameObject, state: GameState, dark_effect_fn) -> list[Interceptor]:
    """Register the Dark Pool trigger interceptor for an Order.

    The global system interceptor in finance.py fires FIN_MARKET_EVENT when
    the Dark Pool Order's turn comes.  This card-level interceptor reacts to
    that event and runs the actual effect.
    """
    def _filter(event: Event, state: GameState) -> bool:
        try:
            return (
                event.type == EventType.FIN_MARKET_EVENT
                and event.payload.get("obj_id") == obj.id
            )
        except Exception:
            return False

    def _effect(event: Event, state: GameState) -> InterceptorResult:
        new_events = dark_effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_effect,
        duration="until_leaves",
    )]


# =============================================================================
# Shared helpers — Leverage + Arbitrage mechanics
# =============================================================================

def _add_leverage_etb(obj: GameObject, n: int) -> Interceptor:
    """ETB trigger that adds N leverage counters."""
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        o = state.objects.get(obj.id)
        if o:
            o.state.counters["leverage"] = o.state.counters.get("leverage", 0) + n
        return []
    return make_etb_trigger(obj, etb_fn)


def _make_leverage_power_query(obj: GameObject) -> Interceptor:
    """QUERY interceptor: QUERY_POWER += leverage counter count.

    bug #19: was priority=TRANSFORM (never iterated by get_power) and mutated
    payload['power'] (never read). Now priority=QUERY and returns TRANSFORM
    with transformed_event.payload['value'] updated, matching the contract
    in queries.get_power.
    """
    def _filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.QUERY_POWER
            and event.payload.get("object_id") == obj.id
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        o = state.objects.get(obj.id)
        lev = o.state.counters.get("leverage", 0) if o else 0
        if lev <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + lev
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,  # bug #19: was TRANSFORM (unread)
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )


def _make_arbitrage_etb(obj: GameObject, n: int) -> Interceptor:
    """ETB trigger: if controller controls more Traders than opponent, gain N Liquidity."""
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        my_t = sum(
            1 for oid in bf.objects
            if (o := state.objects.get(oid))
            and CardType.FIN_TRADER in o.characteristics.types
            and o.controller == obj.controller
        )
        opp_t = sum(
            1 for oid in bf.objects
            if (o := state.objects.get(oid))
            and CardType.FIN_TRADER in o.characteristics.types
            and o.controller != obj.controller
        )
        if my_t > opp_t:
            player = state.players.get(obj.controller)
            if player:
                player.mana_crystals_available = min(
                    player.mana_crystals_available + n,
                    player.mana_crystals,
                )
        return []
    return make_etb_trigger(obj, etb_fn)


def _make_alpha_strike(obj: GameObject) -> Interceptor:
    """ATTACK trigger: if attacking alone (+3/+0 or archetype variant), grant PT bonus.

    Bug #2/#18 fix: relies on finance_combat.declare_attackers() marking ALL
    attackers as attacking BEFORE emitting per-attacker ATTACK_DECLARED events
    so the count below reflects the final attacker set.

    Bug #4 fix: Direct Market Access upgrade flag bumps the bonus by +1.
    Bug #6 fix: solo-alpha attack sets fin_alpha_struck_alone_<controller>.
    Bug #2 sequential-call fix: emitted PT_MOD carries ``_tag='alpha_strike'``
    so finance_combat can revoke it if a later declare_attackers call raises
    the attacker count past 1.
    """
    def atk_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        attacking_count = sum(
            1 for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller == obj.controller
            and getattr(o.state, "attacking", False)
            and CardType.FIN_TRADER in o.characteristics.types
        )
        if attacking_count == 1:
            # Bug #6: mark that an alpha-striker attacked alone this turn.
            state.turn_data[f"fin_alpha_struck_alone_{obj.controller}"] = True
            # Bug #4: Direct Market Access upgrades the bonus by +1.
            upgrade_key = f"fin_alpha_strike_upgrade_{obj.controller}"
            bonus = 3 + (1 if state.turn_data.get(upgrade_key) else 0)
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": obj.id,
                    "power_mod": bonus,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                    "_tag": "alpha_strike",
                },
                source=obj.id,
            )]
        return []
    return make_attack_trigger(obj, atk_fn)


def _make_alpha_strike_plus4(obj: GameObject) -> Interceptor:
    """ATTACK trigger: Alpha Strike with +4/+0 bonus (variant for special cards).

    Bug #2/#18 fix: relies on finance_combat.declare_attackers() marking ALL
    attackers as attacking BEFORE emitting per-attacker ATTACK_DECLARED events.
    Multi-attack now correctly fails the count==1 check for ALL attackers
    (not just the first declared).

    Bug #4 fix: Direct Market Access upgrade flag bumps the bonus by +1.
    Bug #6 fix: solo-alpha attack sets fin_alpha_struck_alone_<controller>.
    Bug #2 sequential-call fix: emitted PT_MOD carries ``_tag='alpha_strike'``
    so finance_combat can revoke it (see ``_make_alpha_strike`` above).
    """
    def atk_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        attacking_count = sum(
            1 for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller == obj.controller
            and getattr(o.state, "attacking", False)
            and CardType.FIN_TRADER in o.characteristics.types
        )
        if attacking_count == 1:
            # Bug #6: mark that an alpha-striker attacked alone this turn.
            state.turn_data[f"fin_alpha_struck_alone_{obj.controller}"] = True
            # Bug #4: Direct Market Access upgrades the bonus by +1.
            upgrade_key = f"fin_alpha_strike_upgrade_{obj.controller}"
            bonus = 4 + (1 if state.turn_data.get(upgrade_key) else 0)
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": obj.id,
                    "power_mod": bonus,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                    "_tag": "alpha_strike",
                },
                source=obj.id,
            )]
        return []
    return make_attack_trigger(obj, atk_fn)


def _count_dark_pool_played(state: GameState, controller: str) -> int:
    """Count Dark Pool Orders placed this game (tracked in turn_data)."""
    return int(state.turn_data.get(f"fin_dp_played_{controller}", 0))


def _count_dark_pool_triggered(state: GameState, controller: str) -> int:
    """Count Dark Pool Orders that have triggered this game."""
    return int(state.turn_data.get(f"fin_dp_triggered_{controller}", 0))


def _dark_pool_is_occupied(state: GameState) -> bool:
    return get_dark_pool(state) is not None


def _get_opponent_ids(obj: GameObject, state: GameState) -> list[str]:
    return [pid for pid in state.players if pid != obj.controller]


# =============================================================================
# TRADERS — 14 cards
# =============================================================================

# Hidden Accumulator {2} 2/2
# When you play a Dark Pool Order, this Trader gets +1/+1 until Market Close.
def _hidden_accumulator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        # FIN_PLAY_CARD with dark_pool=True played by the controller
        if event.type != EventType.FIN_PLAY_CARD:
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        o_id = event.payload.get("object_id") or event.payload.get("card_id")
        if not o_id:
            return False
        played_obj = state.objects.get(o_id)
        if played_obj is None:
            return False
        cd = played_obj.card_def
        return cd is not None and getattr(cd, "_dark_pool", False)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={"object_id": obj.id, "power_mod": 1, "toughness_mod": 1, "duration": "end_of_turn"},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]

HIDDEN_ACCUMULATOR = make_trader(
    "Hidden Accumulator", "{2}", 2, 2,
    text="When you play a Dark Pool Order, this Trader gets +1/+1 until Market Close.",
    setup_interceptors=_hidden_accumulator_setup,
)


# Stealth Position Builder {3} 2/4
# When a Dark Pool Order you staged triggers, draw a card.
def _stealth_position_builder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.FIN_MARKET_EVENT:
            return False
        dp_id = event.payload.get("obj_id")
        if not dp_id:
            return False
        dp_obj = state.objects.get(dp_id)
        if dp_obj is None:
            return False
        return dp_obj.controller == obj.controller

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]

STEALTH_POSITION_BUILDER = make_trader(
    "Stealth Position Builder", "{3}", 2, 4,
    text="When a Dark Pool Order you staged triggers, draw a card.",
    setup_interceptors=_stealth_position_builder_setup,
)


# Off-Exchange Operative {3} 3/3 — Leverage 1. Arbitrage 1.
def _off_exchange_operative_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [
        _add_leverage_etb(obj, 1),
        _make_leverage_power_query(obj),
        _make_arbitrage_etb(obj, 1),
    ]

OFF_EXCHANGE_OPERATIVE = make_trader(
    "Off-Exchange Operative", "{3}", 3, 4,  # rebalance: dead-card repair toughness 3 → 4 (Lev1+Arb1 self-tax punishes 3/3 too much)
    text="Leverage 1. Arbitrage 1.",
    setup_interceptors=_off_exchange_operative_setup,
)


# Dark Flow Aggregator {3} 3/2
# When this enters, place a Dark Pool Order from your hand into the Dark Pool zone (bypassing cost).
def _dark_flow_aggregator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        # Simplified: find the first Dark Pool Order in the controller's hand
        # and move it to the Dark Pool slot (for free).
        # Full implementation would open a PendingChoice; this picks the first available.
        hand_zone = None
        for zone_key, zone in state.zones.items():
            if zone.owner == obj.controller and zone.type == ZoneType.HAND:
                hand_zone = zone
                break
        if not hand_zone:
            return []
        for oid in list(hand_zone.objects):
            candidate = state.objects.get(oid)
            if candidate is None:
                continue
            cd = candidate.card_def
            if cd is None:
                continue
            if not getattr(cd, "_dark_pool", False):
                continue
            # Place the Dark Pool Order into the Dark Pool slot
            if get_dark_pool(state) is not None:
                set_dark_pool(state, None)  # replace existing
            set_dark_pool(state, oid)
            # Remove from hand (zone-change to a "dark pool" holding; we use EXILE
            # as a proxy since Dark Pool is modelled in turn_data, not a real ZoneType).
            hand_zone.objects.remove(oid)
            candidate.zone = ZoneType.EXILE  # hidden staging
            # Track play count
            key = f"fin_dp_played_{obj.controller}"
            state.turn_data[key] = state.turn_data.get(key, 0) + 1
            break
        return []
    return [make_etb_trigger(obj, etb_fn)]

DARK_FLOW_AGGREGATOR = make_trader(
    "Dark Flow Aggregator", "{3}", 3, 2,
    text="When this enters, place a Dark Pool Order from your hand into the Dark Pool zone (bypassing cost).",
    setup_interceptors=_dark_flow_aggregator_setup,
)


# Institutional Block Trader {4} 3/4 — Leverage 2. Arbitrage 1. When this enters, gain 2 Liquidity this turn.
def _institutional_block_trader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_gain(event: Event, state: GameState) -> list[Event]:
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals_available + 2, player.mana_crystals
            )
        return []
    return [
        _add_leverage_etb(obj, 2),
        _make_leverage_power_query(obj),
        _make_arbitrage_etb(obj, 1),
        make_etb_trigger(obj, etb_gain),
    ]

INSTITUTIONAL_BLOCK_TRADER = make_trader(
    "Institutional Block Trader", "{5}", 3, 4,  # cyc3: cost {4}→{5}
    text="Leverage 2. Arbitrage 1. When this enters, gain 2 Liquidity this turn.",
    rarity="uncommon",
    setup_interceptors=_institutional_block_trader_setup,
)


# Principal Crossings Desk {4} 4/4 — Leverage 2.
# When this attacks, if the Dark Pool slot is occupied, this gets +2/+0 until Market Close.
def _principal_crossings_desk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def atk_fn(event: Event, state: GameState) -> list[Event]:
        if _dark_pool_is_occupied(state):
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={"object_id": obj.id, "power_mod": 2, "toughness_mod": 0, "duration": "end_of_turn"},
                source=obj.id,
            )]
        return []
    return [
        _add_leverage_etb(obj, 2),
        _make_leverage_power_query(obj),
        make_attack_trigger(obj, atk_fn),
    ]

PRINCIPAL_CROSSINGS_DESK = make_trader(
    "Principal Crossings Desk", "{4}", 3, 4,  # balanced: power 4 → 3 (4+ power FIN_TRADER nerf)
    text="Leverage 2. When this attacks, if the Dark Pool slot is occupied, this gets +2/+0 until Market Close.",
    rarity="uncommon",
    setup_interceptors=_principal_crossings_desk_setup,
)


# Dark Pool Architect {5} 4/4 — Leverage 2. Arbitrage 2.
# When this enters, you may play a Dark Pool Order from your hand at no cost.
def _dark_pool_architect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        # Simplified: auto-stage the first Dark Pool Order in hand at no cost.
        hand_zone = None
        for zone_key, zone in state.zones.items():
            if zone.owner == obj.controller and zone.type == ZoneType.HAND:
                hand_zone = zone
                break
        if not hand_zone:
            return []
        for oid in list(hand_zone.objects):
            candidate = state.objects.get(oid)
            if candidate is None:
                continue
            cd = candidate.card_def
            if cd is None:
                continue
            if not getattr(cd, "_dark_pool", False):
                continue
            if get_dark_pool(state) is not None:
                set_dark_pool(state, None)
            set_dark_pool(state, oid)
            hand_zone.objects.remove(oid)
            candidate.zone = ZoneType.EXILE
            key = f"fin_dp_played_{obj.controller}"
            state.turn_data[key] = state.turn_data.get(key, 0) + 1
            break
        return []
    return [
        _add_leverage_etb(obj, 2),
        _make_leverage_power_query(obj),
        _make_arbitrage_etb(obj, 2),
        make_etb_trigger(obj, etb_fn),
    ]

DARK_POOL_ARCHITECT = make_trader(
    "Dark Pool Architect", "{5}", 4, 4,
    text="Leverage 2. Arbitrage 2. When this enters, you may play a Dark Pool Order from your hand at no cost.",
    rarity="rare",
    setup_interceptors=_dark_pool_architect_setup,
)


# Dark Pool Aggressor {5} 3/4 — Leverage 2 (was 3). Arbitrage 2. Alpha Strike.
def _dark_pool_aggressor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [
        _add_leverage_etb(obj, 2),  # balanced: Leverage 3 → 2
        _make_leverage_power_query(obj),
        _make_arbitrage_etb(obj, 2),
        _make_alpha_strike(obj),
    ]

DARK_POOL_AGGRESSOR = make_trader(
    "Dark Pool Aggressor", "{7}", 3, 4,  # cyc3: cost {5}→{7} (combo finisher too cheap)
    text="Leverage 3. Arbitrage 2. Alpha Strike.",
    rarity="rare",
    setup_interceptors=_dark_pool_aggressor_setup,
)


# OTC Behemoth {6} 5/5 — Leverage 2 (was 3). Arbitrage 2.
# When this attacks alone, opponent cannot play Orders this turn.
def _otc_behemoth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def atk_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        attacking_count = sum(
            1 for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller == obj.controller
            and getattr(o.state, "attacking", False)
            and CardType.FIN_TRADER in o.characteristics.types
        )
        if attacking_count == 1:
            # Mark opponents as order-locked this turn
            for opp_id in _get_opponent_ids(obj, state):
                state.turn_data[f"fin_order_locked_{opp_id}"] = True
        return []

    return [
        _add_leverage_etb(obj, 2),  # balanced: Leverage 3 → 2
        _make_leverage_power_query(obj),
        _make_arbitrage_etb(obj, 2),
        make_attack_trigger(obj, atk_fn),
    ]

OTC_BEHEMOTH = make_trader(
    "OTC Behemoth", "{6}", 5, 5,
    text="Leverage 3. Arbitrage 2. When this attacks alone, opponent cannot play Orders this turn.",
    rarity="rare",
    setup_interceptors=_otc_behemoth_setup,
)


# Internalized Flow Monster {7} 6/5 — Leverage 3 (was 4). Arbitrage 3. Alpha Strike.
# When this enters, trigger all Dark Pool Orders currently staged.
def _internalized_flow_monster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        dp_id = get_dark_pool(state)
        if dp_id:
            set_dark_pool(state, None)
            return [Event(
                type=EventType.FIN_MARKET_EVENT,
                payload={"obj_id": dp_id},
                source=obj.id,
            )]
        return []
    return [
        _add_leverage_etb(obj, 3),  # balanced: Leverage 4 → 3
        _make_leverage_power_query(obj),
        _make_arbitrage_etb(obj, 3),
        _make_alpha_strike(obj),
        make_etb_trigger(obj, etb_fn),
    ]

INTERNALIZED_FLOW_MONSTER = make_trader(
    "Internalized Flow Monster", "{7}", 6, 5,
    text="Leverage 4. Arbitrage 3. Alpha Strike. When this enters, trigger all Dark Pool Orders currently staged.",
    rarity="mythic",
    setup_interceptors=_internalized_flow_monster_setup,
)


# Shadow Accumulation Desk {4} 3/4 — Arbitrage 2. When this enters, look at opponent's hand.
def _shadow_accumulation_desk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        # RECONCILE TODO: needs hand visibility mechanic — return empty list for now
        return []
    return [
        _make_arbitrage_etb(obj, 2),
        make_etb_trigger(obj, etb_fn),
    ]

SHADOW_ACCUMULATION_DESK = make_trader(
    "Shadow Accumulation Desk", "{4}", 3, 4,
    text="Arbitrage 2. When this enters, look at opponent's hand.",
    setup_interceptors=_shadow_accumulation_desk_setup,
)


# Dark Inventory Position {3} 2/3
# When this enters, search your Book for a Dark Pool Order and put it into your hand.
def _dark_inventory_position_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        # Emit a SEARCH_LIBRARY event — the engine resolves it as a tutor for the player.
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                "player": obj.controller,
                "filter": "dark_pool_order",
                "destination": "hand",
                "count": 1,
            },
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_fn)]

DARK_INVENTORY_POSITION = make_trader(
    "Dark Inventory Position", "{3}", 2, 3,
    text="When this enters, search your Book for a Dark Pool Order and put it into your hand.",
    setup_interceptors=_dark_inventory_position_setup,
)


# Crossing Network Pilot {4} 4/3 — Leverage 2.
# When this attacks, deal 1 damage to target Trader regardless of blocking.
#
# Phase 4 demo: damage allocation uses ``divide_allocation`` PendingChoice so
# humans can choose which enemy Trader takes the leverage damage. AI keeps the
# old "all-to-weakest" behavior via ``heuristic_pick``. Each target gets at
# least 1, so with ``total_amount=1`` exactly one target absorbs the damage.
def _crossing_network_pilot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def atk_fn(event: Event, state: GameState) -> list[Event]:
        # Find all candidate opposing Traders
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        opp_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller != obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        if not opp_traders:
            return []

        # Lazy import: avoids circulars when this module is loaded for cards.
        from src.engine.pending_choice_helpers import create_choice_and_resolve

        total_amount = 1  # printed: "deal 1 damage". See card text above.
        source_id = obj.id
        controller = obj.controller

        # Build options for ChoiceModal. ``name``/``type``/``life`` (toughness
        # here) keys are surfaced by the divide_allocation renderer for the
        # +/- target chips.
        options = [
            {
                "id": t.id,
                "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "name": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "type": "Trader",
                "life": (t.characteristics.toughness or 0) - int(getattr(t.state, "damage", 0) or 0),
                "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
            }
            for t in opp_traders
        ]

        # AI heuristic: preserve the old "all-to-weakest" pick.
        weakest = min(opp_traders, key=lambda o: o.characteristics.toughness or 0)
        heuristic = [{"target_id": weakest.id, "amount": total_amount}]

        def _resolve_handler(choice, selected, st):
            # ``selected`` is a list of {target_id, amount} after normalization
            # by Game._process_divide_allocation_choice — or a dict mapping
            # target_id -> amount.
            allocations = selected if isinstance(selected, dict) else {}
            if not allocations and isinstance(selected, list):
                for item in selected:
                    if isinstance(item, dict):
                        tid = item.get("target_id") or item.get("id")
                        if tid:
                            allocations[tid] = int(item.get("amount", 0) or 0)
                    elif isinstance(item, tuple) and len(item) == 2:
                        allocations[item[0]] = int(item[1] or 0)
            if not allocations:
                # Safety: empty/invalid selection -> fall back to heuristic.
                allocations = {weakest.id: total_amount}
            return [
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": tid, "amount": int(amt or 0), "source": source_id},
                    source=source_id,
                    controller=controller,
                )
                for tid, amt in allocations.items()
                if amt and int(amt) > 0
            ]

        return create_choice_and_resolve(
            state,
            choice_type="divide_allocation",
            player_id=controller,
            prompt="Distribute leverage damage among opposing Traders",
            options=options,
            source_id=source_id,
            min_choices=1,
            max_choices=len(options),
            handler=_resolve_handler,
            heuristic_pick=heuristic,
            total_amount=total_amount,
            effect_type="damage",
        )

    return [
        _add_leverage_etb(obj, 2),
        _make_leverage_power_query(obj),
        make_attack_trigger(obj, atk_fn),
    ]

CROSSING_NETWORK_PILOT = make_trader(
    "Crossing Network Pilot", "{4}", 4, 3,  # rebalance: dead-card repair power 3 → 4 (outclassed by Vega Amplifier at same cost)
    text="Leverage 2. When this attacks, deal 1 damage to target Trader regardless of blocking.",
    rarity="uncommon",
    setup_interceptors=_crossing_network_pilot_setup,
)


# Off-Exchange Finisher {5} 5/4 — Leverage 2. Arbitrage 2. Alpha Strike bonus is +4/+0.
def _off_exchange_finisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [
        _add_leverage_etb(obj, 2),
        _make_leverage_power_query(obj),
        _make_arbitrage_etb(obj, 2),
        _make_alpha_strike_plus4(obj),
    ]

OFF_EXCHANGE_FINISHER = make_trader(
    "Off-Exchange Finisher", "{5}", 3, 4,  # cyc3: power 5→3 (base 5+lev2+alpha4=11 was lethal)
    text="Leverage 2. Arbitrage 2. Alpha Strike bonus is +4/+0 for this Trader.",
    rarity="rare",
    setup_interceptors=_off_exchange_finisher_setup,
)


# =============================================================================
# ORDERS — 9 cards
# =============================================================================

# Iceberg Order {1} — Dark Pool. When this triggers, deal 1 damage to target Trader and draw a card.
#
# Phase 4 migration: damage allocation now uses ``divide_allocation``
# PendingChoice so humans can spread the 1 leverage damage across opposing
# Traders. AI keeps the old "all-to-weakest" pick via ``heuristic_pick``.
def _iceberg_order_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        # Always track trigger count + always draw, regardless of damage path.
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        draw_event = Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1},
            source=obj.id,
        )
        bf = state.zones.get("battlefield")
        if not bf:
            return [draw_event]
        opp_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller != obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        if not opp_traders:
            # No targets: still draw (the draw is unconditional in card text).
            return [draw_event]

        # Lazy import: avoids circulars during finance.py setup.
        from src.engine.pending_choice_helpers import create_choice_and_resolve

        total_amount = 1  # printed: "deal 1 damage"
        source_id = obj.id
        controller = obj.controller

        options = [
            {
                "id": t.id,
                "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "name": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "type": "Trader",
                "life": (t.characteristics.toughness or 0) - int(getattr(t.state, "damage", 0) or 0),
                "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
            }
            for t in opp_traders
        ]

        # AI heuristic: preserve old "weakest-toughness" pick.
        weakest = min(opp_traders, key=lambda o: o.characteristics.toughness or 0)
        heuristic = [{"target_id": weakest.id, "amount": total_amount}]

        def _resolve_handler(choice, selected, st):
            allocations: dict[str, int] = selected if isinstance(selected, dict) else {}
            if not allocations and isinstance(selected, list):
                for item in selected:
                    if isinstance(item, dict):
                        tid = item.get("target_id") or item.get("id")
                        if tid:
                            allocations[tid] = int(item.get("amount", 0) or 0)
                    elif isinstance(item, tuple) and len(item) == 2:
                        allocations[item[0]] = int(item[1] or 0)
            if not allocations:
                allocations = {weakest.id: total_amount}
            dmg_events = [
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": tid, "amount": int(amt or 0), "source": source_id},
                    source=source_id,
                    controller=controller,
                )
                for tid, amt in allocations.items()
                if amt and int(amt) > 0
            ]
            # Card text: "deal 1 damage AND draw a card". Both happen.
            return dmg_events + [Event(
                type=EventType.DRAW,
                payload={"player": controller, "count": 1},
                source=source_id,
            )]

        return create_choice_and_resolve(
            state,
            choice_type="divide_allocation",
            player_id=controller,
            prompt="Distribute Iceberg Order damage among opposing Traders",
            options=options,
            source_id=source_id,
            min_choices=1,
            max_choices=len(options),
            handler=_resolve_handler,
            heuristic_pick=heuristic,
            total_amount=total_amount,
            effect_type="damage",
        )

    return dark_pool_setup(obj, state, dark_effect)

ICEBERG_ORDER = make_order(
    "Iceberg Order", "{1}",
    text="Dark Pool. When this triggers, deal 1 damage to target Trader and draw a card.",
    dark_pool=True,
    setup_interceptors=_iceberg_order_setup,
)


# Off-Exchange Position {2} — Dark Pool. When this triggers, target Trader gets -3/-0 until Market Close.
#
# Phase 4 migration: humans pick the debuff target via a "target" PendingChoice;
# AI keeps the old "highest-power threat" pick via ``heuristic_pick``.
def _off_exchange_position_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1

        bf = state.zones.get("battlefield")
        if not bf:
            return []
        opp_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller != obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        if not opp_traders:
            return []

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        source_id = obj.id
        controller = obj.controller

        options = [
            {
                "id": t.id,
                "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
            }
            for t in opp_traders
        ]

        # AI heuristic: preserve old "highest-power threat" pick.
        best = max(opp_traders, key=lambda o: o.characteristics.power or 0)

        def _resolve_handler(choice, selected, st):
            tid = selected[0] if selected else best.id
            if isinstance(tid, dict):
                tid = tid.get("id") or tid.get("target_id")
            if not tid:
                tid = best.id
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={"object_id": tid, "power_mod": -3, "toughness_mod": 0, "duration": "end_of_turn"},
                source=source_id,
                controller=controller,
            )]

        return create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=controller,
            prompt="Choose an opposing Trader to give -3/-0",
            options=options,
            source_id=source_id,
            handler=_resolve_handler,
            heuristic_pick=[best.id],
        )

    return dark_pool_setup(obj, state, dark_effect)

OFF_EXCHANGE_POSITION = make_order(
    "Off-Exchange Position", "{2}",
    text="Dark Pool. Requires a populated Dark Pool slot to cast. When this triggers, target Trader gets -3/-0 until Market Close.",  # bug #13: clarify prerequisite
    dark_pool=True,
    dark_pool_consumer=True,  # bug #13: refuse cast without DP slot already populated
    setup_interceptors=_off_exchange_position_setup,
)


# Block Trade Sweep {3} — Dark Pool. When this triggers, destroy target Trader with Defense Rating 3 or less.
#
# Phase 4 migration: humans pick the destroyed Trader via a "target" choice
# (filtered to defense ≤3); AI keeps the old min-toughness pick.
def _block_trade_sweep_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1

        bf = state.zones.get("battlefield")
        if not bf:
            return []
        small_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller != obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
            and (o.characteristics.toughness or 0) <= 3
        ]
        if not small_traders:
            return []

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        source_id = obj.id
        controller = obj.controller

        options = [
            {
                "id": t.id,
                "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
            }
            for t in small_traders
        ]

        weakest = min(small_traders, key=lambda o: o.characteristics.toughness or 0)

        def _resolve_handler(choice, selected, st):
            tid = selected[0] if selected else weakest.id
            if isinstance(tid, dict):
                tid = tid.get("id") or tid.get("target_id")
            if not tid:
                tid = weakest.id
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": tid, "reason": "block_trade_sweep"},
                source=source_id,
                controller=controller,
            )]

        return create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=controller,
            prompt="Choose an opposing Trader (Defense ≤3) to destroy",
            options=options,
            source_id=source_id,
            handler=_resolve_handler,
            heuristic_pick=[weakest.id],
        )

    return dark_pool_setup(obj, state, dark_effect)

BLOCK_TRADE_SWEEP = make_order(
    "Block Trade Sweep", "{2}",  # rebalance: removal cost-cut {3} → {2} (conditional+DP-gated removal at {3} too steep)
    text="Dark Pool. When this triggers, destroy target Trader with Defense Rating 3 or less.",
    dark_pool=True,
    rarity="uncommon",
    setup_interceptors=_block_trade_sweep_setup,
)


# Forced Liquidation {3} — Order. Destroy target Trader.
# rebalance: NEW card (the missing answer) — unconditional {3} destroy-target-Trader.
# Mirrors Murder/Doom Blade benchmark; format previously had no clean answer at this cost.
#
# Phase 4 migration: humans pick the destroyed Trader; AI keeps the old
# "highest-power threat" pick via ``heuristic_pick``.
def _forced_liquidation_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    candidates = [
        o for oid in getattr(bf, "objects", [])
        if (o := state.objects.get(oid))
        and o.controller != controller
        and CardType.FIN_TRADER in o.characteristics.types
    ]
    if not candidates:
        return []

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    source_id = event.payload.get("source_id", "") or event.source or ""

    options = [
        {
            "id": t.id,
            "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
            "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
        }
        for t in candidates
    ]

    best = max(candidates, key=lambda o: o.characteristics.power or 0)

    def _resolve_handler(choice, selected, st):
        tid = selected[0] if selected else best.id
        if isinstance(tid, dict):
            tid = tid.get("id") or tid.get("target_id")
        if not tid:
            tid = best.id
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={"object_id": tid, "reason": "forced_liquidation"},
            source=source_id,
            controller=controller,
        )]

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=controller,
        prompt="Choose an opposing Trader to destroy",
        options=options,
        source_id=source_id,
        handler=_resolve_handler,
        heuristic_pick=[best.id],
    )


FORCED_LIQUIDATION = make_order(
    "Forced Liquidation", "{3}",
    text="Destroy target Trader.",
    rarity="uncommon",
    resolve=_forced_liquidation_resolve,
)


# Forced Unwinding {3} — Order. Asymmetric voltron-buster.
# rebalance v2 (2026-05-09): voltron centralization ~89.8%; the format lacks a
# detach-all answer.  Forced Unwinding strips every Derivative off opponent's
# Traders and re-stages them on opponent's Derivatives Desk (room permitting).
# The Derivatives are NOT destroyed — they're just unattached, so their
# attached_to-driven QUERY_POWER buffs stop applying immediately.  Mirrors
# Equipment-cleanup semantics already wired in finance.py.
def _forced_unwinding_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []

    # Lazy import to avoid circular-import: dark_arbitrage.py is loaded during
    # finance.py's setup (deck assembly) and finance.py imports this module.
    from src.engine.finance import (
        add_to_deriv_desk,
        get_deriv_desk,
        MAX_DERIV_DESK,
    )

    bf = state.zones.get("battlefield")
    if not bf:
        return []

    # All opposing Traders that could host a Derivative.
    opp_trader_ids: set[str] = set()
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != controller
                and CardType.FIN_TRADER in o.characteristics.types):
            opp_trader_ids.add(oid)

    if not opp_trader_ids:
        return []

    # Detach every Derivative whose host is an opposing Trader.  Re-stage on
    # the Derivative's *own controller's* Desk (= the opponent who lost the
    # voltron stack).  Skip if the Desk is full — the Derivative still
    # detaches (so the buff stops) but doesn't get re-staged.
    detached_count = 0
    for oid in list(state.objects.keys()):
        o = state.objects.get(oid)
        if o is None:
            continue
        if CardType.FIN_DERIVATIVE not in o.characteristics.types:
            continue
        host_id = getattr(o.state, "attached_to", None)
        if host_id not in opp_trader_ids:
            continue
        # Detach.
        o.state.attached_to = None
        detached_count += 1
        # Re-stage on the Derivative's controller's Desk if there's room.
        desk = get_deriv_desk(state, o.controller)
        if o.id not in desk and len(desk) < MAX_DERIV_DESK:
            try:
                add_to_deriv_desk(state, o.controller, o.id)
            except ValueError:
                pass  # Race-safe: desk was at cap; effect still detaches.

    # Effect produces no further events (state mutated in-place).  Return an
    # empty list so the resolve infrastructure sees a no-op cast that still
    # routes the spell to the graveyard.  Detached_count is implicit in state.
    _ = detached_count
    return []


FORCED_UNWINDING = make_order(
    "Forced Unwinding", "{3}",
    text=(
        "Detach all Derivatives from Traders your opponent controls. "
        "They return to that opponent's Derivatives Desk."
    ),
    rarity="uncommon",
    resolve=_forced_unwinding_resolve,
)


# Margin Squeeze {2} — Order. Conditional destroy-Trader (only voltron hosts).
# rebalance v2 (2026-05-09): cheap targeted answer to voltron — destroys a
# Trader that has at least one attached Derivative.  Mirrors Block Trade Sweep
# pricing (conditional removal at {2}; counterplay-costing memo benchmark).
# Resolve must be a no-op if no valid target exists (no random pick, since
# the answer is a *targeted* removal — cast must fail / waste mana).
def _margin_squeeze_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []

    bf = state.zones.get("battlefield")
    if not bf:
        return []

    # Helper: count Derivatives attached to a given Trader id.
    def _attached_count(host_id: str) -> int:
        return sum(
            1 for o in state.objects.values()
            if (CardType.FIN_DERIVATIVE in o.characteristics.types
                and getattr(o.state, "attached_to", None) == host_id)
        )

    # Targeted form: prefer the explicit target_id wired by finance_turn.
    target_id: str | None = event.payload.get("target_id")
    if not target_id:
        targets = event.payload.get("targets") or []
        if targets:
            first = targets[0]
            if isinstance(first, str):
                target_id = first
            elif isinstance(first, list) and first:
                target_id = first[0]

    target_obj = state.objects.get(target_id) if target_id else None
    valid = (
        target_obj is not None
        and target_obj.controller != controller
        and CardType.FIN_TRADER in target_obj.characteristics.types
        and _attached_count(target_obj.id) >= 1
    )

    # No-target fallback (AI passes []): pick the highest-attached opposing
    # Trader so the AI can still cast it productively.  This mirrors
    # Forced Liquidation's auto-pick behaviour.
    if not valid:
        candidates = [
            o for oid in getattr(bf, "objects", [])
            if (o := state.objects.get(oid))
            and o.controller != controller
            and CardType.FIN_TRADER in o.characteristics.types
            and _attached_count(o.id) >= 1
        ]
        if not candidates:
            # Cast fails: no valid voltron host on opponent's board.
            return []
        target_obj = max(candidates, key=lambda o: _attached_count(o.id))

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": target_obj.id, "reason": "margin_squeeze"},
        source=event.payload.get("source_id", ""),
    )]


MARGIN_SQUEEZE = make_order(
    "Margin Squeeze", "{2}",
    text="Destroy target Trader with one or more attached Derivatives.",
    rarity="uncommon",
    resolve=_margin_squeeze_resolve,
)


# Crossed Market {2} — Dark Pool. When this triggers, target Trader cannot attack OR block this turn.
# rebalance: effect upgrade — was can't-block-only; now can't-attack-or-block (can't-block useless when
# the trigger fires on opponent's TS since opponent is attacking, not defending).
#
# Phase 4 migration: humans pick which Trader is locked out; AI keeps the old
# "highest-toughness threat" pick via ``heuristic_pick``.
def _crossed_market_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        # bug #29: the global system trigger fires FIN_MARKET_EVENT on the
        # next active player's PHASE_START(trading_session) — which for a
        # freshly staged DP is the OPPONENT'S TS. The "can't attack" half of
        # the new effect IS useful on opp's TS, but "can't block" only matters
        # on controller's TS, so we still defer-when-opponent for full impact.
        active_player = event.controller or event.payload.get("controller")
        if active_player and active_player != obj.controller:
            set_dark_pool(state, obj.id)
            return []
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1

        bf = state.zones.get("battlefield")
        if not bf:
            return []
        opp_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller != obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        if not opp_traders:
            return []

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        source_id = obj.id
        controller = obj.controller

        options = [
            {
                "id": t.id,
                "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
            }
            for t in opp_traders
        ]

        best = max(opp_traders, key=lambda o: o.characteristics.toughness or 0)

        def _resolve_handler(choice, selected, st):
            tid = selected[0] if selected else best.id
            if isinstance(tid, dict):
                tid = tid.get("id") or tid.get("target_id")
            if not tid:
                tid = best.id
            # Mark as can't-attack AND can't-block this turn (mutate state in place,
            # since this is a marker rather than a pipeline event).
            st.turn_data[f"fin_cant_block_{tid}"] = True
            st.turn_data[f"fin_cant_attack_{tid}"] = True
            return []

        return create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=controller,
            prompt="Choose an opposing Trader; it cannot attack or block this turn",
            options=options,
            source_id=source_id,
            handler=_resolve_handler,
            heuristic_pick=[best.id],
        )

    return dark_pool_setup(obj, state, dark_effect)

CROSSED_MARKET = make_order(
    "Crossed Market", "{2}",
    text="Dark Pool. When this triggers, target Trader cannot attack or block this turn.",
    dark_pool=True,
    setup_interceptors=_crossed_market_setup,
)


# Hidden Aggression {2} — Dark Pool. When this triggers, target Trader you control gets +4/+0 until Market Close.
#
# Phase 4 migration: humans pick which friendly Trader gets the buff; AI keeps
# the old "highest-power friendly" pick via ``heuristic_pick``.
def _hidden_aggression_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1

        bf = state.zones.get("battlefield")
        if not bf:
            return []
        my_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller == obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        if not my_traders:
            return []

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        source_id = obj.id
        controller = obj.controller

        options = [
            {
                "id": t.id,
                "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
            }
            for t in my_traders
        ]

        best = max(my_traders, key=lambda o: o.characteristics.power or 0)

        def _resolve_handler(choice, selected, st):
            tid = selected[0] if selected else best.id
            if isinstance(tid, dict):
                tid = tid.get("id") or tid.get("target_id")
            if not tid:
                tid = best.id
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={"object_id": tid, "power_mod": 2, "toughness_mod": 0, "duration": "end_of_turn"},  # cyc3: +4→+2
                source=source_id,
                controller=controller,
            )]

        return create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=controller,
            prompt="Choose one of your Traders to give +2/+0",
            options=options,
            source_id=source_id,
            handler=_resolve_handler,
            heuristic_pick=[best.id],
        )

    return dark_pool_setup(obj, state, dark_effect)

HIDDEN_AGGRESSION = make_order(
    "Hidden Aggression", "{2}",
    text="Dark Pool. When this triggers, target Trader you control gets +2/+0 until Market Close.",  # bug #12: text was +4/+0 but code applies +2/+0 (cyc3 nerf)
    dark_pool=True,
    setup_interceptors=_hidden_aggression_setup,
)


# Lit-Market Decoy {1} — Draw a card. You may play a Dark Pool Order from your hand this turn without paying its cost.
def _lit_market_decoy_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    # Grant permission to play one Dark Pool Order for free this turn
    state.turn_data[f"fin_free_dark_pool_{controller}"] = True
    return [Event(
        type=EventType.DRAW,
        payload={"player": controller, "count": 1},
        source=event.source,
    )]

LIT_MARKET_DECOY = make_order(
    "Lit-Market Decoy", "{1}",
    text="Draw a card. You may play a Dark Pool Order from your hand this turn without paying its cost.",
    resolve=_lit_market_decoy_resolve,
)


# Internalization Order {3} — Dark Pool. When this triggers, deal 3 damage to target Trader.
#
# Phase 4 migration: humans split the 3 damage across opposing Traders via
# divide_allocation; AI keeps the old "all-to-toughest" pick (preserves the
# original "always kills it dead" heuristic).
def _internalization_order_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1

        bf = state.zones.get("battlefield")
        if not bf:
            return []
        opp_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller != obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        if not opp_traders:
            return []

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        total_amount = 3  # printed: "deal 3 damage"
        source_id = obj.id
        controller = obj.controller

        options = [
            {
                "id": t.id,
                "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "name": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
                "type": "Trader",
                "life": (t.characteristics.toughness or 0) - int(getattr(t.state, "damage", 0) or 0),
                "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0}",
            }
            for t in opp_traders
        ]

        # AI heuristic: preserve old "all-to-highest-toughness" pick (the most
        # likely to actually survive the damage and need a finisher).
        target = max(opp_traders, key=lambda o: o.characteristics.toughness or 0)
        heuristic = [{"target_id": target.id, "amount": total_amount}]

        def _resolve_handler(choice, selected, st):
            allocations: dict[str, int] = selected if isinstance(selected, dict) else {}
            if not allocations and isinstance(selected, list):
                for item in selected:
                    if isinstance(item, dict):
                        tid = item.get("target_id") or item.get("id")
                        if tid:
                            allocations[tid] = int(item.get("amount", 0) or 0)
                    elif isinstance(item, tuple) and len(item) == 2:
                        allocations[item[0]] = int(item[1] or 0)
            if not allocations:
                allocations = {target.id: total_amount}
            return [
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": tid, "amount": int(amt or 0), "source": source_id},
                    source=source_id,
                    controller=controller,
                )
                for tid, amt in allocations.items()
                if amt and int(amt) > 0
            ]

        return create_choice_and_resolve(
            state,
            choice_type="divide_allocation",
            player_id=controller,
            prompt="Distribute Internalization Order damage among opposing Traders",
            options=options,
            source_id=source_id,
            min_choices=1,
            max_choices=len(options),
            handler=_resolve_handler,
            heuristic_pick=heuristic,
            total_amount=total_amount,
            effect_type="damage",
        )

    return dark_pool_setup(obj, state, dark_effect)

INTERNALIZATION_ORDER = make_order(
    "Internalization Order", "{3}",
    text="Dark Pool. When this triggers, deal 3 damage to target Trader.",
    dark_pool=True,
    rarity="uncommon",
    setup_interceptors=_internalization_order_setup,
)


# Payment for Order Flow {2} — Dark Pool. When this triggers, gain 3 Liquidity this turn.
def _payment_for_order_flow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        # bug #29: PFOF grants Liquidity "this turn", which is only useful on
        # the controller's TS (so they can spend it). Firing on the opponent's
        # TS dumps Liquidity at a player who can't cast — wasted ramp. Defer
        # by re-staging when the active player is not the controller.
        active_player = event.controller or event.payload.get("controller")
        if active_player and active_player != obj.controller:
            set_dark_pool(state, obj.id)
            return []
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals_available + 1,  # cyc3: 3→1 Liquidity (free ramp was too strong)
                player.mana_crystals,
            )
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return []
    return dark_pool_setup(obj, state, dark_effect)

PAYMENT_FOR_ORDER_FLOW = make_order(
    "Payment for Order Flow", "{2}",
    text="Dark Pool. When this triggers, gain 3 Liquidity this turn.",
    dark_pool=True,
    setup_interceptors=_payment_for_order_flow_setup,
)


# Pre-Positioned Strike {3} — Dark Pool. When this triggers, deal 2 damage to target player's Capital Reserve directly.
def _pre_positioned_strike_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp_id in _get_opponent_ids(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": opp_id, "amount": -2},
                source=obj.id,
            ))
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
    return dark_pool_setup(obj, state, dark_effect)

PRE_POSITIONED_STRIKE = make_order(
    "Pre-Positioned Strike", "{3}",
    text="Dark Pool. When this triggers, deal 2 damage to target player's Capital Reserve directly.",
    dark_pool=True,
    rarity="uncommon",
    setup_interceptors=_pre_positioned_strike_setup,
)


# =============================================================================
# STRATEGIES — 5 cards
# =============================================================================

# Liquidity Event {4} — Gain Liquidity equal to the number of Dark Pool Orders you have played this game (max 5).
def _liquidity_event_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    count = min(5, _count_dark_pool_played(state, controller))
    if count <= 0:
        return []
    player = state.players.get(controller)
    if player:
        player.mana_crystals_available = min(
            player.mana_crystals_available + count,
            player.mana_crystals,
        )
    return []

LIQUIDITY_EVENT = make_strategy(
    "Liquidity Event", "{4}",
    text="Gain Liquidity equal to the number of Dark Pool Orders you have played this game (maximum 5).",
    rarity="uncommon",
    resolve=_liquidity_event_resolve,
)


# Information Asymmetry {3} — Gain control of the opponent's currently staged Dark Pool Order.
# rebalance: dead-card repair — added "draw 2 cards" floor when opponent has no DP slot
# so the card is never a complete brick.
def _information_asymmetry_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    dp_id = get_dark_pool(state)
    dp_obj = state.objects.get(dp_id) if dp_id else None
    # If opponent has a staged DP Order, take control of it.
    if dp_obj is not None and dp_obj.controller != controller:
        dp_obj.controller = controller
        return []
    # Otherwise (no DP slot, or it's our own), draw 2 cards as a floor effect.
    return [Event(
        type=EventType.DRAW,
        payload={"player": controller, "count": 2},
        source=event.payload.get("source_id", ""),
    )]

INFORMATION_ASYMMETRY = make_strategy(
    "Information Asymmetry", "{3}",
    text="Gain control of the opponent's currently staged Dark Pool Order. If they have no Dark Pool slot, draw 2 cards instead.",
    rarity="rare",
    resolve=_information_asymmetry_resolve,
)


# Dark Liquidity Surge {4} — Gain 2 Liquidity for each Dark Pool Order that has triggered this game (max 6).
def _dark_liquidity_surge_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    count = min(6, _count_dark_pool_triggered(state, controller) * 2)
    if count <= 0:
        return []
    player = state.players.get(controller)
    if player:
        player.mana_crystals_available = min(
            player.mana_crystals_available + count,
            player.mana_crystals,
        )
    return []

DARK_LIQUIDITY_SURGE = make_strategy(
    "Dark Liquidity Surge", "{4}",
    text="Gain 2 Liquidity for each Dark Pool Order that has triggered this game (maximum 6).",
    rarity="uncommon",
    resolve=_dark_liquidity_surge_resolve,
)


# Capital Structure Arb {5} — Place 3 Leverage counters on target Trader you control.
# It also gets Arbitrage 2 until Market Close.
#
# Phase 4 migration: humans pick the Trader; AI keeps the old "highest
# (power+leverage)" pick via ``heuristic_pick``.
def _capital_structure_arb_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    my_traders = [
        o for oid in bf.objects
        if (o := state.objects.get(oid))
        and o.controller == controller
        and CardType.FIN_TRADER in o.characteristics.types
    ]
    if not my_traders:
        return []

    from src.engine.pending_choice_helpers import create_choice_and_resolve

    source_id = event.payload.get("source_id", "") or event.source or ""

    options = [
        {
            "id": t.id,
            "label": getattr(t.card_def, "name", t.id) if getattr(t, "card_def", None) else t.id,
            "description": f"P/T {t.characteristics.power or 0}/{t.characteristics.toughness or 0} · Lev {t.state.counters.get('leverage', 0)}",
        }
        for t in my_traders
    ]

    # AI heuristic: preserve old "highest (power+leverage)" pick.
    best = max(
        my_traders,
        key=lambda o: (o.characteristics.power or 0) + o.state.counters.get("leverage", 0),
    )

    def _resolve_handler(choice, selected, st):
        tid = selected[0] if selected else best.id
        if isinstance(tid, dict):
            tid = tid.get("id") or tid.get("target_id")
        if not tid:
            tid = best.id
        target_obj = st.objects.get(tid)
        if target_obj is None:
            target_obj = best
            tid = best.id
        target_obj.state.counters["leverage"] = target_obj.state.counters.get("leverage", 0) + 3
        # Grant Arbitrage 2 until Market Close — stored in turn_data as a temporary buff
        st.turn_data[f"fin_arb_buff_{tid}"] = 2
        return []

    return create_choice_and_resolve(
        state,
        choice_type="target",
        player_id=controller,
        prompt="Choose one of your Traders to place 3 Leverage counters on (and gain Arbitrage 2)",
        options=options,
        source_id=source_id,
        handler=_resolve_handler,
        heuristic_pick=[best.id],
    )

CAPITAL_STRUCTURE_ARB = make_strategy(
    "Capital Structure Arb", "{5}",
    text="Place 3 Leverage counters on target Trader you control. It also gets Arbitrage 2 until Market Close.",
    rarity="rare",
    resolve=_capital_structure_arb_resolve,
)


# Spoofing Campaign {3} — Destroy all Traders with Aggression 2 or less.
def _spoofing_campaign_resolve(event: Event, state: GameState) -> list[Event]:
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    events = []
    for oid in list(bf.objects):
        o = state.objects.get(oid)
        if o is None:
            continue
        if CardType.FIN_TRADER not in o.characteristics.types:
            continue
        if (o.characteristics.power or 0) <= 2:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": oid, "reason": "spoofing_campaign"},
                source=event.source,
            ))
    return events

SPOOFING_CAMPAIGN = make_strategy(
    "Spoofing Campaign", "{3}",
    text="Destroy all Traders with Aggression 2 or less.",
    rarity="uncommon",
    resolve=_spoofing_campaign_resolve,
)


# =============================================================================
# STRUCTURES — 2 cards
# =============================================================================

# Principal Trading Desk {4} — At the start of your Pre-Market, if the Dark Pool slot is empty, draw a card.
def _principal_trading_desk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "pre_market"
            and event.payload.get("player") == obj.controller
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        if get_dark_pool(state) is None:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "count": 1},
                    source=obj.id,
                )],
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]

PRINCIPAL_TRADING_DESK = make_structure(
    "Principal Trading Desk", "{4}",
    text="At the start of your Pre-Market, if the Dark Pool slot is empty, draw a card.",
    rarity="uncommon",
    setup_interceptors=_principal_trading_desk_setup,
)


# Dark Venue Console {4} — At the start of your Trading Session, you may pay {1} to trigger the staged Dark Pool Order immediately.
def _dark_venue_console_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "trading_session"
            and event.payload.get("player") == obj.controller
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        dp_id = get_dark_pool(state)
        if dp_id is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        player = state.players.get(obj.controller)
        if player and player.mana_crystals_available >= 1:
            player.mana_crystals_available -= 1
            set_dark_pool(state, None)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.FIN_MARKET_EVENT,
                    payload={"obj_id": dp_id},
                    source=obj.id,
                )],
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]

DARK_VENUE_CONSOLE = make_structure(
    "Dark Venue Console", "{4}",
    text="At the start of your Trading Session, you may pay {1} to trigger the staged Dark Pool Order immediately.",
    rarity="rare",
    setup_interceptors=_dark_venue_console_setup,
)


# =============================================================================
# ASSETS — 3 cards
# =============================================================================

# Dark Flow Engine {3} — Static: Dark Pool Orders you control cost {1} less to stage.
def _dark_flow_engine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_COST:
            return False
        card_id = event.payload.get("object_id") or event.payload.get("card_id")
        if not card_id:
            return False
        card_obj = state.objects.get(card_id)
        if not card_obj or card_obj.controller != obj.controller:
            return False
        cd = card_obj.card_def
        # bug #28: attribute is `dark_pool`, not `_dark_pool`.
        return cd is not None and getattr(cd, "dark_pool", False)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        # bug #28: cost_query reads transformed_event.payload['reduction'] (REDUCTION_KEY).
        # Previous handler mutated payload['cost'] and returned PASS — never read.
        new_event = event.copy()
        new_event.payload["reduction"] = new_event.payload.get("reduction", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        # bug #28: priority must be QUERY for cost_query.get_effective_mana_cost to iterate it.
        priority=InterceptorPriority.QUERY,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]

DARK_FLOW_ENGINE = make_asset(
    "Dark Flow Engine", "{3}",
    text="Static: Dark Pool Orders you control cost {1} less to stage.",
    rarity="uncommon",
    setup_interceptors=_dark_flow_engine_setup,
)


# Order Flow Analytics {3} — At the start of your Pre-Market, if the Dark Pool slot is occupied, gain 2 Liquidity this turn.
def _order_flow_analytics_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "pre_market"
            and event.payload.get("player") == obj.controller
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        if _dark_pool_is_occupied(state):
            player = state.players.get(obj.controller)
            if player:
                player.mana_crystals_available = min(
                    player.mana_crystals_available + 2,
                    player.mana_crystals,
                )
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]

ORDER_FLOW_ANALYTICS = make_asset(
    "Order Flow Analytics", "{3}",
    text="At the start of your Pre-Market, if the Dark Pool slot is occupied, gain 2 Liquidity this turn.",
    setup_interceptors=_order_flow_analytics_setup,
)


# Off-Exchange Yield {4} — At the start of your Market Close, if a Dark Pool Order triggered this turn, gain 3 Capital Reserve.
def _off_exchange_yield_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "market_close"
            and event.payload.get("player") == obj.controller
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        if state.turn_data.get(f"fin_dp_triggered_this_turn_{obj.controller}", False):
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.LIFE_CHANGE,
                    payload={"player": obj.controller, "amount": 3},
                    source=obj.id,
                )],
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    # Also listen for FIN_MARKET_EVENT to set the "triggered this turn" flag
    def _dp_trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.FIN_MARKET_EVENT:
            return False
        dp_id = event.payload.get("obj_id")
        if not dp_id:
            return False
        dp_obj = state.objects.get(dp_id)
        return dp_obj is not None and dp_obj.controller == obj.controller

    def _dp_trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if me and me.zone == ZoneType.BATTLEFIELD:
            state.turn_data[f"fin_dp_triggered_this_turn_{obj.controller}"] = True
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_filter,
            handler=_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_dp_trigger_filter,
            handler=_dp_trigger_handler,
            duration="while_on_battlefield",
        ),
    ]

OFF_EXCHANGE_YIELD = make_asset(
    "Off-Exchange Yield", "{4}",
    text="At the start of your Market Close, if a Dark Pool Order triggered this turn, gain 3 Capital Reserve.",
    rarity="uncommon",
    setup_interceptors=_off_exchange_yield_setup,
)


# =============================================================================
# DERIVATIVES — 3 cards
# =============================================================================

# Rho Leverage Amplifier {3} — Attach to a Trader: it gets +1/+1 for each Dark Pool Order that has triggered this game (max +4/+4).
def _rho_leverage_amplifier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _power_filter(event: Event, state: GameState) -> bool:
        host_id = state.turn_data.get(f"fin_deriv_host_{obj.id}")
        return (
            event.type == EventType.QUERY_POWER
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def _power_handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        bonus = min(4, _count_dark_pool_triggered(state, obj.controller))
        if bonus <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        # priority class: queries.get_power reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + bonus
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    def _tough_filter(event: Event, state: GameState) -> bool:
        host_id = state.turn_data.get(f"fin_deriv_host_{obj.id}")
        return (
            event.type == EventType.QUERY_TOUGHNESS
            and host_id is not None
            and event.payload.get("object_id") == host_id
        )

    def _tough_handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        bonus = min(4, _count_dark_pool_triggered(state, obj.controller))
        if bonus <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        # priority class: queries.get_toughness reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + bonus
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            # priority class: must be QUERY for queries.get_power to iterate it.
            priority=InterceptorPriority.QUERY,
            filter=_power_filter,
            handler=_power_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            # priority class: must be QUERY for queries.get_toughness to iterate it.
            priority=InterceptorPriority.QUERY,
            filter=_tough_filter,
            handler=_tough_handler,
            duration="while_on_battlefield",
        ),
    ]

RHO_LEVERAGE_AMPLIFIER = make_derivative(
    "Rho Leverage Amplifier", "{3}",
    text="Attach to a Trader: it gets +1/+1 for each Dark Pool Order that has triggered this game (maximum +4/+4).",
    rarity="uncommon",
    setup_interceptors=_rho_leverage_amplifier_setup,
)


# Shadow Protocol Module {2} — Attach to a Trader: Dark Pool Orders you stage while this Trader is on the field cost {1} less.
def _shadow_protocol_module_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_COST:
            return False
        card_id = event.payload.get("object_id") or event.payload.get("card_id")
        if not card_id:
            return False
        card_obj = state.objects.get(card_id)
        if not card_obj or card_obj.controller != obj.controller:
            return False
        cd = card_obj.card_def
        # priority class: attribute is `dark_pool`, not `_dark_pool`.
        return cd is not None and getattr(cd, "dark_pool", False)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Check host is on the battlefield
        host_id = me.state.attached_to
        if host_id:
            host = state.objects.get(host_id)
            if not host or host.zone != ZoneType.BATTLEFIELD:
                return InterceptorResult(action=InterceptorAction.PASS)
        # priority class: cost_query reads transformed_event.payload['reduction'].
        new_event = event.copy()
        new_event.payload["reduction"] = new_event.payload.get("reduction", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        # priority class: must be QUERY for cost_query to iterate it.
        priority=InterceptorPriority.QUERY,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )]

SHADOW_PROTOCOL_MODULE = make_derivative(
    "Shadow Protocol Module", "{2}",
    text="Attach to a Trader: Dark Pool Orders you stage while this Trader is on the field cost {1} less.",
    setup_interceptors=_shadow_protocol_module_setup,
)


# Off-Exchange Boost Rig {3} — Attach to a Trader: when a Dark Pool Order triggers, this Trader gets +2/+0 until Market Close.
def _off_exchange_boost_rig_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _dp_trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.FIN_MARKET_EVENT:
            return False
        dp_id = event.payload.get("obj_id")
        if not dp_id:
            return False
        dp_obj = state.objects.get(dp_id)
        return dp_obj is not None and dp_obj.controller == obj.controller

    def _dp_trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Find the host Trader this derivative is attached to
        host_id = me.state.attached_to
        if not host_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        host = state.objects.get(host_id)
        if not host or host.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={"object_id": host_id, "power_mod": 2, "toughness_mod": 0, "duration": "end_of_turn"},
                source=obj.id,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_dp_trigger_filter,
        handler=_dp_trigger_handler,
        duration="while_on_battlefield",
    )]

OFF_EXCHANGE_BOOST_RIG = make_derivative(
    "Off-Exchange Boost Rig", "{3}",
    text="Attach to a Trader: when a Dark Pool Order triggers, this Trader gets +2/+0 until Market Close.",
    rarity="uncommon",
    setup_interceptors=_off_exchange_boost_rig_setup,
)


# =============================================================================
# NEUTRAL — 3 cards
# =============================================================================

# Market Maker {2} 2/2 — When this enters, gain 1 Liquidity this turn.
def _market_maker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals_available + 1,
                player.mana_crystals,
            )
        return []
    return [make_etb_trigger(obj, etb_fn)]

MARKET_MAKER = make_trader(
    "Market Maker", "{2}", 2, 2,
    text="When this enters, gain 1 Liquidity this turn.",
    setup_interceptors=_market_maker_setup,
)


# Capital Injection {3} — Strategy. Gain 5 Capital Reserve.
def _capital_injection_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    player = state.players.get(controller)
    if player:
        max_life = getattr(player, "max_life", 30)
        player.life = min(player.life + 5, max_life)
    return []

CAPITAL_INJECTION = make_strategy(
    "Capital Injection", "{3}",
    text="Gain 5 Capital Reserve.",
    resolve=_capital_injection_resolve,
)


# Book Building {2} — Order. Draw 2 cards. Discard 1 card.
def _book_building_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    return [
        Event(type=EventType.DRAW, payload={"player": controller, "count": 2}, source=event.source),
        Event(type=EventType.DISCARD, payload={"player": controller, "count": 1}, source=event.source),
    ]

BOOK_BUILDING = make_order(
    "Book Building", "{2}",
    text="Draw 2 cards. Discard 1 card.",
    resolve=_book_building_resolve,
)


# =============================================================================
# SPICE PASS v1 — cost-cards skill pilot (2026-05-09)
# =============================================================================
# Three new spice cards (2 DA + 1 cross-archetype Neutral). DA is over-
# centralized at 83.3% WR per polish punchlist — spice for DA adds
# *value-without-centralization* (DP-stage counter scaling) and a tempo
# AOE Order that doesn't push the wide-DP combo. Neutral adds a multi-
# archetype lord that supports any archetype's spice-pass synergies.

# --- Phantom Pool Operator {4} 3/3 Leverage 2 (Mythic) ---
# Patterns: 11 (build-around — needs DP fans), 3 (snowball).
# Heuristic walk:
#   vanilla 3/3 = {3} (HS curve, P+T=6 ~ {3.5})
#   Leverage 2 = +1.0
#   Alpha Strike on power-3 ×0.7 alone-condition = +0.7
#   recurring +1/+1 per DP staged (avg 2-3 per game) = +1.5
#   total {6.7} → push to {4} as build-around mythic (×0.6 build-around
#   discount: needs DP fans to be on-curve).
def _phantom_pool_operator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    leverage_etb = _add_leverage_etb(obj, 2)
    leverage_power = _make_leverage_power_query(obj)
    alpha_atk = _make_alpha_strike(obj)

    def dp_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.FIN_PLAY_CARD:
            return False
        if event.payload.get("controller") != obj.controller:
            return False
        played_id = event.payload.get("object_id") or event.payload.get("card_id")
        if not played_id:
            return False
        played = state.objects.get(played_id)
        if played is None or played.card_def is None:
            return False
        return bool(getattr(played.card_def, "_dark_pool", False)
                    or getattr(played.card_def, "dark_pool", False))

    def dp_handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if me is None or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    "object_id": obj.id,
                    "counter_type": "+1/+1",
                    "amount": 1,
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    dp_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=dp_filter,
        handler=dp_handler,
        duration="while_on_battlefield",
    )
    dp_icp.is_triggered_ability = True
    dp_icp.effect_fn = lambda ev, st: [Event(
        type=EventType.COUNTER_ADDED,
        payload={"object_id": obj.id, "counter_type": "+1/+1", "amount": 1},
        source=obj.id,
    )]
    return [leverage_etb, leverage_power, alpha_atk, dp_icp]


PHANTOM_POOL_OPERATOR = make_trader(
    "Phantom Pool Operator", "{4}", 3, 3,
    text=("Leverage 2. Alpha Strike. Whenever you stage a Dark Pool Order, "
          "place a +1/+1 counter on this Trader."),
    rarity="mythic",
    setup_interceptors=_phantom_pool_operator_setup,
)


# --- Coordinated Block Strategy {2} Order Dark Pool (Rare) ---
# Patterns: 4 (compression — small AoE + cantrip).
# Heuristic walk:
#   1 dmg AoE to opp Traders (~1.5 dmg average board) = +1.5
#   draw 1 = +1.0
#   Dark Pool premium (hostile) = +0.5
#   total {3.0} → push to {2} as DA spice (build-around DA timing window).
def _coordinated_block_strategy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        bf = state.zones.get("battlefield")
        if bf is not None:
            for oid in list(bf.objects):
                o = state.objects.get(oid)
                if (o is None
                        or o.controller == obj.controller
                        or CardType.FIN_TRADER not in o.characteristics.types):
                    continue
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={
                        "target": oid,
                        "amount": 1,
                        "source": obj.id,
                        "is_finance": True,
                    },
                    source=obj.id,
                ))
        events.append(Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1},
            source=obj.id,
        ))
        # increment the DP-triggered counter so other DA cards (Off-Exchange
        # Yield, Rho Leverage Amplifier, Dark Liquidity Surge) see this fire.
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
    return dark_pool_setup(obj, state, dark_effect)


COORDINATED_BLOCK_STRATEGY = make_order(
    "Coordinated Block Strategy", "{2}",
    text=("Dark Pool. When this triggers, deal 1 damage to each of opponent's "
          "Traders. Draw a card."),
    rarity="rare",
    dark_pool=True,
    setup_interceptors=_coordinated_block_strategy_setup,
)


# --- Floor Captain Caro {4} 3/4 Neutral Legendary Trader (Mythic) ---
# Patterns: 4 (compression — lord + ramp on a body), 1 (efficiency).
# Heuristic walk:
#   vanilla 3/4 = {3} (HS curve, P+T=7)
#   ETB lord +1/+0 to all other Traders (avg 2-3 affected, one-shot) = +0.7
#   ETB +1 Liquidity = +0.5
#   legendary tax (rule of one in deckbuilding) = -0.5
#   total {3.7} → fair {4} (round up, legendary single-copy variance).
def _floor_captain_caro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        bf = state.zones.get("battlefield")
        if bf is not None:
            for oid in list(bf.objects):
                if oid == obj.id:
                    continue
                o = state.objects.get(oid)
                if (o is None
                        or o.controller != obj.controller
                        or CardType.FIN_TRADER not in o.characteristics.types):
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
                ))
        # gain 1 Liquidity this turn.
        player = state.players.get(obj.controller)
        if player is not None:
            player.mana_crystals_available = min(
                player.mana_crystals_available + 1,
                player.mana_crystals,
            )
        return events
    return [make_etb_trigger(obj, etb_fn)]


FLOOR_CAPTAIN_CARO = make_trader(
    "Floor Captain Caro", "{4}", 3, 4,
    text=("Legendary. When this enters, each other Trader you control gets "
          "+1/+0 until Market Close. When this enters, gain 1 Liquidity this "
          "turn."),
    rarity="mythic",
    setup_interceptors=_floor_captain_caro_setup,
)


# =============================================================================
# Export
# =============================================================================

DARK_ARBITRAGE_CARDS: dict[str, CardDefinition] = {
    # --- TRADERS (14) ---
    "Hidden Accumulator": HIDDEN_ACCUMULATOR,
    "Stealth Position Builder": STEALTH_POSITION_BUILDER,
    "Off-Exchange Operative": OFF_EXCHANGE_OPERATIVE,
    "Dark Flow Aggregator": DARK_FLOW_AGGREGATOR,
    "Institutional Block Trader": INSTITUTIONAL_BLOCK_TRADER,
    "Principal Crossings Desk": PRINCIPAL_CROSSINGS_DESK,
    "Dark Pool Architect": DARK_POOL_ARCHITECT,
    "Dark Pool Aggressor": DARK_POOL_AGGRESSOR,
    "OTC Behemoth": OTC_BEHEMOTH,
    "Internalized Flow Monster": INTERNALIZED_FLOW_MONSTER,
    "Shadow Accumulation Desk": SHADOW_ACCUMULATION_DESK,
    "Dark Inventory Position": DARK_INVENTORY_POSITION,
    "Crossing Network Pilot": CROSSING_NETWORK_PILOT,
    "Off-Exchange Finisher": OFF_EXCHANGE_FINISHER,
    # --- ORDERS (12) ---  (rebalance v2: +2 — added Forced Unwinding, Margin Squeeze)
    "Iceberg Order": ICEBERG_ORDER,
    "Off-Exchange Position": OFF_EXCHANGE_POSITION,
    "Block Trade Sweep": BLOCK_TRADE_SWEEP,
    "Forced Liquidation": FORCED_LIQUIDATION,  # rebalance: NEW {3} destroy-target-Trader
    "Forced Unwinding": FORCED_UNWINDING,  # rebalance v2: detach-all-opp Derivatives
    "Margin Squeeze": MARGIN_SQUEEZE,  # rebalance v2: {2} destroy-Trader-with-attached
    "Crossed Market": CROSSED_MARKET,
    "Hidden Aggression": HIDDEN_AGGRESSION,
    "Lit-Market Decoy": LIT_MARKET_DECOY,
    "Internalization Order": INTERNALIZATION_ORDER,
    "Payment for Order Flow": PAYMENT_FOR_ORDER_FLOW,
    "Pre-Positioned Strike": PRE_POSITIONED_STRIKE,
    # --- STRATEGIES (5) ---
    "Liquidity Event": LIQUIDITY_EVENT,
    "Information Asymmetry": INFORMATION_ASYMMETRY,
    "Dark Liquidity Surge": DARK_LIQUIDITY_SURGE,
    "Capital Structure Arb": CAPITAL_STRUCTURE_ARB,
    "Spoofing Campaign": SPOOFING_CAMPAIGN,
    # --- STRUCTURES (2) ---
    "Principal Trading Desk": PRINCIPAL_TRADING_DESK,
    "Dark Venue Console": DARK_VENUE_CONSOLE,
    # --- ASSETS (3) ---
    "Dark Flow Engine": DARK_FLOW_ENGINE,
    "Order Flow Analytics": ORDER_FLOW_ANALYTICS,
    "Off-Exchange Yield": OFF_EXCHANGE_YIELD,
    # --- DERIVATIVES (3) ---
    "Rho Leverage Amplifier": RHO_LEVERAGE_AMPLIFIER,
    "Shadow Protocol Module": SHADOW_PROTOCOL_MODULE,
    "Off-Exchange Boost Rig": OFF_EXCHANGE_BOOST_RIG,
    # --- NEUTRAL (3) ---
    "Market Maker": MARKET_MAKER,
    "Capital Injection": CAPITAL_INJECTION,
    "Book Building": BOOK_BUILDING,
    # Spice pass v1 (cost-cards skill pilot, 2026-05-09): +3 cards
    # (2 DA + 1 Neutral cross-archetype legendary)
    "Phantom Pool Operator": PHANTOM_POOL_OPERATOR,
    "Coordinated Block Strategy": COORDINATED_BLOCK_STRATEGY,
    "Floor Captain Caro": FLOOR_CAPTAIN_CARO,
}
