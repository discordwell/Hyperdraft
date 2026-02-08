"""
Ability System - Targets and Filters

Target types for triggers:
- SelfTarget: "~" (the card itself)
- AnotherCreature: "another creature"
- CreatureYouControl: "a creature you control"
- AnotherCreatureYouControl: "another creature you control"
- CreatureWithSubtype: "a Goblin you control"
- AnyCreature: "a creature"

Filter types for static abilities:
- CreaturesYouControlFilter: "Creatures you control"
- OtherCreaturesYouControlFilter: "Other creatures you control"
- CreaturesWithSubtypeFilter: "Elf creatures you control"
- AllCreaturesFilter: "All creatures"
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Set

if TYPE_CHECKING:
    from src.engine.types import GameObject, GameState, CardType


# =============================================================================
# Trigger Targets
# =============================================================================

class TriggerTarget(ABC):
    """Base class for trigger targets."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        """Render the target description for rules text."""
        ...

    @abstractmethod
    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        """Check if a candidate object matches this target specification."""
        ...


@dataclass
class SelfTarget(TriggerTarget):
    """The card itself (~)."""

    def render_text(self, card_name: str) -> str:
        return card_name

    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        return candidate.id == source.id


@dataclass
class AnyCreature(TriggerTarget):
    """Any creature."""

    def render_text(self, card_name: str) -> str:
        return "a creature"

    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType
        return CardType.CREATURE in candidate.characteristics.types


@dataclass
class AnotherCreature(TriggerTarget):
    """Another creature (not self)."""

    def render_text(self, card_name: str) -> str:
        return "another creature"

    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType
        if candidate.id == source.id:
            return False
        return CardType.CREATURE in candidate.characteristics.types


@dataclass
class CreatureYouControl(TriggerTarget):
    """A creature you control."""

    def render_text(self, card_name: str) -> str:
        return "a creature you control"

    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType
        if candidate.controller != source.controller:
            return False
        return CardType.CREATURE in candidate.characteristics.types


@dataclass
class AnotherCreatureYouControl(TriggerTarget):
    """Another creature you control (not self)."""

    def render_text(self, card_name: str) -> str:
        return "another creature you control"

    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType
        if candidate.id == source.id:
            return False
        if candidate.controller != source.controller:
            return False
        return CardType.CREATURE in candidate.characteristics.types


@dataclass
class CreatureWithSubtype(TriggerTarget):
    """A creature with a specific subtype."""
    subtype: str
    you_control: bool = True
    exclude_self: bool = False

    def render_text(self, card_name: str) -> str:
        parts = []
        if self.exclude_self:
            parts.append("another")
        parts.append(self.subtype)
        if self.you_control:
            parts.append("you control")
        return " ".join(parts)

    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType

        if self.exclude_self and candidate.id == source.id:
            return False
        if self.you_control and candidate.controller != source.controller:
            return False
        if CardType.CREATURE not in candidate.characteristics.types:
            return False
        return self.subtype in candidate.characteristics.subtypes


@dataclass
class NonlandPermanent(TriggerTarget):
    """A nonland permanent."""
    you_control: bool = False
    exclude_self: bool = False

    def render_text(self, card_name: str) -> str:
        parts = []
        if self.exclude_self:
            parts.append("another")
        parts.append("nonland permanent")
        if self.you_control:
            parts.append("you control")
        return " ".join(parts)

    def matches(self, candidate: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType, ZoneType

        if self.exclude_self and candidate.id == source.id:
            return False
        if self.you_control and candidate.controller != source.controller:
            return False
        if candidate.zone != ZoneType.BATTLEFIELD:
            return False
        return CardType.LAND not in candidate.characteristics.types


# =============================================================================
# Static Ability Filters
# =============================================================================

class TargetFilter(ABC):
    """Base class for static ability filters."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        """Render the filter description for rules text."""
        ...

    @abstractmethod
    def matches(self, target: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        """Check if a target matches this filter."""
        ...


@dataclass
class CreaturesYouControlFilter(TargetFilter):
    """Creatures you control."""

    def render_text(self, card_name: str) -> str:
        return "Creatures you control"

    def matches(self, target: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType, ZoneType

        if target.controller != source.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return CardType.CREATURE in target.characteristics.types


@dataclass
class OtherCreaturesYouControlFilter(TargetFilter):
    """Other creatures you control."""

    def render_text(self, card_name: str) -> str:
        return "Other creatures you control"

    def matches(self, target: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType, ZoneType

        if target.id == source.id:
            return False
        if target.controller != source.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return CardType.CREATURE in target.characteristics.types


@dataclass
class CreaturesWithSubtypeFilter(TargetFilter):
    """Creatures with a specific subtype."""
    subtype: str
    include_self: bool = True
    you_control: bool = True

    def render_text(self, card_name: str) -> str:
        parts = []
        if not self.include_self:
            parts.append("Other")
        parts.append(f"{self.subtype} creatures")
        if self.you_control:
            parts.append("you control")
        return " ".join(parts)

    def matches(self, target: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType, ZoneType

        if not self.include_self and target.id == source.id:
            return False
        if self.you_control and target.controller != source.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return self.subtype in target.characteristics.subtypes


@dataclass
class AllCreaturesFilter(TargetFilter):
    """All creatures."""

    def render_text(self, card_name: str) -> str:
        return "All creatures"

    def matches(self, target: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType, ZoneType

        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return CardType.CREATURE in target.characteristics.types


@dataclass
class OpponentCreaturesFilter(TargetFilter):
    """Creatures opponents control."""

    def render_text(self, card_name: str) -> str:
        return "Creatures your opponents control"

    def matches(self, target: 'GameObject', source: 'GameObject', state: 'GameState') -> bool:
        from src.engine.types import CardType, ZoneType

        if target.controller == source.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return CardType.CREATURE in target.characteristics.types


# =============================================================================
# Effect Targets
# =============================================================================

class EffectTarget(ABC):
    """Base class for effect targets."""

    @abstractmethod
    def render_text(self, card_name: str) -> str:
        ...

    @abstractmethod
    def resolve(self, event: 'Event', state: 'GameState', source: 'GameObject') -> list[str]:
        """Return list of target IDs (player or object)."""
        ...


@dataclass
class ControllerTarget(EffectTarget):
    """The controller of the source."""

    def render_text(self, card_name: str) -> str:
        return "you"

    def resolve(self, event, state, source) -> list[str]:
        return [source.controller]


@dataclass
class EachOpponentTarget(EffectTarget):
    """Each opponent."""

    def render_text(self, card_name: str) -> str:
        return "each opponent"

    def resolve(self, event, state, source) -> list[str]:
        return [p_id for p_id in state.players.keys() if p_id != source.controller]


@dataclass
class TriggeringObjectTarget(EffectTarget):
    """The object that triggered this ability."""

    def render_text(self, card_name: str) -> str:
        return "that creature"

    def resolve(self, event, state, source) -> list[str]:
        obj_id = event.payload.get('object_id')
        return [obj_id] if obj_id else []


@dataclass
class DamageTarget(EffectTarget):
    """The target of a DAMAGE event (event.payload['target'])."""

    def render_text(self, card_name: str) -> str:
        return "that creature"

    def resolve(self, event, state, source) -> list[str]:
        target_id = event.payload.get('target')
        return [target_id] if target_id else []
