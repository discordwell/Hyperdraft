/**
 * useCatsGame Hook
 *
 * Cats-engine game state + action dispatch. Mirrors the shape of
 * useMinecraftGame / useHSGame: subscribes to gameState via useSocket, then
 * projects the nested `gameState.cats` payload (built by the server's
 * cats serializer in session.py) into the CatsState shape the cats.tsx
 * board renders.
 *
 * Action protocol:
 *  - CATS_PLAY_CARD  { card_id }     — commit a card to the current trick
 *  - CATS_CLAIM_PILE { pile_name }   — winner picks a pile (UI shorthand);
 *                                      sent to the server as CATS_CHOOSE_PILE
 *                                      with pile_name=`pile_<name>`.
 */
import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';
import { matchAPI } from '../services/api';
import type { ActionType } from '../types';

// ---------------------------------------------------------------------------
// Local types — the canonical wire shape for cats. Sourced from
// src/server/session.py:_serialize_cats_state.
// ---------------------------------------------------------------------------

export type CatsCategory = 'Sleek' | 'Fluffy' | 'Scrappy' | 'Sneaky';
export type CatsCardType = 'Cat' | 'Mood' | 'Snack' | 'Trinket' | 'Commander';
export type CatsPileName = 'territory' | 'nap' | 'snack' | 'attention';
export type CatsPhase =
  | 'stretch'
  | 'pounce'
  | 'counter_pounce'
  | 'resolve'
  | 'claim'
  | 'curl_up';
export type CatsSeat = 'me' | 'opponent';

export interface CatsCard {
  id: string;
  name: string;
  value: number; // 1-10 for cats; 0 for moods
  category?: CatsCategory;
  card_type: CatsCardType;
  text?: string;
  tapped?: boolean; // "knocked over"
  // Server-computed flag: this card lives in the viewer's own pile,
  // is currently untapped, and has a registered CATS_KNOCK_OVER
  // handler. Only set for cards in the viewer's piles — opponent
  // cards and hand cards always have this undefined.
  is_activatable?: boolean;
}

export interface CatsPiles {
  territory: CatsCard[];
  nap: CatsCard[];
  snack: CatsCard[];
  attention: CatsCard[];
}

export interface PlayerState {
  hand: CatsCard[];
  piles: CatsPiles;
  commander: CatsCard | null;
}

export interface ScoreBreakdown {
  territory: number;
  nap: number;
  snack: number;
  attention: number;
  total: number;
}

export interface CatsTrick {
  pounce_card: CatsCard | null;
  counter_card: CatsCard | null;
  winner: CatsSeat | null;
  installed_rule: CatsCategory | null;
}

export interface CatsState {
  round_number: number; // 1..9
  phase: CatsPhase;
  lead_player: CatsSeat;
  current_trick: CatsTrick;
  player: PlayerState;
  opponent: PlayerState;
  game_over: boolean;
  final_scores?: { me: ScoreBreakdown; opponent: ScoreBreakdown };
}

// Action vocab — the cats.tsx board emits CATS_PLAY_CARD and CATS_CLAIM_PILE.
// CATS_CLAIM_PILE is the UI/local name; we translate to the server's
// CATS_CHOOSE_PILE wire action when dispatching.
export type CatsAction =
  | { type: 'CATS_PLAY_CARD'; cardId: string }
  | { type: 'CATS_CLAIM_PILE'; pile: Exclude<CatsPileName, 'attention'> }
  | { type: 'CATS_KNOCK_OVER'; cardId: string }
  | { type: 'CATS_END_ROUND' };

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseCatsGameResult {
  state: CatsState | null;
  sendAction: (action: CatsAction) => void;
  isLoading: boolean;
  isConnected: boolean;
  error: string | null;
}

const PILE_NAME_TO_SERVER: Record<Exclude<CatsPileName, 'attention'>, string> = {
  territory: 'pile_territory',
  nap: 'pile_nap',
  snack: 'pile_snack',
};

export function useCatsGame(): UseCatsGameResult {
  const store = useGameStore();
  const { matchId, playerId, gameState, setGameState, setError } = store;

  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  // Project the server's nested `cats` payload into CatsState. The backend
  // already gives us a seat-relative shape (player vs opponent), so this is
  // mostly a passthrough with a type assertion.
  const state = useMemo<CatsState | null>(() => {
    if (!gameState) return null;
    const cats = (gameState as unknown as { cats?: CatsState | null }).cats;
    if (!cats) return null;
    return cats;
  }, [gameState]);

  const sendAction = useCallback(
    async (action: CatsAction) => {
      if (!matchId || !playerId) return;
      let request: { action_type: ActionType; player_id: string; card_id?: string; pile_name?: string };
      if (action.type === 'CATS_PLAY_CARD') {
        request = {
          action_type: 'CATS_PLAY_CARD' as ActionType,
          player_id: playerId,
          card_id: action.cardId,
        };
      } else if (action.type === 'CATS_CLAIM_PILE') {
        request = {
          action_type: 'CATS_CHOOSE_PILE' as ActionType,
          player_id: playerId,
          pile_name: PILE_NAME_TO_SERVER[action.pile],
        };
      } else if (action.type === 'CATS_KNOCK_OVER') {
        request = {
          action_type: 'CATS_KNOCK_OVER' as ActionType,
          player_id: playerId,
          card_id: action.cardId,
        };
      } else {
        return; // CATS_END_ROUND unused for v1 — rounds auto-advance server-side.
      }
      try {
        const result = await matchAPI.submitAction(matchId, request as unknown as Parameters<typeof matchAPI.submitAction>[1]);
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

  return { state, sendAction, isLoading, isConnected, error };
}
