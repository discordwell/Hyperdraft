/**
 * useSCP2Game — SCP: SECURE / CONTAIN / SUBVERT (asymmetric Foundation vs Chaos Insurgency).
 *
 * Subscribes to gameState via useSocket and projects the server's viewer-redacted
 * `gameState.scp2` payload (built by session.py:_serialize_scp2_state) into the typed
 * SCP2State the board renders. Fog of war is enforced server-side: face-down identities
 * arrive as `[FACE-DOWN]` with `hidden:true`, while advancement "heat" is always public.
 *
 * Action protocol (→ src/server/models.py SCP2_* + PlayerActionRequest fields):
 *   SCP2_GAIN        {}                         — +2 credits (1 AP)
 *   SCP2_DRAW        {}                         — draw 1 (1 AP)
 *   SCP2_PLAY        { card_id, cell_id?, scp2_target? }
 *   SCP2_ADVANCE     { anomaly_id }
 *   SCP2_CONTAIN     { anomaly_id }
 *   SCP2_INFILTRATE  { scp2_target: ['cell','3'] | ['central','research'] }
 *   SCP2_ACTIVATE    { card_id, scp2_target? }
 *   SCP2_END_TURN    {}
 */
import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType, PlayerActionRequest } from '../types';

// ---------------------------------------------------------------------------
// Types — mirror the _serialize_scp2_state wire shape
// ---------------------------------------------------------------------------
export type SCP2Faction = 'foundation' | 'insurgency';
export type SCP2Kind =
  | 'SCP2_ANOMALY' | 'SCP2_LAYER' | 'SCP2_ASSET' | 'SCP2_OPERATION'
  | 'SCP2_OPERATIVE' | 'SCP2_TOOL' | 'SCP2_EVENT' | 'SCP2_IDENTITY' | null;

export interface SCP2Card {
  id: string;
  name: string;
  hidden: boolean;
  kind: SCP2Kind;
  text?: string;
  cost?: number;
  // anomaly
  threshold?: number;
  value?: number;
  trap?: boolean;
  // layer
  ltype?: 'barrier' | 'sentry' | 'sensor' | null;
  strength?: number;
  rez?: number;
  rezzed?: boolean;
  // operative
  breaks?: 'barrier' | 'sentry' | 'sensor' | null;
  power?: number;
  boost?: number;
}

export interface SCP2CellAnomaly {
  id: string;
  advancement: number;
  name: string;
  hidden: boolean;
}
export interface SCP2CellLayer {
  id: string;
  name: string;
  rezzed: boolean;
  hidden: boolean;
}
export interface SCP2Cell {
  id: number;
  anomaly: SCP2CellAnomaly | null;
  layers: SCP2CellLayer[];
}

export interface SCP2Seat {
  faction: SCP2Faction;
  credits: number;
  ap: number;
  containment_points: number;
  liberation_points: number;
  total_breach: number;
  exposed: number;
  cells: SCP2Cell[];
  rig: SCP2Card[];
  assets: SCP2Card[];
  hand: SCP2Card[] | null; // own hand only; null for opponent
  hand_count: number;
  deck_count: number;
  discard_count: number;
  identity: string | null;
}

export interface SCP2Targets {
  containment: number;
  liberation: number;
  breach: number;
}

export interface SCP2State {
  foundationId: string | null;
  insurgencyId: string | null;
  viewerFaction: SCP2Faction | null;
  yourTurn: boolean;
  gameOver: boolean;
  winner: string | null;
  winReason: string | null;
  targets: SCP2Targets;
  me: SCP2Seat | null;
  opponent: SCP2Seat | null;
}

export type SCP2Action =
  | { type: 'GAIN' }
  | { type: 'DRAW' }
  | { type: 'PLAY'; cardId: string; cellId?: number; target?: string[] }
  | { type: 'ADVANCE'; anomalyId: string }
  | { type: 'CONTAIN'; anomalyId: string }
  | { type: 'INFILTRATE'; target: string[] }
  | { type: 'ACTIVATE'; cardId: string; target?: string[] }
  | { type: 'END_TURN' };

