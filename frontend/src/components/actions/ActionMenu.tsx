/**
 * ActionMenu Component
 *
 * Displays available actions and handles action selection.
 * Includes smart auto-pass controls for less tedious priority handling.
 */

import clsx from 'clsx';
import type { LegalActionData } from '../../types';
import type { AutoPassMode } from '../../stores/gameStore';

interface ActionMenuProps {
  actions: LegalActionData[];
  selectedAction?: LegalActionData | null;
  canAct: boolean;
  isLoading?: boolean;
  autoPassMode: AutoPassMode;
  hasActionsOtherThanPass: boolean;
  onActionSelect: (action: LegalActionData) => void;
  onPass: () => void;
  onConfirm: () => void;
  onCancel: () => void;
  onSetAutoPassMode: (mode: AutoPassMode) => void;
  onPassUntilEndOfTurn: () => void;
}

export function ActionMenu({
  actions,
  selectedAction,
  canAct,
  isLoading = false,
  autoPassMode,
  hasActionsOtherThanPass,
  onActionSelect,
  onPass,
  onConfirm,
  onCancel,
  onSetAutoPassMode,
  onPassUntilEndOfTurn,
}: ActionMenuProps) {
  const hasSelectedAction = selectedAction != null && selectedAction !== undefined;

  // Filter out PASS from the actions list (we have a dedicated button)
  const displayActions = actions.filter((a) => a.type !== 'PASS');

  const isSameAction = (a: LegalActionData | null | undefined, b: LegalActionData): boolean => {
    if (!a) return false;
    return (
      a.type === b.type &&
      a.card_id === b.card_id &&
      a.ability_id === b.ability_id &&
      a.source_id === b.source_id
    );
  };

  // Determine if auto-pass is actively working
  const isAutoPassing = autoPassMode !== 'off' && !hasActionsOtherThanPass;

  return (
    <div className="p-4 rounded-lg bg-game-surface border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-400 uppercase tracking-wide">
          Actions
        </span>
        {canAct && !isAutoPassing && (
          <span className="text-xs bg-game-accent text-white px-2 py-0.5 rounded-full animate-pulse">
            Your Turn to Act
          </span>
        )}
        {isAutoPassing && (
          <span className="text-xs bg-green-600 text-white px-2 py-0.5 rounded-full">
            Auto-passing
          </span>
        )}
      </div>

      {!canAct ? (
        <div className="text-gray-500 text-sm italic text-center py-4">
          Waiting for opponent...
        </div>
      ) : (
        <>
          {/* Selected Action Info */}
          {hasSelectedAction && selectedAction && (
            <div className="mb-3 p-2 bg-blue-900/30 border border-blue-500 rounded">
              <div className="text-sm text-blue-300">
                Selected: <span className="font-semibold">{selectedAction.description}</span>
              </div>
              {selectedAction.requires_targets && (
                <div className="text-xs text-blue-400 mt-1">
                  Click a valid target to complete this action
                </div>
              )}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex flex-wrap gap-2 mb-3">
            {displayActions.map((action, idx) => (
              <button
                key={`${action.type}:${action.card_id ?? 'none'}:${action.ability_id ?? 'none'}:${action.source_id ?? 'none'}:${idx}`}
                className={clsx(
                  'px-3 py-2 rounded text-sm font-semibold transition-all',
                  {
                    'bg-blue-600 text-white hover:bg-blue-500':
                      isSameAction(selectedAction, action),
                    'bg-gray-700 text-gray-200 hover:bg-gray-600':
                      !isSameAction(selectedAction, action),
                    'opacity-50 cursor-not-allowed': isLoading,
                  }
                )}
                onClick={() => onActionSelect(action)}
                disabled={isLoading}
              >
                {action.description}
                {action.requires_mana && ' 💎'}
              </button>
            ))}
          </div>

          {/* Primary Action Buttons */}
          <div className="flex gap-2">
            {/* Pass Button */}
            <button
              className={clsx(
                'flex-1 px-4 py-2 rounded font-semibold transition-all',
                'bg-gray-600 text-white hover:bg-gray-500',
                {
                  'opacity-50 cursor-not-allowed': isLoading,
                }
              )}
              onClick={onPass}
              disabled={isLoading}
            >
              {isLoading ? 'Processing...' : 'Pass Priority'}
            </button>

            {/* Confirm Button (when action is selected) */}
            {hasSelectedAction && selectedAction && !selectedAction.requires_targets && (
              <button
                className={clsx(
                  'flex-1 px-4 py-2 rounded font-semibold transition-all',
                  'bg-green-600 text-white hover:bg-green-500',
                  {
                    'opacity-50 cursor-not-allowed': isLoading,
                  }
                )}
                onClick={onConfirm}
                disabled={isLoading}
              >
                Confirm Action
              </button>
            )}

            {/* Cancel Button (when action is selected) */}
            {hasSelectedAction && (
              <button
                className={clsx(
                  'px-4 py-2 rounded font-semibold transition-all',
                  'bg-red-600 text-white hover:bg-red-500',
                  {
                    'opacity-50 cursor-not-allowed': isLoading,
                  }
                )}
                onClick={onCancel}
                disabled={isLoading}
              >
                Cancel
              </button>
            )}
          </div>

          {/* F6 - Pass Until End of Turn */}
          <div className="mt-3 pt-3 border-t border-gray-700">
            <button
              className={clsx(
                'w-full px-4 py-2 rounded font-semibold transition-all text-sm',
                {
                  'bg-amber-600 text-white hover:bg-amber-500': autoPassMode !== 'end_of_turn',
                  'bg-red-600 text-white hover:bg-red-500': autoPassMode === 'end_of_turn',
                  'opacity-50 cursor-not-allowed': isLoading,
                }
              )}
              onClick={() => {
                if (autoPassMode === 'end_of_turn') {
                  onSetAutoPassMode('no_actions');
                } else {
                  onPassUntilEndOfTurn();
                }
              }}
              disabled={isLoading}
              title="Press F6 to toggle"
            >
              {autoPassMode === 'end_of_turn' ? 'Cancel Pass Until End of Turn' : 'Pass Until End of Turn (F6)'}
            </button>
          </div>

          {/* Auto-Pass Settings */}
          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400 uppercase tracking-wide">
                Auto-Pass Mode
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              <button
                className={clsx(
                  'px-2 py-1 rounded text-xs font-medium transition-all',
                  {
                    'bg-blue-600 text-white': autoPassMode === 'off',
                    'bg-gray-700 text-gray-300 hover:bg-gray-600': autoPassMode !== 'off',
                  }
                )}
                onClick={() => onSetAutoPassMode('off')}
                title="Never auto-pass - always wait for manual input"
              >
                Off
              </button>
              <button
                className={clsx(
                  'px-2 py-1 rounded text-xs font-medium transition-all',
                  {
                    'bg-blue-600 text-white': autoPassMode === 'no_actions',
                    'bg-gray-700 text-gray-300 hover:bg-gray-600': autoPassMode !== 'no_actions',
                  }
                )}
                onClick={() => onSetAutoPassMode('no_actions')}
                title="Auto-pass when you have no spells or abilities to play"
              >
                Smart
              </button>
              <button
                className={clsx(
                  'px-2 py-1 rounded text-xs font-medium transition-all',
                  {
                    'bg-blue-600 text-white': autoPassMode === 'stack_empty',
                    'bg-gray-700 text-gray-300 hover:bg-gray-600': autoPassMode !== 'stack_empty',
                  }
                )}
                onClick={() => onSetAutoPassMode('stack_empty')}
                title="Pass until something is put on the stack"
              >
                Until Stack
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              {autoPassMode === 'off' && 'You must manually pass priority every time.'}
              {autoPassMode === 'no_actions' && 'Automatically passes when you have no meaningful actions.'}
              {autoPassMode === 'stack_empty' && 'Passes automatically until something goes on the stack.'}
              {autoPassMode === 'end_of_turn' && 'Passing until end of turn. Click to cancel.'}
            </p>
          </div>

          {/* Loading Indicator */}
          {isLoading && (
            <div className="mt-2 text-center">
              <div className="inline-flex items-center gap-2 text-gray-400">
                <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                Processing...
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default ActionMenu;
