"""
Game registry for the deckbuilder.

Centralizes per-game knowledge: card pool, deck rules (size, copies, sideboard),
cost parsing, and stats. The deckbuilder routes dispatch through here so the
frontend can build decks for any supported game with a single API surface.

Supported games (canonical IDs match GameState.game_mode):
  - "mtg"        — Magic: The Gathering (default)
  - "minecraft"  — Minecraft TCG
  - "pokemon"    — Pokemon TCG
  - "yugioh"     — Yu-Gi-Oh!
  - "hearthstone" — Hearthstone
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.cards import ALL_CARDS as MTG_CARDS
from src.cards.hearthstone import ALL_CARDS as HS_CARDS_LIST
from src.cards.minecraft import MINECRAFT_CARDS
from src.cards.pokemon.sv_starter import SV_STARTER_CARDS as POKEMON_CARDS
from src.cards.yugioh import ALL_YGO_CARDS as YGO_CARDS

from src.engine.types import CardDefinition, CardType


# ---------------------------------------------------------------------------
# Game IDs — canonical names matching GameState.game_mode
# ---------------------------------------------------------------------------

GAMES = ("mtg", "minecraft", "pokemon", "yugioh", "hearthstone")
DEFAULT_GAME = "mtg"


def is_supported_game(game: str) -> bool:
    return game in GAMES


def normalize_game(game: Optional[str]) -> str:
    """Coerce a possibly-missing/aliased game id to a canonical one."""
    if not game:
        return DEFAULT_GAME
    g = game.lower().strip()
    aliases = {
        "magic": "mtg",
        "magic_the_gathering": "mtg",
        "ygo": "yugioh",
        "yu-gi-oh": "yugioh",
        "yu-gi-oh!": "yugioh",
        "hs": "hearthstone",
        "pkm": "pokemon",
        "mc": "minecraft",
    }
    g = aliases.get(g, g)
    return g if g in GAMES else DEFAULT_GAME


# ---------------------------------------------------------------------------
# Card-pool dispatch
# ---------------------------------------------------------------------------

def _hs_pool_dict() -> dict[str, CardDefinition]:
    """Hearthstone ALL_CARDS is a list — collapse to name-keyed dict.
    Duplicates (same name across class lists) win in last-seen order."""
    return {c.name: c for c in HS_CARDS_LIST}


_POOLS: dict[str, Callable[[], dict[str, CardDefinition]]] = {
    "mtg": lambda: MTG_CARDS,
    "minecraft": lambda: MINECRAFT_CARDS,
    "pokemon": lambda: POKEMON_CARDS,
    "yugioh": lambda: YGO_CARDS,
    "hearthstone": _hs_pool_dict,
}


def get_card_pool(game: str) -> dict[str, CardDefinition]:
    """Return the canonical card pool for a game (name → CardDefinition)."""
    g = normalize_game(game)
    return _POOLS[g]()


# ---------------------------------------------------------------------------
# Deck rules per game
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DeckRules:
    min_main: int
    max_main: Optional[int]   # None = no upper bound (e.g., MTG Standard 60+)
    max_copies: int
    sideboard_max: int        # 0 means no sideboard supported
    basic_lands_unlimited: bool


_RULES: dict[str, DeckRules] = {
    "mtg": DeckRules(min_main=60, max_main=None, max_copies=4,
                     sideboard_max=15, basic_lands_unlimited=True),
    "minecraft": DeckRules(min_main=50, max_main=50, max_copies=2,
                           sideboard_max=0, basic_lands_unlimited=False),
    "pokemon": DeckRules(min_main=60, max_main=60, max_copies=4,
                         sideboard_max=0, basic_lands_unlimited=True),  # basic energy unlimited
    "yugioh": DeckRules(min_main=40, max_main=60, max_copies=3,
                        sideboard_max=15, basic_lands_unlimited=False),
    "hearthstone": DeckRules(min_main=30, max_main=30, max_copies=2,
                             sideboard_max=0, basic_lands_unlimited=False),
}


def get_deck_rules(game: str) -> DeckRules:
    return _RULES[normalize_game(game)]


# ---------------------------------------------------------------------------
# Card-data shape — game-specific fields go through `extras`
# ---------------------------------------------------------------------------

def _mtg_extras(card_def: CardDefinition) -> dict[str, Any]:
    chars = card_def.characteristics
    return {
        "mana_cost": chars.mana_cost,
        "colors": [c.name for c in chars.colors],
    }


def _minecraft_extras(card_def: CardDefinition) -> dict[str, Any]:
    return {
        "mc_cost": getattr(card_def, "mc_cost", None) or {},
        "mc_keywords": sorted(getattr(card_def, "mc_keywords", None) or []),
        "mc_attack": getattr(card_def, "mc_attack", None),
        "mc_armor": getattr(card_def, "mc_armor", None),
        "mc_mining_bonus": getattr(card_def, "mc_mining_bonus", None),
        "mc_tool_slot": getattr(card_def, "mc_tool_slot", None),
    }


def _pokemon_extras(card_def: CardDefinition) -> dict[str, Any]:
    chars = card_def.characteristics
    return {
        "hp": getattr(card_def, "pkm_hp", None) or chars.toughness,
        "energy_type": getattr(card_def, "pkm_type", None),
        "stage": getattr(card_def, "pkm_stage", None),
        "evolves_from": getattr(card_def, "pkm_evolves_from", None),
        "weakness": getattr(card_def, "pkm_weakness", None),
        "resistance": getattr(card_def, "pkm_resistance", None),
        "retreat_cost": getattr(card_def, "pkm_retreat_cost", None),
    }


def _yugioh_extras(card_def: CardDefinition) -> dict[str, Any]:
    return {
        "attribute": getattr(card_def, "ygo_attribute", None),
        "monster_type": getattr(card_def, "ygo_type", None),
        "level": getattr(card_def, "ygo_level", None),
        "atk": getattr(card_def, "ygo_atk", None),
        "def": getattr(card_def, "ygo_def", None),
        "spell_trap_kind": getattr(card_def, "ygo_spell_trap_kind", None),
    }


def _hearthstone_extras(card_def: CardDefinition) -> dict[str, Any]:
    return {
        "mana_cost": getattr(card_def, "hs_cost", None),
        "attack": card_def.characteristics.power,
        "health": card_def.characteristics.toughness,
        "rarity": getattr(card_def, "hs_rarity", None),
        "card_class": getattr(card_def, "hs_class", None),
    }


_EXTRAS: dict[str, Callable[[CardDefinition], dict[str, Any]]] = {
    "mtg": _mtg_extras,
    "minecraft": _minecraft_extras,
    "pokemon": _pokemon_extras,
    "yugioh": _yugioh_extras,
    "hearthstone": _hearthstone_extras,
}


def card_to_data(game: str, name: str, card_def: CardDefinition) -> dict[str, Any]:
    """Serialize a CardDefinition for the deckbuilder UI.

    Returns a dict so we don't have to wrestle with Pydantic union types — the
    route layer wraps it in CardDefinitionData(**dict).
    """
    g = normalize_game(game)
    chars = card_def.characteristics
    return {
        "name": name,
        "domain": getattr(card_def, "domain", None),
        "game": g,
        "types": [t.name for t in chars.types],
        "subtypes": list(chars.subtypes),
        "power": chars.power,
        "toughness": chars.toughness,
        "text": card_def.text or "",
        "image_url": getattr(card_def, "image_url", None),
        # Legacy MTG fields kept on the wire so existing UI keeps working until
        # frontend is migrated.
        "mana_cost": chars.mana_cost,
        "colors": [c.name for c in chars.colors],
        "extras": _EXTRAS[g](card_def),
    }


# ---------------------------------------------------------------------------
# Cost parsing — single integer for sorting/filtering, game-specific
# ---------------------------------------------------------------------------

def _mtg_cost(card_def: CardDefinition) -> int:
    s = card_def.characteristics.mana_cost or ""
    if not s:
        return 0
    total = 0
    i = 0
    while i < len(s):
        if s[i] == "{":
            end = s.find("}", i)
            if end == -1:
                break
            sym = s[i + 1:end]
            if sym.isdigit():
                total += int(sym)
            elif sym == "X":
                pass
            else:
                total += 1
            i = end + 1
        else:
            i += 1
    return total


def _mc_cost(card_def: CardDefinition) -> int:
    raw = getattr(card_def, "mc_cost", None) or {}
    return sum(int(v or 0) for v in raw.values())


def _hs_cost(card_def: CardDefinition) -> int:
    return int(getattr(card_def, "hs_cost", 0) or 0)


def _ygo_level(card_def: CardDefinition) -> int:
    """For YGO, "cost" is meaningless — sort by level/rank instead."""
    return int(getattr(card_def, "ygo_level", 0) or 0)


def _pkm_cost(card_def: CardDefinition) -> int:
    """Pokemon attack cost is per-attack; use HP / 10 as a coarse proxy
    for sortability. Trainers/Energy fall back to 0."""
    hp = getattr(card_def, "pkm_hp", None)
    if isinstance(hp, int):
        return hp // 10
    return 0


_COSTS: dict[str, Callable[[CardDefinition], int]] = {
    "mtg": _mtg_cost,
    "minecraft": _mc_cost,
    "hearthstone": _hs_cost,
    "yugioh": _ygo_level,
    "pokemon": _pkm_cost,
}


def get_card_cost(game: str, card_def: CardDefinition) -> int:
    return _COSTS[normalize_game(game)](card_def)


# ---------------------------------------------------------------------------
# Stats — game-specific, all return a dict the frontend can render
# ---------------------------------------------------------------------------

def _mtg_is_land(card_def: CardDefinition) -> bool:
    return CardType.LAND in card_def.characteristics.types


def _is_basic_land(card_name: str) -> bool:
    return card_name in {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


def compute_stats(game: str, mainboard: list[dict], sideboard: list[dict]) -> dict[str, Any]:
    """Compute deck statistics. Each game returns the same top-level shape:
        card_count, cost_curve, type_breakdown, validation, extras
    `extras` carries game-specific extras (color distribution for MTG, energy
    type distribution for Pokemon, etc.). The frontend dispatches off `game`.
    """
    g = normalize_game(game)
    pool = get_card_pool(g)
    rules = get_deck_rules(g)

    card_count = 0
    cost_curve: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    type_breakdown: dict[str, int] = {}
    extras: dict[str, Any] = {}

    if g == "mtg":
        extras["color_distribution"] = {}
        extras["land_count"] = 0
        extras["creature_count"] = 0
        extras["spell_count"] = 0
        extras["nonland_total_cost"] = 0
        extras["nonland_count"] = 0

    if g == "minecraft":
        extras["material_distribution"] = {"wood": 0, "stone": 0, "iron": 0, "redstone": 0, "diamond": 0}

    if g == "pokemon":
        extras["energy_distribution"] = {}
        extras["pokemon_count"] = 0
        extras["trainer_count"] = 0
        extras["energy_card_count"] = 0

    if g == "yugioh":
        extras["attribute_distribution"] = {}
        extras["monster_count"] = 0
        extras["spell_count"] = 0
        extras["trap_count"] = 0

    if g == "hearthstone":
        extras["class_distribution"] = {}
        extras["minion_count"] = 0
        extras["spell_count"] = 0
        extras["weapon_count"] = 0

    for entry in mainboard:
        name = entry.get("card") if isinstance(entry, dict) else getattr(entry, "card_name", None)
        qty = int(entry.get("qty", 0) if isinstance(entry, dict) else getattr(entry, "quantity", 0))
        card_def = pool.get(name)
        if not card_def:
            continue

        card_count += qty
        chars = card_def.characteristics

        # Type breakdown (raw type names, game-agnostic)
        for t in chars.types:
            type_breakdown[t.name] = type_breakdown.get(t.name, 0) + qty

        # Cost curve — special-case MTG to skip lands
        cost = get_card_cost(g, card_def)
        if g == "mtg":
            if _mtg_is_land(card_def):
                extras["land_count"] += qty
            else:
                extras["nonland_count"] += qty
                extras["nonland_total_cost"] += cost * qty
                cost_curve[min(cost, 6)] = cost_curve.get(min(cost, 6), 0) + qty
            if CardType.CREATURE in chars.types:
                extras["creature_count"] += qty
            elif not _mtg_is_land(card_def):
                extras["spell_count"] += qty
            for c in chars.colors:
                extras["color_distribution"][c.name] = extras["color_distribution"].get(c.name, 0) + qty
        else:
            cost_curve[min(cost, 6)] = cost_curve.get(min(cost, 6), 0) + qty

        if g == "minecraft":
            for mat, amount in (getattr(card_def, "mc_cost", None) or {}).items():
                if mat in extras["material_distribution"]:
                    extras["material_distribution"][mat] += int(amount or 0) * qty

        if g == "pokemon":
            etype = getattr(card_def, "pkm_type", None)
            if etype:
                extras["energy_distribution"][etype] = extras["energy_distribution"].get(etype, 0) + qty
            type_names = {t.name for t in chars.types}
            if "PKM_POKEMON" in type_names:
                extras["pokemon_count"] += qty
            elif "PKM_TRAINER" in type_names:
                extras["trainer_count"] += qty
            elif "PKM_ENERGY" in type_names:
                extras["energy_card_count"] += qty

        if g == "yugioh":
            attr = getattr(card_def, "ygo_attribute", None)
            if attr:
                extras["attribute_distribution"][attr] = extras["attribute_distribution"].get(attr, 0) + qty
            type_names = {t.name for t in chars.types}
            if "YGO_MONSTER" in type_names:
                extras["monster_count"] += qty
            elif "YGO_SPELL" in type_names:
                extras["spell_count"] += qty
            elif "YGO_TRAP" in type_names:
                extras["trap_count"] += qty

        if g == "hearthstone":
            cls = getattr(card_def, "hs_class", None)
            if cls:
                extras["class_distribution"][cls] = extras["class_distribution"].get(cls, 0) + qty
            type_names = {t.name for t in chars.types}
            if "HS_MINION" in type_names:
                extras["minion_count"] += qty
            elif "HS_SPELL" in type_names:
                extras["spell_count"] += qty
            elif "HS_WEAPON" in type_names:
                extras["weapon_count"] += qty

    if g == "mtg" and extras["nonland_count"] > 0:
        extras["average_cost"] = round(extras["nonland_total_cost"] / extras["nonland_count"], 2)
    elif card_count > 0:
        total_cost_sum = sum(cost * count for cost, count in cost_curve.items())
        extras["average_cost"] = round(total_cost_sum / card_count, 2)
    else:
        extras["average_cost"] = 0.0

    is_valid, errors = validate(g, mainboard, sideboard)

    return {
        "card_count": card_count,
        "cost_curve": {str(k): v for k, v in sorted(cost_curve.items())},
        "type_breakdown": type_breakdown,
        "extras": extras,
        "validation": {"is_valid": is_valid, "errors": errors},
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(game: str, mainboard: list[dict], sideboard: list[dict]) -> tuple[bool, list[str]]:
    g = normalize_game(game)
    rules = get_deck_rules(g)
    errors: list[str] = []

    main_count = sum(int(e.get("qty", 0) if isinstance(e, dict) else e.quantity) for e in mainboard)
    side_count = sum(int(e.get("qty", 0) if isinstance(e, dict) else e.quantity) for e in sideboard or [])

    if main_count < rules.min_main:
        errors.append(f"Mainboard has {main_count} cards, need at least {rules.min_main}")
    if rules.max_main is not None and main_count > rules.max_main:
        errors.append(f"Mainboard has {main_count} cards, max is {rules.max_main}")

    if side_count > rules.sideboard_max:
        if rules.sideboard_max == 0:
            errors.append(f"{g} does not support a sideboard")
        else:
            errors.append(f"Sideboard has {side_count} cards, max is {rules.sideboard_max}")

    pool = get_card_pool(g)
    for entry in mainboard:
        name = entry.get("card") if isinstance(entry, dict) else entry.card_name
        qty = int(entry.get("qty", 0) if isinstance(entry, dict) else entry.quantity)
        if rules.basic_lands_unlimited and (
            (g == "mtg" and _is_basic_land(name))
            or (g == "pokemon" and name in pool and "PKM_ENERGY" in {t.name for t in pool[name].characteristics.types})
        ):
            continue
        if qty > rules.max_copies:
            errors.append(f"Too many copies of {name}: {qty} (max {rules.max_copies})")

    return len(errors) == 0, errors
