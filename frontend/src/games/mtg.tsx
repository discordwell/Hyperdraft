/**
 * Magic: The Gathering — deckbuilder module.
 *
 * MTG already has the most polish (color pips + mana curve in the existing
 * UI). This module just centralizes its config; the existing components keep
 * doing the rendering for back-compat.
 */

import type { GameModule } from './types';
import { CARD_TYPES } from '../types/deckbuilder';

export const mtg: GameModule = {
  id: 'mtg',
  label: 'Magic: The Gathering',
  showColors: true,
  costLabel: 'Mana Value',
  typeFilters: CARD_TYPES,
  formatType: (t) => t.charAt(0) + t.slice(1).toLowerCase(),
  tiles: (stats) => {
    if (!stats) return [];
    return [
      { label: 'Lands', value: stats.land_count ?? 0 },
      { label: 'Creatures', value: stats.creature_count ?? 0 },
      { label: 'Spells', value: stats.spell_count ?? 0 },
    ];
  },
  // No StatsExtras: MTG keeps its existing color pips + mana curve treatment.
};
