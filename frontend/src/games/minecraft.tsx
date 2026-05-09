/**
 * Minecraft TCG — deckbuilder module.
 *
 * Polish: stacked material distribution bar (wood / stone / iron / redstone
 * / diamond) so the player can see at a glance how resource-heavy the deck
 * is, and which biome upgrades to prioritize.
 */

import type { GameModule } from './types';
import type { DeckStats } from '../types/deckbuilder';
import { defaultFormatType } from './types';
import { StackedBar } from './StackedBar';

const MATERIAL_COLORS: Record<string, string> = {
  wood: '#8b6f47',     // oak plank brown
  stone: '#7a7a7a',    // cobblestone
  iron: '#9ca3af',     // ingot grey (gray-400 — visible on dark bg)
  redstone: '#dc2626', // redstone red
  diamond: '#22d3ee',  // diamond cyan
};
const MATERIAL_ORDER = ['wood', 'stone', 'iron', 'redstone', 'diamond'];

function MinecraftStatsExtras({ stats }: { stats: DeckStats }) {
  const mat = (stats.extras?.material_distribution as Record<string, number>) || {};
  return (
    <StackedBar
      title="Material curve"
      segments={MATERIAL_ORDER.map((m) => ({
        key: m,
        label: m.charAt(0).toUpperCase() + m.slice(1),
        value: mat[m] || 0,
        color: MATERIAL_COLORS[m],
      }))}
    />
  );
}

export const minecraft: GameModule = {
  id: 'minecraft',
  label: 'Minecraft TCG',
  showColors: false,
  costLabel: 'Materials',
  typeFilters: ['MC_MOB', 'MC_STRUCTURE', 'MC_BLOCK', 'MC_TOOL', 'MC_ACTION'],
  formatType: defaultFormatType,
  tiles: (stats) => {
    if (!stats) return [];
    const mat = (stats.extras?.material_distribution as Record<string, number>) || {};
    return [
      { label: 'Wood', value: mat.wood ?? 0 },
      { label: 'Stone', value: mat.stone ?? 0 },
      {
        label: 'Iron+',
        value: (mat.iron ?? 0) + (mat.redstone ?? 0) + (mat.diamond ?? 0),
      },
    ];
  },
  StatsExtras: MinecraftStatsExtras,
};
