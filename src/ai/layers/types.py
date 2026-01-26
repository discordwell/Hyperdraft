"""
Strategy Layer Types

Dataclasses for the three-layer strategic knowledge system.
Each layer has:
- Programmatic fields: Used by Hard AI for scoring
- Text guidance: Used by Ultra AI for LLM context
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CardStrategy:
    """
    Layer 1: General strategy for playing a card.

    This is cached globally by card name since it doesn't
    depend on deck context or matchup.
    """
    card_name: str

    # === Programmatic Fields (Hard AI) ===
    timing: str = "any"
    """When to play: "early", "mid", "late", "reactive", "any" """

    base_priority: float = 0.5
    """How eager to play (0.0-1.0). Higher = play sooner."""

    role: str = "utility"
    """Card role: "removal", "threat", "utility", "finisher", "engine" """

    target_priority: list[str] = field(default_factory=lambda: ["creature"])
    """Target preference order: ["creature", "planeswalker", "player"]"""

    # === Text Guidance (Ultra AI) ===
    when_to_play: str = ""
    """Guidance on when to play this card."""

    when_not_to_play: str = ""
    """Guidance on when to hold this card."""

    targeting_advice: str = ""
    """Guidance on what makes good targets."""

    def to_dict(self) -> dict:
        """Convert to dictionary for caching."""
        return {
            "card_name": self.card_name,
            "timing": self.timing,
            "base_priority": self.base_priority,
            "role": self.role,
            "target_priority": self.target_priority,
            "when_to_play": self.when_to_play,
            "when_not_to_play": self.when_not_to_play,
            "targeting_advice": self.targeting_advice
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CardStrategy':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class DeckRole:
    """
    Layer 2: How a card functions in a specific deck.

    Cached by (card_name, deck_hash) since the same card
    can have different roles in different decks.
    """
    card_name: str
    deck_hash: str

    # === Programmatic Fields (Hard AI) ===
    role_weight: float = 1.0
    """Importance in deck: 0.5=filler, 1.0=normal, 1.5=key card"""

    curve_slot: int = 3
    """Ideal turn to play (1-7+)"""

    synergy_cards: list[str] = field(default_factory=list)
    """Cards that combo with this one."""

    enables: list[str] = field(default_factory=list)
    """Win conditions this card enables."""

    is_key_card: bool = False
    """Is this central to the deck's game plan?"""

    # === Text Guidance (Ultra AI) ===
    deck_role: str = ""
    """Description of card's role in this deck."""

    play_pattern: str = ""
    """When and how to sequence this card."""

    synergy_notes: str = ""
    """How this interacts with other deck cards."""

    def to_dict(self) -> dict:
        """Convert to dictionary for caching."""
        return {
            "card_name": self.card_name,
            "deck_hash": self.deck_hash,
            "role_weight": self.role_weight,
            "curve_slot": self.curve_slot,
            "synergy_cards": self.synergy_cards,
            "enables": self.enables,
            "is_key_card": self.is_key_card,
            "deck_role": self.deck_role,
            "play_pattern": self.play_pattern,
            "synergy_notes": self.synergy_notes
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DeckRole':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class MatchupGuide:
    """
    Layer 3: How to use a card against a specific opponent deck.

    Cached by (card_name, matchup_hash) where matchup_hash
    combines both deck hashes.
    """
    card_name: str
    matchup_hash: str

    # === Programmatic Fields (Hard AI) ===
    priority_modifier: float = 1.0
    """Multiplier: 1.5=more important, 0.5=less important in this matchup"""

    save_for: list[str] = field(default_factory=list)
    """Opponent cards to save this for."""

    dont_use_on: list[str] = field(default_factory=list)
    """Opponent cards not worth targeting."""

    threat_level: float = 0.5
    """How dangerous our card is to them (0.0-1.0)"""

    # === Text Guidance (Ultra AI) ===
    matchup_role: str = ""
    """How this card's role changes in this matchup."""

    key_targets: str = ""
    """What to target in this matchup."""

    timing_advice: str = ""
    """When to use this card in this matchup."""

    def to_dict(self) -> dict:
        """Convert to dictionary for caching."""
        return {
            "card_name": self.card_name,
            "matchup_hash": self.matchup_hash,
            "priority_modifier": self.priority_modifier,
            "save_for": self.save_for,
            "dont_use_on": self.dont_use_on,
            "threat_level": self.threat_level,
            "matchup_role": self.matchup_role,
            "key_targets": self.key_targets,
            "timing_advice": self.timing_advice
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'MatchupGuide':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class CardLayers:
    """
    All three layers for a card.

    Contains the complete strategic knowledge for a card
    in a specific context.
    """
    card_strategy: CardStrategy
    deck_role: Optional[DeckRole] = None
    matchup_guide: Optional[MatchupGuide] = None

    # Deck-level context (set by LayerGenerator)
    deck_analysis: Optional['DeckAnalysis'] = None
    matchup_analysis: Optional['MatchupAnalysis'] = None


@dataclass
class DeckAnalysis:
    """
    Overall deck strategy analysis.

    Computed once per deck and shared across all cards.
    """
    deck_hash: str

    archetype: str = "midrange"
    """Deck type: "aggro", "control", "midrange", "combo", "tempo" """

    win_conditions: list[str] = field(default_factory=list)
    """How the deck wins."""

    key_cards: list[str] = field(default_factory=list)
    """Most important cards in the deck."""

    curve: dict = field(default_factory=dict)
    """Mana value distribution: {1: 4, 2: 8, 3: 12, ...}"""

    game_plan: str = ""
    """Text description of how to pilot this deck."""

    def to_dict(self) -> dict:
        """Convert to dictionary for caching."""
        return {
            "deck_hash": self.deck_hash,
            "archetype": self.archetype,
            "win_conditions": self.win_conditions,
            "key_cards": self.key_cards,
            "curve": self.curve,
            "game_plan": self.game_plan
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DeckAnalysis':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class MatchupAnalysis:
    """
    How our deck matches up against opponent's.

    Computed once per deck pair and shared across all cards.
    """
    matchup_hash: str

    our_role: str = "midrange"
    """Our role in this matchup: "beatdown" or "control" """

    their_threats: list[str] = field(default_factory=list)
    """Opponent cards we must answer."""

    their_answers: list[str] = field(default_factory=list)
    """Opponent cards that answer our cards."""

    game_plan: str = ""
    """How to approach this matchup."""

    key_turns: dict = field(default_factory=dict)
    """Critical turns: {4: "Watch for board wipe", 5: "Deploy threats"}"""

    def to_dict(self) -> dict:
        """Convert to dictionary for caching."""
        return {
            "matchup_hash": self.matchup_hash,
            "our_role": self.our_role,
            "their_threats": self.their_threats,
            "their_answers": self.their_answers,
            "game_plan": self.game_plan,
            "key_turns": self.key_turns
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'MatchupAnalysis':
        """Create from dictionary."""
        return cls(**data)
