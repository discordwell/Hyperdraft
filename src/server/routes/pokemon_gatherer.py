"""
Pokemon Gatherer Routes

API endpoints for browsing Pokemon TCG card sets. Parallel to the MTG
gatherer in deckbuilder.py but Pokemon-aware (HP, attacks, weakness,
retreat cost, etc.).
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from src.cards.pokemon.set_registry import (
    POKEMON_SETS,
    get_all_pokemon_sets,
    get_pokemon_cards_in_set,
    get_pokemon_guild,
    get_pokemon_guilds,
    get_pokemon_set_info,
)
from src.engine.types import CardType, PokemonType


router = APIRouter(prefix="/pokemon", tags=["pokemon-gatherer"])


# =============================================================================
# Response Models
# =============================================================================

class PokemonEnergyCost(BaseModel):
    """One slice of an attack's energy cost."""
    type: str  # PokemonType code: G/R/W/L/P/F/D/M/C
    count: int


class PokemonAttackData(BaseModel):
    name: str
    cost: list[PokemonEnergyCost] = Field(default_factory=list)
    damage: Optional[int] = None  # None for status-only attacks
    text: str = ""


class PokemonAbilityData(BaseModel):
    name: str
    text: str = ""
    ability_type: Optional[str] = None  # "Ability", "Poke-Power", etc.


class PokemonCardData(BaseModel):
    """Pokemon-domain card for the Pokemon gatherer."""
    name: str
    supertype: str  # "Pokemon" | "Trainer" | "Energy"
    trainer_subtype: Optional[str] = None  # "Item"|"Supporter"|"Stadium"|"Tool"
    text: str = ""
    rarity: Optional[str] = None
    image_url: Optional[str] = None
    guild: Optional[str] = None  # Beyond Ravnica only

    # Pokemon
    hp: Optional[int] = None
    pokemon_type: Optional[str] = None  # PokemonType code
    evolution_stage: Optional[str] = None  # "Basic"|"Stage 1"|"Stage 2"
    evolves_from: Optional[str] = None
    weakness_type: Optional[str] = None
    weakness_modifier: Optional[str] = None
    resistance_type: Optional[str] = None
    resistance_modifier: Optional[int] = None
    retreat_cost: Optional[int] = None
    is_ex: bool = False
    rule_box: Optional[str] = None
    prize_count: Optional[int] = None
    attacks: list[PokemonAttackData] = Field(default_factory=list)
    ability: Optional[PokemonAbilityData] = None

    # Energy
    energy_type: Optional[str] = None  # for energy cards, == pokemon_type


class PokemonSetInfoResponse(BaseModel):
    code: str
    name: str
    card_count: int
    release_date: str
    set_type: str


class PokemonSetListResponse(BaseModel):
    sets: list[PokemonSetInfoResponse]
    total: int


class PokemonSetDetailResponse(BaseModel):
    code: str
    name: str
    card_count: int
    release_date: str
    set_type: str
    supertype_breakdown: dict[str, int]
    type_breakdown: dict[str, int]
    guilds: list[str] = Field(default_factory=list)  # populated for BRV


class PokemonCardSearchResponse(BaseModel):
    cards: list[PokemonCardData]
    total: int
    has_more: bool


# =============================================================================
# Conversion helpers
# =============================================================================

def _supertype_for(card_def) -> tuple[str, Optional[str]]:
    """Return (supertype, trainer_subtype)."""
    types = card_def.characteristics.types
    if CardType.POKEMON in types:
        return "Pokemon", None
    if CardType.ENERGY in types:
        return "Energy", None
    if CardType.TRAINER in types:
        if CardType.ITEM in types:
            return "Trainer", "Item"
        if CardType.SUPPORTER in types:
            return "Trainer", "Supporter"
        if CardType.STADIUM in types:
            return "Trainer", "Stadium"
        if CardType.POKEMON_TOOL in types:
            return "Trainer", "Tool"
        return "Trainer", None
    return "Unknown", None


def _attack_to_data(attack: dict) -> PokemonAttackData:
    cost_raw = attack.get("cost") or []
    cost = [
        PokemonEnergyCost(type=c.get("type", "C"), count=int(c.get("count", 0)))
        for c in cost_raw
    ]
    dmg_raw = attack.get("damage")
    damage = int(dmg_raw) if isinstance(dmg_raw, (int, float)) else None
    return PokemonAttackData(
        name=attack.get("name", ""),
        cost=cost,
        damage=damage,
        text=attack.get("text") or "",
    )


