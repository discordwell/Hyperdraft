#!/usr/bin/env python3
"""
Snapshot rendered card text for fan sets that use the src/engine/abilities/ DSL.

Captures each card's identity plus rendered text into a deterministic JSON file.
Intended as ground truth before migrating away from the abilities DSL; after
migration, diff the new rendered text against this snapshot to catch drift.

Usage:
    python scripts/snapshot_fan_set_text.py

Output:
    tests/fixtures/fan_set_card_text_snapshot.json

Constraints:
    - Deterministic output (sort_keys=True, no timestamps, stable ordering).
    - Do not modify any card or engine files.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path so `src.*` imports resolve when run as a script.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import CardDefinition  # noqa: E402

# The 5 fan-set modules targeted for the abilities-DSL migration.
TARGET_MODULES = [
    "src.cards.custom.studio_ghibli",
    "src.cards.custom.naruto",
    "src.cards.custom.my_hero_academia",
    "src.cards.custom.attack_on_titan",
    "src.cards.custom.jujutsu_kaisen",
]

OUTPUT_PATH = REPO_ROOT / "tests" / "fixtures" / "fan_set_card_text_snapshot.json"


def _set_to_sorted_list(value: Any) -> Any:
    """Normalize sets to sorted lists for deterministic JSON."""
    if isinstance(value, (set, frozenset)):
        return sorted(
            [_normalize_enum(v) for v in value],
            key=lambda x: str(x),
        )
    return value


def _normalize_enum(value: Any) -> Any:
    """Convert enums (CardType, Color) to their stable .name/.value string."""
    if value is None:
        return None
    # Enum-like: has `name` or `value`
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    val = getattr(value, "value", None)
    if isinstance(val, (str, int)):
        return val
    return value


def _normalize_enum_set(value: Any) -> list:
    if not value:
        return []
    return sorted([_normalize_enum(v) for v in value], key=lambda x: str(x))


def _keyword_list_from_abilities(abilities: list) -> list[str]:
    """Extract keyword strings from Characteristics.abilities (list of dicts)."""
    out = []
    for a in abilities or []:
        if isinstance(a, dict):
            kw = a.get("keyword")
            if kw:
                out.append(str(kw).lower())
    return sorted(set(out))


def _has_text_source(source_lines: list[str]) -> bool | None:
    """
    Heuristic: does this card's source include an explicit `text=` kwarg?

    Returns None if we can't find the definition (e.g., card came from a helper).
    """
    joined = "".join(source_lines)
    # Strip whitespace variations; looking for `text=` kwarg in the call.
    # Rough heuristic — good enough to bucket cards into hand-written vs auto.
    return "text=" in joined


def _locate_card_sources(module) -> dict[int, dict]:
    """
    Map id(card_def) -> {var_name, has_text_kwarg} for every module-level
    CardDefinition attribute. has_text_kwarg is inferred from the module
    source by locating the assignment line and reading until its closing paren.
    """
    try:
        source = inspect.getsource(module)
    except (OSError, TypeError):
        source = ""
    source_lines = source.splitlines(keepends=True)

    # Map var_name -> (start_line_idx, end_line_idx) from assignments of the form
    # `VAR_NAME = <something>` at column 0, where <something> is a call spanning
    # until the matching close paren.
    assignments: dict[str, tuple[int, int]] = {}
    i = 0
    while i < len(source_lines):
        line = source_lines[i]
        # Look for top-level `VAR = ` (no leading whitespace) with uppercase var.
        stripped = line.lstrip()
        if (
            line
            and line[0].isalpha()
            and line[0].isupper()
            and "=" in line
            and not line.startswith("class ")
            and not line.startswith("def ")
        ):
            # e.g., "FOO_BAR = make_creature("
            name_part, _, _ = line.partition("=")
            name_part = name_part.strip()
            if name_part.replace("_", "").isalnum() and name_part.isupper():
                start = i
                # Walk until balanced parens or blank line (for simple scalar).
                depth = line.count("(") - line.count(")")
                j = i
                while depth > 0 and j + 1 < len(source_lines):
                    j += 1
                    depth += source_lines[j].count("(") - source_lines[j].count(")")
                assignments[name_part] = (start, j)
                i = j + 1
                continue
        i += 1

    result: dict[int, dict] = {}
    for var_name, obj in vars(module).items():
        if not isinstance(obj, CardDefinition):
            continue
        info: dict[str, Any] = {"var_name": var_name}
        if var_name in assignments:
            s, e = assignments[var_name]
            block = source_lines[s : e + 1]
            info["has_text_kwarg"] = _has_text_source(block)
        else:
            info["has_text_kwarg"] = None
        result[id(obj)] = info
    return result


def _card_fingerprint(card: CardDefinition, var_name: str) -> dict:
    """Build the snapshot record for a single card."""
    chars = card.characteristics
    abilities = card.abilities or []

    ability_fingerprints = []
    for ab in abilities:
        entry: dict[str, Any] = {"class": f"{type(ab).__module__}.{type(ab).__name__}"}
        # Best-effort introspection of ability internals for spot checks.
        render = None
        if hasattr(ab, "render_text"):
            try:
                render = ab.render_text(card.name)
            except Exception as exc:
                render = f"<render_error: {type(exc).__name__}: {exc}>"
        entry["render_text"] = render
        # Pull shallow attribute fingerprint (names of sub-objects).
        attrs = {}
        for attr_name in ("trigger", "effect", "filter", "static_effect", "keyword"):
            if hasattr(ab, attr_name):
                val = getattr(ab, attr_name)
                attrs[attr_name] = f"{type(val).__module__}.{type(val).__name__}" if val is not None else None
        entry["attrs"] = attrs
        ability_fingerprints.append(entry)

    return {
        "var_name": var_name,
        "name": card.name,
        "text": card.text or "",
        "mana_cost": card.mana_cost,
        "domain": card.domain,
        "rarity": card.rarity,
        "types": _normalize_enum_set(chars.types),
        "subtypes": sorted(chars.subtypes or []),
        "supertypes": sorted(chars.supertypes or []),
        "colors": _normalize_enum_set(chars.colors),
        "power": chars.power,
        "toughness": chars.toughness,
        "keywords": _keyword_list_from_abilities(chars.abilities),
        "has_setup_interceptors": card.setup_interceptors is not None,
        "has_resolve": card.resolve is not None,
        "abilities_count": len(abilities),
        "abilities_fingerprint": ability_fingerprints,
    }


def snapshot() -> dict:
    modules_data: dict[str, dict] = {}
    summary: dict[str, dict] = {}

    for mod_name in TARGET_MODULES:
        module = importlib.import_module(mod_name)
        source_info = _locate_card_sources(module)

        # Prefer the module's CARDS list (canonical registration order) when present;
        # otherwise fall back to module-level attribute order.
        cards_list = getattr(module, "CARDS", None)
        if cards_list is not None:
            # De-duplicate while preserving order.
            seen = set()
            ordered_cards = []
            for c in cards_list:
                if isinstance(c, CardDefinition) and id(c) not in seen:
                    seen.add(id(c))
                    ordered_cards.append(c)
        else:
            ordered_cards = [
                v for v in vars(module).values() if isinstance(v, CardDefinition)
            ]

        card_records: dict[str, dict] = {}
        auto_text = 0
        hand_text = 0
        unknown_text = 0

        for card in ordered_cards:
            info = source_info.get(id(card), {})
            var_name = info.get("var_name")
            if var_name is None:
                # Try to locate by scanning module attributes (cards created via
                # helpers may not be bound to a module-level var).
                for k, v in vars(module).items():
                    if v is card:
                        var_name = k
                        break
            if var_name is None:
                var_name = f"<anon:{card.name}>"

            record = _card_fingerprint(card, var_name)
            card_records[var_name] = record

            has_text_kw = info.get("has_text_kwarg")
            if has_text_kw is True:
                hand_text += 1
            elif has_text_kw is False:
                auto_text += 1
            else:
                unknown_text += 1

        modules_data[mod_name] = card_records
        summary[mod_name] = {
            "card_count": len(card_records),
            "hand_written_text": hand_text,
            "auto_generated_text": auto_text,
            "text_source_unknown": unknown_text,
        }

    return {
        "schema_version": 1,
        "summary": {
            "total_cards": sum(m["card_count"] for m in summary.values()),
            "per_module": summary,
        },
        "cards": modules_data,
    }


def main() -> int:
    data = snapshot()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic: sort keys, stable separators, trailing newline.
    payload = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)
    OUTPUT_PATH.write_text(payload + "\n", encoding="utf-8")

    # Brief console summary.
    total = data["summary"]["total_cards"]
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} ({total} cards)")
    for mod, stats in data["summary"]["per_module"].items():
        print(
            f"  {mod}: {stats['card_count']} cards "
            f"(hand-written text={stats['hand_written_text']}, "
            f"auto={stats['auto_generated_text']}, "
            f"unknown={stats['text_source_unknown']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
