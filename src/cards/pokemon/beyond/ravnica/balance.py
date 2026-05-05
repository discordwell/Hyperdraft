"""Static balance profiles for Beyond Ravnica Pokemon guild decks."""

from __future__ import annotations

from collections import Counter

from src.engine.types import CardDefinition, CardType


def _has(card: CardDefinition, card_type: CardType) -> bool:
    return card_type in card.characteristics.types


def ravnica_guild_profile(guild: str, deck: list[CardDefinition]) -> dict:
    """Summarize balance-relevant deck shape for one guild."""
    pokemon = [card for card in deck if _has(card, CardType.POKEMON)]
    energy = [card for card in deck if _has(card, CardType.ENERGY)]
    item = [card for card in deck if _has(card, CardType.ITEM)]
    supporter = [card for card in deck if _has(card, CardType.SUPPORTER)]
    stadium = [card for card in deck if _has(card, CardType.STADIUM)]
    type_counts = Counter(
        card.pokemon_type
        for card in pokemon + energy
        if getattr(card, "pokemon_type", None)
    )
    names = Counter(card.name for card in deck)
    profile = {
        "guild": guild,
        "size": len(deck),
        "pokemon_count": len(pokemon),
        "basic_count": sum(1 for card in pokemon if card.evolution_stage == "Basic"),
        "stage1_count": sum(1 for card in pokemon if card.evolution_stage == "Stage 1"),
        "stage2_count": sum(1 for card in pokemon if card.evolution_stage == "Stage 2"),
        "ex_count": sum(1 for card in pokemon if card.is_ex),
        "energy_count": len(energy),
        "item_count": len(item),
        "supporter_count": len(supporter),
        "stadium_count": len(stadium),
        "average_pokemon_hp": round(
            sum((card.hp or 0) for card in pokemon) / len(pokemon), 1
        ) if pokemon else 0,
        "primary_type_count": max(type_counts.values(), default=0),
        "secondary_type_count": min(type_counts.values(), default=0) if type_counts else 0,
        "copy_violations": sorted(
            (name, count) for name, count in names.items()
            if count > 4 and not any(card.name == name and _has(card, CardType.ENERGY) for card in deck)
        ),
    }
    profile["consistency_score"] = (
        profile["basic_count"] * 3
        + profile["item_count"]
        + profile["supporter_count"]
        - profile["stage2_count"] * 2
    )
    profile["pressure_score"] = (
        profile["ex_count"] * 10
        + profile["stage2_count"] * 8
        + int(profile["average_pokemon_hp"] / 20)
    )
    profile["balance_flags"] = ravnica_balance_flags(guild, profile)
    return profile


def ravnica_balance_flags(guild: str, profile: dict) -> list[str]:
    """Return static balance flags for a Beyond Ravnica guild deck profile."""
    flags = []
    if profile["size"] != 60:
        flags.append("invalid_deck_size")
    if profile["copy_violations"]:
        flags.append("copy_limit_violation")
    if profile["pokemon_count"] < 14:
        flags.append("too_few_pokemon")
    if profile["basic_count"] < 8:
        flags.append("too_few_basics")
    if not 10 <= profile["energy_count"] <= 18:
        flags.append("energy_count_out_of_range")
    if profile["supporter_count"] < 8:
        flags.append("too_few_supporters")
    if profile["item_count"] < 12:
        flags.append("too_few_items")
    if profile["consistency_score"] < 45:
        flags.append("low_consistency_score")
    if profile["pressure_score"] < 40:
        flags.append("low_pressure_score")
    if profile["stadium_count"] > 3:
        flags.append("too_many_stadiums")
    return flags


def ravnica_balance_summary() -> dict[str, dict]:
    """Return balance profiles for every Beyond Ravnica guild deck."""
    from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS

    return {
        guild: ravnica_guild_profile(guild, builder())
        for guild, builder in GUILD_DECK_BUILDERS.items()
    }
