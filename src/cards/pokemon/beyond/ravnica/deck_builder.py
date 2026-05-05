"""Validated Beyond Ravnica Pokemon deckbuilder entrypoints."""

from __future__ import annotations

from copy import copy

from src.cards.pokemon.beyond.ravnica.balance import ravnica_guild_profile


def list_ravnica_guild_decks() -> list[str]:
    """Return available Beyond Ravnica guild deck names."""
    from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS

    return sorted(GUILD_DECK_BUILDERS)


def build_ravnica_guild_deck(guild: str, *, enforce_balance: bool = True) -> tuple[list, dict]:
    """Return a validated Beyond Ravnica guild deck as (deck, strategy)."""
    from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS

    try:
        builder = GUILD_DECK_BUILDERS[guild]
    except KeyError as exc:
        available = ", ".join(list_ravnica_guild_decks())
        raise ValueError(f"Unknown Beyond Ravnica guild '{guild}'. Available: {available}") from exc

    deck = [copy(card) for card in builder()]
    strategy = {
        "name": f"{guild.title()} guild",
        "role": "guild",
        "guild": guild,
    }
    if enforce_balance:
        profile = ravnica_guild_profile(guild, deck)
        if profile["balance_flags"]:
            raise ValueError(
                f"Beyond Ravnica guild '{guild}' failed balance checks: "
                f"{profile['balance_flags']}"
            )
    return deck, strategy
