#!/usr/bin/env python3
"""Split a card-art manifest into even owned slices."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ("name", "prompt", "types", "subtypes", "expansion_code", "target_path")


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")
    cards = data.get("cards")
    if not isinstance(cards, list):
        raise ValueError("Manifest must contain a top-level 'cards' list")
    return data


def _normalize_card(card: Any, source_index: int) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError(f"Card at index {source_index} must be an object")
    missing = [field for field in REQUIRED_FIELDS if field not in card]
    if missing:
        raise ValueError(f"Card at index {source_index} is missing required fields: {', '.join(missing)}")
    name = card.get("name")
    target_path = card.get("target_path")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Card at index {source_index} has an invalid name")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError(f"Card '{name}' has an invalid target_path")
    return {"source_index": source_index, **{field: card.get(field) for field in REQUIRED_FIELDS}}


def _split_counts(total: int, slices: int) -> list[int]:
    if slices < 1:
        raise ValueError("--slices must be at least 1")
    base, remainder = divmod(total, slices)
    return [base + (1 if index < remainder else 0) for index in range(slices)]


def split_manifest(manifest_path: Path, out_dir: Path, slices: int) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    cards = [_normalize_card(card, index) for index, card in enumerate(manifest["cards"])]

    name_counts = Counter(card["name"] for card in cards)
    duplicate_names = sorted(name for name, count in name_counts.items() if count > 1)
    if duplicate_names:
        raise ValueError(f"Manifest contains duplicate card names: {', '.join(duplicate_names[:10])}")

    out_dir.mkdir(parents=True, exist_ok=True)
    counts = _split_counts(len(cards), slices)
    written = []
    cursor = 0

    for slice_index, count in enumerate(counts, start=1):
        chunk = cards[cursor : cursor + count]
        cursor += count
        payload = {
            "schema_version": "hyperdraft.card_art_slice.v1",
            "source_manifest": str(manifest_path),
            "source_schema_version": manifest.get("schema_version"),
            "slice_index": slice_index,
            "slice_count": slices,
            "card_count": len(chunk),
            "cards": chunk,
        }
        path = out_dir / f"slice-{slice_index:02d}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written.append({"path": str(path), "card_count": len(chunk)})

    index = {
        "schema_version": "hyperdraft.card_art_slices.v1",
        "source_manifest": str(manifest_path),
        "total_cards": len(cards),
        "slice_count": slices,
        "counts": counts,
        "files": written,
    }
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to a JSON manifest with a top-level cards list")
    parser.add_argument("--out", type=Path, required=True, help="Directory where slice JSON files will be written")
    parser.add_argument("--slices", type=int, default=6, help="Number of slices to create")
    args = parser.parse_args()

    index = split_manifest(args.manifest, args.out, args.slices)
    print(json.dumps(index, indent=2))


if __name__ == "__main__":
    main()
