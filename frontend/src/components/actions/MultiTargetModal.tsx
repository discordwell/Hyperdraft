/**
 * MultiTargetModal Component
 *
 * Modal overlay for selecting additional targets after the first target
 * has been selected via drag and drop.
 *
 * Used for spells like Sheltered by Ghosts which target your creature
 * AND let you exile an opponent's permanent.
 */

import { useCallback, useMemo, useEffect } from 'react';
import clsx from 'clsx';
import { Card } from '../cards';
import { useDragDropStore } from '../../hooks/useDragDrop';
import type { CardData } from '../../types';

interface MultiTargetModalProps {
  availableTargets: CardData[];
  firstTargetCard?: CardData;
  targetPrompt?: string;
  onSelect: (targetId: string) => void;
  onCancel: () => void;
}

export function MultiTargetModal({
  availableTargets,
  firstTargetCard,
  targetPrompt = 'Select a target',
  onSelect,
  onCancel,
}: MultiTargetModalProps) {
  const { multiTargetMode, multiTargetSpell, firstTarget, cancelMultiTarget } = useDragDropStore();

  const handleSelect = useCallback((targetId: string) => {
    onSelect(targetId);
    cancelMultiTarget();
  }, [onSelect, cancelMultiTarget]);

  const handleCancel = useCallback(() => {
    onCancel();
    cancelMultiTarget();
  }, [onCancel, cancelMultiTarget]);

  // Handle keyboard shortcuts
  useEffect(() => {
    if (!multiTargetMode) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleCancel();
      }
      // Number keys 1-9 to select targets
      const num = parseInt(e.key);
      if (num >= 1 && num <= availableTargets.length) {
        handleSelect(availableTargets[num - 1].id);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [multiTargetMode, availableTargets, handleCancel, handleSelect]);

  // Derive a better prompt based on spell text
  const derivedPrompt = useMemo(() => {
    if (targetPrompt && targetPrompt !== 'Select a target') {
      return targetPrompt;
    }
    // Default contextual prompts
    return 'Select the second target for this spell';
  }, [targetPrompt]);

  if (!multiTargetMode || !multiTargetSpell) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-md"
        onClick={handleCancel}
      />

      {/* Modal */}
      <div className="relative bg-gradient-to-b from-slate-800 to-slate-900 border-2 border-cyan-500/50 rounded-2xl p-6 shadow-2xl max-w-3xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col">
        {/* Spell info header */}
        <div className="mb-6 pb-4 border-b border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
            <h2 className="text-xl font-bold text-white">
              Additional Target Required
            </h2>
          </div>
          <p className="text-slate-300 text-sm mb-2">
            {derivedPrompt}
          </p>
          <div className="flex items-center gap-4 text-xs">
            {multiTargetSpell && (
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Spell:</span>
                <span className="bg-blue-600/30 text-blue-300 px-2 py-0.5 rounded">
                  {multiTargetSpell.description}
                </span>
              </div>
            )}
            {firstTarget && (
              <div className="flex items-center gap-2">
                <span className="text-slate-500">First Target:</span>
                <span className="bg-emerald-600/30 text-emerald-300 px-2 py-0.5 rounded">
                  {firstTargetCard?.name || 'Selected'}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* First target display (if we have the card data) */}
        {firstTargetCard && (
          <div className="mb-4">
            <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">First Target</p>
            <div className="inline-block opacity-60">
              <Card card={firstTargetCard} size="small" isSelected={true} />
            </div>
          </div>
        )}

        {/* Target Options */}
        <div className="flex-1 overflow-y-auto">
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-3">
            Choose Second Target ({availableTargets.length} available)
          </p>
          {availableTargets.length === 0 ? (
            <div className="text-slate-500 text-center py-8 italic border border-dashed border-slate-700 rounded-lg">
              No valid targets available. The spell cannot be cast.
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {availableTargets.map((target, index) => (
                <div
                  key={target.id}
                  className={clsx(
                    'cursor-pointer transition-all duration-200 relative group',
                    'hover:scale-105 hover:z-10',
                    'rounded-xl'
                  )}
                  onClick={() => handleSelect(target.id)}
                >
                  <Card
                    card={target}
                    size="small"
                    isTargetable={true}
                    showDetails={true}
                  />
                  {/* Keyboard shortcut hint */}
                  {index < 9 && (
                    <div className="absolute -top-2 -left-2 w-6 h-6 bg-slate-700 rounded-full flex items-center justify-center text-xs font-bold text-slate-300 border border-slate-600 group-hover:bg-cyan-600 group-hover:border-cyan-500 transition-colors">
                      {index + 1}
                    </div>
                  )}
                  {/* Hover overlay */}
                  <div className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity bg-cyan-500/20 pointer-events-none flex items-center justify-center">
                    <span className="bg-cyan-600 text-white px-3 py-1 rounded-lg text-sm font-bold shadow-lg">
                      Select
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-6 flex justify-between items-center pt-4 border-t border-slate-700">
          <p className="text-xs text-slate-500">
            Press 1-9 to quick-select or Escape to cancel
          </p>
          <button
            className="px-5 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg font-medium transition-colors"
            onClick={handleCancel}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export default MultiTargetModal;
