"""Yu-Gi-Oh! deckbuilding quality metrics.

The optimized Yu-Gi-Oh! decks carry strategy hints, but this module gives
tests and reports stable numeric signals before tuning decklists.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from src.engine.types import CardDefinition, CardType


def _text_blob(card: CardDefinition) -> str:
    return f"{card.name} {card.text or ''}".lower()


def _is_monster(card: CardDefinition) -> bool:
    return CardType.YGO_MONSTER in card.characteristics.types


def _is_spell(card: CardDefinition) -> bool:
    return CardType.YGO_SPELL in card.characteristics.types


def _is_trap(card: CardDefinition) -> bool:
    return CardType.YGO_TRAP in card.characteristics.types


def _has_any(card: CardDefinition, terms: Iterable[str]) -> bool:
    blob = _text_blob(card)
    return any(term in blob for term in terms)


def analyze_ygo_deck_quality(deck: list[CardDefinition], strategy: dict | None = None) -> dict:
    """Return stable, role-aware quality metrics for a Yu-Gi-Oh! deck."""
    names = [card.name for card in deck]
    copies = Counter(names)
    monsters = [card for card in deck if _is_monster(card)]
    spells = [card for card in deck if _is_spell(card)]
    traps = [card for card in deck if _is_trap(card)]

    low_level = [card for card in monsters if (getattr(card, "level", 0) or 0) <= 4]
    tribute = [card for card in monsters if (getattr(card, "level", 0) or 0) >= 5]
    pressure = [card for card in monsters if (getattr(card, "atk", 0) or 0) >= 1800]

    draw_terms = ("draw", "pot of greed", "graceful charity", "dekoichi")
    removal_terms = (
        "destroy", "banish", "raigeki", "dark hole", "mirror force",
        "sakuretsu", "bottomless", "nobleman", "torrential",
        "dimensional prison", "book of moon",
    )
    burn_terms = (
        "damage", "inflict", "burn", "ookazi", "secret barrel",
        "just desserts", "magic cylinder", "ring of destruction",
    )
    reach_terms = (
        "inflict", "direct damage", "opponent takes", "ookazi",
        "secret barrel", "just desserts", "magic cylinder",
        "stealth bird", "des koala", "damage to opponent",
    )
    stall_terms = (
        "cannot attack", "gravity bind", "messenger of peace",
        "swords of revealing light", "marshmallon", "spirit reaper",
    )
    stall_lock_terms = (
        "gravity bind", "messenger of peace",
        "swords of revealing light", "level limit - area b",
    )
    fodder_terms = (
        "special summon", "token", "tribute fodder", "treeborn",
        "mystic tomato", "sangan", "masked dragon", "gravekeeper's spy",
        "giant germ",
    )
    revival_terms = (
        "monster reborn", "premature burial", "call of the haunted",
        "revive", "special summon 1 monster from your gy",
    )

    role = (strategy or {}).get("archetype", "unknown")
    summon_priority = list((strategy or {}).get("summon_priority", []))
    set_priority = list((strategy or {}).get("set_priority", []))
    missing_summon_priority = sorted(name for name in summon_priority if name not in copies)
    missing_set_priority = sorted(name for name in set_priority if name not in copies)
    summary = {
        "size": len(deck),
        "role": role,
        "monster_count": len(monsters),
        "spell_count": len(spells),
        "trap_count": len(traps),
        "low_level_monster_count": len(low_level),
        "tribute_monster_count": len(tribute),
        "pressure_monster_count": len(pressure),
        "draw_count": sum(1 for card in deck if _has_any(card, draw_terms)),
        "removal_count": sum(1 for card in deck if _has_any(card, removal_terms)),
        "burn_count": sum(1 for card in deck if _has_any(card, burn_terms)),
        "reliable_reach_count": sum(1 for card in deck if _has_any(card, reach_terms)),
        "stall_count": sum(1 for card in deck if _has_any(card, stall_terms)),
        "stall_lock_count": sum(1 for card in deck if _has_any(card, stall_lock_terms)),
        "tribute_fodder_count": sum(1 for card in deck if _has_any(card, fodder_terms)),
        "revival_spell_count": sum(1 for card in deck if _has_any(card, revival_terms)),
        "revival_target_count": sum(
            1 for card in monsters
            if (getattr(card, "atk", 0) or 0) >= 1800 or (getattr(card, "level", 0) or 0) >= 5
        ),
        "dragon_count": sum(
            1 for card in deck
            if "Dragon" in card.characteristics.subtypes or "dragon" in card.name.lower()
        ),
        "summon_priority_count": sum(1 for name in summon_priority if name in copies),
        "set_priority_count": sum(1 for name in set_priority if name in copies),
        "missing_summon_priority": missing_summon_priority,
        "missing_set_priority": missing_set_priority,
        "copy_violations": sorted((name, count) for name, count in copies.items() if count > 3),
    }
    summary["quality_flags"] = ygo_deck_quality_flags(summary)
    summary["role_quality_flags"] = ygo_role_quality_flags(summary)
    return summary


def ygo_deck_quality_flags(summary: dict) -> list[str]:
    """Generic deck-construction issues independent of archetype."""
    flags = []
    if not 40 <= summary["size"] <= 60:
        flags.append("invalid_main_deck_size")
    if summary["copy_violations"]:
        flags.append("copy_limit_violation")
    if summary["monster_count"] < 10:
        flags.append("too_few_monsters")
    if summary["low_level_monster_count"] < 8:
        flags.append("too_few_normal_summons")
    if summary["removal_count"] < 5:
        flags.append("too_little_interaction")
    if summary["tribute_monster_count"] > summary["tribute_fodder_count"] + 3:
        flags.append("tribute_load_exceeds_fodder")
    if summary["missing_summon_priority"] or summary["missing_set_priority"]:
        flags.append("strategy_priority_missing_cards")
    if summary["revival_spell_count"] >= 2 and summary["revival_target_count"] < 2:
        flags.append("revival_package_low_targets")
    return flags


def ygo_role_quality_flags(summary: dict) -> list[str]:
    """Role-specific deckbuilding checks for the optimized YGO decks."""
    role = summary["role"].lower()
    flags = []
    if "burn" in role:
        if summary["burn_count"] < 8:
            flags.append("burn_low_reach")
        if summary["reliable_reach_count"] < 10:
            flags.append("burn_low_reliable_reach")
        if summary["stall_count"] < 3:
            flags.append("burn_low_stall")
        if summary["stall_lock_count"] < 3:
            flags.append("burn_low_stall_locks")
        if summary["monster_count"] > 16:
            flags.append("burn_too_monster_heavy")
    elif "dragon" in role or "beatdown" in role:
        if summary["dragon_count"] < 14:
            flags.append("dragon_low_dragon_density")
        if summary["pressure_monster_count"] < 10:
            flags.append("dragon_low_pressure")
        if summary["tribute_fodder_count"] < 5:
            flags.append("dragon_low_fodder")
    elif "tribute" in role or "monarch" in role:
        if summary["tribute_monster_count"] < 8:
            flags.append("monarch_low_tribute_density")
        if summary["tribute_fodder_count"] < 8:
            flags.append("monarch_low_fodder")
        if summary["low_level_monster_count"] < 8:
            flags.append("monarch_low_early_board")
    elif "control" in role:
        if summary["draw_count"] < 3:
            flags.append("control_low_draw")
        if summary["removal_count"] < 10:
            flags.append("control_low_interaction")
        if summary["low_level_monster_count"] < 10:
            flags.append("control_low_early_board")
    return flags


def analyze_all_ygo_optimized_decks() -> dict[str, dict]:
    """Analyze every optimized Yu-Gi-Oh! deck registry entry."""
    from src.cards.yugioh.ygo_optimized import YGO_OPTIMIZED_DECKS

    return {
        name: analyze_ygo_deck_quality(entry["deck"], entry.get("strategy"))
        for name, entry in YGO_OPTIMIZED_DECKS.items()
    }
