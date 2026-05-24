/**
 * useClankersGame Hook
 *
 * Clankers-engine game state + action dispatch. Currently MOCK-ONLY: returns
 * a representative two-player board snapshot so the in-game UI can be rendered
 * and visually validated before the server route is wired up.
 *
 * Wire shape (eventual): the server will serialize a `clankers` payload
 * mirroring the cats pattern; we'll then read `gameState.clankers` and project
 * it into ClankersState. For now `dispatch` simply console-logs and (for
 * locally-rendered demo flair) optimistically mutates the mock state.
 *
 * Action protocol (planned):
 *  - CLANKERS_PLAY_CHASSIS  { card_id }
 *  - CLANKERS_PLAY_PART     { card_id, attach_to?: chassis_id }
 *  - CLANKERS_PLAY_TRANSIENT{ card_id }
 *  - CLANKERS_PLAY_STRUCTURE{ card_id }
 *  - CLANKERS_ATTACH_PART   { part_id, chassis_id }
 *  - CLANKERS_ACTIVATE      { source_id }
 *  - CLANKERS_DECLARE_ATTACK{ chassis_id }
 *  - CLANKERS_DECLARE_BLOCK { blocker_id, attacker_id }
 *  - CLANKERS_REFILL_RESPONSE { accept: boolean }
 *  - CLANKERS_PASS_PHASE
 */
import { useCallback, useState } from 'react';

// ---------------------------------------------------------------------------
// Types — engine-facing
// ---------------------------------------------------------------------------

export type ClankersSeat = 'me' | 'opponent';

export type ClankersCardType =
  | 'CLANKERS_CHASSIS'
  | 'CLANKERS_WEAPON'
  | 'CLANKERS_ADD_ON'
  | 'CLANKERS_TRANSIENT'
  | 'CLANKERS_STRUCTURE'
  | 'CLANKERS_CORE';

export type ClankersPhase =
  | 'boot'
  | 'allocate'
  | 'assemble'
  | 'combat'
  | 'reassemble'
  | 'cleanup';

export type ClankersArchetype =
  | 'rush'
  | 'brick'
  | 'swarm'
  | 'control'
  | 'artillery'
  | string;

/**
 * A single card on a player's board, in hand, or in a pile. The same shape is
 * reused for every zone — interpretation depends on which list it lives in.
 */
export interface ClankersCard {
  id: string;
  name: string;
  card_type: ClankersCardType;
  compute_cost: number;
  text?: string;
  // CHASSIS / solo-part stats:
  power?: number;
  integrity?: number;
  weapon_slots?: number;
  add_on_slots?: number;
  // PART stats:
  power_bonus?: number;
  integrity_bonus?: number;
  weapon_slot_cost?: number;
  armor_value?: number;
  // Runtime state (battlefield-only):
  tapped?: boolean;            // "exhausted"
  damage_marked?: number;      // chassis-only; integrity floor before destruction
  attached_to?: string | null; // part: id of host chassis
  attachments?: ClankersCard[]; // chassis: weapons + add-ons currently attached
  // Combat staging:
  is_attacking?: boolean;      // chassis declared as attacker this combat
  blocking?: string | null;    // chassis id this one is currently blocking
  // Flavor:
  archetype?: ClankersArchetype;
  keywords?: string[];
}

export interface ClankersCore {
  id: string;
  name: string;
  text?: string;
  passive?: string;
}

export interface ClankersPlayerState {
  display_name: string;
  core: ClankersCore;
  workshop_integrity: number;
  workshop_integrity_max: number;
  compute_pool: number;
  compute_cap: number;
  scrap_pool: number;
  refill_used: boolean;
  hand: ClankersCard[];               // viewer sees full hand; opponent only counts
  hand_size: number;                  // canonical; for opponent hand.length === 0
  library_size: number;
  scrap_heap_size: number;
  assembly_floor: ClankersCard[];     // chassis + solo parts (parts attach via attachments[])
  structures: ClankersCard[];         // up to 3
}

