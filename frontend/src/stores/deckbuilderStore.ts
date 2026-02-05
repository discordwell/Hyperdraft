/**
 * Deckbuilder State Store
 *
 * Zustand store for managing deckbuilder state.
 */

import { create } from 'zustand';
import type {
  DeckData,
  DeckStats,
  DeckSummary,
  CardDefinitionData,
  CardFilter,
} from '../types/deckbuilder';
import { deckbuilderAPI } from '../services/deckbuilderApi';

interface DeckbuilderStore {
  // Current deck being edited
  currentDeck: DeckData;

  // Deck statistics (computed from API)
  deckStats: DeckStats | null;

  // Card browser state
  searchResults: CardDefinitionData[];
  searchTotal: number;
  searchLoading: boolean;
  cardFilter: CardFilter;

  // Saved decks
  savedDecks: DeckSummary[];

  // UI state
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  hasUnsavedChanges: boolean;

  // Deck actions
  newDeck: () => void;
  setDeckName: (name: string) => void;
  setDeckArchetype: (archetype: string) => void;
  setDeckColors: (colors: string[]) => void;
  setDeckDescription: (description: string) => void;
  setDeckFormat: (format: string) => void;

  // Card management
  addCard: (cardName: string, toSideboard?: boolean) => void;
  removeCard: (cardName: string, fromSideboard?: boolean) => void;
  setCardQuantity: (cardName: string, quantity: number, inSideboard?: boolean) => void;
  clearDeck: () => void;

  // Search
  setCardFilter: (filter: Partial<CardFilter>) => void;
  searchCards: () => Promise<void>;
  loadMoreCards: () => Promise<void>;

  // Persistence
  loadDeck: (deckId: string) => Promise<void>;
  saveDeck: () => Promise<void>;
  deleteDeck: (deckId: string) => Promise<void>;
  loadSavedDecks: () => Promise<void>;

  // Import/Export
  importDeck: (text: string) => Promise<void>;
  exportDeck: () => Promise<string>;

  // Stats
  refreshStats: () => Promise<void>;

  // Error handling
  setError: (error: string | null) => void;
  clearError: () => void;
}

const emptyDeck: DeckData = {
  name: 'Untitled Deck',
  archetype: 'Aggro',
  colors: [],
  description: '',
  mainboard: [],
  sideboard: [],
  format: 'Standard',
};

