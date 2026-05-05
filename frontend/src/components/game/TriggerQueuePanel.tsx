/**
 * TriggerQueuePanel Component
 *
 * Shows triggered abilities that have fired but are not yet on the stack
 * (CR 603.2). Renders ``state.pending_triggers`` so the active player can
 * preview the queue before it drains onto the stack on the next priority
 * pass.
 *
 * v1 limitations:
 *   - Read-only display. Re-ordering a player's own simultaneous triggers
 *     (CR 603.3b) is deferred — current order matches engine registration
 *     order, which is deterministic.
 *   - No visual distinction for triggers from different sources beyond
 *     the controller's color rail.
 */

import clsx from 'clsx';
import type { PendingTriggerData } from '../../types';

interface TriggerQueuePanelProps {
  pendingTriggers: PendingTriggerData[];
  playerId?: string;
}

export function TriggerQueuePanel({
  pendingTriggers,
  playerId,
}: TriggerQueuePanelProps) {
  if (!pendingTriggers || pendingTriggers.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="trigger-queue-panel"
      className="p-3 rounded-lg bg-game-surface border border-amber-500/60 shadow-lg shadow-amber-500/20"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs text-amber-300 uppercase tracking-wide">
          Triggers Queued ({pendingTriggers.length})
        </div>
        <div className="text-[10px] text-gray-500 italic">
          Goes on stack next
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        {pendingTriggers.map((trig, index) => {
          const isYours = trig.controller === playerId;
          return (
            <div
              key={trig.id || `${trig.source_id}-${index}`}
              data-testid="trigger-queue-item"
              className={clsx(
                'p-2 rounded border-l-4 bg-amber-900/20 border border-amber-700/40',
                {
                  'border-l-blue-500': isYours,
                  'border-l-red-500': !isYours,
                }
              )}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-semibold text-amber-100 text-sm truncate">
                  {trig.source_name}
                </span>
                <span className="text-[10px] text-gray-400 whitespace-nowrap">
                  {isYours ? 'Yours' : 'Opponent'}
                </span>
              </div>
              {trig.description && (
                <div className="text-xs text-gray-300 mt-1 leading-snug">
                  {trig.description}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default TriggerQueuePanel;
