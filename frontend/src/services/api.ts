/**
 * REST API Client
 *
 * Handles all REST API calls to the Hyperdraft backend.
 */

import type {
  CreateMatchRequest,
  CreateMatchResponse,
  GameState,
  PlayerActionRequest,
  ActionResultResponse,
  StartBotGameRequest,
  BotGameResponse,
  BotGameStatus,
  ReplayResponse,
  CardListResponse,
  CardDefinitionData,
  DeckSummary,
  YgoDeckSummary,
} from '../types';

const API_BASE = '/api';

// Generic fetch wrapper with error handling
async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API Error: ${response.status}`);
  }

  return response.json();
}

// Match API
export const matchAPI = {
  listDecks: (): Promise<{ decks: DeckSummary[]; total: number }> =>
    fetchAPI('/match/decks'),

  listYgoDecks: (): Promise<{ decks: YgoDeckSummary[] }> =>
    fetchAPI('/match/ygo-decks'),

  create: (request: Partial<CreateMatchRequest> & { variant?: string; hero_class?: string } = {}): Promise<CreateMatchResponse> =>
    fetchAPI('/match/create', {
      method: 'POST',
      body: JSON.stringify({
        mode: 'human_vs_bot',
        game_mode: 'mtg',
        player_name: 'Player',
        ai_difficulty: 'medium',
        ...request,
      }),
    }),

  start: (matchId: string): Promise<{ status: string; match_id: string }> =>
    fetchAPI(`/match/${matchId}/start`, { method: 'POST' }),

  getState: (matchId: string, playerId?: string): Promise<GameState> => {
    const params = playerId ? `?player_id=${playerId}` : '';
    return fetchAPI(`/match/${matchId}/state${params}`);
  },

  submitAction: (
    matchId: string,
    action: PlayerActionRequest
  ): Promise<ActionResultResponse> =>
    fetchAPI(`/match/${matchId}/action`, {
      method: 'POST',
      body: JSON.stringify(action),
    }),

  concede: (
    matchId: string,
    playerId: string
  ): Promise<{ status: string; winner: string }> =>
    fetchAPI(`/match/${matchId}/concede?player_id=${playerId}`, {
      method: 'POST',
    }),

  delete: (matchId: string): Promise<{ status: string; match_id: string }> =>
    fetchAPI(`/match/${matchId}`, { method: 'DELETE' }),

  getReplay: (matchId: string, options?: { since?: number; limit?: number }): Promise<ReplayResponse> => {
    const params = new URLSearchParams();
    if (options?.since !== undefined) params.set('since', options.since.toString());
    if (options?.limit !== undefined) params.set('limit', options.limit.toString());
    const query = params.toString();
    return fetchAPI(`/match/${matchId}/replay${query ? `?${query}` : ''}`);
  },

  getReplayManifest: (matchId: string): Promise<{
    match_id: string;
    game_mode: string | null;
    total_frames: number;
    is_complete: boolean;
    marks: { frame: number; turn: number; phase: string }[];
  }> => fetchAPI(`/match/${matchId}/replay/manifest`),

  listReplays: (limit: number = 30): Promise<{
    replays: {
      match_id: string;
      game_mode: string | null;
      winner: string | null;
      total_turns: number | null;
      total_frames: number;
      archived_at: number;
    }[];
    total: number;
  }> => fetchAPI(`/match/replays/list?limit=${limit}`),

  submitChoice: (
    matchId: string,
    choiceId: string,
    playerId: string,
    selected: string[]
  ): Promise<ActionResultResponse> =>
    fetchAPI(`/match/${matchId}/choice`, {
      method: 'POST',
      body: JSON.stringify({
        choice_id: choiceId,
        player_id: playerId,
        selected,
      }),
    }),
};

// Bot Game API
export const botGameAPI = {
  start: (request: Partial<StartBotGameRequest> = {}): Promise<BotGameResponse> =>
    fetchAPI('/bot-game/start', {
      method: 'POST',
      body: JSON.stringify({
        bot1_deck: [],
        bot2_deck: [],
        bot1_difficulty: 'medium',
        bot2_difficulty: 'medium',
        bot1_brain: 'heuristic',
        bot2_brain: 'heuristic',
        delay_ms: 1000,
        ...request,
      }),
    }),

  getState: (gameId: string): Promise<GameState> =>
    fetchAPI(`/bot-game/${gameId}/state`),

  getStatus: (gameId: string): Promise<BotGameStatus> =>
    fetchAPI(`/bot-game/${gameId}/status`),

  getReplay: (gameId: string, options?: { since?: number; limit?: number }): Promise<ReplayResponse> => {
    const params = new URLSearchParams();
    if (options?.since !== undefined) params.set('since', options.since.toString());
    if (options?.limit !== undefined) params.set('limit', options.limit.toString());
    const query = params.toString();
    return fetchAPI(`/bot-game/${gameId}/replay${query ? `?${query}` : ''}`);
  },

  list: (status?: 'running' | 'finished'): Promise<{ games: BotGameStatus[]; total: number }> => {
    const params = status ? `?status=${status}` : '';
    return fetchAPI(`/bot-game/list${params}`);
  },

  delete: (gameId: string): Promise<{ status: string; game_id: string }> =>
    fetchAPI(`/bot-game/${gameId}`, { method: 'DELETE' }),
};

// Cards API
export const cardsAPI = {
  list: (options: {
    type_filter?: string;
    color_filter?: string;
    name_search?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<CardListResponse> => {
    const params = new URLSearchParams();
    if (options.type_filter) params.set('type_filter', options.type_filter);
    if (options.color_filter) params.set('color_filter', options.color_filter);
    if (options.name_search) params.set('name_search', options.name_search);
    if (options.limit) params.set('limit', options.limit.toString());
    if (options.offset) params.set('offset', options.offset.toString());

    const queryString = params.toString();
    return fetchAPI(`/cards${queryString ? `?${queryString}` : ''}`);
  },

  get: (cardName: string): Promise<CardDefinitionData> =>
    fetchAPI(`/cards/${encodeURIComponent(cardName)}`),

  getTypes: (): Promise<{ types: string[] }> =>
    fetchAPI('/cards/types/list'),

  getColors: (): Promise<{ colors: string[] }> =>
    fetchAPI('/cards/colors/list'),
};

// ────────────────────────────────────────────────────────────────────────
// Pipeline-the-Game v0.2 — HD-CRIT-002 §06
// ────────────────────────────────────────────────────────────────────────

export interface PipelineCardSnapshot {
  id: string;
  engine: string;
  stage: 'TRANSFORM' | 'PREVENT' | 'RESOLVE' | 'REACT';
  cost: number;
  name: string;
  text: string;
  art: 'tri' | 'bar' | 'square' | 'circle' | 'grid';
}

export interface PipelineEventSnapshot {
  id: string;
  type: string;
  payload: Record<string, unknown>;
}

export interface PipelineImpact {
  damage_dealt: number;
  life_gained: number;
  cards_drawn: number;
  cards_destroyed: number;
  prevented: number;
  total: number;
}

export interface PipelineResolution {
  winner: string | null;
  a_impact: PipelineImpact;
  b_impact: PipelineImpact;
  log: string[];
}

export interface PipelineSnapshot {
  match_id: string;
  player_a_id: string;
  player_b_id: string;
  hands: Record<string, PipelineCardSnapshot[]>;
  slots: Record<string, Record<string, PipelineCardSnapshot | null>>;
  current_event: PipelineEventSnapshot;
  event_idx: number;
  turn: number;
  tricks: Record<string, number>;
  phase: 'slot' | 'resolving' | 'won';
  winner: string | null;
  last_trick: {
    winner: string | null;
    a_impact: PipelineImpact;
    b_impact: PipelineImpact;
    log: string[];
  } | null;
  deck_count: Record<string, number>;
}

export interface PipelineStartResponse {
  match_id: string;
  player_id: string;
  snapshot: PipelineSnapshot;
}

export interface PipelinePlayResponse {
  snapshot: PipelineSnapshot;
  trick_resolved: boolean;
  resolution: PipelineResolution | null;
}

export const pipelineAPI = {
  start: (
    opts: { deck_a_id?: string; deck_b_id?: string; rng_seed?: number } = {},
  ): Promise<PipelineStartResponse> =>
    fetchAPI('/pipeline/start', {
      method: 'POST',
      body: JSON.stringify(opts),
    }),
  getState: (matchId: string): Promise<PipelineSnapshot> =>
    fetchAPI(`/pipeline/${matchId}`),
  playCard: (
    matchId: string,
    playerId: string,
    cardId: string,
  ): Promise<PipelinePlayResponse> =>
    fetchAPI(`/pipeline/${matchId}/play`, {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId, card_id: cardId }),
    }),
  reshuffle: (matchId: string): Promise<PipelineStartResponse> =>
    fetchAPI(`/pipeline/${matchId}/reshuffle`, {
      method: 'POST',
      body: '{}',
    }),
};

// Health check
export const healthCheck = (): Promise<{ status: string; service: string }> =>
  fetchAPI('/health');
