/**
 * Game State Types
 *
 * TypeScript types matching the API models.
 */

// Enums
export type MatchMode = 'human_vs_bot' | 'bot_vs_bot' | 'human_vs_human';
export type AIDifficulty = 'easy' | 'medium' | 'hard' | 'ultra';

export type ActionType =
  | 'PASS'
  | 'CAST_SPELL'
  | 'ACTIVATE_ABILITY'
  | 'PLAY_LAND'
  | 'SPECIAL_ACTION'
  | 'DECLARE_ATTACKERS'
  | 'DECLARE_BLOCKERS';

export type Phase =
  | 'BEGINNING'
  | 'PRECOMBAT_MAIN'
  | 'COMBAT'
  | 'POSTCOMBAT_MAIN'
  | 'ENDING';

export type Step =
  | 'UNTAP'
  | 'UPKEEP'
  | 'DRAW'
  | 'MAIN'
  | 'BEGINNING_OF_COMBAT'
  | 'DECLARE_ATTACKERS'
  | 'DECLARE_BLOCKERS'
  | 'COMBAT_DAMAGE'
  | 'FIRST_STRIKE_DAMAGE'
  | 'END_OF_COMBAT'
  | 'END_STEP'
  | 'CLEANUP';

// Card Types
export interface CardData {
  id: string;
  name: string;
  mana_cost: string | null;
  types: string[];
  subtypes: string[];
  power: number | null;
  toughness: number | null;
  text: string;
  tapped: boolean;
  counters: Record<string, number>;
  damage: number;
  controller: string | null;
  owner: string | null;
}

// Stack Item
export interface StackItemData {
  id: string;
  type: string;
  source_id: string;
  source_name: string;
  controller: string;
}

// Legal Action
export interface LegalActionData {
  type: ActionType;
  card_id: string | null;
  ability_id: string | null;
  source_id: string | null;
  description: string;
  requires_targets: boolean;
  requires_mana: boolean;
}

// Player Data
export interface PlayerData {
  id: string;
  name: string;
  life: number;
  has_lost: boolean;
  hand_size: number;
  library_size: number;
}

// Combat Data
export interface CombatData {
  attackers: AttackDeclaration[];
  blockers: BlockDeclaration[];
  blocked_attackers: string[];
}

export interface AttackDeclaration {
  attacker_id: string;
  defending_player: string;
}

export interface BlockDeclaration {
  blocker_id: string;
  attacker_id: string;
}

// Pending Choice (for modal/target/scry/surveil decisions)
export interface ChoiceOption {
  id: string;
  label?: string;
  description?: string;
  // Extended properties for divide_allocation
  name?: string;
  type?: 'creature' | 'permanent' | 'player' | 'unknown';
  life?: number;
  // Extended properties for modal_with_targeting
  index?: number;
  requires_targeting?: boolean;
}

export interface PendingChoice {
  choice_type: 'modal' | 'target' | 'scry' | 'surveil' | string;
  player: string;
  prompt: string;
  options: ChoiceOption[];
  source_id: string;
  min_choices: number;
  max_choices: number;
}

// Full Game State
export interface GameState {
  match_id: string;
  turn_number: number;
  phase: Phase;
  step: Step;
  active_player: string | null;
  priority_player: string | null;
  players: Record<string, PlayerData>;
  battlefield: CardData[];
  stack: StackItemData[];
  hand: CardData[];
  graveyard: Record<string, CardData[]>;
  legal_actions: LegalActionData[];
  combat: CombatData | null;
  is_game_over: boolean;
  winner: string | null;
  pending_choice?: PendingChoice | null;
}

// Request/Response Types
export interface CreateMatchRequest {
  mode: MatchMode;
  player_deck?: string[];
  player_deck_id?: string;
  player_name: string;
  ai_difficulty?: AIDifficulty;
  ai_deck?: string[];
  ai_deck_id?: string;
}

export interface CreateMatchResponse {
  match_id: string;
  player_id: string;
  opponent_id: string;
  status: string;
}

export interface PlayerActionRequest {
  action_type: ActionType;
  player_id: string;
  card_id?: string;
  targets?: string[][];
  x_value?: number;
  ability_id?: string;
  source_id?: string;
  attackers?: AttackDeclaration[];
  blockers?: BlockDeclaration[];
}

export interface ActionResultResponse {
  success: boolean;
  message: string;
  new_state?: GameState;
  events: Record<string, unknown>[];
}

// Bot Game Types
export interface StartBotGameRequest {
  mode?: 'mtg' | 'hearthstone';
  bot1_deck: string[];
  bot2_deck: string[];
  bot1_deck_id?: string;
  bot2_deck_id?: string;
  bot1_difficulty: AIDifficulty;
  bot2_difficulty: AIDifficulty;
  bot1_brain?: 'heuristic' | 'openai' | 'anthropic' | 'ollama';
  bot2_brain?: 'heuristic' | 'openai' | 'anthropic' | 'ollama';
  bot1_model?: string;
  bot2_model?: string;
  bot1_name?: string;
  bot2_name?: string;
  bot1_temperature?: number;
  bot2_temperature?: number;
  record_prompts?: boolean;
  max_replay_frames?: number;
  delay_ms: number;
}

export interface BotGameResponse {
  game_id: string;
  status: string;
}

export interface BotGameStatus {
  game_id: string;
  status: 'running' | 'finished';
  turn: number;
  winner: string | null;
}

// Replay Types
export interface ReplayFrame {
  turn: number;
  phase: string;
  step: string;
  action: Record<string, unknown> | null;
  state: GameState;
  timestamp: number;
}

export interface ReplayResponse {
  game_id: string;
  winner: string | null;
  total_turns: number;
  frames: ReplayFrame[];
}