def _ability_to_data(ability: Optional[dict]) -> Optional[PokemonAbilityData]:
    if not ability:
        return None
    return PokemonAbilityData(
        name=ability.get("name", ""),
        text=ability.get("text") or "",
        ability_type=ability.get("ability_type"),
    )


def _card_to_data(card_def, set_code: str) -> PokemonCardData:
    supertype, trainer_subtype = _supertype_for(card_def)
    guild = get_pokemon_guild(card_def.name) if set_code == "BRV" else None

    energy_type = None
    if supertype == "Energy":
        energy_type = card_def.pokemon_type

    return PokemonCardData(
        name=card_def.name,
        supertype=supertype,
        trainer_subtype=trainer_subtype,
        text=card_def.text or "",
        rarity=card_def.rarity,
        image_url=card_def.image_url,
        guild=guild,
        hp=card_def.hp,
        pokemon_type=card_def.pokemon_type,
        evolution_stage=card_def.evolution_stage,
        evolves_from=card_def.evolves_from,
        weakness_type=card_def.weakness_type,
        weakness_modifier=card_def.weakness_modifier,
        resistance_type=card_def.resistance_type,
        resistance_modifier=card_def.resistance_modifier,
        retreat_cost=card_def.retreat_cost if supertype == "Pokemon" else None,
        is_ex=card_def.is_ex,
        rule_box=card_def.rule_box,
        prize_count=card_def.prize_count if supertype == "Pokemon" else None,
        attacks=[_attack_to_data(a) for a in (card_def.attacks or [])],
        ability=_ability_to_data(card_def.ability),
        energy_type=energy_type,
    )


# =============================================================================
# Filtering / sorting
# =============================================================================

_SUPERTYPE_ORDER = {"Pokemon": 0, "Trainer": 1, "Energy": 2, "Unknown": 3}
_STAGE_ORDER = {"Basic": 0, "Stage 1": 1, "Stage 2": 2}


def _sort_key(card: PokemonCardData, sort_by: str):
    # Caller (_sort_pokemon_cards) splits cards with the missing attribute
    # out before this is reached, so we never need a sentinel for that
    # axis. The `or 0` / `or ""` fallbacks just keep the type signature
    # honest in case a card slips through.
    if sort_by == "hp":
        return (card.hp or 0, card.name.lower())
    if sort_by == "type":
        return (card.pokemon_type or "", card.name.lower())
    if sort_by == "rarity":
        return (card.rarity or "", card.name.lower())
    if sort_by == "stage":
        return (_STAGE_ORDER.get(card.evolution_stage or "", 99), card.name.lower())
    if sort_by == "supertype":
        return (_SUPERTYPE_ORDER.get(card.supertype, 99), card.name.lower())
    return card.name.lower()


def _sort_pokemon_cards(
    cards: list[PokemonCardData], sort_by: str, sort_order: str
) -> list[PokemonCardData]:
    """Sort with "missing-attribute" cards always pinned to the bottom,
    regardless of asc/desc — otherwise asc by HP would bubble Energy /
    Trainer (null HP) to the top instead of bottom. Same logic for
    rarity (most BRV custom cards have no rarity) and type."""
    reverse = sort_order.lower() == "desc"

    def is_missing(c: PokemonCardData) -> bool:
        if sort_by == "hp":
            return c.hp is None
        if sort_by == "stage":
            return c.evolution_stage is None
        if sort_by == "type":
            return c.pokemon_type is None
        if sort_by == "rarity":
            return not c.rarity
        return False

    present = [c for c in cards if not is_missing(c)]
    absent = [c for c in cards if is_missing(c)]
    present.sort(key=lambda c: _sort_key(c, sort_by), reverse=reverse)
    absent.sort(key=lambda c: c.name.lower())
    return present + absent


# =============================================================================
# Routes
# =============================================================================

