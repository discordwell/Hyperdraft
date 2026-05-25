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
  | 'DECLARE_BLOCKERS'
  | 'HS_PLAY_CARD'
  | 'HS_ATTUNE_CARD'
  | 'HS_ATTACK'
  | 'HS_HERO_POWER'
  | 'HS_END_TURN'
  | 'PKM_PLAY_CARD'
  | 'PKM_ATTACH_ENERGY'
  | 'PKM_ATTACK'
  | 'PKM_RETREAT'
  | 'PKM_EVOLVE'
  | 'PKM_USE_ABILITY'
  | 'PKM_END_TURN'
  | 'YGO_NORMAL_SUMMON'
  | 'YGO_SET_MONSTER'
  | 'YGO_FLIP_SUMMON'
  | 'YGO_CHANGE_POSITION'
  | 'YGO_ACTIVATE'
  | 'YGO_SET_SPELL_TRAP'
  | 'YGO_DECLARE_ATTACK'
  | 'YGO_DIRECT_ATTACK'
  | 'YGO_CHAIN_RESPONSE'
  | 'YGO_CHAIN_PASS'
  | 'YGO_END_TURN'
  | 'YGO_SPECIAL_SUMMON'
  | 'YGO_END_PHASE'
  | 'MC_PLAY_CARD'
  | 'MC_ASSIGN_WORKER'
  | 'MC_AVATAR_ACTION'
  | 'MC_EXPLORE_BIOME'
  | 'MC_DECLARE_ATTACKERS'
  | 'MC_DECLARE_BLOCKERS'
  | 'MC_END_TURN'
  | 'MC_MULLIGAN_DECISION'
  | 'DEPTHS_PLAY_CARD'
  | 'DEPTHS_DIVE'
  | 'DEPTHS_SURFACE'
  | 'DEPTHS_LAY_MINE'
  | 'DEPTHS_DECLARE_ATTACKERS'
  | 'DEPTHS_DETECT'
  | 'DEPTHS_DECLARE_INTERCEPTORS'
  | 'DEPTHS_ACTIVATE_ABILITY'
  | 'DEPTHS_END_TURN'
  | 'FIN_PLAY_CARD'
  | 'FIN_DECLARE_ATTACKERS'
  | 'FIN_DECLARE_BLOCKERS'
  | 'FIN_ACTIVATE_ABILITY'
  | 'FIN_END_PHASE'
  | 'FIN_END_TURN'
  | 'FIN_PLAY_RESPONSE'
  | 'FIN_PASS_RESPONSE'
  | 'SCP_OPEN_DOSSIER'
  | 'SCP_REVEAL_DOSSIER'
  | 'SCP_RESEARCH'
  | 'SCP_CONTAIN'
  | 'SCP_SUPPRESS'
  | 'SCP_SPEND_ETHICS'
  | 'SCP_SHIFT_MOOD'
  | 'SCP_CROSS_CONTAIN'
  | 'SCP_MEMORY_HOLE'
  | 'SCP_APPLY_PROTOCOL'
  | 'SCP_RESOLVE_INCIDENT'
  | 'SCP_END_TURN'
  | 'CATS_PLAY_CARD'
  | 'CATS_CHOOSE_PILE'
  | 'CATS_KNOCK_OVER'
  | 'CLANKERS_PLAY_CHASSIS'
  | 'CLANKERS_PLAY_PART'
  | 'CLANKERS_PLAY_TRANSIENT'
  | 'CLANKERS_PLAY_STRUCTURE'
  | 'CLANKERS_PLAY_CARD'
  | 'CLANKERS_ATTACH_PART'
  | 'CLANKERS_ACTIVATE'
  | 'CLANKERS_ACTIVATE_ABILITY'
  | 'CLANKERS_DECLARE_ATTACK'
  | 'CLANKERS_DECLARE_ATTACKERS'
  | 'CLANKERS_DECLARE_BLOCK'
  | 'CLANKERS_DECLARE_BLOCKERS'
  | 'CLANKERS_REFILL_RESPONSE'
  | 'CLANKERS_REFILL_DECISION'
  | 'CLANKERS_END_PHASE'
  | 'CLANKERS_PASS_PHASE';

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
  domain?: string | null;
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
  keywords?: string[];
  foil?: boolean;
  // Hearthstone state
  divine_shield?: boolean;
  stealth?: boolean;
  windfury?: boolean;
  frozen?: boolean;
  summoning_sickness?: boolean;
  attacks_this_turn?: number;
  // Pokemon state
  hp?: number;
  damage_counters?: number;
  pokemon_type?: string;
  evolution_stage?: string;
  attacks?: { name: string; cost: { type: string; count: number }[]; damage: number; text: string }[];
  ability_name?: string;
  ability_text?: string;
  weakness_type?: string;
  resistance_type?: string;
  retreat_cost?: number;
  attached_energy?: string[];
  attached_tool_name?: string;
  status_conditions?: string[];
  is_ex?: boolean;
  prize_count?: number;
  image_url?: string;
  // Yu-Gi-Oh! state
  level?: number;
  rank?: number;
  link_rating?: number;
  atk?: number;
  def_val?: number;
  attribute?: string;
  ygo_monster_type?: string;
  ygo_spell_type?: string;
  ygo_trap_type?: string;
  ygo_position?: string;
  face_down?: boolean;
  overlay_units?: number;
  is_tuner?: boolean;
  // Minecraft state/metadata
  mc_cost?: Record<string, number>;
  mc_grid_x?: number | null;
  mc_grid_y?: number | null;
  mc_gear_slot?: string | null;
  mc_exhausted?: boolean;
  mc_keywords?: string[];
  // Depths (submarine fleet) state/metadata
  depths_cost?: { tc?: number; sc?: number };
  depth_band?: 'SURFACE' | 'PERISCOPE' | 'MID' | 'DEEP' | 'CRUSH' | string;
  detected?: boolean;
  oxygen?: number;
  hull?: number;
  is_flagship?: boolean;
  depths_keywords?: string[];
  // SCP Containment TCG state/metadata
  scp_red_tape?: number;
  scp_clearance?: number;
  scp_containment?: number;
  scp_curiosity?: number;
  scp_hazard?: number;
  scp_skills?: Record<string, number>;
  scp_bonus?: Record<string, number>;
  scp_status?: string | null;
  scp_paperwork?: number;
  scp_exhausted?: boolean;
  scp_researched?: number;
  scp_suppressed?: number;
  scp_mood?: string | null;
  scp_bound_to?: string | null;
  scp_protocols?: string[];
  scp_public_tags?: string[];
}

