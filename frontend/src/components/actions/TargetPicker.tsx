/**
 * TargetPicker Component
 *
 * Overlay for selecting targets during spell/ability resolution.
 */

import clsx from 'clsx';

interface TargetPickerProps {
  isActive: boolean;
  selectedTargets: string[];
  requiredCount: number;
  targetType?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function TargetPicker({
  isActive,
  selectedTargets,
  requiredCount,
  targetType = 'target',
  onConfirm,
  onCancel,
}: TargetPickerProps) {
  if (!isActive) return null;

  const hasEnoughTargets = selectedTargets.length >= requiredCount;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50">
      <div className="bg-game-surface border-2 border-game-accent rounded-lg p-4 shadow-xl shadow-game-accent/30">
        <div className="text-center mb-3">
          <div className="text-lg font-semibold text-white">
            Select {requiredCount} {targetType}
            {requiredCount > 1 ? 's' : ''}
          </div>
          <div className="text-sm text-gray-400">
            Selected: {selectedTargets.length} / {requiredCount}
          </div>
        </div>

        {/* Selected targets indicator */}
        {selectedTargets.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3 justify-center">
            {selectedTargets.map((targetId, idx) => (
              <span
                key={targetId}
                className="px-2 py-1 bg-blue-600 text-white text-xs rounded"
              >
                Target {idx + 1}
              </span>
            ))}
          </div>
        )}

        {/* Instructions */}
        <div className="text-xs text-gray-400 text-center mb-3">
          Click valid targets on the battlefield to select them.
          <br />
          Valid targets are highlighted with a green glow.
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 justify-center">
          <button
            className={clsx(
              'px-4 py-2 rounded font-semibold transition-all',
              hasEnoughTargets
                ? 'bg-green-600 text-white hover:bg-green-500'
                : 'bg-gray-600 text-gray-400 cursor-not-allowed'
            )}
            onClick={onConfirm}
            disabled={!hasEnoughTargets}
          >
            Confirm Targets
          </button>
          <button
            className="px-4 py-2 rounded font-semibold bg-red-600 text-white hover:bg-red-500 transition-all"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export default TargetPicker;
