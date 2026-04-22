/**
 * PKMSetupOverlay - Setup phase UI for Pokemon TCG.
 *
 * Shows during game setup when the player needs to choose:
 * 1. Active Pokemon from basics in hand
 * 2. Bench Pokemon (optional) from remaining basics
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PKMCard } from './PKMCard';
import { modalBackdrop, modalContent } from '../../utils/pkmAnimations';
import type { CardData, PendingChoice } from '../../types';

interface PKMSetupOverlayProps {
  choice: PendingChoice;
  hand: CardData[];
  onSubmit: (choiceId: string, selected: string[]) => void;
}

export function PKMSetupOverlay({ choice, hand, onSubmit }: PKMSetupOverlayProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Reset selection when the choice changes
  useEffect(() => setSelected(new Set()), [choice.id]);

  const isSelectActive = choice.choice_type === 'pkm_select_active';
  const isSelectBench = choice.choice_type === 'pkm_select_bench';

  const optionIds = new Set(choice.options.map((o) => typeof o === 'string' ? o : o.id));
  const selectableCards = hand.filter(c => optionIds.has(c.id));

  const toggleCard = (cardId: string) => {
    const next = new Set(selected);
    if (next.has(cardId)) {
      next.delete(cardId);
    } else {
      if (isSelectActive) {
        // Single select for active
        next.clear();
        next.add(cardId);
      } else {
        // Multi-select for bench, up to max_choices
        if (next.size < choice.max_choices) {
          next.add(cardId);
        }
      }
    }
    setSelected(next);
  };

  const handleConfirm = () => {
    if (isSelectActive && selected.size !== 1) return;
    onSubmit(choice.id, Array.from(selected));
  };

  const canConfirm = isSelectActive ? selected.size === 1 : selected.size >= choice.min_choices;

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50"
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
        >
          {/* Progress indicator */}
          <div className="flex items-center gap-2 mb-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              isSelectActive ? 'bg-emerald-600 text-white' : 'bg-gray-700 text-gray-400'
            }`}>1</div>
            <div className="h-0.5 flex-1 bg-gray-700">
              <div className={`h-full transition-all ${isSelectBench ? 'bg-emerald-500 w-full' : 'w-0'}`} />
            </div>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              isSelectBench ? 'bg-emerald-600 text-white' : 'bg-gray-700 text-gray-400'
            }`}>2</div>
          </div>

          {/* Title */}
          <h2 className="text-xl font-bold text-white mb-1">
            {isSelectActive ? 'Choose Your Active Pokemon' : 'Place Bench Pokemon'}
          </h2>
          <p className="text-gray-400 text-sm mb-4">
            {isSelectActive
              ? 'Select a Basic Pokemon to be your Active Pokemon.'
              : `Select up to ${choice.max_choices} Basic Pokemon for your bench (optional).`
            }
          </p>

          {/* Card grid */}
          <div className="flex flex-wrap gap-3 justify-center mb-6 min-h-[120px]">
            {selectableCards.map(card => (
              <div
                key={card.id}
                className={`cursor-pointer transition-all ${
                  selected.has(card.id) ? 'ring-2 ring-emerald-400 rounded-lg scale-105' : 'opacity-70 hover:opacity-100'
                }`}
                onClick={() => toggleCard(card.id)}
              >
                <PKMCard card={card} isSelected={selected.has(card.id)} />
              </div>
            ))}
            {selectableCards.length === 0 && (
              <div className="text-gray-500 text-sm py-8">No eligible cards.</div>
            )}
          </div>

          {/* Non-selectable cards shown grayed */}
          {hand.filter(c => !optionIds.has(c.id)).length > 0 && (
            <div className="mb-4">
              <div className="text-gray-600 text-xs mb-2">Other cards in hand:</div>
              <div className="flex flex-wrap gap-2 justify-center opacity-40">
                {hand.filter(c => !optionIds.has(c.id)).map(card => (
                  <PKMCard key={card.id} card={card} />
                ))}
              </div>
            </div>
          )}

          {/* Confirm */}
          <div className="flex justify-center gap-3">
            {isSelectBench && (
              <button
                onClick={() => onSubmit(choice.id, [])}
                className="px-6 py-2 bg-gray-700 text-gray-300 rounded-lg font-bold hover:bg-gray-600 transition-all"
              >
                Skip
              </button>
            )}
            <button
              onClick={handleConfirm}
              disabled={!canConfirm}
              className={`px-6 py-2 rounded-lg font-bold transition-all ${
                canConfirm
                  ? 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg'
                  : 'bg-gray-700 text-gray-500 cursor-not-allowed'
              }`}
            >
              {isSelectActive ? 'Set Active' : `Place on Bench (${selected.size})`}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
