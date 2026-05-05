"""Validated Yu-Gi-Oh! deckbuilder entrypoints."""

from __future__ import annotations

from copy import copy

from src.cards.yugioh.deck_quality import analyze_ygo_deck_quality
from src.cards.yugioh.ygo_optimized import YGO_OPTIMIZED_DECKS


def list_ygo_optimized_decks() -> list[str]:
    """Return available optimized Yu-Gi-Oh! deck names."""
    return sorted(YGO_OPTIMIZED_DECKS)


def build_ygo_optimized_deck(name: str, *, enforce_quality: bool = True) -> tuple[list, list, dict]:
    """Return a validated optimized Yu-Gi-Oh! deck as (main, extra, strategy)."""
    try:
        entry = YGO_OPTIMIZED_DECKS[name]
    except KeyError as exc:
        available = ", ".join(list_ygo_optimized_decks())
        raise ValueError(f"Unknown Yu-Gi-Oh! optimized deck '{name}'. Available: {available}") from exc

    main = [copy(card) for card in entry["deck"]]
    extra = [copy(card) for card in entry["extra"]]
    strategy = dict(entry["strategy"])
    if enforce_quality:
        summary = analyze_ygo_deck_quality(main, strategy)
        flags = summary["quality_flags"] + summary["role_quality_flags"]
        if flags:
            raise ValueError(f"Yu-Gi-Oh! optimized deck '{name}' failed quality checks: {flags}")
    return main, extra, strategy
