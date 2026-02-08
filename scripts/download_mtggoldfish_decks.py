#!/usr/bin/env python3
"""
Download MTGGoldfish deck exports to data/netdecks/mtggoldfish/.

Examples:
  # Download specific deck IDs
  python scripts/download_mtggoldfish_decks.py --deck 7612489 --deck 7608383

  # Download top N decklists from a tournament page
  python scripts/download_mtggoldfish_decks.py --tournament https://www.mtggoldfish.com/tournament/61376 --top 8
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path


_DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "netdecks" / "mtggoldfish"


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Hyperdraft deck fetch)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _deck_download_url(deck_id: int) -> str:
    return f"https://www.mtggoldfish.com/deck/download/{deck_id}"


def _extract_deck_ids_from_tournament_html(html: str) -> list[int]:
    # Keep order, de-dupe.
    deck_ids: list[int] = []
    seen: set[int] = set()

    # Tournament pages link deck pages like: href="/deck/7608380"
    import re

    for m in re.finditer(r'href=\"/deck/(\\d+)\"', html):
        did = int(m.group(1))
        if did in seen:
            continue
        seen.add(did)
        deck_ids.append(did)

    return deck_ids


def _download_deck(deck_id: int, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = _fetch_text(_deck_download_url(deck_id))
    path = out_dir / f"{deck_id}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Download MTGGoldfish deck exports")
    p.add_argument("--deck", action="append", type=int, default=[], help="MTGGoldfish deck ID (repeatable)")
    p.add_argument("--tournament", type=str, default=None, help="MTGGoldfish tournament URL")
    p.add_argument("--top", type=int, default=8, help="Top N decks to download from tournament (default: 8)")
    p.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR, help="Output directory")
    args = p.parse_args(argv)

    deck_ids: list[int] = list(args.deck)

    if args.tournament:
        html = _fetch_text(args.tournament)
        tournament_decks = _extract_deck_ids_from_tournament_html(html)
        deck_ids.extend(tournament_decks[: max(0, args.top)])

    # De-dupe requested deck ids while preserving order.
    seen: set[int] = set()
    ordered: list[int] = []
    for did in deck_ids:
        if did in seen:
            continue
        seen.add(did)
        ordered.append(did)

    if not ordered:
        print("No deck IDs specified. Use --deck or --tournament.", file=sys.stderr)
        return 2

    for did in ordered:
        path = _download_deck(did, args.out_dir)
        print(f"Saved {did} -> {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

