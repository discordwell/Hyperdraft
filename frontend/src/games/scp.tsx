import type { DeckStats } from '../types/deckbuilder';
import type { GameModule } from './types';
import { defaultFormatType } from './types';

// SCP: SECURE / CONTAIN / SUBVERT — asymmetric Foundation vs Chaos Insurgency.
const SCP_TYPES = [
  'SCP_ANOMALY',
  'SCP_LAYER',
  'SCP_ASSET',
  'SCP_OPERATION',
  'SCP_OPERATIVE',
  'SCP_TOOL',
  'SCP_EVENT',
  'SCP_IDENTITY',
] as const;

function num(stats: DeckStats | null, key: string): number {
  const value = stats?.extras?.[key];
  return typeof value === 'number' ? value : 0;
}

function SCPStatsExtras({ stats }: { stats: DeckStats }) {
  return (
    <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
      {[
        ['Anomalies', num(stats, 'anomaly_count')],
        ['Layers', num(stats, 'layer_count')],
        ['Operatives', num(stats, 'operative_count')],
        ['Containment value', num(stats, 'containment_value_total')],
      ].map(([label, value]) => (
        <div key={label} className="rounded border border-gray-700 bg-gray-900/60 px-3 py-2">
          <div className="uppercase tracking-wide text-gray-500">{label}</div>
          <div className="mt-1 text-lg font-semibold text-gray-100">{value}</div>
        </div>
      ))}
    </div>
  );
}

export const scp: GameModule = {
  id: 'scp',
  label: 'SCP: Secure / Contain / Subvert',
  showColors: false,
  costLabel: 'Cost',
  typeFilters: SCP_TYPES,
  formatType: defaultFormatType,
  tiles: (stats) => [
    { label: 'Anomalies', value: num(stats, 'anomaly_count') },
    { label: 'Layers', value: num(stats, 'layer_count') },
    { label: 'Operatives', value: num(stats, 'operative_count') },
  ],
  StatsExtras: SCPStatsExtras,
};

export default scp;
