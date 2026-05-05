/**
 * Pokemon Gatherer Store
 *
 * Zustand store for the Pokemon card browser. Mirrors gathererStore.ts.
 */

import { create } from 'zustand';
import type {
  PokemonCardData,
  PokemonSetCardFilter,
  PokemonSetDetail,
  PokemonSetInfo,
  PokemonSortField,
  PokemonSortOrder,
} from '../types/pokemonGatherer';
import { pokemonGathererAPI } from '../services/deckbuilderApi';

interface PokemonGathererStore {
  sets: PokemonSetInfo[];
  setsLoading: boolean;
  setsError: string | null;

  currentSet: PokemonSetDetail | null;
  currentSetLoading: boolean;

  cards: PokemonCardData[];
  cardsTotal: number;
  cardsLoading: boolean;
  cardsHasMore: boolean;

  filter: PokemonSetCardFilter;
  sortBy: PokemonSortField;
  sortOrder: PokemonSortOrder;

  selectedCard: PokemonCardData | null;
  setTypeFilter: string | null;

  loadSets: (setType?: string) => Promise<void>;
  selectSet: (setCode: string) => Promise<void>;
  loadCards: () => Promise<void>;
  loadMoreCards: () => Promise<void>;
  setFilter: (filter: Partial<PokemonSetCardFilter>) => void;
  clearFilter: () => void;
  setSortBy: (sortBy: PokemonSortField) => void;
  setSortOrder: (sortOrder: PokemonSortOrder) => void;
  toggleSortOrder: () => void;
  selectCard: (card: PokemonCardData | null) => void;
  setSetTypeFilter: (setType: string | null) => void;
}

const CARDS_PER_PAGE = 60;

// Module-scoped request counter. Each card-fetch captures the value on
// entry and discards its response if a newer request has started — keeps
// rapid filter / set toggling from clobbering the latest state with a
// stale response.
let requestSeq = 0;

export const usePokemonGathererStore = create<PokemonGathererStore>((set, get) => ({
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

  loadSets: async (setType?: string) => {
    set({ setsLoading: true, setsError: null });
    try {
      const response = await pokemonGathererAPI.getSets(setType);
      set({
        sets: response.sets,
        setsLoading: false,
        setTypeFilter: setType ?? null,
      });
    } catch (err) {
      set({
        setsError: err instanceof Error ? err.message : 'Failed to load Pokemon sets',
        setsLoading: false,
      });
    }
  },

  // Filters persist across set switches (matches MTG gatherer). Guild
  // is the one BRV-only axis — clear it when leaving BRV so it doesn't
  // strand the user on an empty result page in SVS.
  selectSet: async (setCode: string) => {
    const id = ++requestSeq;
    set((state) => {
      const nextFilter =
        setCode.toUpperCase() === 'BRV'
          ? state.filter
          : { ...state.filter, guild: undefined };
      return {
        currentSetLoading: true,
        cards: [],
        cardsTotal: 0,
        filter: nextFilter,
      };
    });
    try {
      const detail = await pokemonGathererAPI.getSetDetails(setCode);
      if (id !== requestSeq) return;
      set({ currentSet: detail, currentSetLoading: false });
      get().loadCards();
    } catch (err) {
      if (id !== requestSeq) return;
      console.error('Failed to load Pokemon set:', err);
      set({ currentSetLoading: false });
    }
  },

  loadCards: async () => {
    const { currentSet, filter, sortBy, sortOrder } = get();
    if (!currentSet) return;
    const id = ++requestSeq;
    set({ cardsLoading: true });
    try {
      const response = await pokemonGathererAPI.getSetCards(currentSet.code, {
        ...filter,
        sortBy,
        sortOrder,
        limit: CARDS_PER_PAGE,
        offset: 0,
      });
      if (id !== requestSeq) return;
      set({
        cards: response.cards,
        cardsTotal: response.total,
        cardsHasMore: response.has_more,
        cardsLoading: false,
      });
    } catch (err) {
      if (id !== requestSeq) return;
      console.error('Failed to load Pokemon cards:', err);
      set({ cardsLoading: false });
    }
  },

  loadMoreCards: async () => {
    const { currentSet, cards, filter, sortBy, sortOrder, cardsHasMore, cardsLoading } = get();
    if (!currentSet || !cardsHasMore || cardsLoading) return;
    const id = ++requestSeq;
    set({ cardsLoading: true });
    try {
      const response = await pokemonGathererAPI.getSetCards(currentSet.code, {
        ...filter,
        sortBy,
        sortOrder,
        limit: CARDS_PER_PAGE,
        offset: cards.length,
      });
      if (id !== requestSeq) return;
      // Defensive: dedupe in case a race ever slips past the request-id
      // and reentry guards. Pokemon names are unique within a set.
      const seen = new Set(cards.map((c) => c.name));
      const additions = response.cards.filter((c) => !seen.has(c.name));
      set({
        cards: [...cards, ...additions],
        cardsHasMore: response.has_more,
        cardsLoading: false,
      });
    } catch (err) {
      if (id !== requestSeq) return;
      console.error('Failed to load more Pokemon cards:', err);
      set({ cardsLoading: false });
    }
  },

  setFilter: (newFilter) => {
    set((state) => ({ filter: { ...state.filter, ...newFilter } }));
    get().loadCards();
  },

  clearFilter: () => {
    set({ filter: {} });
    get().loadCards();
  },

  setSortBy: (sortBy) => {
    set({ sortBy });
    get().loadCards();
  },

  setSortOrder: (sortOrder) => {
    set({ sortOrder });
    get().loadCards();
  },

  toggleSortOrder: () => {
    const { sortOrder } = get();
    set({ sortOrder: sortOrder === 'asc' ? 'desc' : 'asc' });
    get().loadCards();
  },

  selectCard: (card) => set({ selectedCard: card }),

  setSetTypeFilter: (setType) => {
    set({ setTypeFilter: setType });
    get().loadSets(setType ?? undefined);
  },
}));
