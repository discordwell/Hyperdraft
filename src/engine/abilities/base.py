"""
Ability System - Base Classes

Single source of truth for card abilities: declare once, get both
human-readable text AND interceptor implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Callable

if TYPE_CHECKING:
    from src.engine.types import GameObject, GameState, Interceptor


@dataclass
class Ability(ABC):
    """Base class for all abilities."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        """Generate human-readable rules text for this ability."""
        ...

    @abstractmethod
    def generate_interceptors(self, obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        """Generate interceptors that implement this ability's behavior."""
        ...


@dataclass
class TriggeredAbility(Ability):
    """
    A triggered ability that fires when a specific event occurs.

    Examples:
        - "When ~ enters the battlefield, you gain 3 life."
        - "Whenever another creature dies, draw a card."
        - "At the beginning of your upkeep, scry 1."
    """
    trigger: 'Trigger'
    effect: 'Effect'
    condition: Optional['Condition'] = None
    optional: bool = False  # "you may"

    def render_text(self, card_name: str) -> str:
        parts = []

        # Trigger text
        trigger_text = self.trigger.render_text(card_name)
        parts.append(trigger_text)

        # Condition (if present)
        if self.condition:
            parts.append(self.condition.render_text(card_name))

        # Effect text (with optional "you may")
        effect_text = self.effect.render_text(card_name)
        if self.optional:
            effect_text = f"you may {effect_text}"
        parts.append(effect_text)

        return ", ".join(parts) + "."

    def generate_interceptors(self, obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        return self.trigger.create_interceptor(obj, self.effect, self.condition, self.optional)


@dataclass
class StaticAbility(Ability):
    """
    A static ability that provides a continuous effect.

    Examples:
        - "Other creatures you control get +1/+1."
        - "Creatures you control have flying."
    """
    effect: 'StaticEffect'
    filter: 'TargetFilter'

    def render_text(self, card_name: str) -> str:
        filter_text = self.filter.render_text(card_name)
        effect_text = self.effect.render_text(card_name)
        return f"{filter_text} {effect_text}."

    def generate_interceptors(self, obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        return self.effect.create_interceptors(obj, self.filter)


@dataclass
class KeywordAbility(Ability):
    """
    A keyword ability like Flying, Trample, Lifelink, etc.

    Examples:
        - Flying
        - Trample
        - Lifelink
        - First strike
    """
    keyword: str
    reminder_text: Optional[str] = None

    def render_text(self, card_name: str) -> str:
        if self.reminder_text:
            return f"{self.keyword} ({self.reminder_text})"
        return self.keyword

    def generate_interceptors(self, obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        # Keywords are typically checked via has_ability() query
        # Some keywords need interceptors (e.g., lifelink, first strike)
        from .keywords import get_keyword_interceptors
        return get_keyword_interceptors(self.keyword, obj, state)


@dataclass
class ActivatedAbility(Ability):
    """
    An activated ability with a cost.

    Examples:
        - "{T}: Add {G}."
        - "{2}{U}: Draw a card."
        - "{1}, Sacrifice this creature: Destroy target artifact."
    """
    cost: 'Cost'
    effect: 'Effect'
    timing: str = "instant"  # "instant" or "sorcery"

    def render_text(self, card_name: str) -> str:
        cost_text = self.cost.render_text(card_name)
        effect_text = self.effect.render_text(card_name)
        return f"{cost_text}: {effect_text.capitalize()}."

    def generate_interceptors(self, obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        # Activated abilities register with the priority system
        # This is more complex - defer to stack integration
        return []


# Forward declarations for type hints
class Trigger(ABC):
    """Base class for triggers."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        ...

    @abstractmethod
    def create_interceptor(
        self,
        obj: 'GameObject',
        effect: 'Effect',
        condition: Optional['Condition'],
        optional: bool
    ) -> list['Interceptor']:
        ...


class Effect(ABC):
    """Base class for effects."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        ...

    @abstractmethod
    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        ...


class StaticEffect(ABC):
    """Base class for static/continuous effects."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        ...

    @abstractmethod
    def create_interceptors(self, obj: 'GameObject', filter: 'TargetFilter') -> list['Interceptor']:
        ...


class TargetFilter(ABC):
    """Base class for target filters."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        ...

    @abstractmethod
    def matches(self, target: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        ...


class Condition(ABC):
    """Base class for conditions."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        ...

    @abstractmethod
    def check(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> bool:
        ...


class Cost(ABC):
    """Base class for costs."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        ...

    @abstractmethod
    def can_pay(self, obj: 'GameObject', state: 'GameState') -> bool:
        ...

    @abstractmethod
    def pay(self, obj: 'GameObject', state: 'GameState') -> list['Event']:
        ...
