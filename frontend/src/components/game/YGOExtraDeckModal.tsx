/**
 * YGOExtraDeckModal - Purple-themed modal for viewing Extra Deck cards.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { modalBackdrop, modalContent } from '../../utils/ygoAnimations';
import { YGOCard } from './YGOCard';
import type { CardData } from '../../types';

interface YGOExtraDeckModalProps {
  isOpen: boolean;
  onClose: () => void;
  cards: CardData[];
}

export default function YGOExtraDeckModal({
  isOpen,
  onClose,
  cards,
}: YGOExtraDeckModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          variants={modalBackdrop}
          initial="initial"
          animate="animate"
          exit="exit"
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-40"
          onClick={onClose}
        >
          <motion.div
            variants={modalContent}
            initial="initial"
            animate="animate"
            exit="exit"
            className="bg-ygo-dark/95 border border-ygo-purple/40 rounded-xl p-6 max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <h3 className="text-lg font-bold text-purple-300 mb-4 tracking-wide">
              Extra Deck
            </h3>

            <div className="flex flex-wrap gap-2">
              {cards.map((card, i) => (
                <YGOCard key={`${card.id}-${i}`} card={card} size="md" animate={false} />
              ))}
              {cards.length === 0 && (
                <p className="text-gray-600 text-sm italic">Extra Deck is empty</p>
              )}
            </div>

            <button
              onClick={onClose}
              className="mt-4 px-4 py-1.5 bg-purple-800 hover:bg-purple-700 text-white text-sm rounded transition-colors"
            >
              Close
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
