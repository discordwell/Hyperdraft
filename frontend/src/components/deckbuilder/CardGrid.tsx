/**
 * CardGrid Component
 *
 * Displays search results in a scrollable grid using SketchCard.
 * Uses simple CSS grid with lazy loading instead of full virtualization
 * for better compatibility.
 */

import { useCallback, useRef, useEffect } from 'react';
import { useDeckbuilderStore } from '../../stores/deckbuilderStore';
import { SketchCard } from '../gatherer/SketchCard';

export function CardGrid() {
  const {
    searchResults,
    searchTotal,
    searchLoading,
    loadMoreCards,
    addCard,
  } = useDeckbuilderStore();

  const containerRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef<HTMLDivElement>(null);

  // Intersection observer for infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (
          entries[0].isIntersecting &&
          !searchLoading &&
          searchResults.length < searchTotal
        ) {
          loadMoreCards();
        }
      },
      { threshold: 0.1 }
    );

    if (loadingRef.current) {
      observer.observe(loadingRef.current);
    }

    return () => observer.disconnect();
  }, [searchLoading, searchResults.length, searchTotal, loadMoreCards]);

  const handleAdd = useCallback(
    (cardName: string) => {
      addCard(cardName);
    },
    [addCard]
  );

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
      {/* Results count */}
      <div className="text-sm text-gray-500 mb-3">
        {searchTotal.toLocaleString()} cards found
      </div>

      {/* Card Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {searchResults.map((card) => (
          <SketchCard
            key={card.name}
            card={card}
            onAdd={handleAdd}
            showAddOverlay
          />
        ))}
      </div>

      {/* Loading indicator / load more trigger */}
      <div ref={loadingRef} className="py-4 text-center">
        {searchLoading && (
          <div className="text-gray-400">Loading more cards...</div>
        )}
        {!searchLoading && searchResults.length < searchTotal && (
          <button
            onClick={() => loadMoreCards()}
            className="text-game-accent hover:underline"
          >
            Load more ({searchTotal - searchResults.length} remaining)
          </button>
        )}
        {!searchLoading && searchResults.length === 0 && (
          <div className="text-gray-500">No cards found matching your filters.</div>
        )}
      </div>
    </div>
  );
}
