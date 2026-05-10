"""Shared mechanics for ABYS — Abyssal Expanse.

The expansion uses Depths-native mechanics that the current engine can
simulate:

* Vent: when this Vessel dives to DEEP/CRUSH, gain charges or pump it.
* Salvage: when this Vessel is sunk, gain charges, draw, or leave a Drone.
* Formation N: attack bonuses if enough friendly Vessels share its band.
* Scan: ETB/action effects that mark opposing Vessels detected.
* Pressure: static bonuses while the Vessel is at DEEP/CRUSH.

Some rules text talks about "choosing" the best target; the simulation uses a
deterministic target choice (lowest hull or first legal object) because the
Depths AI/harness does not yet expose per-card target prompts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Iterable, Optional

from src.cards.depths.submarine_fleet._factories import (
    DepthBand,
    make_action as _subs_action,
    make_crew as _subs_crew,
    make_depths_dive_phase_trigger,
    make_depths_end_phase_trigger,
    make_doctrine as _subs_doctrine,
    make_mine as _subs_mine,
    make_vessel as _subs_vessel,
    make_weapon as _subs_weapon,
)
from src.cards.interceptor_helpers import (
    make_attack_trigger,
    make_damage_trigger,
    make_death_trigger,
    make_dynamic_pt_boost,
    make_etb_trigger,
    make_keyword_grant,
    make_static_pt_boost,
)
from src.engine import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    ZoneType,
)
from src.engine.depths import get_flagship, is_vessel

ABYS_CODE = "ABYS"


def compose_setups(*setups):
    active = [setup for setup in setups if setup is not None]
    if not active:
        return None

    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        out: list[Interceptor] = []
        for setup in active:
            out.extend(setup(obj, state) or [])
        return out

    return _setup


def _domain(card):
    card.domain = ABYS_CODE
    return card


def abys_vessel(*args, **kwargs):
    return _domain(_subs_vessel(*args, **kwargs))


def abys_crew(*args, **kwargs):
    return _domain(_subs_crew(*args, **kwargs))


def abys_weapon(*args, **kwargs):
    return _domain(_subs_weapon(*args, **kwargs))


def abys_mine(*args, **kwargs):
    return _domain(_subs_mine(*args, **kwargs))


def abys_action(*args, **kwargs):
    return _domain(_subs_action(*args, **kwargs))


def abys_doctrine(*args, **kwargs):
    return _domain(_subs_doctrine(*args, **kwargs))


def _battlefield(state: GameState) -> list[GameObject]:
    zone = state.zones.get("battlefield")
    if not zone:
        return []
    return [state.objects[oid] for oid in list(zone.objects) if oid in state.objects]


def own_vessels(controller: str, state: GameState) -> list[GameObject]:
    return [
        obj for obj in _battlefield(state)
        if obj.controller == controller and is_vessel(obj)
    ]


def opposing_vessels(controller: str, state: GameState) -> list[GameObject]:
    return [
        obj for obj in _battlefield(state)
        if obj.controller != controller and is_vessel(obj)
    ]


def opposing_flagship(controller: str, state: GameState) -> GameObject | None:
    for pid in state.players:
        if pid == controller:
            continue
        flag = get_flagship(pid, state)
        if flag is not None:
            return flag
    return None


def _charges(player_id: str, source_id: str, *, tc: int = 0, sc: int = 0) -> Event:
    return Event(
        type=EventType.DEPTHS_RESUPPLY,
        payload={
            "player": player_id,
            "tc_gained": max(0, int(tc)),
            "sc_gained": max(0, int(sc)),
            "reason": "abys_card_effect",
        },
        source=source_id,
        controller=player_id,
    )


def _add_charges(state: GameState, player_id: str, *, tc: int = 0, sc: int = 0) -> None:
    player = state.players.get(player_id)
    if player is None:
        return
    player.tc = min(10, int(getattr(player, "tc", 0)) + max(0, int(tc)))
    player.sc = min(10, int(getattr(player, "sc", 0)) + max(0, int(sc)))


def _draw(player_id: str, source_id: str, count: int = 1) -> Event:
    return Event(
        type=EventType.DRAW,
        payload={"player": player_id, "count": max(1, int(count))},
        source=source_id,
        controller=player_id,
    )


def _pt(target_id: str, source_id: str, *, power: int = 0, hull: int = 0) -> Event:
    return Event(
        type=EventType.PT_MODIFICATION,
        payload={
            "object_id": target_id,
            "power_mod": int(power),
            "toughness_mod": int(hull),
            "duration": "end_of_turn",
        },
        source=source_id,
    )


def _damage(target_id: str, source_id: str, amount: int) -> Event:
    return Event(
        type=EventType.DAMAGE,
        payload={
            "target": target_id,
            "amount": max(0, int(amount)),
            "source": source_id,
            "is_combat": False,
            "reason": "abys_card_effect",
        },
        source=source_id,
    )


def _detect(target: GameObject, source_id: str) -> Event:
    return Event(
        type=EventType.DEPTHS_DETECT,
        payload={"object_id": target.id, "duration": "end_of_turn"},
        source=source_id,
        controller=target.controller,
    )


def _drone(controller: str, source_id: str, *, name: str = "Abyss Drone") -> Event:
    return Event(
        type=EventType.OBJECT_CREATED,
        payload={
            "name": name,
            "controller": controller,
            "types": {CardType.DEPTHS_VESSEL},
            "subtypes": {"Drone"},
            "power": 1,
            "toughness": 1,
            "keywords": ["homing"],
            "depth_band": DepthBand.SURFACE,
            "is_token": True,
        },
        source=source_id,
        controller=controller,
    )


def _lowest_hull(vessels: Iterable[GameObject]) -> GameObject | None:
    pool = list(vessels)
    if not pool:
        return None
    return min(
        pool,
        key=lambda v: int(v.characteristics.toughness or 0) - int(getattr(v.state, "damage", 0) or 0),
    )


def mark_detected(vessel: GameObject, *, duration: str = "end_of_turn") -> None:
    vessel.state.detected = True
    vessel.state.detected_until = duration


def make_salvage_setup(
    *,
    tc: int = 0,
    sc: int = 0,
    draw: int = 0,
    drone: bool = False,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(_event: Event, _state: GameState) -> list[Event]:
            events: list[Event] = []
            if tc or sc:
                _add_charges(_state, obj.controller, tc=tc, sc=sc)
                events.append(_charges(obj.controller, obj.id, tc=tc, sc=sc))
            for _ in range(max(0, draw)):
                events.append(_draw(obj.controller, obj.id, 1))
            if drone:
                events.append(_drone(obj.controller, obj.id))
            return events

        return [make_death_trigger(obj, effect)]

    return _setup


def make_vent_setup(
    *,
    tc: int = 0,
    sc: int = 1,
    pump: int = 0,
    draw: int = 0,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def _filter(event: Event, _state: GameState, source: GameObject) -> bool:
            return (
                event.type == EventType.DEPTHS_DIVE
                and event.payload.get("object_id") == source.id
                and event.payload.get("to_band") in {DepthBand.DEEP, DepthBand.CRUSH}
            )

        def effect(_event: Event, _state: GameState) -> list[Event]:
            events: list[Event] = []
            if tc or sc:
                _add_charges(_state, obj.controller, tc=tc, sc=sc)
                events.append(_charges(obj.controller, obj.id, tc=tc, sc=sc))
            if pump:
                events.append(_pt(obj.id, obj.id, power=pump))
            for _ in range(max(0, draw)):
                events.append(_draw(obj.controller, obj.id, 1))
            return events

        return [_depth_change_trigger(obj, effect, _filter)]

    return _setup


def _depth_change_trigger(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Callable[[Event, GameState, GameObject], bool],
) -> Interceptor:
    from src.engine import InterceptorAction, InterceptorPriority, InterceptorResult, new_id

    def _filter(event: Event, state: GameState) -> bool:
        source = state.objects.get(obj.id)
        return bool(source and source.zone == ZoneType.BATTLEFIELD and filter_fn(event, state, source))

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state) or [],
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


def make_formation_attack_setup(
    *,
    n: int = 2,
    power: int = 1,
    draw: int = 0,
    flag_damage: int = 0,
    same_depth_only: bool = True,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(_event: Event, st: GameState) -> list[Event]:
            source = st.objects.get(obj.id)
            if source is None:
                return []
            allies = [
                v for v in own_vessels(obj.controller, st)
                if v.id != obj.id
                and getattr(v.state, "attacking", False)
                and (not same_depth_only or v.state.depth_band == source.state.depth_band)
            ]
            if len(allies) < n:
                return []
            events: list[Event] = []
            if power:
                events.append(_pt(obj.id, obj.id, power=power))
            for _ in range(max(0, draw)):
                events.append(_draw(obj.controller, obj.id, 1))
            if flag_damage:
                flag = opposing_flagship(obj.controller, st)
                if flag:
                    events.append(_damage(flag.id, obj.id, flag_damage))
            return events

        return [make_attack_trigger(obj, effect)]

    return _setup


def make_scan_etb_setup(
    *,
    count: int = 1,
    damage_detected: int = 0,
    draw_if_any: bool = False,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(_event: Event, st: GameState) -> list[Event]:
            targets = [v for v in opposing_vessels(obj.controller, st) if "Flagship" not in v.characteristics.subtypes]
            targets = targets[:max(0, count)]
            events: list[Event] = []
            for target in targets:
                mark_detected(target)
                events.append(_detect(target, obj.id))
                if damage_detected:
                    events.append(_damage(target.id, obj.id, damage_detected))
            if draw_if_any and targets:
                events.append(_draw(obj.controller, obj.id, 1))
            return events

        return [make_etb_trigger(obj, effect)]

    return _setup


def make_pressure_setup(
    *,
    power: int = 1,
    hull: int = 0,
    keywords: Optional[Iterable[str]] = None,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def affects(target: GameObject, _state: GameState) -> bool:
            return (
                target.id == obj.id
                and target.zone == ZoneType.BATTLEFIELD
                and target.state.depth_band in {DepthBand.DEEP, DepthBand.CRUSH}
            )

        out: list[Interceptor] = []
        out.extend(make_static_pt_boost(obj, power, hull, affects))
        if keywords:
            out.append(make_keyword_grant(obj, [str(k) for k in keywords], affects))
        return out

    return _setup


def make_same_depth_lord_setup(
    *,
    subtype: str | None = None,
    power: int = 1,
    hull: int = 0,
    keyword: str | None = None,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def affects(target: GameObject, _state: GameState) -> bool:
            if target.controller != obj.controller or not is_vessel(target):
                return False
            if target.zone != ZoneType.BATTLEFIELD:
                return False
            if target.state.depth_band != obj.state.depth_band:
                return False
            if subtype and subtype not in target.characteristics.subtypes:
                return False
            return True

        out: list[Interceptor] = []
        out.extend(make_static_pt_boost(obj, power, hull, affects))
        if keyword:
            out.append(make_keyword_grant(obj, [keyword], affects))
        return out

    return _setup


def make_depth_end_charge_setup(*, tc: int = 0, sc: int = 0, drones: int = 0):
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(_event: Event, _state: GameState) -> list[Event]:
            events: list[Event] = []
            if tc or sc:
                _add_charges(_state, obj.controller, tc=tc, sc=sc)
                events.append(_charges(obj.controller, obj.id, tc=tc, sc=sc))
            for _ in range(max(0, drones)):
                events.append(_drone(obj.controller, obj.id))
            return events

        return [make_depths_end_phase_trigger(obj, effect)]

    return _setup


def make_dive_phase_scan_setup(*, count: int = 1):
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(_event: Event, st: GameState) -> list[Event]:
            targets = opposing_vessels(obj.controller, st)[:count]
            events: list[Event] = []
            for target in targets:
                mark_detected(target)
                events.append(_detect(target, obj.id))
            return events

        return [make_depths_dive_phase_trigger(obj, effect)]

    return _setup


def make_damage_flagship_draw_setup() -> Callable[[GameObject, GameState], list[Interceptor]]:
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(event: Event, st: GameState) -> list[Event]:
            target = st.objects.get(event.payload.get("target"))
            if target and "Flagship" in target.characteristics.subtypes:
                return [_draw(obj.controller, obj.id, 1)]
            return []

        return [make_damage_trigger(obj, effect, combat_only=True)]

    return _setup


def make_simple_activated_setup(
    *,
    cost: str,
    description: str,
    damage: int = 0,
    tc: int = 0,
    sc: int = 0,
    scan: bool = False,
    self_pump: int = 0,
):
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def effect(game, player_id: str, source: GameObject, targets: list[str]):
            events: list[Event] = []
            target_id = targets[0] if targets else None
            if scan:
                target = game.state.objects.get(target_id) if target_id else _lowest_hull(opposing_vessels(player_id, game.state))
                if target:
                    mark_detected(target)
                    events.append(_detect(target, source.id))
            if damage:
                target = game.state.objects.get(target_id) if target_id else _lowest_hull(opposing_vessels(player_id, game.state))
                if target:
                    events.append(_damage(target.id, source.id, damage))
            if tc or sc:
                _add_charges(game.state, player_id, tc=tc, sc=sc)
                events.append(_charges(player_id, source.id, tc=tc, sc=sc))
            if self_pump:
                events.append(_pt(source.id, source.id, power=self_pump))
            return events

        obj.state.activated_abilities.append({
            "cost": cost,
            "description": description,
            "effect": effect,
        })
        return []

    _setup.depths_grants_activated_ability = True
    return _setup


def action_damage(amount: int):
    def effect(obj: GameObject, state: GameState) -> list[Event]:
        target = _lowest_hull(opposing_vessels(obj.controller, state))
        return [_damage(target.id, obj.id, amount)] if target else []

    return effect


def action_scan_damage(amount: int = 0, count: int = 1):
    def effect(obj: GameObject, state: GameState) -> list[Event]:
        events: list[Event] = []
        for target in opposing_vessels(obj.controller, state)[:count]:
            mark_detected(target)
            events.append(_detect(target, obj.id))
            if amount:
                events.append(_damage(target.id, obj.id, amount))
        return events

    return effect


def action_draw_charge(draw: int = 1, *, tc: int = 0, sc: int = 0):
    def effect(obj: GameObject, state: GameState) -> list[Event]:
        events: list[Event] = [_draw(obj.controller, obj.id, draw)]
        if tc or sc:
            _add_charges(state, obj.controller, tc=tc, sc=sc)
            events.append(_charges(obj.controller, obj.id, tc=tc, sc=sc))
        return events

    return effect


def action_create_drones(count: int):
    def effect(obj: GameObject, state: GameState) -> list[Event]:
        return [_drone(obj.controller, obj.id) for _ in range(max(0, count))]

    return effect


def pressure_count(source: GameObject, target: GameObject, state: GameState) -> tuple[int, int]:
    count = sum(1 for v in own_vessels(source.controller, state) if v.state.depth_band in {DepthBand.DEEP, DepthBand.CRUSH})
    return (min(3, count), 0)


def make_pressure_count_setup():
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        return make_dynamic_pt_boost(
            obj,
            pressure_count,
            lambda target, _state: target.id == obj.id,
        )

    return _setup


__all__ = [
    "ABYS_CODE",
    "DepthBand",
    "abys_action",
    "abys_crew",
    "abys_doctrine",
    "abys_mine",
    "abys_vessel",
    "abys_weapon",
    "action_create_drones",
    "action_damage",
    "action_draw_charge",
    "action_scan_damage",
    "compose_setups",
    "make_damage_flagship_draw_setup",
    "make_depth_end_charge_setup",
    "make_dive_phase_scan_setup",
    "make_formation_attack_setup",
    "make_pressure_count_setup",
    "make_pressure_setup",
    "make_salvage_setup",
    "make_same_depth_lord_setup",
    "make_scan_etb_setup",
    "make_simple_activated_setup",
    "make_vent_setup",
    "mark_detected",
]
