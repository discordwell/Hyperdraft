"""Static balance profiles for Beyond Kamigawa Yu-Gi-Oh! decks."""

from __future__ import annotations

from collections import Counter

from src.engine.types import CardDefinition, CardType


def _has_type(card: CardDefinition, card_type: CardType) -> bool:
    return card_type in card.characteristics.types


def _blob(card: CardDefinition) -> str:
    return f"{card.name} {card.text or ''}".lower()


def _count_terms(deck: list[CardDefinition], terms: tuple[str, ...]) -> int:
    return sum(1 for card in deck if any(term in _blob(card) for term in terms))


def kamigawa_deck_profile(name: str, main: list[CardDefinition], extra: list[CardDefinition]) -> dict:
    """Summarize the balance-relevant deck shape for one archetype."""
    monsters = [card for card in main if _has_type(card, CardType.YGO_MONSTER)]
    spells = [card for card in main if _has_type(card, CardType.YGO_SPELL)]
    traps = [card for card in main if _has_type(card, CardType.YGO_TRAP)]
    copies = Counter(card.name for card in main)
    atk_values = [getattr(card, "atk", 0) or 0 for card in monsters]
    profile = {
        "name": name,
        "size": len(main),
        "extra_size": len(extra),
        "monster_count": len(monsters),
        "spell_count": len(spells),
        "trap_count": len(traps),
        "field_spell_count": sum(
            1 for card in spells
            if getattr(card, "ygo_spell_type", "") == "Field"
        ),
        "low_level_monster_count": sum(1 for card in monsters if (getattr(card, "level", 0) or 0) <= 4),
        "tribute_monster_count": sum(1 for card in monsters if (getattr(card, "level", 0) or 0) >= 5),
        "pressure_monster_count": sum(1 for card in monsters if (getattr(card, "atk", 0) or 0) >= 1800),
        "boss_monster_count": sum(1 for card in monsters if (getattr(card, "atk", 0) or 0) >= 2400),
        "average_monster_atk": round(sum(atk_values) / len(atk_values), 1) if atk_values else 0,
        "removal_count": _count_terms(main, ("destroy", "banish", "return", "bounce", "doom blade", "wrath", "judgment", "bolt")),
        "draw_count": _count_terms(main, ("draw", "brainstorm", "ponder", "fact or fiction", "insight")),
        "burn_count": _count_terms(main, ("damage", "inflict", "lightning bolt")),
        "counter_count": _count_terms(main, ("negate", "counter")),
        "equip_identity_count": _count_terms(main, ("equip", "equipped", "plating", "embercleave", "boots", "sword")),
        "copy_violations": sorted((card, count) for card, count in copies.items() if count > 3),
    }
    profile["pressure_score"] = (
        profile["pressure_monster_count"] * 2
        + profile["boss_monster_count"] * 3
        + profile["burn_count"]
    )
    profile["control_score"] = (
        profile["removal_count"]
        + profile["counter_count"]
        + profile["draw_count"]
        + profile["trap_count"]
    )
    profile["curve_stability_score"] = (
        profile["low_level_monster_count"] * 2
        - profile["tribute_monster_count"]
    )
    profile["balance_flags"] = kamigawa_balance_flags(name, profile)
    return profile


def kamigawa_balance_flags(archetype: str, profile: dict) -> list[str]:
    """Return static balance flags for one Beyond Kamigawa deck profile."""
    flags = []
    if profile["size"] != 40:
        flags.append("invalid_main_size")
    if profile["extra_size"] > 15:
        flags.append("extra_deck_too_large")
    if profile["copy_violations"]:
        flags.append("copy_limit_violation")
    if profile.get("field_spell_count", 0) > 3:
        flags.append("too_many_field_spells")
    if profile["monster_count"] < 12:
        flags.append("too_few_monsters")
    if profile["low_level_monster_count"] < 8:
        flags.append("too_few_early_monsters")
    if profile["removal_count"] < 5:
        flags.append("too_little_interaction")
    if profile["pressure_monster_count"] > 12:
        flags.append("pressure_density_too_high")
    if profile.get("curve_stability_score", 0) < 15:
        flags.append("curve_stability_too_low")
    if profile.get("control_score", 0) < 15:
        flags.append("low_control_tools")

    if archetype == "samurai":
        if profile["monster_count"] < 20:
            flags.append("samurai_low_creature_density")
        if profile["boss_monster_count"] > 3:
            flags.append("samurai_too_boss_heavy")
    elif archetype == "ninja":
        if profile["spell_count"] < 12:
            flags.append("ninja_low_trick_density")
        if profile["pressure_monster_count"] < 4:
            flags.append("ninja_low_closing_pressure")
    elif archetype == "spirit_dragons":
        if profile["boss_monster_count"] < 5:
            flags.append("spirit_low_dragon_identity")
        if profile["monster_count"] < 24:
            flags.append("spirit_low_monster_density")
    elif archetype == "moonfolk":
        if profile["draw_count"] < 5:
            flags.append("moonfolk_low_card_flow")
        if profile["removal_count"] < 12:
            flags.append("moonfolk_low_control_density")
    elif archetype == "modified":
        if profile["equip_identity_count"] < 8:
            flags.append("modified_low_equipment_identity")
        if profile["pressure_monster_count"] > 6:
            flags.append("modified_too_much_base_pressure")
    return flags


def kamigawa_balance_summary() -> dict[str, dict]:
    """Return balance profiles for every Beyond Kamigawa archetype deck."""
    from src.cards.yugioh.beyond.kamigawa import ARCHETYPE_DECK_BUILDERS

    return {
        name: kamigawa_deck_profile(name, *builder())
        for name, builder in ARCHETYPE_DECK_BUILDERS.items()
    }
