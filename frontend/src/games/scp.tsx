import type { DeckStats } from '../types/deckbuilder';
import type { GameModule } from './types';
import { defaultFormatType } from './types';

const SCP_TYPES = [
  'SCP_ANOMALY',
  'SCP_PERSONNEL',
  'SCP_FACILITY',
  'SCP_PROCEDURE',
  'SCP_MANDATE',
] as const;

function num(stats: DeckStats | null, key: string): number {
  const value = stats?.extras?.[key];
  return typeof value === 'number' ? value : 0;
}

function SCPStatsExtras({ stats }: { stats: DeckStats }) {
  const totalRedTape = num(stats, 'red_tape_total');
  const anomalies = num(stats, 'anomalies');
  const personnel = num(stats, 'personnel');
  const procedures = num(stats, 'procedures');
  const facilities = num(stats, 'facilities');

  return (
    <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
      {[
        ['Anomalies', anomalies],
        ['Personnel', personnel],
        ['Procedures', procedures],
        ['Facilities', facilities],
        ['Red Tape', totalRedTape],
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
  label: 'SCP Containment TCG',
  showColors: false,
  costLabel: 'Red Tape',
  typeFilters: SCP_TYPES,
  formatType: defaultFormatType,
  tiles: (stats) => [
    { label: 'Anomalies', value: num(stats, 'anomalies') },
    { label: 'Personnel', value: num(stats, 'personnel') },
    { label: 'Red Tape', value: num(stats, 'red_tape_total') },
  ],
  StatsExtras: SCPStatsExtras,
};

export default scp;
