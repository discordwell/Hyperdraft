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
  create: (request: Partial<CreateMatchRequest> = {}): Promise<CreateMatchResponse> =>
    fetchAPI('/match/create', {
      method: 'POST',
      body: JSON.stringify({
        mode: 'human_vs_bot',
        player_deck: [],
        player_name: 'Player',
        ai_difficulty: 'medium',
        ai_deck: [],
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
        delay_ms: 1000,
        ...request,
      }),
    }),

  getState: (gameId: string): Promise<GameState> =>
    fetchAPI(`/bot-game/${gameId}/state`),

  getStatus: (gameId: string): Promise<BotGameStatus> =>
    fetchAPI(`/bot-game/${gameId}/status`),

  getReplay: (gameId: string): Promise<ReplayResponse> =>
    fetchAPI(`/bot-game/${gameId}/replay`),

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

// Health check
export const healthCheck = (): Promise<{ status: string; service: string }> =>
  fetchAPI('/health');
