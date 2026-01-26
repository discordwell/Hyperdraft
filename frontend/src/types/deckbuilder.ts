/**
 * Deckbuilder Types
 *
 * TypeScript types for the deckbuilder feature.
 */

// Deck entry (card name + quantity)
export interface DeckEntry {
  card: string;
  qty: number;
}

// Full deck data
export interface DeckData {
  id?: string;
  name: string;
  archetype: string;
  colors: string[];
  description: string;
  mainboard: DeckEntry[];
  sideboard: DeckEntry[];
  format: string;
  mainboard_count?: number;
  land_count?: number;
  created_at?: string;
  updated_at?: string;
}

// Deck summary for list view
export interface DeckSummary {
  id: string;
  name: string;
  archetype: string;
  colors: string[];
  format: string;
  mainboard_count: number;
  land_count: number;
  updated_at: string;
}

// Deck statistics
export interface DeckStats {
  card_count: number;
  land_count: number;
  creature_count: number;
  spell_count: number;
  average_cmc: number;
  color_distribution: Record<string, number>;
  mana_curve: Record<string, number>;
  type_breakdown: Record<string, number>;
  validation: {
    is_valid: boolean;
    errors: string[];
  };
}

// Card search filter
export interface CardFilter {
  query?: string;
  types?: string[];
  colors?: string[];
  cmcMin?: number;
  cmcMax?: number;
  textSearch?: string;
}

// Card search request
export interface CardSearchRequest {
  query?: string;
  types?: string[];
  colors?: string[];
  cmc_min?: number;
  cmc_max?: number;
  text_search?: string;
  limit?: number;
  offset?: number;
}

// Card search response
export interface CardSearchResponse {
  cards: CardDefinitionData[];
  total: number;
  has_more: boolean;
}

// Card definition (from existing types, extended)
export interface CardDefinitionData {
  name: string;
  mana_cost: string | null;
  types: string[];
  subtypes: string[];
  power: number | null;
  toughness: number | null;
  text: string;
  colors: string[];
}

// Deck list response
export interface DeckListResponse {
  decks: DeckSummary[];
  total: number;
}

// Export deck response
export interface ExportDeckResponse {
  text: string;
  deck_name: string;
}

// Color constants
export const COLORS = {
  W: { name: 'White', symbol: 'W', hex: '#F8E7B9' },
  U: { name: 'Blue', symbol: 'U', hex: '#0E68AB' },
  B: { name: 'Black', symbol: 'B', hex: '#150B00' },
  R: { name: 'Red', symbol: 'R', hex: '#D3202A' },
  G: { name: 'Green', symbol: 'G', hex: '#00733E' },
} as const;

// Card type constants
export const CARD_TYPES = [
  'CREATURE',
  'INSTANT',
  'SORCERY',
  'ENCHANTMENT',
  'ARTIFACT',
  'LAND',
  'PLANESWALKER',
] as const;

// Archetype constants
export const ARCHETYPES = [
  'Aggro',
  'Midrange',
  'Control',
  'Combo',
  'Ramp',
  'Tempo',
  'Tokens',
  'Tribal',
  'Other',
] as const;

// Format constants
export const FORMATS = [
  'Standard',
  'Modern',
  'Legacy',
  'Vintage',
  'Commander',
  'Pauper',
  'Pioneer',
] as const;

export type ColorSymbol = keyof typeof COLORS;
export type CardType = (typeof CARD_TYPES)[number];
export type Archetype = (typeof ARCHETYPES)[number];
export type Format = (typeof FORMATS)[number];