export interface ClankersDeathclock {
  active: boolean;
  turn: number;       // 0 if inactive; 1 means "next damage = base * 2^0 = 2"
  next_damage: number; // precomputed for UI
}

export interface ClankersCombat {
  active: boolean;
  attackers: string[];                          // chassis ids currently attacking
  blocks: Record<string, string>;               // attacker_id → blocker_id (one-to-one)
}

export interface ClankersRefillPrompt {
  // The viewer is being asked whether to refill their hand to 7. Surface
  // this as a yes/no in the Allocate UI. Hard AI may decline; we let the
  // human do the same.
  pending: boolean;
  current_hand_size: number;
  target: number;
}

export interface ClankersState {
  turn_number: number;
  active_seat: ClankersSeat;
  phase: ClankersPhase;
  player: ClankersPlayerState;
  opponent: ClankersPlayerState;
  deathclock: ClankersDeathclock;
  combat: ClankersCombat;
  refill_prompt: ClankersRefillPrompt;
  game_over: boolean;
  winner?: ClankersSeat | null;
}

// ---------------------------------------------------------------------------
// Action vocab (mock-only for now)
// ---------------------------------------------------------------------------

export type ClankersAction =
  | { type: 'CLANKERS_PLAY_CHASSIS'; cardId: string }
  | { type: 'CLANKERS_PLAY_PART'; cardId: string; attachTo?: string }
  | { type: 'CLANKERS_PLAY_TRANSIENT'; cardId: string }
  | { type: 'CLANKERS_PLAY_STRUCTURE'; cardId: string }
  | { type: 'CLANKERS_ATTACH_PART'; partId: string; chassisId: string }
  | { type: 'CLANKERS_ACTIVATE'; sourceId: string }
  | { type: 'CLANKERS_DECLARE_ATTACK'; chassisId: string }
  | { type: 'CLANKERS_DECLARE_BLOCK'; blockerId: string; attackerId: string }
  | { type: 'CLANKERS_REFILL_RESPONSE'; accept: boolean }
  | { type: 'CLANKERS_PASS_PHASE' };

// ---------------------------------------------------------------------------
// Mock fixture — a representative mid-game state at turn 5, viewer's Assemble.
// ---------------------------------------------------------------------------

