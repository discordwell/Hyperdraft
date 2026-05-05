/**
 * PokemonCardDetailModal
 *
 * Full-card overlay for the Pokemon gatherer. Wraps PKMCardDisplay.
 */

import { useEffect } from 'react';
import { usePokemonGathererStore } from '../../stores/pokemonGathererStore';
import { PKMCardDisplay } from './PKMCardDisplay';

export function PokemonCardDetailModal() {
  const { selectedCard, selectCard, currentSet } = usePokemonGathererStore();

  useEffect(() => {
    if (!selectedCard) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') selectCard(null);
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [selectedCard, selectCard]);

  if (!selectedCard) return null;

  return (
    <div
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
      onClick={() => selectCard(null)}
    >
      <div
        className="relative w-full max-w-md bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-5 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={() => selectCard(null)}
          className="absolute -top-3 -right-3 w-8 h-8 bg-stone-800 hover:bg-stone-700 text-white rounded-full flex items-center justify-center shadow-lg z-10 transition-colors"
          aria-label="Close"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {currentSet && (
          <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">
            {currentSet.name} · {currentSet.code}
          </div>
        )}

        <PKMCardDisplay card={selectedCard} />
      </div>
    </div>
  );
}

export default PokemonCardDetailModal;
