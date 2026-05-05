"""Quality metrics for heuristic deckbuilder outputs."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.decks.deck import Deck
from src.engine.types import CardType

from .archetypes import get_template
from .pool import resolve_pool
from .scorer import cmc_of, is_castable, role_of


_BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}


def _is_land(card_def: Any, card_name: str) -> bool:
    if card_name in _BASIC_LANDS:
        return True
    chars = getattr(card_def, "characteristics", None)
    return bool(chars and CardType.LAND in (chars.types or set()))


def _curve_bucket(card_def: Any) -> str:
    cmc = cmc_of(card_def)
    if cmc >= 6:
        return "6+"
    return str(max(cmc, 1))


def analyze_deck_quality(
    deck: Deck,
    *,
    set_codes: list[str] | None = None,
    pool: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Summarize deckbuilder output in stable, JSON-friendly metrics.

    The metrics intentionally avoid asserting that a deck is "good"; they
    expose curve, role, mana, and resolution signals so benchmark scripts can
    compare deltas across commits.
    """
    card_pool = pool if pool is not None else resolve_pool(set_codes or ["FDN"])
    curve_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    unresolved_cards: list[str] = []
    off_color_cards: list[str] = []
    land_count = 0
    nonland_count = 0
    textless_nonland_count = 0
    functional_nonland_count = 0

    for entry in deck.mainboard:
        card_def = card_pool.get(entry.card_name)
        if card_def is None:
            unresolved_cards.append(entry.card_name)
            continue

        if _is_land(card_def, entry.card_name):
            land_count += entry.quantity
            continue

        nonland_count += entry.quantity
        if not (getattr(card_def, "text", "") or "").strip():
            textless_nonland_count += entry.quantity
        if (
            (getattr(card_def, "text", "") or "").strip()
            or getattr(card_def, "setup_interceptors", None)
            or getattr(card_def, "resolve", None)
        ):
            functional_nonland_count += entry.quantity
        curve_counts[_curve_bucket(card_def)] += entry.quantity
        role_counts[role_of(card_def)] += entry.quantity
        if not is_castable(card_def, deck.colors):
            off_color_cards.append(entry.card_name)

    role_deficits: dict[str, int] = {}
    curve_error = 0
    role_fill_rate = 1.0
    try:
        template = get_template(deck.archetype)
        for bucket, target in template.curve_targets.items():
            key = "6+" if bucket >= 6 else str(bucket)
            curve_error += abs(curve_counts.get(key, 0) - target)
        role_targets = template.role_targets or {}
        if role_targets:
            filled = 0
            total = sum(role_targets.values())
            for role, target in role_targets.items():
                have = role_counts.get(role, 0)
                filled += min(have, target)
                if have < target:
                    role_deficits[role] = target - have
            role_fill_rate = round(filled / total, 3) if total else 1.0
    except KeyError:
        template = None

    mainboard_count = deck.mainboard_count
    flags: list[str] = []
    if unresolved_cards:
        flags.append("unresolved_cards")
    if off_color_cards:
        flags.append("off_color_cards")
    if mainboard_count != 60:
        flags.append("non_60_mainboard")
    if land_count < 20 or land_count > 28:
        flags.append("land_count_outside_default_band")
    if role_deficits:
        flags.append("role_deficits")

    return {
        "deck_name": deck.name,
        "archetype": deck.archetype,
        "colors": list(deck.colors),
        "mainboard_count": mainboard_count,
        "land_count": land_count,
        "nonland_count": nonland_count,
        "textless_nonland_count": textless_nonland_count,
        "functional_nonland_count": functional_nonland_count,
        "functional_nonland_ratio": round(functional_nonland_count / nonland_count, 3) if nonland_count else 0.0,
        "land_ratio": round(land_count / mainboard_count, 3) if mainboard_count else 0.0,
        "curve_counts": dict(sorted(curve_counts.items())),
        "curve_error": curve_error,
        "role_counts": dict(sorted(role_counts.items())),
        "role_deficits": role_deficits,
        "role_fill_rate": role_fill_rate,
        "unresolved_count": len(unresolved_cards),
        "off_color_count": len(set(off_color_cards)),
        "quality_flags": flags,
    }


__all__ = ["analyze_deck_quality"]