function makeMockState(): ClankersState {
  // ---- Viewer (FORGE-Δ) — mid-game artillery build ----
  const viewerBuzzsaw: ClankersCard = {
    id: 'p1_buzzsaw',
    name: 'Buzzsaw Arm',
    card_type: 'CLANKERS_WEAPON',
    compute_cost: 2,
    power_bonus: 2,
    weapon_slot_cost: 1,
    text: 'When this part is destroyed, deal 1 damage to the killer.',
    attached_to: 'p1_ironframe',
    archetype: 'brick',
  };
  const viewerPlating: ClankersCard = {
    id: 'p1_plating',
    name: 'Reinforced Plating',
    card_type: 'CLANKERS_ADD_ON',
    compute_cost: 2,
    power_bonus: 0,
    integrity_bonus: 2,
    armor_value: 2,
    keywords: ['armor'],
    text: 'Armor 2 — exhaust to absorb up to 2 damage to host.',
    attached_to: 'p1_ironframe',
    archetype: 'brick',
  };
  const viewerIronFrame: ClankersCard = {
    id: 'p1_ironframe',
    name: 'Iron Frame',
    card_type: 'CLANKERS_CHASSIS',
    compute_cost: 4,
    power: 3,
    integrity: 4,
    weapon_slots: 2,
    add_on_slots: 2,
    damage_marked: 0,
    archetype: 'brick',
    attachments: [viewerBuzzsaw, viewerPlating],
    text: 'A reliable workhorse chassis. Welds straight.',
  };

  const viewerScout: ClankersCard = {
    id: 'p1_scout',
    name: 'Scout Chassis',
    card_type: 'CLANKERS_CHASSIS',
    compute_cost: 2,
    power: 2,
    integrity: 2,
    weapon_slots: 1,
    add_on_slots: 2,
    damage_marked: 1,
    archetype: 'rush',
    attachments: [],
    tapped: true,
  };

  const viewerSoloCannon: ClankersCard = {
    id: 'p1_plasma_solo',
    name: 'Plasma Cannon',
    card_type: 'CLANKERS_WEAPON',
    compute_cost: 3,
    power_bonus: 3,
    weapon_slot_cost: 1,
    attached_to: null,
    text: 'Big gun, no host. Fragile alone (1/1).',
    archetype: 'artillery',
  };

  const viewerCore: ClankersCore = {
    id: 'p1_core',
    name: 'FORGE-Δ',
    text: 'Affection metrics: optimizing. Your weapons cost 1 less Compute.',
    passive: 'Weapons cost 1 less Compute.',
  };

  const viewerStructure: ClankersCard = {
    id: 'p1_struct_anvil',
    name: 'Resonant Anvil',
    card_type: 'CLANKERS_STRUCTURE',
    compute_cost: 3,
    text: 'Your chassis have +1 Power.',
    archetype: 'brick',
  };

  const viewerHand: ClankersCard[] = [
    {
      id: 'h1',
      name: 'Heavy Tread',
      card_type: 'CLANKERS_CHASSIS',
      compute_cost: 5,
      power: 5,
      integrity: 5,
      weapon_slots: 3,
      add_on_slots: 4,
      archetype: 'brick',
      text: 'Slow. Patient. Inevitable.',
    },
    {
      id: 'h2',
      name: 'Targeting Laser',
      card_type: 'CLANKERS_ADD_ON',
      compute_cost: 1,
      power_bonus: 1,
      integrity_bonus: 0,
      archetype: 'artillery',
      text: 'Host\'s attacks cannot be blocked by chassis with 1 integrity.',
    },
    {
      id: 'h3',
      name: 'Overclock',
      card_type: 'CLANKERS_TRANSIENT',
      compute_cost: 2,
      archetype: 'rush',
      text: 'A chassis you control gets +2 Power until end of turn.',
    },
    {
      id: 'h4',
      name: 'Rivet Gun',
      card_type: 'CLANKERS_WEAPON',
      compute_cost: 1,
      power_bonus: 1,
      weapon_slot_cost: 1,
      archetype: 'rush',
    },
    {
      id: 'h5',
      name: 'Scrap-Heap Salvage',
      card_type: 'CLANKERS_TRANSIENT',
      compute_cost: 3,
      archetype: 'control',
      text: 'Return a weapon from your scrap heap to your hand.',
    },
    {
      id: 'h6',
      name: 'Plasma Shielding',
      card_type: 'CLANKERS_ADD_ON',
      compute_cost: 3,
      power_bonus: 0,
      integrity_bonus: 3,
      keywords: ['armor'],
      armor_value: 3,
      archetype: 'brick',
    },
    {
      id: 'h7',
      name: 'Skitter Frame',
      card_type: 'CLANKERS_CHASSIS',
      compute_cost: 1,
      power: 1,
      integrity: 1,
      weapon_slots: 1,
      add_on_slots: 1,
      archetype: 'swarm',
      text: 'Cheap. Disposable. Useful.',
    },
  ];

  // ---- Opponent (ETHOS-7) — slower assembled brick ----
  const oppHeavySawblade: ClankersCard = {
    id: 'p2_sawblade',
    name: 'Industrial Sawblade',
    card_type: 'CLANKERS_WEAPON',
    compute_cost: 3,
    power_bonus: 3,
    weapon_slot_cost: 2,
    attached_to: 'p2_tread',
    archetype: 'brick',
  };
  const oppTread: ClankersCard = {
    id: 'p2_tread',
    name: 'Heavy Tread',
    card_type: 'CLANKERS_CHASSIS',
    compute_cost: 5,
    power: 5,
    integrity: 5,
    weapon_slots: 3,
    add_on_slots: 4,
    damage_marked: 0,
    archetype: 'brick',
    attachments: [oppHeavySawblade],
  };

  const oppSkitter: ClankersCard = {
    id: 'p2_skitter',
    name: 'Skitter Frame',
    card_type: 'CLANKERS_CHASSIS',
    compute_cost: 1,
    power: 1,
    integrity: 1,
    weapon_slots: 1,
    add_on_slots: 1,
    damage_marked: 0,
    archetype: 'swarm',
    attachments: [],
  };

  const oppCore: ClankersCore = {
    id: 'p2_core',
    name: 'ETHOS-7',
    text: 'Cycling subroutine engaged. Empathy: pending.',
    passive: 'Each turn, draw 1 extra card. (Refill includes one bonus.)',
  };

  const viewer: ClankersPlayerState = {
    display_name: 'you',
    core: viewerCore,
    workshop_integrity: 22,
    workshop_integrity_max: 25,
    compute_pool: 4,
    compute_cap: 10,
    scrap_pool: 3,
    refill_used: true,
    hand: viewerHand,
    hand_size: viewerHand.length,
    library_size: 38,
    scrap_heap_size: 6,
    assembly_floor: [viewerIronFrame, viewerScout, viewerSoloCannon],
    structures: [viewerStructure],
  };

  const opponent: ClankersPlayerState = {
    display_name: 'ETHOS-7',
    core: oppCore,
    workshop_integrity: 18,
    workshop_integrity_max: 25,
    compute_pool: 5,
    compute_cap: 10,
    scrap_pool: 1,
    refill_used: true,
    hand: [], // hidden from viewer; counts via hand_size
    hand_size: 7,
    library_size: 31,
    scrap_heap_size: 9,
    assembly_floor: [oppTread, oppSkitter],
    structures: [],
  };

  return {
    turn_number: 5,
    active_seat: 'me',
    phase: 'assemble',
    player: viewer,
    opponent,
    deathclock: { active: false, turn: 0, next_damage: 2 },
    combat: { active: false, attackers: [], blocks: {} },
    refill_prompt: { pending: false, current_hand_size: 7, target: 7 },
    game_over: false,
    winner: null,
  };
}

