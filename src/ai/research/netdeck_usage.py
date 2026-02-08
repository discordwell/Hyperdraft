"""
Netdeck Usage Stats

Build lightweight usage stats from the local netdeck corpus.
This is derived from decklists we already downloaded (MTGGoldfish).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CardUsage:
    decks: int = 0
    copies: int = 0
    archetype_counts: dict[str, int] = None

    def __post_init__(self) -> None:
        if self.archetype_counts is None:
            self.archetype_counts = {}

    @property
    def avg_copies_per_deck(self) -> float:
        if self.decks <= 0:
            return 0.0
        return self.copies / self.decks


def build_netdeck_usage() -> tuple[dict[str, CardUsage], int]:
    """
    Compute per-card usage from the NETDECKS registry.

    Returns (usage_map, total_decks).
    """
    from src.decks import NETDECKS

    usage: dict[str, CardUsage] = {}
    total_decks = 0

    for _deck_id, deck in NETDECKS.items():
        total_decks += 1
        seen_in_deck: set[str] = set()

        entries = list(deck.mainboard) + list(deck.sideboard)
        for entry in entries:
            name = entry.card_name
            qty = int(entry.quantity or 0)
            if not name or qty <= 0:
                continue

            u = usage.get(name)
            if not u:
                u = CardUsage()
                usage[name] = u

            u.copies += qty
            if name not in seen_in_deck:
                u.decks += 1
                seen_in_deck.add(name)

            arch = (deck.archetype or "").strip() or "Unknown"
            u.archetype_counts[arch] = u.archetype_counts.get(arch, 0) + 1

    return usage, total_decks


def format_usage_context(
    card_name: str,
    usage_map: dict[str, CardUsage],
    total_decks: int,
    max_archetypes: int = 3,
) -> Optional[str]:
    """
    Format a short usage blurb suitable for LLM prompts.
    """
    u = usage_map.get(card_name)
    if not u or u.decks <= 0 or total_decks <= 0:
        return None

    pct = (100.0 * u.decks) / total_decks
    archetypes = sorted(u.archetype_counts.items(), key=lambda kv: kv[1], reverse=True)
    arch_str = ", ".join(f"{a}({n})" for a, n in archetypes[:max_archetypes])

    return (
        f"Netdeck usage: in {u.decks}/{total_decks} decks ({pct:.1f}%), "
        f"avg copies {u.avg_copies_per_deck:.2f}; archetypes: {arch_str}."
    )

