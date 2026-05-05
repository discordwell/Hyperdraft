/**
 * PriorityPrompt Component
 *
 * A bottom-of-screen banner that appears when the player has priority
 * AND there is something on the stack (or in the trigger queue) that
 * they may want to respond to. Surfaces a clear "Pass Priority" or
 * "Respond" affordance.
 *
 * Players already have an action menu in the sidebar; this prompt's job
 * is to make it obvious WHEN they have priority during a stack
 * resolution window — that's the moment that's easy to miss in the
 * default UI, where stack items can flash by.
 *
 * v1 scope:
 *   - Shows when priority_player == me AND (stack non-empty OR pending
 *     triggers non-empty).
 *   - "Respond" scrolls/focuses the action menu (no inline action UI).
 *   - "Pass" sends a PASS action.
 *   - AI players never see this (they auto-pass via the engine).
 */

import { useMemo } from 'react';
import clsx from 'clsx';
import type { GameState } from '../../types';

interface PriorityPromptProps {
  gameState: GameState | null | undefined;
  playerId: string | null | undefined;
  onPass: () => void;
  onRespond?: () => void;
  /**
   * If true (the typical case), only render when there's something on
   * the stack worth responding to. When false (debug), render any time
   * we have priority — useful for wet tests.
   */
  onlyWhenStackActive?: boolean;
}

export function PriorityPrompt({
  gameState,
  playerId,
  onPass,
  onRespond,
  onlyWhenStackActive = true,
}: PriorityPromptProps) {
  const hasPriority = useMemo(() => {
    return Boolean(gameState && playerId && gameState.priority_player === playerId);
  }, [gameState, playerId]);

  const stackCount = gameState?.stack?.length ?? 0;
  const pendingCount = gameState?.pending_triggers?.length ?? 0;
  const stackActive = stackCount > 0 || pendingCount > 0;

  // Are there any non-PASS legal actions? If yes, "Respond" is meaningful.
  const canRespond = useMemo(() => {
    if (!gameState) return false;
    return gameState.legal_actions.some((a) => a.type !== 'PASS');
  }, [gameState]);

  if (!hasPriority) return null;
  if (onlyWhenStackActive && !stackActive) return null;

  // Top-of-stack info for context
  const topItem = stackCount > 0
    ? gameState!.stack[stackCount - 1]
    : null;

  return (
    <div
      data-testid="priority-prompt"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 pointer-events-auto"
    >
      <div
        className={clsx(
          'flex items-center gap-3 rounded-lg px-4 py-3 shadow-xl',
          'bg-game-surface border-2 border-purple-500',
          'animate-pulse-slow'
        )}
      >
        <div className="flex flex-col">
          <span className="text-xs uppercase tracking-wide text-purple-300">
            You have priority
          </span>
          <span className="text-sm text-gray-200">
            {topItem
              ? `Top of stack: ${topItem.source_name}`
              : pendingCount > 0
              ? `${pendingCount} trigger${pendingCount === 1 ? '' : 's'} queued`
              : 'Respond or pass'}
          </span>
        </div>

        <div className="flex gap-2">
          {canRespond && (
            <button
              type="button"
              onClick={onRespond}
              data-testid="priority-respond"
              className={clsx(
                'px-3 py-1.5 rounded text-sm font-semibold transition-all',
                'bg-amber-600 hover:bg-amber-500 text-white',
                'border border-amber-400'
              )}
            >
              Respond
            </button>
          )}
          <button
            type="button"
            onClick={onPass}
            data-testid="priority-pass"
            className={clsx(
              'px-3 py-1.5 rounded text-sm font-semibold transition-all',
              'bg-purple-700 hover:bg-purple-600 text-white',
              'border border-purple-400'
            )}
          >
            Pass {!canRespond && '(Space)'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default PriorityPrompt;
