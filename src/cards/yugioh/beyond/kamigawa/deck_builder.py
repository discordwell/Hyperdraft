"""Validated Beyond Kamigawa deckbuilder entrypoints."""

from __future__ import annotations

from copy import copy

from src.cards.yugioh.beyond.kamigawa.balance import kamigawa_deck_profile


def list_kamigawa_archetypes() -> list[str]:
    """Return available Beyond Kamigawa Yu-Gi-Oh! archetype names."""
    from src.cards.yugioh.beyond.kamigawa import ARCHETYPE_DECK_BUILDERS

    return sorted(ARCHETYPE_DECK_BUILDERS)


def build_kamigawa_deck(archetype: str, *, enforce_balance: bool = True) -> tuple[list, list]:
    """Return a validated Beyond Kamigawa archetype deck as (main, extra)."""
    from src.cards.yugioh.beyond.kamigawa import ARCHETYPE_DECK_BUILDERS

    try:
        builder = ARCHETYPE_DECK_BUILDERS[archetype]
    except KeyError as exc:
        available = ", ".join(list_kamigawa_archetypes())
        raise ValueError(f"Unknown Beyond Kamigawa archetype '{archetype}'. Available: {available}") from exc

    main, extra = builder()
    main = [copy(card) for card in main]
    extra = [copy(card) for card in extra]
    if enforce_balance:
        profile = kamigawa_deck_profile(archetype, main, extra)
        if profile["balance_flags"]:
            raise ValueError(
                f"Beyond Kamigawa archetype '{archetype}' failed balance checks: "
                f"{profile['balance_flags']}"
            )
    return main, extra
