/**
 * ActionMenu Component
 *
 * Displays available actions and handles action selection.
 */

import clsx from 'clsx';
import type { LegalActionData } from '../../types';

interface ActionMenuProps {
  actions: LegalActionData[];
  selectedAction?: LegalActionData | null;
  canAct: boolean;
  isLoading?: boolean;
  onActionSelect: (action: LegalActionData) => void;
  onPass: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ActionMenu({
  actions,
  selectedAction,
  canAct,
  isLoading = false,
  onActionSelect,
  onPass,
  onConfirm,
  onCancel,
}: ActionMenuProps) {
  const hasActions = actions.length > 0;
  const hasSelectedAction = selectedAction !== null;

  // Filter out PASS from the actions list (we have a dedicated button)
  const displayActions = actions.filter((a) => a.type !== 'PASS');

  return (
    <div className="p-4 rounded-lg bg-game-surface border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-400 uppercase tracking-wide">
          Actions
        </span>
        {canAct && (
          <span className="text-xs bg-game-accent text-white px-2 py-0.5 rounded-full animate-pulse">
            Your Turn to Act
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
          {hasSelectedAction && (
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
                key={`${action.type}-${action.card_id || action.ability_id || idx}`}
                className={clsx(
                  'px-3 py-2 rounded text-sm font-semibold transition-all',
                  {
                    'bg-blue-600 text-white hover:bg-blue-500':
                      selectedAction?.card_id === action.card_id &&
                      selectedAction?.type === action.type,
                    'bg-gray-700 text-gray-200 hover:bg-gray-600':
                      selectedAction?.card_id !== action.card_id ||
                      selectedAction?.type !== action.type,
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
            {hasSelectedAction && !selectedAction.requires_targets && (
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
