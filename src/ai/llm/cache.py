"""
Multi-tier LLM Response Cache

Persistent caching for LLM responses across sessions.
Supports card patterns, deck analysis, and matchup caching.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class CacheEntry:
    """A cached value with timestamp."""
    value: Any
    timestamp: float
    model: str
    hits: int = 0


class LLMCache:
    """
    Multi-tier persistent cache for LLM responses.

    Tiers:
    - Card patterns: Long-lived (24hr TTL), cached globally by card name
    - Deck analysis: Medium-lived (12hr TTL), cached by deck hash
    - Matchups: Per-matchup (6hr TTL), cached by deck pair hash
    """

    # TTLs in seconds
    CARD_TTL = 86400      # 24 hours
    DECK_TTL = 43200      # 12 hours
    MATCHUP_TTL = 21600   # 6 hours

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the cache.

        Args:
            cache_dir: Directory for persistent cache files.
                      Defaults to ~/.hyperdraft/llm_cache/
        """
        self.cache_dir = cache_dir or Path.home() / ".hyperdraft" / "llm_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (self.cache_dir / "cards").mkdir(exist_ok=True)
        (self.cache_dir / "decks").mkdir(exist_ok=True)
        (self.cache_dir / "matchups").mkdir(exist_ok=True)

        # In-memory caches for fast access
        self._card_cache: dict[str, CacheEntry] = {}
        self._deck_cache: dict[str, CacheEntry] = {}
        self._matchup_cache: dict[str, CacheEntry] = {}

    def _hash(self, *args) -> str:
        """Create a short hash from arguments."""
        data = json.dumps(args, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _hash_deck(self, deck_cards: list[str]) -> str:
        """Create a hash for a deck (list of card names)."""
        sorted_cards = sorted(deck_cards)
        return self._hash("deck", sorted_cards)

    def _hash_matchup(self, our_deck: list[str], opp_deck: list[str]) -> str:
        """Create a hash for a matchup (two decks)."""
        our_hash = self._hash_deck(our_deck)
        opp_hash = self._hash_deck(opp_deck)
        return self._hash("matchup", our_hash, opp_hash)

    # === Card Pattern Cache ===

    def get_card_strategy(self, card_name: str) -> Optional[dict]:
        """
        Get cached card strategy.

        Checks memory first, then disk.
        """
        key = self._hash("card_strategy", card_name)

        # Check memory
        if key in self._card_cache:
            entry = self._card_cache[key]
            if time.time() - entry.timestamp < self.CARD_TTL:
                entry.hits += 1
                return entry.value

        # Check disk
        path = self.cache_dir / "cards" / f"{key}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if time.time() - data["timestamp"] < self.CARD_TTL:
                    entry = CacheEntry(
                        value=data["value"],
                        timestamp=data["timestamp"],
                        model=data.get("model", "unknown"),
                        hits=data.get("hits", 0) + 1
                    )
                    self._card_cache[key] = entry
                    return entry.value
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def set_card_strategy(self, card_name: str, strategy: dict, model: str = "unknown"):
        """Cache a card strategy."""
        key = self._hash("card_strategy", card_name)

        entry = CacheEntry(
            value=strategy,
            timestamp=time.time(),
            model=model
        )
        self._card_cache[key] = entry

        # Persist to disk
        path = self.cache_dir / "cards" / f"{key}.json"
        path.write_text(json.dumps({
            "value": strategy,
            "timestamp": entry.timestamp,
            "model": model,
            "card_name": card_name
        }))

    # === Deck Role Cache ===

    def get_deck_role(self, card_name: str, deck_cards: list[str]) -> Optional[dict]:
        """Get cached deck role for a card in a specific deck."""
        deck_hash = self._hash_deck(deck_cards)
        key = self._hash("deck_role", card_name, deck_hash)

        if key in self._deck_cache:
            entry = self._deck_cache[key]
            if time.time() - entry.timestamp < self.DECK_TTL:
                entry.hits += 1
                return entry.value

        path = self.cache_dir / "decks" / f"{key}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if time.time() - data["timestamp"] < self.DECK_TTL:
                    entry = CacheEntry(
                        value=data["value"],
                        timestamp=data["timestamp"],
                        model=data.get("model", "unknown")
                    )
                    self._deck_cache[key] = entry
                    return entry.value
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def set_deck_role(
        self,
        card_name: str,
        deck_cards: list[str],
        role: dict,
        model: str = "unknown"
    ):
        """Cache a deck role."""
        deck_hash = self._hash_deck(deck_cards)
        key = self._hash("deck_role", card_name, deck_hash)

        entry = CacheEntry(
            value=role,
            timestamp=time.time(),
            model=model
        )
        self._deck_cache[key] = entry

        path = self.cache_dir / "decks" / f"{key}.json"
        path.write_text(json.dumps({
            "value": role,
            "timestamp": entry.timestamp,
            "model": model,
            "card_name": card_name,
            "deck_hash": deck_hash
        }))

    # === Matchup Guide Cache ===

    def get_matchup_guide(
        self,
        card_name: str,
        our_deck: list[str],
        opp_deck: list[str]
    ) -> Optional[dict]:
        """Get cached matchup guide for a card."""
        matchup_hash = self._hash_matchup(our_deck, opp_deck)
        key = self._hash("matchup_guide", card_name, matchup_hash)

        if key in self._matchup_cache:
            entry = self._matchup_cache[key]
            if time.time() - entry.timestamp < self.MATCHUP_TTL:
                entry.hits += 1
                return entry.value

        path = self.cache_dir / "matchups" / f"{key}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if time.time() - data["timestamp"] < self.MATCHUP_TTL:
                    entry = CacheEntry(
                        value=data["value"],
                        timestamp=data["timestamp"],
                        model=data.get("model", "unknown")
                    )
                    self._matchup_cache[key] = entry
                    return entry.value
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def set_matchup_guide(
        self,
        card_name: str,
        our_deck: list[str],
        opp_deck: list[str],
        guide: dict,
        model: str = "unknown"
    ):
        """Cache a matchup guide."""
        matchup_hash = self._hash_matchup(our_deck, opp_deck)
        key = self._hash("matchup_guide", card_name, matchup_hash)

        entry = CacheEntry(
            value=guide,
            timestamp=time.time(),
            model=model
        )
        self._matchup_cache[key] = entry

        path = self.cache_dir / "matchups" / f"{key}.json"
        path.write_text(json.dumps({
            "value": guide,
            "timestamp": entry.timestamp,
            "model": model,
            "card_name": card_name,
            "matchup_hash": matchup_hash
        }))

    # === Deck Analysis Cache ===

    def get_deck_analysis(self, deck_cards: list[str]) -> Optional[dict]:
        """Get cached overall deck analysis."""
        deck_hash = self._hash_deck(deck_cards)
        key = self._hash("deck_analysis", deck_hash)

        if key in self._deck_cache:
            entry = self._deck_cache[key]
            if time.time() - entry.timestamp < self.DECK_TTL:
                entry.hits += 1
                return entry.value

        path = self.cache_dir / "decks" / f"{key}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if time.time() - data["timestamp"] < self.DECK_TTL:
                    entry = CacheEntry(
                        value=data["value"],
                        timestamp=data["timestamp"],
                        model=data.get("model", "unknown")
                    )
                    self._deck_cache[key] = entry
                    return entry.value
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def set_deck_analysis(self, deck_cards: list[str], analysis: dict, model: str = "unknown"):
        """Cache deck analysis."""
        deck_hash = self._hash_deck(deck_cards)
        key = self._hash("deck_analysis", deck_hash)

        entry = CacheEntry(
            value=analysis,
            timestamp=time.time(),
            model=model
        )
        self._deck_cache[key] = entry

        path = self.cache_dir / "decks" / f"{key}.json"
        path.write_text(json.dumps({
            "value": analysis,
            "timestamp": entry.timestamp,
            "model": model,
            "deck_hash": deck_hash
        }))

    # === Matchup Analysis Cache ===

    def get_matchup_analysis(self, our_deck: list[str], opp_deck: list[str]) -> Optional[dict]:
        """Get cached matchup analysis."""
        matchup_hash = self._hash_matchup(our_deck, opp_deck)
        key = self._hash("matchup_analysis", matchup_hash)

        if key in self._matchup_cache:
            entry = self._matchup_cache[key]
            if time.time() - entry.timestamp < self.MATCHUP_TTL:
                entry.hits += 1
                return entry.value

        path = self.cache_dir / "matchups" / f"{key}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if time.time() - data["timestamp"] < self.MATCHUP_TTL:
                    entry = CacheEntry(
                        value=data["value"],
                        timestamp=data["timestamp"],
                        model=data.get("model", "unknown")
                    )
                    self._matchup_cache[key] = entry
                    return entry.value
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def set_matchup_analysis(
        self,
        our_deck: list[str],
        opp_deck: list[str],
        analysis: dict,
        model: str = "unknown"
    ):
        """Cache matchup analysis."""
        matchup_hash = self._hash_matchup(our_deck, opp_deck)
        key = self._hash("matchup_analysis", matchup_hash)

        entry = CacheEntry(
            value=analysis,
            timestamp=time.time(),
            model=model
        )
        self._matchup_cache[key] = entry

        path = self.cache_dir / "matchups" / f"{key}.json"
        path.write_text(json.dumps({
            "value": analysis,
            "timestamp": entry.timestamp,
            "model": model,
            "matchup_hash": matchup_hash
        }))

    # === Cache Management ===

    def clear_memory_cache(self):
        """Clear in-memory caches (disk cache remains)."""
        self._card_cache.clear()
        self._deck_cache.clear()
        self._matchup_cache.clear()

    def clear_all(self):
        """Clear all caches including disk."""
        self.clear_memory_cache()

        import shutil
        for subdir in ["cards", "decks", "matchups"]:
            path = self.cache_dir / subdir
            if path.exists():
                shutil.rmtree(path)
                path.mkdir()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        card_files = list((self.cache_dir / "cards").glob("*.json"))
        deck_files = list((self.cache_dir / "decks").glob("*.json"))
        matchup_files = list((self.cache_dir / "matchups").glob("*.json"))

        return {
            "card_cache": {
                "memory": len(self._card_cache),
                "disk": len(card_files)
            },
            "deck_cache": {
                "memory": len(self._deck_cache),
                "disk": len(deck_files)
            },
            "matchup_cache": {
                "memory": len(self._matchup_cache),
                "disk": len(matchup_files)
            }
        }