export const useDeckbuilderStore = create<DeckbuilderStore>((set, get) => ({
  // Initial state
  currentDeck: { ...emptyDeck },
  deckStats: null,
  searchResults: [],
  searchTotal: 0,
  searchLoading: false,
  cardFilter: {},
  savedDecks: [],
  isLoading: false,
  isSaving: false,
  error: null,
  hasUnsavedChanges: false,

  // Deck actions
  newDeck: () => {
    set({
      currentDeck: { ...emptyDeck },
      deckStats: null,
      hasUnsavedChanges: false,
    });
  },

  setDeckName: (name) => {
    set((state) => ({
      currentDeck: { ...state.currentDeck, name },
      hasUnsavedChanges: true,
    }));
  },

  setDeckArchetype: (archetype) => {
    set((state) => ({
      currentDeck: { ...state.currentDeck, archetype },
      hasUnsavedChanges: true,
    }));
  },

  setDeckColors: (colors) => {
    set((state) => ({
      currentDeck: { ...state.currentDeck, colors },
      hasUnsavedChanges: true,
    }));
  },

  setDeckDescription: (description) => {
    set((state) => ({
      currentDeck: { ...state.currentDeck, description },
      hasUnsavedChanges: true,
    }));
  },

  setDeckFormat: (format) => {
    set((state) => ({
      currentDeck: { ...state.currentDeck, format },
      hasUnsavedChanges: true,
    }));
  },

  // Card management
  addCard: (cardName, toSideboard = false) => {
    set((state) => {
      const board = toSideboard ? 'sideboard' : 'mainboard';
      const cards = [...state.currentDeck[board]];

      const existingIndex = cards.findIndex((e) => e.card === cardName);
      if (existingIndex >= 0) {
        cards[existingIndex] = {
          ...cards[existingIndex],
          qty: cards[existingIndex].qty + 1,
        };
      } else {
        cards.push({ card: cardName, qty: 1 });
      }

      // Update colors based on card
      const cardDef = state.searchResults.find((c) => c.name === cardName);
      let newColors = [...state.currentDeck.colors];
      if (cardDef && cardDef.colors) {
        for (const color of cardDef.colors) {
          const colorCode = color[0]; // W, U, B, R, G
          if (!newColors.includes(colorCode)) {
            newColors.push(colorCode);
          }
        }
      }

      return {
        currentDeck: {
          ...state.currentDeck,
          [board]: cards,
          colors: newColors,
        },
        hasUnsavedChanges: true,
      };
    });

    // Refresh stats after adding card
    get().refreshStats();
  },

  removeCard: (cardName, fromSideboard = false) => {
    set((state) => {
      const board = fromSideboard ? 'sideboard' : 'mainboard';
      const cards = [...state.currentDeck[board]];

      const existingIndex = cards.findIndex((e) => e.card === cardName);
      if (existingIndex >= 0) {
        if (cards[existingIndex].qty > 1) {
          cards[existingIndex] = {
            ...cards[existingIndex],
            qty: cards[existingIndex].qty - 1,
          };
        } else {
          cards.splice(existingIndex, 1);
        }
      }

      return {
        currentDeck: {
          ...state.currentDeck,
          [board]: cards,
        },
        hasUnsavedChanges: true,
      };
    });

    // Refresh stats after removing card
    get().refreshStats();
  },

  setCardQuantity: (cardName, quantity, inSideboard = false) => {
    set((state) => {
      const board = inSideboard ? 'sideboard' : 'mainboard';
      const cards = [...state.currentDeck[board]];

      const existingIndex = cards.findIndex((e) => e.card === cardName);
      if (quantity <= 0) {
        if (existingIndex >= 0) {
          cards.splice(existingIndex, 1);
        }
      } else if (existingIndex >= 0) {
        cards[existingIndex] = { ...cards[existingIndex], qty: quantity };
      } else {
        cards.push({ card: cardName, qty: quantity });
      }

      return {
        currentDeck: {
          ...state.currentDeck,
          [board]: cards,
        },
        hasUnsavedChanges: true,
      };
    });

    get().refreshStats();
  },

  clearDeck: () => {
    set((state) => ({
      currentDeck: {
        ...state.currentDeck,
        mainboard: [],
        sideboard: [],
        colors: [],
      },
      deckStats: null,
      hasUnsavedChanges: true,
    }));
  },

  // Search
  setCardFilter: (filter) => {
    set((state) => ({
      cardFilter: { ...state.cardFilter, ...filter },
    }));
  },

  searchCards: async () => {
    const { cardFilter } = get();
    set({ searchLoading: true, error: null });

    try {
      const response = await deckbuilderAPI.searchCards({
        query: cardFilter.query,
        types: cardFilter.types,
        colors: cardFilter.colors,
        cmc_min: cardFilter.cmcMin,
        cmc_max: cardFilter.cmcMax,
        text_search: cardFilter.textSearch,
        limit: 50,
        offset: 0,
      });

      set({
        searchResults: response.cards,
        searchTotal: response.total,
        searchLoading: false,
      });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Search failed',
        searchLoading: false,
      });
    }
  },

  loadMoreCards: async () => {
    const { cardFilter, searchResults } = get();
    set({ searchLoading: true });

    try {
      const response = await deckbuilderAPI.searchCards({
        query: cardFilter.query,
        types: cardFilter.types,
        colors: cardFilter.colors,
        cmc_min: cardFilter.cmcMin,
        cmc_max: cardFilter.cmcMax,
        text_search: cardFilter.textSearch,
        limit: 50,
        offset: searchResults.length,
      });

      set({
        searchResults: [...searchResults, ...response.cards],
        searchTotal: response.total,
        searchLoading: false,
      });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Load more failed',
        searchLoading: false,
      });
    }
  },

  // Persistence
  loadDeck: async (deckId) => {
    set({ isLoading: true, error: null });

    try {
      const deck = await deckbuilderAPI.getDeck(deckId);
      set({
        currentDeck: deck,
        isLoading: false,
        hasUnsavedChanges: false,
      });
      get().refreshStats();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to load deck',
        isLoading: false,
      });
    }
  },

  saveDeck: async () => {
    const { currentDeck } = get();
    set({ isSaving: true, error: null });

    try {
      const saved = await deckbuilderAPI.saveDeck({
        deck_id: currentDeck.id,
        name: currentDeck.name,
        archetype: currentDeck.archetype,
        colors: currentDeck.colors,
        description: currentDeck.description,
        mainboard: currentDeck.mainboard,
        sideboard: currentDeck.sideboard,
        format: currentDeck.format,
      });

      set({
        currentDeck: saved,
        isSaving: false,
        hasUnsavedChanges: false,
      });

      // Refresh the saved decks list
      get().loadSavedDecks();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to save deck',
        isSaving: false,
      });
    }
  },

  deleteDeck: async (deckId) => {
    set({ isLoading: true, error: null });

    try {
      await deckbuilderAPI.deleteDeck(deckId);
      set({ isLoading: false });

      // If we deleted the current deck, reset to new
      const { currentDeck } = get();
      if (currentDeck.id === deckId) {
        get().newDeck();
      }

      // Refresh the list
      get().loadSavedDecks();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to delete deck',
        isLoading: false,
      });
    }
  },

  loadSavedDecks: async () => {
    try {
      const response = await deckbuilderAPI.listDecks();
      set({ savedDecks: response.decks });
    } catch (err) {
      console.error('Failed to load saved decks:', err);
    }
  },

  // Import/Export
  importDeck: async (text) => {
    set({ isLoading: true, error: null });

    try {
      const deck = await deckbuilderAPI.importDeck(text, get().currentDeck.format);
      set({
        currentDeck: deck,
        isLoading: false,
        hasUnsavedChanges: false,
      });
      get().refreshStats();
      get().loadSavedDecks();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to import deck',
        isLoading: false,
      });
    }
  },

  exportDeck: async () => {
    const { currentDeck } = get();
    if (!currentDeck.id) {
      // Generate text locally if not saved
      const lines: string[] = [`// ${currentDeck.name}`];
      for (const entry of currentDeck.mainboard) {
        lines.push(`${entry.qty} ${entry.card}`);
      }
      if (currentDeck.sideboard.length > 0) {
        lines.push('', 'Sideboard');
        for (const entry of currentDeck.sideboard) {
          lines.push(`${entry.qty} ${entry.card}`);
        }
      }
      return lines.join('\n');
    }

    try {
      const response = await deckbuilderAPI.exportDeck(currentDeck.id);
      return response.text;
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to export deck');
    }
  },

  // Stats
  refreshStats: async () => {
    const { currentDeck } = get();
    if (currentDeck.mainboard.length === 0) {
      set({ deckStats: null });
      return;
    }

    try {
      const stats = await deckbuilderAPI.getDeckStats(
        currentDeck.mainboard,
        currentDeck.sideboard
      );
      set({ deckStats: stats });
    } catch (err) {
      console.error('Failed to refresh stats:', err);
    }
  },

  // Error handling
  setError: (error) => set({ error }),
  clearError: () => set({ error: null }),
}));
