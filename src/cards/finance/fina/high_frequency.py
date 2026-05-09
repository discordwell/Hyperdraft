"""
HIGH-FREQUENCY archetype cards for Finance TCG — FINA set.

37 cards implementing the Alpha Strike swarm strategy:
Deploy cheap Alpha Strike Traders turns 1–3, protect with Dark Pool Orders,
swing alone for 5–7 damage. Key loop:
    Deploy cheap Alpha Strike Traders → Dark Pool Orders clear blockers
    → Alpha Strike alone for lethal.
"""

from __future__ import annotations

from typing import Optional

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
from src.cards.interceptor_helpers import (
    make_etb_trigger,
    make_attack_trigger,
    make_end_step_trigger,
    make_activated_ability,
)

try:
    from src.engine.finance import (
        get_dark_pool,
        set_dark_pool,
        ensure_finance_state,
    )
    _HAS_FINANCE = True
except ImportError:
    _HAS_FINANCE = False
    get_dark_pool = None  # type: ignore[assignment]
    set_dark_pool = None  # type: ignore[assignment]
    ensure_finance_state = None  # type: ignore[assignment]

# Resolve Finance-specific EventTypes at runtime (they're guaranteed in types.py
# but importing EventType.FIN_MARKET_EVENT directly avoids AttributeError during
# early import when finance.py might not yet have registered them).
FIN_MARKET_EVENT: Optional[EventType] = getattr(EventType, "FIN_MARKET_EVENT", None)
FIN_PLAY_CARD: Optional[EventType] = getattr(EventType, "FIN_PLAY_CARD", None)


# =============================================================================
# Card factory helpers
# =============================================================================

def _int_cost(mana_cost_str: str) -> int:
    """Parse '{N}' to N."""
    s = mana_cost_str.strip("{}")
    try:
        return int(s)
    except ValueError:
        return 0


def make_trader(
    name: str,
    cost: str,
    power: int,
    toughness: int,
    *,
    subtypes: Optional[list[str]] = None,
    text: str = "",
    setup_interceptors=None,
    keywords: Optional[list[str]] = None,
    domain: str = "FINA",
    rarity: Optional[str] = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_TRADER},
        subtypes=set(subtypes or ["Trader"]),
        power=power,
        toughness=toughness,
        mana_cost=cost,
    )
    cd = CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )
    return cd


def make_order(
    name: str,
    cost: str,
    *,
    text: str = "",
    resolve=None,
    setup_interceptors=None,
    dark_pool: bool = False,
    domain: str = "FINA",
    rarity: Optional[str] = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_ORDER},
        subtypes={"Dark Pool Order"} if dark_pool else {"Market Order"},
        mana_cost=cost,
    )
    cd = CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        resolve=resolve,
        setup_interceptors=setup_interceptors,
    )
    cd.dark_pool = dark_pool  # type: ignore[attr-defined]
    return cd


def make_strategy(
    name: str,
    cost: str,
    *,
    text: str = "",
    resolve=None,
    domain: str = "FINA",
    rarity: Optional[str] = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_STRATEGY},
        subtypes={"Strategy"},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        domain=domain,
        text=text,
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
    rarity: Optional[str] = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_ASSET},
        subtypes={"Asset"},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        domain=domain,
        text=text,
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
    rarity: Optional[str] = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_STRUCTURE},
        subtypes={"Structure"},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        domain=domain,
        text=text,
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
    rarity: Optional[str] = None,
) -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_DERIVATIVE},
        subtypes={"Derivative"},
        mana_cost=cost,
    )
    return CardDefinition(
        name=name,
        mana_cost=cost,
        characteristics=chars,
        domain=domain,
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors,
    )


# =============================================================================
# Shared helpers
# =============================================================================

def _count_attacking_traders(controller: str, state: GameState) -> int:
    """Count FIN_TRADER objects controlled by `controller` that are attacking."""
    count = 0
    bf = state.zones.get("battlefield")
    if not bf:
        return 0
    for oid in list(getattr(bf, "objects", [])):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller == controller
                and getattr(o.state, "attacking", False)
                and CardType.FIN_TRADER in o.characteristics.types):
            count += 1
    return count


def _alpha_strike_bonus(obj: GameObject, state: GameState, power_mod: int = 3) -> list[Event]:
    """Emit PT_MODIFICATION if this Trader is attacking alone.

    Bug #4 fix: when Direct Market Access is on the battlefield for the
    controller, the upgrade flag ``fin_alpha_strike_upgrade_<controller>``
    is set; in that case bump the bonus by +1 (so default 3 becomes 4, and
    OEF's 4 becomes 5).

    Bug #6 fix: when an Alpha Strike attacker is declared SOLO (count==1),
    set ``fin_alpha_struck_alone_<controller>`` so Tick Data Archive's
    next-turn pre-market trigger can fire.

    Bug #2 fix (sequential-call robustness): the emitted PT_MODIFICATION
    carries ``_tag='alpha_strike'`` so ``FinanceCombatManager`` can revoke
    it from ``obj.state.pt_modifiers`` if a later ``declare_attackers``
    call raises the attacker count past 1 (i.e. the attacker is no longer
    alone). The same revocation step clears ``fin_alpha_struck_alone_<ctrl>``.
    See ``finance_combat._cleanup_stale_alpha_pt_mods``.
    """
    if _count_attacking_traders(obj.controller, state) == 1:
        # Bug #6: mark that an alpha-striker attacked alone this turn.
        state.turn_data[f"fin_alpha_struck_alone_{obj.controller}"] = True
        # Bug #4: Direct Market Access upgrades the bonus by +1.
        upgrade_key = f"fin_alpha_strike_upgrade_{obj.controller}"
        bonus = power_mod + (1 if state.turn_data.get(upgrade_key) else 0)
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


def _make_alpha_strike_setup(power_mod: int = 3):
    """Return a setup_interceptors function that wires the standard Alpha Strike bonus."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect_fn(event: Event, state: GameState) -> list[Event]:
            return _alpha_strike_bonus(obj, state, power_mod=power_mod)
        return [make_attack_trigger(obj, effect_fn)]
    return setup


def _make_dark_pool_setup(effect_fn_inner):
    """
    Return a setup_interceptors function that registers a FIN_MARKET_EVENT
    interceptor for a Dark Pool Order card.

    `effect_fn_inner(event, state, obj) -> list[Event]` is the per-card effect.
    """
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def _filter(event: Event, state: GameState) -> bool:
            if FIN_MARKET_EVENT is None:
                return False
            return (event.type == FIN_MARKET_EVENT
                    and event.payload.get("obj_id") == obj.id)

        def _handler(event: Event, state: GameState) -> InterceptorResult:
            new_events = effect_fn_inner(event, state, obj)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events,
            )

        icp = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_filter,
            handler=_handler,
            duration="while_on_battlefield",
        )
        return [icp]
    return setup


def _make_phase_start_trigger(phase_name: str, effect_fn_inner, *, controller_only: bool = True):
    """
    Return a setup_interceptors function that fires effect_fn_inner on
    PHASE_START for the given phase name.
    """
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def _filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get("phase") != phase_name:
                return False
            if controller_only and state.active_player != obj.controller:
                return False
            return True

        def _handler(event: Event, state: GameState) -> InterceptorResult:
            new_events = effect_fn_inner(event, state, obj)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events,
            )

        icp = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_filter,
            handler=_handler,
            duration="while_on_battlefield",
        )
        icp.is_triggered_ability = True
        icp.effect_fn = lambda ev, st: effect_fn_inner(ev, st, obj)
        return [icp]
    return setup


def _make_trading_session_start_setup(effect_fn_inner):
    """Fire on PHASE_START for trading_session (controller's turn only)."""
    return _make_phase_start_trigger("trading_session", effect_fn_inner, controller_only=True)


def _make_pre_market_setup(effect_fn_inner, *, controller_only: bool = True):
    """Fire on PHASE_START for pre_market."""
    return _make_phase_start_trigger("pre_market", effect_fn_inner, controller_only=controller_only)


# =============================================================================
# TRADERS (14)
# =============================================================================

# --- Flash Crash Bot {1} 2/1 ---
# Alpha Strike. When this enters, gain 1 Liquidity this turn.
def _flash_crash_bot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals,
                player.mana_crystals_available + 1,
            )
        return []

    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    return [
        make_etb_trigger(obj, etb_fn),
        make_attack_trigger(obj, attack_fn),
    ]


