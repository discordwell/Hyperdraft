"""FINM - Market Meltdown expansion for the Finance TCG.

Expansion goal: add a second Finance environment with six supported
archetypes and mechanics that the current simulator can execute:

* Covenant N - comeback income if your Capital Reserve is not ahead.
* Coupon N - pre-market income on income permanents.
* Hedge N - once each turn, reduce incoming damage to this Trader.
* All-In - ETB payoff if the card emptied your Liquidity pool.
* Restructure N - death payoff that returns Liquidity.
* Buyback N - grows when you cast Orders or Strategies.

The card list is generated from explicit specs to keep 180 cards reviewable
without 180 near-identical factory calls. Each spec creates a playable
CardDefinition with real Finance types and supported interceptors/resolvers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.cards.interceptor_helpers import make_death_trigger, make_etb_trigger
from src.engine.queries import get_toughness
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

DOMAIN = "FINM"
EXPECTED_CARD_COUNT = 180


@dataclass(frozen=True)
class CardSpec:
    name: str
    kind: str
    cost: int
    power: int | None
    toughness: int | None
    text: str
    rarity: str
    mechanic: str = ""
    n: int = 0
    archetype: str = ""


def _mana(cost: int) -> str:
    return "{" + str(cost) + "}"


def _other_player(state: GameState, player_id: str) -> str | None:
    return next((pid for pid in state.players if pid != player_id), None)


def _player(state: GameState, player_id: str):
    return state.players.get(player_id)


def _battlefield(state: GameState):
    return state.zones.get("battlefield")


def _is_trader(obj: GameObject | None) -> bool:
    return bool(
        obj is not None
        and obj.zone == ZoneType.BATTLEFIELD
        and CardType.FIN_TRADER in obj.characteristics.types
    )


def _own_traders(state: GameState, player_id: str) -> list[GameObject]:
    bf = _battlefield(state)
    if not bf:
        return []
    return [
        obj for oid in list(bf.objects)
        if _is_trader(obj := state.objects.get(oid)) and obj.controller == player_id
    ]


def _opp_traders(state: GameState, player_id: str) -> list[GameObject]:
    opp = _other_player(state, player_id)
    return _own_traders(state, opp) if opp else []


def _effective_defense(obj: GameObject, state: GameState) -> int:
    return int(get_toughness(obj, state) or 0)


def _gain_liquidity(state: GameState, player_id: str, amount: int) -> None:
    player = _player(state, player_id)
    if not player or amount <= 0:
        return
    player.mana_crystals_available = int(player.mana_crystals_available or 0) + amount


def _target_from_event(event: Event) -> str | None:
    target_id = event.payload.get("target_id")
    if target_id:
        return target_id
    targets = event.payload.get("targets") or []
    if targets:
        first = targets[0]
        if isinstance(first, list) and first:
            return first[0]
        if isinstance(first, str):
            return first
    return None


def _best_enemy_trader(state: GameState, controller: str) -> str | None:
    enemies = _opp_traders(state, controller)
    if not enemies:
        return None
    enemies.sort(
        key=lambda o: ((o.characteristics.power or 0) + (o.characteristics.toughness or 0), o.characteristics.power or 0),
        reverse=True,
    )
    return enemies[0].id


def _weakest_enemy_trader(state: GameState, controller: str, max_toughness: int) -> str | None:
    candidates = [
        o for o in _opp_traders(state, controller)
        if _effective_defense(o, state) <= max_toughness
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda o: (_effective_defense(o, state), o.characteristics.power or 0))
    return candidates[0].id


def _is_legal_enemy_trader_under_defense(
    state: GameState,
    controller: str,
    target_id: str | None,
    max_defense: int,
) -> bool:
    if not target_id:
        return False
    target = state.objects.get(target_id)
    return bool(
        _is_trader(target)
        and target.controller != controller
        and _effective_defense(target, state) <= max_defense
    )


def _make_query_stat_interceptor(
    obj: GameObject,
    stat: str,
    amount_fn: Callable[[GameState], int],
    applies_fn: Callable[[GameObject, GameState], bool],
) -> Interceptor:
    event_type = EventType.QUERY_POWER if stat == "power" else EventType.QUERY_TOUGHNESS

    def _filter(event: Event, state: GameState) -> bool:
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id)
        return event.type == event_type and target is not None and applies_fn(target, state)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        amount = amount_fn(state)
        if amount == 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_event = event.copy()
        new_event.payload["value"] = int(new_event.payload.get("value", 0) or 0) + amount
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )


def _pre_market_interceptor(obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    def _filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "pre_market"
            and event.payload.get("player") == obj.controller
        )

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )


def _covenant_setup(n: int):
    """Covenant N: at your Pre-Market, if not ahead on Capital, gain N Liquidity."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, state: GameState) -> list[Event]:
            me = _player(state, obj.controller)
            opp_id = _other_player(state, obj.controller)
            opp = _player(state, opp_id) if opp_id else None
            if me and opp and int(me.life or 0) <= int(opp.life or 0):
                _gain_liquidity(state, obj.controller, n)
                return [Event(
                    type=EventType.FIN_CAPITAL_CALL,
                    payload={"player": obj.controller, "amount": n, "kind": "covenant"},
                    source=obj.id,
                    controller=obj.controller,
                )]
            return []

        return [_pre_market_interceptor(obj, effect)]
    return setup


