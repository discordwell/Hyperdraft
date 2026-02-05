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
} from '../types/deckbuilder';
import type {
  SetDetail,
  SetListResponse,
  SetCardSearchRequest,
  SetCardSearchResponse,
} from '../types/gatherer';

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

// Deckbuilder API
export const deckbuilderAPI = {
  // Card Search
  searchCards: (request: CardSearchRequest = {}): Promise<CardSearchResponse> =>
    fetchAPI('/deckbuilder/cards/search', {
      method: 'POST',
      body: JSON.stringify({
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

  getAllCards: (limit = 100, offset = 0): Promise<CardSearchResponse> =>
    fetchAPI(`/deckbuilder/cards/all?limit=${limit}&offset=${offset}`),

  getCard: (cardName: string): Promise<CardDefinitionData> =>
    fetchAPI(`/deckbuilder/cards/${encodeURIComponent(cardName)}`),

  // Deck Management
  listDecks: (): Promise<DeckListResponse> =>
    fetchAPI('/deckbuilder/decks'),

  getDeck: (deckId: string): Promise<DeckData> =>
    fetchAPI(`/deckbuilder/decks/${deckId}`),

  saveDeck: (deck: {
    deck_id?: string;
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
  getDeckStats: (mainboard: DeckEntry[], sideboard: DeckEntry[] = []): Promise<DeckStats> =>
    fetchAPI('/deckbuilder/decks/stats', {
      method: 'POST',
      body: JSON.stringify({ mainboard, sideboard }),
    }),

  validateDeck: (mainboard: DeckEntry[], sideboard: DeckEntry[] = []): Promise<{
    is_valid: boolean;
    errors: string[];
    missing_cards: string[];
  }> =>
    fetchAPI('/deckbuilder/decks/validate', {
      method: 'POST',
      body: JSON.stringify({ mainboard, sideboard }),
    }),

  // Import/Export
  importDeck: (text: string, format = 'Standard'): Promise<DeckData> =>
    fetchAPI('/deckbuilder/import', {
      method: 'POST',
      body: JSON.stringify({ text, format }),
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