FLASH_CRASH_BOT = make_trader(
    "Flash Crash Bot",
    "{1}",
    power=2,
    toughness=1,
    text="Alpha Strike. When this enters, gain 1 Liquidity this turn.",
    setup_interceptors=_flash_crash_bot_setup,
    rarity="common",
)


# --- Retail Flow Chaser {1} 1/1 ---
# Alpha Strike.
RETAIL_FLOW_CHASER = make_trader(
    "Retail Flow Chaser",
    "{1}",
    power=1,
    toughness=2,  # rebalance: HF curve buff toughness 1 → 2 (vanilla 1/1 trades with everything; 1/2 survives the {1} mirror)
    text="Alpha Strike.",
    setup_interceptors=_make_alpha_strike_setup(3),
    rarity="common",
)


# --- Spoofing Algo {2} 2/1 ---
# Alpha Strike. When this attacks alone, opponent cannot play Orders until Market Close.
def _spoofing_algo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        evts = _alpha_strike_bonus(obj, state)
        if _count_attacking_traders(obj.controller, state) == 1:
            # Mark a turn_data flag that the opponent's Order play is suppressed.
            # The turn manager reads 'fin_orders_suppressed_<player_id>' to enforce.
            for pid in state.players:
                if pid != obj.controller:
                    key = f"fin_orders_suppressed_{pid}"
                    state.turn_data[key] = True
        return evts

    return [make_attack_trigger(obj, attack_fn)]


SPOOFING_ALGO = make_trader(
    "Spoofing Algo",
    "{2}",
    power=2,
    toughness=1,
    text="Alpha Strike. When this attacks alone, opponent cannot play Orders until Market Close.",
    setup_interceptors=_spoofing_algo_setup,
    rarity="uncommon",
)


# --- Front-Running Algo {2} 2/1 ---
# Alpha Strike. When this deals unblocked damage to Capital Reserve, draw a card.
def _front_running_algo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    # The draw-on-unblocked-damage effect listens for DAMAGE events where
    # the source is this Trader and the target is a player (Capital Reserve).
    def dmg_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return (event.payload.get("source") == obj.id
                and event.payload.get("target_player") is not None)

    def dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "amount": 1},
                source=obj.id,
            )],
        )

    dmg_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=dmg_filter,
        handler=dmg_handler,
        duration="while_on_battlefield",
    )
    dmg_icp.is_triggered_ability = True
    dmg_icp.effect_fn = lambda ev, st: [Event(
        type=EventType.DRAW,
        payload={"player": obj.controller, "amount": 1},
        source=obj.id,
    )]
    return [make_attack_trigger(obj, attack_fn), dmg_icp]


FRONT_RUNNING_ALGO = make_trader(
    "Front-Running Algo",
    "{2}",
    power=2,
    toughness=1,
    text="Alpha Strike. When this deals unblocked damage to Capital Reserve, draw a card.",
    setup_interceptors=_front_running_algo_setup,
    rarity="uncommon",
)


# --- Tape Painter {2} 1/2 ---
# Alpha Strike. When this attacks alone, gain 1 Liquidity this turn.
def _tape_painter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        evts = _alpha_strike_bonus(obj, state)
        if _count_attacking_traders(obj.controller, state) == 1:
            player = state.players.get(obj.controller)
            if player:
                player.mana_crystals_available = min(
                    player.mana_crystals,
                    player.mana_crystals_available + 1,
                )
        return evts

    return [make_attack_trigger(obj, attack_fn)]


TAPE_PAINTER = make_trader(
    "Tape Painter",
    "{2}",
    power=2,  # rebalance: HF curve buff power 1 → 2 (was strictly worse than FCB {1} 2/1)
    toughness=2,
    text="Alpha Strike. When this attacks alone, gain 1 Liquidity this turn.",
    setup_interceptors=_tape_painter_setup,
    rarity="common",
)


# --- Colocation Server {2} 2/2 ---
# Alpha Strike. Summoning sickness does not apply to this Trader.
def _colocation_server_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Remove summoning sickness on ETB.
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        o = state.objects.get(obj.id)
        if o is not None:
            o.state.summoning_sickness = False
        return []

    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    return [
        make_etb_trigger(obj, etb_fn),
        make_attack_trigger(obj, attack_fn),
    ]


COLOCATION_SERVER = make_trader(
    "Colocation Server",
    "{2}",
    power=2,
    toughness=2,
    text="Alpha Strike. Summoning sickness does not apply to this Trader.",
    setup_interceptors=_colocation_server_setup,
    rarity="uncommon",
)


# --- Latency Arbitrageur {3} 3/1 ---
# Alpha Strike. When this attacks alone and deals unblocked damage, it deals 1 additional damage.
def _latency_arbitrageur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    # Listen for unblocked damage to player — deal +1 more.
    def dmg_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DAMAGE
                and event.payload.get("source") == obj.id
                and event.payload.get("target_player") is not None)

    def dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        target_player = event.payload.get("target_player")
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={"player": target_player, "amount": -1},
                source=obj.id,
            )],
        )

    dmg_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=dmg_filter,
        handler=dmg_handler,
        duration="while_on_battlefield",
    )
    dmg_icp.is_triggered_ability = True
    dmg_icp.effect_fn = lambda ev, st: [Event(
        type=EventType.LIFE_CHANGE,
        payload={"player": ev.payload.get("target_player"), "amount": -1},
        source=obj.id,
    )]
    return [make_attack_trigger(obj, attack_fn), dmg_icp]


LATENCY_ARBITRAGEUR = make_trader(
    "Latency Arbitrageur",
    "{3}",
    power=3,  # cyc3: restored to 3 (cyc2 over-nerfed to 2)
    toughness=2,  # rebalance: HF curve buff toughness 1 → 2 (3/1 dies to anything)
    text="Alpha Strike. When this attacks alone and deals unblocked damage, it deals 1 additional damage.",
    setup_interceptors=_latency_arbitrageur_setup,
    rarity="uncommon",
)


# --- Momentum Igniter {3} 3/2 ---
# Alpha Strike. When this enters, each other Trader you control gains Alpha Strike until Market Close.
def _momentum_igniter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        # Grant all other friendly Traders a PT_MODIFICATION-style flag via
        # turn_data so the attack-trigger alpha-strike logic sees them as buffed.
        # Concrete effect: each other Trader gets a +0/+0 marker event that
        # signals Alpha Strike grant — the attack trigger for those cards already
        # checks the global alpha_strike state. Here we register a turn-scoped
        # key so the turn manager / alpha_strike logic can read it.
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        affected = [
            oid for oid in getattr(bf, "objects", [])
            if oid != obj.id
            and (o := state.objects.get(oid)) is not None
            and o.controller == obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        ]
        for oid in affected:
            state.turn_data[f"fin_alpha_strike_granted_{oid}"] = True
        return []

    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    return [
        make_etb_trigger(obj, etb_fn),
        make_attack_trigger(obj, attack_fn),
    ]