def _coupon_setup(n: int):
    """Coupon N: at your Pre-Market, gain N available Liquidity."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, state: GameState) -> list[Event]:
            _gain_liquidity(state, obj.controller, n)
            return [Event(
                type=EventType.FIN_CAPITAL_CALL,
                payload={"player": obj.controller, "amount": n, "kind": "coupon"},
                source=obj.id,
                controller=obj.controller,
            )]

        return [_pre_market_interceptor(obj, effect)]
    return setup


def _hedge_setup(n: int):
    """Hedge N: once each turn, reduce damage dealt to this Trader by N."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def _filter(event: Event, state: GameState) -> bool:
            return event.type == EventType.DAMAGE and event.payload.get("target") == obj.id

        def _handler(event: Event, state: GameState) -> InterceptorResult:
            turn = int(getattr(state, "turn_number", 0) or 0)
            key = f"finm_hedge_used_{obj.id}_{turn}"
            if state.turn_data.get(key):
                return InterceptorResult(action=InterceptorAction.PASS)
            amount = int(event.payload.get("amount", 0) or 0)
            if amount <= 0:
                return InterceptorResult(action=InterceptorAction.PASS)
            state.turn_data[key] = True
            new_event = event.copy()
            new_event.payload["amount"] = max(0, amount - n)
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event,
            )

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=_filter,
            handler=_handler,
            duration="while_on_battlefield",
        )]
    return setup


def _all_in_setup(n: int):
    """All-In: ETB tempo payoff if this play left you with no Liquidity."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def etb(event: Event, state: GameState) -> list[Event]:
            player = _player(state, obj.controller)
            if player and int(player.mana_crystals_available or 0) == 0:
                return [
                    Event(
                        type=EventType.PT_MODIFICATION,
                        payload={
                            "object_id": obj.id,
                            "power_mod": n,
                            "toughness_mod": 0,
                            "duration": "end_of_turn",
                            "_tag": "finm_all_in",
                        },
                        source=obj.id,
                        controller=obj.controller,
                    ),
                ]
            return []

        return [make_etb_trigger(obj, etb)]
    return setup


def _restructure_setup(n: int):
    """Restructure N: when this Trader is liquidated, regain N Liquidity."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, state: GameState) -> list[Event]:
            _gain_liquidity(state, obj.controller, n)
            return [Event(
                    type=EventType.FIN_CAPITAL_CALL,
                    payload={"player": obj.controller, "amount": n, "kind": "restructure"},
                    source=obj.id,
                    controller=obj.controller,
            )]

        return [make_death_trigger(obj, effect)]
    return setup


