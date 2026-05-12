"""Report card-text depth for custom existing-game sets.

The score is intentionally heuristic. It is a repeatable NG+ gate for finding
thin cards, not a rules oracle.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


CLAUSE_RE = re.compile(
    r"[.;:]|\bwhen\b|\bwhenever\b|\bat\b|\bif\b|\bunless\b|\buntil\b|"
    r"\bthen\b|\bchoose\b|\btarget\b|\bonce\b|\bafter\b|\bbefore\b|"
    r"\bactivate\b|\bequip\b|\bevolve\b|\bdiscard\b|\bsacrifice\b|"
    r"\bsearch\b|\bdraw\b|\bdestroy\b|\breturn\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[A-Za-z0-9+/-]+")


@dataclass(frozen=True)
class DepthSet:
    label: str
    registry_path: str
    import_path: str
    registry_name: str


SETS = {
    "modern_mtg": DepthSet(
        label="Modern MTG benchmark",
        registry_path="src.cards.bloomburrow:BLOOMBURROW_CARDS",
        import_path="src.cards.bloomburrow",
        registry_name="BLOOMBURROW_CARDS",
    ),
    "mtg_pkh": DepthSet(
        label="MTG PKH",
        registry_path="src.cards.custom.pokemon_horizons:POKEMON_HORIZONS_CARDS",
        import_path="src.cards.custom.pokemon_horizons",
        registry_name="POKEMON_HORIZONS_CARDS",
    ),
    "hearthstone_custom": DepthSet(
        label="Hearthstone custom",
        registry_path="src.cards.hearthstone.decks:custom",
        import_path="src.cards.hearthstone.decks",
        registry_name="custom",
    ),
    "pokemon_brv": DepthSet(
        label="Pokemon Beyond Ravnica",
        registry_path="src.cards.pokemon.beyond.ravnica:BEYOND_RAVNICA_CARDS",
        import_path="src.cards.pokemon.beyond.ravnica",
        registry_name="BEYOND_RAVNICA_CARDS",
    ),
    "ygo_bk": DepthSet(
        label="YGO Beyond Kamigawa",
        registry_path="src.cards.yugioh.beyond.kamigawa:BEYOND_KAMIGAWA_CARDS",
        import_path="src.cards.yugioh.beyond.kamigawa",
        registry_name="BEYOND_KAMIGAWA_CARDS",
    ),
}


def _import_module(path: str):
    import importlib

    with contextlib.redirect_stdout(sys.stderr):
        return importlib.import_module(path)


def _dedupe_cards(cards: Iterable) -> list:
    seen: set[int] = set()
    unique = []
    for card in cards:
        if id(card) in seen:
            continue
        seen.add(id(card))
        unique.append(card)
    return unique


def _load_cards(spec: DepthSet) -> list:
    module = _import_module(spec.import_path)
    if spec.registry_name == "custom":
        cards = []
        with contextlib.redirect_stdout(sys.stderr):
            from src.cards.hearthstone.stormrift import STORMRIFT_DECKS
            from src.cards.hearthstone.frierenrift import FRIERENRIFT_DECKS
            from src.cards.hearthstone.riftclash import RIFTCLASH_DECKS

            custom_decks = {
                **{f"Stormrift {name}": deck for name, deck in STORMRIFT_DECKS.items()},
                **{f"Frierenrift {name}": deck for name, deck in FRIERENRIFT_DECKS.items()},
                **{f"Riftclash {name}": deck for name, deck in RIFTCLASH_DECKS.items()},
            }
            for deck in custom_decks.values():
                cards.extend(deck)
        return _dedupe_cards(cards)

    registry = getattr(module, spec.registry_name)
    if isinstance(registry, dict):
        return list(registry.values())
    return list(registry)


def _text_blob(card) -> str:
    parts: list[str] = []
    text = getattr(card, "text", "") or ""
    if text:
        parts.append(text)
    ability = getattr(card, "ability", None)
    if isinstance(ability, dict):
        parts.extend(str(ability.get(k, "")) for k in ("name", "text") if ability.get(k))
    for attack in getattr(card, "attacks", []) or []:
        if not isinstance(attack, dict):
            continue
        for key in ("name", "text"):
            val = attack.get(key)
            if val:
                parts.append(str(val))
        damage = attack.get("damage", 0)
        if damage:
            parts.append(f"damage {damage}")
    for field_name in ("ygo_spell_type", "ygo_trap_type", "ygo_monster_type"):
        val = getattr(card, field_name, None)
        if val:
            parts.append(str(val))
    return " ".join(parts)


def card_depth(card) -> dict:
    text = _text_blob(card)
    chars = getattr(card, "characteristics", None)
    keywords = set()
    if chars is not None:
        keywords |= set(getattr(chars, "keywords", set()) or set())
    for ability in getattr(card, "abilities", []) or []:
        if isinstance(ability, dict) and ability.get("keyword"):
            keywords.add(str(ability["keyword"]).lower())
    words = len(WORD_RE.findall(text))
    clauses = len(CLAUSE_RE.findall(text))
    wired = int(any(
        getattr(card, attr, None)
        for attr in (
            "setup_interceptors",
            "setup_in_graveyard",
            "setup_in_hand",
            "battlecry",
            "deathrattle",
            "spell_effect",
            "resolve",
        )
    ))
    wired += sum(
        1
        for attack in getattr(card, "attacks", []) or []
        if isinstance(attack, dict) and attack.get("effect_fn")
    )
    if getattr(card, "ability", None) and getattr(card, "ability", {}).get("effect_fn"):
        wired += 1
    score = words + clauses * 4 + len(keywords) * 3 + min(wired, 3) * 8
    return {
        "name": getattr(card, "name", "unknown"),
        "score": score,
        "words": words,
        "clauses": clauses,
        "keywords": sorted(keywords),
        "wired_hooks": wired,
        "text": text,
    }


def summarize_set(cards: list, *, thin_threshold: int = 28) -> dict:
    rows = [card_depth(card) for card in cards if getattr(card, "name", None)]
    if not rows:
        return {
            "card_count": 0,
            "avg_score": 0,
            "median_score": 0,
            "thin_count": 0,
            "thin_pct": 0,
            "wired_pct": 0,
            "thinnest": [],
        }
    scores = [row["score"] for row in rows]
    thin = [row for row in rows if row["score"] < thin_threshold]
    return {
        "card_count": len(rows),
        "avg_score": round(statistics.mean(scores), 2),
        "median_score": round(statistics.median(scores), 2),
        "avg_words": round(statistics.mean(row["words"] for row in rows), 2),
        "thin_threshold": thin_threshold,
        "thin_count": len(thin),
        "thin_pct": round(len(thin) / len(rows) * 100, 1),
        "wired_pct": round(
            sum(1 for row in rows if row["wired_hooks"] > 0) / len(rows) * 100,
            1,
        ),
        "thinnest": [
            {
                "name": row["name"],
                "score": row["score"],
                "text": row["text"][:180],
            }
            for row in sorted(rows, key=lambda r: (r["score"], r["name"]))[:12]
        ],
    }


def build_report(set_names: list[str], thin_threshold: int) -> dict:
    report = {
        "schema_version": "hyperdraft.custom_set_depth_report.v1",
        "thin_threshold": thin_threshold,
        "sets": {},
    }
    benchmark_score = None
    if "modern_mtg" not in set_names:
        set_names = ["modern_mtg", *set_names]
    for name in set_names:
        spec = SETS[name]
        cards = _load_cards(spec)
        summary = summarize_set(cards, thin_threshold=thin_threshold)
        summary["label"] = spec.label
        summary["registry"] = spec.registry_path
        report["sets"][name] = summary
        if name == "modern_mtg":
            benchmark_score = summary["avg_score"]
    if benchmark_score:
        for name, summary in report["sets"].items():
            summary["benchmark_ratio"] = round(summary["avg_score"] / benchmark_score, 3)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sets",
        nargs="+",
        default=["mtg_pkh", "hearthstone_custom", "pokemon_brv", "ygo_bk"],
        choices=sorted(SETS),
        help="Set keys to report. modern_mtg is included as a benchmark automatically.",
    )
    parser.add_argument("--thin-threshold", type=int, default=28)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = build_report(args.sets, args.thin_threshold)
    payload = json.dumps(report, indent=None if args.compact else 2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
