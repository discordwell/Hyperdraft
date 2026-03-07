/**
 * PKMChoiceModal - Trainer targeting / choice modal for Pokemon TCG.
 *
 * Shows when a trainer card or ability requires target selection.
 * Supports choice types: pkm_select_target, pkm_discard, pkm_select_pokemon, pkm_select_energy
 */

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PKMCard } from './PKMCard';
import { modalBackdrop, modalContent } from '../../utils/pkmAnimations';
import type { CardData, PendingChoice } from '../../types';

interface PKMChoiceModalProps {
  choice: PendingChoice;
  cards: CardData[];  // All field/hand cards for reference
  onSubmit: (choiceId: string, selected: string[]) => void;
  onCardHover?: (card: CardData | null) => void;
}

export function PKMChoiceModal({ choice, cards, onSubmit, onCardHover }: PKMChoiceModalProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Reset selection when the choice changes
  useEffect(() => setSelected(new Set()), [choice.id]);

  const optionCards = choice.options.map((opt: any) => {
    const id = typeof opt === 'string' ? opt : opt.id;
    return cards.find(c => c.id === id) || null;
  }).filter(Boolean) as CardData[];

  // Text-only options (for non-card choices)
  const textOptions = choice.options.filter((opt: any) => {
    const id = typeof opt === 'string' ? opt : opt.id;
    return !cards.find(c => c.id === id);
  });

  const toggleOption = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        if (choice.max_choices === 1) {
          next.clear();
        }
        if (next.size < choice.max_choices) {
          next.add(id);
        }
      }
      return next;
    });
  }, [choice.max_choices]);

  const handleConfirm = useCallback(() => {
    if (selected.size < choice.min_choices) return;
    onSubmit(choice.id, Array.from(selected));
  }, [selected, choice, onSubmit]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && choice.min_choices === 0) {
        onSubmit(choice.id, []);
        return;
      }
      if (e.key === 'Enter' && selected.size >= choice.min_choices) {
        handleConfirm();
        return;
      }
      // Number keys 1-9 to select options
      const num = parseInt(e.key);
      if (num >= 1 && num <= 9) {
        const allOptions = [...optionCards, ...textOptions];
        const idx = num - 1;
        if (idx < allOptions.length) {
          const opt = allOptions[idx];
          const id = (opt as CardData).id || (typeof opt === 'string' ? opt : (opt as any).id);
          if (id) toggleOption(id);
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [choice, selected, handleConfirm, optionCards, textOptions, toggleOption, onSubmit]);

  const canConfirm = selected.size >= choice.min_choices && selected.size <= choice.max_choices;

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
        variants={modalBackdrop}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        <motion.div
          className="bg-gray-900 border border-emerald-700 rounded-xl p-6 max-w-2xl w-full mx-4"
          variants={modalContent}
          initial="initial"
          animate="animate"
          exit="exit"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Title */}
          <h2 className="text-lg font-bold text-white mb-1">{choice.prompt}</h2>
          <p className="text-gray-400 text-sm mb-4">
            {choice.min_choices === choice.max_choices
              ? `Select ${choice.min_choices}.`
              : `Select ${choice.min_choices} to ${choice.max_choices}.`
            }
            {choice.min_choices === 0 && ' (Press Escape to cancel)'}
          </p>

          {/* Card options */}
          {optionCards.length > 0 && (
            <div className="flex flex-wrap gap-3 justify-center mb-4">
              {optionCards.map((card, idx) => (
                <div
                  key={card.id}
                  className={`relative cursor-pointer transition-all ${
                    selected.has(card.id) ? 'ring-2 ring-emerald-400 rounded-lg scale-105' : 'hover:scale-105'
                  }`}
                  onClick={() => toggleOption(card.id)}
                  onMouseEnter={() => onCardHover?.(card)}
                  onMouseLeave={() => onCardHover?.(null)}
                >
                  <PKMCard card={card} isSelected={selected.has(card.id)} />
                  <div className="absolute top-0 left-0 bg-gray-800/80 text-gray-300 text-[9px] font-bold px-1 rounded-br">
                    {idx + 1}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Text options */}
          {textOptions.length > 0 && (
            <div className="space-y-2 mb-4">
              {textOptions.map((opt: any, idx: number) => {
                const id = typeof opt === 'string' ? opt : opt.id;
                const label = typeof opt === 'string' ? opt : (opt.label || opt.description || opt.id);
                return (
                  <button
                    key={id}
                    onClick={() => toggleOption(id)}
                    className={`w-full text-left px-4 py-2 rounded-lg border transition-all ${
                      selected.has(id)
                        ? 'border-emerald-500 bg-emerald-900/30 text-emerald-300'
                        : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-500'
                    }`}
                  >
                    <span className="text-gray-500 text-xs mr-2">{optionCards.length + idx + 1}.</span>
                    {label}
                  </button>
                );
              })}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-center gap-3">
            {choice.min_choices === 0 && (
              <button
                onClick={() => onSubmit(choice.id, [])}
                className="px-5 py-2 bg-gray-700 text-gray-300 rounded-lg font-bold hover:bg-gray-600 transition-all"
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleConfirm}
              disabled={!canConfirm}
              className={`px-5 py-2 rounded-lg font-bold transition-all ${
                canConfirm
                  ? 'bg-emerald-600 text-white hover:bg-emerald-500'
                  : 'bg-gray-700 text-gray-500 cursor-not-allowed'
              }`}
            >
              Confirm ({selected.size})
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