export interface UseSCP2GameResult {
  state: SCP2State | null;
  dispatch: (action: SCP2Action) => void;
  isLoading: boolean;
  isConnected: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Projector — the server shape is already clean; type it with safe defaults.
// ---------------------------------------------------------------------------
function projectSeat(raw: unknown): SCP2Seat | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const arr = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
  const n = (v: unknown): number => (typeof v === 'number' ? v : 0);
  return {
    faction: (r.faction as SCP2Faction) ?? 'foundation',
    credits: n(r.credits),
    ap: n(r.ap),
    containment_points: n(r.containment_points),
    liberation_points: n(r.liberation_points),
    total_breach: n(r.total_breach),
    exposed: n(r.exposed),
    cells: arr<SCP2Cell>(r.cells),
    rig: arr<SCP2Card>(r.rig),
    assets: arr<SCP2Card>(r.assets),
    hand: Array.isArray(r.hand) ? (r.hand as SCP2Card[]) : null,
    hand_count: n(r.hand_count),
    deck_count: n(r.deck_count),
    discard_count: n(r.discard_count),
    identity: (r.identity as string) ?? null,
  };
}

export function projectSCP2State(raw: Record<string, unknown>): SCP2State {
  const targets = (raw.targets as Record<string, number>) ?? {};
  return {
    foundationId: (raw.foundation_id as string) ?? null,
    insurgencyId: (raw.insurgency_id as string) ?? null,
    viewerFaction: (raw.viewer_faction as SCP2Faction) ?? null,
    yourTurn: Boolean(raw.your_turn),
    gameOver: Boolean(raw.game_over),
    winner: (raw.winner as string) ?? null,
    winReason: (raw.win_reason as string) ?? null,
    targets: {
      containment: targets.containment ?? 6,
      liberation: targets.liberation ?? 7,
      breach: targets.breach ?? 14,
    },
    me: projectSeat(raw.me),
    opponent: projectSeat(raw.opponent),
  };
}

function buildWireRequest(action: SCP2Action, playerId: string): PlayerActionRequest | null {
  const base = { player_id: playerId };
  switch (action.type) {
    case 'GAIN':
      return { ...base, action_type: 'SCP2_GAIN' as ActionType };
    case 'DRAW':
      return { ...base, action_type: 'SCP2_DRAW' as ActionType };
    case 'PLAY':
      return {
        ...base, action_type: 'SCP2_PLAY' as ActionType, card_id: action.cardId,
        cell_id: action.cellId, scp2_target: action.target,
      };
    case 'ADVANCE':
      return { ...base, action_type: 'SCP2_ADVANCE' as ActionType, anomaly_id: action.anomalyId };
    case 'CONTAIN':
      return { ...base, action_type: 'SCP2_CONTAIN' as ActionType, anomaly_id: action.anomalyId };
    case 'INFILTRATE':
      return { ...base, action_type: 'SCP2_INFILTRATE' as ActionType, scp2_target: action.target };
    case 'ACTIVATE':
      return { ...base, action_type: 'SCP2_ACTIVATE' as ActionType, card_id: action.cardId, scp2_target: action.target };
    case 'END_TURN':
      return { ...base, action_type: 'SCP2_END_TURN' as ActionType };
    default:
      return null;
  }
}

export function useSCP2Game(): UseSCP2GameResult {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  const state = useMemo<SCP2State | null>(() => {
    if (gameState) {
      const raw = (gameState as unknown as { scp2?: Record<string, unknown> | null }).scp2;
      if (raw) return projectSCP2State(raw);
    }
    return null;
  }, [gameState]);

  const dispatch = useCallback(
    async (action: SCP2Action) => {
      if (!matchId || !playerId) {
        // eslint-disable-next-line no-console
        console.log('[scp2] dispatch ignored (no match)', action);
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

  return { state, dispatch, isLoading: !state, isConnected, error: store.ui?.error ?? null };
}