// ---------------------------------------------------------------------------
// Hook (mock-only)
// ---------------------------------------------------------------------------

export interface UseClankersGameResult {
  state: ClankersState | null;
  dispatch: (action: ClankersAction) => void;
  isLoading: boolean;
  error: string | null;
}

export function useClankersGame(_matchId?: string): UseClankersGameResult {
  const [state, setState] = useState<ClankersState | null>(() => makeMockState());

  const dispatch = useCallback((action: ClankersAction) => {
    // For v1 the dispatch is purely local: console.log + small optimistic
    // mock mutation so the UI feels alive while we wire the server.
    // eslint-disable-next-line no-console
    console.log('[clankers] dispatch', action);
    setState((prev) => {
      if (!prev) return prev;
      // Minimal mock effect: PASS_PHASE bumps the phase wheel one click forward.
      if (action.type === 'CLANKERS_PASS_PHASE') {
        const order: ClankersPhase[] = [
          'boot',
          'allocate',
          'assemble',
          'combat',
          'reassemble',
          'cleanup',
        ];
        const idx = order.indexOf(prev.phase);
        const next = order[(idx + 1) % order.length];
        return { ...prev, phase: next };
      }
      if (action.type === 'CLANKERS_REFILL_RESPONSE') {
        return {
          ...prev,
          refill_prompt: { ...prev.refill_prompt, pending: false },
          player: { ...prev.player, refill_used: true },
        };
      }
      return prev;
    });
  }, []);

  return {
    state,
    dispatch,
    isLoading: state === null,
    error: null,
  };
}