// Stack Item
export interface StackItemData {
  id: string;
  type: string;
  source_id: string;
  source_name: string;
  controller: string;
  // Triggered-ability description ("Whenever X enters, you gain 3 life.").
  // Empty string for spells/activated abilities.
  description?: string;
}

// Pending Triggered Ability
// Triggers fire and queue here; the next priority pass drains them onto
// the stack as TRIGGERED_ABILITY stack items. The active player can
// optionally re-order their own simultaneous triggers (CR 603.3b) — v1
// shows the queue read-only, full reordering UI is deferred.
export interface PendingTriggerData {
  id: string;
  controller: string;
  source_id: string;
  source_name: string;
  description?: string;
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
  // Hearthstone fields
  mana_crystals?: number;
  mana_crystals_available?: number;
  armor?: number;
  hero_id?: string | null;
  weapon_attack?: number;
  weapon_durability?: number;
  fatigue_damage?: number;
  hero_power_used?: boolean;
  hero_power_id?: string | null;
  hero_power_name?: string | null;
  hero_power_cost?: number;
  hero_power_text?: string | null;
  max_life?: number;
  variant_resources?: Record<string, number>;
  // Pokemon fields
  prizes_remaining?: number;
  energy_attached_this_turn?: boolean;
  supporter_played_this_turn?: boolean;
  // Yu-Gi-Oh! fields
  lp?: number;
  normal_summon_used?: boolean;
  // Minecraft fields
  mc_materials?: Record<string, number>;
  mc_avatar_gear?: Record<string, string | null>;
  mc_avatar_action_used?: boolean;
  // Depths (submarine fleet) fields
  tc?: number;       // Torpedo Charges (current)
  sc?: number;       // Sonar Charges (current)
  tc_max?: number;   // Per-turn cap
  sc_max?: number;
  flagship_id?: string | null;
}

// Combat Data
export interface CombatData {
  attackers: AttackDeclaration[];
  blockers: BlockDeclaration[];
  blocked_attackers: string[];
}

