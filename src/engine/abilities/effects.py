"""
Ability System - Effects

Effect types for triggered and activated abilities:
- GainLife(amount)
- LoseLife(amount)
- DealDamage(amount, target)
- DrawCards(amount)
- DiscardCards(amount)
- CreateToken(token_def)
- AddCounters(counter_type, amount, target)
- Destroy(target)
- Mill(amount)
- Scry(amount)
- CompositeEffect([effects])
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, List

from .base import Effect
from .targets import EffectTarget, ControllerTarget, EachOpponentTarget

if TYPE_CHECKING:
    from src.engine.types import Event, GameObject, GameState


@dataclass
class GainLife(Effect):
    """
    Gain life.

    Examples:
        - GainLife(3) -> "you gain 3 life"
        - GainLife(1) -> "you gain 1 life"
    """
    amount: int
    target: EffectTarget = field(default_factory=ControllerTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        life_word = "life" if self.amount == 1 else "life"
        if target_text == "you":
            return f"you gain {self.amount} {life_word}"
        else:
            return f"{target_text} gains {self.amount} {life_word}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        targets = self.target.resolve(event, state, obj)
        for target_id in targets:
            events.append(E(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_id, 'amount': self.amount},
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class LoseLife(Effect):
    """
    Lose life.

    Examples:
        - LoseLife(2, target=EachOpponentTarget()) -> "each opponent loses 2 life"
    """
    amount: int
    target: EffectTarget = field(default_factory=EachOpponentTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        life_word = "life"
        if target_text == "you":
            return f"you lose {self.amount} {life_word}"
        else:
            return f"{target_text} loses {self.amount} {life_word}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        targets = self.target.resolve(event, state, obj)
        for target_id in targets:
            events.append(E(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_id, 'amount': -self.amount},
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class DealDamage(Effect):
    """
    Deal damage.

    Examples:
        - DealDamage(3, target=TargetAny()) -> "deal 3 damage to any target"
        - DealDamage(2, target=EachOpponentTarget()) -> "deal 2 damage to each opponent"
    """
    amount: int
    target: EffectTarget

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        return f"{card_name} deals {self.amount} damage to {target_text}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        targets = self.target.resolve(event, state, obj)
        for target_id in targets:
            events.append(E(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': self.amount},
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class DrawCards(Effect):
    """
    Draw cards.

    Examples:
        - DrawCards(1) -> "draw a card"
        - DrawCards(2) -> "draw two cards"
    """
    amount: int
    target: EffectTarget = field(default_factory=ControllerTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)

        # Number words for common amounts
        number_words = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five"}
        amount_text = number_words.get(self.amount, str(self.amount))

        card_word = "card" if self.amount == 1 else "cards"

        if target_text == "you":
            return f"draw {amount_text} {card_word}"
        else:
            return f"{target_text} draws {amount_text} {card_word}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        targets = self.target.resolve(event, state, obj)
        for target_id in targets:
            for _ in range(self.amount):
                events.append(E(
                    type=EventType.DRAW,
                    payload={'player': target_id},
                    source=obj.id,
                    controller=obj.controller
                ))
        return events


@dataclass
class DiscardCards(Effect):
    """
    Discard cards.

    Examples:
        - DiscardCards(1) -> "discard a card"
        - DiscardCards(2, target=EachOpponentTarget()) -> "each opponent discards two cards"
    """
    amount: int
    target: EffectTarget = field(default_factory=ControllerTarget)
    random: bool = False

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)

        number_words = {1: "a", 2: "two", 3: "three"}
        amount_text = number_words.get(self.amount, str(self.amount))

        card_word = "card" if self.amount == 1 else "cards"
        random_text = " at random" if self.random else ""

        if target_text == "you":
            return f"discard {amount_text} {card_word}{random_text}"
        else:
            return f"{target_text} discards {amount_text} {card_word}{random_text}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        targets = self.target.resolve(event, state, obj)
        for target_id in targets:
            for _ in range(self.amount):
                events.append(E(
                    type=EventType.DISCARD,
                    payload={'player': target_id, 'random': self.random},
                    source=obj.id,
                    controller=obj.controller
                ))
        return events


@dataclass
class AddCounters(Effect):
    """
    Add counters to a permanent.

    Examples:
        - AddCounters("+1/+1", 1) -> "put a +1/+1 counter on ~"
        - AddCounters("+1/+1", 2) -> "put two +1/+1 counters on ~"
    """
    counter_type: str
    amount: int
    target: Optional[EffectTarget] = None  # None means self

    def render_text(self, card_name: str) -> str:
        number_words = {1: "a", 2: "two", 3: "three", 4: "four"}
        amount_text = number_words.get(self.amount, str(self.amount))

        counter_word = "counter" if self.amount == 1 else "counters"

        if self.target:
            target_text = self.target.render_text(card_name)
        else:
            target_text = card_name

        return f"put {amount_text} {self.counter_type} {counter_word} on {target_text}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        if self.target:
            targets = self.target.resolve(event, state, obj)
        else:
            targets = [obj.id]

        for target_id in targets:
            for _ in range(self.amount):
                events.append(E(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target_id, 'counter_type': self.counter_type},
                    source=obj.id,
                    controller=obj.controller
                ))
        return events


@dataclass
class RemoveCounters(Effect):
    """
    Remove counters from a permanent.
    """
    counter_type: str
    amount: int
    target: Optional[EffectTarget] = None

    def render_text(self, card_name: str) -> str:
        number_words = {1: "a", 2: "two", 3: "three"}
        amount_text = number_words.get(self.amount, str(self.amount))

        counter_word = "counter" if self.amount == 1 else "counters"

        if self.target:
            target_text = self.target.render_text(card_name)
        else:
            target_text = card_name

        return f"remove {amount_text} {self.counter_type} {counter_word} from {target_text}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        if self.target:
            targets = self.target.resolve(event, state, obj)
        else:
            targets = [obj.id]

        for target_id in targets:
            for _ in range(self.amount):
                events.append(E(
                    type=EventType.COUNTER_REMOVED,
                    payload={'object_id': target_id, 'counter_type': self.counter_type},
                    source=obj.id,
                    controller=obj.controller
                ))
        return events


@dataclass
class Mill(Effect):
    """
    Mill cards (put from library into graveyard).

    Examples:
        - Mill(3) -> "mill three cards"
        - Mill(2, target=EachOpponentTarget()) -> "each opponent mills two cards"
    """
    amount: int
    target: EffectTarget = field(default_factory=ControllerTarget)

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)

        number_words = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five"}
        amount_text = number_words.get(self.amount, str(self.amount))

        card_word = "card" if self.amount == 1 else "cards"

        if target_text == "you":
            return f"mill {amount_text} {card_word}"
        else:
            return f"{target_text} mills {amount_text} {card_word}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType, ZoneType

        events = []
        targets = self.target.resolve(event, state, obj)

        for target_id in targets:
            # Find player's library
            library_key = f"{target_id}_library"
            library = state.zones.get(library_key)
            if not library:
                continue

            # Mill top N cards
            for i in range(min(self.amount, len(library.objects))):
                card_id = library.objects[i]
                events.append(E(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': card_id,
                        'from_zone_type': ZoneType.LIBRARY,
                        'to_zone_type': ZoneType.GRAVEYARD
                    },
                    source=obj.id,
                    controller=obj.controller
                ))

        return events


@dataclass
class Scry(Effect):
    """
    Scry N.

    Examples:
        - Scry(1) -> "scry 1"
        - Scry(2) -> "scry 2"
    """
    amount: int

    def render_text(self, card_name: str) -> str:
        return f"scry {self.amount}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        # Scry is complex and requires player choice
        # For now, emit a placeholder event
        from src.engine.types import Event as E, EventType

        return [E(
            type=EventType.ACTIVATE,  # Placeholder - needs proper SCRY event
            payload={'action': 'scry', 'amount': self.amount, 'player': obj.controller},
            source=obj.id,
            controller=obj.controller
        )]


@dataclass
class CreateToken(Effect):
    """
    Create a token.

    Examples:
        - CreateToken(power=1, toughness=1, name="Soldier", colors={"W"})
          -> "create a 1/1 white Soldier creature token"
    """
    name: str
    power: int
    toughness: int
    colors: set = field(default_factory=set)
    subtypes: set = field(default_factory=set)
    keywords: list = field(default_factory=list)
    count: int = 1

    def render_text(self, card_name: str) -> str:
        parts = ["create"]

        # Count
        if self.count == 1:
            parts.append("a")
        else:
            number_words = {2: "two", 3: "three", 4: "four", 5: "five"}
            parts.append(number_words.get(self.count, str(self.count)))

        # P/T
        parts.append(f"{self.power}/{self.toughness}")

        # Colors
        color_map = {'W': 'white', 'U': 'blue', 'B': 'black', 'R': 'red', 'G': 'green'}
        color_names = [color_map.get(c, c) for c in sorted(self.colors)]
        if color_names:
            parts.append(" ".join(color_names))

        # Name/type
        parts.append(self.name)
        parts.append("creature token")

        # Keywords
        if self.keywords:
            parts.append("with")
            parts.append(", ".join(self.keywords))

        return " ".join(parts)

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        for _ in range(self.count):
            events.append(E(
                type=EventType.OBJECT_CREATED,
                payload={
                    'token': True,
                    'name': self.name,
                    'power': self.power,
                    'toughness': self.toughness,
                    'colors': self.colors,
                    'subtypes': self.subtypes,
                    'keywords': self.keywords,
                    'controller': obj.controller
                },
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class Destroy(Effect):
    """
    Destroy a permanent.
    """
    target: EffectTarget

    def render_text(self, card_name: str) -> str:
        target_text = self.target.render_text(card_name)
        return f"destroy {target_text}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        targets = self.target.resolve(event, state, obj)
        for target_id in targets:
            events.append(E(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id},
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class Sacrifice(Effect):
    """
    Sacrifice a permanent.
    """
    target: Optional[EffectTarget] = None  # None means self

    def render_text(self, card_name: str) -> str:
        if self.target:
            target_text = self.target.render_text(card_name)
            return f"sacrifice {target_text}"
        else:
            return f"sacrifice {card_name}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType, ZoneType

        events = []
        if self.target:
            targets = self.target.resolve(event, state, obj)
        else:
            targets = [obj.id]

        for target_id in targets:
            events.append(E(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.GRAVEYARD,
                    'is_sacrifice': True
                },
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class TapEffect(Effect):
    """
    Tap a permanent.
    """
    target: Optional[EffectTarget] = None

    def render_text(self, card_name: str) -> str:
        if self.target:
            target_text = self.target.render_text(card_name)
            return f"tap {target_text}"
        else:
            return f"tap {card_name}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        if self.target:
            targets = self.target.resolve(event, state, obj)
        else:
            targets = [obj.id]

        for target_id in targets:
            events.append(E(
                type=EventType.TAP,
                payload={'object_id': target_id},
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class UntapEffect(Effect):
    """
    Untap a permanent.
    """
    target: Optional[EffectTarget] = None

    def render_text(self, card_name: str) -> str:
        if self.target:
            target_text = self.target.render_text(card_name)
            return f"untap {target_text}"
        else:
            return f"untap {card_name}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        from src.engine.types import Event as E, EventType

        events = []
        if self.target:
            targets = self.target.resolve(event, state, obj)
        else:
            targets = [obj.id]

        for target_id in targets:
            events.append(E(
                type=EventType.UNTAP,
                payload={'object_id': target_id},
                source=obj.id,
                controller=obj.controller
            ))
        return events


@dataclass
class CompositeEffect(Effect):
    """
    Multiple effects combined.

    Examples:
        - CompositeEffect([GainLife(1), DrawCards(1)])
          -> "you gain 1 life and draw a card"
    """
    effects: list[Effect]

    def render_text(self, card_name: str) -> str:
        texts = [e.render_text(card_name) for e in self.effects]
        if len(texts) == 1:
            return texts[0]
        elif len(texts) == 2:
            return f"{texts[0]} and {texts[1]}"
        else:
            return ", ".join(texts[:-1]) + f", and {texts[-1]}"

    def generate_events(self, event: 'Event', state: 'GameState', obj: 'GameObject') -> list['Event']:
        events = []
        for effect in self.effects:
            events.extend(effect.generate_events(event, state, obj))
        return events
