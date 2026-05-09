/**
 * Deckbuilder API Client
 *
 * Handles all REST API calls for the deckbuilder feature.
 */

import type {
  DeckData,
  DeckStats,
  DeckEntry,
  CardSearchRequest,
  CardSearchResponse,
  DeckListResponse,
  ExportDeckResponse,
  CardDefinitionData,
  Game,
} from '../types/deckbuilder';
import type {
  SetDetail,
  SetListResponse,
  SetCardSearchRequest,
  SetCardSearchResponse,
} from '../types/gatherer';
import type {
  PokemonSetDetail,
  PokemonSetListResponse,
  PokemonSetCardFilter,
  PokemonCardSearchResponse,
  PokemonSortField,
  PokemonSortOrder,
} from '../types/pokemonGatherer';

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

// Deckbuilder API — every endpoint accepts an optional `game` to address a
// per-game card pool / deck list. Defaults to "mtg" for back-compat.
export const deckbuilderAPI = {
  // Card Search
  searchCards: (request: CardSearchRequest = {}): Promise<CardSearchResponse> =>
    fetchAPI('/deckbuilder/cards/search', {
      method: 'POST',
      body: JSON.stringify({
        game: request.game || 'mtg',
        query: request.query || null,
        types: request.types || [],
        colors: request.colors || [],
        cmc_min: request.cmc_min ?? null,
        cmc_max: request.cmc_max ?? null,
        text_search: request.text_search || null,
        limit: request.limit || 50,
        offset: request.offset || 0,
      }),
    }),

  getAllCards: (game: Game = 'mtg', limit = 100, offset = 0): Promise<CardSearchResponse> =>
    fetchAPI(`/deckbuilder/cards/all?game=${game}&limit=${limit}&offset=${offset}`),

  getCard: (cardName: string, game: Game = 'mtg'): Promise<CardDefinitionData> =>
    fetchAPI(`/deckbuilder/cards/${encodeURIComponent(cardName)}?game=${game}`),

  // Deck Management
  listDecks: (game?: Game): Promise<DeckListResponse> =>
    fetchAPI(`/deckbuilder/decks${game ? `?game=${game}` : ''}`),

  getDeck: (deckId: string): Promise<DeckData> =>
    fetchAPI(`/deckbuilder/decks/${deckId}`),

  saveDeck: (deck: {
    deck_id?: string;
    game?: Game;
    name: string;
    archetype: string;
    colors: string[];
    description: string;
    mainboard: DeckEntry[];
    sideboard?: DeckEntry[];
    format?: string;
  }): Promise<DeckData> =>
    fetchAPI('/deckbuilder/decks', {
      method: 'POST',
      body: JSON.stringify({
        deck_id: deck.deck_id || null,
        game: deck.game || 'mtg',
        name: deck.name,
        archetype: deck.archetype,
        colors: deck.colors,
        description: deck.description,
        mainboard: deck.mainboard,
        sideboard: deck.sideboard || [],
        format: deck.format || 'Standard',
      }),
    }),

  updateDeck: (deckId: string, deck: {
    game?: Game;
    name: string;
    archetype: string;
    colors: string[];
    description: string;
    mainboard: DeckEntry[];
    sideboard?: DeckEntry[];
    format?: string;
  }): Promise<DeckData> =>
    fetchAPI(`/deckbuilder/decks/${deckId}`, {
      method: 'PUT',
      body: JSON.stringify({
        game: deck.game || 'mtg',
        name: deck.name,
        archetype: deck.archetype,
        colors: deck.colors,
        description: deck.description,
        mainboard: deck.mainboard,
        sideboard: deck.sideboard || [],
        format: deck.format || 'Standard',
      }),
    }),

  deleteDeck: (deckId: string): Promise<{ status: string; deck_id: string }> =>
    fetchAPI(`/deckbuilder/decks/${deckId}`, { method: 'DELETE' }),

  // Statistics & Validation
  getDeckStats: (
    mainboard: DeckEntry[],
    sideboard: DeckEntry[] = [],
    game: Game = 'mtg',
  ): Promise<DeckStats> =>
    fetchAPI('/deckbuilder/decks/stats', {
      method: 'POST',
      body: JSON.stringify({ game, mainboard, sideboard }),
    }),

  validateDeck: (
    mainboard: DeckEntry[],
    sideboard: DeckEntry[] = [],
    game: Game = 'mtg',
  ): Promise<{
    is_valid: boolean;
    errors: string[];
    missing_cards: string[];
  }> =>
    fetchAPI('/deckbuilder/decks/validate', {
      method: 'POST',
      body: JSON.stringify({ game, mainboard, sideboard }),
    }),

  // Import/Export
  importDeck: (text: string, format = 'Standard', game: Game = 'mtg'): Promise<DeckData> =>
    fetchAPI('/deckbuilder/import', {
      method: 'POST',
      body: JSON.stringify({ text, format, game }),
    }),

  exportDeck: (deckId: string): Promise<ExportDeckResponse> =>
    fetchAPI(`/deckbuilder/export/${deckId}`),

  // LLM Deck Building
  llmBuildDeck: (prompt: string, colors?: string[], format = 'Standard'): Promise<{
    success: boolean;
    deck?: DeckData;
    error?: string;
  }> =>
    fetchAPI('/deckbuilder/llm/build', {
      method: 'POST',
      body: JSON.stringify({ prompt, colors, format }),
    }),

  // Hybrid (heuristic + LLM polish) Deck Building
  // Posts to W3's /deckbuilder/hybrid/build route. Returns the polished
  // deck plus a list of swap-audit entries the UI can display so the
  // user can see what the LLM changed about the heuristic skeleton.
  hybridBuildDeck: (
    archetype: string,
    colors: string[],
    setCodes: string[],
    polish = true,
    userHint = '',
    name = 'Hybrid Build',
  ): Promise<{
    success: boolean;
    deck?: DeckData;
    skeleton?: DeckData;
    swaps?: Array<{ out: string; in: string; reason?: string; qty?: number }>;
    error?: string;
  }> =>
    fetchAPI('/deckbuilder/hybrid/build', {
      method: 'POST',
      body: JSON.stringify({
        name,
        archetype,
        colors,
        set_codes: setCodes,
        user_hint: userHint,
        polish,
      }),
    }),

  llmSuggestCards: (deckId: string, prompt: string): Promise<{
    success: boolean;
    suggestions?: {
      analysis: string;
      suggestions: Array<{
        action: 'add' | 'remove' | 'adjust';
        card: string;
        from_qty: number;
        to_qty: number;
        reason: string;
      }>;
      priority_changes: string[];
    };
    error?: string;
  }> =>
    fetchAPI('/deckbuilder/llm/suggest', {
      method: 'POST',
      body: JSON.stringify({ deck_id: deckId, prompt }),
    }),

  llmStatus: (): Promise<{
    available: boolean;
    provider: string | null;
    message: string;
  }> =>
    fetchAPI('/deckbuilder/llm/status'),
};

