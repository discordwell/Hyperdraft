/**
 * Gatherer Types
 *
 * TypeScript types for the Gatherer card browser feature.
 */

import type { CardDefinitionData } from './deckbuilder';

// Set information
export interface SetInfo {
  code: string;
  name: string;
  card_count: number;
  release_date: string;
  set_type: 'standard' | 'universes_beyond' | 'custom' | 'test';
}

// Detailed set information with rarity breakdown
export interface SetDetail extends SetInfo {
  rarity_breakdown: {
    mythic: number;
    rare: number;
    uncommon: number;
    common: number;
  };
}

// Set list response
export interface SetListResponse {
  sets: SetInfo[];
  total: number;
}

// Card filter for set browsing
export interface SetCardFilter {
  types?: string[];
  colors?: string[];
  rarity?: string;
  cmcMin?: number;
  cmcMax?: number;
  textSearch?: string;
}

// Card search request for a set
export interface SetCardSearchRequest {
  types?: string[];
  colors?: string[];
  rarity?: string;
  cmc_min?: number;
  cmc_max?: number;
  text_search?: string;
  sort_by?: SortField;
  sort_order?: SortOrder;
  limit?: number;
  offset?: number;
}

// Card search response for a set
export interface SetCardSearchResponse {
  cards: CardDefinitionData[];
  total: number;
  has_more: boolean;
  set_code: string;
  set_name: string;
}

// Sort options
export type SortField = 'name' | 'cmc' | 'rarity' | 'color' | 'type' | 'power';
export type SortOrder = 'asc' | 'desc';

// Set type display info
export const SET_TYPE_INFO = {
  standard: {
    label: 'Standard',
    description: 'MTG Standard rotation sets',
    color: '#22c55e', // green
  },
  universes_beyond: {
    label: 'Universes Beyond',
    description: 'Official crossover sets',
    color: '#a855f7', // purple
  },
  custom: {
    label: 'Custom',
    description: 'Fan-made sets with working mechanics',
    color: '#f97316', // orange
  },
  test: {
    label: 'Test',
    description: 'Test cards for development',
    color: '#6b7280', // gray
  },
} as const;

// Rarity display info
export const RARITY_INFO = {
  mythic: { label: 'Mythic', color: '#f97316' },
  rare: { label: 'Rare', color: '#eab308' },
  uncommon: { label: 'Uncommon', color: '#a3a3a3' },
  common: { label: 'Common', color: '#525252' },
} as const;

// Sort field display info
export const SORT_FIELDS: { value: SortField; label: string }[] = [
  { value: 'name', label: 'Name' },
  { value: 'cmc', label: 'Mana Value' },
  { value: 'rarity', label: 'Rarity' },
  { value: 'color', label: 'Color' },
  { value: 'type', label: 'Type' },
  { value: 'power', label: 'Power' },
];

export type SetType = keyof typeof SET_TYPE_INFO;
export type Rarity = keyof typeof RARITY_INFO;
