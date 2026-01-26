/**
 * Gatherer State Store
 *
 * Zustand store for managing Gatherer card browser state.
 */

import { create } from 'zustand';
import type {
  SetInfo,
  SetDetail,
  SetCardFilter,
  SortField,
  SortOrder,
} from '../types/gatherer';
import type { CardDefinitionData } from '../types/deckbuilder';
import { gathererAPI } from '../services/deckbuilderApi';

interface GathererStore {
  // Sets
  sets: SetInfo[];
  setsLoading: boolean;
  setsError: string | null;

  // Current set
  currentSet: SetDetail | null;
  currentSetLoading: boolean;

  // Cards in current set
  cards: CardDefinitionData[];
  cardsTotal: number;
  cardsLoading: boolean;
  cardsHasMore: boolean;

  // Filters and sorting
  filter: SetCardFilter;
  sortBy: SortField;
  sortOrder: SortOrder;

  // Selected card for detail modal
  selectedCard: CardDefinitionData | null;

  // Set type filter for sidebar
  setTypeFilter: string | null;

  // Actions
  loadSets: (setType?: string) => Promise<void>;
  selectSet: (setCode: string) => Promise<void>;
  loadCards: () => Promise<void>;
  loadMoreCards: () => Promise<void>;
  setFilter: (filter: Partial<SetCardFilter>) => void;
  clearFilter: () => void;
  setSortBy: (sortBy: SortField) => void;
  setSortOrder: (sortOrder: SortOrder) => void;
  toggleSortOrder: () => void;
  selectCard: (card: CardDefinitionData | null) => void;
  setSetTypeFilter: (setType: string | null) => void;
}

const CARDS_PER_PAGE = 50;

export const useGathererStore = create<GathererStore>((set, get) => ({
  // Initial state
  sets: [],
  setsLoading: false,
  setsError: null,
  currentSet: null,
  currentSetLoading: false,
  cards: [],
  cardsTotal: 0,
  cardsLoading: false,
  cardsHasMore: false,
  filter: {},
  sortBy: 'name',
  sortOrder: 'asc',
  selectedCard: null,
  setTypeFilter: null,

  // Load all sets
  loadSets: async (setType?: string) => {
    set({ setsLoading: true, setsError: null });

    try {
      const response = await gathererAPI.getSets(setType);
      set({
        sets: response.sets,
        setsLoading: false,
        setTypeFilter: setType || null,
      });
    } catch (err) {
      set({
        setsError: err instanceof Error ? err.message : 'Failed to load sets',
        setsLoading: false,
      });
    }
  },

  // Select a set and load its details
  selectSet: async (setCode: string) => {
    set({ currentSetLoading: true, cards: [], cardsTotal: 0 });

    try {
      const setDetail = await gathererAPI.getSetDetails(setCode);
      set({
        currentSet: setDetail,
        currentSetLoading: false,
      });

      // Load cards for this set
      get().loadCards();
    } catch (err) {
      console.error('Failed to load set:', err);
      set({ currentSetLoading: false });
    }
  },

  // Load cards for current set with current filters
  loadCards: async () => {
    const { currentSet, filter, sortBy, sortOrder } = get();
    if (!currentSet) return;

    set({ cardsLoading: true });

    try {
      const response = await gathererAPI.getSetCards(currentSet.code, {
        types: filter.types,
        colors: filter.colors,
        rarity: filter.rarity,
        cmc_min: filter.cmcMin,
        cmc_max: filter.cmcMax,
        text_search: filter.textSearch,
        sort_by: sortBy,
        sort_order: sortOrder,
        limit: CARDS_PER_PAGE,
        offset: 0,
      });

      set({
        cards: response.cards,
        cardsTotal: response.total,
        cardsHasMore: response.has_more,
        cardsLoading: false,
      });
    } catch (err) {
      console.error('Failed to load cards:', err);
      set({ cardsLoading: false });
    }
  },

  // Load more cards (pagination)
  loadMoreCards: async () => {
    const { currentSet, cards, filter, sortBy, sortOrder, cardsHasMore } = get();
    if (!currentSet || !cardsHasMore) return;

    set({ cardsLoading: true });

    try {
      const response = await gathererAPI.getSetCards(currentSet.code, {
        types: filter.types,
        colors: filter.colors,
        rarity: filter.rarity,
        cmc_min: filter.cmcMin,
        cmc_max: filter.cmcMax,
        text_search: filter.textSearch,
        sort_by: sortBy,
        sort_order: sortOrder,
        limit: CARDS_PER_PAGE,
        offset: cards.length,
      });

      set({
        cards: [...cards, ...response.cards],
        cardsHasMore: response.has_more,
        cardsLoading: false,
      });
    } catch (err) {
      console.error('Failed to load more cards:', err);
      set({ cardsLoading: false });
    }
  },

  // Update filter and reload cards
  setFilter: (newFilter: Partial<SetCardFilter>) => {
    set((state) => ({
      filter: { ...state.filter, ...newFilter },
    }));
    // Reload cards with new filter
    get().loadCards();
  },

  // Clear all filters
  clearFilter: () => {
    set({ filter: {} });
    get().loadCards();
  },

  // Set sort field and reload
  setSortBy: (sortBy: SortField) => {
    set({ sortBy });
    get().loadCards();
  },

  // Set sort order and reload
  setSortOrder: (sortOrder: SortOrder) => {
    set({ sortOrder });
    get().loadCards();
  },

  // Toggle sort order
  toggleSortOrder: () => {
    const { sortOrder } = get();
    set({ sortOrder: sortOrder === 'asc' ? 'desc' : 'asc' });
    get().loadCards();
  },

  // Select a card for the detail modal
  selectCard: (card: CardDefinitionData | null) => {
    set({ selectedCard: card });
  },

  // Set the set type filter for the sidebar
  setSetTypeFilter: (setType: string | null) => {
    set({ setTypeFilter: setType });
    get().loadSets(setType || undefined);
  },
}));
