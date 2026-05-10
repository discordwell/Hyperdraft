"""Export draw/image-generation prompts for the SCP card pool.

The manifest is intentionally data-only. A draw worker can consume each prompt
and write the generated PNG to the target path without importing the game
engine or guessing card metadata.

Usage:
    python -m scripts.art.scp_art_manifest --out frontend/public/scp_art_manifest.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from src.cards.scp import SCP_CARDS


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "scp-card"


def build_manifest() -> dict[str, Any]:
    cards = []
    for name, card in sorted(SCP_CARDS.items(), key=lambda item: (getattr(item[1], "scp_expansion_code", ""), item[0])):
        expansion_code = getattr(card, "scp_expansion_code", None) or "CORE"
        cards.append({
            "name": name,
            "expansion": getattr(card, "scp_expansion", None),
            "expansion_code": expansion_code,
            "archetype": getattr(card, "scp_archetype", None),
            "rarity": card.rarity or "common",
            "types": sorted(card_type.name for card_type in card.characteristics.types),
            "subtypes": sorted(card.characteristics.subtypes or []),
            "prompt": getattr(card, "scp_art_prompt", None),
            "target_path": f"frontend/public/scp-art/{expansion_code.lower()}/{_slug(name)}.png",
        })
    return {
        "schema_version": "hyperdraft.scp_art_manifest.v1",
        "card_count": len(cards),
        "cards": cards,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="frontend/public/scp_art_manifest.json")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(build_manifest(), indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