MOMENTUM_IGNITER = make_trader(
    "Momentum Igniter",
    "{3}",
    power=3,  # cyc3: restored to 3 (cyc2 over-nerfed to 2)
    toughness=2,
    text="Alpha Strike. When this enters, each other Trader you control gains Alpha Strike until Market Close.",
    setup_interceptors=_momentum_igniter_setup,
    rarity="rare",
)


# --- Order Router {3} 2/3 ---
# Alpha Strike. When this blocks, draw a card.
def _order_router_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    def block_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.BLOCK_DECLARED
                and event.payload.get("blocker_id") == obj.id)

    def block_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "amount": 1},
                source=obj.id,
            )],
        )

    block_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=block_filter,
        handler=block_handler,
        duration="while_on_battlefield",
    )
    block_icp.is_triggered_ability = True
    block_icp.effect_fn = lambda ev, st: [Event(
        type=EventType.DRAW,
        payload={"player": obj.controller, "amount": 1},
        source=obj.id,
    )]
    return [make_attack_trigger(obj, attack_fn), block_icp]


ORDER_ROUTER = make_trader(
    "Order Router",
    "{3}",
    power=2,
    toughness=4,  # rebalance: HF curve buff toughness 3 → 4 (dominated by SPB {3} 2/4 and PT {3} 2/3)
    text="Alpha Strike. When this blocks, draw a card.",
    setup_interceptors=_order_router_setup,
    rarity="uncommon",
)


# --- Fill-or-Kill Executor {3} 3/2 ---
# Alpha Strike. When this attacks alone and is not blocked, gain 2 Liquidity this turn.
def _fill_or_kill_executor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    def dmg_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DAMAGE
                and event.payload.get("source") == obj.id
                and event.payload.get("target_player") is not None)

    def dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        player = state.players.get(obj.controller)
        if player:
            player.mana_crystals_available = min(
                player.mana_crystals,
                player.mana_crystals_available + 2,
            )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    dmg_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=dmg_filter,
        handler=dmg_handler,
        duration="while_on_battlefield",
    )
    dmg_icp.is_triggered_ability = True
    dmg_icp.effect_fn = lambda ev, st: []
    return [make_attack_trigger(obj, attack_fn), dmg_icp]


FILL_OR_KILL_EXECUTOR = make_trader(
    "Fill-or-Kill Executor",
    "{3}",
    power=3,  # cyc3: restored to 3 (cyc2 over-nerfed to 2)
    toughness=2,
    text="Alpha Strike. When this attacks alone and is not blocked, gain 2 Liquidity this turn.",
    setup_interceptors=_fill_or_kill_executor_setup,
    rarity="uncommon",
)


# --- Speed Advantage Desk {4} 3/3 ---
# Alpha Strike. (Lev1 self-tax removed in rebalance — see card comment below.)
# rebalance: dead-card repair toughness 2 → 3 AND removed the Lev1 self-tax
# (cyc3 nerf went too far; the Lev tax on a 3-cost body without compensation made it unplayable).
def _speed_advantage_desk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    return [
        make_attack_trigger(obj, attack_fn),
    ]


SPEED_ADVANTAGE_DESK = make_trader(
    "Speed Advantage Desk",
    "{4}",
    power=3,  # balanced: power 4 → 3 (4-cost FIN_TRADER nerf)
    toughness=3,  # rebalance: dead-card repair toughness 2 → 3
    text="Alpha Strike.",
    setup_interceptors=_speed_advantage_desk_setup,
    rarity="rare",
)


# --- Bandwidth Predator {4} 3/3 ---
# Alpha Strike. When this deals damage to a Trader, that Trader does not untap next Pre-Market.
def _bandwidth_predator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    # Listen for DAMAGE where this object is source and target is a Trader.
    def dmg_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get("source") != obj.id:
            return False
        target_id = event.payload.get("target")
        if not target_id:
            return False
        target_obj = state.objects.get(target_id)
        return (target_obj is not None
                and CardType.FIN_TRADER in target_obj.characteristics.types)

    def dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        target_id = event.payload.get("target")
        # Mark the target as frozen (won't untap next pre-market).
        target_obj = state.objects.get(target_id)
        if target_obj is not None:
            target_obj.state.frozen = True
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    dmg_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=dmg_filter,
        handler=dmg_handler,
        duration="while_on_battlefield",
    )
    dmg_icp.is_triggered_ability = True
    dmg_icp.effect_fn = lambda ev, st: []
    return [make_attack_trigger(obj, attack_fn), dmg_icp]


BANDWIDTH_PREDATOR = make_trader(
    "Bandwidth Predator",
    "{4}",
    power=2,  # balanced: power 3 → 2 (4-cost FIN_TRADER nerf)
    toughness=3,
    text="Alpha Strike. When this deals damage to a Trader, that Trader does not untap next Pre-Market.",
    setup_interceptors=_bandwidth_predator_setup,
    rarity="rare",
)


# --- Microwave Relay {4} 4/3 ---
# Alpha Strike. When this enters, if you have no other Traders, gain 2 Liquidity this turn.
def _microwave_relay_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        other_trader_count = sum(
            1 for oid in getattr(bf, "objects", [])
            if oid != obj.id
            and (o := state.objects.get(oid)) is not None
            and o.controller == obj.controller
            and CardType.FIN_TRADER in o.characteristics.types
        )
        if other_trader_count == 0:
            player = state.players.get(obj.controller)
            if player:
                player.mana_crystals_available = min(
                    player.mana_crystals,
                    player.mana_crystals_available + 2,
                )
        return []

    def attack_fn(event: Event, state: GameState) -> list[Event]:
        return _alpha_strike_bonus(obj, state)

    return [
        make_etb_trigger(obj, etb_fn),
        make_attack_trigger(obj, attack_fn),
    ]


MICROWAVE_RELAY = make_trader(
    "Microwave Relay",
    "{4}",
    power=3,  # balanced: power 4 → 3 (4-cost FIN_TRADER nerf)
    toughness=3,
    text="Alpha Strike. When this enters, if you have no other Traders, gain 2 Liquidity this turn.",
    setup_interceptors=_microwave_relay_setup,
    rarity="uncommon",
)


# --- Nanosecond Assassin {5} 5/3 ---
# Alpha Strike. Leverage 2. Alpha Strike bonus is +4/+0 for this Trader.
def _nanosecond_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={"object_id": obj.id, "counter_type": "leverage", "amount": 2},
            source=obj.id,
        )]

    def attack_fn(event: Event, state: GameState) -> list[Event]:
        # Enhanced Alpha Strike: +4/+0 instead of +3/+0.
        return _alpha_strike_bonus(obj, state, power_mod=4)

    return [
        make_etb_trigger(obj, etb_fn),
        make_attack_trigger(obj, attack_fn),
    ]


NANOSECOND_ASSASSIN = make_trader(
    "Nanosecond Assassin",
    "{5}",
    power=5,
    toughness=3,
    text="Alpha Strike. Leverage 2. Alpha Strike bonus is +4/+0 for this Trader.",
    setup_interceptors=_nanosecond_assassin_setup,
    rarity="rare",
)


