/**
 * useSCPGame — SCP: SECURE / CONTAIN / SUBVERT (asymmetric Foundation vs Chaos Insurgency).
 *
 * Subscribes to gameState via useSocket and projects the server's viewer-redacted
 * `gameState.scp` payload (built by session.py:_serialize_scp_state) into the typed
 * SCPState the board renders. Fog of war is enforced server-side: face-down identities
 * arrive as `[FACE-DOWN]` with `hidden:true`, while advancement "heat" is always public.
 *
 * Action protocol (→ src/server/models.py SCP_* + PlayerActionRequest fields):
 *   SCP_GAIN        {}                         — +2 credits (1 AP)
 *   SCP_DRAW        {}                         — draw 1 (1 AP)
 *   SCP_PLAY        { card_id, cell_id?, scp_target? }
 *   SCP_ADVANCE     { anomaly_id }
 *   SCP_CONTAIN     { anomaly_id }
 *   SCP_INFILTRATE  { scp_target: ['cell','3'] | ['central','research'] }
 *   SCP_ACTIVATE    { card_id, scp_target? }
 *   SCP_END_TURN    {}
 */
import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType, PlayerActionRequest } from '../types';

// ---------------------------------------------------------------------------
// Types — mirror the _serialize_scp_state wire shape
// ---------------------------------------------------------------------------
export type SCPFaction = 'foundation' | 'insurgency';
export type SCPKind =
  | 'SCP_ANOMALY' | 'SCP_LAYER' | 'SCP_ASSET' | 'SCP_OPERATION'
  | 'SCP_OPERATIVE' | 'SCP_TOOL' | 'SCP_EVENT' | 'SCP_IDENTITY' | null;

export interface SCPCard {
  id: string;
  name: string;
  hidden: boolean;
  kind: SCPKind;
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

export interface SCPCellAnomaly {
  id: string;
  advancement: number;
  name: string;
  hidden: boolean;
}
export interface SCPCellLayer {
  id: string;
  name: string;
  rezzed: boolean;
  hidden: boolean;
}
export interface SCPCell {
  id: number;
  anomaly: SCPCellAnomaly | null;
  layers: SCPCellLayer[];
}

export interface SCPSeat {
  faction: SCPFaction;
  credits: number;
  ap: number;
  containment_points: number;
  liberation_points: number;
  total_breach: number;
  exposed: number;
  cells: SCPCell[];
  rig: SCPCard[];
  assets: SCPCard[];
  hand: SCPCard[] | null; // own hand only; null for opponent
  hand_count: number;
  deck_count: number;
  discard_count: number;
  identity: string | null;
}

export interface SCPTargets {
  containment: number;
  liberation: number;
  breach: number;
}

export interface SCPState {
  foundationId: string | null;
  insurgencyId: string | null;
  viewerFaction: SCPFaction | null;
  yourTurn: boolean;
  gameOver: boolean;
  winner: string | null;
  winReason: string | null;
  targets: SCPTargets;
  me: SCPSeat | null;
  opponent: SCPSeat | null;
}

export type SCPAction =
  | { type: 'GAIN' }
  | { type: 'DRAW' }
  | { type: 'PLAY'; cardId: string; cellId?: number; target?: string[] }
  | { type: 'ADVANCE'; anomalyId: string }
  | { type: 'CONTAIN'; anomalyId: string }
  | { type: 'INFILTRATE'; target: string[] }
  | { type: 'ACTIVATE'; cardId: string; target?: string[] }
  | { type: 'END_TURN' };

export interface UseSCPGameResult {
  state: SCPState | null;
  dispatch: (action: SCPAction) => void;
  isLoading: boolean;
  isConnected: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Projector — the server shape is already clean; type it with safe defaults.
// ---------------------------------------------------------------------------
function projectSeat(raw: unknown): SCPSeat | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const arr = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
  const n = (v: unknown): number => (typeof v === 'number' ? v : 0);
  return {
    faction: (r.faction as SCPFaction) ?? 'foundation',
    credits: n(r.credits),
    ap: n(r.ap),
    containment_points: n(r.containment_points),
    liberation_points: n(r.liberation_points),
    total_breach: n(r.total_breach),
    exposed: n(r.exposed),
    cells: arr<SCPCell>(r.cells),
    rig: arr<SCPCard>(r.rig),
    assets: arr<SCPCard>(r.assets),
    hand: Array.isArray(r.hand) ? (r.hand as SCPCard[]) : null,
    hand_count: n(r.hand_count),
    deck_count: n(r.deck_count),
    discard_count: n(r.discard_count),
    identity: (r.identity as string) ?? null,
  };
}

export function projectSCPState(raw: Record<string, unknown>): SCPState {
  const targets = (raw.targets as Record<string, number>) ?? {};
  return {
    foundationId: (raw.foundation_id as string) ?? null,
    insurgencyId: (raw.insurgency_id as string) ?? null,
    viewerFaction: (raw.viewer_faction as SCPFaction) ?? null,
    yourTurn: Boolean(raw.your_turn),
    gameOver: Boolean(raw.game_over),
    winner: (raw.winner as string) ?? null,
    winReason: (raw.win_reason as string) ?? null,
    targets: {
      containment: targets.containment ?? 6,
      liberation: targets.liberation ?? 7,
      breach: targets.breach ?? 24,
    },
    me: projectSeat(raw.me),
    opponent: projectSeat(raw.opponent),
  };
}

function buildWireRequest(action: SCPAction, playerId: string): PlayerActionRequest | null {
  const base = { player_id: playerId };
  switch (action.type) {
    case 'GAIN':
      return { ...base, action_type: 'SCP_GAIN' as ActionType };
    case 'DRAW':
      return { ...base, action_type: 'SCP_DRAW' as ActionType };
    case 'PLAY':
      return {
        ...base, action_type: 'SCP_PLAY' as ActionType, card_id: action.cardId,
        cell_id: action.cellId, scp_target: action.target,
      };
    case 'ADVANCE':
      return { ...base, action_type: 'SCP_ADVANCE' as ActionType, anomaly_id: action.anomalyId };
    case 'CONTAIN':
      return { ...base, action_type: 'SCP_CONTAIN' as ActionType, anomaly_id: action.anomalyId };
    case 'INFILTRATE':
      return { ...base, action_type: 'SCP_INFILTRATE' as ActionType, scp_target: action.target };
    case 'ACTIVATE':
      return { ...base, action_type: 'SCP_ACTIVATE' as ActionType, card_id: action.cardId, scp_target: action.target };
    case 'END_TURN':
      return { ...base, action_type: 'SCP_END_TURN' as ActionType };
    default:
      return null;
  }
}

export function useSCPGame(): UseSCPGameResult {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  const state = useMemo<SCPState | null>(() => {
    if (gameState) {
      const raw = (gameState as unknown as { scp?: Record<string, unknown> | null }).scp;
      if (raw) return projectSCPState(raw);
    }
    return null;
  }, [gameState]);

  const dispatch = useCallback(
    async (action: SCPAction) => {
      if (!matchId || !playerId) {
        // eslint-disable-next-line no-console
        console.log('[scp] dispatch ignored (no match)', action);
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
