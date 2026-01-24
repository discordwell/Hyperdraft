"""
Deck Definition and Utilities

Provides the Deck class for representing 60-card constructed decks.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeckEntry:
    """A single entry in a deck (card name + quantity)."""
    card_name: str
    quantity: int


@dataclass
class Deck:
    """
    A constructed deck with mainboard and optional sideboard.

    Standard decks are 60 cards mainboard, 15 cards sideboard.
    """
    name: str
    archetype: str  # e.g., "Aggro", "Control", "Midrange", "Combo"
    colors: list[str]  # e.g., ["U", "R"] for Izzet
    description: str

    mainboard: list[DeckEntry] = field(default_factory=list)
    sideboard: list[DeckEntry] = field(default_factory=list)

    # Metadata
    author: Optional[str] = None
    source: Optional[str] = None
    format: str = "Standard"

    @property
    def mainboard_count(self) -> int:
        """Total cards in mainboard."""
        return sum(e.quantity for e in self.mainboard)

    @property
    def sideboard_count(self) -> int:
        """Total cards in sideboard."""
        return sum(e.quantity for e in self.sideboard)

    @property
    def land_count(self) -> int:
        """Estimate land count (entries with 'Land' type names)."""
        land_keywords = ['Island', 'Forest', 'Plains', 'Mountain', 'Swamp',
                        'Verge', 'Passage', 'Tunnel', 'Pool', 'Foundry',
                        'Canal', 'Falls', 'Archive', 'Temple', 'Sanctuary']
        count = 0
        for entry in self.mainboard:
            if any(kw in entry.card_name for kw in land_keywords):
                count += entry.quantity
        return count

    def get_card_list(self) -> list[str]:
        """
        Get flat list of all mainboard cards (expanded by quantity).

        Returns list like: ["Lightning Bolt", "Lightning Bolt", "Mountain", ...]
        """
        cards = []
        for entry in self.mainboard:
            cards.extend([entry.card_name] * entry.quantity)
        return cards

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'archetype': self.archetype,
            'colors': self.colors,
            'description': self.description,
            'mainboard': [{'card': e.card_name, 'qty': e.quantity} for e in self.mainboard],
            'sideboard': [{'card': e.card_name, 'qty': e.quantity} for e in self.sideboard],
            'author': self.author,
            'source': self.source,
            'format': self.format,
            'mainboard_count': self.mainboard_count,
            'sideboard_count': self.sideboard_count,
            'land_count': self.land_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Deck':
        """Create deck from dictionary."""
        return cls(
            name=data['name'],
            archetype=data['archetype'],
            colors=data['colors'],
            description=data['description'],
            mainboard=[DeckEntry(e['card'], e['qty']) for e in data.get('mainboard', [])],
            sideboard=[DeckEntry(e['card'], e['qty']) for e in data.get('sideboard', [])],
            author=data.get('author'),
            source=data.get('source'),
            format=data.get('format', 'Standard'),
        )


def load_deck(card_registry: dict, deck: Deck) -> list:
    """
    Load a deck using a card registry.

    Returns list of CardDefinition objects for each card in mainboard.
    Missing cards are skipped with a warning.
    """
    cards = []
    missing = []

    for entry in deck.mainboard:
        card_def = card_registry.get(entry.card_name)
        if card_def:
            for _ in range(entry.quantity):
                cards.append(card_def)
        else:
            missing.append(entry.card_name)

    if missing:
        print(f"Warning: Missing cards in deck '{deck.name}': {missing}")

    return cards


def validate_deck(deck: Deck, min_cards: int = 60, max_copies: int = 4) -> tuple[bool, list[str]]:
    """
    Validate a deck meets format requirements.

    Returns (is_valid, list_of_errors).
    """
    errors = []

    # Check minimum deck size
    if deck.mainboard_count < min_cards:
        errors.append(f"Mainboard has {deck.mainboard_count} cards, need at least {min_cards}")

    # Check max copies (except basic lands)
    basic_lands = {'Island', 'Forest', 'Plains', 'Mountain', 'Swamp'}
    for entry in deck.mainboard:
        if entry.card_name not in basic_lands and entry.quantity > max_copies:
            errors.append(f"Too many copies of {entry.card_name}: {entry.quantity} (max {max_copies})")

    # Check sideboard size
    if deck.sideboard_count > 15:
        errors.append(f"Sideboard has {deck.sideboard_count} cards, max is 15")

    return len(errors) == 0, errors
