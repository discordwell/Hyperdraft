"""
Ability System - Triggers

Trigger types for triggered abilities:
- ETBTrigger: When ~ enters the battlefield
- DeathTrigger: When ~ dies
- AttackTrigger: Whenever ~ attacks
- BlockTrigger: Whenever ~ blocks
- DealsDamageTrigger: Whenever ~ deals damage
- UpkeepTrigger: At beginning of upkeep
- EndStepTrigger: At beginning of end step
- SpellCastTrigger: Whenever you cast a spell
- LifeGainTrigger: Whenever you gain life
- DrawTrigger: Whenever you draw a card
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Callable

from .base import Trigger, Effect, Condition
from .targets import TriggerTarget, SelfTarget, AnyCreature

if TYPE_CHECKING:
    from src.engine.types import (
        Event, EventType, GameObject, GameState, Interceptor,
        InterceptorPriority, InterceptorAction, InterceptorResult,
        ZoneType, CardType
    )


def _make_trigger_interceptor(
    obj: 'GameObject',
    event_filter: Callable[['Event', 'GameState'], bool],
    effect: Effect,
    condition: Optional[Condition],
    optional: bool,
    duration: str = 'while_on_battlefield'
) -> list['Interceptor']:
    """Helper to create a standard triggered ability interceptor."""
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, new_id
    )

    def trigger_filter(event: 'Event', state: 'GameState') -> bool:
        if not event_filter(event, state):
            return False
        if condition and not condition.check(event, state, obj):
            return False
        return True

    def trigger_handler(event: 'Event', state: 'GameState') -> 'InterceptorResult':
        new_events = effect.generate_events(event, state, obj)
        # TODO: Handle optional triggers (put on stack, let player decline)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration=duration
    )]


@dataclass
class ETBTrigger(Trigger):
    """
    When [target] enters the battlefield.

    Examples:
        - ETBTrigger() -> "When ~ enters the battlefield"
        - ETBTrigger(target=AnotherCreature()) -> "Whenever another creature enters the battlefield"
    """
    target: TriggerTarget = field(default_factory=SelfTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        if isinstance(self.target, SelfTarget):
            return f"When {target_text} enters the battlefield"
        else:
            return f"Whenever {target_text} enters the battlefield"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType, ZoneType, CardType

        target = self.target

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.ZONE_CHANGE:
                return False
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False

            entering_id = event.payload.get('object_id')
            entering = state.objects.get(entering_id)
            if not entering:
                return False

            return target.matches(entering, obj, state)

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class DeathTrigger(Trigger):
    """
    When [target] dies.

    Examples:
        - DeathTrigger() -> "When ~ dies"
        - DeathTrigger(target=AnotherCreature()) -> "Whenever another creature dies"
    """
    target: TriggerTarget = field(default_factory=SelfTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        if isinstance(self.target, SelfTarget):
            return f"When {target_text} dies"
        else:
            return f"Whenever {target_text} dies"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType, ZoneType

        target = self.target

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.ZONE_CHANGE:
                return False
            if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
                return False
            if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
                return False

            dying_id = event.payload.get('object_id')
            dying = state.objects.get(dying_id)
            if not dying:
                return False

            return target.matches(dying, obj, state)

        duration = 'until_leaves' if isinstance(self.target, SelfTarget) else 'while_on_battlefield'
        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional, duration)


@dataclass
class AttackTrigger(Trigger):
    """
    Whenever [target] attacks.

    Examples:
        - AttackTrigger() -> "Whenever ~ attacks"
        - AttackTrigger(target=CreatureYouControl()) -> "Whenever a creature you control attacks"
    """
    target: TriggerTarget = field(default_factory=SelfTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        return f"Whenever {target_text} attacks"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType

        target = self.target

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.ATTACK_DECLARED:
                return False

            attacker_id = event.payload.get('attacker_id')
            attacker = state.objects.get(attacker_id)
            if not attacker:
                return False

            return target.matches(attacker, obj, state)

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class BlockTrigger(Trigger):
    """
    Whenever [target] blocks.

    Examples:
        - BlockTrigger() -> "Whenever ~ blocks"
    """
    target: TriggerTarget = field(default_factory=SelfTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        return f"Whenever {target_text} blocks"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType

        target = self.target

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.BLOCK_DECLARED:
                return False

            blocker_id = event.payload.get('blocker_id')
            blocker = state.objects.get(blocker_id)
            if not blocker:
                return False

            return target.matches(blocker, obj, state)

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class DealsDamageTrigger(Trigger):
    """
    Whenever [target] deals damage.

    Examples:
        - DealsDamageTrigger() -> "Whenever ~ deals damage"
        - DealsDamageTrigger(combat_only=True) -> "Whenever ~ deals combat damage"
        - DealsDamageTrigger(to_player=True) -> "Whenever ~ deals damage to a player"
    """
    target: TriggerTarget = field(default_factory=SelfTarget)
    combat_only: bool = False
    to_player: bool = False
    to_creature: bool = False

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        parts = [f"Whenever {target_text} deals"]

        if self.combat_only:
            parts.append("combat")

        parts.append("damage")

        if self.to_player:
            parts.append("to a player")
        elif self.to_creature:
            parts.append("to a creature")

        return " ".join(parts)

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType, CardType

        target = self.target
        combat_only = self.combat_only
        to_player = self.to_player
        to_creature = self.to_creature

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.DAMAGE:
                return False

            source_id = event.payload.get('source')
            source = state.objects.get(source_id)
            if not source:
                return False

            if not target.matches(source, obj, state):
                return False

            if combat_only:
                if not event.payload.get('is_combat', False):
                    return False

            if to_player:
                target_id = event.payload.get('target')
                if target_id not in state.players:
                    return False

            if to_creature:
                target_id = event.payload.get('target')
                target_obj = state.objects.get(target_id)
                if not target_obj or CardType.CREATURE not in target_obj.characteristics.types:
                    return False

            return True

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class UpkeepTrigger(Trigger):
    """
    At the beginning of [whose] upkeep.

    Examples:
        - UpkeepTrigger() -> "At the beginning of your upkeep"
        - UpkeepTrigger(each_player=True) -> "At the beginning of each player's upkeep"
    """
    your_upkeep: bool = True
    each_player: bool = False

    def render_text(self, card_name: str) -> str:
        if self.each_player:
            return "At the beginning of each player's upkeep"
        elif self.your_upkeep:
            return "At the beginning of your upkeep"
        else:
            return "At the beginning of each opponent's upkeep"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType

        your_upkeep = self.your_upkeep
        each_player = self.each_player

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'upkeep':
                return False

            if each_player:
                return True
            elif your_upkeep:
                return state.active_player == obj.controller
            else:
                return state.active_player != obj.controller

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class EndStepTrigger(Trigger):
    """
    At the beginning of [whose] end step.

    Examples:
        - EndStepTrigger() -> "At the beginning of your end step"
        - EndStepTrigger(each_end_step=True) -> "At the beginning of each end step"
    """
    your_end_step: bool = True
    each_end_step: bool = False

    def render_text(self, card_name: str) -> str:
        if self.each_end_step:
            return "At the beginning of each end step"
        elif self.your_end_step:
            return "At the beginning of your end step"
        else:
            return "At the beginning of each opponent's end step"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType

        your_end_step = self.your_end_step
        each_end_step = self.each_end_step

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'end_step':
                return False

            if each_end_step:
                return True
            elif your_end_step:
                return state.active_player == obj.controller
            else:
                return state.active_player != obj.controller

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class SpellCastTrigger(Trigger):
    """
    Whenever [who] cast[s] a spell.

    Examples:
        - SpellCastTrigger() -> "Whenever you cast a spell"
        - SpellCastTrigger(any_player=True) -> "Whenever a player casts a spell"
    """
    controller_only: bool = True
    any_player: bool = False
    spell_types: Optional[set] = None  # Set of CardType
    colors: Optional[set] = None  # Set of Color

    def render_text(self, card_name: str) -> str:
        parts = ["Whenever"]

        if self.any_player:
            parts.append("a player casts")
        elif self.controller_only:
            parts.append("you cast")
        else:
            parts.append("an opponent casts")

        if self.colors:
            color_names = sorted([c.name.lower() for c in self.colors])
            if len(color_names) == 1:
                parts.append(f"a {color_names[0]}")
            else:
                parts.append(f"a {' or '.join(color_names)}")
        else:
            parts.append("a")

        if self.spell_types:
            type_names = sorted([t.name.lower() for t in self.spell_types])
            parts.append(" or ".join(type_names))
        else:
            parts.append("spell")

        return " ".join(parts)

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType

        controller_only = self.controller_only
        any_player = self.any_player
        spell_types = self.spell_types
        colors = self.colors

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.CAST:
                return False

            caster = event.payload.get('caster')
            if not any_player:
                if controller_only and caster != obj.controller:
                    return False
                if not controller_only and caster == obj.controller:
                    return False

            if spell_types:
                event_types = set(event.payload.get('types', []))
                if not event_types.intersection(spell_types):
                    return False

            if colors:
                event_colors = set(event.payload.get('colors', []))
                if not event_colors.intersection(colors):
                    return False

            return True

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class LifeGainTrigger(Trigger):
    """
    Whenever [who] gain[s] life.

    Examples:
        - LifeGainTrigger() -> "Whenever you gain life"
    """
    controller_only: bool = True

    def render_text(self, card_name: str) -> str:
        if self.controller_only:
            return "Whenever you gain life"
        else:
            return "Whenever a player gains life"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType

        controller_only = self.controller_only

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.LIFE_CHANGE:
                return False

            amount = event.payload.get('amount', 0)
            if amount <= 0:
                return False

            if controller_only:
                return event.payload.get('player') == obj.controller

            return True

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class DrawTrigger(Trigger):
    """
    Whenever [who] draw[s] a card.

    Examples:
        - DrawTrigger() -> "Whenever you draw a card"
    """
    controller_only: bool = True

    def render_text(self, card_name: str) -> str:
        if self.controller_only:
            return "Whenever you draw a card"
        else:
            return "Whenever a player draws a card"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType

        controller_only = self.controller_only

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.DRAW:
                return False

            if controller_only:
                return event.payload.get('player') == obj.controller

            return True

        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional)


@dataclass
class LeavesPlayTrigger(Trigger):
    """
    When [target] leaves the battlefield.
    """
    target: TriggerTarget = field(default_factory=SelfTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        if isinstance(self.target, SelfTarget):
            return f"When {target_text} leaves the battlefield"
        else:
            return f"Whenever {target_text} leaves the battlefield"

    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: Effect,
        condition: Optional[Condition],
        optional: bool
    ) -> list['Interceptor']:
        from src.engine.types import EventType, ZoneType

        target = self.target

        def event_filter(event: 'Event', state: 'GameState') -> bool:
            if event.type != EventType.ZONE_CHANGE:
                return False
            if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
                return False

            leaving_id = event.payload.get('object_id')
            leaving = state.objects.get(leaving_id)
            if not leaving:
                return False

            return target.matches(leaving, obj, state)

        duration = 'until_leaves' if isinstance(self.target, SelfTarget) else 'while_on_battlefield'
        return _make_trigger_interceptor(obj, event_filter, effect, condition, optional, duration)
