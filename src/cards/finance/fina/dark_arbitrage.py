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
                payload={"object_id": obj.id, "power_mod": bonus, "toughness_mod": 0, "duration": "end_of_turn"},
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
                payload={"object_id": obj.id, "power_mod": bonus, "toughness_mod": 0, "duration": "end_of_turn"},
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
    "Off-Exchange Operative", "{3}", 3, 3,
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
def _crossing_network_pilot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def atk_fn(event: Event, state: GameState) -> list[Event]:
        # Target the weakest opposing Trader
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        opp_traders = [
            state.objects.get(oid) for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller != obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        opp_traders = [o for o in opp_traders if o is not None]
        if not opp_traders:
            return []
        target = min(opp_traders, key=lambda o: o.characteristics.toughness or 0)
        return [Event(
            type=EventType.DAMAGE,
            payload={"target": target.id, "amount": 1, "source": obj.id},
            source=obj.id,
        )]
    return [
        _add_leverage_etb(obj, 2),
        _make_leverage_power_query(obj),
        make_attack_trigger(obj, atk_fn),
    ]

CROSSING_NETWORK_PILOT = make_trader(
    "Crossing Network Pilot", "{4}", 3, 3,  # balanced: power 4 → 3 (4+ power FIN_TRADER nerf)
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
def _iceberg_order_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        events = []
        if bf:
            opp_traders = [
                o for oid in bf.objects
                if (o := state.objects.get(oid))
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types
            ]
            if opp_traders:
                target = min(opp_traders, key=lambda o: o.characteristics.toughness or 0)
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={"target": target.id, "amount": 1, "source": obj.id},
                    source=obj.id,
                ))
        events.append(Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1},
            source=obj.id,
        ))
        # Track trigger count
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
    return dark_pool_setup(obj, state, dark_effect)

ICEBERG_ORDER = make_order(
    "Iceberg Order", "{1}",
    text="Dark Pool. When this triggers, deal 1 damage to target Trader and draw a card.",
    dark_pool=True,
    setup_interceptors=_iceberg_order_setup,
)


# Off-Exchange Position {2} — Dark Pool. When this triggers, target Trader gets -3/-0 until Market Close.
def _off_exchange_position_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        events = []
        if bf:
            opp_traders = [
                o for oid in bf.objects
                if (o := state.objects.get(oid))
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types
            ]
            if opp_traders:
                # Pick the highest-power threat
                target = max(opp_traders, key=lambda o: o.characteristics.power or 0)
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={"object_id": target.id, "power_mod": -3, "toughness_mod": 0, "duration": "end_of_turn"},
                    source=obj.id,
                ))
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
    return dark_pool_setup(obj, state, dark_effect)

OFF_EXCHANGE_POSITION = make_order(
    "Off-Exchange Position", "{2}",
    text="Dark Pool. Requires a populated Dark Pool slot to cast. When this triggers, target Trader gets -3/-0 until Market Close.",  # bug #13: clarify prerequisite
    dark_pool=True,
    dark_pool_consumer=True,  # bug #13: refuse cast without DP slot already populated
    setup_interceptors=_off_exchange_position_setup,
)


# Block Trade Sweep {3} — Dark Pool. When this triggers, destroy target Trader with Defense Rating 3 or less.
def _block_trade_sweep_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        events = []
        if bf:
            small_traders = [
                o for oid in bf.objects
                if (o := state.objects.get(oid))
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types
                and (o.characteristics.toughness or 0) <= 3
            ]
            if small_traders:
                target = min(small_traders, key=lambda o: o.characteristics.toughness or 0)
                events.append(Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": target.id, "reason": "block_trade_sweep"},
                    source=obj.id,
                ))
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
    return dark_pool_setup(obj, state, dark_effect)

BLOCK_TRADE_SWEEP = make_order(
    "Block Trade Sweep", "{3}",
    text="Dark Pool. When this triggers, destroy target Trader with Defense Rating 3 or less.",
    dark_pool=True,
    rarity="uncommon",
    setup_interceptors=_block_trade_sweep_setup,
)