@router.get("/sets", response_model=PokemonSetListResponse)
async def list_pokemon_sets(
    set_type: Optional[str] = Query(None, description="Filter: starter, beyond"),
) -> PokemonSetListResponse:
    sets = get_all_pokemon_sets(set_type)
    return PokemonSetListResponse(
        sets=[
            PokemonSetInfoResponse(
                code=s.code,
                name=s.name,
                card_count=s.card_count,
                release_date=s.release_date,
                set_type=s.set_type,
            )
            for s in sets
        ],
        total=len(sets),
    )


@router.get("/sets/{set_code}", response_model=PokemonSetDetailResponse)
async def get_pokemon_set_detail(set_code: str) -> PokemonSetDetailResponse:
    info = get_pokemon_set_info(set_code)
    if not info:
        raise HTTPException(status_code=404, detail=f"Pokemon set '{set_code}' not found")

    cards = get_pokemon_cards_in_set(set_code).values()

    supertype_breakdown: dict[str, int] = {}
    type_breakdown: dict[str, int] = {}
    for c in cards:
        st, _ = _supertype_for(c)
        supertype_breakdown[st] = supertype_breakdown.get(st, 0) + 1
        if c.pokemon_type and st == "Pokemon":
            type_breakdown[c.pokemon_type] = type_breakdown.get(c.pokemon_type, 0) + 1

    guilds: list[str] = []
    if info.code == "BRV":
        guilds = get_pokemon_guilds()

    return PokemonSetDetailResponse(
        code=info.code,
        name=info.name,
        card_count=info.card_count,
        release_date=info.release_date,
        set_type=info.set_type,
        supertype_breakdown=supertype_breakdown,
        type_breakdown=type_breakdown,
        guilds=guilds,
    )


@router.get("/sets/{set_code}/cards", response_model=PokemonCardSearchResponse)
async def list_pokemon_set_cards(
    set_code: str,
    supertype: Optional[str] = Query(None, description="Pokemon | Trainer | Energy"),
    trainer_subtype: Optional[str] = Query(None, description="Item|Supporter|Stadium|Tool"),
    pokemon_type: Optional[str] = Query(None, description="PokemonType code (G/R/W/L/P/F/D/M/C)"),
    evolution_stage: Optional[str] = Query(None, description="Basic | Stage 1 | Stage 2"),
    is_ex: Optional[bool] = Query(None),
    hp_min: Optional[int] = Query(None, ge=0),
    hp_max: Optional[int] = Query(None, ge=0),
    retreat_cost_min: Optional[int] = Query(None, ge=0),
    retreat_cost_max: Optional[int] = Query(None, ge=0),
    guild: Optional[str] = Query(None, description="BRV only: azorius, boros, ..."),
    text_search: Optional[str] = Query(None),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> PokemonCardSearchResponse:
    info = get_pokemon_set_info(set_code)
    if not info:
        raise HTTPException(status_code=404, detail=f"Pokemon set '{set_code}' not found")

    raw = get_pokemon_cards_in_set(set_code).values()
    cards = [_card_to_data(c, info.code) for c in raw]

    needle = text_search.lower().strip() if text_search else None

    def keep(c: PokemonCardData) -> bool:
        if supertype and c.supertype != supertype:
            return False
        if trainer_subtype and c.trainer_subtype != trainer_subtype:
            return False
        if pokemon_type and c.pokemon_type != pokemon_type:
            return False
        if evolution_stage and c.evolution_stage != evolution_stage:
            return False
        if is_ex is not None and c.is_ex != is_ex:
            return False
        if hp_min is not None and (c.hp is None or c.hp < hp_min):
            return False
        if hp_max is not None and (c.hp is None or c.hp > hp_max):
            return False
        if retreat_cost_min is not None and (c.retreat_cost is None or c.retreat_cost < retreat_cost_min):
            return False
        if retreat_cost_max is not None and (c.retreat_cost is None or c.retreat_cost > retreat_cost_max):
            return False
        if guild and (c.guild or "").lower() != guild.lower():
            return False
        if needle and needle not in c.name.lower() and needle not in (c.text or "").lower():
            return False
        return True

    filtered = _sort_pokemon_cards([c for c in cards if keep(c)], sort_by, sort_order)

    total = len(filtered)
    page = filtered[offset:offset + limit]
    return PokemonCardSearchResponse(
        cards=page,
        total=total,
        has_more=(offset + limit) < total,
    )
