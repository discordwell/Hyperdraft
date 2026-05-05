"""
Heuristic deckbuilder — the slot-filling assembler.

This is the main entry point for the W2 worktree's contribution. The
algorithm:

1. Resolve the card pool from the requested set codes.
2. Score every nonland card via ``score_card``. Drop cards that are
   uncastable in the deck colors (``+inf``).
3. Bucket scored cards by CMC (1, 2, 3, 4, 5, 6+) and by role tag.
4. Greedily slot-fill each CMC bucket from the archetype's curve target,
   capped at 4 copies per non-basic card name. Promote role-tagged
   cards if the role targets aren't met by curve fill alone.
5. Multiples follow the 4-3-2-1 distribution to avoid jamming a deck
   full of singletons (configurable).
6. Pick a mana base via ``pick_lands``.
7. Assemble a ``Deck`` and run it through ``validate_deck`` before
   returning. Validation failures raise ``ValueError``.

Determinism: ``seed`` controls only tiebreakers in the slot filler. With
``seed=None`` the behaviour is still deterministic because card sort keys
are stable (score, name) and the stub scorer returns 1.0 for all
castable cards (so order falls back to alphabetical-by-name).
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from typing import Iterable, Optional

from src.decks.deck import Deck, DeckEntry, validate_deck
from src.engine.types import CardType

from .archetypes import ArchetypeTemplate, get_template
from .manabase import pick_lands
from .pool import resolve_pool
from .scorer import role_of, score_card


# =============================================================================
# Helpers
# =============================================================================


_BASIC_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest"}


def _is_land(card_def) -> bool:
    chars = getattr(card_def, "characteristics", None)
    if chars is None:
        return False
    return CardType.LAND in (chars.types or set())


def _cmc(card_def) -> int:
    """Compute CMC of a card from its mana cost string."""
    chars = getattr(card_def, "characteristics", None)
    cost = getattr(chars, "mana_cost", None) if chars is not None else None
    if not cost:
        return 0
    total = 0
    for raw in re.findall(r"\{([^}]+)\}", cost):
        symbol = raw.upper().strip()
        if symbol == "X":
            continue  # X counts as 0 in pre-cast CMC
        if symbol.isdigit():
            total += int(symbol)
            continue
        if symbol in {"W", "U", "B", "R", "G", "C", "S"}:
            total += 1
            continue
        if "/" in symbol:
            # Hybrid / phyrexian: each pip is worth 1.
            total += 1
            continue
        # Unknown symbol — treat as 1 for safety.
        total += 1
    return total


def _bucket(cmc: int) -> int:
    """Map a card's CMC to its curve bucket key (1-5 or 6 for 6+)."""
    if cmc <= 1:
        return 1
    if cmc >= 6:
        return 6
    return cmc


def _classify_role(card_def) -> Optional[str]:
    """
    Return the scorer's role tag for slot-filling.

    Keeping role buckets aligned with scorer.py avoids the builder promoting
    cards using a weaker or contradictory strategic vocabulary.
    """
    if _is_land(card_def):
        return None
    return role_of(card_def)


def _color_pip_count(card_def, colors: Iterable[str]) -> dict[str, int]:
    """Count colored pips per color in a card's mana cost."""
    counts: dict[str, int] = {c.upper(): 0 for c in colors if c}
    chars = getattr(card_def, "characteristics", None)
    cost = getattr(chars, "mana_cost", None) if chars is not None else None
    if not cost:
        return counts
    for raw in re.findall(r"\{([^}]+)\}", cost):
        symbol = raw.upper().strip()
        if symbol in counts:
            counts[symbol] += 1
        # Hybrid {W/U}: count toward whichever color is in the deck.
        if "/" in symbol:
            for half in symbol.split("/"):
                if half in counts:
                    counts[half] += 1
                    break
    return counts


# =============================================================================
# Slot filler
# =============================================================================


def _multiples_for_index(index: int) -> int:
    """
    4-3-2-1 distribution for top-N cards.

    Card 0 -> 4 copies, card 1 -> 3, card 2 -> 2, card 3+ -> 1.
    """
    table = [4, 3, 2, 1]
    if index < len(table):
        return table[index]
    return 1


def _curve_total(template: ArchetypeTemplate) -> int:
    return sum(template.curve_targets.values())


