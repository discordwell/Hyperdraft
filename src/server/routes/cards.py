"""
Cards Routes

Endpoints for querying the card database.
"""

from fastapi import APIRouter, Query
from typing import Optional

from ..models import CardDefinitionData, CardListResponse

# Card imports
from src.cards.test_cards import TEST_CARDS
from src.engine.types import CardType, Color

router = APIRouter(prefix="/cards", tags=["cards"])


def card_def_to_data(name: str, card_def) -> CardDefinitionData:
    """Convert a CardDefinition to CardDefinitionData."""
    chars = card_def.characteristics

    return CardDefinitionData(
        name=name,
        mana_cost=chars.mana_cost,
        types=[t.name for t in chars.types],
        subtypes=list(chars.subtypes),
        power=chars.power,
        toughness=chars.toughness,
        text=card_def.text,
        colors=[c.name for c in chars.colors]
    )


@router.get("", response_model=CardListResponse)
async def list_cards(
    type_filter: Optional[str] = Query(None, description="Filter by card type (CREATURE, INSTANT, etc)"),
    color_filter: Optional[str] = Query(None, description="Filter by color (WHITE, BLUE, BLACK, RED, GREEN)"),
    name_search: Optional[str] = Query(None, description="Search by card name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
) -> CardListResponse:
    """
    List available cards from the card database.

    Supports filtering by type, color, and name search.
    """
    cards = []

    for name, card_def in TEST_CARDS.items():
        # Apply type filter
        if type_filter:
            try:
                card_type = CardType[type_filter.upper()]
                if card_type not in card_def.characteristics.types:
                    continue
            except KeyError:
                pass

        # Apply color filter
        if color_filter:
            try:
                color = Color[color_filter.upper()]
                if color not in card_def.characteristics.colors:
                    continue
            except KeyError:
                pass

        # Apply name search
        if name_search:
            if name_search.lower() not in name.lower():
                continue

        cards.append(card_def_to_data(name, card_def))

    total = len(cards)

    # Apply pagination
    cards = cards[offset:offset + limit]

    return CardListResponse(
        cards=cards,
        total=total
    )


@router.get("/{card_name}", response_model=CardDefinitionData)
async def get_card(card_name: str) -> CardDefinitionData:
    """
    Get details for a specific card by name.
    """
    # Case-insensitive lookup
    for name, card_def in TEST_CARDS.items():
        if name.lower() == card_name.lower():
            return card_def_to_data(name, card_def)

    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Card '{card_name}' not found")


@router.get("/types/list")
async def list_card_types() -> dict:
    """
    List all available card types.
    """
    return {
        "types": [t.name for t in CardType]
    }


@router.get("/colors/list")
async def list_colors() -> dict:
    """
    List all available colors.
    """
    return {
        "colors": [c.name for c in Color]
    }