export interface AttackDeclaration {
  attacker_id: string;
  defending_player?: string;
  target_id?: string;
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

/**
 * Mirrors src/engine/types.py:DivideAllocation. Surfaced on
 * TargetGroupMetadata.divide when a spell asks the player to distribute
 * a quantity (damage, counters, life) across targets.
 *
 * Engine-agnostic — any TCG with "deal X divided among targets" uses the
 * same shape.
 */
export interface DivideAllocation {
  total: number;
  min_per_target?: number;
  allow_zero?: boolean;
}

/**
 * Mirrors src/engine/types.py:TargetGroupMetadata. Engine-supplied
 * structured target hint for the client, surfaced via
 * `PendingChoice.target_metadata` when `choice_type === 'target'` or
 * `'divide_allocation'`.
 *
 * The frontend renders this directly — no card-text parsing, no
 * per-card frontend logic. Any future user-generated game that emits
 * target requirements inherits the targeting UX for free.
 */
export interface TargetGroupMetadata {
  label: string;
  predicate_description: string;
  min: number;
  max: number;
  unique?: boolean;
  divide?: DivideAllocation;
  group_index?: number;
  total_groups?: number;
}

export interface PendingChoice {
  id: string;
  choice_type: 'modal' | 'target' | 'scry' | 'surveil' | string;
  player: string;
  prompt: string;
  options: ChoiceOption[];
  source_id: string;
  min_choices: number;
  max_choices: number;
  // Rendering hint emitted by the engine. ``'overlay'`` => render as
  // click-to-target board highlights (Phase 5b MTG cast-time targets);
  // absent or ``'modal'`` => standard ChoiceModal panel.
  interaction_mode?: 'modal' | 'overlay';
  // Arc B — structured target metadata. Populated for 'target' and
  // 'divide_allocation' choice types; absent for modal/scry/surveil/etc.
  // The frontend's overlay pill renders directly from this; falls back
  // to min_choices/max_choices/prompt when missing.
  target_metadata?: TargetGroupMetadata;
}

// Game Log Entry
export interface GameLogEntry {
  turn: number;
  text: string;
  event_type: string;
  player?: string;
  timestamp?: number;
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
  pending_triggers?: PendingTriggerData[];
  hand: CardData[];
  graveyard: Record<string, CardData[]>;
  legal_actions: LegalActionData[];
  combat: CombatData | null;
  is_game_over: boolean;
  winner: string | null;
  pending_choice?: PendingChoice | null;
  game_mode?: 'mtg' | 'hearthstone' | 'pokemon' | 'yugioh' | 'minecraft' | 'depths' | 'finance' | 'scp' | 'cats' | 'clankers';
  variant?: string | null;
  max_hand_size?: number;
  // Pokemon zones
  active_pokemon?: Record<string, CardData | null>;
  bench?: Record<string, CardData[]>;
  stadium_card?: CardData | null;
  // Yu-Gi-Oh! zones
  monster_zones?: Record<string, (CardData | null)[]>;
  spell_trap_zones?: Record<string, (CardData | null)[]>;
  field_spells?: Record<string, CardData | null>;
  banished?: Record<string, CardData[]>;
  extra_deck_sizes?: Record<string, number>;
  ygo_phase?: string;
  chain_links?: unknown[];
  // Minecraft state
  minecraft_day_phase?: string;
  minecraft_biomes?: Record<string, { name: string; yields: Record<string, number>; mined?: boolean; level?: number }[]>;
  minecraft_grid?: Record<string, (CardData | null)[][]>;
  minecraft_combat?: Record<string, unknown>;
  minecraft_exposed_targets?: Record<string, string[]>;
  minecraft_mulligan_pending?: Record<
    string,
    {
      mulligan_count: number;
      hand_size_after_keep: number;
      cost_for_next: number;
    }
  >;
  // Depths (submarine fleet) state
  depths_phase?: string;
  depths_combat?: {
    phase?: string;
    attacking_player?: string;
    defending_player?: string;
    attackers?: { attacker_id: string; target_id?: string; firing_band?: string }[];
    legal_interceptors?: string[];
  };
  // Finance state
  finance_phase?: string;
  finance_dark_pool?: string | null;
  finance_turn_data?: Record<string, unknown>;
  finance_stack?: FinanceStackItem[];
  finance_pending_response?: FinancePendingResponse | null;
  // SCP Containment TCG state
  scp_sites?: Record<string, SCPSiteState>;
  scp_anomalies?: Record<string, CardData[]>;
  scp_contained?: Record<string, CardData[]>;
  scp_personnel?: Record<string, CardData[]>;
  scp_facilities?: Record<string, CardData[]>;
  scp_mandates?: Record<string, CardData[]>;
  scp_incidents?: Record<string, SCPIncident[]>;
  scp_assignment_slots?: Record<string, number>;
  // Cats engine — nested payload; useCatsGame.ts projects it into CatsState
  cats?: unknown;
  // Clankers engine — nested payload; useClankersGame.ts projects it into
  // ClankersState. Backend serializer pending — currently the hook falls
  // back to a mock fixture when the field is absent.
  clankers?: unknown;
  // Game log
  game_log?: GameLogEntry[];
}

export interface SCPSiteState {
  secrecy?: number;
  breach?: number;
  archives?: number;
  ethics_debt?: number;
  clearance?: number;
  briefing?: number;
  assignment_slots?: number;
  assignments_used?: number;
}

export interface SCPIncident {
  name?: string;
  turn?: number;
  breach?: number;
  effect?: string;
  [key: string]: unknown;
}

// MTG-style priority stack item used by FINA spells.
export interface FinanceStackItem {
  card_id: string;
  controller: string;
  name: string;
  is_response: boolean;
  countered: boolean;
}

// Open priority window — engine is awaiting a response action from
// the prompted player.
export interface FinancePendingResponse {
  prompted_player_id: string;
  top_card_id: string;
  top_card_name: string;
  top_controller: string;
}

// Request/Response Types
export interface CreateMatchRequest {
  mode: MatchMode;
  game_mode?: 'mtg' | 'hearthstone' | 'pokemon' | 'yugioh' | 'minecraft' | 'depths' | 'finance' | 'scp' | 'cats' | 'clankers';
  variant?: string;
  ultra_agent?: 'claude' | 'codex';
  ultra_model?: string;
  player_deck?: string[];
  player_deck_id?: string;
  player_name: string;
  ai_difficulty?: AIDifficulty;
  ai_deck?: string[];
  ai_deck_id?: string;
  hero_class?: string;
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
  cell?: { x: number; y: number };
  biome_index?: number;
  action_kind?: string;
  // Minecraft mulligan
  keep?: boolean;
  // Depths-specific
  depth_band?: string;
  vessel_id?: string;
  interceptors?: { attacker_id: string; interceptor_id: string }[];
  detect_targets?: string[];
  // SCP-specific
  fast_track?: boolean;
  sealed?: boolean;
  anomaly_id?: string;
  staff_ids?: string[];
  contained_id?: string;
  active_id?: string;
  mood?: string;
  protocol?: string;
  index?: number;
  amount?: number;
  // Clankers-specific — names match src/server/models.py PlayerActionRequest
  target_chassis_id?: string;          // weapon/add-on attach target on CLANKERS_PLAY_CARD or CLANKERS_ATTACH_PART
  part_obj_id?: string;                // CLANKERS_ATTACH_PART floor-part id
  source_obj_id?: string;              // CLANKERS_ACTIVATE_ABILITY source
  ability_index?: number;              // activated-ability index
  attacker_ids?: string[];             // CLANKERS_DECLARE_ATTACKERS chassis/part ids
  blocker_pairs?: Record<string, string>;  // CLANKERS_DECLARE_BLOCKERS {attacker_id: blocker_id}
  refill_decision?: boolean;           // CLANKERS_REFILL_DECISION (true=take, false=decline)
  phase?: string;                      // CLANKERS_END_PHASE label
}

export interface ActionResultResponse {
  success: boolean;
  message: string;
  new_state?: GameState;
  events: Record<string, unknown>[];
}

// Bot Game Types
export interface StartBotGameRequest {
  mode?: 'mtg' | 'hearthstone' | 'pokemon' | 'yugioh' | 'minecraft' | 'depths' | 'finance' | 'scp' | 'cats' | 'clankers';
  bot1_deck: string[];
  bot2_deck: string[];
  bot1_deck_id?: string;
  bot2_deck_id?: string;
  bot1_difficulty: AIDifficulty;
  bot2_difficulty: AIDifficulty;
  bot1_brain?: 'heuristic' | 'openai' | 'ollama' | 'claude_code';
  bot2_brain?: 'heuristic' | 'openai' | 'ollama' | 'claude_code';
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
  // WatchLive lobby enrichment (HD-ART-06). All optional so legacy
  // consumers (completed_replays, older clients) keep working.
  game_mode?: string | null;
  player1_label?: string | null;
  player2_label?: string | null;
  deck_blurb?: string | null;
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