def _build_buckets(
    pool: dict,
    archetype: str,
    colors: list[str],
) -> tuple[dict[int, list[tuple[float, str, object]]], dict[str, list[tuple[float, str, object]]]]:
    """
    Score every nonland card and bucket by CMC and role.

    Returns (curve_buckets, role_buckets). Each bucket value is a sorted
    list of (score, name, card_def) — lowest score first.
    """
    curve_buckets: dict[int, list[tuple[float, str, object]]] = defaultdict(list)
    role_buckets: dict[str, list[tuple[float, str, object]]] = defaultdict(list)

    for name, card_def in pool.items():
        if _is_land(card_def):
            continue
        score = score_card(card_def, archetype, colors)
        if score == math.inf or (isinstance(score, float) and math.isinf(score)):
            continue
        bucket = _bucket(_cmc(card_def))
        curve_buckets[bucket].append((score, name, card_def))
        role = _classify_role(card_def)
        if role:
            role_buckets[role].append((score, name, card_def))

    # Sort each bucket: lowest score first, then alphabetical for stability.
    for bucket in curve_buckets.values():
        bucket.sort(key=lambda t: (t[0], t[1]))
    for bucket in role_buckets.values():
        bucket.sort(key=lambda t: (t[0], t[1]))

    return curve_buckets, role_buckets


def _slot_fill(
    template: ArchetypeTemplate,
    curve_buckets: dict[int, list[tuple[float, str, object]]],
    role_buckets: dict[str, list[tuple[float, str, object]]],
    *,
    rng: Optional[random.Random] = None,
) -> tuple[list[DeckEntry], list]:
    """
    Greedy slot-fill respecting curve targets, role targets, 4-copy max.

    Returns (entries, picked_card_defs). picked_card_defs is the parallel
    list of CardDefinition objects (one per copy) — used by the manabase
    picker for pip-weight computation.
    """
    chosen: list[DeckEntry] = []
    chosen_defs: list = []
    name_to_def: dict[str, object] = {}
    name_counts: Counter = Counter()
    role_counts: Counter = Counter()

    def _has_room(name: str) -> bool:
        return name_counts[name] < 4

    def _take(name: str, card_def, qty: int) -> int:
        """Add up to ``qty`` copies of ``name``, capped at the 4-copy max."""
        if qty <= 0:
            return 0
        room = 4 - name_counts[name]
        take = min(qty, room)
        if take <= 0:
            return 0
        # Merge into existing entry or append new.
        for entry in chosen:
            if entry.card_name == name:
                entry.quantity += take
                break
        else:
            chosen.append(DeckEntry(card_name=name, quantity=take))
        name_to_def[name] = card_def
        name_counts[name] += take
        for _ in range(take):
            chosen_defs.append(card_def)
            role = _classify_role(card_def)
            if role:
                role_counts[role] += 1
        return take

    def _free_slot_for_role(required_role: str, replacement_card_def) -> bool:
        """
        Remove one replaceable copy so role promotion can improve deck shape
        without being trimmed back off after the mana-base pass.
        """
        replacement_bucket = _bucket(_cmc(replacement_card_def))

        def can_replace(entry: DeckEntry, require_same_bucket: bool) -> bool:
            card_def = name_to_def.get(entry.card_name)
            if not card_def:
                return False
            if require_same_bucket and _bucket(_cmc(card_def)) != replacement_bucket:
                return False
            role = _classify_role(card_def)
            if role == required_role:
                return False
            target = (template.role_targets or {}).get(role or "", 0)
            return not role or role_counts.get(role, 0) > target

        for require_same_bucket in (True, False):
            for entry in reversed(chosen):
                if not can_replace(entry, require_same_bucket):
                    continue
                card_def = name_to_def.get(entry.card_name)
                role = _classify_role(card_def) if card_def else None
                entry.quantity -= 1
                name_counts[entry.card_name] -= 1
                if role:
                    role_counts[role] -= 1
                if card_def in chosen_defs:
                    chosen_defs.remove(card_def)
                if entry.quantity <= 0:
                    chosen.remove(entry)
                return True
        return False

    # ------------------------------------------------------------------
    # Pass 1: fill curve buckets with 4-3-2-1 multiples.
    # ------------------------------------------------------------------
    for bucket_key, target in template.curve_targets.items():
        if target <= 0:
            continue
        candidates = list(curve_buckets.get(bucket_key, []))
        filled_in_bucket = 0
        idx = 0
        for slot_index, (score, name, card_def) in enumerate(candidates):
            if filled_in_bucket >= target:
                break
            if not _has_room(name):
                continue
            qty = _multiples_for_index(slot_index)
            qty = min(qty, target - filled_in_bucket)
            actual = _take(name, card_def, qty)
            filled_in_bucket += actual
            idx += 1

    # ------------------------------------------------------------------
    # Pass 2: meet role targets by promoting role-tagged cards.
    # ------------------------------------------------------------------
    for role, target in (template.role_targets or {}).items():
        deficit = max(0, target - role_counts.get(role, 0))
        if deficit <= 0:
            continue
        for slot_index, (score, name, card_def) in enumerate(role_buckets.get(role, [])):
            if deficit <= 0:
                break
            if not _has_room(name):
                continue
            while deficit > 0 and _has_room(name):
                if sum(e.quantity for e in chosen) >= _curve_total(template):
                    if not _free_slot_for_role(role, card_def):
                        break
                if sum(e.quantity for e in chosen) >= _curve_total(template):
                    break
                actual = _take(name, card_def, 1)
                if actual <= 0:
                    break
                deficit -= actual

    # ------------------------------------------------------------------
    # Pass 3: pad up to curve total if anything fell short (ramps that
    # didn't fill, missing CMC buckets, etc.). Walk all remaining
    # candidates in score order until we hit the curve total or run out.
    # ------------------------------------------------------------------
    target_nonland = _curve_total(template)
    # Build a flat list of all candidates not yet at 4-copy max.
    remaining: list[tuple[float, str, object]] = []
    seen: set[str] = set()
    for bucket in curve_buckets.values():
        for triple in bucket:
            if triple[1] in seen:
                continue
            seen.add(triple[1])
            remaining.append(triple)
    remaining.sort(key=lambda t: (t[0], t[1]))

    for score, name, card_def in remaining:
        current = sum(e.quantity for e in chosen)
        if current >= target_nonland:
            break
        if not _has_room(name):
            continue
        # Take 1 at a time in this pad pass to keep variety.
        _take(name, card_def, 1)

    return chosen, chosen_defs


