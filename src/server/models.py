"""
Pydantic Models for Hyperdraft API

Data transfer objects for the REST API and WebSocket communication.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class MatchMode(str, Enum):
    """Match mode types."""
    HUMAN_VS_BOT = "human_vs_bot"
    BOT_VS_BOT = "bot_vs_bot"
    HUMAN_VS_HUMAN = "human_vs_human"


class AIDifficulty(str, Enum):
    """AI difficulty levels."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ActionType(str, Enum):
    """Player action types."""
    PASS = "PASS"
    CAST_SPELL = "CAST_SPELL"
    ACTIVATE_ABILITY = "ACTIVATE_ABILITY"
    PLAY_LAND = "PLAY_LAND"
    SPECIAL_ACTION = "SPECIAL_ACTION"
    DECLARE_ATTACKERS = "DECLARE_ATTACKERS"
    DECLARE_BLOCKERS = "DECLARE_BLOCKERS"


# =============================================================================
# Request Models
# =============================================================================

class CreateMatchRequest(BaseModel):
    """Request to create a new match."""
    mode: MatchMode = MatchMode.HUMAN_VS_BOT
    player_deck: list[str] = Field(default_factory=list, description="List of card names (custom deck)")
    player_deck_id: Optional[str] = Field(default=None, description="Standard deck ID (e.g., 'mono_red_aggro')")
    player_name: str = Field(default="Player", description="Human player name")
    ai_difficulty: AIDifficulty = AIDifficulty.MEDIUM
    ai_deck: list[str] = Field(default_factory=list, description="AI deck card names (optional)")
    ai_deck_id: Optional[str] = Field(default=None, description="Standard deck ID for AI")


class PlayerActionRequest(BaseModel):
    """Request to perform a player action."""
    action_type: ActionType
    player_id: str
    card_id: Optional[str] = None
    targets: list[list[str]] = Field(default_factory=list)
    x_value: int = 0
    ability_id: Optional[str] = None
    source_id: Optional[str] = None
    attackers: list[dict] = Field(default_factory=list, description="Attack declarations")
    blockers: list[dict] = Field(default_factory=list, description="Block declarations")


class StartBotGameRequest(BaseModel):
    """Request to start a bot vs bot game."""
    bot1_deck: list[str] = Field(default_factory=list)
    bot2_deck: list[str] = Field(default_factory=list)
    bot1_difficulty: AIDifficulty = AIDifficulty.MEDIUM
    bot2_difficulty: AIDifficulty = AIDifficulty.MEDIUM
    delay_ms: int = Field(default=1000, ge=100, le=5000, description="Delay between actions in ms")


# =============================================================================
# Response Models
# =============================================================================

class CreateMatchResponse(BaseModel):
    """Response after creating a match."""
    match_id: str
    player_id: str
    opponent_id: str
    status: str = "created"


class CardData(BaseModel):
    """Card data for API responses."""
    id: str
    name: str
    mana_cost: Optional[str] = None
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    power: Optional[int] = None
    toughness: Optional[int] = None
    text: str = ""
    tapped: bool = False
    counters: dict[str, int] = Field(default_factory=dict)
    damage: int = 0
    controller: Optional[str] = None
    owner: Optional[str] = None


class StackItemData(BaseModel):
    """Stack item data for API responses."""
    id: str
    type: str
    source_id: str
    source_name: str
    controller: str


class LegalActionData(BaseModel):
    """Legal action data for API responses."""
    type: str
    card_id: Optional[str] = None
    ability_id: Optional[str] = None
    source_id: Optional[str] = None
    description: str = ""
    requires_targets: bool = False
    requires_mana: bool = False


class PlayerData(BaseModel):
    """Player data for API responses."""
    id: str
    name: str
    life: int
    has_lost: bool = False
    hand_size: int = 0
    library_size: int = 0


class CombatData(BaseModel):
    """Combat state data for API responses."""
    attackers: list[dict] = Field(default_factory=list)
    blockers: list[dict] = Field(default_factory=list)
    blocked_attackers: list[str] = Field(default_factory=list)


class GameStateResponse(BaseModel):
    """Complete game state for a player."""
    match_id: str
    turn_number: int
    phase: str
    step: str
    active_player: Optional[str] = None
    priority_player: Optional[str] = None
    players: dict[str, PlayerData]
    battlefield: list[CardData] = Field(default_factory=list)
    stack: list[StackItemData] = Field(default_factory=list)
    hand: list[CardData] = Field(default_factory=list)
    graveyard: dict[str, list[CardData]] = Field(default_factory=dict)
    legal_actions: list[LegalActionData] = Field(default_factory=list)
    combat: Optional[CombatData] = None
    is_game_over: bool = False
    winner: Optional[str] = None


class ActionResultResponse(BaseModel):
    """Response after processing an action."""
    success: bool
    message: str = ""
    new_state: Optional[GameStateResponse] = None
    events: list[dict] = Field(default_factory=list)


class CardDefinitionData(BaseModel):
    """Card definition for the card database."""
    name: str
    mana_cost: Optional[str] = None
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    power: Optional[int] = None
    toughness: Optional[int] = None
    text: str = ""
    colors: list[str] = Field(default_factory=list)


class CardListResponse(BaseModel):
    """Response with list of available cards."""
    cards: list[CardDefinitionData]
    total: int


class BotGameResponse(BaseModel):
    """Response after starting a bot game."""
    game_id: str
    status: str = "running"


class ReplayFrame(BaseModel):
    """Single frame of a game replay."""
    turn: int
    phase: str
    step: str
    action: Optional[dict] = None
    state: dict
    timestamp: float


class ReplayResponse(BaseModel):
    """Full replay data for a completed game."""
    game_id: str
    winner: Optional[str] = None
    total_turns: int
    frames: list[ReplayFrame]


# =============================================================================
# WebSocket Event Models
# =============================================================================

class WSJoinMatch(BaseModel):
    """WebSocket event to join a match."""
    match_id: str
    player_id: str


class WSGameState(BaseModel):
    """WebSocket event with full game state."""
    event: str = "game_state"
    data: GameStateResponse


class WSGameUpdate(BaseModel):
    """WebSocket event with incremental update."""
    event: str = "game_update"
    match_id: str
    update_type: str
    data: dict


class WSPlayerAction(BaseModel):
    """WebSocket event for player action."""
    event: str = "player_action"
    match_id: str
    action: PlayerActionRequest


class WSError(BaseModel):
    """WebSocket error event."""
    event: str = "error"
    message: str
    code: Optional[str] = None