def _buyback_setup(n: int):
    """Buyback N: this Trader gets a permanent +1/+1 counter after your Nth spell."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def _filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.FIN_PLAY_CARD:
                return False
            if event.payload.get("controller") != obj.controller and event.payload.get("player") != obj.controller:
                return False
            cast_id = event.payload.get("object_id") or event.payload.get("card_id")
            cast_obj = state.objects.get(cast_id)
            if cast_obj is None:
                return False
            return bool(
                CardType.FIN_ORDER in cast_obj.characteristics.types
                or CardType.FIN_STRATEGY in cast_obj.characteristics.types
            )

        def _handler(event: Event, state: GameState) -> InterceptorResult:
            key = f"finm_buyback_count_{obj.id}"
            count = int(state.turn_data.get(key, 0) or 0) + 1
            state.turn_data[key] = count
            if count % max(1, n) != 0:
                return InterceptorResult(action=InterceptorAction.PASS)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.COUNTER_ADDED,
                    payload={"object_id": obj.id, "counter_type": "+1/+1", "amount": 1},
                    source=obj.id,
                    controller=obj.controller,
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
    return setup


def _lord_setup(power_bonus: int = 0, toughness_bonus: int = 1):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors: list[Interceptor] = []
        if power_bonus:
            interceptors.append(_make_query_stat_interceptor(
                obj,
                "power",
                lambda s: power_bonus,
                lambda target, s: (
                    target.id != obj.id
                    and target.controller == obj.controller
                    and CardType.FIN_TRADER in target.characteristics.types
                ),
            ))
        if toughness_bonus:
            interceptors.append(_make_query_stat_interceptor(
                obj,
                "toughness",
                lambda s: toughness_bonus,
                lambda target, s: (
                    target.id != obj.id
                    and target.controller == obj.controller
                    and CardType.FIN_TRADER in target.characteristics.types
                ),
            ))
        return interceptors
    return setup


def _derivative_setup(power_bonus: int, toughness_bonus: int):
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        return [
            _make_query_stat_interceptor(
                obj,
                "power",
                lambda s: power_bonus,
                lambda target, s: getattr(obj.state, "attached_to", None) == target.id,
            ),
            _make_query_stat_interceptor(
                obj,
                "toughness",
                lambda s: toughness_bonus,
                lambda target, s: getattr(obj.state, "attached_to", None) == target.id,
            ),
        ]
    return setup


def _make_resolve(effect: str, n: int):
    def resolve(event: Event, state: GameState) -> list[Event]:
        controller = event.payload.get("controller") or event.controller
        source_id = event.payload.get("source_id") or event.source or ""
        if not controller:
            return []
        if effect == "draw":
            return [Event(type=EventType.DRAW, payload={"player": controller, "count": n}, source=source_id, controller=controller)]
        if effect == "liquidity":
            _gain_liquidity(state, controller, n)
            return [Event(type=EventType.FIN_CAPITAL_CALL, payload={"player": controller, "amount": n, "kind": "liquidity"}, source=source_id, controller=controller)]
        if effect == "capital":
            return [Event(type=EventType.LIFE_CHANGE, payload={"player": controller, "amount": n}, source=source_id, controller=controller)]
        if effect == "burn":
            target_id = _target_from_event(event)
            if not target_id:
                target_id = _best_enemy_trader(state, controller)
            if target_id:
                return [Event(type=EventType.DAMAGE, payload={"target": target_id, "amount": n, "source": source_id, "is_finance": True}, source=source_id, controller=controller)]
            opp = _other_player(state, controller)
            if opp:
                return [Event(type=EventType.LIFE_CHANGE, payload={"player": opp, "amount": -n, "reason": "finm_burn"}, source=source_id, controller=controller)]
        if effect == "destroy_small":
            max_defense = n + 1
            explicit_target_id = _target_from_event(event)
            if explicit_target_id:
                if not _is_legal_enemy_trader_under_defense(state, controller, explicit_target_id, max_defense):
                    return []
                target_id = explicit_target_id
            else:
                target_id = _weakest_enemy_trader(state, controller, max_defense)
            if target_id:
                return [Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": target_id, "reason": "finm_resolution"}, source=source_id, controller=controller)]
        if effect == "sweeper":
            events: list[Event] = []
            bf = _battlefield(state)
            if bf:
                for oid in list(bf.objects):
                    obj = state.objects.get(oid)
                    if _is_trader(obj) and _effective_defense(obj, state) <= n:
                        events.append(Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": oid, "reason": "finm_sweeper"}, source=source_id, controller=controller))
            return events
        return []

    return resolve


def _setup_for_spec(spec: CardSpec):
    if spec.mechanic == "covenant":
        return _covenant_setup(spec.n)
    if spec.mechanic == "coupon":
        return _coupon_setup(spec.n)
    if spec.mechanic == "hedge":
        return _hedge_setup(spec.n)
    if spec.mechanic == "all_in":
        return _all_in_setup(spec.n)
    if spec.mechanic == "restructure":
        return _restructure_setup(spec.n)
    if spec.mechanic == "buyback":
        return _buyback_setup(spec.n)
    if spec.mechanic == "lord_p":
        return _lord_setup(power_bonus=spec.n, toughness_bonus=0)
    if spec.mechanic == "lord_t":
        return _lord_setup(power_bonus=0, toughness_bonus=spec.n)
    if spec.mechanic == "derivative":
        return _derivative_setup(max(0, spec.power or 0), max(0, spec.toughness or 0))
    return None


def _resolve_for_spec(spec: CardSpec):
    if spec.mechanic in {"draw", "liquidity", "capital", "burn", "destroy_small", "sweeper"}:
        return _make_resolve(spec.mechanic, spec.n)
    return None


def _make_definition(spec: CardSpec) -> CardDefinition:
    type_map = {
        "trader": CardType.FIN_TRADER,
        "order": CardType.FIN_ORDER,
        "strategy": CardType.FIN_STRATEGY,
        "asset": CardType.FIN_ASSET,
        "structure": CardType.FIN_STRUCTURE,
        "derivative": CardType.FIN_DERIVATIVE,
    }
    card_type = type_map[spec.kind]
    subtypes = {spec.kind.title(), spec.archetype} if spec.archetype else {spec.kind.title()}
    abilities = []
    if "Trample" in spec.text:
        abilities.append({"keyword": "trample"})
    chars = Characteristics(
        types={card_type},
        subtypes=subtypes,
        mana_cost=_mana(spec.cost),
        power=spec.power,
        toughness=spec.toughness,
        abilities=abilities,
    )
    return CardDefinition(
        name=spec.name,
        mana_cost=_mana(spec.cost),
        characteristics=chars,
        domain=DOMAIN,
        text=spec.text,
        rarity=spec.rarity,
        setup_interceptors=_setup_for_spec(spec),
        resolve=_resolve_for_spec(spec),
    )


def _curve_trader_specs(prefix: str, archetype: str, mechanic: str, ns: list[int], bodies: list[tuple[int, int, int]], rarity: str) -> list[CardSpec]:
    specs: list[CardSpec] = []
    desks = [
        "Analyst", "Associate", "Specialist", "Director", "Partner",
        "Architect", "Operator", "Controller", "Broker", "Chief",
    ]
    for i, (cost, power, toughness) in enumerate(bodies):
        n = ns[i % len(ns)]
        label = desks[i % len(desks)]
        text = {
            "covenant": f"Covenant {n}. At your Pre-Market, if your Capital is not ahead, gain {n} Liquidity.",
            "coupon": f"Coupon {n}. At your Pre-Market, gain {n} Liquidity.",
            "hedge": f"Hedge {n}. Once each turn, prevent {n} damage to this Trader.",
            "all_in": f"All-In {n}. When this enters with no Liquidity remaining, it gets +{n}/+0 this turn.",
            "restructure": f"Restructure {n}. When this is liquidated, regain {n} Liquidity.",
            "buyback": f"Buyback {n}. Each {n}th Order or Strategy you cast gives this a +1/+1 counter.",
        }[mechanic]
        specs.append(CardSpec(
            name=f"{prefix} {label}",
            kind="trader",
            cost=cost,
            power=power,
            toughness=toughness,
            text=text,
            rarity=rarity if i >= 6 else "common",
            mechanic=mechanic,
            n=n,
            archetype=archetype,
        ))
    return specs


def _spell_specs(prefix: str, archetype: str, entries: list[tuple[str, str, int, int, str, str]]) -> list[CardSpec]:
    return [
        CardSpec(
            name=f"{prefix} {name}",
            kind=kind,
            cost=cost,
            power=None,
            toughness=None,
            text=text,
            rarity=rarity,
            mechanic=mechanic,
            n=n,
            archetype=archetype,
        )
        for name, kind, cost, n, mechanic, rarity, text in entries
    ]


def _permanent_specs(prefix: str, archetype: str, entries: list[tuple[str, str, int, int | None, int | None, str, int, str, str]]) -> list[CardSpec]:
    return [
        CardSpec(
            name=f"{prefix} {name}",
            kind=kind,
            cost=cost,
            power=power,
            toughness=toughness,
            text=text,
            rarity=rarity,
            mechanic=mechanic,
            n=n,
            archetype=archetype,
        )
        for name, kind, cost, power, toughness, mechanic, n, rarity, text in entries
    ]


def _build_specs() -> list[CardSpec]:
    specs: list[CardSpec] = []

    specs += _curve_trader_specs(
        "Covenant",
        "Credit",
        "covenant",
        [1, 1, 2, 2, 3],
        [(1, 1, 2), (2, 2, 3), (2, 1, 4), (3, 3, 3), (3, 2, 5), (4, 4, 4), (4, 3, 6), (5, 5, 5), (6, 5, 7), (7, 7, 7)],
        "rare",
    )
    specs += _spell_specs("Covenant", "Credit", [
        ("Amendment", "order", 1, 1, "capital", "common", "Gain 1 Capital."),
        ("Standstill", "order", 2, 2, "destroy_small", "uncommon", "Liquidate a small hostile Trader."),
        ("Rescue Facility", "strategy", 3, 2, "draw", "uncommon", "Draw 2 cards."),
        ("Creditor Committee", "strategy", 4, 3, "capital", "rare", "Gain 3 Capital."),
        ("Debtor-in-Possession Loan", "strategy", 4, 4, "liquidity", "rare", "Gain 4 Liquidity this turn."),
        ("Forbearance", "order", 2, 2, "capital", "common", "Gain 2 Capital."),
        ("Cramdown", "strategy", 5, 3, "sweeper", "rare", "Liquidate all Traders with Defense 3 or less."),
        ("Chapter Eleven", "strategy", 6, 4, "draw", "mythic", "Draw 4 cards."),
    ])
    specs += _permanent_specs("Covenant", "Credit", [
        ("Indenture Archive", "asset", 2, None, None, "coupon", 1, "uncommon", "Coupon 1."),
        ("Collateral Trustee", "structure", 3, None, None, "coupon", 1, "uncommon", "Coupon 1."),
        ("Seniority Ladder", "asset", 3, None, None, "lord_t", 1, "rare", "Other Traders you control get +0/+1."),
        ("Recovery Waterfall", "structure", 4, None, None, "coupon", 2, "rare", "Coupon 2."),
        ("Priming Lien", "derivative", 2, 1, 2, "derivative", 0, "common", "Attached Trader gets +1/+2."),
        ("Make-Whole Warrant", "derivative", 3, 2, 1, "derivative", 0, "uncommon", "Attached Trader gets +2/+1."),
        ("Secured Note Shell", "derivative", 4, 1, 3, "derivative", 0, "rare", "Attached Trader gets +1/+3."),
        ("Distressed Exchange", "asset", 5, None, None, "coupon", 2, "mythic", "Coupon 2."),
        ("Exit Financing Desk", "structure", 5, None, None, "lord_t", 2, "mythic", "Other Traders you control get +0/+2."),
        ("Covenant-lite Package", "asset", 2, None, None, "covenant", 1, "common", "Covenant 1."),
        ("Lien Search", "order", 1, None, None, "draw", 1, "common", "Draw a card."),
        ("Recovery Model", "strategy", 3, None, None, "draw", 2, "uncommon", "Draw 2 cards."),
    ])

    specs += _curve_trader_specs(
        "Coupon",
        "Treasury",
        "coupon",
        [1, 1, 1, 2],
        [(1, 1, 2), (2, 2, 3), (2, 1, 4), (3, 2, 4), (3, 3, 4), (4, 3, 5), (4, 4, 4), (5, 4, 6), (6, 5, 7), (7, 6, 8)],
        "rare",
    )
    specs += _spell_specs("Coupon", "Treasury", [
        ("Treasury Bill", "order", 1, 1, "liquidity", "common", "Gain 1 Liquidity this turn."),
        ("Cash Sweep", "order", 2, 2, "capital", "common", "Gain 2 Capital."),
        ("Bond Ladder", "strategy", 3, 2, "draw", "uncommon", "Draw 2 cards."),
        ("Repo Window", "strategy", 3, 3, "liquidity", "uncommon", "Gain 3 Liquidity this turn."),
        ("Duration Match", "order", 2, 2, "destroy_small", "uncommon", "Liquidate a small hostile Trader."),
        ("Convex Carry", "strategy", 5, 5, "capital", "rare", "Gain 5 Capital."),
        ("Auction Calendar", "strategy", 4, 3, "draw", "rare", "Draw 3 cards."),
        ("Reserve Drain", "order", 3, 3, "burn", "rare", "Deal 3 damage to a hostile Trader."),
    ])
    specs += _permanent_specs("Coupon", "Treasury", [
        ("Bill Vault", "asset", 2, None, None, "coupon", 1, "common", "Coupon 1."),
        ("Funding Desk", "structure", 3, None, None, "coupon", 1, "uncommon", "Coupon 1."),
        ("Carry Warehouse", "asset", 4, None, None, "coupon", 2, "rare", "Coupon 2."),
        ("Treasury Operations", "structure", 5, None, None, "coupon", 2, "rare", "Coupon 2."),
        ("Duration Sleeve", "derivative", 2, 0, 3, "derivative", 0, "common", "Attached Trader gets +0/+3."),
        ("Repo Haircut", "derivative", 2, 1, 1, "derivative", 0, "common", "Attached Trader gets +1/+1."),
        ("Collateral Upgrade", "derivative", 3, 1, 2, "derivative", 0, "uncommon", "Attached Trader gets +1/+2."),
        ("Yield Curve Console", "structure", 4, None, None, "lord_t", 1, "rare", "Other Traders you control get +0/+1."),
        ("Central Bank Swap Line", "asset", 6, None, None, "coupon", 3, "mythic", "Coupon 3."),
        ("Treasury Futures Pit", "structure", 4, None, None, "lord_p", 1, "rare", "Other Traders you control get +1/+0."),
        ("Cash Forecast", "order", 1, None, None, "draw", 1, "common", "Draw a card."),
        ("Collateral Optimization", "strategy", 4, None, None, "liquidity", 4, "rare", "Gain 4 Liquidity this turn."),
    ])

    specs += _curve_trader_specs(
        "Hedge",
        "Risk",
        "hedge",
        [1],
        [(1, 1, 2), (2, 2, 3), (2, 1, 4), (3, 2, 5), (3, 3, 4), (4, 3, 6), (4, 4, 5), (5, 4, 7), (6, 5, 8), (7, 6, 9)],
        "rare",
    )
    specs += _spell_specs("Hedge", "Risk", [
        ("Stop Loss", "order", 1, 2, "destroy_small", "common", "Liquidate a small hostile Trader."),
        ("Variance Cap", "order", 2, 2, "capital", "common", "Gain 2 Capital."),
        ("Tail Event Map", "strategy", 3, 2, "draw", "uncommon", "Draw 2 cards."),
        ("VaR Breach", "strategy", 4, 3, "sweeper", "rare", "Liquidate all Traders with Defense 3 or less."),
        ("Stress Scenario", "order", 3, 3, "burn", "uncommon", "Deal 3 damage to a hostile Trader."),
        ("Risk Committee", "strategy", 4, 3, "draw", "rare", "Draw 3 cards."),
        ("Insurance Premium", "order", 2, 2, "capital", "uncommon", "Gain 2 Capital."),
        ("Model Override", "strategy", 5, 4, "destroy_small", "rare", "Liquidate a medium hostile Trader."),
    ])
    specs += _permanent_specs("Hedge", "Risk", [
        ("Risk Dashboard", "asset", 2, None, None, "lord_t", 1, "uncommon", "Other Traders you control get +0/+1."),
        ("Control Room", "structure", 3, None, None, "coupon", 1, "uncommon", "Coupon 1."),
        ("Insurance Book", "asset", 3, None, None, "coupon", 1, "rare", "Coupon 1."),
        ("Capital Buffer", "structure", 4, None, None, "coupon", 2, "rare", "Coupon 2."),
        ("Put Spread", "derivative", 2, 0, 2, "derivative", 0, "common", "Attached Trader gets +0/+2."),
        ("Tail Hedge Sleeve", "derivative", 3, 1, 3, "derivative", 0, "rare", "Attached Trader gets +1/+3."),
        ("Stop-Out Harness", "derivative", 2, 1, 1, "derivative", 0, "common", "Attached Trader gets +1/+1."),
        ("Scenario Library", "asset", 4, None, None, "draw", 1, "rare", "Draw a card."),
        ("Chief Risk Office", "structure", 5, None, None, "lord_t", 2, "mythic", "Other Traders you control get +0/+2."),
        ("Catastrophe Bond", "asset", 5, None, None, "coupon", 2, "mythic", "Coupon 2."),
        ("Limit Check", "order", 1, None, None, "draw", 1, "common", "Draw a card."),
        ("Exposure Report", "strategy", 3, None, None, "draw", 2, "uncommon", "Draw 2 cards."),
    ])

    specs += _curve_trader_specs(
        "All-In",
        "Activist",
        "all_in",
        [1, 1, 2, 2, 3],
        [(1, 1, 1), (2, 1, 2), (2, 2, 2), (3, 2, 3), (3, 3, 3), (4, 3, 4), (4, 4, 4), (5, 4, 5), (6, 5, 5), (7, 6, 6)],
        "rare",
    )
    specs += _spell_specs("All-In", "Activist", [
        ("Tender Offer", "order", 1, 2, "burn", "common", "Deal 2 damage to a hostile Trader."),
        ("Proxy Fight", "strategy", 3, 3, "burn", "uncommon", "Deal 3 damage to a hostile Trader."),
        ("Board Seat", "strategy", 2, 2, "draw", "uncommon", "Draw 2 cards."),
        ("Hostile Bid", "order", 3, 4, "destroy_small", "rare", "Liquidate a medium hostile Trader."),
        ("Poison Pill", "order", 2, 2, "capital", "common", "Gain 2 Capital."),
        ("Dawn Raid", "strategy", 4, 3, "sweeper", "rare", "Liquidate all Traders with Defense 3 or less."),
        ("Consent Solicitation", "strategy", 4, 3, "draw", "rare", "Draw 3 cards."),
        ("Greenmail Exit", "order", 2, 3, "liquidity", "uncommon", "Gain 3 Liquidity this turn."),
    ])
    specs += _permanent_specs("All-In", "Activist", [
        ("Proxy Advisor", "asset", 2, None, None, "lord_p", 1, "uncommon", "Other Traders you control get +1/+0."),
        ("War Room", "structure", 3, None, None, "lord_p", 1, "rare", "Other Traders you control get +1/+0."),
        ("Voting Trust", "asset", 3, None, None, "coupon", 1, "uncommon", "Coupon 1."),
        ("Boardroom Floor", "structure", 4, None, None, "coupon", 2, "rare", "Coupon 2."),
        ("Control Premium", "derivative", 2, 2, 0, "derivative", 0, "common", "Attached Trader gets +2/+0."),
        ("Poison Pill Wrap", "derivative", 3, 1, 2, "derivative", 0, "uncommon", "Attached Trader gets +1/+2."),
        ("Golden Parachute", "derivative", 4, 2, 2, "derivative", 0, "rare", "Attached Trader gets +2/+2."),
        ("Activist Letter", "asset", 2, None, None, "buyback", 2, "rare", "Buyback 2."),
        ("Settlement Agreement", "structure", 5, None, None, "coupon", 2, "mythic", "Coupon 2."),
        ("Control Bloc", "asset", 5, None, None, "lord_p", 2, "mythic", "Other Traders you control get +2/+0."),
        ("Schedule 13D", "order", 1, None, None, "draw", 1, "common", "Draw a card."),
        ("White Knight Search", "strategy", 3, None, None, "draw", 2, "uncommon", "Draw 2 cards."),
    ])

    specs += _curve_trader_specs(
        "Restructure",
        "Distressed",
        "restructure",
        [1, 1, 1, 1, 2],
        [(1, 1, 1), (2, 1, 2), (2, 1, 3), (3, 2, 2), (3, 2, 3), (4, 3, 3), (4, 3, 4), (5, 4, 4), (6, 5, 5), (7, 6, 6)],
        "rare",
    )
    specs += _spell_specs("Restructure", "Distressed", [
        ("Fire Sale", "order", 1, 2, "burn", "common", "Deal 2 damage to a hostile Trader."),
        ("Asset Strip", "strategy", 3, 3, "destroy_small", "uncommon", "Liquidate a small hostile Trader."),
        ("Debtor Rollup", "strategy", 2, 2, "liquidity", "common", "Gain 2 Liquidity this turn."),
        ("Liquidation Trust", "strategy", 4, 3, "draw", "rare", "Draw 3 cards."),
        ("Stalking Horse", "order", 2, 2, "draw", "uncommon", "Draw 2 cards."),
        ("Foreclosure Wave", "strategy", 5, 3, "sweeper", "rare", "Liquidate all Traders with Defense 3 or less."),
        ("Haircut Notice", "order", 2, 3, "burn", "common", "Deal 3 damage to a hostile Trader."),
        ("Claims Trade", "strategy", 4, 4, "liquidity", "rare", "Gain 4 Liquidity this turn."),
    ])
    specs += _permanent_specs("Restructure", "Distressed", [
        ("Claims Register", "asset", 2, None, None, "coupon", 1, "common", "Coupon 1."),
        ("Auction Block", "structure", 3, None, None, "lord_p", 1, "uncommon", "Other Traders you control get +1/+0."),
        ("Workout Desk", "asset", 3, None, None, "covenant", 1, "uncommon", "Covenant 1."),
        ("Liquidation Court", "structure", 4, None, None, "coupon", 2, "rare", "Coupon 2."),
        ("Claims Warrant", "derivative", 2, 1, 1, "derivative", 0, "common", "Attached Trader gets +1/+1."),
        ("DIP Rollup Sleeve", "derivative", 3, 2, 1, "derivative", 0, "uncommon", "Attached Trader gets +2/+1."),
        ("Credit Bid Token", "derivative", 4, 3, 0, "derivative", 0, "rare", "Attached Trader gets +3/+0."),
        ("Distress Screen", "asset", 4, None, None, "draw", 1, "rare", "Draw a card."),
        ("Bankruptcy Courtroom", "structure", 5, None, None, "lord_p", 2, "mythic", "Other Traders you control get +2/+0."),
        ("Fulcrum Security", "asset", 5, None, None, "coupon", 2, "mythic", "Coupon 2."),
        ("Claim Diligence", "order", 1, None, None, "draw", 1, "common", "Draw a card."),
        ("Plan Sponsor", "strategy", 3, None, None, "draw", 2, "uncommon", "Draw 2 cards."),
    ])

    specs += _curve_trader_specs(
        "Buyback",
        "M&A",
        "buyback",
        [3, 3, 4, 4],
        [(1, 1, 1), (2, 1, 2), (2, 2, 2), (3, 2, 3), (3, 2, 4), (4, 3, 4), (4, 3, 5), (5, 4, 5), (6, 5, 5), (7, 6, 6)],
        "rare",
    )
    specs += _spell_specs("Buyback", "M&A", [
        ("Term Sheet", "order", 1, 1, "draw", "common", "Draw a card."),
        ("Fairness Opinion", "order", 2, 2, "draw", "uncommon", "Draw 2 cards."),
        ("Merger Model", "strategy", 3, 2, "draw", "uncommon", "Draw 2 cards."),
        ("Synergy Capture", "strategy", 4, 4, "liquidity", "rare", "Gain 4 Liquidity this turn."),
        ("Breakup Fee", "order", 2, 2, "burn", "common", "Deal 2 damage to a hostile Trader."),
        ("Regulatory Approval", "strategy", 5, 4, "destroy_small", "rare", "Liquidate a medium hostile Trader."),
        ("Take-Private", "strategy", 6, 4, "sweeper", "mythic", "Liquidate all Traders with Defense 4 or less."),
        ("Accretion Math", "order", 2, 2, "liquidity", "common", "Gain 2 Liquidity this turn."),
    ])
    specs += _permanent_specs("Buyback", "M&A", [
        ("Data Room", "asset", 2, None, None, "buyback", 2, "uncommon", "Buyback 2."),
        ("Integration Office", "structure", 3, None, None, "lord_t", 1, "uncommon", "Other Traders you control get +0/+1."),
        ("Synergy Ledger", "asset", 3, None, None, "coupon", 1, "rare", "Coupon 1."),
        ("Deal Desk", "structure", 4, None, None, "lord_p", 1, "rare", "Other Traders you control get +1/+0."),
        ("Earnout Clause", "derivative", 2, 1, 1, "derivative", 0, "common", "Attached Trader gets +1/+1."),
        ("Bridge Loan", "derivative", 3, 2, 1, "derivative", 0, "uncommon", "Attached Trader gets +2/+1."),
        ("Synergy Harness", "derivative", 4, 2, 2, "derivative", 0, "rare", "Attached Trader gets +2/+2."),
        ("Board Approval Room", "structure", 5, None, None, "coupon", 2, "mythic", "Coupon 2."),
        ("Roll-Up Platform", "asset", 5, None, None, "lord_t", 2, "mythic", "Other Traders you control get +0/+2."),
        ("Tender Mechanics", "asset", 2, None, None, "buyback", 1, "rare", "Buyback 1."),
        ("Due Diligence", "order", 1, None, None, "draw", 1, "common", "Draw a card."),
        ("Closing Dinner", "strategy", 3, None, None, "capital", 3, "uncommon", "Gain 3 Capital."),
    ])

    return specs


FINM_SPECS = _build_specs()
FINM_CARDS: dict[str, CardDefinition] = {
    spec.name: _make_definition(spec)
    for spec in FINM_SPECS
}

assert len(FINM_CARDS) == EXPECTED_CARD_COUNT, (
    f"FINM should contain {EXPECTED_CARD_COUNT} cards, got {len(FINM_CARDS)}"
)
assert len(FINM_CARDS) == len({spec.name for spec in FINM_SPECS}), "FINM card names must be unique"

__all__ = ["FINM_CARDS", "FINM_SPECS", "EXPECTED_CARD_COUNT"]
