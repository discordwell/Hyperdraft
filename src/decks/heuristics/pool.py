# STUB-W2: replaced at integration by W1
"""
Card pool resolver for the heuristic deckbuilder.

``resolve_pool(set_codes)`` returns the union of all cards from the given
sets as a ``{card_name: CardDefinition}`` dict. On name collisions across
MTG/custom registries, the set code listed earlier in ``set_codes`` wins.

This is intentionally tiny: it does not filter by color, type, or any
other property. Filtering belongs in the scorer / slot-filler.
"""

from __future__ import annotations

from src.cards.set_registry import SET_TO_CARDS
from src.engine.types import CardDefinition


def resolve_pool(set_codes: list[str]) -> dict[str, CardDefinition]:
    """
    Union the card registries for the given set codes.

    Args:
        set_codes: Ordered list of set codes (e.g. ``["FDN", "OTJ"]``).
            Set codes are upper-cased for lookup. Unknown codes are
            silently skipped — the caller is responsible for validating
            input. An empty list returns an empty dict.

    Returns:
        Dict mapping card name to ``CardDefinition``. On name collisions
        (e.g. a reprint that exists in both FDN and WOE), the set listed
        earlier in ``set_codes`` wins.
    """
    pool: dict[str, CardDefinition] = {}
    for code in set_codes:
        if not code:
            continue
        cards = SET_TO_CARDS.get(code.upper(), {})
        for name, card_def in cards.items():
            # Earlier wins: only add if not already present.
            if name not in pool:
                pool[name] = card_def
    return pool


__all__ = ["resolve_pool"]
