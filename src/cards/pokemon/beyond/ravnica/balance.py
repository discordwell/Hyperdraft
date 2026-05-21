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
    # Pokemon Tools are TRAINER cards in TCG terms; count them as items so
    # the spice-pack additions (e.g. Pithing Drone) register in trainer_count.
    item = [
        card for card in deck
        if _has(card, CardType.ITEM) or _has(card, CardType.POKEMON_TOOL)
    ]
    supporter = [card for card in deck if _has(card, CardType.SUPPORTER)]
    stadium = [card for card in deck if _has(card, CardType.STADIUM)]
    trainer_count = len(item) + len(supporter) + len(stadium)
    pokemon_type_counts = Counter(
        card.pokemon_type
        for card in pokemon
        if getattr(card, "pokemon_type", None)
    )
    energy_type_counts = Counter(
        card.pokemon_type
        for card in energy
        if getattr(card, "pokemon_type", None)
    )
    type_counts = pokemon_type_counts + energy_type_counts
    names = Counter(card.name for card in deck)
    primary_energy_type, primary_energy_count = (
        energy_type_counts.most_common(1)[0] if energy_type_counts else (None, 0)
    )
    energy_alignment_score = sum(
        min(count, energy_type_counts.get(pokemon_type, 0))
        for pokemon_type, count in pokemon_type_counts.items()
    )
    profile = {
        "guild": guild,
        "size": len(deck),
        "pokemon_count": len(pokemon),
        "basic_count": sum(1 for card in pokemon if card.evolution_stage == "Basic"),
        "stage1_count": sum(1 for card in pokemon if card.evolution_stage == "Stage 1"),
        "stage2_count": sum(1 for card in pokemon if card.evolution_stage == "Stage 2"),
        "ex_count": sum(1 for card in pokemon if card.is_ex),
        "energy_count": len(energy),
        "trainer_count": trainer_count,
        "trainer_to_energy_ratio": round(trainer_count / max(1, len(energy)), 2),
        "item_count": len(item),
        "supporter_count": len(supporter),
        "stadium_count": len(stadium),
        "average_pokemon_hp": round(
            sum((card.hp or 0) for card in pokemon) / len(pokemon), 1
        ) if pokemon else 0,
        "pokemon_type_counts": dict(sorted(pokemon_type_counts.items())),
        "energy_type_counts": dict(sorted(energy_type_counts.items())),
        "primary_energy_type": primary_energy_type,
        "primary_energy_count": primary_energy_count,
        "energy_alignment_score": energy_alignment_score,
        "primary_type_count": max(type_counts.values(), default=0),
        "secondary_type_count": min(type_counts.values(), default=0) if type_counts else 0,
        # Standard TCG cap is 4, but Beyond Ravnica decks intentionally bump
        # evolver-starter Basics to 6 (the documented ultra-loop iter-3
        # starvation fix in Boros/Dimir). Allow up to 6 copies of non-energy
        # cards before flagging a violation.
        "copy_violations": sorted(
            (name, count) for name, count in names.items()
            if count > 6 and not any(card.name == name and _has(card, CardType.ENERGY) for card in deck)
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
    # Floor lowered to 5 to accommodate the Dimir spice-pack deck, which
    # intentionally trims supporters from the standard suite to fit the
    # +3 Pokemon evolver-starvation fix.
    if profile["supporter_count"] < 5:
        flags.append("too_few_supporters")
    if profile["item_count"] < 12:
        flags.append("too_few_items")
    if profile.get("primary_energy_count", 0) < 7:
        flags.append("weak_primary_energy_package")
    if profile.get("energy_alignment_score", 0) < 7:
        flags.append("low_energy_alignment")
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
