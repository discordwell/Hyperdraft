/**
 * YGOBanishedModal - Ethereal-styled modal for viewing banished cards.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { modalBackdrop, modalContent } from '../../utils/ygoAnimations';
import { YGOCard } from './YGOCard';
import type { CardData } from '../../types';

interface YGOBanishedModalProps {
  isOpen: boolean;
  onClose: () => void;
  myBanished: CardData[];
  oppBanished: CardData[];
  tab: 'mine' | 'opp';
  onTabChange: (tab: 'mine' | 'opp') => void;
}

export default function YGOBanishedModal({
  isOpen,
  onClose,
  myBanished,
  oppBanished,
  tab,
  onTabChange,
}: YGOBanishedModalProps) {
  const cards = tab === 'mine' ? myBanished : oppBanished;

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
            className="bg-ygo-dark/95 border border-gray-600/50 rounded-xl p-6 max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl"
            onClick={e => e.stopPropagation()}
            style={{
              background: 'linear-gradient(135deg, rgba(10,14,26,0.95) 0%, rgba(30,20,40,0.95) 100%)',
            }}
          >
            <h3 className="text-lg font-bold text-gray-300 mb-3 tracking-wide">
              Banished Zone
            </h3>

            {/* Tabs */}
            <div className="flex gap-2 mb-4">
              {(['mine', 'opp'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => onTabChange(t)}
                  className={`px-3 py-1 text-xs font-bold rounded transition-colors ${
                    tab === t
                      ? 'bg-gray-600 text-white'
                      : 'bg-gray-800 text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {t === 'mine' ? 'Your Cards' : "Opponent's"}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              {cards.map((card, i) => (
                <YGOCard key={`${card.id}-${i}`} card={card} size="md" animate={false} />
              ))}
              {cards.length === 0 && (
                <p className="text-gray-600 text-sm italic">No banished cards</p>
              )}
            </div>

            <button
              onClick={onClose}
              className="mt-4 px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors"
            >
              Close
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
