"""Validated Pokemon deckbuilder entrypoints."""

from __future__ import annotations

from copy import copy

from src.cards.pokemon.deck_quality import analyze_pokemon_deck_quality


SV_STARTER_DECK_BUILDERS = {
    "fire": ("starter", "Fire starter", "src.cards.pokemon.sv_starter", "make_fire_deck"),
    "water": ("starter", "Water starter", "src.cards.pokemon.sv_starter", "make_water_deck"),
}


def list_sv_starter_decks() -> list[str]:
    """Return available Scarlet/Violet starter deck names."""
    return sorted(SV_STARTER_DECK_BUILDERS)


def build_sv_starter_deck(name: str, *, enforce_quality: bool = True) -> tuple[list, dict]:
    """Return a validated Scarlet/Violet starter deck as (deck, strategy)."""
    try:
        role, label, module_name, builder_name = SV_STARTER_DECK_BUILDERS[name]
    except KeyError as exc:
        available = ", ".join(list_sv_starter_decks())
        raise ValueError(f"Unknown Pokemon starter deck '{name}'. Available: {available}") from exc

    module = __import__(module_name, fromlist=[builder_name])
    builder = getattr(module, builder_name)
    deck = [copy(card) for card in builder()]
    strategy = {
        "name": label,
        "role": role,
        "deck": name,
    }
    if enforce_quality:
        summary = analyze_pokemon_deck_quality(deck, role=role)
        flags = summary["quality_flags"] + summary["role_quality_flags"]
        if flags:
            raise ValueError(f"Pokemon starter deck '{name}' failed quality checks: {flags}")
    return deck, strategy