// Gatherer API (Set Browsing)
export const gathererAPI = {
  // Get all sets
  getSets: (setType?: string): Promise<SetListResponse> => {
    const params = setType ? `?set_type=${setType}` : '';
    return fetchAPI(`/deckbuilder/sets${params}`);
  },

  // Get set details
  getSetDetails: (setCode: string): Promise<SetDetail> =>
    fetchAPI(`/deckbuilder/sets/${setCode}`),

  // Get cards in a set with filters
  getSetCards: (setCode: string, request: SetCardSearchRequest = {}): Promise<SetCardSearchResponse> =>
    fetchAPI(`/deckbuilder/sets/${setCode}/cards`, {
      method: 'POST',
      body: JSON.stringify({
        types: request.types || [],
        colors: request.colors || [],
        rarity: request.rarity || null,
        cmc_min: request.cmc_min ?? null,
        cmc_max: request.cmc_max ?? null,
        text_search: request.text_search || null,
        sort_by: request.sort_by || 'name',
        sort_order: request.sort_order || 'asc',
        limit: request.limit || 50,
        offset: request.offset || 0,
      }),
    }),
};

// Pokemon Gatherer API
interface PokemonGetCardsOptions extends PokemonSetCardFilter {
  sortBy?: PokemonSortField;
  sortOrder?: PokemonSortOrder;
  limit?: number;
  offset?: number;
}

function pokemonQueryString(opts: PokemonGetCardsOptions): string {
  const params = new URLSearchParams();
  const add = (k: string, v: unknown) => {
    if (v === undefined || v === null || v === '') return;
    params.set(k, String(v));
  };
  add('supertype', opts.supertype);
  add('trainer_subtype', opts.trainerSubtype);
  add('pokemon_type', opts.pokemonType);
  add('evolution_stage', opts.evolutionStage);
  if (opts.isEx !== undefined) add('is_ex', opts.isEx);
  add('hp_min', opts.hpMin);
  add('hp_max', opts.hpMax);
  add('retreat_cost_min', opts.retreatCostMin);
  add('retreat_cost_max', opts.retreatCostMax);
  add('guild', opts.guild);
  add('text_search', opts.textSearch);
  add('sort_by', opts.sortBy ?? 'name');
  add('sort_order', opts.sortOrder ?? 'asc');
  add('limit', opts.limit ?? 50);
  add('offset', opts.offset ?? 0);
  return params.toString();
}

export const pokemonGathererAPI = {
  getSets: (setType?: string): Promise<PokemonSetListResponse> => {
    const params = setType ? `?set_type=${setType}` : '';
    return fetchAPI(`/pokemon/sets${params}`);
  },

  getSetDetails: (setCode: string): Promise<PokemonSetDetail> =>
    fetchAPI(`/pokemon/sets/${setCode}`),

  getSetCards: (
    setCode: string,
    options: PokemonGetCardsOptions = {}
  ): Promise<PokemonCardSearchResponse> => {
    const qs = pokemonQueryString(options);
    return fetchAPI(`/pokemon/sets/${setCode}/cards${qs ? `?${qs}` : ''}`);
  },
};
