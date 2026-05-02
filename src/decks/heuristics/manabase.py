"""
Mana base picker for the heuristic deckbuilder.

Given the deck colors and a target land count, return a list of
``DeckEntry`` objects covering basics + (when available) typed dual
lands from the resolved pool.

Strategy:
- mono-color: ``land_count`` of the matching basic
- 2-color:    ~8 typed duals (subtype filter), remainder split as basics
- 3+ color:   degrade gracefully — pick whatever multi-typed lands
              exist, fill the rest with basics weighted by deck color count

No new schema. The returned ``DeckEntry`` list is meant to be appended
directly to ``Deck.mainboard``.
"""

from __future__ import annotations

import random
from typing import Optional

from src.decks.deck import DeckEntry
from src.engine.types import CardType


# Single-letter color code -> basic land subtype name.
_BASIC_FOR_COLOR: dict[str, str] = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}
_BASIC_SUBTYPES: set[str] = set(_BASIC_FOR_COLOR.values())


def _is_land(card_def) -> bool:
    chars = getattr(card_def, "characteristics", None)
    if chars is None:
        return False
    types = getattr(chars, "types", set()) or set()
    return CardType.LAND in types


def _land_subtypes(card_def) -> set[str]:
    chars = getattr(card_def, "characteristics", None)
    if chars is None:
        return set()
    return set(chars.subtypes or set())


