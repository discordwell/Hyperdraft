"""
Scryfall Research Helpers

Lightweight client for fetching extra card context from Scryfall:
- oracle data via /cards/named
- rulings via the card's rulings_uri

This is meant for offline/precompute tools. It uses urllib to avoid adding
hard runtime deps.
"""

from __future__ import annotations

import json
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any


SCRYFALL_API = "https://api.scryfall.com"


@dataclass
class ScryfallCardContext:
    name: str
    oracle_text: str = ""
    type_line: str = ""
    mana_cost: str = ""
    rulings: list[str] = None  # human-readable one-line rulings

    def __post_init__(self) -> None:
        if self.rulings is None:
            self.rulings = []


class ScryfallClient:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        request_delay_s: float = 0.1,
        max_retries: int = 3,
        retry_delay_s: float = 1.0,
    ):
        self.cache_dir = cache_dir or (Path.home() / ".hyperdraft" / "scryfall_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "named").mkdir(exist_ok=True)
        (self.cache_dir / "rulings").mkdir(exist_ok=True)

        self.request_delay_s = request_delay_s
        self.max_retries = max_retries
        self.retry_delay_s = retry_delay_s
        # Global (per-client) rate limiting for concurrent callers.
        self._rate_lock = threading.Lock()
        self._next_request_time = 0.0

    def _fetch_json(self, url: str) -> dict[str, Any]:
        # Scryfall asks for ~50-100ms between requests. Enforce per-client pacing,
        # even with multiple threads calling into this client.
        now = time.time()
        with self._rate_lock:
            wait_until = max(now, self._next_request_time)
            self._next_request_time = wait_until + self.request_delay_s

        wait_s = wait_until - now
        if wait_s > 0:
            time.sleep(wait_s)

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Hyperdraft/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 429:
                    wait = self.retry_delay_s * (attempt + 1) * 2
                    time.sleep(wait)
                    continue
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay_s)
                    continue
                raise
            except Exception as e:
                last_err = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay_s)
                    continue
                raise

        raise RuntimeError(f"Failed to fetch {url}: {last_err}")

    def _cache_path(self, kind: str, key: str) -> Path:
        safe = "".join(c for c in key if c.isalnum() or c in ("-", "_", "."))
        return self.cache_dir / kind / f"{safe}.json"

    def get_named(self, name: str) -> Optional[dict[str, Any]]:
        """
        Fetch a card object by exact name (fallback fuzzy).
        Returns the raw Scryfall JSON object (or None if not found).
        """
        key = name
        path = self._cache_path("named", key)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # exact first, then fuzzy
        for mode in ("exact", "fuzzy"):
            q = urllib.parse.urlencode({mode: name})
            url = f"{SCRYFALL_API}/cards/named?{q}"
            try:
                data = self._fetch_json(url)
                path.write_text(json.dumps(data), encoding="utf-8")
                return data
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                raise
            except Exception:
                continue

        return None

    def get_rulings(self, rulings_uri: str) -> list[str]:
        """Fetch rulings for a card (returns list of one-line strings)."""
        if not rulings_uri:
            return []

        key = rulings_uri.split("/")[-1] or "rulings"
        path = self._cache_path("rulings", key)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return _format_rulings(raw)
            except Exception:
                pass

        try:
            raw = self._fetch_json(rulings_uri)
        except Exception:
            return []

        try:
            path.write_text(json.dumps(raw), encoding="utf-8")
        except Exception:
            pass

        return _format_rulings(raw)

    def get_card_context(self, name: str) -> Optional[ScryfallCardContext]:
        obj = self.get_named(name)
        if not obj:
            return None

        rulings = self.get_rulings(obj.get("rulings_uri", "")) if obj.get("rulings_uri") else []

        return ScryfallCardContext(
            name=obj.get("name", name),
            oracle_text=obj.get("oracle_text", "") or "",
            type_line=obj.get("type_line", "") or "",
            mana_cost=obj.get("mana_cost", "") or "",
            rulings=rulings,
        )


def _format_rulings(raw: dict[str, Any]) -> list[str]:
    data = raw.get("data", []) if isinstance(raw, dict) else []
    out: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = (item.get("comment") or "").strip()
        if not text:
            continue
        out.append(text)
    return out
