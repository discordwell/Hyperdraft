/**
 * Pokemon Gatherer Types
 *
 * TypeScript types for the Pokemon card browser. Mirrors
 * src/server/routes/pokemon_gatherer.py.
 */

export interface PokemonEnergyCost {
  type: string; // PokemonType code: G/R/W/L/P/F/D/M/C
  count: number;
}

export interface PokemonAttackData {
  name: string;
  cost: PokemonEnergyCost[];
  damage: number | null;
  text: string;
}

export interface PokemonAbilityData {
  name: string;
  text: string;
  ability_type: string | null;
}

export type PokemonSupertype = 'Pokemon' | 'Trainer' | 'Energy' | 'Unknown';
export type PokemonTrainerSubtype = 'Item' | 'Supporter' | 'Stadium' | 'Tool';
export type PokemonEvolutionStage = 'Basic' | 'Stage 1' | 'Stage 2';

export interface PokemonCardData {
  name: string;
  supertype: PokemonSupertype;
  trainer_subtype: PokemonTrainerSubtype | null;
  text: string;
  rarity: string | null;
  image_url: string | null;
  guild: string | null;

  hp: number | null;
  pokemon_type: string | null;
  evolution_stage: PokemonEvolutionStage | null;
  evolves_from: string | null;
  weakness_type: string | null;
  weakness_modifier: string | null;
  resistance_type: string | null;
  resistance_modifier: number | null;
  retreat_cost: number | null;
  is_ex: boolean;
  rule_box: string | null;
  prize_count: number | null;
  attacks: PokemonAttackData[];
  ability: PokemonAbilityData | null;

  energy_type: string | null;
}

export interface PokemonSetInfo {
  code: string;
  name: string;
  card_count: number;
  release_date: string;
  set_type: 'starter' | 'beyond';
}

export interface PokemonSetDetail extends PokemonSetInfo {
  supertype_breakdown: Record<string, number>;
  type_breakdown: Record<string, number>;
  guilds: string[];
}

export interface PokemonSetListResponse {
  sets: PokemonSetInfo[];
  total: number;
}

export interface PokemonSetCardFilter {
  supertype?: PokemonSupertype;
  trainerSubtype?: PokemonTrainerSubtype;
  pokemonType?: string;
  evolutionStage?: PokemonEvolutionStage;
  isEx?: boolean;
  hpMin?: number;
  hpMax?: number;
  retreatCostMin?: number;
  retreatCostMax?: number;
  guild?: string;
  textSearch?: string;
}

export function hasActivePokemonFilters(f: PokemonSetCardFilter): boolean {
  return (
    !!f.supertype ||
    !!f.trainerSubtype ||
    !!f.pokemonType ||
    !!f.evolutionStage ||
    f.isEx !== undefined ||
    f.hpMin !== undefined ||
    f.hpMax !== undefined ||
    f.retreatCostMin !== undefined ||
    f.retreatCostMax !== undefined ||
    !!f.guild ||
    !!f.textSearch
  );
}

export type PokemonSortField =
  | 'name'
  | 'hp'
  | 'type'
  | 'rarity'
  | 'stage'
  | 'supertype';
export type PokemonSortOrder = 'asc' | 'desc';

export interface PokemonCardSearchResponse {
  cards: PokemonCardData[];
  total: number;
  has_more: boolean;
}

// Display metadata for the 9 Pokemon types.
export const POKEMON_TYPE_INFO: Record<
  string,
  { label: string; color: string; symbol: string }
> = {
  G: { label: 'Grass', color: '#4caf50', symbol: 'G' },
  R: { label: 'Fire', color: '#ef5350', symbol: 'R' },
  W: { label: 'Water', color: '#42a5f5', symbol: 'W' },
  L: { label: 'Lightning', color: '#fdd835', symbol: 'L' },
  P: { label: 'Psychic', color: '#ab47bc', symbol: 'P' },
  F: { label: 'Fighting', color: '#8d6e63', symbol: 'F' },
  D: { label: 'Darkness', color: '#37474f', symbol: 'D' },
  M: { label: 'Metal', color: '#9e9e9e', symbol: 'M' },
  C: { label: 'Colorless', color: '#cfd8dc', symbol: 'C' },
};

export const POKEMON_TYPE_ORDER = ['G', 'R', 'W', 'L', 'P', 'F', 'D', 'M', 'C'];

export const POKEMON_SET_TYPE_INFO: Record<
  string,
  { label: string; color: string; description: string }
> = {
  starter: {
    label: 'Starter',
    color: '#22c55e',
    description: 'Real Pokemon TCG starter sets',
  },
  beyond: {
    label: 'Beyond',
    color: '#a855f7',
    description: 'Crossover sets visiting MTG planes',
  },
};

export const POKEMON_SORT_FIELDS: { value: PokemonSortField; label: string }[] = [
  { value: 'name', label: 'Name' },
  { value: 'hp', label: 'HP' },
  { value: 'type', label: 'Type' },
  { value: 'stage', label: 'Stage' },
  { value: 'rarity', label: 'Rarity' },
  { value: 'supertype', label: 'Category' },
];
