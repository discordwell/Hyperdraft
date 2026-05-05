"""Pokemon deckbuilding quality metrics."""

from __future__ import annotations

from collections import Counter

from src.engine.types import CardDefinition, CardType


def _has(card: CardDefinition, card_type: CardType) -> bool:
    return card_type in card.characteristics.types


def _blob(card: CardDefinition) -> str:
    return f"{card.name} {card.text or ''}".lower()


def analyze_pokemon_deck_quality(deck: list[CardDefinition], role: str = "midrange") -> dict:
    """Return stable Pokemon deck quality metrics for a 60-card deck."""
    names = Counter(card.name for card in deck)
    pokemon = [card for card in deck if _has(card, CardType.POKEMON)]
    energy = [card for card in deck if _has(card, CardType.ENERGY)]
    trainers = [
        card for card in deck
        if _has(card, CardType.ITEM)
        or _has(card, CardType.SUPPORTER)
        or _has(card, CardType.STADIUM)
        or _has(card, CardType.POKEMON_TOOL)
    ]
    basics = [card for card in pokemon if card.evolution_stage == "Basic"]
    stage1 = [card for card in pokemon if card.evolution_stage == "Stage 1"]
    stage2 = [card for card in pokemon if card.evolution_stage == "Stage 2"]
    ex_pokemon = [card for card in pokemon if card.is_ex]
    supporter = [card for card in deck if _has(card, CardType.SUPPORTER)]
    items = [card for card in deck if _has(card, CardType.ITEM)]
    stadiums = [card for card in deck if _has(card, CardType.STADIUM)]
    tools = [card for card in deck if _has(card, CardType.POKEMON_TOOL)]
    energy_types = Counter(
        card.pokemon_type
        for card in energy
        if getattr(card, "pokemon_type", None)
    )
    primary_energy_type = energy_types.most_common(1)[0][0] if energy_types else None
    primary_energy_count = energy_types.get(primary_energy_type, 0) if primary_energy_type else 0

    base_names = {card.name for card in basics}
    stage1_targets = {card.evolves_from for card in stage1 if card.evolves_from}
    stage2_targets = {card.evolves_from for card in stage2 if card.evolves_from}

    search_terms = ("search your deck", "put it into your hand", "put it onto your bench")
    draw_terms = ("draw", "shuffles their hand", "shuffles your hand")
    switch_terms = ("switch", "retreat")
    heal_terms = ("heal", "remove", "damage counters")
    setup_item_names = {"Nest Ball", "Ultra Ball", "Rare Candy"}
    setup_item_count = sum(names.get(name, 0) for name in setup_item_names)
    draw_supporter_count = sum(
        1 for card in supporter if any(term in _blob(card) for term in draw_terms)
    )

    summary = {
        "size": len(deck),
        "role": role,
        "pokemon_count": len(pokemon),
        "energy_count": len(energy),
        "trainer_count": len(trainers),
        "basic_count": len(basics),
        "stage1_count": len(stage1),
        "stage2_count": len(stage2),
        "ex_count": len(ex_pokemon),
        "supporter_count": len(supporter),
        "item_count": len(items),
        "stadium_count": len(stadiums),
        "tool_count": len(tools),
        "energy_type_counts": dict(sorted(energy_types.items())),
        "primary_energy_type": primary_energy_type,
        "primary_energy_count": primary_energy_count,
        "off_type_energy_count": len(energy) - primary_energy_count,
        "draw_count": sum(1 for card in deck if any(term in _blob(card) for term in draw_terms)),
        "draw_supporter_count": draw_supporter_count,
        "search_count": sum(1 for card in deck if any(term in _blob(card) for term in search_terms)),
        "switch_count": sum(1 for card in deck if any(term in _blob(card) for term in switch_terms)),
        "heal_count": sum(1 for card in deck if any(term in _blob(card) for term in heal_terms)),
        "rare_candy_count": names.get("Rare Candy", 0),
        "setup_item_count": setup_item_count,
        "stage2_setup_ratio": (
            round(setup_item_count / len(stage2), 2) if stage2 else None
        ),
        "gust_count": names.get("Boss's Orders", 0),
        "copy_violations": sorted(
            (name, count) for name, count in names.items()
            if count > 4 and not any(card.name == name and _has(card, CardType.ENERGY) for card in deck)
        ),
        "stage1_without_basic": sorted(name for name in stage1_targets if name not in base_names),
        "stage2_without_stage1": sorted(name for name in stage2_targets if name not in names),
    }
    summary["quality_flags"] = pokemon_deck_quality_flags(summary)
    summary["role_quality_flags"] = pokemon_role_quality_flags(summary)
    return summary


def pokemon_deck_quality_flags(summary: dict) -> list[str]:
    """Generic Pokemon deck construction flags."""
    flags = []
    if summary["size"] != 60:
        flags.append("invalid_deck_size")
    if summary["copy_violations"]:
        flags.append("copy_limit_violation")
    if summary["pokemon_count"] < 12:
        flags.append("too_few_pokemon")
    if summary["basic_count"] < 8:
        flags.append("too_few_basics")
    if not 12 <= summary["energy_count"] <= 24:
        flags.append("energy_count_out_of_range")
    if summary["energy_count"] and summary["primary_energy_count"] < summary["energy_count"] * 0.75:
        flags.append("unstable_energy_mix")
    if summary["trainer_count"] < 16:
        flags.append("too_few_trainers")
    if summary["search_count"] < 4:
        flags.append("too_little_search")
    if summary["draw_count"] < 4:
        flags.append("too_little_draw")
    if summary["stage1_without_basic"] or summary["stage2_without_stage1"]:
        flags.append("broken_evolution_line")
    if summary["stage2_count"] and summary["rare_candy_count"] < 1:
        flags.append("stage2_without_candy")
    return flags


def pokemon_role_quality_flags(summary: dict) -> list[str]:
    """Role-specific flags for starter-style Pokemon decks."""
    flags = []
    role = summary["role"].lower()
    if role in {"starter", "midrange"}:
        if summary["basic_count"] < 8:
            flags.append("midrange_low_basic_density")
        if summary["stage2_count"] and summary["setup_item_count"] < 6:
            flags.append("midrange_low_setup_engine")
        if summary["draw_supporter_count"] < 4:
            flags.append("midrange_low_draw_supporters")
        if summary["gust_count"] < 1:
            flags.append("midrange_missing_gust")
        if summary["switch_count"] < 2:
            flags.append("midrange_missing_switch")
    return flags


def analyze_sv_starter_decks() -> dict[str, dict]:
    """Analyze the built-in Scarlet/Violet starter decks."""
    from src.cards.pokemon.sv_starter import make_fire_deck, make_water_deck

    return {
        "fire": analyze_pokemon_deck_quality(make_fire_deck(), role="starter"),
        "water": analyze_pokemon_deck_quality(make_water_deck(), role="starter"),
    }
