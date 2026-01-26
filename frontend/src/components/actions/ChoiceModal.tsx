/**
 * ChoiceModal Component
 *
 * Modal overlay for player choices like modal abilities, target selection,
 * scry, surveil, and other game decisions.
 */

import { useCallback, useMemo, useState, useEffect } from 'react';
import clsx from 'clsx';
import { Card } from '../cards';
import type { PendingChoice, CardData } from '../../types';

interface ChoiceModalProps {
  pendingChoice: PendingChoice;
  battlefield: CardData[];
  hand: CardData[];
  graveyard: Record<string, CardData[]>;
  onSubmit: (selectedIds: string[]) => void;
  onCancel?: () => void;
  isLoading?: boolean;
}

export function ChoiceModal({
  pendingChoice,
  battlefield,
  hand,
  graveyard,
  onSubmit,
  onCancel,
  isLoading = false,
}: ChoiceModalProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const { choice_type, prompt, options, min_choices, max_choices } = pendingChoice;

  // Reset selection when pending choice changes
  useEffect(() => {
    setSelectedIds([]);
  }, [pendingChoice.source_id, pendingChoice.prompt]);

  // Check if selection is valid
  const isSelectionValid = useMemo(() => {
    return selectedIds.length >= min_choices && selectedIds.length <= max_choices;
  }, [selectedIds, min_choices, max_choices]);

  // Check if we can select more
  const canSelectMore = useMemo(() => {
    return selectedIds.length < max_choices;
  }, [selectedIds, max_choices]);

  // Toggle selection of an option
  const toggleSelection = useCallback((optionId: string) => {
    setSelectedIds((prev) => {
      const isSelected = prev.includes(optionId);

      if (isSelected) {
        // Deselect
        return prev.filter((id) => id !== optionId);
      } else if (canSelectMore) {
        // Select
        // If single select and something is already selected, replace it
        if (max_choices === 1) {
          return [optionId];
        }
        return [...prev, optionId];
      }

      return prev;
    });
  }, [canSelectMore, max_choices]);

  // Handle confirm
  const handleConfirm = useCallback(() => {
    if (isSelectionValid && !isLoading) {
      onSubmit(selectedIds);
    }
  }, [isSelectionValid, isLoading, selectedIds, onSubmit]);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape to cancel (if allowed)
      if (e.key === 'Escape' && onCancel) {
        onCancel();
        return;
      }

      // Enter to confirm (if valid)
      if (e.key === 'Enter' && isSelectionValid && !isLoading) {
        handleConfirm();
        return;
      }

      // Number keys 1-9 to toggle selection for modal choices
      if (choice_type === 'modal') {
        const num = parseInt(e.key);
        if (num >= 1 && num <= options.length) {
          toggleSelection(options[num - 1].id);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [choice_type, options, isSelectionValid, isLoading, handleConfirm, toggleSelection, onCancel]);

  // Build a lookup map of card data by ID
  const cardLookup = useMemo(() => {
    const lookup: Record<string, CardData> = {};

    // Add battlefield cards
    battlefield.forEach((card) => {
      lookup[card.id] = card;
    });

    // Add hand cards
    hand.forEach((card) => {
      lookup[card.id] = card;
    });

    // Add graveyard cards
    Object.values(graveyard).forEach((cards) => {
      cards.forEach((card) => {
        lookup[card.id] = card;
      });
    });

    return lookup;
  }, [battlefield, hand, graveyard]);

  // Check if an option represents a card (for target choices)
  const isTargetChoice = choice_type === 'target';

  // Get icon based on choice type
  const choiceIcon = useMemo(() => {
    switch (choice_type) {
      case 'modal':
        return '?';
      case 'target':
        return '!';
      case 'scry':
        return 'S';
      case 'surveil':
        return 'E';
      default:
        return '*';
    }
  }, [choice_type]);

  // Get color theme based on choice type
  const themeColor = useMemo(() => {
    switch (choice_type) {
      case 'modal':
        return 'cyan';
      case 'target':
        return 'amber';
      case 'scry':
        return 'blue';
      case 'surveil':
        return 'purple';
      default:
        return 'cyan';
    }
  }, [choice_type]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-md"
        onClick={onCancel}
      />

      {/* Modal */}
      <div className="relative bg-gradient-to-b from-slate-800 to-slate-900 border-2 border-opacity-50 rounded-2xl p-6 shadow-2xl max-w-4xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col"
        style={{ borderColor: `var(--color-${themeColor}-500, #06b6d4)` }}
      >
        {/* Header */}
        <div className="mb-6 pb-4 border-b border-slate-700">
          <div className="flex items-center gap-3 mb-2">
            <div className={clsx(
              'w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg',
              themeColor === 'cyan' && 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50',
              themeColor === 'amber' && 'bg-amber-500/20 text-amber-400 border border-amber-500/50',
              themeColor === 'blue' && 'bg-blue-500/20 text-blue-400 border border-blue-500/50',
              themeColor === 'purple' && 'bg-purple-500/20 text-purple-400 border border-purple-500/50',
            )}>
              {choiceIcon}
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">
                {choice_type === 'modal' && 'Choose a Mode'}
                {choice_type === 'target' && 'Select Target'}
                {choice_type === 'scry' && 'Scry'}
                {choice_type === 'surveil' && 'Surveil'}
                {!['modal', 'target', 'scry', 'surveil'].includes(choice_type) && 'Make a Choice'}
              </h2>
              <p className="text-slate-400 text-sm">{prompt}</p>
            </div>
          </div>

          {/* Selection info */}
          <div className="flex items-center gap-4 text-xs mt-3">
            <div className="flex items-center gap-2">
              <span className="text-slate-500">Selected:</span>
              <span className={clsx(
                'px-2 py-0.5 rounded font-medium',
                isSelectionValid
                  ? 'bg-emerald-600/30 text-emerald-300'
                  : 'bg-slate-600/30 text-slate-400'
              )}>
                {selectedIds.length} / {max_choices === min_choices ? min_choices : `${min_choices}-${max_choices}`}
              </span>
            </div>
            {min_choices !== max_choices && (
              <div className="text-slate-500">
                (min: {min_choices}, max: {max_choices})
              </div>
            )}
          </div>
        </div>

        {/* Options */}
        <div className="flex-1 overflow-y-auto">
          {options.length === 0 ? (
            <div className="text-slate-500 text-center py-8 italic border border-dashed border-slate-700 rounded-lg">
              No options available.
            </div>
          ) : isTargetChoice ? (
            // Target choice - show cards if available
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {options.map((option, index) => {
                const cardData = cardLookup[option.id];
                const isSelected = selectedIds.includes(option.id);
                const isDisabled = !isSelected && !canSelectMore;

                if (cardData) {
                  // Render as card
                  return (
                    <div
                      key={option.id}
                      className={clsx(
                        'cursor-pointer transition-all duration-200 relative group',
                        isSelected && 'scale-105 z-10',
                        isDisabled && 'opacity-40 cursor-not-allowed',
                        !isDisabled && 'hover:scale-105 hover:z-10',
                        'rounded-xl'
                      )}
                      onClick={() => !isDisabled && toggleSelection(option.id)}
                    >
                      <Card
                        card={cardData}
                        size="small"
                        isSelected={isSelected}
                        isTargetable={!isSelected && !isDisabled}
                        showDetails={true}
                      />
                      {/* Keyboard shortcut hint */}
                      {index < 9 && (
                        <div className={clsx(
                          'absolute -top-2 -left-2 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border transition-colors',
                          isSelected
                            ? 'bg-emerald-600 border-emerald-500 text-white'
                            : 'bg-slate-700 border-slate-600 text-slate-300 group-hover:bg-amber-600 group-hover:border-amber-500'
                        )}>
                          {index + 1}
                        </div>
                      )}
                    </div>
                  );
                } else {
                  // Render as button (fallback for non-card targets)
                  return (
                    <button
                      key={option.id}
                      className={clsx(
                        'p-4 rounded-xl border-2 transition-all duration-200 text-left',
                        isSelected
                          ? 'bg-emerald-600/30 border-emerald-500 text-emerald-100'
                          : isDisabled
                            ? 'bg-slate-800/50 border-slate-700 text-slate-500 cursor-not-allowed'
                            : 'bg-slate-800 border-slate-600 text-slate-200 hover:border-amber-500 hover:bg-amber-500/10'
                      )}
                      onClick={() => !isDisabled && toggleSelection(option.id)}
                      disabled={isDisabled}
                    >
                      <div className="font-medium">{option.label}</div>
                      {option.description && (
                        <div className="text-xs mt-1 opacity-70">{option.description}</div>
                      )}
                    </button>
                  );
                }
              })}
            </div>
          ) : (
            // Modal/other choices - show as buttons
            <div className="flex flex-col gap-3">
              {options.map((option, index) => {
                const isSelected = selectedIds.includes(option.id);
                const isDisabled = !isSelected && !canSelectMore;

                return (
                  <button
                    key={option.id}
                    className={clsx(
                      'p-4 rounded-xl border-2 transition-all duration-200 text-left flex items-start gap-4',
                      isSelected
                        ? 'bg-cyan-600/30 border-cyan-500 text-cyan-100'
                        : isDisabled
                          ? 'bg-slate-800/50 border-slate-700 text-slate-500 cursor-not-allowed'
                          : 'bg-slate-800 border-slate-600 text-slate-200 hover:border-cyan-500 hover:bg-cyan-500/10'
                    )}
                    onClick={() => !isDisabled && toggleSelection(option.id)}
                    disabled={isDisabled}
                  >
                    {/* Number badge */}
                    {index < 9 && (
                      <div className={clsx(
                        'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border flex-shrink-0 transition-colors',
                        isSelected
                          ? 'bg-cyan-600 border-cyan-500 text-white'
                          : 'bg-slate-700 border-slate-600 text-slate-300'
                      )}>
                        {index + 1}
                      </div>
                    )}
                    <div className="flex-1">
                      <div className="font-medium text-lg">{option.label}</div>
                      {option.description && (
                        <div className="text-sm mt-1 opacity-80">{option.description}</div>
                      )}
                    </div>
                    {/* Selection indicator */}
                    {isSelected && (
                      <div className="w-6 h-6 rounded-full bg-cyan-500 flex items-center justify-center flex-shrink-0">
                        <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-6 flex justify-between items-center pt-4 border-t border-slate-700">
          <p className="text-xs text-slate-500">
            {choice_type === 'modal'
              ? 'Press 1-9 to select, Enter to confirm'
              : 'Click to select, Enter to confirm'
            }
            {onCancel && ', Escape to cancel'}
          </p>
          <div className="flex gap-3">
            {onCancel && (
              <button
                className="px-5 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg font-medium transition-colors"
                onClick={onCancel}
                disabled={isLoading}
              >
                Cancel
              </button>
            )}
            <button
              className={clsx(
                'px-6 py-2 rounded-lg font-medium transition-all duration-200',
                isSelectionValid && !isLoading
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-500/30'
                  : 'bg-slate-700 text-slate-500 cursor-not-allowed'
              )}
              onClick={handleConfirm}
              disabled={!isSelectionValid || isLoading}
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Submitting...
                </span>
              ) : (
                `Confirm${selectedIds.length > 0 ? ` (${selectedIds.length})` : ''}`
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ChoiceModal;
