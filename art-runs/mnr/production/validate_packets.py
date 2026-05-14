#!/usr/bin/env python3
"""Validate SCP card-art production packet files."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FIELDS = {
    "name",
    "source_index",
    "expansion_code",
    "archetype",
    "types",
    "subtypes",
    "target_path",
    "composition_rotation",
    "setting_faction",
    "card_type_direction",
    "location",
    "action",
    "focus",
    "mood",
    "artist_reference_title",
    "artist_reference_url",
    "reference_traits",
    "final_prompt",
    "negative_prompt",
    "qa_notes",
}


def _packet_list(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("cards"), list):
        return data["cards"]
    if isinstance(data, list):
        return data
    raise ValueError(f"{path} must be a list or object with a cards list")


def main() -> None:
    root = Path(__file__).resolve().parent
    paths = sorted(root.glob("slice-*-packets.json"))
    if not paths:
        raise SystemExit("No slice packet files found")

    total = 0
    names: list[str] = []
    errors: list[str] = []
    for path in paths:
        cards = _packet_list(path)
        total += len(cards)
        for index, card in enumerate(cards):
            missing = sorted(REQUIRED_FIELDS - set(card))
            if missing:
                errors.append(f"{path.name}[{index}] missing {', '.join(missing)}")
            name = card.get("name")
            if isinstance(name, str):
                names.append(name)
            prompt = card.get("final_prompt", "")
            if isinstance(prompt, str):
                normalized = prompt.lower()
                if "in the style of " in normalized or "style of <" in normalized:
                    errors.append(f"{path.name}[{index}] final_prompt uses exact style-imitation phrasing")
                for positive_token in ("include watermark", "add watermark", "with watermark", "official scp logo", "magic card frame"):
                    if positive_token in normalized:
                        errors.append(f"{path.name}[{index}] final_prompt asks for banned visual token: {positive_token}")

    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        errors.append(f"duplicate packet names: {', '.join(duplicate_names[:10])}")

    print(f"packet_files={len(paths)}")
    print(f"total_packets={total}")
    print(f"unique_names={len(set(names))}")
    if errors:
        print("errors:")
        for error in errors[:50]:
            print(f"- {error}")
        raise SystemExit(1)
    print("ok")


if __name__ == "__main__":
    main()
