/**
 * Hearthstone — deckbuilder module.
 *
 * Polish: class distribution. Helps spot off-class splashes that won't be
 * legal for the chosen Hero, and visualizes neutral-vs-class-card balance.
 */

import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { defaultFormatType } from './types';
import { StackedBar } from './StackedBar';

const CLASS_COLORS: Record<string, string> = {
  Mage: '#3b82f6',
  Hunter: '#16a34a',
  Paladin: '#fbbf24',
  Priest: '#e5e7eb',
  Rogue: '#1f2937',
  Shaman: '#1e3a8a',
  Warlock: '#7c3aed',
  Warrior: '#b91c1c',
  Druid: '#ca8a04',
  'Demon Hunter': '#831843',
  Neutral: '#6b7280',
};

function HearthstoneStatsExtras({ stats }: { stats: DeckStats }) {
  const dist = (stats.extras?.class_distribution as Record<string, number>) || {};
  const known = Object.keys(CLASS_COLORS);
  const ordered = [
    ...known.filter((k) => dist[k]),
    ...Object.keys(dist).filter((k) => !known.includes(k)),
  ];
  return (
    <StackedBar
      title="Class breakdown"
      segments={ordered.map((c) => ({
        key: c,
        label: c,
        value: dist[c] || 0,
        color: CLASS_COLORS[c] || '#9ca3af',
      }))}
    />
  );
}

export const hearthstone: GameModule = {
  id: 'hearthstone',
  label: 'Hearthstone',
  showColors: false,
  costLabel: 'Mana',
  typeFilters: ['HS_MINION', 'HS_SPELL', 'HS_WEAPON', 'HS_HERO'],
  formatType: defaultFormatType,
  tiles: (stats) => {
    if (!stats) return [];
    const ex = (stats.extras ?? {}) as Record<string, number>;
    return [
      { label: 'Minions', value: ex.minion_count ?? 0 },
      { label: 'Spells', value: ex.spell_count ?? 0 },
      { label: 'Weapons', value: ex.weapon_count ?? 0 },
    ];
  },
  StatsExtras: HearthstoneStatsExtras,
};
