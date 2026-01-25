"""
Ability System - Static Effects

Static effect types for continuous abilities:
- PTBoost(power, toughness): +X/+Y
- KeywordGrant(keywords): have flying, trample, etc.
- CostReduction(amount, filter): cost {1} less
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from .base import StaticEffect, TargetFilter

if TYPE_CHECKING:
    from src.engine.types import GameObject, GameState, Interceptor


@dataclass
class PTBoost(StaticEffect):
    """
    Power/toughness modification.

    Examples:
        - PTBoost(1, 1) -> "get +1/+1"
        - PTBoost(2, 0) -> "get +2/+0"
        - PTBoost(-1, -1) -> "get -1/-1"
    """
    power: int
    toughness: int

    def render_text(self, card_name: str) -> str:
        p_sign = "+" if self.power >= 0 else ""
        t_sign = "+" if self.toughness >= 0 else ""
        return f"get {p_sign}{self.power}/{t_sign}{self.toughness}"

    def create_interceptors(self, obj: 'GameObject', filter: TargetFilter) -> list['Interceptor']:
        from src.engine.types import (
            Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
            EventType, new_id
        )

        interceptors = []

        if self.power != 0:
            power_mod = self.power

            def power_filter(event, state, src=obj, flt=filter):
                if event.type != EventType.QUERY_POWER:
                    return False
                target_id = event.payload.get('object_id')
                target = state.objects.get(target_id)
                if not target:
                    return False
                return flt.matches(target, src, state)

            def power_handler(event, state, mod=power_mod):
                current = event.payload.get('value', 0)
                new_event = event.copy()
                new_event.payload['value'] = current + mod
                return InterceptorResult(
                    action=InterceptorAction.TRANSFORM,
                    transformed_event=new_event
                )

            interceptors.append(Interceptor(
                id=new_id(),
                source=obj.id,
                controller=obj.controller,
                priority=InterceptorPriority.QUERY,
                filter=power_filter,
                handler=power_handler,
                duration='while_on_battlefield'
            ))

        if self.toughness != 0:
            toughness_mod = self.toughness

            def toughness_filter(event, state, src=obj, flt=filter):
                if event.type != EventType.QUERY_TOUGHNESS:
                    return False
                target_id = event.payload.get('object_id')
                target = state.objects.get(target_id)
                if not target:
                    return False
                return flt.matches(target, src, state)

            def toughness_handler(event, state, mod=toughness_mod):
                current = event.payload.get('value', 0)
                new_event = event.copy()
                new_event.payload['value'] = current + mod
                return InterceptorResult(
                    action=InterceptorAction.TRANSFORM,
                    transformed_event=new_event
                )

            interceptors.append(Interceptor(
                id=new_id(),
                source=obj.id,
                controller=obj.controller,
                priority=InterceptorPriority.QUERY,
                filter=toughness_filter,
                handler=toughness_handler,
                duration='while_on_battlefield'
            ))

        return interceptors


@dataclass
class KeywordGrant(StaticEffect):
    """
    Grant keywords to creatures.

    Examples:
        - KeywordGrant(["flying"]) -> "have flying"
        - KeywordGrant(["flying", "vigilance"]) -> "have flying and vigilance"
    """
    keywords: list[str]

    def render_text(self, card_name: str) -> str:
        if len(self.keywords) == 1:
            return f"have {self.keywords[0]}"
        elif len(self.keywords) == 2:
            return f"have {self.keywords[0]} and {self.keywords[1]}"
        else:
            return "have " + ", ".join(self.keywords[:-1]) + f", and {self.keywords[-1]}"

    def create_interceptors(self, obj: 'GameObject', filter: TargetFilter) -> list['Interceptor']:
        from src.engine.types import (
            Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
            EventType, new_id
        )

        keywords = self.keywords

        def ability_filter(event, state, src=obj, flt=filter):
            if event.type != EventType.QUERY_ABILITIES:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return flt.matches(target, src, state)

        def ability_handler(event, state, kws=keywords):
            new_event = event.copy()
            granted = list(new_event.payload.get('granted', []))
            for kw in kws:
                if kw not in granted:
                    granted.append(kw)
            new_event.payload['granted'] = granted
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=ability_filter,
            handler=ability_handler,
            duration='while_on_battlefield'
        )]


@dataclass
class TypeGrant(StaticEffect):
    """
    Grant creature types.

    Examples:
        - TypeGrant(["Zombie"]) -> "are Zombies in addition to their other types"
    """
    types: list[str]

    def render_text(self, card_name: str) -> str:
        if len(self.types) == 1:
            return f"are {self.types[0]}s in addition to their other types"
        else:
            type_list = " ".join(self.types)
            return f"are {type_list} in addition to their other types"

    def create_interceptors(self, obj: 'GameObject', filter: TargetFilter) -> list['Interceptor']:
        from src.engine.types import (
            Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
            EventType, new_id
        )

        types = self.types

        def type_filter(event, state, src=obj, flt=filter):
            if event.type != EventType.QUERY_TYPES:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return flt.matches(target, src, state)

        def type_handler(event, state, ts=types):
            new_event = event.copy()
            subtypes = set(new_event.payload.get('subtypes', set()))
            for t in ts:
                subtypes.add(t)
            new_event.payload['subtypes'] = subtypes
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=type_filter,
            handler=type_handler,
            duration='while_on_battlefield'
        )]


@dataclass
class CostReduction(StaticEffect):
    """
    Reduce costs.

    Examples:
        - CostReduction(1) -> "cost {1} less to cast"
        - CostReduction(2) -> "cost {2} less to cast"
    """
    amount: int
    spell_filter: Optional['TargetFilter'] = None  # Which spells are reduced

    def render_text(self, card_name: str) -> str:
        return f"cost {{{self.amount}}} less to cast"

    def create_interceptors(self, obj: 'GameObject', filter: TargetFilter) -> list['Interceptor']:
        # Cost reduction is typically handled during casting
        # This requires integration with the mana/casting system
        # For now, return empty - this is a placeholder
        return []


@dataclass
class CantBlockEffect(StaticEffect):
    """
    Creatures can't block.

    Examples:
        - CantBlockEffect() -> "can't block"
    """

    def render_text(self, card_name: str) -> str:
        return "can't block"

    def create_interceptors(self, obj: 'GameObject', filter: TargetFilter) -> list['Interceptor']:
        from src.engine.types import (
            Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
            EventType, new_id
        )

        def block_filter(event, state, src=obj, flt=filter):
            if event.type != EventType.BLOCK_DECLARED:
                return False
            blocker_id = event.payload.get('blocker_id')
            blocker = state.objects.get(blocker_id)
            if not blocker:
                return False
            return flt.matches(blocker, src, state)

        def block_handler(event, state):
            return InterceptorResult(action=InterceptorAction.PREVENT)

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.PREVENT,
            filter=block_filter,
            handler=block_handler,
            duration='while_on_battlefield'
        )]


@dataclass
class CantAttackEffect(StaticEffect):
    """
    Creatures can't attack.

    Examples:
        - CantAttackEffect() -> "can't attack"
    """

    def render_text(self, card_name: str) -> str:
        return "can't attack"

    def create_interceptors(self, obj: 'GameObject', filter: TargetFilter) -> list['Interceptor']:
        from src.engine.types import (
            Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
            EventType, new_id
        )

        def attack_filter(event, state, src=obj, flt=filter):
            if event.type != EventType.ATTACK_DECLARED:
                return False
            attacker_id = event.payload.get('attacker_id')
            attacker = state.objects.get(attacker_id)
            if not attacker:
                return False
            return flt.matches(attacker, src, state)

        def attack_handler(event, state):
            return InterceptorResult(action=InterceptorAction.PREVENT)

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.PREVENT,
            filter=attack_filter,
            handler=attack_handler,
            duration='while_on_battlefield'
        )]