def _normalize_colors(colors: list[str]) -> list[str]:
    """Uppercase, dedupe (preserve order), keep only valid color codes."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in colors:
        if not raw:
            continue
        c = raw.upper()
        if c not in _BASIC_FOR_COLOR:
            continue
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _basics_in_pool(pool: dict) -> dict[str, str]:
    """
    Map color code -> exact card name of the basic land in the pool.

    Falls back to the canonical basic name ("Plains", etc.) when the
    pool itself doesn't contain that basic — many small custom sets
    don't ship basics, but tournament loaders and the validator both
    treat ``"Plains"`` etc. as valid card names.
    """
    out: dict[str, str] = {}
    for color, subtype in _BASIC_FOR_COLOR.items():
        # Prefer the exact-name basic if the pool has it.
        cd = pool.get(subtype)
        if cd is not None and _is_land(cd) and subtype in _land_subtypes(cd):
            out[color] = subtype
            continue
        # Otherwise scan for any land that has the matching subtype.
        for name, candidate in pool.items():
            if not _is_land(candidate):
                continue
            if subtype in _land_subtypes(candidate):
                out[color] = name
                break
        else:
            # No matching basic in pool — use the canonical name.
            # The deck loader is permissive and the validator treats
            # these as auto-pass for the 4-copy rule.
            out[color] = subtype
    return out


def _typed_duals_for_pair(pool: dict, color_a: str, color_b: str) -> list:
    """
    Find non-basic lands that have BOTH basic-land-types for the pair.

    Returns the CardDefinitions, sorted by name for determinism.
    """
    sub_a = _BASIC_FOR_COLOR[color_a]
    sub_b = _BASIC_FOR_COLOR[color_b]
    duals: list = []
    for name, cd in pool.items():
        if not _is_land(cd):
            continue
        subs = _land_subtypes(cd)
        if sub_a in subs and sub_b in subs and name not in _BASIC_SUBTYPES:
            duals.append(cd)
    duals.sort(key=lambda c: c.name)
    return duals


def _multi_color_lands(pool: dict, colors: list[str]) -> list:
    """
    Find non-basic lands that mention any TWO of the deck's colors via
    basic-land subtypes. Used as a graceful fallback for 3+ color decks.
    """
    if len(colors) < 2:
        return []
    relevant_subs = {_BASIC_FOR_COLOR[c] for c in colors}
    out: list = []
    for name, cd in pool.items():
        if not _is_land(cd) or name in _BASIC_SUBTYPES:
            continue
        subs = _land_subtypes(cd) & relevant_subs
        if len(subs) >= 2:
            out.append(cd)
    out.sort(key=lambda c: c.name)
    return out


def _accumulate(entries: list[DeckEntry], name: str, qty: int = 1) -> None:
    """Add quantity for ``name`` to ``entries`` (merge if already present)."""
    if qty <= 0:
        return
    for entry in entries:
        if entry.card_name == name:
            entry.quantity += qty
            return
    entries.append(DeckEntry(card_name=name, quantity=qty))


def _split_basics(
    colors: list[str],
    basic_total: int,
    basics_by_color: dict[str, str],
    pip_weights: Optional[dict[str, int]] = None,
) -> dict[str, int]:
    """
    Distribute ``basic_total`` basics across the deck colors.

    With ``pip_weights`` (count of each color pip in the deck's nonland
    portion), distribute proportionally; otherwise split evenly.
    """
    if not colors:
        return {}

    if pip_weights and any(pip_weights.get(c, 0) > 0 for c in colors):
        weights = {c: max(0, pip_weights.get(c, 0)) for c in colors}
        total_w = sum(weights.values()) or 1
        per = {c: (basic_total * w) // total_w for c, w in weights.items()}
    else:
        # Even split with remainder going to first color(s).
        base = basic_total // len(colors)
        per = {c: base for c in colors}

    # Round up: assign any leftover one-by-one to ensure we hit basic_total.
    leftover = basic_total - sum(per.values())
    i = 0
    while leftover > 0 and colors:
        per[colors[i % len(colors)]] += 1
        leftover -= 1
        i += 1

    return per


def pick_lands(
    colors: list[str],
    land_count: int,
    pool: dict,
    *,
    pip_weights: Optional[dict[str, int]] = None,
    seed: Optional[int] = None,
) -> list[DeckEntry]:
    """
    Pick a mana base of ``land_count`` lands for the given colors.

    Args:
        colors: Single-letter color codes (e.g. ``["W", "U"]``). Order is
            preserved for tiebreaking.
        land_count: Total lands to return (sum of all entry quantities).
        pool: Resolved card pool keyed by card name.
        pip_weights: Optional dict of color -> pip count in the nonland
            portion of the deck. Used to weight basics for 3+ color decks.
        seed: Optional deterministic-tiebreaker seed. Default ``None``
            falls back to the implicit alphabetic ordering from sort.

    Returns:
        List of ``DeckEntry`` whose quantities sum to ``land_count``.
    """
    rng = random.Random(seed) if seed is not None else None  # noqa: F841

    norm_colors = _normalize_colors(colors)
    if not norm_colors or land_count <= 0:
        return []

    basics_by_color = _basics_in_pool(pool)
    entries: list[DeckEntry] = []

    if len(norm_colors) == 1:
        # Mono-color: 100% basics of that color.
        color = norm_colors[0]
        _accumulate(entries, basics_by_color[color], land_count)
        return entries

    if len(norm_colors) == 2:
        ca, cb = norm_colors[0], norm_colors[1]
        duals = _typed_duals_for_pair(pool, ca, cb)
        # Aim for roughly 1/3 of lands as duals, capped at 8 and at duals * 4.
        target_duals = min(8, land_count // 3) if duals else 0
        # 4-copy max per non-basic card.
        added_duals = 0
        for cd in duals:
            if added_duals >= target_duals:
                break
            take = min(4, target_duals - added_duals)
            _accumulate(entries, cd.name, take)
            added_duals += take

        remaining = land_count - added_duals
        per_color = _split_basics(norm_colors, remaining, basics_by_color, pip_weights)
        for color in norm_colors:
            qty = per_color.get(color, 0)
            if qty > 0:
                _accumulate(entries, basics_by_color[color], qty)
        return entries

    # 3+ color: graceful degrade.
    multi_lands = _multi_color_lands(pool, norm_colors)
    target_multi = min(len(multi_lands) * 4, max(0, land_count - len(norm_colors) * 4))
    added_multi = 0
    for cd in multi_lands:
        if added_multi >= target_multi:
            break
        take = min(4, target_multi - added_multi)
        _accumulate(entries, cd.name, take)
        added_multi += take

    remaining = land_count - added_multi
    per_color = _split_basics(norm_colors, remaining, basics_by_color, pip_weights)
    for color in norm_colors:
        qty = per_color.get(color, 0)
        if qty > 0:
            _accumulate(entries, basics_by_color[color], qty)

    # Final guard: ensure exactly land_count total. Pad with primary basic
    # if rounding lost a card.
    total = sum(e.quantity for e in entries)
    if total < land_count and norm_colors:
        _accumulate(entries, basics_by_color[norm_colors[0]], land_count - total)
    elif total > land_count:
        # Trim from the last entries first.
        excess = total - land_count
        for entry in reversed(entries):
            if excess <= 0:
                break
            cut = min(entry.quantity, excess)
            entry.quantity -= cut
            excess -= cut
        entries = [e for e in entries if e.quantity > 0]

    return entries


__all__ = ["pick_lands"]
