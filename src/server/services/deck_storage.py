"""
Deck Storage Service

File-based persistence for user-created decks.
Stores decks as JSON files in data/decks/ directory.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.decks.deck import Deck, DeckEntry


class DeckStorageService:
    """
    File-based deck storage service.

    Decks are stored as individual JSON files in data/decks/.
    An index.json file tracks all decks for fast listing.
    """

    def __init__(self, data_dir: str = "data/decks"):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / "index.json"
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index([])

    def _read_index(self) -> list[dict]:
        """Read the deck index."""
        try:
            with open(self.index_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_index(self, index: list[dict]):
        """Write the deck index."""
        with open(self.index_path, 'w') as f:
            json.dump(index, f, indent=2)

    def _deck_path(self, deck_id: str) -> Path:
        """Get the path for a deck file."""
        return self.data_dir / f"{deck_id}.json"

    def list_decks(self, game: Optional[str] = None) -> list[dict]:
        """
        List all saved decks with metadata.

        Args:
            game: If set, only return decks tagged with this game id. Decks
                  saved before the multi-game refactor have no `game` field
                  and are treated as MTG.

        Returns list of deck summaries (id, name, archetype, colors, etc.)
        """
        decks = self._read_index()
        if game is None:
            return decks
        return [d for d in decks if (d.get("game") or "mtg") == game]

    def get_deck(self, deck_id: str) -> Optional[dict]:
        """
        Get a deck by ID.

        Returns the full deck data or None if not found.
        """
        deck_path = self._deck_path(deck_id)
        if not deck_path.exists():
            return None

        try:
            with open(deck_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save_deck(
        self,
        name: str,
        archetype: str,
        colors: list[str],
        description: str,
        mainboard: list[dict],
        sideboard: list[dict] = None,
        format: str = "Standard",
        deck_id: str = None,
        game: str = "mtg",
    ) -> dict:
        """
        Save a new deck or update an existing one.

        Args:
            name: Deck name
            archetype: Deck archetype (Aggro, Control, etc.)
            colors: List of color codes (W, U, B, R, G)
            description: Deck description
            mainboard: List of {card: str, qty: int}
            sideboard: List of {card: str, qty: int}
            format: Format (Standard, Modern, etc.)
            deck_id: Optional ID for updates
            game: Which game this deck is for (mtg, minecraft, pokemon, yugioh, hearthstone)

        Returns:
            The saved deck data including ID
        """
        now = datetime.now(timezone.utc).isoformat()

        if deck_id is None:
            deck_id = str(uuid.uuid4())
            created_at = now
        else:
            # Preserve original creation time + original game tag if set
            existing = self.get_deck(deck_id)
            if existing:
                created_at = existing.get('created_at', now)
                # Don't let an update silently move a deck to a different game.
                game = existing.get('game') or game
            else:
                created_at = now

        deck_data = {
            'id': deck_id,
            'name': name,
            'archetype': archetype,
            'colors': colors,
            'description': description,
            'mainboard': mainboard,
            'sideboard': sideboard or [],
            'format': format,
            'game': game,
            'created_at': created_at,
            'updated_at': now,
        }

        # Calculate summary stats
        mainboard_count = sum(e.get('qty', 0) for e in mainboard)
        # Land count is MTG-specific — only compute when the deck is MTG.
        if game == "mtg":
            land_keywords = ['Island', 'Forest', 'Plains', 'Mountain', 'Swamp',
                            'Verge', 'Passage', 'Tunnel', 'Pool', 'Foundry',
                            'Canal', 'Falls', 'Archive', 'Temple', 'Sanctuary']
            land_count = sum(
                e.get('qty', 0) for e in mainboard
                if any(kw in e.get('card', '') for kw in land_keywords)
            )
        else:
            land_count = 0

        deck_data['mainboard_count'] = mainboard_count
        deck_data['land_count'] = land_count

        # Save deck file
        deck_path = self._deck_path(deck_id)
        with open(deck_path, 'w') as f:
            json.dump(deck_data, f, indent=2)

        # Update index
        index = self._read_index()
        index = [d for d in index if d.get('id') != deck_id]  # Remove old entry
        index.append({
            'id': deck_id,
            'name': name,
            'archetype': archetype,
            'colors': colors,
            'format': format,
            'game': game,
            'mainboard_count': mainboard_count,
            'land_count': land_count,
            'updated_at': now,
        })
        self._write_index(index)

        return deck_data

    def delete_deck(self, deck_id: str) -> bool:
        """
        Delete a deck by ID.

        Returns True if deleted, False if not found.
        """
        deck_path = self._deck_path(deck_id)
        if not deck_path.exists():
            return False

        # Remove file
        os.remove(deck_path)

        # Update index
        index = self._read_index()
        index = [d for d in index if d.get('id') != deck_id]
        self._write_index(index)

        return True

    def to_deck_object(self, deck_data: dict) -> Deck:
        """
        Convert stored deck data to a Deck object.
        """
        return Deck(
            name=deck_data['name'],
            archetype=deck_data['archetype'],
            colors=deck_data['colors'],
            description=deck_data['description'],
            mainboard=[
                DeckEntry(e['card'], e['qty'])
                for e in deck_data.get('mainboard', [])
            ],
            sideboard=[
                DeckEntry(e['card'], e['qty'])
                for e in deck_data.get('sideboard', [])
            ],
            format=deck_data.get('format', 'Standard'),
        )


# Global service instance
deck_storage = DeckStorageService()
