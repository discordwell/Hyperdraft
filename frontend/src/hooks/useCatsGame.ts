/**
 * useCatsGame Hook
 *
 * Cats-engine game state + action dispatch. Mirrors the shape of
 * useMinecraftGame / useHSGame so a future GameView page can drop this in
 * without ceremony.
 *
 * Backend wiring (the FastAPI route + socket payload schema) is not yet
 * shipped; until it lands, this hook surfaces a deterministic mock state so
 * the cats.tsx page renders end-to-end during design / wet-test. The mock
 * is gated behind a single feature flag at the top of the file — flip it
 * off (or delete the branch) once the real socket payload exists.
 */
import { useCallback, useMemo } from 'react';
import { useGameStore } from '../stores/gameStore';
import { useSocket } from './useSocket';

// ---------------------------------------------------------------------------
// Local types — kept self-contained until the backend defines the canonical
// shape. When the server wire-up lands these can be promoted to types/game.ts.
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

// Action vocab — these strings will become real ActionType members once
// the server route lands. Until then the hook accepts them locally.
export type CatsAction =
  | { type: 'CATS_PLAY_CARD'; cardId: string }
  | { type: 'CATS_CLAIM_PILE'; pile: Exclude<CatsPileName, 'attention'> }
  | { type: 'CATS_KNOCK_OVER'; cardId: string }
  | { type: 'CATS_END_ROUND' };

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

// Flip to false (or delete the whole branch) once the real socket payload
// flows through useGameStore.gameState.
const USE_MOCK_DATA = true;

function mockState(): CatsState {
  const myHand: CatsCard[] = [
    {
      id: 'me-h-1',
      name: 'Mister Whiskers',
      value: 7,
      category: 'Sleek',
      card_type: 'Cat',
      text: 'When this enters a pile: peek at opponent\'s hand.',
    },
    {
      id: 'me-h-2',
      name: 'Sir Reginald Loafington',
      value: 6,
      category: 'Fluffy',
      card_type: 'Cat',
      text: 'Knock over: +1 Value to any played Fluffy cat this round.',
    },
    {
      id: 'me-h-3',
      name: 'The 3 a.m. Zoomies',
      value: 0,
      card_type: 'Mood',
      text: 'Tonight everyone is unhinged. Lowest Value wins this trick.',
    },
    {
      id: 'me-h-4',
      name: 'Catnip Mouse',
      value: 2,
      category: 'Sleek',
      card_type: 'Snack',
      text: 'When this enters your Snack pile, draw a card.',
    },
    {
      id: 'me-h-5',
      name: 'Greg',
      value: 4,
      category: 'Scrappy',
      card_type: 'Cat',
      text: 'Greg has seen things.',
    },
  ];

  const myTerritory: CatsCard[] = [
    {
      id: 'me-t-1',
      name: 'Aggressive Loafing',
      value: 5,
      category: 'Fluffy',
      card_type: 'Cat',
      text: 'Cannot be moved. Refuses.',
    },
    {
      id: 'me-t-2',
      name: 'Sitting In The Box',
      value: 3,
      category: 'Sleek',
      card_type: 'Cat',
      text: 'If it fits, it sits.',
      tapped: true,
    },
  ];

  const myNap: CatsCard[] = [
    {
      id: 'me-n-1',
      name: 'Lord Fluffinbottom',
      value: 8,
      category: 'Fluffy',
      card_type: 'Cat',
      text: 'Generously distributes hair on all surfaces.',
    },
  ];

  const oppHand: CatsCard[] = Array.from({ length: 5 }, (_, i) => ({
    id: `opp-h-${i + 1}`,
    name: 'Hidden Cat',
    value: 0,
    card_type: 'Cat' as const,
  }));

  const oppTerritory: CatsCard[] = [
    {
      id: 'opp-t-1',
      name: 'Princess Mayhem the Third',
      value: 9,
      category: 'Sneaky',
      card_type: 'Cat',
      text: 'Royalty. Naturally.',
    },
  ];

  const oppSnack: CatsCard[] = [
    {
      id: 'opp-s-1',
      name: 'Tuna Can',
      value: 1,
      category: 'Sleek',
      card_type: 'Snack',
      text: 'A negotiation lubricant.',
    },
    {
      id: 'opp-s-2',
      name: 'Knocking Things Off Tables',
      value: 5,
      category: 'Scrappy',
      card_type: 'Cat',
      text: 'Gravity is, in fact, a hypothesis worth testing.',
    },
  ];

  return {
    round_number: 3,
    phase: 'pounce',
    lead_player: 'me',
    current_trick: {
      pounce_card: null,
      counter_card: null,
      winner: null,
      installed_rule: null,
    },
    player: {
      hand: myHand,
      piles: {
        territory: myTerritory,
        nap: myNap,
        snack: [],
        attention: [],
      },
      commander: {
        id: 'me-cmd',
        name: 'Karen the Dignified Calico',
        value: 0,
        card_type: 'Commander',
        text: 'Your Snack pile cap is 7 instead of 5.',
      },
    },
    opponent: {
      hand: oppHand,
      piles: {
        territory: oppTerritory,
        nap: [],
        snack: oppSnack,
        attention: [],
      },
      commander: {
        id: 'opp-cmd',
        name: 'Gary the One-Eyed Tabby',
        value: 0,
        card_type: 'Commander',
        text: 'Once per round, peek at the top card of your deck.',
      },
    },
    game_over: false,
  };
}

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

export function useCatsGame(): UseCatsGameResult {
  const store = useGameStore();
  const { matchId, playerId, gameState, setError } = store;

  // Wire socket presence even when the payload isn't routed yet. Once the
  // server sends a cats GameState, useGameStore.gameState will carry it
  // and we drop the mock path.
  const { isConnected } = useSocket({
    matchId: matchId || undefined,
    playerId: playerId || undefined,
    isSpectator: false,
    onError: (msg) => setError(msg),
  });

  const state = useMemo<CatsState | null>(() => {
    if (USE_MOCK_DATA) return mockState();
    // TODO: project gameState (server payload) into CatsState. Until the
    // server schema is finalized this branch returns null and the page
    // renders an empty board.
    if (!gameState) return null;
    const anyState = gameState as unknown as Record<string, unknown>;
    const projected = anyState['cats'] as CatsState | undefined;
    return projected ?? null;
  }, [gameState]);

  const sendAction = useCallback(
    (action: CatsAction) => {
      // Server route is not wired yet; while USE_MOCK_DATA is on we log so
      // wet-tests can see player intent. Once the route exists, swap this
      // for `matchAPI.submitAction(matchId, { action_type, player_id, ... })`
      // following the useMinecraftGame.ts pattern.
      if (USE_MOCK_DATA) {
        // eslint-disable-next-line no-console
        console.debug('[cats] mock sendAction', action);
        return;
      }
      if (!matchId || !playerId) return;
      // TODO: dispatch through matchAPI.submitAction once ActionType union
      // gains CATS_* members.
    },
    [matchId, playerId],
  );

  const isLoading = !USE_MOCK_DATA && !state;
  const error = store.ui?.error ?? null;

  return { state, sendAction, isLoading, isConnected, error };
}
