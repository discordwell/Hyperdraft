/**
 * PhaseIndicator Component
 *
 * Displays the current turn, phase, and step.
 */

import clsx from 'clsx';
import type { Phase, Step } from '../../types';

interface PhaseIndicatorProps {
  turnNumber: number;
  phase: Phase;
  step: Step;
  activePlayerName?: string;
}

const PHASE_LABELS: Record<Phase, string> = {
  BEGINNING: 'Beginning',
  PRECOMBAT_MAIN: 'Main 1',
  COMBAT: 'Combat',
  POSTCOMBAT_MAIN: 'Main 2',
  ENDING: 'Ending',
};

const STEP_LABELS: Record<Step, string> = {
  UNTAP: 'Untap',
  UPKEEP: 'Upkeep',
  DRAW: 'Draw',
  MAIN: 'Main Phase',
  BEGINNING_OF_COMBAT: 'Begin Combat',
  DECLARE_ATTACKERS: 'Attackers',
  DECLARE_BLOCKERS: 'Blockers',
  COMBAT_DAMAGE: 'Damage',
  FIRST_STRIKE_DAMAGE: 'First Strike',
  END_OF_COMBAT: 'End Combat',
  END_STEP: 'End Step',
  CLEANUP: 'Cleanup',
};

const PHASES: Phase[] = [
  'BEGINNING',
  'PRECOMBAT_MAIN',
  'COMBAT',
  'POSTCOMBAT_MAIN',
  'ENDING',
];

export function PhaseIndicator({
  turnNumber,
  phase,
  step,
  activePlayerName,
}: PhaseIndicatorProps) {
  return (
    <div className="flex flex-col items-center gap-2 p-3 bg-game-surface rounded-lg border border-gray-700">
      {/* Turn Number */}
      <div className="text-sm text-gray-400">
        Turn <span className="font-bold text-white">{turnNumber}</span>
        {activePlayerName && (
          <span className="ml-2">
            - <span className="text-game-gold">{activePlayerName}</span>
          </span>
        )}
      </div>

      {/* Phase Bar */}
      <div className="flex gap-1">
        {PHASES.map((p) => (
          <div
            key={p}
            className={clsx(
              'px-2 py-1 text-xs rounded transition-all',
              p === phase
                ? 'bg-game-accent text-white font-semibold'
                : 'bg-gray-700 text-gray-400'
            )}
          >
            {PHASE_LABELS[p]}
          </div>
        ))}
      </div>

      {/* Current Step */}
      <div className="text-sm">
        <span className="text-gray-400">Step: </span>
        <span className="font-semibold text-white">{STEP_LABELS[step]}</span>
      </div>
    </div>
  );
}

export default PhaseIndicator;
