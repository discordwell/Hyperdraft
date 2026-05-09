/**
 * Yu-Gi-Oh! — deckbuilder module.
 *
 * Polish: monster Attribute breakdown (Light / Dark / Earth / Water / Fire
 * / Wind / Divine). Useful for tribal-attribute archetypes and to confirm
 * the deck has the right mix for support cards.
 */

import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { defaultFormatType } from './types';
import { StackedBar } from './StackedBar';

const ATTRIBUTE_COLORS: Record<string, string> = {
  LIGHT: '#fde68a',
  DARK: '#1f2937',
  EARTH: '#854d0e',
  WATER: '#2563eb',
  FIRE: '#dc2626',
  WIND: '#16a34a',
  DIVINE: '#facc15',
};

const ATTRIBUTE_ORDER = ['LIGHT', 'DARK', 'EARTH', 'WATER', 'FIRE', 'WIND', 'DIVINE'];

function pretty(attr: string): string {
  return attr.charAt(0) + attr.slice(1).toLowerCase();
}

function YugiohStatsExtras({ stats }: { stats: DeckStats }) {
  const dist = (stats.extras?.attribute_distribution as Record<string, number>) || {};
  // Normalize keys to upper-case for color lookup.
  const normalized: Record<string, number> = {};
  for (const [k, v] of Object.entries(dist)) {
    const key = k.toUpperCase();
    normalized[key] = (normalized[key] || 0) + v;
  }
  const ordered = [
    ...ATTRIBUTE_ORDER.filter((k) => normalized[k]),
    ...Object.keys(normalized).filter((k) => !ATTRIBUTE_ORDER.includes(k)),
  ];
  return (
    <StackedBar
      title="Attributes"
      segments={ordered.map((t) => ({
        key: t,
        label: pretty(t),
        value: normalized[t] || 0,
        color: ATTRIBUTE_COLORS[t] || '#9ca3af',
      }))}
    />
  );
}

export const yugioh: GameModule = {
  id: 'yugioh',
  label: 'Yu-Gi-Oh!',
  showColors: false,
  costLabel: 'Level',
  typeFilters: ['YGO_MONSTER', 'YGO_SPELL', 'YGO_TRAP'],
  formatType: defaultFormatType,
  tiles: (stats) => {
    if (!stats) return [];
    const ex = (stats.extras ?? {}) as Record<string, number>;
    return [
      { label: 'Monsters', value: ex.monster_count ?? 0 },
      { label: 'Spells', value: ex.spell_count ?? 0 },
      { label: 'Traps', value: ex.trap_count ?? 0 },
    ];
  },
  StatsExtras: YugiohStatsExtras,
};
