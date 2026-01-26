/**
 * Card Detail Modal Component
 *
 * Displays full card details in a modal overlay using the SketchCardDetail component.
 */

import { useEffect } from 'react';
import { useGathererStore } from '../../stores/gathererStore';
import { SketchCardDetail } from './SketchCardDetail';

export function CardDetailModal() {
  const { selectedCard, selectCard, currentSet } = useGathererStore();

  // Close on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        selectCard(null);
      }
    };

    if (selectedCard) {
      document.addEventListener('keydown', handleKeyDown);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
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
        className="relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={() => selectCard(null)}
          className="absolute -top-3 -right-3 w-8 h-8 bg-stone-800 hover:bg-stone-700 text-white rounded-full flex items-center justify-center shadow-lg z-10 transition-colors"
          aria-label="Close"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Card Detail */}
        <SketchCardDetail
          card={selectedCard}
          setCode={currentSet?.code}
          setName={currentSet?.name}
        />
      </div>
    </div>
  );
}

export default CardDetailModal;
