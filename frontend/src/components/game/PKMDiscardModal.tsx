/**
 * PKMDiscardModal - Pokemon TCG discard pile viewer.
 *
 * Modal showing cards in both players' discard piles with tab switching,
 * card category filtering, and hover previews.
 */

import { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { CardData } from '../../types';
import { PKMCard } from './PKMCard';
import { modalBackdrop, modalContent } from '../../utils/pkmAnimations';

type Tab = 'mine' | 'opponent';
type Filter = 'all' | 'pokemon' | 'trainer' | 'energy';

interface PKMDiscardModalProps {
  isOpen: boolean;
  onClose: () => void;
  myGraveyard: CardData[];
  opponentGraveyard: CardData[];
  myName: string;
  opponentName: string;
  onCardHover?: (card: CardData | null) => void;
}

function filterCards(cards: CardData[], filter: Filter): CardData[] {
  if (filter === 'all') return cards;
  if (filter === 'pokemon') {
    return cards.filter((c) => c.types.includes('POKEMON'));
  }
  if (filter === 'trainer') {
    return cards.filter(
      (c) =>
        c.types.includes('ITEM') ||
        c.types.includes('SUPPORTER') ||
        c.types.includes('STADIUM') ||
        c.types.includes('POKEMON_TOOL')
    );
  }
  // energy
  return cards.filter((c) => c.types.includes('ENERGY'));
}

export function PKMDiscardModal({
  isOpen,
  onClose,
  myGraveyard,
  opponentGraveyard,
  myName,
  opponentName,
  onCardHover,
}: PKMDiscardModalProps) {
  const [activeTab, setActiveTab] = useState<Tab>('mine');
  const [filter, setFilter] = useState<Filter>('all');

  // Escape key closes the modal
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, onClose]);

  const sourceCards = activeTab === 'mine' ? myGraveyard : opponentGraveyard;
  const displayedCards = filterCards(sourceCards, filter);

  const FILTERS: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'pokemon', label: 'Pokemon' },
    { key: 'trainer', label: 'Trainer' },
    { key: 'energy', label: 'Energy' },
  ];

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          variants={modalBackdrop}
          initial="initial"
          animate="animate"
          exit="exit"
          onClick={onClose}
        >
          <motion.div
            className="relative w-full max-w-2xl max-h-[80vh] overflow-y-auto bg-gray-900 border border-gray-700 rounded-xl p-4"
            variants={modalContent}
            initial="initial"
            animate="animate"
            exit="exit"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              className="absolute top-2 right-3 text-gray-400 hover:text-white text-xl leading-none"
              onClick={onClose}
            >
              &times;
            </button>

            {/* Tabs */}
            <div className="flex gap-2 mb-3">
              <button
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'mine'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                }`}
                onClick={() => {
                  setActiveTab('mine');
                  setFilter('all');
                }}
              >
                My Discard
              </button>
              <button
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'opponent'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                }`}
                onClick={() => {
                  setActiveTab('opponent');
                  setFilter('all');
                }}
              >
                Opponent's Discard
              </button>
            </div>

            {/* Card count header */}
            <div className="text-gray-300 text-sm mb-2">
              {activeTab === 'mine' ? myName : opponentName} &mdash;{' '}
              {sourceCards.length} card{sourceCards.length !== 1 ? 's' : ''} in
              discard
            </div>

            {/* Filter buttons */}
            <div className="flex gap-1.5 mb-4">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    filter === f.key
                      ? 'bg-gray-600 text-white'
                      : 'bg-gray-800 text-gray-500 hover:text-gray-300'
                  }`}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {/* Cards grid */}
            {displayedCards.length === 0 ? (
              <div className="text-gray-500 text-center py-8 text-sm">
                No cards to show.
              </div>
            ) : (
              <div className="flex flex-wrap gap-3 justify-center">
                {displayedCards.map((card) => (
                  <div
                    key={card.id}
                    onMouseEnter={() => onCardHover?.(card)}
                    onMouseLeave={() => onCardHover?.(null)}
                  >
                    <PKMCard card={card} />
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