# Crossed Market {2} — Dark Pool. When this triggers, target Trader cannot block this turn.
def _crossed_market_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        events = []
        if bf:
            opp_traders = [
                o for oid in bf.objects
                if (o := state.objects.get(oid))
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types
            ]
            if opp_traders:
                target = max(opp_traders, key=lambda o: o.characteristics.toughness or 0)
                # Mark as can't-block this turn
                state.turn_data[f"fin_cant_block_{target.id}"] = True
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
    return dark_pool_setup(obj, state, dark_effect)

CROSSED_MARKET = make_order(
    "Crossed Market", "{2}",
    text="Dark Pool. When this triggers, target Trader cannot block this turn.",
    dark_pool=True,
    setup_interceptors=_crossed_market_setup,
)


# Hidden Aggression {2} — Dark Pool. When this triggers, target Trader you control gets +4/+0 until Market Close.
def _hidden_aggression_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        my_traders = [
            o for oid in bf.objects
            if (o := state.objects.get(oid))
            and o.controller == obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        events = []
        if my_traders:
            # Buff the highest-power friendly Trader
            target = max(my_traders, key=lambda o: o.characteristics.power or 0)
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={"object_id": target.id, "power_mod": 2, "toughness_mod": 0, "duration": "end_of_turn"},  # cyc3: +4→+2
                source=obj.id,
            ))
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
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
def _internalization_order_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def dark_effect(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        events = []
        if bf:
            opp_traders = [
                o for oid in bf.objects
                if (o := state.objects.get(oid))
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types
            ]
            if opp_traders:
                target = max(opp_traders, key=lambda o: o.characteristics.toughness or 0)
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={"target": target.id, "amount": 3, "source": obj.id},
                    source=obj.id,
                ))
        key = f"fin_dp_triggered_{obj.controller}"
        state.turn_data[key] = state.turn_data.get(key, 0) + 1
        return events
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
def _information_asymmetry_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    dp_id = get_dark_pool(state)
    if not dp_id:
        return []
    dp_obj = state.objects.get(dp_id)
    if dp_obj is None or dp_obj.controller == controller:
        return []
    # Change controller of the Dark Pool Order object
    dp_obj.controller = controller
    return []

INFORMATION_ASYMMETRY = make_strategy(
    "Information Asymmetry", "{3}",
    text="Gain control of the opponent's currently staged Dark Pool Order.",
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
    # Target the highest-power friendly Trader
    target = max(my_traders, key=lambda o: (o.characteristics.power or 0) + o.state.counters.get("leverage", 0))
    target.state.counters["leverage"] = target.state.counters.get("leverage", 0) + 3
    # Grant Arbitrage 2 until Market Close — stored in turn_data as a temporary buff
    state.turn_data[f"fin_arb_buff_{target.id}"] = 2
    return []

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
        return cd is not None and getattr(cd, "_dark_pool", False)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        me = state.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        current = event.payload.get("cost", 0)
        event.payload["cost"] = max(0, current - 1)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
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
        if bonus > 0:
            event.payload["power"] = event.payload.get("power", 0) + bonus
        return InterceptorResult(action=InterceptorAction.PASS)

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
        if bonus > 0:
            event.payload["toughness"] = event.payload.get("toughness", 0) + bonus
        return InterceptorResult(action=InterceptorAction.PASS)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=_power_filter,
            handler=_power_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
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
        return cd is not None and getattr(cd, "_dark_pool", False)

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
        current = event.payload.get("cost", 0)
        event.payload["cost"] = max(0, current - 1)
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
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
    # --- ORDERS (9) ---
    "Iceberg Order": ICEBERG_ORDER,
    "Off-Exchange Position": OFF_EXCHANGE_POSITION,
    "Block Trade Sweep": BLOCK_TRADE_SWEEP,
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
}
