"""
Deckbuilder Routes

API endpoints for deck building, card search, and deck management.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from src.cards import ALL_CARDS
from src.decks.deck import validate_deck, Deck, DeckEntry
from src.engine.types import CardType, Color
from ..services.deck_storage import deck_storage
from ..models import CardDefinitionData


router = APIRouter(prefix="/deckbuilder", tags=["deckbuilder"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CardSearchRequest(BaseModel):
    """Advanced card search request."""
    query: Optional[str] = Field(None, description="Search in card name or text")
    types: list[str] = Field(default_factory=list, description="Filter by card types")
    colors: list[str] = Field(default_factory=list, description="Filter by colors (W, U, B, R, G)")
    cmc_min: Optional[int] = Field(None, ge=0, description="Minimum mana value")
    cmc_max: Optional[int] = Field(None, ge=0, description="Maximum mana value")
    text_search: Optional[str] = Field(None, description="Search in card text only")
    rarity: Optional[str] = Field(None, description="Filter by rarity")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class CardSearchResponse(BaseModel):
    """Card search results."""
    cards: list[CardDefinitionData]
    total: int
    has_more: bool


class DeckEntryData(BaseModel):
    """A single deck entry."""
    card: str
    qty: int = Field(ge=1, le=99)


class SaveDeckRequest(BaseModel):
    """Request to save a deck."""
    deck_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=100)
    archetype: str = Field(default="Aggro")
    colors: list[str] = Field(default_factory=list)
    description: str = Field(default="")
    mainboard: list[DeckEntryData]
    sideboard: list[DeckEntryData] = Field(default_factory=list)
    format: str = Field(default="Standard")


class DeckResponse(BaseModel):
    """Full deck data response."""
    id: str
    name: str
    archetype: str
    colors: list[str]
    description: str
    mainboard: list[dict]
    sideboard: list[dict]
    format: str
    mainboard_count: int
    land_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DeckListResponse(BaseModel):
    """List of deck summaries."""
    decks: list[dict]
    total: int


class DeckStatsRequest(BaseModel):
    """Request for deck statistics."""
    mainboard: list[DeckEntryData]
    sideboard: list[DeckEntryData] = Field(default_factory=list)


class DeckStatsResponse(BaseModel):
    """Deck statistics response."""
    card_count: int
    land_count: int
    creature_count: int
    spell_count: int
    average_cmc: float
    color_distribution: dict[str, int]
    mana_curve: dict[str, int]  # CMC -> count
    type_breakdown: dict[str, int]
    validation: dict


class ImportDeckRequest(BaseModel):
    """Request to import a deck from text."""
    text: str = Field(..., description="Deck list in text format")
    format: str = Field(default="Standard")


class ExportDeckResponse(BaseModel):
    """Exported deck in text format."""
    text: str
    deck_name: str


# =============================================================================
# Helper Functions
# =============================================================================

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


def parse_mana_cost(mana_cost: str) -> int:
    """Parse a mana cost string to get total mana value."""
    if not mana_cost:
        return 0

    total = 0
    i = 0
    while i < len(mana_cost):
        if mana_cost[i] == '{':
            end = mana_cost.find('}', i)
            if end == -1:
                break
            symbol = mana_cost[i+1:end]
            if symbol.isdigit():
                total += int(symbol)
            elif symbol in ('W', 'U', 'B', 'R', 'G', 'C'):
                total += 1
            elif '/' in symbol:  # Hybrid mana
                total += 1
            elif symbol == 'X':
                pass  # X is 0 for CMC calculation
            i = end + 1
        else:
            i += 1

    return total


def get_card_types(card_def) -> list[str]:
    """Get card types as strings."""
    return [t.name for t in card_def.characteristics.types]


def is_land(card_def) -> bool:
    """Check if a card is a land."""
    return CardType.LAND in card_def.characteristics.types


def is_creature(card_def) -> bool:
    """Check if a card is a creature."""
    return CardType.CREATURE in card_def.characteristics.types


# =============================================================================
# Card Search Endpoints
# =============================================================================

@router.post("/cards/search", response_model=CardSearchResponse)
async def search_cards(request: CardSearchRequest) -> CardSearchResponse:
    """
    Advanced card search with multiple filters.

    Searches the full card database (7,850+ cards).
    """
    results = []

    for name, card_def in ALL_CARDS.items():
        chars = card_def.characteristics

        # Query filter (name or text)
        if request.query:
            query_lower = request.query.lower()
            name_match = query_lower in name.lower()
            text_match = query_lower in (card_def.text or '').lower()
            if not name_match and not text_match:
                continue

        # Type filter
        if request.types:
            card_types = [t.name for t in chars.types]
            if not any(t.upper() in card_types for t in request.types):
                continue

        # Color filter
        if request.colors:
            card_colors = [c.name for c in chars.colors]
            # Match if card has any of the requested colors
            if not any(c.upper() in card_colors for c in request.colors):
                continue

        # CMC filter
        cmc = parse_mana_cost(chars.mana_cost)
        if request.cmc_min is not None and cmc < request.cmc_min:
            continue
        if request.cmc_max is not None and cmc > request.cmc_max:
            continue

        # Text search filter
        if request.text_search:
            if request.text_search.lower() not in (card_def.text or '').lower():
                continue

        results.append(card_def_to_data(name, card_def))

    total = len(results)

    # Sort by name
    results.sort(key=lambda c: c.name)

    # Apply pagination
    paginated = results[request.offset:request.offset + request.limit]

    return CardSearchResponse(
        cards=paginated,
        total=total,
        has_more=request.offset + len(paginated) < total
    )


@router.get("/cards/all", response_model=CardSearchResponse)
async def get_all_cards(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
) -> CardSearchResponse:
    """
    Get all cards with pagination.

    Use search endpoint for filtered queries.
    """
    all_cards = [
        card_def_to_data(name, card_def)
        for name, card_def in ALL_CARDS.items()
    ]
    all_cards.sort(key=lambda c: c.name)

    total = len(all_cards)
    paginated = all_cards[offset:offset + limit]

    return CardSearchResponse(
        cards=paginated,
        total=total,
        has_more=offset + len(paginated) < total
    )


@router.get("/cards/{card_name}", response_model=CardDefinitionData)
async def get_card(card_name: str) -> CardDefinitionData:
    """Get a specific card by name."""
    # Case-insensitive lookup
    for name, card_def in ALL_CARDS.items():
        if name.lower() == card_name.lower():
            return card_def_to_data(name, card_def)

    raise HTTPException(status_code=404, detail=f"Card '{card_name}' not found")


# =============================================================================
# Deck Management Endpoints
# =============================================================================

@router.get("/decks", response_model=DeckListResponse)
async def list_decks() -> DeckListResponse:
    """List all saved decks."""
    decks = deck_storage.list_decks()
    return DeckListResponse(decks=decks, total=len(decks))


@router.get("/decks/{deck_id}", response_model=DeckResponse)
async def get_deck(deck_id: str) -> DeckResponse:
    """Get a deck by ID."""
    deck_data = deck_storage.get_deck(deck_id)
    if not deck_data:
        raise HTTPException(status_code=404, detail=f"Deck '{deck_id}' not found")

    return DeckResponse(**deck_data)


@router.post("/decks", response_model=DeckResponse)
async def save_deck(request: SaveDeckRequest) -> DeckResponse:
    """Save a new deck or update an existing one."""
    deck_data = deck_storage.save_deck(
        deck_id=request.deck_id,
        name=request.name,
        archetype=request.archetype,
        colors=request.colors,
        description=request.description,
        mainboard=[{'card': e.card, 'qty': e.qty} for e in request.mainboard],
        sideboard=[{'card': e.card, 'qty': e.qty} for e in request.sideboard],
        format=request.format,
    )

    return DeckResponse(**deck_data)


@router.put("/decks/{deck_id}", response_model=DeckResponse)
async def update_deck(deck_id: str, request: SaveDeckRequest) -> DeckResponse:
    """Update an existing deck."""
    existing = deck_storage.get_deck(deck_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Deck '{deck_id}' not found")

    deck_data = deck_storage.save_deck(
        deck_id=deck_id,
        name=request.name,
        archetype=request.archetype,
        colors=request.colors,
        description=request.description,
        mainboard=[{'card': e.card, 'qty': e.qty} for e in request.mainboard],
        sideboard=[{'card': e.card, 'qty': e.qty} for e in request.sideboard],
        format=request.format,
    )

    return DeckResponse(**deck_data)


@router.delete("/decks/{deck_id}")
async def delete_deck(deck_id: str) -> dict:
    """Delete a deck."""
    if not deck_storage.delete_deck(deck_id):
        raise HTTPException(status_code=404, detail=f"Deck '{deck_id}' not found")

    return {"status": "deleted", "deck_id": deck_id}


# =============================================================================
# Deck Statistics & Validation
# =============================================================================

@router.post("/decks/stats", response_model=DeckStatsResponse)
async def calculate_deck_stats(request: DeckStatsRequest) -> DeckStatsResponse:
    """Calculate statistics for a deck."""
    card_count = 0
    land_count = 0
    creature_count = 0
    spell_count = 0
    total_cmc = 0
    nonland_count = 0

    color_dist: dict[str, int] = {}
    mana_curve: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}  # 6+ bucket
    type_breakdown: dict[str, int] = {}

    for entry in request.mainboard:
        card_def = ALL_CARDS.get(entry.card)
        if not card_def:
            continue

        qty = entry.qty
        card_count += qty
        chars = card_def.characteristics

        # Type counting
        if is_land(card_def):
            land_count += qty
        else:
            nonland_count += qty
            cmc = parse_mana_cost(chars.mana_cost)
            total_cmc += cmc * qty

            # Mana curve
            bucket = min(cmc, 6)
            mana_curve[bucket] = mana_curve.get(bucket, 0) + qty

        if is_creature(card_def):
            creature_count += qty
        elif not is_land(card_def):
            spell_count += qty

        # Color distribution
        for color in chars.colors:
            color_dist[color.name] = color_dist.get(color.name, 0) + qty

        # Type breakdown
        for card_type in chars.types:
            type_breakdown[card_type.name] = type_breakdown.get(card_type.name, 0) + qty

    # Calculate average CMC (excluding lands)
    avg_cmc = total_cmc / nonland_count if nonland_count > 0 else 0.0

    # Validate the deck
    deck = Deck(
        name="",
        archetype="",
        colors=[],
        description="",
        mainboard=[DeckEntry(e.card, e.qty) for e in request.mainboard],
        sideboard=[DeckEntry(e.card, e.qty) for e in request.sideboard],
    )
    is_valid, errors = validate_deck(deck)

    return DeckStatsResponse(
        card_count=card_count,
        land_count=land_count,
        creature_count=creature_count,
        spell_count=spell_count,
        average_cmc=round(avg_cmc, 2),
        color_distribution=color_dist,
        mana_curve={str(k): v for k, v in mana_curve.items()},
        type_breakdown=type_breakdown,
        validation={"is_valid": is_valid, "errors": errors}
    )


@router.post("/decks/validate")
async def validate_deck_endpoint(request: DeckStatsRequest) -> dict:
    """Validate a deck for format legality."""
    deck = Deck(
        name="",
        archetype="",
        colors=[],
        description="",
        mainboard=[DeckEntry(e.card, e.qty) for e in request.mainboard],
        sideboard=[DeckEntry(e.card, e.qty) for e in request.sideboard],
    )
    is_valid, errors = validate_deck(deck)

    # Check for missing cards
    missing_cards = []
    for entry in request.mainboard:
        if entry.card not in ALL_CARDS:
            missing_cards.append(entry.card)

    return {
        "is_valid": is_valid and len(missing_cards) == 0,
        "errors": errors,
        "missing_cards": missing_cards,
    }


# =============================================================================
# Import/Export
# =============================================================================

@router.post("/import", response_model=DeckResponse)
async def import_deck(request: ImportDeckRequest) -> DeckResponse:
    """
    Import a deck from text format.

    Supports formats like:
    - 4 Lightning Bolt
    - 4x Lightning Bolt
    - Lightning Bolt x4
    """
    lines = request.text.strip().split('\n')
    mainboard: list[dict] = []
    sideboard: list[dict] = []
    in_sideboard = False
    deck_name = "Imported Deck"
    colors: set[str] = set()

    for line in lines:
        line = line.strip()
        if not line or line.startswith('//'):
            continue

        # Check for sideboard marker
        if line.lower() in ('sideboard', 'sideboard:', '// sideboard'):
            in_sideboard = True
            continue

        # Check for deck name
        if line.lower().startswith('deck:') or line.lower().startswith('name:'):
            deck_name = line.split(':', 1)[1].strip()
            continue

        # Parse card entry
        # Format: "4 Card Name" or "4x Card Name" or "Card Name x4"
        qty = 1
        card_name = line

        # Try "4 Card Name" or "4x Card Name"
        parts = line.split(' ', 1)
        if len(parts) == 2:
            first = parts[0].rstrip('x')
            if first.isdigit():
                qty = int(first)
                card_name = parts[1]

        # Try "Card Name x4"
        if ' x' in line.lower():
            idx = line.lower().rfind(' x')
            suffix = line[idx+2:].strip()
            if suffix.isdigit():
                qty = int(suffix)
                card_name = line[:idx].strip()

        # Clean up card name
        card_name = card_name.strip()

        # Find card in registry (case-insensitive)
        found_name = None
        for name in ALL_CARDS.keys():
            if name.lower() == card_name.lower():
                found_name = name
                break

        if found_name:
            entry = {'card': found_name, 'qty': qty}
            if in_sideboard:
                sideboard.append(entry)
            else:
                mainboard.append(entry)

            # Track colors
            card_def = ALL_CARDS[found_name]
            for color in card_def.characteristics.colors:
                colors.add(color.name[0])  # W, U, B, R, G

    if not mainboard:
        raise HTTPException(status_code=400, detail="No valid cards found in import text")

    # Save the imported deck
    deck_data = deck_storage.save_deck(
        name=deck_name,
        archetype="Imported",
        colors=list(colors),
        description="Imported deck",
        mainboard=mainboard,
        sideboard=sideboard,
        format=request.format,
    )

    return DeckResponse(**deck_data)


@router.get("/export/{deck_id}", response_model=ExportDeckResponse)
async def export_deck(deck_id: str) -> ExportDeckResponse:
    """Export a deck to text format."""
    deck_data = deck_storage.get_deck(deck_id)
    if not deck_data:
        raise HTTPException(status_code=404, detail=f"Deck '{deck_id}' not found")

    lines = [f"// {deck_data['name']}"]
    lines.append(f"// Format: {deck_data.get('format', 'Standard')}")
    lines.append("")

    # Mainboard
    for entry in deck_data.get('mainboard', []):
        lines.append(f"{entry['qty']} {entry['card']}")

    # Sideboard
    if deck_data.get('sideboard'):
        lines.append("")
        lines.append("Sideboard")
        for entry in deck_data['sideboard']:
            lines.append(f"{entry['qty']} {entry['card']}")

    return ExportDeckResponse(
        text='\n'.join(lines),
        deck_name=deck_data['name']
    )


# =============================================================================
# LLM Deck Building
# =============================================================================

class LLMBuildRequest(BaseModel):
    """Request for LLM to build a deck."""
    prompt: str = Field(..., min_length=5, description="What kind of deck to build")
    colors: Optional[list[str]] = Field(None, description="Color restriction (W, U, B, R, G)")
    format: str = Field(default="Standard")


class LLMSuggestRequest(BaseModel):
    """Request for LLM deck suggestions."""
    deck_id: str = Field(..., description="ID of the deck to improve")
    prompt: str = Field(..., min_length=5, description="What improvements to make")


class LLMBuildResponse(BaseModel):
    """Response from LLM deck building."""
    success: bool
    deck: Optional[dict] = None
    error: Optional[str] = None


class LLMSuggestResponse(BaseModel):
    """Response from LLM suggestions."""
    success: bool
    suggestions: Optional[dict] = None
    error: Optional[str] = None


@router.post("/llm/build", response_model=LLMBuildResponse)
async def llm_build_deck(request: LLMBuildRequest) -> LLMBuildResponse:
    """
    Use LLM to build a complete deck from a prompt.

    Requires Ollama to be running with a compatible model.
    """
    from ..services.llm_deckbuilder import llm_deckbuilder

    result = await llm_deckbuilder.build_deck(
        prompt=request.prompt,
        colors=request.colors,
        format=request.format
    )

    return LLMBuildResponse(
        success=result.get("success", False),
        deck=result.get("deck"),
        error=result.get("error")
    )


@router.post("/llm/suggest", response_model=LLMSuggestResponse)
async def llm_suggest_cards(request: LLMSuggestRequest) -> LLMSuggestResponse:
    """
    Use LLM to suggest improvements for an existing deck.

    Requires Ollama to be running with a compatible model.
    """
    from ..services.llm_deckbuilder import llm_deckbuilder

    # Load the deck
    deck_data = deck_storage.get_deck(request.deck_id)
    if not deck_data:
        return LLMSuggestResponse(
            success=False,
            error=f"Deck '{request.deck_id}' not found"
        )

    result = await llm_deckbuilder.suggest_cards(
        deck_name=deck_data['name'],
        archetype=deck_data['archetype'],
        colors=deck_data['colors'],
        mainboard=deck_data['mainboard'],
        sideboard=deck_data.get('sideboard', []),
        prompt=request.prompt
    )

    return LLMSuggestResponse(
        success=result.get("success", False),
        suggestions=result.get("suggestions"),
        error=result.get("error")
    )


@router.get("/llm/status")
async def llm_status() -> dict:
    """Check if LLM is available for deck building."""
    from ..services.llm_deckbuilder import llm_deckbuilder

    return {
        "available": llm_deckbuilder.is_available,
        "provider": llm_deckbuilder.provider.model_name if llm_deckbuilder.is_available else None,
        "message": "LLM deck building ready" if llm_deckbuilder.is_available else "Ollama not available. Run: ollama serve && ollama pull qwen2.5:7b"
    }
