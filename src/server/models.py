"""
Pydantic Models for Hyperdraft API

Data transfer objects for the REST API and WebSocket communication.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
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
    ULTRA = "ultra"


class BotBrain(str, Enum):
    """Controller type for bot players."""
    HEURISTIC = "heuristic"      # Built-in heuristic AIEngine
    OPENAI = "openai"            # OpenAI API models (requires OPENAI_API_KEY)
    OLLAMA = "ollama"            # Local Ollama models (requires Ollama running)
    CLAUDE_CODE = "claude_code"  # `claude -p` subprocess (uses OAuth, no API key)


class ActionType(str, Enum):
    """Player action types."""
    PASS = "PASS"
    CAST_SPELL = "CAST_SPELL"
    ACTIVATE_ABILITY = "ACTIVATE_ABILITY"
    PLAY_LAND = "PLAY_LAND"
    SPECIAL_ACTION = "SPECIAL_ACTION"
    DECLARE_ATTACKERS = "DECLARE_ATTACKERS"
    DECLARE_BLOCKERS = "DECLARE_BLOCKERS"
    # Hearthstone action types
    HS_PLAY_CARD = "HS_PLAY_CARD"
    HS_ATTUNE_CARD = "HS_ATTUNE_CARD"
    HS_ATTACK = "HS_ATTACK"
    HS_HERO_POWER = "HS_HERO_POWER"
    HS_END_TURN = "HS_END_TURN"
    # Pokemon action types
    PKM_PLAY_CARD = "PKM_PLAY_CARD"
    PKM_ATTACH_ENERGY = "PKM_ATTACH_ENERGY"
    PKM_ATTACK = "PKM_ATTACK"
    PKM_RETREAT = "PKM_RETREAT"
    PKM_EVOLVE = "PKM_EVOLVE"
    PKM_USE_ABILITY = "PKM_USE_ABILITY"
    PKM_END_TURN = "PKM_END_TURN"
    # Yu-Gi-Oh! action types
    YGO_NORMAL_SUMMON = "YGO_NORMAL_SUMMON"
    YGO_SET_MONSTER = "YGO_SET_MONSTER"
    YGO_FLIP_SUMMON = "YGO_FLIP_SUMMON"
    YGO_CHANGE_POSITION = "YGO_CHANGE_POSITION"
    YGO_ACTIVATE = "YGO_ACTIVATE"
    YGO_SET_SPELL_TRAP = "YGO_SET_SPELL_TRAP"
    YGO_DECLARE_ATTACK = "YGO_DECLARE_ATTACK"
    YGO_DIRECT_ATTACK = "YGO_DIRECT_ATTACK"
    YGO_CHAIN_RESPONSE = "YGO_CHAIN_RESPONSE"
    YGO_CHAIN_PASS = "YGO_CHAIN_PASS"
    YGO_END_TURN = "YGO_END_TURN"
    YGO_SPECIAL_SUMMON = "YGO_SPECIAL_SUMMON"
    YGO_END_PHASE = "YGO_END_PHASE"
    # Minecraft TCG action types
    MC_PLAY_CARD = "MC_PLAY_CARD"
    MC_ASSIGN_WORKER = "MC_ASSIGN_WORKER"
    MC_AVATAR_ACTION = "MC_AVATAR_ACTION"
    MC_EXPLORE_BIOME = "MC_EXPLORE_BIOME"
    MC_DECLARE_ATTACKERS = "MC_DECLARE_ATTACKERS"
    MC_DECLARE_BLOCKERS = "MC_DECLARE_BLOCKERS"
    MC_END_TURN = "MC_END_TURN"
    MC_MULLIGAN_DECISION = "MC_MULLIGAN_DECISION"
    # Finance TCG action types
    FIN_PLAY_CARD = "FIN_PLAY_CARD"
    FIN_DECLARE_ATTACKERS = "FIN_DECLARE_ATTACKERS"
    FIN_DECLARE_BLOCKERS = "FIN_DECLARE_BLOCKERS"
    FIN_ACTIVATE_ABILITY = "FIN_ACTIVATE_ABILITY"
    FIN_END_PHASE = "FIN_END_PHASE"
    FIN_END_TURN = "FIN_END_TURN"
    FIN_PLAY_RESPONSE = "FIN_PLAY_RESPONSE"
    FIN_PASS_RESPONSE = "FIN_PASS_RESPONSE"
    # Depths: Submarine Fleet action types
    DEPTHS_DEPLOY_VESSEL = "DEPTHS_DEPLOY_VESSEL"
    DEPTHS_PLAY_CARD = "DEPTHS_PLAY_CARD"         # frontend alias for DEPLOY_VESSEL
    DEPTHS_DIVE = "DEPTHS_DIVE"
    DEPTHS_SURFACE_VESSEL = "DEPTHS_SURFACE_VESSEL"
    DEPTHS_SURFACE = "DEPTHS_SURFACE"              # frontend alias for SURFACE_VESSEL
    DEPTHS_ATTACH = "DEPTHS_ATTACH"
    DEPTHS_CAST_SPELL = "DEPTHS_CAST_SPELL"
    DEPTHS_LAY_MINE = "DEPTHS_LAY_MINE"
    DEPTHS_ACTIVATE_ABILITY = "DEPTHS_ACTIVATE_ABILITY"
    DEPTHS_DECLARE_ATTACKERS = "DEPTHS_DECLARE_ATTACKERS"
    DEPTHS_DETECT = "DEPTHS_DETECT"
    DEPTHS_DECLARE_INTERCEPTORS = "DEPTHS_DECLARE_INTERCEPTORS"
    DEPTHS_END_TURN = "DEPTHS_END_TURN"
    # SCP Containment TCG action types
    SCP_OPEN_DOSSIER = "SCP_OPEN_DOSSIER"
    SCP_REVEAL_DOSSIER = "SCP_REVEAL_DOSSIER"
    SCP_RESEARCH = "SCP_RESEARCH"
    SCP_CONTAIN = "SCP_CONTAIN"
    SCP_SUPPRESS = "SCP_SUPPRESS"
    SCP_SPEND_ETHICS = "SCP_SPEND_ETHICS"
    SCP_SHIFT_MOOD = "SCP_SHIFT_MOOD"
    SCP_CROSS_CONTAIN = "SCP_CROSS_CONTAIN"
    SCP_MEMORY_HOLE = "SCP_MEMORY_HOLE"
    SCP_APPLY_PROTOCOL = "SCP_APPLY_PROTOCOL"
    SCP_RESOLVE_INCIDENT = "SCP_RESOLVE_INCIDENT"
    SCP_END_TURN = "SCP_END_TURN"
    # Cats (trick-taking + pile-building) action types
    CATS_PLAY_CARD = "CATS_PLAY_CARD"
    CATS_CHOOSE_PILE = "CATS_CHOOSE_PILE"
    CATS_KNOCK_OVER = "CATS_KNOCK_OVER"
    # Clankers (multi-part robot assembly) action types
    CLANKERS_PLAY_CARD = "CLANKERS_PLAY_CARD"
    CLANKERS_ATTACH_PART = "CLANKERS_ATTACH_PART"
    CLANKERS_ACTIVATE_ABILITY = "CLANKERS_ACTIVATE_ABILITY"
    CLANKERS_DECLARE_ATTACKERS = "CLANKERS_DECLARE_ATTACKERS"
    CLANKERS_DECLARE_BLOCKERS = "CLANKERS_DECLARE_BLOCKERS"
    CLANKERS_REFILL_DECISION = "CLANKERS_REFILL_DECISION"
    CLANKERS_END_PHASE = "CLANKERS_END_PHASE"


class ChoiceType(str, Enum):
    """Player choice types for modal spells, scry, etc."""
    MODAL = "modal"
    TARGET = "target"
    SCRY = "scry"
    SURVEIL = "surveil"
    ORDER = "order"
    DISCARD = "discard"
    SACRIFICE = "sacrifice"
    MAY = "may"
    CUSTOM = "custom"


# =============================================================================
# Request Models
# =============================================================================

class CreateMatchRequest(BaseModel):
    """Request to create a new match."""
    mode: MatchMode = MatchMode.HUMAN_VS_BOT
    game_mode: Literal["mtg", "hearthstone", "pokemon", "yugioh", "minecraft", "finance", "depths", "scp", "cats", "clankers"] = Field(
        default="mtg",
        description="Rules engine: 'mtg', 'hearthstone', 'pokemon', 'yugioh', 'minecraft', 'finance', 'depths', 'scp', 'cats', or 'clankers'"
    )
    variant: Optional[str] = Field(default=None, description="Game variant (e.g. 'stormrift') — installs heroes/decks/modifiers")
    hero_class: Optional[str] = Field(default=None, description="Hero class for variant (e.g. 'Pyromancer', 'Cryomancer')")
    ultra_agent: Optional[Literal["claude", "codex"]] = Field(
        default=None,
        description="External agent runner for human-vs-bot Ultra matches"
    )
    ultra_model: Optional[str] = Field(default=None, description="Optional model passed to the external Ultra agent")
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
    cell: Optional[dict[str, int]] = Field(default=None, description="Minecraft 3x3 grid cell {x,y}")
    biome_index: Optional[int] = Field(default=None, description="Minecraft biome slot index")
    action_kind: Optional[str] = Field(default=None, description="Minecraft avatar action kind")
    target_column: Optional[int] = Field(default=None, description="Minecraft column index for column-based attacks")
    keep: Optional[bool] = Field(default=None, description="Mulligan decision: True to keep current hand, False to mulligan")
    # Depths: Submarine Fleet action fields
    depth_band: Optional[str] = Field(default=None, description="Depth band for deploy/mine (SURFACE/PERISCOPE/MID/DEEP/CRUSH)")
    vessel_id: Optional[str] = Field(default=None, description="Vessel object ID for dive/surface actions")
    interceptors: list[dict] = Field(default_factory=list, description="Interceptor pairings {attacker_id, interceptor_id}")
    detect_targets: list[str] = Field(default_factory=list, description="Vessel IDs to detect via sonar")
    # SCP action fields
    fast_track: bool = Field(default=False, description="SCP: bypass dossier paperwork by spending secrecy")
    sealed: bool = Field(default=False, description="SCP: open anomaly as a sealed dossier")
    anomaly_id: Optional[str] = Field(default=None, description="SCP anomaly object ID")
    staff_ids: list[str] = Field(default_factory=list, description="SCP personnel IDs assigned to an action")
    contained_id: Optional[str] = Field(default=None, description="SCP contained anomaly ID for cross-containment")
    active_id: Optional[str] = Field(default=None, description="SCP active anomaly ID for cross-containment")
    mood: Optional[str] = Field(default=None, description="SCP anomaly mood")
    protocol: Optional[str] = Field(default=None, description="SCP special containment protocol")
    index: Optional[int] = Field(default=None, description="SCP incident index")
    amount: Optional[int] = Field(default=None, description="SCP numeric action amount")
    # Cats action fields
    pile_name: Optional[str] = Field(default=None, description="Cats pile name for CATS_CHOOSE_PILE (pile_territory/pile_nap/pile_snack)")
    # Clankers action fields
    target_chassis_id: Optional[str] = Field(default=None, description="Clankers chassis id for weapon/add-on attach")
    part_obj_id: Optional[str] = Field(default=None, description="Clankers floor part id for CLANKERS_ATTACH_PART")
    source_obj_id: Optional[str] = Field(default=None, description="Clankers ability source id for CLANKERS_ACTIVATE_ABILITY")
    ability_index: Optional[int] = Field(default=None, description="Clankers activated-ability index")
    attacker_ids: list[str] = Field(default_factory=list, description="Clankers attacker chassis/part ids")
    blocker_pairs: dict[str, str] = Field(default_factory=dict, description="Clankers blocker mapping {attacker_id: blocker_id}")
    refill_decision: Optional[bool] = Field(default=None, description="Clankers Allocate-phase may-refill choice (True=take, False=decline)")
    phase: Optional[str] = Field(default=None, description="Clankers phase label for CLANKERS_END_PHASE (assemble/reassemble/combat)")
    # Ultra-agent telemetry — when the LLM pilot sends a structured rationale
    # along with its action POST, we capture it into the per-match decisions
    # JSONL. Optional; absent for human / heuristic-AI submissions.
    reasoning: Optional[str] = Field(default=None, description="LLM-pilot rationale for this action (Ultra only)")


class StartBotGameRequest(BaseModel):
    """Request to start a bot vs bot game."""
    mode: str = Field(default="mtg", description="Game mode: 'mtg', 'hearthstone', 'pokemon', or 'yugioh'")
    bot1_deck: list[str] = Field(default_factory=list)
    bot2_deck: list[str] = Field(default_factory=list)
    bot1_deck_id: Optional[str] = Field(default=None, description="Deck ID from /match/decks (e.g., mono_red_netdeck)")
    bot2_deck_id: Optional[str] = Field(default=None, description="Deck ID from /match/decks (e.g., azorius_simulacrum_netdeck)")
    bot1_difficulty: AIDifficulty = AIDifficulty.MEDIUM
    bot2_difficulty: AIDifficulty = AIDifficulty.MEDIUM
    bot1_brain: BotBrain = BotBrain.HEURISTIC
    bot2_brain: BotBrain = BotBrain.HEURISTIC
    bot1_model: Optional[str] = Field(default=None, description="Model id (for OpenAI/Ollama/Claude Code brains)")
    bot2_model: Optional[str] = Field(default=None, description="Model id (for OpenAI/Ollama/Claude Code brains)")
    bot1_name: Optional[str] = Field(default=None, description="Override display name for bot 1")
    bot2_name: Optional[str] = Field(default=None, description="Override display name for bot 2")
    bot1_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    bot2_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    record_prompts: bool = Field(default=False, description="Store LLM prompts in replay frames (debug)")
    max_replay_frames: int = Field(default=5000, ge=100, le=50000, description="Cap replay frames to avoid OOM")
    delay_ms: int = Field(default=1000, ge=0, le=5000, description="Delay between actions in ms")


class SubmitChoiceRequest(BaseModel):
    """Request to submit a player choice (modal, scry, target, etc.)."""
    choice_id: str = Field(..., description="ID of the pending choice being answered")
    player_id: str = Field(..., description="ID of the player submitting the choice")
    selected: list[Any] = Field(default_factory=list, description="Selected options")


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
    domain: Optional[str] = Field(default=None, description="Card domain / cardspace (e.g., MTG, TMH, TLAC)")
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
    keywords: list[str] = Field(default_factory=list)
    # Cosmetic — true if this card instance is "foil" (holographic rendering)
    foil: bool = False
    # Hearthstone-specific state
    divine_shield: bool = False
    stealth: bool = False
    windfury: bool = False
    frozen: bool = False
    summoning_sickness: bool = False
    attacks_this_turn: int = 0
    # Pokemon-specific state
    hp: Optional[int] = None
    damage_counters: int = 0
    pokemon_type: Optional[str] = None
    evolution_stage: Optional[str] = None
    attacks: list[dict] = Field(default_factory=list)
    ability_name: Optional[str] = None
    ability_text: Optional[str] = None
    weakness_type: Optional[str] = None
    resistance_type: Optional[str] = None
    retreat_cost: int = 0
    attached_energy: list[str] = Field(default_factory=list)
    attached_tool_name: Optional[str] = None
    status_conditions: list[str] = Field(default_factory=list)
    is_ex: bool = False
    prize_count: int = 1
    image_url: Optional[str] = None
    # Yu-Gi-Oh! state
    level: Optional[int] = None
    rank: Optional[int] = None
    link_rating: Optional[int] = None
    atk: Optional[int] = None
    def_val: Optional[int] = None
    attribute: Optional[str] = None
    ygo_monster_type: Optional[str] = None
    ygo_spell_type: Optional[str] = None
    ygo_trap_type: Optional[str] = None
    ygo_position: Optional[str] = None
    face_down: bool = False
    overlay_units: int = 0
    is_tuner: bool = False
    # Minecraft-specific state/metadata
    mc_cost: dict[str, int] = Field(default_factory=dict)
    mc_grid_x: Optional[int] = None
    mc_grid_y: Optional[int] = None
    mc_gear_slot: Optional[str] = None
    mc_exhausted: bool = False
    mc_keywords: list[str] = Field(default_factory=list)
    # Depths: Submarine Fleet card state
    depth_band: Optional[str] = None
    detected: bool = False
    is_flagship: bool = False
    depths_cost: dict = Field(default_factory=dict)
    # SCP Containment TCG state/metadata
    scp_red_tape: int = 0
    scp_clearance: int = 0
    scp_containment: int = 0
    scp_curiosity: int = 0
    scp_hazard: int = 0
    scp_skills: dict[str, int] = Field(default_factory=dict)
    scp_bonus: dict[str, int] = Field(default_factory=dict)
    scp_status: Optional[str] = None
    scp_paperwork: int = 0
    scp_exhausted: bool = False
    scp_researched: int = 0
    scp_suppressed: int = 0
    scp_mood: Optional[str] = None
    scp_bound_to: Optional[str] = None
    scp_protocols: list[str] = Field(default_factory=list)
    scp_public_tags: list[str] = Field(default_factory=list)


class StackItemData(BaseModel):
    """Stack item data for API responses."""
    id: str
    type: str
    source_id: str
    source_name: str
    controller: str
    # Description (used for triggered abilities; spells leave it blank).
    description: str = ""


class PendingTriggerData(BaseModel):
    """A queued triggered ability waiting to be put on the stack.

    These accumulate in ``state.pending_triggers`` between the triggering
    event and the next priority window. The frontend uses this list to show
    the player which triggers are about to go on the stack so they can
    optionally re-order their own triggers (CR 603.3b).
    """
    id: str
    controller: str
    source_id: str
    source_name: str
    description: str = ""


class LegalActionData(BaseModel):
    """Legal action data for API responses."""
    type: str
    card_id: Optional[str] = None
    ability_id: Optional[str] = None
    source_id: Optional[str] = None
    description: str = ""
    requires_targets: bool = False
    requires_mana: bool = False


class PendingChoiceData(BaseModel):
    """Pending choice data for API responses."""
    id: str
    choice_type: str
    player: str
    prompt: str
    options: list[Any] = Field(default_factory=list)
    source_id: str
    min_choices: int = 1
    max_choices: int = 1
    # Optional rendering hint from the engine. ``"overlay"`` tells the
    # frontend to render this choice as click-to-target board highlights
    # instead of a modal panel (Phase 5b: MTG cast-time targets). Absent
    # or ``"modal"`` keeps the legacy modal rendering used by every other
    # engine that emits a PendingChoice.
    interaction_mode: Optional[str] = None


class PendingChoiceWaitingData(BaseModel):
    """Simplified pending choice data when another player is making a choice."""
    waiting_for: str
    choice_type: str


class PlayerData(BaseModel):
    """Player data for API responses."""
    id: str
    name: str
    life: int
    has_lost: bool = False
    hand_size: int = 0
    library_size: int = 0
    # Hearthstone fields
    mana_crystals: int = 0
    mana_crystals_available: int = 0
    armor: int = 0
    hero_id: Optional[str] = None
    weapon_attack: int = 0
    weapon_durability: int = 0
    fatigue_damage: int = 0
    hero_power_used: bool = False
    hero_power_id: Optional[str] = None
    hero_power_name: Optional[str] = None
    hero_power_cost: int = 2
    hero_power_text: Optional[str] = None
    max_life: int = 30
    # Variant-specific resource counters (e.g. tri-color shards in Frierenrift)
    variant_resources: dict[str, int] = Field(default_factory=dict)
    # Pokemon fields
    prizes_remaining: int = 0
    energy_attached_this_turn: bool = False
    supporter_played_this_turn: bool = False
    # Yu-Gi-Oh! fields
    lp: int = 0
    normal_summon_used: bool = False
    # Minecraft fields
    mc_materials: dict[str, int] = Field(default_factory=dict)
    mc_avatar_gear: dict[str, Optional[str]] = Field(default_factory=dict)
    mc_avatar_action_used: bool = False
    # Depths: Submarine Fleet fields
    tc: int = 0
    sc: int = 0
    tc_max: int = 0
    sc_max: int = 0
    flagship_id: Optional[str] = None


class CombatData(BaseModel):
    """Combat state data for API responses."""
    attackers: list[dict] = Field(default_factory=list)
    blockers: list[dict] = Field(default_factory=list)
    blocked_attackers: list[str] = Field(default_factory=list)


class GameLogEntry(BaseModel):
    """Single game log entry for the event log."""
    turn: int = 0
    text: str = ""
    event_type: str = ""
    player: Optional[str] = None
    timestamp: float = 0.0


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
    # Triggered abilities that have fired but not yet been put on the stack
    # (drained on the next priority pass). Surfaced to the client so the
    # active player can preview the queue before their own triggers go on
    # the stack (CR 603.3b — active player orders their simultaneous triggers).
    pending_triggers: list[PendingTriggerData] = Field(default_factory=list)
    hand: list[CardData] = Field(default_factory=list)
    graveyard: dict[str, list[CardData]] = Field(default_factory=dict)
    legal_actions: list[LegalActionData] = Field(default_factory=list)
    combat: Optional[CombatData] = None
    is_game_over: bool = False
    winner: Optional[str] = None
    pending_choice: Optional[PendingChoiceData] = None  # Choice for this player
    waiting_for_choice: Optional[PendingChoiceWaitingData] = None  # Another player's choice
    game_mode: str = "mtg"  # "mtg", "hearthstone", "pokemon", or "yugioh"
    variant: Optional[str] = None  # Game variant (e.g. "stormrift")
    max_hand_size: int = 7  # 7 for MTG, 10 for Hearthstone
    # Pokemon zones
    active_pokemon: dict[str, Optional[CardData]] = Field(default_factory=dict)
    bench: dict[str, list[CardData]] = Field(default_factory=dict)
    stadium_card: Optional[CardData] = None
    # Yu-Gi-Oh! zones
    monster_zones: dict[str, list[Optional[CardData]]] = Field(default_factory=dict)
    spell_trap_zones: dict[str, list[Optional[CardData]]] = Field(default_factory=dict)
    field_spells: dict[str, Optional[CardData]] = Field(default_factory=dict)
    banished: dict[str, list[CardData]] = Field(default_factory=dict)
    extra_deck_sizes: dict[str, int] = Field(default_factory=dict)
    ygo_phase: Optional[str] = None
    chain_links: list[dict] = Field(default_factory=list)
    # Minecraft zones/state
    minecraft_day_phase: str = "day"
    minecraft_biomes: dict[str, list[dict]] = Field(default_factory=dict)
    minecraft_grid: dict[str, list[list[Optional[CardData]]]] = Field(default_factory=dict)
    minecraft_combat: dict = Field(default_factory=dict)
    minecraft_exposed_targets: dict[str, list[str]] = Field(default_factory=dict)
    # Mulligan prompt state. Non-empty only while a Minecraft player is being asked to keep
    # or mulligan. Keyed by player_id; absent when no decision is pending.
    # Shape: { mulligan_count: int, hand_size_after_keep: int, cost_for_next: int }
    minecraft_mulligan_pending: dict[str, dict] = Field(default_factory=dict)
    # Finance TCG state
    finance_phase: Optional[str] = None
    finance_dark_pool: Optional[str] = None
    finance_turn_data: dict = Field(default_factory=dict)
    # MTG-style priority stack: list of {card_id, controller, is_response,
    # countered, name} dicts in LIFO order (last = top).
    finance_stack: list[dict] = Field(default_factory=list)
    # When the engine is awaiting a response from a player, this carries:
    # { prompted_player_id, top_card_id, top_card_name, allowed_card_ids: [..] }.
    # None when no priority window is open.
    finance_pending_response: Optional[dict] = None
    # Depths: Submarine Fleet state
    depths_phase: Optional[str] = None
    depths_combat: dict = Field(default_factory=dict)
    # SCP Containment TCG state
    scp_sites: dict[str, dict] = Field(default_factory=dict)
    scp_anomalies: dict[str, list[CardData]] = Field(default_factory=dict)
    scp_contained: dict[str, list[CardData]] = Field(default_factory=dict)
    scp_personnel: dict[str, list[CardData]] = Field(default_factory=dict)
    scp_facilities: dict[str, list[CardData]] = Field(default_factory=dict)
    scp_mandates: dict[str, list[CardData]] = Field(default_factory=dict)
    scp_incidents: dict[str, list[dict]] = Field(default_factory=dict)
    scp_assignment_slots: dict[str, int] = Field(default_factory=dict)
    # Cats engine state — trick-taking + pile-building, symmetric per round.
    # The frontend reads `cats` as a single nested object so the cats.tsx page
    # can project it through useCatsGame.ts without flattening into top-level
    # fields used by other engines.
    cats: Optional[dict] = Field(default=None, description="Nested cats engine state (phase/trick/piles/scores)")
    # Clankers engine state — multi-part assembly battler. The frontend reads
    # `clankers` as a single nested object so its viewer can project workshop /
    # compute / scrap / floor data without flattening into top-level fields.
    clankers: Optional[dict] = Field(default=None, description="Nested clankers engine state (phases/floor/workshop/compute/scrap)")
    # Game log
    game_log: list[GameLogEntry] = Field(default_factory=list)


class ChoiceResultResponse(BaseModel):
    """Response after submitting a choice."""
    success: bool
    message: str = ""
    new_state: Optional[GameStateResponse] = None
    events: list[dict] = Field(default_factory=list)


class ActionResultResponse(BaseModel):
    """Response after processing an action."""
    success: bool
    message: str = ""
    new_state: Optional[GameStateResponse] = None
    events: list[dict] = Field(default_factory=list)


class CardDefinitionData(BaseModel):
    """Card definition for the card database (multi-game)."""
    name: str
    game: str = Field(default="mtg", description="Game id: mtg, minecraft, pokemon, yugioh, hearthstone")
    domain: Optional[str] = Field(default=None, description="Card domain / cardspace (e.g., MTG, TMH, TLAC)")
    mana_cost: Optional[str] = None
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    power: Optional[int] = None
    toughness: Optional[int] = None
    text: str = ""
    colors: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    extras: dict = Field(default_factory=dict, description="Game-specific fields (energy_type for Pokemon, mc_cost for Minecraft, etc.)")


class CardListResponse(BaseModel):
    """Response with list of available cards."""
    cards: list[CardDefinitionData]
    total: int


class BotGameResponse(BaseModel):
    """Response after starting a bot game."""
    game_id: str
    status: str = "running"


class BotGameStatus(BaseModel):
    """Per-game row returned by /bot-game/list (and /bot-game/{id}/status).

    The original shape was ``{game_id, status, turn, winner}``. The WatchLive
    lobby (HD-ART-06) wants an engine code, player-seat labels (brain +
    difficulty), and a deck archetype blurb — so consumers like the
    frontend's mock-fallback can drop their padding and render the real
    running matches. All enrichment fields are Optional so legacy consumers
    keep working.
    """
    game_id: str
    status: str  # 'running' | 'finished'
    turn: int
    winner: Optional[str] = None
    # Engine id matching the GameModeId on the frontend ('mtg', 'depths',
    # 'cats', etc). Optional only because completed_replays predate the
    # enrichment and may not carry a mode hint.
    game_mode: Optional[str] = None
    # Seat labels formatted as "<brain_or_name> · <difficulty>" — e.g.
    # "Heuristic · medium", "Claude · ultra", "GPT-5.3 · ultra". Brain takes
    # priority over the per-seat display name when both are set.
    player1_label: Optional[str] = None
    player2_label: Optional[str] = None
    # Short archetype/deck blurb (title-cased). For decks resolved by ID we
    # de-slug the ID; explicit-list decks have no blurb. None for game modes
    # without an obvious deck identity.
    deck_blurb: Optional[str] = None


class BotGameListResponse(BaseModel):
    """Envelope returned by /bot-game/list."""
    games: list[BotGameStatus]
    total: int


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
