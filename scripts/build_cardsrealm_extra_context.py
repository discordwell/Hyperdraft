#!/usr/bin/env python3
"""
Build per-card extra context (web research) from Cardsrealm card pages.

Outputs a JSON file suitable for:
  scripts/precompute_card_strategies.py --extra-context-json <file>

We currently use Cardsrealm because:
- It has per-card human-readable "About" / review text (strategy-ish).
- Pages are statically fetchable (no JS required).

This script is intentionally lightweight: urllib + simple string parsing.
"""

from __future__ import annotations

import argparse
import json
import html as html_lib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, ".")

from src.cards.set_registry import get_cards_in_set, get_set_info  # noqa: E402


CARDSREALM_BASE = "https://mtg.cardsrealm.com/en-us/card"


def _slugify_card_name(name: str) -> str:
    s = name.lower()
    # Drop punctuation that commonly appears in card names.
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s


def _fetch(url: str, *, timeout_s: int = 30) -> str:
    headers = {
        "User-Agent": "Hyperdraft/1.0 (+https://github.com/discordwell/Hyperdraft)",
        "Accept": "text/html,application/xhtml+xml",
    }

    # Cardsrealm occasionally returns transient 5xx errors. Retry a bit.
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (500, 502, 503, 504) and attempt < 2:
                time.sleep(0.75 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.75 * (attempt + 1))
                continue
            raise

    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _extract_json_string_field(html: str, field: str) -> str | None:
    """
    Extract a JSON string field value from raw HTML, handling escapes.

    Looks for: "<field>": "<json string>"
    """
    marker = f"\"{field}\""
    start = html.find(marker)
    if start == -1:
        return None

    colon = html.find(":", start)
    if colon == -1:
        return None

    # Find opening quote of JSON string.
    q0 = html.find('"', colon + 1)
    if q0 == -1:
        return None

    # Scan to closing quote, respecting backslash escapes.
    i = q0 + 1
    esc = False
    while i < len(html):
        ch = html[i]
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            break
        i += 1

    if i >= len(html) or html[i] != '"':
        return None

    try:
        return json.loads(html[q0 : i + 1])
    except Exception:
        return None


def _extract_meta_types(html: str) -> list[str]:
    # Examples:
    #   <li class="meta_type_li"><a href="/en-us/card/?&types=card_life">Life gain</a></li>
    return [m.strip() for m in re.findall(r'meta_type_li\"><a[^>]*>([^<]+)</a>', html)]


@dataclass
class CardContext:
    name: str
    url: str
    review_body: str | None
    meta_types: list[str]

    def to_lines(self) -> list[str]:
        out: list[str] = []
        if self.review_body:
            out.append(f"Cardsrealm review: {self.review_body.strip()}")
        if self.meta_types:
            out.append("Cardsrealm meta types: " + ", ".join(self.meta_types))
        out.append(f"Cardsrealm source: {self.url}")
        return out


def _build_one(name: str, *, cache_dir: Path | None, sleep_s: float) -> CardContext:
    slug = _slugify_card_name(name)
    url = f"{CARDSREALM_BASE}/{urllib.parse.quote(slug)}"

    cache_path = (cache_dir / f"{slug}.html") if cache_dir else None
    html: str
    if cache_path and cache_path.exists():
        html = cache_path.read_text(encoding="utf-8", errors="replace")
    else:
        html = _fetch(url)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(html, encoding="utf-8")

    # "reviewBody" seems to be the most useful compact play guidance on the page.
    review = _extract_json_string_field(html, "reviewBody")
    if review:
        review = html_lib.unescape(review)
    meta_types = _extract_meta_types(html)

    if sleep_s > 0:
        time.sleep(sleep_s)

    return CardContext(name=name, url=url, review_body=review, meta_types=meta_types)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--set-code", required=True, help="Set code in Hyperdraft set registry (e.g., BIG, MKM, OTJ)")
    p.add_argument("--out", default=None, help="Output JSON path (default: logs/cardsrealm_<set>.json)")
    p.add_argument("--cache-dir", default="logs/cardsrealm_cache", help="Cache directory for fetched HTML")
    p.add_argument("--no-cache", action="store_true", help="Disable cache reads/writes")
    p.add_argument("--sleep", type=float, default=0.25, help="Sleep between requests (seconds)")
    args = p.parse_args(argv)

    set_info = get_set_info(args.set_code)
    cards = get_cards_in_set(args.set_code)
    if not cards:
        print(f"Unknown or empty set code: {args.set_code}", file=sys.stderr)
        return 2

    out_path = Path(args.out or f"logs/cardsrealm_{args.set_code.upper()}.json")
    cache_dir = None if args.no_cache else Path(args.cache_dir)

    context_map: dict[str, list[str]] = {}
    failed: list[str] = []

    names = sorted(cards.keys())
    for idx, name in enumerate(names, start=1):
        try:
            ctx = _build_one(name, cache_dir=cache_dir, sleep_s=max(0.0, float(args.sleep)))
            context_map[name] = ctx.to_lines()
            if ctx.review_body is None:
                failed.append(name)
        except urllib.error.HTTPError as e:
            failed.append(name)
            context_map[name] = [f"Cardsrealm fetch failed: HTTP {e.code} for {name}", f"Cardsrealm source: {CARDSREALM_BASE}/{_slugify_card_name(name)}"]
        except Exception as e:
            failed.append(name)
            context_map[name] = [f"Cardsrealm fetch failed: {e}", f"Cardsrealm source: {CARDSREALM_BASE}/{_slugify_card_name(name)}"]

        if idx % 10 == 0:
            label = f"{set_info.name} ({set_info.code})" if set_info else args.set_code.upper()
            print(f"[{label}] processed {idx}/{len(names)}", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(context_map, indent=2, sort_keys=True), encoding="utf-8")

    if failed:
        print(f"Wrote {out_path} but {len(failed)} cards had no reviewBody (still wrote source/meta types).", file=sys.stderr)
    else:
        print(f"Wrote {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
