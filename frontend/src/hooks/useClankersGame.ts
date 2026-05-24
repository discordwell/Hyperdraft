/**
 * useClankersGame Hook
 *
 * Clankers-engine game state + action dispatch. Mirrors useCatsGame: subscribes
 * to gameState via useSocket, then projects the nested `gameState.clankers`
 * payload (built by the eventual server serializer) into the ClankersState
 * shape the clankers.tsx board renders.
 *
 * Until the backend ships a `clankers` serializer (see session.py's
 * `_serialize_cats_state` for the cats template), the hook falls back to a
 * representative mock fixture so the board UI stays interactive in design
 * review. As soon as the server starts emitting `gameState.clankers`, the
 * mock is bypassed automatically — no further frontend change needed.
 *
 * Action protocol:
 *  - CLANKERS_PLAY_CHASSIS    { card_id }
 *  - CLANKERS_PLAY_PART       { card_id, attach_to?: chassis_id }
 *  - CLANKERS_PLAY_TRANSIENT  { card_id }
 *  - CLANKERS_PLAY_STRUCTURE  { card_id }
 *  - CLANKERS_ATTACH_PART     { part_id, chassis_id }
 *  - CLANKERS_ACTIVATE        { source_id }
 *  - CLANKERS_DECLARE_ATTACK  { chassis_id }
 *  - CLANKERS_DECLARE_BLOCK   { blocker_id, attacker_id }
 *  - CLANKERS_REFILL_RESPONSE { accept: boolean }
 *  - CLANKERS_PASS_PHASE
 *
 * The board component imports `dispatch` from this hook — both the mock and
 * real paths expose the same function signature so swapping is transparent.
 */
import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType, PlayerActionRequest } from '../types';

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
// Action vocab
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
// Hook
// ---------------------------------------------------------------------------

export interface UseClankersGameResult {
  state: ClankersState | null;
  dispatch: (action: ClankersAction) => void;
  isLoading: boolean;
  isConnected: boolean;
  error: string | null;
}

// Map UI action → wire action. The wire vocabulary is more conservative
// (e.g. attackers/blockers are usually batched). The hook translates the
// per-card UI events into the canonical engine actions the server expects.
function buildWireRequest(
  action: ClankersAction,
  playerId: string,
): PlayerActionRequest | null {
  // Backend expects 7 canonical action types (per src/server/models.py
  // CLANKERS_* members) and field names that match PlayerActionRequest's
  // declared Clankers fields (card_id, target_chassis_id, part_obj_id,
  // source_obj_id, ability_index, attacker_ids, blocker_pairs,
  // refill_decision, phase). The UI emits more granular events; this
  // function collapses play_chassis/part/transient/structure → PLAY_CARD
  // (the backend dispatches by the card's CardType) and renames fields.
  switch (action.type) {
    case 'CLANKERS_PLAY_CHASSIS':
    case 'CLANKERS_PLAY_TRANSIENT':
    case 'CLANKERS_PLAY_STRUCTURE':
      return {
        action_type: 'CLANKERS_PLAY_CARD' as ActionType,
        player_id: playerId,
        card_id: action.cardId,
      };
    case 'CLANKERS_PLAY_PART':
      return {
        action_type: 'CLANKERS_PLAY_CARD' as ActionType,
        player_id: playerId,
        card_id: action.cardId,
        target_chassis_id: action.attachTo,
      };
    case 'CLANKERS_ATTACH_PART':
      return {
        action_type: 'CLANKERS_ATTACH_PART' as ActionType,
        player_id: playerId,
        part_obj_id: action.partId,
        target_chassis_id: action.chassisId,
      };
    case 'CLANKERS_ACTIVATE':
      return {
        action_type: 'CLANKERS_ACTIVATE_ABILITY' as ActionType,
        player_id: playerId,
        source_obj_id: action.sourceId,
      };
    case 'CLANKERS_DECLARE_ATTACK':
      // UI fires this once per attacker; we batch into a single wire
      // event with attacker_ids = [chassisId]. The board may collect all
      // attackers and dispatch once when the user clicks "End Attack".
      return {
        action_type: 'CLANKERS_DECLARE_ATTACKERS' as ActionType,
        player_id: playerId,
        attacker_ids: [action.chassisId],
      };
    case 'CLANKERS_DECLARE_BLOCK':
      // Same: one-pair-per-event; backend treats blocker_pairs as the
      // full mapping. The board may batch all blocks then dispatch.
      return {
        action_type: 'CLANKERS_DECLARE_BLOCKERS' as ActionType,
        player_id: playerId,
        blocker_pairs: { [action.attackerId]: action.blockerId },
      };
    case 'CLANKERS_REFILL_RESPONSE':
      return {
        action_type: 'CLANKERS_REFILL_DECISION' as ActionType,
        player_id: playerId,
        refill_decision: action.accept,
      };
    case 'CLANKERS_PASS_PHASE':
      return {
        action_type: 'CLANKERS_END_PHASE' as ActionType,
        player_id: playerId,
      };
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Mock fallback fixture — a representative mid-game state at turn 5, viewer's
// Assemble. Used only when the server hasn't shipped the `clankers` payload
// yet (so the board UI stays renderable for design review). The board itself
// is unchanged whether this mock or a real serialized state is in use.
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

// Stable singleton so the mock state mutates (PASS_PHASE bumps phase, etc.)
// across calls — same UX as the previous useState-only implementation.
let mockStateRef: ClankersState | null = null;
function getMockState(): ClankersState {
  if (mockStateRef === null) mockStateRef = makeMockState();
  return mockStateRef;
}

export function useClankersGame(): UseClankersGameResult {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  // Project the server's nested `clankers` payload into ClankersState. The
  // backend is expected to emit a seat-relative shape (player vs opponent)
  // like the cats serializer does; this is mostly a passthrough with a
  // typed cast. When the field is absent (no active match, or backend not
  // yet wired), fall back to the mock fixture so the board still renders.
  const state = useMemo<ClankersState | null>(() => {
    if (gameState) {
      const clankers = (gameState as unknown as { clankers?: ClankersState | null }).clankers;
      if (clankers) return clankers;
    }
    // No real state available — surface mock fixture for design review.
    // The board cannot distinguish; it just gets a ClankersState shape.
    return getMockState();
  }, [gameState]);

  const dispatch = useCallback(
    async (action: ClankersAction) => {
      // No active match → optimistic mock mutation so PASS_PHASE still
      // ticks the phase wheel during design review.
      if (!matchId || !playerId) {
        if (action.type === 'CLANKERS_PASS_PHASE' && mockStateRef) {
          const order: ClankersPhase[] = [
            'boot',
            'allocate',
            'assemble',
            'combat',
            'reassemble',
            'cleanup',
          ];
          const idx = order.indexOf(mockStateRef.phase);
          mockStateRef = {
            ...mockStateRef,
            phase: order[(idx + 1) % order.length],
          };
        }
        // eslint-disable-next-line no-console
        console.log('[clankers] mock dispatch (no match)', action);
        return;
      }

      const request = buildWireRequest(action, playerId);
      if (!request) return;
      try {
        const result = await matchAPI.submitAction(matchId, request);
        if (result.success && result.new_state) setGameState(result.new_state);
        else if (!result.success) setError(result.message);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Action failed');
      }
    },
    [matchId, playerId, setGameState, setError],
  );

  const isLoading = !state;
  const error = store.ui?.error ?? null;

  return { state, dispatch, isLoading, isConnected, error };
}