# --- Capital Skimmer {2} 1/1 Trader ---
# rebalance v2 (2026-05-09): seed for the burn archetype.  Prodigal-Sorcerer
# pattern — chip burn each turn that scales with mana and can target the
# opponent's Capital Reserve directly.  The {tap} cost prevents same-turn
# attack-and-ping.
def _capital_skimmer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Register the {tap}: 1 damage activated ability."""

    def _resolve_target_id(targets: list) -> Optional[str]:
        """Accept either a Target wrapper, a bare object id, or a player id."""
        if not targets:
            return None
        first = targets[0]
        if hasattr(first, "object_id"):
            return first.object_id  # type: ignore[attr-defined]
        if isinstance(first, str):
            return first
        if isinstance(first, list) and first:
            return first[0]
        return None

    def effect_fn(o: GameObject, st: GameState, targets: list) -> list[Event]:
        target_id = _resolve_target_id(targets)
        if target_id is None:
            # No target chosen: auto-pick an opposing player (the most common
            # finance.py burn-target convention — see Pre-Positioned Strike).
            for pid, _player in st.players.items():
                if pid != o.controller:
                    target_id = pid
                    break
        if target_id is None:
            return []
        # DAMAGE event accepts both player ids and object ids in 'target'
        # (see pipeline/handlers/damage.py::_handle_damage).  Player branch
        # routes through the mode adapter's apply_player_damage so the
        # Capital Reserve drops by 1.
        return [Event(
            type=EventType.DAMAGE,
            payload={
                "target": target_id,
                "amount": 1,
                "source": o.id,
                "is_finance": True,
            },
            source=o.id,
            controller=o.controller,
        )]

    make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=effect_fn,
        description="Deal 1 damage to target Trader or opponent.",
        targets_required=1,
        target_kind="trader_or_player",
    )
    return []


CAPITAL_SKIMMER = make_trader(
    "Capital Skimmer",
    "{2}",
    power=1,
    toughness=1,
    text="{T}: Deal 1 damage to target Trader or opponent.",
    setup_interceptors=_capital_skimmer_setup,
    rarity="uncommon",
)


# --- Tick Sniper {1} 2/1 ---
# rebalance v3 (2026-05-09): the missing 1-cost pinnacle aggro body for HF.
# RFC at {1} 1/2 doesn't apply pressure; Tick Sniper at 2/1 does. Vanilla
# Alpha Strike — no other text. The {1} slot's job is "deal damage early."
TICK_SNIPER = make_trader(
    "Tick Sniper",
    "{1}",
    power=2,
    toughness=1,
    text="Alpha Strike.",
    setup_interceptors=_make_alpha_strike_setup(3),
    rarity="common",
)


# =============================================================================
# ORDERS (9)
# =============================================================================

# --- Dark Pool Flash Order {1} Dark Pool ---
# Dark Pool. When this triggers, deal 2 damage to target Trader.
def _dark_pool_flash_order_effect(event: Event, state: GameState, obj: GameObject) -> list[Event]:
    # Target: opponent's Traders on the battlefield (simplified: hit first found).
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types):
            return [Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 2, "source": obj.id},
                source=obj.id,
            )]
    return []


DARK_POOL_FLASH_ORDER = make_order(
    "Dark Pool Flash Order",
    "{1}",
    text="Dark Pool. When this triggers, deal 2 damage to target Trader.",
    dark_pool=True,
    setup_interceptors=_make_dark_pool_setup(_dark_pool_flash_order_effect),
    rarity="common",
)


# --- Sub-Penny Intercept {1} Market Order ---
# Target attacking Trader gets -2/-0 until end of Trading Session.
def _sub_penny_intercept_resolve(event: Event, state: GameState) -> list[Event]:
    # Find the first attacking opponent Trader.
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    controller = event.payload.get("controller")
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != controller
                and CardType.FIN_TRADER in o.characteristics.types
                and getattr(o.state, "attacking", False)):
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": oid,
                    "power_mod": -2,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                },
                source=event.payload.get("source_id", ""),
            )]
    return []


SUB_PENNY_INTERCEPT = make_order(
    "Sub-Penny Intercept",
    "{1}",
    text="Target attacking Trader gets -2/-0 until end of Trading Session.",
    resolve=_sub_penny_intercept_resolve,
    rarity="common",
)


# --- Pre-Market Raid {1} Market Order ---
# During opponent's Trading Session only: deal 1 damage to target Trader.
def _pre_market_raid_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    # Find opponent's Trader with most damage (greedy target).
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != controller
                and CardType.FIN_TRADER in o.characteristics.types):
            return [Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 1, "source": event.payload.get("source_id", "")},
                source=event.payload.get("source_id", ""),
            )]
    return []


PRE_MARKET_RAID = make_order(
    "Pre-Market Raid",
    "{1}",
    text="During opponent's Trading Session only: deal 1 damage to target Trader.",
    resolve=_pre_market_raid_resolve,
    rarity="common",
)


# --- Execution Glitch {2} Market Order ---
# Counter target Order.
def _execution_glitch_resolve(event: Event, state: GameState) -> list[Event]:
    target_id = event.payload.get("target_id")
    if not target_id:
        return []
    fin_stack = getattr(state, "fin_stack", None)
    if fin_stack is None:
        return []
    target_item = fin_stack.find(target_id)
    if target_item is None:
        return []
    target_obj = state.objects.get(target_id)
    if target_obj is None:
        return []
    fin_order = getattr(CardType, "FIN_ORDER", None)
    if fin_order is None or fin_order not in target_obj.characteristics.types:
        return []
    fin_stack.mark_countered(target_id)
    return []


EXECUTION_GLITCH = make_order(
    "Execution Glitch",
    "{2}",
    text="Counter target Order.",
    resolve=_execution_glitch_resolve,
    rarity="uncommon",
)


# --- Spoofed Bid {2} Dark Pool ---
# Dark Pool. When this triggers, target Trader gets -3/-0 until Market Close.
def _spoofed_bid_effect(event: Event, state: GameState, obj: GameObject) -> list[Event]:
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types):
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": oid,
                    "power_mod": -3,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                },
                source=obj.id,
            )]
    return []


SPOOFED_BID = make_order(
    "Spoofed Bid",
    "{2}",
    text="Dark Pool. When this triggers, target Trader gets -3/-0 until Market Close.",
    dark_pool=True,
    setup_interceptors=_make_dark_pool_setup(_spoofed_bid_effect),
    rarity="uncommon",
)


# --- Cancel Order {2} Market Order ---
# Target Trader cannot attack this turn.
def _cancel_order_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != controller
                and CardType.FIN_TRADER in o.characteristics.types
                and not getattr(o.state, "tapped", False)):
            # Tap the Trader to prevent attacking this turn.
            return [Event(
                type=EventType.TAP,
                payload={"object_id": oid},
                source=event.payload.get("source_id", ""),
            )]
    return []


CANCEL_ORDER = make_order(
    "Cancel Order",
    "{2}",
    text="Target Trader cannot attack this turn.",
    resolve=_cancel_order_resolve,
    rarity="common",
)


# --- Quote Stuffing Burst {2} Market Order ---
# Target Trader you control gets +3/+0 and Alpha Strike until Market Close.
def _quote_stuffing_burst_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    # Target the controller's largest Trader (greedy).
    best = None
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller == controller
                and CardType.FIN_TRADER in o.characteristics.types):
            if best is None:
                best = oid
    if best is None:
        return []
    # Grant +3/+0 until Market Close and mark Alpha Strike.
    state.turn_data[f"fin_alpha_strike_granted_{best}"] = True
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={
            "object_id": best,
            "power_mod": 3,
            "toughness_mod": 0,
            "duration": "end_of_turn",
        },
        source=event.payload.get("source_id", ""),
    )]


QUOTE_STUFFING_BURST = make_order(
    "Quote Stuffing Burst",
    "{2}",  # cyc3: restored to {2} (cyc2 over-nerfed to {3})
    text="Target Trader you control gets +3/+0 and Alpha Strike until Market Close.",
    resolve=_quote_stuffing_burst_resolve,
    rarity="uncommon",
)


# --- Circuit Breaker Trip {3} Market Order ---
# Destroy target Trader with Aggression 4 or greater.
def _circuit_breaker_trip_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != controller
                and CardType.FIN_TRADER in o.characteristics.types
                and (o.characteristics.power or 0) >= 4):
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": oid},
                source=event.payload.get("source_id", ""),
            )]
    return []


CIRCUIT_BREAKER_TRIP = make_order(
    "Circuit Breaker Trip",
    "{2}",  # rebalance: removal cost-cut {3} → {2} (conditional removal MTG-priced at {2})
    text="Destroy target Trader with Aggression 4 or greater.",
    resolve=_circuit_breaker_trip_resolve,
    rarity="uncommon",
)


# --- Regulatory Halt {3} Dark Pool ---
# Dark Pool. When this triggers, tap target Trader (it cannot attack this turn).
def _regulatory_halt_effect(event: Event, state: GameState, obj: GameObject) -> list[Event]:
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller != obj.controller
                and CardType.FIN_TRADER in o.characteristics.types):
            return [Event(
                type=EventType.TAP,
                payload={"object_id": oid},
                source=obj.id,
            )]
    return []


REGULATORY_HALT = make_order(
    "Regulatory Halt",
    "{2}",  # rebalance: removal cost-cut {3} → {2} (strictly worse than Cancel Order {2} at higher cost)
    text="Dark Pool. When this triggers, tap target Trader (it cannot attack this turn).",
    dark_pool=True,
    setup_interceptors=_make_dark_pool_setup(_regulatory_halt_effect),
    rarity="uncommon",
)


# =============================================================================
# Burn helpers (rebalance v3, 2026-05-09)
# =============================================================================
# Direct-damage Orders for the burn archetype. Pattern: emit a DAMAGE event
# to either a player (Capital Reserve drop via mode adapter) or a Trader
# (damage marked on the object). Auto-targets opp player when no target chosen
# (the burn deck wants face damage by default — same convention as Capital
# Skimmer's _resolve_target_id).

def _resolve_burn_target_id(
    targets: list,
    state: GameState,
    controller: str,
) -> Optional[str]:
    """Return a target id (object id OR player id), defaulting to opponent.

    Accepts the same flexible target shapes the rest of the FINA codebase
    uses: Target wrappers (with .object_id), bare ids, or nested lists.
    """
    if targets:
        first = targets[0]
        if hasattr(first, "object_id"):
            tid = first.object_id  # type: ignore[attr-defined]
            if tid:
                return tid
        elif isinstance(first, str) and first:
            return first
        elif isinstance(first, list) and first:
            tid = first[0]
            if isinstance(tid, str) and tid:
                return tid
    # Default: hit the opponent's Capital Reserve.
    for pid in state.players:
        if pid != controller:
            return pid
    return None


def _make_burn_order_resolve(damage: int):
    """Return a resolve_fn that deals `damage` to a Trader or opponent.

    Reads target_id (set by finance_turn._resolve_stack_item from
    targets[0]) and emits a DAMAGE event. When no target is provided
    (targets=[]) the resolve auto-picks the opponent player id.
    """
    def resolve(event: Event, state: GameState) -> list[Event]:
        controller = event.payload.get("controller") or event.controller
        if not controller:
            return []
        target_id = event.payload.get("target_id")
        if not target_id:
            target_id = _resolve_burn_target_id(
                event.payload.get("targets") or [], state, controller
            )
        if not target_id:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={
                "target": target_id,
                "amount": damage,
                "source": event.payload.get("source_id", ""),
                "is_finance": True,
            },
            source=event.payload.get("source_id", ""),
            controller=controller,
        )]
    return resolve


# --- Capital Skim {1} Order ---
# rebalance v3 (2026-05-09): Lightning-Bolt-tier-cheap chip burn for the burn
# archetype. {1} for 1 damage is the burn deck's reach card. Pairs with
# Capital Skimmer (the recurring engine) for cumulative chip burn that ignores
# Synthetic-Collar walls and goes straight to face.
CAPITAL_SKIM = make_order(
    "Capital Skim",
    "{1}",
    text="Deal 1 damage to target Trader or opponent.",
    resolve=_make_burn_order_resolve(1),
    rarity="common",
)


# --- Volatility Bomb {2} Order ---
# rebalance v3 (2026-05-09): Lightning Bolt analog. {2} for 3 damage is the
# canonical MTG cost. Strictly a removal AND finisher — hits Traders for
# trades AND chips opponent's Capital. The card a burn deck mainboards 4-of.
VOLATILITY_BOMB = make_order(
    "Volatility Bomb",
    "{2}",
    text="Deal 3 damage to target Trader or opponent.",
    resolve=_make_burn_order_resolve(3),
    rarity="uncommon",
)


# =============================================================================
# STRATEGIES (5)
# =============================================================================

# --- Low-Latency Strike {2} Strategy ---
# Each of your Traders with Alpha Strike may attack this turn even if they have summoning sickness.
#
# Bug #3 fix: the finance engine's one-shot effect dispatcher
# (finance_turn._play_card_action) looks for ``cast_effect`` /
# ``spell_effect`` / ``effect`` with signature ``(obj, state, targets)``,
# NOT ``resolve(event, state)``. The original ``resolve=...`` path was
# never invoked, so Low-Latency Strike was a 2-mana no-op. Provide both
# a ``resolve`` function (for any caller that uses the legacy event-based
# signature) and a ``cast_effect`` adapter that the finance engine
# actually dispatches.
def _low_latency_strike_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    return _low_latency_strike_apply(controller, state)


def _low_latency_strike_apply(controller: str, state: GameState) -> list[Event]:
    """Clear summoning sickness on every controlled Trader."""
    bf = state.zones.get("battlefield")
    if not bf or not controller:
        return []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller == controller
                and CardType.FIN_TRADER in o.characteristics.types):
            o.state.summoning_sickness = False
    return []


def _low_latency_strike_cast_effect(obj: GameObject, state: GameState, targets) -> list[Event]:
    """Adapter for finance_turn one-shot dispatcher: signature (obj, state, targets)."""
    return _low_latency_strike_apply(obj.controller, state)


LOW_LATENCY_STRIKE = make_strategy(
    "Low-Latency Strike",
    "{2}",
    text="Each of your Traders with Alpha Strike may attack this turn even if they have summoning sickness.",
    resolve=_low_latency_strike_resolve,
    rarity="uncommon",
)
# Bug #3: wire the cast_effect attribute the finance engine actually invokes.
LOW_LATENCY_STRIKE.cast_effect = _low_latency_strike_cast_effect  # type: ignore[attr-defined]


# --- Momentum Ignition {3} Strategy ---
# Each of your Traders attacks this turn if able.
# Traders with Alpha Strike get +2/+0 until Market Close.
def _momentum_ignition_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    evts: list[Event] = []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller == controller
                and CardType.FIN_TRADER in o.characteristics.types
                and not getattr(o.state, "tapped", False)
                and not getattr(o.state, "summoning_sickness", False)):
            # Force attack — mark turn_data so the turn manager forces attackers.
            state.turn_data.setdefault("fin_forced_attackers", [])
            state.turn_data["fin_forced_attackers"].append(oid)
            # Grant +2/+0 for those with Alpha Strike (all in HF archetype).
            evts.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": oid,
                    "power_mod": 2,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                },
                source=event.payload.get("source_id", ""),
            ))
    return evts


MOMENTUM_IGNITION = make_strategy(
    "Momentum Ignition",
    "{3}",  # cyc3: restored to {3} (cyc2 over-nerfed to {4})
    text="Each of your Traders attacks this turn if able. Traders with Alpha Strike get +2/+0 until Market Close.",
    resolve=_momentum_ignition_resolve,
    rarity="rare",
)


# --- Flash Crash Event {3} Strategy ---
# Destroy all Traders with Defense Rating 2 or less.
def _flash_crash_event_resolve(event: Event, state: GameState) -> list[Event]:
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    evts: list[Event] = []
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and CardType.FIN_TRADER in o.characteristics.types
                and (o.characteristics.toughness or 0) <= 2):
            evts.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": oid},
                source=event.payload.get("source_id", ""),
            ))
    return evts


FLASH_CRASH_EVENT = make_strategy(
    "Flash Crash Event",
    "{3}",
    text="Destroy all Traders with Defense Rating 2 or less.",
    resolve=_flash_crash_event_resolve,
    rarity="rare",
)


# --- Pump-and-Dump {4} Strategy ---
# Target Trader you control gets +4/+0 until Market Close.
# Then place 2 Leverage counters on it.
def _pump_and_dump_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    best = None
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller == controller
                and CardType.FIN_TRADER in o.characteristics.types):
            best = oid
            break
    if best is None:
        return []
    src = event.payload.get("source_id", "")
    return [
        Event(
            type=EventType.PT_MODIFICATION,
            payload={
                "object_id": best,
                "power_mod": 4,
                "toughness_mod": 0,
                "duration": "end_of_turn",
            },
            source=src,
        ),
        Event(
            type=EventType.COUNTER_ADDED,
            payload={"object_id": best, "counter_type": "leverage", "amount": 2},
            source=src,
        ),
    ]


PUMP_AND_DUMP = make_strategy(
    "Pump-and-Dump",
    "{4}",  # rebalance: dead-card repair cost {5} → {4} (dead at {5} relative to QSB {2})
    text="Target Trader you control gets +4/+0 until Market Close. Then place 2 Leverage counters on it.",
    resolve=_pump_and_dump_resolve,
    rarity="uncommon",
)


# --- Acceleration Protocol {4} Strategy ---
# Your Traders get +2/+0 until Market Close.
# Each Trader with Alpha Strike gets +1/+0 additionally.
def _acceleration_protocol_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller")
    bf = state.zones.get("battlefield")
    if not bf:
        return []
    evts: list[Event] = []
    src = event.payload.get("source_id", "")
    for oid in getattr(bf, "objects", []):
        o = state.objects.get(oid)
        if (o is not None
                and o.controller == controller
                and CardType.FIN_TRADER in o.characteristics.types):
            # All friendly Traders get +2/+0.
            evts.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    "object_id": oid,
                    "power_mod": 2,
                    "toughness_mod": 0,
                    "duration": "end_of_turn",
                },
                source=src,
            ))
            # HF Traders with Alpha Strike (turn_data marker or archetype keyword)
            # get an additional +1/+0.
            if state.turn_data.get(f"fin_alpha_strike_granted_{oid}"):
                evts.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        "object_id": oid,
                        "power_mod": 1,
                        "toughness_mod": 0,
                        "duration": "end_of_turn",
                    },
                    source=src,
                ))
    return evts


ACCELERATION_PROTOCOL = make_strategy(
    "Acceleration Protocol",
    "{3}",  # rebalance: dead-card repair cost {4} → {3} (dominated by Momentum Ignition {3})
    text="Your Traders get +2/+0 until Market Close. Each Trader with Alpha Strike gets +1/+0 additionally.",
    resolve=_acceleration_protocol_resolve,
    rarity="rare",
)


# --- Cascading Liquidations {3} Strategy ---
# rebalance v3 (2026-05-09): Burn finisher. Scales with attrition — every
# Trader you've lost or sacrificed becomes damage. Max 6 caps the variance.
# {3} for "up to 6 damage to the face" matches MTG burn finisher costing
# (Lava Spike {1} = 3, Searing Blaze {2} = 3+3, Cascading at {3} for ≤6 is
# in line with mid-burn finishers). NOT to be confused with the existing
# Liquidation Cascade (DERIVATIVES) which destroys up to 3 Derivatives.
def _cascading_liquidations_resolve(event: Event, state: GameState) -> list[Event]:
    controller = event.payload.get("controller") or event.controller
    if not controller:
        return []
    # Count Traders in OUR graveyard.
    gz = state.zones.get(f"graveyard_{controller}")
    if gz is None:
        return []
    trader_count = 0
    for oid in getattr(gz, "objects", []):
        o = state.objects.get(oid)
        if o is not None and CardType.FIN_TRADER in o.characteristics.types:
            trader_count += 1
    damage = min(6, trader_count)
    if damage <= 0:
        return []
    # Auto-target the opponent (face damage finisher).
    target_id = _resolve_burn_target_id([], state, controller)
    if not target_id:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={
            "target": target_id,
            "amount": damage,
            "source": event.payload.get("source_id", ""),
            "is_finance": True,
        },
        source=event.payload.get("source_id", ""),
        controller=controller,
    )]


CASCADING_LIQUIDATIONS = make_strategy(
    "Cascading Liquidations",
    "{3}",
    text="Deal damage to target opponent equal to the number of Traders in your graveyard (maximum 6).",
    resolve=_cascading_liquidations_resolve,
    rarity="rare",
)


# =============================================================================
# ASSETS (5)
# =============================================================================

# --- HFT Feed Colocation {2} Asset ---
# Static: your Traders with Alpha Strike get +1/+0.
# Implemented as a QUERY_POWER interceptor boosting friendly Traders.
def _hft_feed_colocation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id) if target_id else None
        return (target is not None
                and target.controller == obj.controller
                and CardType.FIN_TRADER in target.characteristics.types)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        # bug #21: queries.get_power reads transformed_event.payload['value'] only.
        # Previous handler mutated payload['power'] and returned PASS — never read.
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        # bug #21: priority must be QUERY for queries.get_power to iterate it.
        priority=InterceptorPriority.QUERY,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )
    return [icp]


HFT_FEED_COLOCATION = make_asset(
    "HFT Feed Colocation",
    "{2}",
    text="Static: your Traders with Alpha Strike get +1/+0.",
    setup_interceptors=_hft_feed_colocation_setup,
    rarity="uncommon",
)


# --- Tick Data Archive {2} Asset ---
# At the start of your Pre-Market, if any of your Traders attacked alone last turn, draw a card.
def _tick_data_archive_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # We track "attacked alone last turn" via a turn_data key set by alpha_strike triggers.
    def pre_market_fn(event: Event, state: GameState, obj: GameObject) -> list[Event]:
        key = f"fin_alpha_struck_alone_{obj.controller}"
        if state.turn_data.get(key):
            state.turn_data[key] = False
            return [Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "amount": 1},
                source=obj.id,
            )]
        return []

    return _make_pre_market_setup(pre_market_fn)(obj, state)


TICK_DATA_ARCHIVE = make_asset(
    "Tick Data Archive",
    "{2}",
    text="At the start of your Pre-Market, if any of your Traders attacked alone last turn, draw a card.",
    setup_interceptors=_tick_data_archive_setup,
    rarity="uncommon",
)


# --- Speed Co-location Hub {3} Asset ---
# At the start of your Trading Session, you may have one Trader lose summoning sickness this turn.
def _speed_colocation_hub_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def ts_fn(event: Event, state: GameState, obj: GameObject) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        for oid in getattr(bf, "objects", []):
            o = state.objects.get(oid)
            if (o is not None
                    and o.controller == obj.controller
                    and CardType.FIN_TRADER in o.characteristics.types
                    and getattr(o.state, "summoning_sickness", False)):
                o.state.summoning_sickness = False
                break  # Only one Trader per turn.
        return []

    return _make_trading_session_start_setup(ts_fn)(obj, state)


SPEED_COLOCATION_HUB = make_asset(
    "Speed Co-location Hub",
    "{2}",  # rebalance: dead-card repair cost {3} → {2} (SS-removal narrower than Low-Latency Strike's broader effect)
    text="At the start of your Trading Session, you may have one Trader lose summoning sickness this turn.",
    setup_interceptors=_speed_colocation_hub_setup,
    rarity="rare",
)


# --- Direct Market Access {3} Asset ---
# Static: your Alpha Strike bonus is +4/+0 instead of +3/+0.
# Implementation: mark a turn_data/global flag that the bonus is upgraded.
def _direct_market_access_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # On ETB, set the upgrade flag; it stays while this Asset is in play.
    def etb_fn(event: Event, state: GameState) -> list[Event]:
        state.turn_data[f"fin_alpha_strike_upgrade_{obj.controller}"] = True
        return []

    # The flag needs to be cleared when this card leaves the battlefield.
    # We use a ZONE_CHANGE listener for that.
    def leave_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ZONE_CHANGE
                and event.payload.get("object_id") == obj.id
                and event.payload.get("from_zone_type") == ZoneType.BATTLEFIELD)

    def leave_handler(event: Event, state: GameState) -> InterceptorResult:
        state.turn_data.pop(f"fin_alpha_strike_upgrade_{obj.controller}", None)
        return InterceptorResult(action=InterceptorAction.PASS)

    leave_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=leave_filter,
        handler=leave_handler,
        duration="until_leaves",
    )
    return [
        make_etb_trigger(obj, etb_fn),
        leave_icp,
    ]


DIRECT_MARKET_ACCESS = make_asset(
    "Direct Market Access",
    "{3}",
    text="Static: your Alpha Strike bonus is +4/+0 instead of +3/+0.",
    setup_interceptors=_direct_market_access_setup,
    rarity="rare",
)


# --- High-Speed Network {4} Asset ---
# Activated: {2}, tap — give target Trader Alpha Strike until Market Close.
def _high_speed_network_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], "object_id") else targets[0]
        st.turn_data[f"fin_alpha_strike_granted_{target_id}"] = True
        return []

    make_activated_ability(
        obj,
        cost="{2}, tap",
        effect_fn=effect_fn,
        description="Give target Trader Alpha Strike until Market Close.",
        targets_required=1,
        target_kind="trader",
    )
    return []


HIGH_SPEED_NETWORK = make_asset(
    "High-Speed Network",
    "{2}",  # rebalance: dead-card repair cost {4} → {2} (TTD at {2} grants permanent Alpha; HSN once-per-turn at {4} is just bad)
    text="Activated: {2}, tap — give target Trader Alpha Strike until Market Close.",
    setup_interceptors=_high_speed_network_setup,
    rarity="uncommon",
)


# =============================================================================
# STRUCTURES (2)
# =============================================================================

# --- Order Matching Engine {3} Structure ---
# Tap: target Trader you control gets +2/+0 until Market Close.
def _order_matching_engine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], "object_id") else targets[0]
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                "object_id": target_id,
                "power_mod": 2,
                "toughness_mod": 0,
                "duration": "end_of_turn",
            },
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="tap",
        effect_fn=effect_fn,
        description="Target Trader you control gets +2/+0 until Market Close.",
        targets_required=1,
        target_kind="trader",
    )
    return []


ORDER_MATCHING_ENGINE = make_structure(
    "Order Matching Engine",
    "{2}",  # rebalance: dead-card repair cost {3} → {2} (clunky activation + small effect)
    text="Tap: target Trader you control gets +2/+0 until Market Close.",
    setup_interceptors=_order_matching_engine_setup,
    rarity="uncommon",
)


# --- Low-Latency Exchange {4} Structure ---
# At the start of your Trading Session, each of your Traders with Alpha Strike gets +1/+0
# until Market Close.
def _low_latency_exchange_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def ts_fn(event: Event, state: GameState, obj: GameObject) -> list[Event]:
        bf = state.zones.get("battlefield")
        if not bf:
            return []
        evts: list[Event] = []
        for oid in getattr(bf, "objects", []):
            o = state.objects.get(oid)
            if (o is not None
                    and o.controller == obj.controller
                    and CardType.FIN_TRADER in o.characteristics.types):
                evts.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        "object_id": oid,
                        "power_mod": 1,
                        "toughness_mod": 0,
                        "duration": "end_of_turn",
                    },
                    source=obj.id,
                ))
        return evts

    return _make_trading_session_start_setup(ts_fn)(obj, state)


LOW_LATENCY_EXCHANGE = make_structure(
    "Low-Latency Exchange",
    "{3}",  # rebalance: dead-card repair cost {4} → {3}
    text="At the start of your Trading Session, each of your Traders with Alpha Strike gets +1/+0 until Market Close.",
    setup_interceptors=_low_latency_exchange_setup,
    rarity="rare",
)


# =============================================================================
# DERIVATIVES (2)
# =============================================================================

# --- Ticker Tape Derivative {2} Derivative ---
# Attach to a Trader: it gains Alpha Strike.
# Bug #26 fix: the original ETB-based impl set `fin_alpha_strike_granted_` in
# turn_data, which resets every Market Close.  The grant therefore expired after
# the very first turn, making TTD a single-turn Alpha grant at best.  The fix
# registers a *persistent* ATTACK_DECLARED interceptor that fires on behalf of
# the attached Trader every turn TTD remains attached, calling
# `_alpha_strike_bonus` exactly as a native Alpha Strike card does.
def _ticker_tape_derivative_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attached_to = getattr(obj.state, "attached_to", None)
        return (attached_to is not None
                and event.payload.get("attacker_id") == attached_to)

    def attack_handler(event: Event, state: GameState) -> InterceptorResult:
        attached_to = getattr(obj.state, "attached_to", None)
        if attached_to is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        target = state.objects.get(attached_to)
        if target is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Bug #30 fix: if the attached Trader already has native Alpha Strike
        # (detected via card text), its own ATTACK_DECLARED interceptor will
        # call _alpha_strike_bonus independently.  Calling it a second time
        # here would double-stack the bonus (+6 instead of +3).  Only grant
        # the alpha bonus when the Trader does NOT have native Alpha Strike.
        target_text = str(
            getattr(target.characteristics, "text", None)
            or getattr(target, "text", None)
            or ""
        )
        if "Alpha Strike" in target_text:
            # Native Alpha Strike already wired — TTD grant is a no-op here.
            return InterceptorResult(action=InterceptorAction.PASS)
        bonus_events = _alpha_strike_bonus(target, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=bonus_events,
        )

    alpha_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration="while_on_battlefield",
    )
    alpha_icp.is_triggered_ability = True
    return [alpha_icp]


TICKER_TAPE_DERIVATIVE = make_derivative(
    "Ticker Tape Derivative",
    "{2}",
    text="Attach to a Trader: it gains Alpha Strike.",
    setup_interceptors=_ticker_tape_derivative_setup,
    rarity="common",
)


# --- Speed Amplifier {2} Derivative ---
# Attach to a Trader: it gets +2/+0.
# When it attacks alone, draw a card.
def _speed_amplifier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Static +2/+0 to the attached Trader via QUERY_POWER.
    def pwr_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        attached_to = getattr(obj.state, "attached_to", None)
        return (attached_to is not None
                and event.payload.get("object_id") == attached_to)

    def pwr_handler(event: Event, state: GameState) -> InterceptorResult:
        # priority class: queries.get_power reads transformed_event.payload['value'].
        new_event = event.copy()
        new_event.payload["value"] = new_event.payload.get("value", 0) + 2
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    pwr_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=pwr_filter,
        handler=pwr_handler,
        duration="while_on_battlefield",
    )

    # When the attached Trader attacks alone, draw a card.
    def atk_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attached_to = getattr(obj.state, "attached_to", None)
        return (attached_to is not None
                and event.payload.get("attacker_id") == attached_to)

    def atk_handler(event: Event, state: GameState) -> InterceptorResult:
        if _count_attacking_traders(obj.controller, state) == 1:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.DRAW,
                    payload={"player": obj.controller, "amount": 1},
                    source=obj.id,
                )],
            )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    atk_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=atk_filter,
        handler=atk_handler,
        duration="while_on_battlefield",
    )
    atk_icp.is_triggered_ability = True
    atk_icp.effect_fn = lambda ev, st: (
        [Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "amount": 1},
            source=obj.id,
        )] if _count_attacking_traders(obj.controller, st) == 1 else []
    )

    # Bug #5 fix: when the attached host leaves the battlefield (dies, exiles,
    # bounces) Speed Amplifier orphans on a stale object_id and contributes
    # nothing for the rest of the game. Tie our lifetime to the host's: when
    # the host is destroyed OR ZONE_CHANGEs off battlefield, destroy ourselves
    # (and clear attached_to so the static +2/+0 stops applying immediately).
    def host_leave_filter(event: Event, state: GameState) -> bool:
        attached_to = getattr(obj.state, "attached_to", None)
        if attached_to is None:
            return False
        if event.type == EventType.OBJECT_DESTROYED:
            return event.payload.get("object_id") == attached_to
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get("object_id") != attached_to:
                return False
            # Engine emits multiple shapes: from_zone_type=BATTLEFIELD,
            # or "from"="battlefield" (finance_combat liquidation path).
            return (event.payload.get("from_zone_type") == ZoneType.BATTLEFIELD
                    or event.payload.get("from") == "battlefield")
        return False

    def host_leave_handler(event: Event, state: GameState) -> InterceptorResult:
        # Clear our attached_to immediately so the static power buff stops
        # applying even before our destroy-event resolves.
        obj.state.attached_to = None
        # Issue an OBJECT_DESTROYED on ourselves so we hit the graveyard
        # via the standard SBA pathway (consistent with other Derivatives).
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": obj.id, "reason": "host_died"},
                source=obj.id,
            )],
        )

    host_leave_icp = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=host_leave_filter,
        handler=host_leave_handler,
        duration="while_on_battlefield",
    )
    host_leave_icp.is_triggered_ability = True
    host_leave_icp.effect_fn = lambda ev, st: [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": obj.id, "reason": "host_died"},
        source=obj.id,
    )]
    return [pwr_icp, atk_icp, host_leave_icp]


SPEED_AMPLIFIER = make_derivative(
    "Speed Amplifier",
    "{2}",
    text="Attach to a Trader: it gets +2/+0. When it attacks alone, draw a card.",
    setup_interceptors=_speed_amplifier_setup,
    rarity="uncommon",
)


# =============================================================================
# Export dict — exact card names from fina.md HIGH-FREQUENCY section
# =============================================================================

HIGH_FREQUENCY_CARDS: dict[str, CardDefinition] = {
    # Traders (16) — rebalance v3: +1 (Tick Sniper)
    "Flash Crash Bot":       FLASH_CRASH_BOT,
    "Retail Flow Chaser":    RETAIL_FLOW_CHASER,
    "Spoofing Algo":         SPOOFING_ALGO,
    "Front-Running Algo":    FRONT_RUNNING_ALGO,
    "Tape Painter":          TAPE_PAINTER,
    "Colocation Server":     COLOCATION_SERVER,
    "Latency Arbitrageur":   LATENCY_ARBITRAGEUR,
    "Momentum Igniter":      MOMENTUM_IGNITER,
    "Order Router":          ORDER_ROUTER,
    "Fill-or-Kill Executor": FILL_OR_KILL_EXECUTOR,
    "Speed Advantage Desk":  SPEED_ADVANTAGE_DESK,
    "Bandwidth Predator":    BANDWIDTH_PREDATOR,
    "Microwave Relay":       MICROWAVE_RELAY,
    "Nanosecond Assassin":   NANOSECOND_ASSASSIN,
    "Capital Skimmer":       CAPITAL_SKIMMER,  # rebalance v2: burn-archetype seed
    "Tick Sniper":           TICK_SNIPER,      # rebalance v3: pinnacle T1 aggro body
    # Orders (11) — rebalance v3: +2 (Capital Skim, Volatility Bomb)
    "Dark Pool Flash Order": DARK_POOL_FLASH_ORDER,
    "Sub-Penny Intercept":   SUB_PENNY_INTERCEPT,
    "Pre-Market Raid":       PRE_MARKET_RAID,
    "Execution Glitch":      EXECUTION_GLITCH,
    "Spoofed Bid":           SPOOFED_BID,
    "Cancel Order":          CANCEL_ORDER,
    "Quote Stuffing Burst":  QUOTE_STUFFING_BURST,
    "Circuit Breaker Trip":  CIRCUIT_BREAKER_TRIP,
    "Regulatory Halt":       REGULATORY_HALT,
    "Capital Skim":          CAPITAL_SKIM,      # rebalance v3: {1} chip burn
    "Volatility Bomb":       VOLATILITY_BOMB,   # rebalance v3: {2} Lightning Bolt analog
    # Strategies (6) — rebalance v3: +1 (Cascading Liquidations)
    "Low-Latency Strike":    LOW_LATENCY_STRIKE,
    "Momentum Ignition":     MOMENTUM_IGNITION,
    "Flash Crash Event":     FLASH_CRASH_EVENT,
    "Pump-and-Dump":         PUMP_AND_DUMP,
    "Acceleration Protocol": ACCELERATION_PROTOCOL,
    "Cascading Liquidations": CASCADING_LIQUIDATIONS,  # rebalance v3: burn finisher
    # Assets (5)
    "HFT Feed Colocation":   HFT_FEED_COLOCATION,
    "Tick Data Archive":     TICK_DATA_ARCHIVE,
    "Speed Co-location Hub": SPEED_COLOCATION_HUB,
    "Direct Market Access":  DIRECT_MARKET_ACCESS,
    "High-Speed Network":    HIGH_SPEED_NETWORK,
    # Structures (2)
    "Order Matching Engine": ORDER_MATCHING_ENGINE,
    "Low-Latency Exchange":  LOW_LATENCY_EXCHANGE,
    # Derivatives (2)
    "Ticker Tape Derivative": TICKER_TAPE_DERIVATIVE,
    "Speed Amplifier":        SPEED_AMPLIFIER,
}

assert len(HIGH_FREQUENCY_CARDS) == 42, (
    f"Expected 42 HIGH-FREQUENCY cards, got {len(HIGH_FREQUENCY_CARDS)}"
)
