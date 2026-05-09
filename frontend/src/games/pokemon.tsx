/**
 * Pokemon TCG — deckbuilder module.
 *
 * Polish: energy-type breakdown so the player can see what type the deck
 * is paying for and verify they have enough energy of the right type.
 */

import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { defaultFormatType } from './types';
import { StackedBar } from './StackedBar';

// Canonical Pokemon TCG energy palette.
const ENERGY_COLORS: Record<string, string> = {
  Grass: '#4caf50',
  Fire: '#ef5350',
  Water: '#2196f3',
  Lightning: '#fbc02d',
  Psychic: '#ab47bc',
  Fighting: '#a1887f',
  Darkness: '#37474f',
  Metal: '#90a4ae',
  Fairy: '#f48fb1',
  Dragon: '#d4a017',
  Colorless: '#bdbdbd',
};

function PokemonStatsExtras({ stats }: { stats: DeckStats }) {
  const dist = (stats.extras?.energy_distribution as Record<string, number>) || {};
  const known = Object.keys(ENERGY_COLORS);
  // Show known types in a stable order, then any unknowns appended.
  const ordered = [
    ...known.filter((k) => dist[k]),
    ...Object.keys(dist).filter((k) => !known.includes(k)),
  ];
  return (
    <StackedBar
      title="Energy mix"
      segments={ordered.map((t) => ({
        key: t,
        label: t,
        value: dist[t] || 0,
        color: ENERGY_COLORS[t] || '#9ca3af',
      }))}
    />
  );
}

export const pokemon: GameModule = {
  id: 'pokemon',
  label: 'Pokémon TCG',
  showColors: false,
  costLabel: 'HP Tier',
  typeFilters: ['PKM_POKEMON', 'PKM_TRAINER', 'PKM_ENERGY'],
  formatType: defaultFormatType,
  tiles: (stats) => {
    if (!stats) return [];
    const ex = (stats.extras ?? {}) as Record<string, number>;
    return [
      { label: 'Pokémon', value: ex.pokemon_count ?? 0 },
      { label: 'Trainers', value: ex.trainer_count ?? 0 },
      { label: 'Energy', value: ex.energy_card_count ?? 0 },
    ];
  },
  StatsExtras: PokemonStatsExtras,
};
