/**
 * HSGameLog - Hearthstone-themed wrapper over the shared GameLog.
 *
 * Thin re-export so HSGameView can mount one without re-implementing the
 * shared icon/cluster logic. Uses a warmer accent to match the HS theme.
 */

import type { GameLogEntry } from '../../types/game';
import { GameLog } from './GameLog';

interface HSGameLogProps {
  entries: GameLogEntry[];
  playerNames?: Record<string, string>;
}

export function HSGameLog({ entries, playerNames }: HSGameLogProps) {
  return (
    <GameLog
      entries={entries}
      playerNames={playerNames}
      accentClass="bg-orange-600/40"
      heading="Game Log"
      scrollClass="max-h-72"
    />
  );
}

export default HSGameLog;