# =============================================================================
# Public entry point
# =============================================================================


def build_heuristic_deck(
    name: str,
    archetype: str,
    colors: list[str],
    set_codes: list[str],
    *,
    seed: Optional[int] = None,
) -> Deck:
    """
    Assemble a 60-card constructed deck using deterministic heuristics.

    Args:
        name: Display name for the deck.
        archetype: One of ``Aggro``, ``Midrange``, ``Control``, ``Tempo``, ``Ramp``.
        colors: List of single-letter color codes (``["W", "U"]``).
        set_codes: Set codes whose cards form the legal pool. Mixes MTG and
            custom freely (``["FDN", "TMH"]``).
        seed: Optional deterministic-tiebreak seed. Default ``None`` is
            still deterministic via stable sort keys.

    Returns:
        A fully-typed ``Deck`` whose mainboard sums to 60 and passes
        ``validate_deck``.

    Raises:
        ValueError: if ``validate_deck`` reports any error.
        KeyError: if ``archetype`` is not a known template.
    """
    template = get_template(archetype)
    pool = resolve_pool(set_codes)
    rng = random.Random(seed) if seed is not None else None

    # Bucket and slot-fill.
    curve_buckets, role_buckets = _build_buckets(pool, template.name, colors)
    nonland_entries, nonland_defs = _slot_fill(template, curve_buckets, role_buckets, rng=rng)

    # Compute pip weights from the picked nonland portion to weight basics.
    pip_weights: Counter = Counter()
    for cd in nonland_defs:
        for color, count in _color_pip_count(cd, colors).items():
            pip_weights[color] += count

    # Mana base.
    target_nonland = template.mainboard_size - template.land_count
    nonland_total = sum(e.quantity for e in nonland_entries)

    # If we couldn't fill enough nonlands from the pool, top up the land
    # count to maintain the mainboard size.
    actual_land_count = template.mainboard_size - nonland_total
    actual_land_count = max(template.land_count, actual_land_count)

    land_entries = pick_lands(
        colors=colors,
        land_count=actual_land_count,
        pool=pool,
        pip_weights=dict(pip_weights),
        seed=seed,
    )

    # If we still overshot or undershot the mainboard target, trim/pad.
    main_total = sum(e.quantity for e in nonland_entries) + sum(
        e.quantity for e in land_entries
    )
    if main_total > template.mainboard_size:
        # Trim from the bottom of the nonland list (lowest-scored first).
        excess = main_total - template.mainboard_size
        for entry in reversed(nonland_entries):
            if excess <= 0:
                break
            cut = min(entry.quantity, excess)
            entry.quantity -= cut
            excess -= cut
        nonland_entries = [e for e in nonland_entries if e.quantity > 0]
    elif main_total < template.mainboard_size and land_entries:
        # Pad extra basic of the first color.
        deficit = template.mainboard_size - main_total
        primary_basic_name = land_entries[0].card_name
        # Try to merge into existing entry.
        for entry in land_entries:
            if entry.card_name == primary_basic_name:
                entry.quantity += deficit
                break
        else:
            land_entries.append(DeckEntry(primary_basic_name, deficit))

    mainboard = list(nonland_entries) + list(land_entries)

    deck = Deck(
        name=name,
        archetype=template.name,
        colors=list(colors),
        description=f"Hybrid heuristic, sets={','.join(set_codes)}",
        mainboard=mainboard,
        sideboard=[],
    )

    is_valid, errors = validate_deck(deck)
    if not is_valid:
        raise ValueError(
            f"Heuristic deckbuilder produced invalid deck for "
            f"archetype={archetype} colors={colors} sets={set_codes}: {errors}"
        )

    return deck


__all__ = ["build_heuristic_deck"]
